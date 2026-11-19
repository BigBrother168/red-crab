# -*- coding: utf-8 -*-
"""clawd_mac.win32: the Win32 subset the pets use, over AppKit.  The calls are those of clawd_pet.pyw itself (its
structures, its _api bindings), on windows of this process only; input is synthetic NSEvents handed to those
windows, never anything posted to the system."""
import ctypes
import importlib.machinery
import importlib.util
import itertools
import os
import subprocess
import sys
import textwrap
import time

import pytest
from AppKit import NSRunLoop, NSRunLoopCommonModes, NSTimer

from clawd_mac import lock
from clawd_mac import win32
from clawd_mac import win32_base as base
from clawd_mac import win32_loop as loop
from clawd_mac import win32_menu as menu
from clawd_mac import win32_screen as screen
from clawd_mac import win32_synthetic as synth
from clawd_mac import win32_window as window

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PET_PATH = os.path.join(ROOT, "clawd_pet.pyw")
WM_USER = 0x0400
WM_COMMAND = 0x0111
LAYERED = 0x00080000 | 0x00000008 | 0x00000080 | 0x08000000     # what the pets' windows are
_names = itertools.count(1)

win32.install()


def load_pet(name):
    """clawd_pet.pyw as a module of its own (nothing runs but its top level)."""
    loader = importlib.machinery.SourceFileLoader(name, PET_PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pet():
    return load_pet("clawd_pet_for_win32_tests")


def later(secs, fn):
    """fn() once, secs from now, from an NSTimer in the common modes (so also while a menu tracks).  Whatever fn
    returns is dropped: the block is void, and PyObjC refuses a value from it."""

    def fire(timer):
        fn()

    t = NSTimer.timerWithTimeInterval_repeats_block_(secs, False, fire)
    NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
    return t


class Recorder(object):
    """A window procedure that writes down what it gets (and can answer some messages with a function)."""

    def __init__(self):
        self.calls = []
        self.on = {}

    def __call__(self, hwnd, msg, wparam, lparam):
        self.calls.append((hwnd, msg, wparam, lparam))
        fn = self.on.get(msg)
        return fn(hwnd, msg, wparam, lparam) if fn else 0

    def of(self, msg, hwnd=None):
        return [c for c in self.calls if c[1] == msg and (hwnd is None or c[0] == hwnd)]


class Kit(object):
    """A window class of the test's own (registered as Family registers CLASS_NAME), and the windows made with it."""

    def __init__(self, pet):
        self.pet = pet
        self.rec = Recorder()
        self.proc = pet.WNDPROC(self.rec)
        self.name = "ClawdTest%d" % next(_names)
        self.hinst = pet.GetModuleHandleW(None)
        wc = self.wc = pet.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(pet.WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self.proc
        wc.hInstance = self.hinst
        wc.hCursor = pet.LoadCursorW(None, pet.IDC_HAND)
        wc.lpszClassName = self.name
        assert pet.RegisterClassExW(ctypes.byref(wc))
        self.gdi = []

    def window(self, x, y, w, h, ex=LAYERED, title="test"):
        hwnd = self.pet.CreateWindowExW(ex, self.name, title, self.pet.WS_POPUP, x, y, w, h, None, None, self.hinst,
                                        None)
        assert hwnd
        return hwnd

    def layered(self, x, y, w, h, raw, show=True):
        """A layered window showing raw (top-down premultiplied BGRA), made as Pet._create_window makes one."""
        p = self.pet
        memdc = p.CreateCompatibleDC(None)
        bmi = p.BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(p.BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = p.BI_RGB
        bits = p.LPVOID()
        hbmp = p.CreateDIBSection(memdc, ctypes.byref(bmi), p.DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        assert hbmp and bits.value
        p.GdiFlush()
        stock = p.SelectObject(memdc, hbmp)
        self.gdi.append((memdc, hbmp, stock))
        ctypes.memmove(bits.value, raw, len(raw))
        hwnd = self.window(x, y, w, h)
        blend = p.BLENDFUNCTION(p.AC_SRC_OVER, 0, 255, p.AC_SRC_ALPHA)
        assert p.UpdateLayeredWindow(hwnd, None, ctypes.byref(p.POINT(x, y)), ctypes.byref(p.SIZE(w, h)), memdc,
                                     ctypes.byref(p.POINT(0, 0)), 0, ctypes.byref(blend), p.ULW_ALPHA)
        if show:
            p.ShowWindow(hwnd, p.SW_SHOWNOACTIVATE)
            p.SetWindowPos(hwnd, p.HWND_TOPMOST, 0, 0, 0, 0, p.SWP_NOMOVE | p.SWP_NOSIZE | p.SWP_NOACTIVATE)
        return hwnd, memdc, bits.value

    def close(self):
        p = self.pet
        for hwnd in window.find_windows():
            if base.window(hwnd).cls.name == self.name:
                p.DestroyWindow(hwnd)
        for memdc, hbmp, stock in self.gdi:
            p.SelectObject(memdc, stock)
            p.DeleteDC(memdc)
            assert p.DeleteObject(hbmp)
        p.UnregisterClassW(self.name, self.hinst)


@pytest.fixture
def kit(pet):
    k = Kit(pet)
    yield k
    k.close()


def place(dx=60, dy=60):
    """A spot inside the primary screen's work area."""
    l, t, r, b = screen.screens()[0].work
    return l + dx, t + dy


def picture(w, h, opaque_cols):
    """Opaque red where x < opaque_cols, transparent elsewhere (premultiplied BGRA, top-down)."""
    row = b"\x00\x00\xff\xff" * opaque_cols + b"\x00\x00\x00\x00" * (w - opaque_cols)
    return row * h


def lo_hi(v):
    return ctypes.c_short(v & 0xFFFF).value, ctypes.c_short((v >> 16) & 0xFFFF).value


# --------------------------------------------------------------------------- ctypes and the libraries
def test_import_makes_no_app_and_no_window():
    code = textwrap.dedent("""
        import os, sys
        sys.path.insert(0, %r)
        import AppKit, Quartz
        from clawd_mac import win32
        assert AppKit.NSApp() is None, "an NSApplication on import"
        win32.install()
        assert AppKit.NSApp() is None, "an NSApplication from install()"
        mine = [w for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
                if w["kCGWindowOwnerPID"] == os.getpid()]
        assert not mine, mine
        assert "clawd_mac.gdiplus" not in sys.modules
        print("ok")
    """ % ROOT)
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "ok", out.stderr


def test_install_is_idempotent_and_adds_only_what_ctypes_lacks(monkeypatch):
    names = ("WinDLL", "windll", "WINFUNCTYPE", "WinError", "get_last_error", "set_last_error")
    for n in names:
        monkeypatch.delattr(ctypes, n, raising=False)
    theirs = object()
    monkeypatch.setattr(ctypes, "WinError", theirs, raising=False)
    win32.install()
    first = dict((n, getattr(ctypes, n)) for n in names)
    win32.install()
    assert all(getattr(ctypes, n) is first[n] for n in names)
    assert ctypes.WinError is theirs
    assert ctypes.WinDLL is win32.WinDLL and ctypes.windll is win32.windll
    assert ctypes.WINFUNCTYPE is ctypes.CFUNCTYPE
    assert ctypes.get_last_error is win32.get_last_error and ctypes.set_last_error is win32.set_last_error


def test_libraries_as_ctypes_gives_them():
    with pytest.raises(OSError):
        ctypes.WinDLL("nope")
    with pytest.raises(OSError):
        ctypes.windll.nope
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    assert user32 is ctypes.windll.user32 is ctypes.WinDLL("USER32.dll")
    with pytest.raises(AttributeError):
        user32.NoSuchFunction
    fn = user32.ShowWindow
    fn.restype, fn.argtypes = ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]      # what _api does: allowed
    imm = ctypes.WinDLL("imm32")
    ctypes.set_last_error(0)
    assert imm.ImmDisableIME(0xFFFFFFFF) == 0 and ctypes.get_last_error() == 120
    for name in ("shcore", "dwmapi", "psapi"):
        assert getattr(ctypes.WinDLL(name), "AnyFunction")() == 0


def test_gdiplus_is_imported_only_when_asked_for():
    try:
        there = importlib.util.find_spec("clawd_mac.gdiplus") is not None
    except ImportError:
        there = False
    if there:
        assert ctypes.WinDLL("gdiplus") is importlib.import_module("clawd_mac.gdiplus")
    else:
        with pytest.raises(OSError):
            ctypes.WinDLL("gdiplus")


def test_not_yet_fails_as_win32_and_says_so_once(capsys):
    kernel32 = ctypes.WinDLL("kernel32")
    ctypes.set_last_error(0)
    assert kernel32.OpenProcess(0x1000, 0, os.getpid()) == 0 and ctypes.get_last_error() == 120
    kernel32.OpenProcess(0x1000, 0, os.getpid())
    err = capsys.readouterr().err
    assert err.count("OpenProcess") <= 1               # once per process (an earlier test may have said it)
    assert ctypes.windll.kernel32.CreateToolhelp32Snapshot(2, 0) == 0
    assert ctypes.windll.user32.EnumWindows(None, 0) == 0
    assert ctypes.windll.ntdll.NtResumeProcess(0) != 0     # an NTSTATUS: 0 would be success


def test_win_error_and_the_last_error_are_per_thread():
    e = ctypes.WinError(1400)
    assert isinstance(e, OSError) and e.winerror == 1400 and "[WinError 1400]" in str(e)
    ctypes.set_last_error(183)
    assert ctypes.WinError().winerror == 183
    assert ctypes.set_last_error(5) == 183
    import threading
    seen = []
    t = threading.Thread(target=lambda: seen.append(ctypes.get_last_error()))
    t.start()
    t.join()
    assert seen == [0] and ctypes.get_last_error() == 5


def test_startup_calls_of_the_pets_change_nothing(pet):
    pet.disable_ime()
    pet.set_dpi_awareness()
    assert pet.GetModuleHandleW(None) == 1
    assert pet.system_lang() in ("zh", "en")
    assert ctypes.windll.kernel32.GetUserDefaultUILanguage() in (0x0804, 0x0409)
    tc = pet.RegisterWindowMessageW("TaskbarCreated")
    assert tc >= 0xC000 and pet.RegisterWindowMessageW("taskbarcreated") == tc
    assert pet.RegisterWindowMessageW("SomethingElse") not in (0, tc)
    assert pet.GetDoubleClickTime() > 0 and pet.LoadCursorW(None, pet.IDC_HAND)
    assert pet.GetSystemMetrics(pet.SM_SWAPBUTTON) == 0 and pet.GetSystemMetrics(pet.SM_CXSMICON) > 0
    pt = pet.POINT()
    assert pet.GetCursorPos(ctypes.byref(pt))


def test_named_mutexes_are_locks(tmp_path, monkeypatch, pet):
    monkeypatch.setattr(lock, "lock_dir", lambda: str(tmp_path))
    name = "Local\\ClawdWin32Test"
    m1 = pet.CreateMutexW(None, False, name)
    assert m1 and ctypes.get_last_error() == 0 and lock.held(name)
    m2 = pet.CreateMutexW(None, False, name)
    assert m2 and ctypes.get_last_error() == pet.ERROR_ALREADY_EXISTS
    h = pet.OpenMutexW(0x00100000, False, name)
    assert h
    assert pet.CloseHandle(h) and pet.CloseHandle(m1)
    assert lock.held(name)                              # m2 still has it
    assert pet.CloseHandle(m2) and not lock.held(name)
    assert not pet.OpenMutexW(0x00100000, False, name) and ctypes.get_last_error() == 2
    assert not pet.CloseHandle(m2) and ctypes.get_last_error() == 6


# --------------------------------------------------------------------------- the pixel space
def test_points_and_virtual_pixels_round_trip_with_the_y_flip():
    s = screen.scale()
    h0 = screen.primary_height()
    assert screen.to_pixels(0, h0) == (0, 0)                     # the primary's top-left corner
    assert screen.to_pixels(0, 0) == (0, h0 * s)                  # its bottom-left
    for x, y in ((0, 0), (17, 33), (-250, 1200), (3000.5, -40)):
        px, py = screen.to_pixels(*screen.to_points(x, y))
        assert abs(px - x) < 1e-9 and abs(py - y) < 1e-9
    f = screen.frame_of(100, 200, 40, 60)
    assert (f.origin.x, f.origin.y, f.size.width, f.size.height) == (100 / s, h0 - 260 / s, 40 / s, 60 / s)


def test_monitors_and_the_work_area(pet):
    prim = screen.screens()[0]
    l, t, r, b = prim.frame
    assert (l, t) == (0, 0)
    assert pet.GetSystemMetrics(0) == r and pet.GetSystemMetrics(1) == b
    hmon = pet.MonitorFromPoint(pet.POINT(r // 2, b // 2), pet.MONITOR_DEFAULTTONULL)
    assert hmon == pet.MonitorFromPoint(pet.POINT(5, 5), pet.MONITOR_DEFAULTTONEAREST)
    mi = pet.MONITORINFO()
    mi.cbSize = ctypes.sizeof(pet.MONITORINFO)
    assert pet.GetMonitorInfoW(hmon, ctypes.byref(mi))
    assert (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom) == prim.frame
    assert (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom) == prim.work
    assert mi.dwFlags == 1 and mi.rcWork.top >= mi.rcMonitor.top and mi.rcWork.bottom <= mi.rcMonitor.bottom
    wa = pet.RECT()
    assert pet.SystemParametersInfoW(pet.SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
    assert (wa.left, wa.top, wa.right, wa.bottom) == prim.work
    assert pet.Pet._work_area().bottom == prim.work[3]
    assert not pet.MonitorFromPoint(pet.POINT(-10 ** 6, -10 ** 6), pet.MONITOR_DEFAULTTONULL)
    assert pet.MonitorFromPoint(pet.POINT(-10 ** 6, -10 ** 6), pet.MONITOR_DEFAULTTONEAREST)


# --------------------------------------------------------------------------- messages and timers
def test_posted_messages_come_in_order_and_quit_last(kit, pet):
    hw = kit.window(*place(), w=10, h=10)
    assert pet.PostMessageW(hw, WM_USER + 1, 1, 2)
    pet.PostQuitMessage(7)
    assert pet.PostMessageW(hw, WM_USER + 2, 3, 4)
    msg = pet.MSG()
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 1
    assert (msg.hwnd, msg.message, msg.wParam, msg.lParam) == (hw, WM_USER + 1, 1, 2)
    pet.TranslateMessage(ctypes.byref(msg))
    pet.DispatchMessageW(ctypes.byref(msg))
    assert kit.rec.of(WM_USER + 1) == [(hw, WM_USER + 1, 1, 2)]
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 1 and msg.message == WM_USER + 2
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 0
    assert msg.message == 0x0012 and msg.wParam == 7
    assert not pet.PostMessageW(0x7FFF0000, WM_USER, 0, 0) and ctypes.get_last_error() == 1400


def test_a_timer_fires_wm_timer_and_kill_stops_it(kit, pet):
    hw = kit.window(*place(), w=10, h=10)
    assert pet.SetTimer(hw, 5, 20, None)
    assert pet.SetTimer(hw, 5, 15, None)               # again: it replaces the one before
    assert loop.timers().count((hw, 5)) == 1
    end = time.monotonic() + 3.0                       # a busy (virtual) Mac fires late: wait for 8, up to 3 s
    while len(kit.rec.of(pet.WM_TIMER)) < 8 and time.monotonic() < end:
        loop.run_for(0.05)
    n = len(kit.rec.of(pet.WM_TIMER))
    assert n >= 8 and all(c[2] == 5 for c in kit.rec.of(pet.WM_TIMER))
    assert pet.KillTimer(hw, 5)
    loop.run_for(0.15)
    assert len(kit.rec.of(pet.WM_TIMER)) == n and not pet.KillTimer(hw, 5)


def test_a_quit_posted_from_a_timer_wakes_get_message(kit, pet):
    hw = kit.window(*place(), w=10, h=10)

    def tick(hwnd, msg, wparam, lparam):
        if len(kit.rec.of(pet.WM_TIMER)) == 3:
            pet.KillTimer(hwnd, 1)
            pet.PostQuitMessage(0)
        return 0
    kit.rec.on[pet.WM_TIMER] = tick
    pet.SetTimer(hw, 1, 10, None)
    msg = pet.MSG()
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 0 and len(kit.rec.of(pet.WM_TIMER)) == 3


def test_destroy_window_says_wm_destroy_while_still_a_window(kit, pet):
    hw = kit.window(*place(), w=10, h=10)
    pet.SetTimer(hw, 1, 50, None)
    during = []
    kit.rec.on[pet.WM_DESTROY] = lambda h, m, w, l: during.append(pet.IsWindow(h)) or 0
    assert pet.DestroyWindow(hw) and during == [1]
    assert not pet.IsWindow(hw) and (hw, 1) not in loop.timers()
    assert not pet.DestroyWindow(hw) and ctypes.get_last_error() == 1400


def test_classes_register_once(kit, pet):
    assert not pet.RegisterClassExW(ctypes.byref(kit.wc)) and ctypes.get_last_error() == 1410
    assert not pet.CreateWindowExW(0, "ClawdNoSuchClass", "x", 0, 0, 0, 1, 1, None, None, 1, None)
    buf = ctypes.create_unicode_buffer(64)
    hw = kit.window(*place(), w=10, h=10, title="Clawd test")
    assert pet.window_class(hw) == kit.name and pet.GetClassNameW(hw, buf, 64) == len(kit.name)
    assert ctypes.windll.user32.GetWindowTextLengthW(hw) == len("Clawd test")


# --------------------------------------------------------------------------- what a layered window shows
def test_layered_window_shows_its_pixels_and_takes_the_mouse_where_they_are_opaque(kit, pet):
    x, y = place()
    w, h = 64, 48
    raw = picture(w, h, 40)
    hw, memdc, bits = kit.layered(x, y, w, h, raw)
    assert window.presented(hw) == (w, h, raw)
    r = pet.RECT()
    assert pet.GetWindowRect(hw, ctypes.byref(r)) and (r.left, r.top, r.right, r.bottom) == (x, y, x + w, y + h)
    f, want = window.panel_of(hw).frame(), screen.frame_of(x, y, w, h)
    assert (f.origin.x, f.origin.y, f.size.width, f.size.height) == \
        (want.origin.x, want.origin.y, want.size.width, want.size.height)
    assert window.polling()                              # a visible layered window: the poll runs
    win = base.window(hw)
    window.hit_test([win], x + 10, y + 10)
    assert not window.panel_of(hw).ignoresMouseEvents()  # opaque under the cursor: it takes the mouse
    window.hit_test([win], x + 50, y + 10)
    assert window.panel_of(hw).ignoresMouseEvents()      # transparent: clicks go through
    window.hit_test([win], x - 5, y + 10)
    assert window.panel_of(hw).ignoresMouseEvents()
    win.buttons.add(0)                                   # a button down on it: no switching meanwhile
    window.hit_test([win], x + 10, y + 10)
    assert window.panel_of(hw).ignoresMouseEvents()
    win.buttons.clear()
    # a new frame (as Pet._draw: memmove into the bits, present without moving: pptDst None keeps the place)
    ctypes.memmove(bits, picture(w, h, 8), w * h * 4)
    blend = pet.BLENDFUNCTION(pet.AC_SRC_OVER, 0, 255, pet.AC_SRC_ALPHA)
    assert pet.UpdateLayeredWindow(hw, None, None, ctypes.byref(pet.SIZE(w, h)), memdc, ctypes.byref(pet.POINT(0, 0)),
                                   0, ctypes.byref(blend), pet.ULW_ALPHA)
    assert window.presented(hw)[2] == picture(w, h, 8)
    assert pet.GetWindowRect(hw, ctypes.byref(r)) and (r.left, r.top) == (x, y)
    window.hit_test([win], x + 10, y + 10)
    assert window.panel_of(hw).ignoresMouseEvents()
    # moved as Pet._move_feet moves it
    assert pet.SetWindowPos(hw, None, x + 30, y + 20, 0, 0, pet.SWP_NOSIZE | pet.SWP_NOZORDER | pet.SWP_NOACTIVATE)
    assert pet.GetWindowRect(hw, ctypes.byref(r)) and (r.left, r.top, r.right, r.bottom) == (x + 30, y + 20,
                                                                                               x + 30 + w, y + 20 + h)
    assert pet.ShowWindow(hw, pet.SW_HIDE) == 1 and not window.polling()
    assert not pet.user32.IsWindowVisible(hw)


def test_a_click_through_window_never_takes_the_mouse(kit, pet):
    x, y = place()
    hw = kit.window(x, y, 16, 16, ex=LAYERED | pet.WS_EX_TRANSPARENT)
    win = base.window(hw)
    win.pixels, win.pw, win.ph = picture(16, 16, 16), 16, 16
    window.hit_test([win], x + 3, y + 3)
    assert window.panel_of(hw).ignoresMouseEvents()


# --------------------------------------------------------------------------- input
def test_synthetic_input_reaches_the_window_procedure_as_wm_messages(kit, pet):
    x, y = place()
    hw, _, _ = kit.layered(x, y, 64, 48, picture(64, 48, 64))
    rec = kit.rec
    synth.mouse(hw, "left_down", x + 10, y + 12)
    synth.mouse(hw, "left_drag", x + 30, y + 20)
    synth.mouse(hw, "left_drag", x - 7, y - 3)          # off the window while the button is down: still ours
    synth.mouse(hw, "left_up", x - 7, y - 3)
    synth.mouse(hw, "right_down", x + 5, y + 6)
    synth.mouse(hw, "right_up", x + 5, y + 6)
    got = [(m, wp, lo_hi(lp)) for h, m, wp, lp in rec.calls if h == hw and 0x200 <= m <= 0x20A]
    assert got == [(pet.WM_LBUTTONDOWN, 0x01, (10, 12)), (pet.WM_MOUSEMOVE, 0x01, (30, 20)),
                   (pet.WM_MOUSEMOVE, 0x01, (-7, -3)), (pet.WM_LBUTTONUP, 0, (-7, -3)),
                   (pet.WM_RBUTTONDOWN, 0x02, (5, 6)), (pet.WM_RBUTTONUP, 0, (5, 6))]
    del rec.calls[:]
    ev = synth.scroll(hw, x + 10, y + 12, 2, flags=synth.CONTROL)
    sign = -1 if ev.isDirectionInvertedFromDevice() else 1
    (h, m, wp, lp), = rec.of(pet.WM_MOUSEWHEEL)
    assert ctypes.c_short((wp >> 16) & 0xFFFF).value == sign * 2 * pet.WHEEL_DELTA
    assert wp & 0xFFFF & pet.MK_CONTROL and lo_hi(lp) == (x + 10, y + 12)
    del rec.calls[:]
    synth.scroll(hw, x + 10, y + 12, -1, flags=synth.COMMAND)
    (h, m, wp, lp), = rec.of(pet.WM_MOUSEWHEEL)
    assert ctypes.c_short((wp >> 16) & 0xFFFF).value == -sign * pet.WHEEL_DELTA and wp & pet.MK_CONTROL


def test_hovering_moves_only_over_opaque_pixels(kit, pet):
    x, y = place()
    hw, _, _ = kit.layered(x, y, 32, 32, picture(32, 32, 16))
    synth.mouse(hw, "move", x + 4, y + 5, when=1000.0)
    synth.mouse(hw, "move", x + 4, y + 5, when=1000.0)   # the same event twice: one message
    synth.mouse(hw, "move", x + 20, y + 5)               # transparent: Windows sends nothing there
    assert [(wp, lo_hi(lp)) for h, m, wp, lp in kit.rec.of(pet.WM_MOUSEMOVE)] == [(0, (4, 5))]
    assert window.panel_of(hw).ignoresMouseEvents()      # and the window lets the mouse through


def test_the_capture_takes_the_mouse_and_says_when_it_goes(kit, pet):
    x, y = place()
    a, _, _ = kit.layered(x, y, 32, 32, picture(32, 32, 32))
    b, _, _ = kit.layered(x + 100, y, 32, 32, picture(32, 32, 32))
    assert pet.SetCapture(a) == 0 and pet.GetCapture() == a
    synth.mouse(b, "left_down", x + 105, y + 4)          # on b, but a has the capture
    (h, m, wp, lp), = kit.rec.of(pet.WM_LBUTTONDOWN)
    assert h == a and lo_hi(lp) == (105, 4)
    synth.mouse(b, "left_up", x + 105, y + 4)
    assert pet.SetCapture(b) == a
    assert kit.rec.of(pet.WM_CAPTURECHANGED) == [(a, pet.WM_CAPTURECHANGED, 0, b)]
    assert pet.ReleaseCapture() and pet.GetCapture() == 0
    assert kit.rec.of(pet.WM_CAPTURECHANGED)[-1] == (b, pet.WM_CAPTURECHANGED, 0, 0)


def test_track_mouse_event_gives_one_leave_off_the_opaque_pixels(kit, pet):
    x, y = place()
    hw, _, _ = kit.layered(x, y, 32, 32, picture(32, 32, 16))
    tme = pet.TRACKMOUSEEVENT(ctypes.sizeof(pet.TRACKMOUSEEVENT), pet.TME_LEAVE, hw, 0)
    assert pet.TrackMouseEvent(ctypes.byref(tme))
    win = base.window(hw)
    window.hit_test([win], x + 4, y + 4)                 # still on it
    assert loop.pending() == 0
    window.hit_test([win], x + 20, y + 4)                # off its opaque pixels
    window.hit_test([win], x + 24, y + 4)
    pet.PostQuitMessage(0)
    msg = pet.MSG()
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 1 and (msg.hwnd, msg.message) == (hw, pet.WM_MOUSELEAVE)
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 0


def test_key_state_is_the_real_one():
    for vk in (0x01, 0x02, 0x10, 0x11, 0x12):
        assert ctypes.windll.user32.GetAsyncKeyState(vk) in (0, -0x8000)
    assert ctypes.windll.user32.GetAsyncKeyState(0x41) == 0


def test_screen_changes_and_logging_out_reach_every_window(kit, pet):
    a = kit.window(*place(), w=10, h=10)
    b = kit.window(*place(80, 60), w=10, h=10)
    window.screens_changed()
    assert [c[0] for c in kit.rec.of(pet.WM_DISPLAYCHANGE)] == [a, b]
    window.power_off()
    got = [(c[0], c[1], c[2]) for c in kit.rec.calls if c[1] in (pet.WM_QUERYENDSESSION, pet.WM_ENDSESSION)]
    assert got == [(a, pet.WM_QUERYENDSESSION, 0), (b, pet.WM_QUERYENDSESSION, 0), (a, pet.WM_ENDSESSION, 1),
                   (b, pet.WM_ENDSESSION, 1)]


# --------------------------------------------------------------------------- menus
def test_track_popup_menu_returns_the_item_chosen_and_timers_fire_meanwhile(kit, pet):
    x, y = place()
    hw = kit.window(x, y, 10, 10)
    m, sub = pet.CreatePopupMenu(), pet.CreatePopupMenu()
    assert pet.AppendMenuW(sub, pet.MF_STRING, 21, "Sub &one")
    assert pet.AppendMenuW(m, pet.MF_STRING, 11, "&Wave\tCtrl+W")
    assert pet.AppendMenuW(m, pet.MF_STRING | pet.MF_GRAYED, 12, "Fish && chips")
    assert pet.AppendMenuW(m, pet.MF_SEPARATOR, 0, None)
    assert pet.AppendMenuW(m, pet.MF_POPUP, sub, "More")
    assert pet.AppendMenuW(m, pet.MF_STRING | pet.MF_CHECKED, 13, "Third")
    seen = {}

    def choose():
        if len(kit.rec.of(pet.WM_TIMER)) < 8 and time.monotonic() < end:     # a busy (virtual) Mac fires late
            later(0.05, choose)
            return
        ns = menu.tracking()
        seen["titles"] = [str(it.title()) for it in ns.itemArray()]
        seen["enabled"] = [bool(it.isEnabled()) for it in ns.itemArray()]
        seen["checked"] = [int(it.state()) for it in ns.itemArray()]
        seen["sub"] = [str(it.title()) for it in ns.itemArray()[3].submenu().itemArray()]
        seen["ticks"] = len(kit.rec.of(pet.WM_TIMER))
        ns.performActionForItemAtIndex_(4)
        ns.cancelTracking()
    pet.SetTimer(hw, 3, 20, None)
    end = time.monotonic() + 3.0                         # up to 3 s for 8 ticks
    later(0.4, choose)
    cmd = pet.TrackPopupMenu(m, pet.TPM_RETURNCMD | pet.TPM_RIGHTBUTTON | pet.TPM_NONOTIFY, x, y, 0, hw, None)
    pet.KillTimer(hw, 3)
    assert cmd == 13
    assert seen["titles"] == ["Wave", "Fish & chips", "", "More", "Third"]
    assert seen["enabled"][:2] == [True, False] and seen["checked"][4] == 1 and seen["checked"][0] == 0
    assert seen["sub"] == ["Sub one"]
    assert seen["ticks"] >= 8                            # the timer went on while the menu was up
    assert menu.tracking() is None
    assert pet.DestroyMenu(m) and not pet.DestroyMenu(sub)    # the submenu went with it


def test_a_menu_closed_without_a_choice_returns_0_or_posts_nothing(kit, pet):
    x, y = place()
    hw = kit.window(x, y, 10, 10)
    m = pet.CreatePopupMenu()
    pet.AppendMenuW(m, pet.MF_STRING, 11, "Wave")
    later(0.2, lambda: menu.tracking().cancelTracking())
    assert pet.TrackPopupMenu(m, pet.TPM_RETURNCMD | pet.TPM_NONOTIFY, x, y, 0, hw, None) == 0
    later(0.2, lambda: (menu.tracking().performActionForItemAtIndex_(0), menu.tracking().cancelTracking()))
    assert pet.TrackPopupMenu(m, 0, x, y, 0, hw, None) == 1
    pet.PostQuitMessage(0)
    msg = pet.MSG()
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 1 and (msg.message, msg.wParam) == (WM_COMMAND, 11)
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 0
    pet.DestroyMenu(m)


def test_menu_labels_as_windows_shows_them():
    assert menu.label("&Wave") == "Wave"
    assert menu.label("Fish && chips") == "Fish & chips"
    assert menu.label("Open\tCtrl+O") == "Open"
    assert menu.label("a&&&b") == "a&b"
    assert menu.label(None) == ""
