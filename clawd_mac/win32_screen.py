# -*- coding: utf-8 -*-
"""Screens, and the one pixel space every coordinate of the shim is in.

Virtual px = points x S, S being the main screen's backingScaleFactor when first asked (2 on a Retina Mac), for all
screens alike.  The origin is the top-left corner of the primary screen (NSScreen.screens()[0], the one with the
menu bar in System Settings), y grows downward: Windows' virtual screen.  Cocoa's global points have their origin
at the primary screen's bottom-left and y growing upward, so y flips through the primary screen's height H0:

    x_px = x_pt * S                 y_px = (H0 - y_pt) * S
    x_pt = x_px / S                 y_pt = H0 - y_px / S

Quartz's global coordinates (CGEventGetLocation) already have the top-left origin: px = pt * S.  A frame drawn 1:1
is crisp where the screen's own scale is S, and scaled by the window server elsewhere."""
import math
import time

from AppKit import NSEvent, NSScreen
from Foundation import NSMakeRect

from clawd_mac import win32_base as base

MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTOPRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1
SPI_GETWORKAREA = 0x0030

SM_CXSCREEN, SM_CYSCREEN = 0, 1
SM_CXICON, SM_CYICON = 11, 12
SM_SWAPBUTTON = 23
SM_CXDOUBLECLK, SM_CYDOUBLECLK = 36, 37
SM_CXSMICON, SM_CYSMICON = 49, 50
SM_CXDRAG, SM_CYDRAG = 68, 69
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
SM_CMONITORS = 80
SMALL_ICON_PT, ICON_PT, DOUBLE_CLICK_PT, DRAG_PT = 16, 32, 4, 4    # Windows' sizes at 100 %, in points here

SCREENS_FRESH = 2.0         # s a look at the screens is trusted; a change of them also says so at once (changed())
NO_SCREEN = (0, 0, 1280, 720)   # without a window server: what the pets assume when Windows says nothing

_state = {"scale": None, "screens": None, "at": -1e9}
_monitors = {}              # display number -> its HMONITOR, the same for as long as the process runs


class Monitor(object):
    """What an HMONITOR stands for: one display, by its number."""

    def __init__(self, number):
        self.number = number


class Screen(object):
    """One screen as Win32 sees it, in virtual px: frame (rcMonitor) and work (rcWork: without the menu bar and the
    Dock), each (left, top, right, bottom)."""

    def __init__(self, handle, frame, work, primary, h0):
        self.handle, self.frame, self.work, self.primary, self.h0 = handle, frame, work, primary, h0


def scale():
    """S: virtual px per point, fixed at the first question."""
    if _state["scale"] is None:
        main = NSScreen.mainScreen() or (list(NSScreen.screens() or []) or [None])[0]
        s = float(main.backingScaleFactor()) if main is not None else 1.0
        _state["scale"] = s if s > 0 else 1.0
    return _state["scale"]


def screens():
    """The screens now, the primary first (looked at again after SCREENS_FRESH or a change)."""
    now = time.monotonic()
    if _state["screens"] is None or now - _state["at"] > SCREENS_FRESH:
        _state["screens"] = _look()
        _state["at"] = now
    return _state["screens"]


def changed():
    """The screens changed (NSApplicationDidChangeScreenParametersNotification): look again at the next question."""
    _state["screens"] = None


def _monitor(number):
    h = _monitors.get(number)
    if h is None:
        h = _monitors[number] = base.new_handle(Monitor(number))
    return h


def _rect(r, h0, s):
    x0, y0 = r.origin.x, r.origin.y
    x1, y1 = x0 + r.size.width, y0 + r.size.height
    return (int(round(x0 * s)), int(round((h0 - y1) * s)), int(round(x1 * s)), int(round((h0 - y0) * s)))


def _look():
    s = scale()
    found = list(NSScreen.screens() or [])
    if not found:
        return [Screen(_monitor(0), NO_SCREEN, NO_SCREEN, True, NO_SCREEN[3] / s)]
    h0 = found[0].frame().size.height
    out = []
    for i, sc in enumerate(found):
        number = sc.deviceDescription().get("NSScreenNumber")
        number = int(number) if number is not None else -1 - i
        out.append(Screen(_monitor(number), _rect(sc.frame(), h0, s), _rect(sc.visibleFrame(), h0, s), i == 0, h0))
    return out


