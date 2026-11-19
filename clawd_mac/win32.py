# -*- coding: utf-8 -*-
"""Win32 for the pets on macOS, over AppKit (PyObjC): the contract is clawd_mac/README.md.

install() puts in ctypes what macOS has none of (WinDLL, windll, WINFUNCTYPE, WinError, get_last_error,
set_last_error), so the program's ctypes code runs unchanged.  WinDLL("user32") and the others are the libraries
below; their functions live in the win32_*.py helpers, by area:

  win32_base    the last error, the handle table, how arguments arrive, what is not there yet
  win32_screen  the pixel space, monitors, the work area, system metrics, the cursor
  win32_loop    the NSApplication, posted messages, GetMessageW, timers
  win32_window  classes, windows (NSPanels), UpdateLayeredWindow, the hit-test poll, screen changes, logging out
  win32_input   mouse input into the window procedures, capture, the keys, TrackMouseEvent
  win32_gdi     memory DCs, DIB sections and CreateBitmap
  win32_menu    popup menus
  win32_tray    the tray icon as a status item in the menu bar, and the icons

Importing this makes no NSApplication and no window: the first window, timer or message loop does."""
import ctypes
import importlib
import os

from Foundation import NSLocale

from clawd_mac import lock
from clawd_mac import win32_base as base
from clawd_mac import win32_gdi as gdi
from clawd_mac import win32_input as mouse
from clawd_mac import win32_loop as loop
from clawd_mac import win32_menu as menu
from clawd_mac import win32_screen as screen
from clawd_mac import win32_tray as tray
from clawd_mac import win32_window as window

get_last_error = base.get_last_error
set_last_error = base.set_last_error

LANG_ZH_CN = 0x0804
LANG_EN_US = 0x0409
MODULE_HANDLE = 1           # GetModuleHandleW: the one module there is
STATUS_NOT_IMPLEMENTED = -0x3FFFFFFE    # 0xC0000002 as an NTSTATUS (a LONG)
MESSAGE_FIRST = 0xC000      # RegisterWindowMessageW's ids


# --------------------------------------------------------------------------- errors
class WinOSError(OSError):
    """What ctypes.WinError() gives: an OSError with .winerror, said as Windows says it."""

    def __str__(self):
        return "[WinError %d] %s" % (self.winerror, self.strerror)


def WinError(code=None, descr=None):
    if code is None:
        code = base.get_last_error()
    if descr is None:
        descr = base.MESSAGES.get(code, "Windows error %d" % code)
    e = WinOSError(None, descr)
    e.winerror = code
    return e


# --------------------------------------------------------------------------- kernel32: the process
class Mutex(object):
    """A named mutex handle: holds says it counts towards this process holding the lock (clawd_mac.lock)."""

    def __init__(self, name, holds):
        self.name, self.holds = name, holds


_mutex_refs = {}            # name -> handles open in this process that hold its lock


def CreateMutexW(attributes, initial_owner, name):
    """A named one is clawd_mac.lock's lock of that name.  Already there (another process holds it, or this one has
    it open): last error 183 and still a handle, as on Windows; else last error 0."""
    name = base.text(name)
    if not name:
        base.set_last_error(base.ERROR_SUCCESS)
        return base.new_handle(Mutex(None, False))
    if _mutex_refs.get(name):
        _mutex_refs[name] += 1
        base.set_last_error(base.ERROR_ALREADY_EXISTS)
        return base.new_handle(Mutex(name, True))
    if lock.acquire(name):
        _mutex_refs[name] = 1
        base.set_last_error(base.ERROR_SUCCESS)
        return base.new_handle(Mutex(name, True))
    base.set_last_error(base.ERROR_ALREADY_EXISTS)
    return base.new_handle(Mutex(name, False))


def OpenMutexW(access, inherit, name):
    name = base.text(name)
    if not name or not lock.held(name):
        return base.fail(base.ERROR_FILE_NOT_FOUND)
    return base.new_handle(Mutex(name, False))


def CloseHandle(h):
    """Mutexes only; the last handle of this process to a lock lets go of it."""
    m = base.lookup(h, Mutex)
    if m is None:
        return base.fail(base.ERROR_INVALID_HANDLE)
    base.release(h)
    if m.holds:
        _mutex_refs[m.name] -= 1
        if not _mutex_refs[m.name]:
            del _mutex_refs[m.name]
            lock.release(m.name)
    return 1


def GetModuleHandleW(name):
    return MODULE_HANDLE


def GetUserDefaultUILanguage():
    """Chinese (simplified) when the first preferred language is zh*, else English (US)."""
    langs = list(NSLocale.preferredLanguages() or [])
    return LANG_ZH_CN if langs and str(langs[0]).lower().startswith("zh") else LANG_EN_US


# --------------------------------------------------------------------------- user32: odds and ends
_messages = {}              # RegisterWindowMessageW: name, casefolded -> id


def RegisterWindowMessageW(name):
    name = base.text(name)
    if not name:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    return _messages.setdefault(name.casefold(), MESSAGE_FIRST + len(_messages))


def SetProcessDpiAwarenessContext(context):
    return 1                                   # the pixel space is the screen's own already


def SetProcessDPIAware():
    return 1


def GetWindowThreadProcessId(hwnd, ppid):
    """Our windows: this process and its one thread; other apps' windows are not seen (a later step)."""
    if base.window(hwnd) is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    pid = base.deref(ppid)
    if pid is not None:
        pid.value = os.getpid()
    return 1


