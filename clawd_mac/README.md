# clawd_mac: the Windows parts, on macOS

`clawd_pet.pyw` talks to Windows through ctypes (`WinDLL("user32")`, `WINFUNCTYPE`, `get_last_error`, ...). On
macOS the block at its top calls `clawd_mac.win32.install()`, and from then on the same code runs over AppKit
(PyObjC): every Win32 function it uses is a Python function of the same name that does the same thing with a Cocoa
window, an NSTimer, an NSMenu or a status item in the menu bar. So the program's Win32 code runs as it is. What
Windows gives it outside these calls (the registry, Job Objects, `os.startfile`, PowerShell, other programs' windows,
`%APPDATA%`) has a `sys.platform == "darwin"` branch in the program itself, which uses `system.py` and `lock.py`.

Needs PyObjC (AppKit, Quartz, Foundation; tested with 13.0) on Python 3.

| File | What is in it |
| --- | --- |
| `win32.py` | `install()`, `WinDLL` / `windll`, `WinError`, the libraries, named mutexes, odds and ends |
| `win32_base.py` | the last error, the handle table, how arguments arrive, the stubs |
| `win32_screen.py` | the pixel space, monitors, the work area, system metrics, the cursor |
| `win32_loop.py` | the NSApplication, posted messages, `GetMessageW`, timers |
| `win32_window.py` | classes, windows (NSPanels), `UpdateLayeredWindow`, hit-testing, screen changes, logging out |
| `win32_input.py` | mouse events into the window procedures, the capture, the keys, `TrackMouseEvent`, the cursor |
| `win32_gdi.py` | memory DCs, DIB sections, `CreateBitmap` |
| `win32_menu.py` | popup menus |
| `win32_tray.py` | the tray icon as a status item in the menu bar, and the icons it shows |
| `win32_synthetic.py` | tests only: synthetic mouse and wheel events for our own windows |
| `gdiplus.py` | the GDI+ flat API the program uses (sign boards, scaling frames, `clawd_scale.py`), over Quartz and CoreText with plain ctypes: no PyObjC, so it also runs under `python -I -S` and without a window server |
| `lock.py` | named single-instance locks (what a named mutex is on Windows) |
| `system.py` | what is not Win32: where the saves and caches live, the UI language, start at login (a LaunchAgent), the pet's processes, other apps (running, in front, brought forward), the app bundle and App Translocation |

`import clawd_mac.win32` makes no NSApplication and no window, and does not import `clawd_mac.gdiplus`: the first
window, timer or message loop makes the app; `WinDLL("gdiplus")` imports gdiplus.

## The contract

### ctypes

`install()` sets `ctypes.WinDLL`, `ctypes.windll`, `ctypes.WINFUNCTYPE` (= `CFUNCTYPE`), `ctypes.WinError`,
`ctypes.get_last_error` and `ctypes.set_last_error`, each only if ctypes has none, so calling it twice, or on
Windows, changes nothing.

- `WinDLL(name, use_last_error=False, **kw)`: the name is matched without its folder, `.dll` and case.
  `user32`, `kernel32`, `gdi32`, `shell32`, `ntdll` are the shim's libraries; a function one of them does not have
  raises `AttributeError`, as ctypes does. `imm32`, `shcore`, `dwmapi`, `psapi` mean nothing on macOS: any function
  of theirs is there and fails quietly (0, last error 120). `gdiplus` is the module `clawd_mac.gdiplus`, imported at
  that call (`OSError` if it cannot be). Any other name: `OSError`, as for a DLL that is not there.
- `WinError(code=None, descr=None)`: an `OSError` with `.winerror` (the last error if no code), printed as
  `[WinError n] text`.
- `get_last_error()` / `set_last_error(v)`: per thread; `set_last_error` returns the value before. Every shim
  function that fails sets it, with the Windows code (1400 invalid window handle, 183 already exists, ...).

### Calling convention