def primary_height():
    """H0: the primary screen's height in points."""
    return screens()[0].h0


def to_pixels(x, y):
    """Cocoa global points -> virtual px (floats)."""
    s = scale()
    return x * s, (primary_height() - y) * s


def to_points(x, y):
    """Virtual px -> Cocoa global points."""
    s = scale()
    return x / s, primary_height() - y / s


def frame_of(left, top, w, h):
    """The NSRect (Cocoa points) of a window whose rectangle is left, top, w, h in virtual px."""
    s = scale()
    x, y = to_points(left, top + h)
    return NSMakeRect(x, y, w / s, h / s)


def screen_at(x, y, flags=MONITOR_DEFAULTTONEAREST):
    """The screen with virtual px (x, y) on it; else the primary or the nearest one, as flags say, or None."""
    found = screens()
    for sc in found:
        l, t, r, b = sc.frame
        if l <= x < r and t <= y < b:
            return sc
    if flags == MONITOR_DEFAULTTOPRIMARY:
        return found[0]
    if flags == MONITOR_DEFAULTTONEAREST:
        return min(found, key=lambda sc: _distance2(sc.frame, x, y))
    return None


def _distance2(rect, x, y):
    l, t, r, b = rect
    dx = max(l - x, 0, x - (r - 1))
    dy = max(t - y, 0, y - (b - 1))
    return dx * dx + dy * dy


def _fill(rect, ltrb):
    rect.left, rect.top, rect.right, rect.bottom = ltrb


# --------------------------------------------------------------------------- user32
def MonitorFromPoint(pt, flags):
    p = base.deref(pt)                         # passed by value: the POINT itself
    sc = screen_at(int(p.x), int(p.y), base.number(flags))
    return sc.handle if sc is not None else 0


def GetMonitorInfoW(hmonitor, pmi):
    mi = base.deref(pmi)
    h = base.handle(hmonitor)
    sc = next((sc for sc in screens() if sc.handle == h), None)
    if mi is None or sc is None:               # not a monitor, or one unplugged since
        return base.fail(base.ERROR_INVALID_PARAMETER)
    _fill(mi.rcMonitor, sc.frame)
    _fill(mi.rcWork, sc.work)
    mi.dwFlags = MONITORINFOF_PRIMARY if sc.primary else 0
    return 1


def SystemParametersInfoW(action, param, pv, winini):
    """SPI_GETWORKAREA only: the primary screen's visibleFrame."""
    r = base.deref(pv)
    if base.number(action) != SPI_GETWORKAREA or r is None:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    _fill(r, screens()[0].work)
    return 1


def GetSystemMetrics(index):
    index = base.number(index)
    s = scale()
    found = screens()
    l, t, r, b = found[0].frame
    if index == SM_CXSCREEN:
        return r - l
    if index == SM_CYSCREEN:
        return b - t
    if index in (SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN):
        vl = min(sc.frame[0] for sc in found)
        vt = min(sc.frame[1] for sc in found)
        vr = max(sc.frame[2] for sc in found)
        vb = max(sc.frame[3] for sc in found)
        return {SM_XVIRTUALSCREEN: vl, SM_YVIRTUALSCREEN: vt, SM_CXVIRTUALSCREEN: vr - vl,
                SM_CYVIRTUALSCREEN: vb - vt}[index]
    if index == SM_CMONITORS:
        return len(found)
    sizes = {SM_CXSMICON: SMALL_ICON_PT, SM_CYSMICON: SMALL_ICON_PT, SM_CXICON: ICON_PT, SM_CYICON: ICON_PT,
             SM_CXDOUBLECLK: DOUBLE_CLICK_PT, SM_CYDOUBLECLK: DOUBLE_CLICK_PT, SM_CXDRAG: DRAG_PT, SM_CYDRAG: DRAG_PT}
    if index in sizes:
        return int(round(sizes[index] * s))
    return 0                                   # SM_SWAPBUTTON among them: the primary button is the left one


def GetCursorPos(ppt):
    p = base.deref(ppt)
    if p is None:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    loc = NSEvent.mouseLocation()
    x, y = to_pixels(loc.x, loc.y)
    p.x, p.y = int(math.floor(x)), int(math.floor(y))
    return 1