# --------------------------------------------------------------------------- the libraries
class Library(object):
    """A DLL as ctypes gives one: its functions are attributes (plain functions: restype and argtypes may be set on
    them); one it has none of raises AttributeError, as ctypes does."""

    def __init__(self, name, functions):
        self._name = name
        self._functions = functions

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        try:
            return self._functions[name]
        except KeyError:
            raise AttributeError("function '%s' not found in %s (clawd_mac.win32)" % (name, self._name))

    def __getitem__(self, name):
        return getattr(self, name)

    def __repr__(self):
        return "<clawd_mac.win32 %s>" % self._name


class StubLibrary(Library):
    """A DLL that means nothing on macOS (imm32, shcore, dwmapi, psapi): every function is there and fails
    harmlessly (0, last error 120)."""

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        fn = self._functions.get(name)
        if fn is None:
            fn = self._functions[name] = base.no_meaning(name)
        return fn


def _pick(module, names):
    return dict((n, getattr(module, n)) for n in names.split())


def _not_yet(names, result=0):
    return dict((n, base.not_yet(n, result)) for n in names.split())


def _merge(*parts):
    out = {}
    for p in parts:
        out.update(p)
    return out


USER32 = Library("user32", _merge(
    _pick(window, "RegisterClassExW UnregisterClassW CreateWindowExW DestroyWindow ShowWindow SetWindowPos "
                  "GetWindowRect UpdateLayeredWindow IsWindow IsWindowVisible IsIconic GetForegroundWindow "
                  "SetForegroundWindow GetClassNameW GetWindowTextLengthW"),
    _pick(loop, "DefWindowProcW GetMessageW TranslateMessage DispatchMessageW PostMessageW PostQuitMessage "
                "SetTimer KillTimer GetMessageTime"),
    _pick(mouse, "SetCapture ReleaseCapture GetCapture GetAsyncKeyState TrackMouseEvent GetDoubleClickTime "
                 "LoadCursorW"),
    _pick(screen, "MonitorFromPoint GetMonitorInfoW SystemParametersInfoW GetSystemMetrics GetCursorPos"),
    _pick(menu, "CreatePopupMenu AppendMenuW DestroyMenu TrackPopupMenu"),
    {"RegisterWindowMessageW": RegisterWindowMessageW, "SetProcessDpiAwarenessContext": SetProcessDpiAwarenessContext,
     "SetProcessDPIAware": SetProcessDPIAware, "GetWindowThreadProcessId": GetWindowThreadProcessId},
    _pick(tray, "CreateIconIndirect DestroyIcon LoadIconW"),
    _not_yet("EnumWindows GetWindow")))
KERNEL32 = Library("kernel32", _merge(
    {"CreateMutexW": CreateMutexW, "OpenMutexW": OpenMutexW, "CloseHandle": CloseHandle,
     "GetModuleHandleW": GetModuleHandleW, "GetUserDefaultUILanguage": GetUserDefaultUILanguage},
    _not_yet("CreateJobObjectW SetInformationJobObject QueryInformationJobObject AssignProcessToJobObject "
             "TerminateJobObject OpenProcess QueryFullProcessImageNameW CreateToolhelp32Snapshot Process32FirstW "
             "Process32NextW")))
GDI32 = Library("gdi32", _merge(
    _pick(gdi, "CreateCompatibleDC DeleteDC CreateDIBSection CreateBitmap SelectObject DeleteObject GdiFlush")))
SHELL32 = Library("shell32", _pick(tray, "Shell_NotifyIconW"))
NTDLL = Library("ntdll", _not_yet("NtResumeProcess", STATUS_NOT_IMPLEMENTED))
LIBRARIES = dict([("user32", USER32), ("kernel32", KERNEL32), ("gdi32", GDI32), ("shell32", SHELL32),
                  ("ntdll", NTDLL)] + [(n, StubLibrary(n, {})) for n in ("imm32", "shcore", "dwmapi", "psapi")])


def _dll_name(name):
    n = os.path.basename(str(name)).lower()
    return n[:-4] if n.endswith(".dll") else n


def WinDLL(name, use_last_error=False, **kw):
    """The shim's library of that name; "gdiplus" is the module clawd_mac.gdiplus, imported now (OSError if it
    cannot be, as for a DLL that is missing); any other name: OSError."""
    key = _dll_name(name)
    lib = LIBRARIES.get(key)
    if lib is not None:
        return lib
    if key == "gdiplus":
        try:
            return importlib.import_module("clawd_mac.gdiplus")
        except ImportError as e:
            raise OSError("gdiplus is not there (clawd_mac.gdiplus: %s)" % e)
    raise OSError("%s: no such library on macOS (clawd_mac.win32)" % name)


class _Loader(object):
    """ctypes.windll: windll.user32 is WinDLL("user32")."""

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return WinDLL(name)

    def __getitem__(self, name):
        return WinDLL(name)

    def LoadLibrary(self, name):
        return WinDLL(name)


windll = _Loader()


def install():
    """ctypes gets WinDLL, windll, WINFUNCTYPE (= CFUNCTYPE), WinError, get_last_error and set_last_error, each
    only if it has none; calling it again changes nothing."""
    for name, value in (("WinDLL", WinDLL), ("windll", windll), ("WINFUNCTYPE", ctypes.CFUNCTYPE),
                        ("WinError", WinError), ("get_last_error", get_last_error),
                        ("set_last_error", set_last_error)):
        if not hasattr(ctypes, name):
            setattr(ctypes, name, value)