The functions are plain Python functions. `_api()` in the program sets `restype` and `argtypes` on them; that is
allowed and changes nothing. So an argument arrives as the caller wrote it: an int, `None`, a `str`, a ctypes
instance (`c_void_p(h)`), `ctypes.byref(x)` (the shim uses `x`), a pointer (`.contents`), an array or a structure.
Structures are read and written by field name (`msg.hwnd`, `rc.left`), never by Windows' byte layout, so the
program's own `MSG`, `RECT`, `BITMAPINFO`, ... work as they are (`LONG` is 8 bytes here; nothing depends on it).
Results are plain ints: BOOL 1 or 0, handles non-zero ints.

A window procedure is the program's `WNDPROC` (a `CFUNCTYPE` callback, kept alive by the program). The shim calls
it from Python, with Python ints: `wndproc(hwnd, msg, wparam, lparam)`. An exception in it is told on stderr and
never reaches AppKit.

### Handles

One table for all of them: windows, menus, DCs, bitmaps, mutexes, monitors, cursors. Handles are ints from 0x10000
up in steps of 4, never reused while the object lives. `None`, 0 and a `c_void_p` of 0 are "no handle"; negative
ints (`HWND_TOPMOST` = -1) keep their Windows meaning. A handle of the wrong kind fails as an invalid one would.
`GetModuleHandleW` is 1, the one module there is.

### Memory

`CreateDIBSection` makes a ctypes buffer of w x h x 4 bytes (32 bpp only: premultiplied BGRA, rows top-down for a
negative `biHeight`, bottom-up otherwise) and writes its address into `ppvBits`. The program `memmove`s into it,
`clawd_mac.gdiplus` draws into it by address, and `UpdateLayeredWindow` copies out of it. The buffer lives until
`DeleteObject`, which fails while the bitmap is still selected into a DC, as on Windows. A memory DC starts with a
1 x 1 stock bitmap selected, which `SelectObject` hands back. `CreateBitmap(w, h, 1, bpp, bits)` makes a bitmap of
1 bpp (an icon's mask) or 32 bpp from rows top-down, each a whole number of WORDs, as Windows reads them; it is for
icons, never what a layered window shows.

### Coordinates

One pixel space for every coordinate the program sees: virtual px = points x S, S being the main screen's
`backingScaleFactor` when first asked (2 on a Retina Mac), for every screen alike. The origin is the top-left corner
of the primary screen (the one with the menu bar), y grows downward, as Windows' virtual screen. Cocoa's points have
their origin at the primary screen's bottom-left, y up, so y flips through the primary screen's height H0:

    x_px = x_pt * S        y_px = (H0 - y_pt) * S
    x_pt = x_px / S        y_pt = H0 - y_px / S

`GetSystemMetrics(SM_CXSCREEN / SM_CYSCREEN)` is the primary screen in px, the virtual-screen metrics the union
of all. `MonitorFromPoint` / `GetMonitorInfoW` give each screen's frame and work area (its `visibleFrame`: without
the menu bar and the Dock); a monitor's handle stays the same while the screen is there. `SystemParametersInfoW` has
only `SPI_GETWORKAREA` (the primary's work area). `GetCursorPos` is `NSEvent.mouseLocation` in px. The program's
DPI calls succeed and change nothing: the pixel space is already the screen's own. A picture drawn 1:1 is crisp on a
screen whose scale is S and scaled by the window server on the others.

### Windows

Every HWND is a borderless, non-activating NSPanel that never becomes key or main: clear, no shadow, on every Space
(also beside a full-screen app), out of the window cycle, not hidden with the app. `WS_EX_TOPMOST` puts it on the
floating level. Its content view hosts a CALayer whose contents are the picture. The rectangle is kept in px and the
panel's frame follows it, so `GetWindowRect` gives back exactly what was set. `SetWindowPos` moves, sizes, shows,
hides and orders (`HWND_TOP`, `HWND_TOPMOST`, `HWND_BOTTOM`, or just behind a given window); `HWND_NOTOPMOST` does
not move it off the floating level. `ShowWindow` shows without activating (minimized is hidden).
`SetForegroundWindow` on our own window succeeds without taking the focus from the user's app.

`UpdateLayeredWindow(hwnd, None, pptDst, psize, hdcSrc, pptSrc, 0, pblend, ULW_ALPHA)`: the window moves to
`pptDst` (`None`: stays), takes `psize`, and shows the `psize` pixels at `pptSrc` of the bitmap selected into
`hdcSrc`, copied into a CGImage (premultiplied first, 32-bit little-endian, sRGB) with `contentsScale` = S;
`SourceConstantAlpha` is the panel's `alphaValue`. The picture shows at once (no implicit animation).

`DestroyWindow` sends `WM_DESTROY` while the window still is one, kills its timers, takes the capture from it and
closes the panel. After a change of screens every window gets `WM_DISPLAYCHANGE`; when the Mac logs out or shuts
down, `WM_QUERYENDSESSION` and then `WM_ENDSESSION` (1).

### Message loop and timers

The NSApplication is an accessory app (no Dock icon, no menu bar), kept out of App Nap so its timers keep their
pace while its windows are hidden, as Windows' timers do. `GetMessageW` pumps NSApp's events until a message has
been posted: `PostMessageW` puts it in the queue (from any thread) and wakes the pump with an application-defined
event (not while a menu tracks: see Menus); `PostQuitMessage` makes `WM_QUIT` come after every message posted before
it, and `GetMessageW` then returns 0. `DispatchMessageW` calls the window's procedure; a message for no window, or
one gone since, is dropped. The filters of `GetMessageW` are not looked at.

Input and timers do not go through the queue: AppKit's callbacks call the window procedure directly, as
`SendMessage` would. `SetTimer(hwnd, id, ms, None)` is a repeating NSTimer in `NSRunLoopCommonModes` (at least 10 ms,
as on Windows) that sends `WM_TIMER` (wparam id), so timers fire in `GetMessageW`, while a menu is up and while a
button is held, as they do in Windows' modal loops. Setting the same (hwnd, id) again replaces it; `KillTimer` and
`DestroyWindow` stop it. `GetMessageTime` is the time of the message being handled (an input event's own time),
in ms on the clock of `time.monotonic()`, as a signed 32-bit value.

### Hit-testing

A layered window takes the mouse only where its picture is not transparent, as on Windows. A poll (40 Hz, only
while a visible layered window is there) looks at the pixel under the cursor in the picture last shown: alpha > 0,
the panel takes the mouse; else it lets it through (`ignoresMouseEvents`) to whatever is below. A window with a
button held on it, or with the capture, keeps what it has until the button is up. `WS_EX_TRANSPARENT` windows never
take the mouse. A hover move that arrives over a transparent pixel anyway is not sent, and the panel lets go.

### Mouse input

The view of each window turns AppKit's events into the window procedure's messages: `WM_MOUSEMOVE`, `WM_L/R/M
BUTTONDOWN/UP` (`WM_LBUTTONDBLCLK` only for a class with `CS_DBLCLKS`), `WM_MOUSEWHEEL`, and `WM_MOUSELEAVE` (posted,
once, after `TrackMouseEvent(TME_LEAVE)`, when the cursor leaves the window's opaque pixels). The point is in client
px (signed 16-bit x and y in lparam), taken from where the event happened, not from where the window is now; wparam
has the `MK_` flags (Control or Command is `MK_CONTROL`). A Control+click is a right click, as everywhere on macOS:
`WM_RBUTTONDOWN` / `WM_RBUTTONUP` (its up too if Control is let go first), its drag with `MK_RBUTTON`, and the
Control in it is no `MK_CONTROL`; Control+wheel stays `MK_CONTROL`. The wheel's delta is in `WHEEL_DELTA` units in
wparam's high word, positive away from the user whatever "natural scrolling" says (a trackpad's points are counted as
a wheel's lines, 3 points a line), with lparam in screen px.

The cursor is the window class's (`hCursor` from `LoadCursorW`) while the pointer is over the window's opaque
pixels or a button is down on it: `IDC_HAND` the pointing hand, `IDC_SIZEALL` the open hand, `IDC_ARROW` and every
other the arrow; once the pointer is off them, the arrow again (the hit-test poll sets it too, so a pet moving under
a still pointer changes it). The program never changes it while dragging (no `SetCursor`), so neither does the shim.

`SetCapture` makes a window get the mouse wherever it is; the window that loses it gets `WM_CAPTURECHANGED` (lparam
the new owner). `GetAsyncKeyState` has the mouse buttons and Shift, Control and Option as they are now.

### Menus

`CreatePopupMenu` / `AppendMenuW` (`MF_STRING`, `MF_POPUP`, `MF_SEPARATOR`, `MF_GRAYED`, `MF_DISABLED`,
`MF_CHECKED`) / `DestroyMenu` (with its submenus) build a menu; `TrackPopupMenu` shows it as a modal NSMenu whose
top-left corner is at the point given (within 0.5 s of a click on a status item: under that item, see The tray
icon) and returns, with `TPM_RETURNCMD`, the id of the item chosen or 0; without it 1 or 0, and a `WM_COMMAND`
posted unless `TPM_NONOTIFY`. Labels lose the `&` of the accelerator (`&&` is `&`) and what follows a tab.

While it is up, as in Windows' menu loop, timers fire and posted messages are dispatched to their window
procedures, in order, by a 10 ms timer in the common modes (no wake events then: an application-defined event that
comes while a menu tracks can close it); messages posted as it closes are dispatched before it returns. A `WM_QUIT` posted meanwhile closes the menu and stays for `GetMessageW`. One menu
at a time: `TrackPopupMenu` while one is up fails with 1446 (`ERROR_POPUP_ALREADY_ACTIVE`).

### The tray icon

`Shell_NotifyIconW(NIM_ADD | NIM_MODIFY | NIM_DELETE, &NOTIFYICONDATAW)` keeps one status item in the menu bar
(`NSVariableStatusItemLength`) per (`hWnd`, `uID`): `NIM_ADD` makes it (0, last error 183, if it is there already;
1400 if `hWnd` is no window of ours), `NIM_MODIFY` changes it and `NIM_DELETE` removes it (both 0, last error 2, if
it is not there). `NIF_ICON` sets its picture, `NIF_TIP` its tooltip (`szTip`), `NIF_MESSAGE` what a click posts.

A click posts `(uCallbackMessage, wparam uID, lparam mouse message)` to `hWnd`, the macOS way round: a click, a
right click or a Control+click is `WM_RBUTTONUP` (the program's tray menu), Option+click `WM_LBUTTONUP` (Windows'
left click: hide or show). Only the up is posted. A `TrackPopupMenu` within 0.5 s of the click opens the menu under
the item, at its left edge, and highlights the item while it is up, as the menu bar's own menus do. On macOS 26 and
later the system draws status items in a process of its own and the item's window here is not where it shows, so its
left edge is taken as where the pointer was at the click less how far into the button the click was, and the menu's
top as the bottom of the menu bar on the pointer's screen. `RegisterWindowMessageW("TaskbarCreated")` has its id, but
the menu bar never restarts under the app: it is never sent.

`CreateIconIndirect(ICONINFO)` copies the colour bitmap (`hbmColor`: a DIB section or a `CreateBitmap` one, 32 bpp,
straight alpha as Windows' icons have it; the program un-premultiplies its frames for it) and the mask (1 bpp, a set
bit transparent, used only when the colour bitmap has no alpha at all), so the bitmaps can be deleted at once, as the
program does. In the menu bar the icon is an NSImage of its own pixels (an `NSBitmapImageRep` of the icon's size)
drawn at the bar's thickness less 4 points, square icons square, not a template: Clawd keeps its colours.
`LoadIconW(None, IDI_*)` is the app's icon, one shared handle per name; `DestroyIcon` frees an icon (a shared one
stays); a status item showing it keeps its picture.

### Process

A named mutex is a `clawd_mac.lock` lock of that name (a flocked file under `~/Library/Caches/Clawd/locks`, let go
when the process ends however it ends). `CreateMutexW` returns a handle and leaves last error 183 when another
process holds the lock or this one has it open already, 0 when it took it; `CloseHandle` of this process's last
handle to it lets go. `OpenMutexW` finds a lock some process holds. `GetUserDefaultUILanguage` is Chinese
(simplified) when the first preferred language is Chinese, else English. `RegisterWindowMessageW` gives one id per
name (from 0xC000).

### What is still a stub

These fail as a Win32 call fails (0, last error 120) and say so on stderr the first time:
`EnumWindows`, `GetWindow`, the Job Object calls (`CreateJobObjectW`, `SetInformationJobObject`,
`QueryInformationJobObject`, `AssignProcessToJobObject`, `TerminateJobObject`), `OpenProcess`,
`QueryFullProcessImageNameW`, `CreateToolhelp32Snapshot`, `Process32FirstW`, `Process32NextW`; `NtResumeProcess`
returns `STATUS_NOT_IMPLEMENTED`. `GetWindowThreadProcessId`, `IsWindowVisible`, `GetClassNameW` and
`GetWindowTextLengthW` know our own windows only.

## Tests

    python -m pytest clawd_mac/tests -q

`test_win32.py` makes windows, timers and menus with the program's own structures and bindings and checks them;
`test_win32_tray.py` does the same for the status item (`Tray._icon`'s icons, `NOTIFYICONDATAW`, clicks), Control+
click, the cursor and the messages posted while a menu is up;
`test_win32_pet.py` runs `clawd_pet.pyw`'s `main()` in the test process (frames from `CLAWD_TEST_FRAMES`, a
fresh home) and drives its window: a drag, its menu, Control+wheel, then `quit` in the event file. Input comes from
`win32_synthetic`: NSEvents made in the process and handed to one of our own windows (`sendEvent_`, a scroll
straight to its view), so nothing is posted to the system and the real mouse is left alone. Menus are chosen from or
closed by a timer while they track (`win32_menu.tracking()`); `win32_window.presented(hwnd)` reads back what a
window shows.

## Done in the program, not here

These are not emulated; `clawd_pet.pyw` (and `clawd.py`, `clawd_scale.py`) do them their macOS way in their darwin
branches:

- Start at login: a LaunchAgent (`system.py`) instead of the registry's Run key, "Open at Login" in the menus.
- Re-rendering a size: `clawd_scale.py` under `nice`, in a process group of its own that the pet stops when it
  quits, and that stops itself when the pet is gone (what the kill-on-close Job Object does on Windows).
- Finding a conversation's window: the hook's `at` line has, on macOS, the pid of the app the agent runs in and its
  terminal's tty, so the pet asks `system.py` about that app (still running, which app, brought forward) and
  switches Terminal's or iTerm2's tab by its tty with `osascript`. Other apps' windows (`EnumWindows`, `GetWindow`,
  the process calls) stay stubs.
- Links and pages: `/usr/bin/open`.

## Not yet

- The cursor while the app is in the background: AppKit lets the frontmost app set the cursor; the shim sets the
  hand over a pet, but whether the window server shows it while another app is frontmost is up to macOS.
- Keyboard input, thread timers and timer procedures (`SetTimer(..., proc)`), `GetMessageW`'s filters.
- Screens of different scales: one S for all, so on a screen whose scale is not S the window server scales the
  picture (soft on a Retina screen when the main screen is not one).
