# -*- coding: utf-8 -*-
"""Mouse input: the view each window shows its picture in turns AppKit's mouse events into the WM_ messages of
its window procedure, called directly (Windows sends input to the window under the cursor, or to the one with the
capture).  Also the capture, the keys' state, TrackMouseEvent's leave and the double-click time.

lparam is the point in client coordinates (x low word, y high word, each signed 16-bit) and wparam the MK_ flags,
for WM_MOUSEMOVE and the button messages; WM_MOUSEWHEEL has the delta in WHEEL_DELTA units in wparam's high word,
the MK_ flags in its low word, and screen coordinates in lparam.  A point is where the event happened (Quartz's
location of it), not where the window is now, so a window moved under a drag does not make the drag jump.  Control
or Command held is MK_CONTROL, but a Control+click is a right click, as everywhere on macOS (WM_RBUTTONDOWN / UP,
its drag MK_RBUTTON, the Control in it no MK_CONTROL).  A double click is WM_LBUTTONDBLCLK only for a class with
CS_DBLCLKS (the pets register none: they count their clicks themselves).

The cursor: over a window's opaque pixels (and while a button is down on it), its class's cursor (hCursor of
LoadCursorW: IDC_HAND is the pointing hand, IDC_SIZEALL the open hand, IDC_ARROW and the others the arrow); the
arrow again once the pointer is off them."""
import math

import AppKit
import objc
import Quartz
from AppKit import NSEvent, NSTrackingArea, NSView
from Foundation import NSMakeRect

from clawd_mac import win32_base as base
from clawd_mac import win32_loop as loop
from clawd_mac import win32_screen as screen

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0201, 0x0202, 0x0203
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK = 0x0204, 0x0205, 0x0206
WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK = 0x0207, 0x0208, 0x0209
WM_MOUSEWHEEL = 0x020A
WM_CAPTURECHANGED = 0x0215
WM_MOUSELEAVE = 0x02A3
MK_LBUTTON, MK_RBUTTON, MK_SHIFT, MK_CONTROL, MK_MBUTTON = 0x01, 0x02, 0x04, 0x08, 0x10
VK_LBUTTON, VK_RBUTTON, VK_MBUTTON = 0x01, 0x02, 0x04
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
KEY_DOWN = -0x8000          # GetAsyncKeyState's high bit, a SHORT
CS_DBLCLKS = 0x0008
TME_LEAVE = 0x00000002
TME_CANCEL = 0x80000000
WHEEL_DELTA = 120
WHEEL_PER_POINT = 3.0       # a touchpad's (precise) scroll: 40 points of it are one notch of a wheel
LEFT, RIGHT, MIDDLE = 0, 1, 2
# per button: down, up, double-click, its MK_ flag
BUTTONS = {LEFT: (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK, MK_LBUTTON),
           RIGHT: (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK, MK_RBUTTON),
           MIDDLE: (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK, MK_MBUTTON)}
PRESSED_BIT = {VK_LBUTTON: 1, VK_RBUTTON: 2, VK_MBUTTON: 4}     # NSEvent.pressedMouseButtons
MODIFIER = {VK_SHIFT: AppKit.NSEventModifierFlagShift, VK_CONTROL: AppKit.NSEventModifierFlagControl,
            VK_MENU: AppKit.NSEventModifierFlagOption}
CONTROLISH = AppKit.NSEventModifierFlagControl | AppKit.NSEventModifierFlagCommand
IDC_ARROW, IDC_SIZEALL, IDC_HAND = 32512, 32646, 32649
CURSORS = {IDC_ARROW: "arrowCursor", IDC_SIZEALL: "openHandCursor", IDC_HAND: "pointingHandCursor"}
TRACKING = (AppKit.NSTrackingMouseMoved | AppKit.NSTrackingMouseEnteredAndExited | AppKit.NSTrackingCursorUpdate
            | AppKit.NSTrackingActiveAlways | AppKit.NSTrackingInVisibleRect)

_state = {"capture": 0, "cursor": None}    # cursor: the NSCursor set over a window, None once given back
_cursors = {}               # LoadCursorW's name -> its handle


class Cursor(object):
    def __init__(self, name):
        self.name = name


# --------------------------------------------------------------------------- the view
class ClawdMacView(NSView):
    """A window's content: its layer shows the picture, its mouse events go to the window procedure.  win is the
    window record (None once the window is gone)."""

    def initWithFrame_(self, frame):
        self = objc.super(ClawdMacView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.win = None
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(NSMakeRect(0, 0, 0, 0), TRACKING, self,
                                                                           None)
        self.addTrackingArea_(area)
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True                            # the first click on a pet is a click, not "come to the front"

    def acceptsFirstResponder(self):
        return True

    def mouseDown_(self, event):
        _guarded(self, event, "down", LEFT)

    def mouseUp_(self, event):
        _guarded(self, event, "up", LEFT)

    def mouseDragged_(self, event):
        _guarded(self, event, "move", LEFT)

    def rightMouseDown_(self, event):
        _guarded(self, event, "down", RIGHT)

    def rightMouseUp_(self, event):
        _guarded(self, event, "up", RIGHT)

    def rightMouseDragged_(self, event):
        _guarded(self, event, "move", RIGHT)

    def otherMouseDown_(self, event):
        _guarded(self, event, "down", MIDDLE)

    def otherMouseUp_(self, event):
        _guarded(self, event, "up", MIDDLE)

    def otherMouseDragged_(self, event):
        _guarded(self, event, "move", MIDDLE)

    def mouseMoved_(self, event):
        _guarded(self, event, "move", None)

    def mouseExited_(self, event):
        _guarded(self, event, "exit", None)

    def scrollWheel_(self, event):
        _guarded(self, event, "wheel", None)

    def cursorUpdate_(self, event):
        _guarded(self, event, "cursor", None)


def _guarded(view, event, what, button):
    try:
        with objc.autorelease_pool():
            win = view.win
            if win is None or not win.alive:
                return
            if what == "wheel":
                _wheel(win, event)
            elif what == "exit":
                _exited(win)
            elif what == "cursor":
                x, y = event_pixels(event)
                show_cursor(cursor_at(win, x - win.x, y - win.y))
            else:
                _mouse(win, event, what, button)
    except Exception:
        base.report("mouse event %s" % what)


# --------------------------------------------------------------------------- events -> messages
def event_pixels(event):
    """Where the event happened, in virtual px (ints)."""
    cg = event.CGEvent()
    if cg is not None:
        p = Quartz.CGEventGetLocation(cg)      # top-left origin already
        s = screen.scale()
        return int(math.floor(p.x * s)), int(math.floor(p.y * s))
    loc = event.locationInWindow()
    if event.window() is not None:
        loc = event.window().convertPointToScreen_(loc)
    x, y = screen.to_pixels(loc.x, loc.y)
    return int(math.floor(x)), int(math.floor(y))


def event_ms(event):
    t = event.timestamp()
    return int(t * 1000) & 0xFFFFFFFF if t > 0 else loop.now_ms()


def mk_flags(event, win):
    flags = 0
    for b in win.buttons:
        flags |= BUTTONS[b][3]
    mods = event.modifierFlags()
    if win.control_click:
        mods &= ~AppKit.NSEventModifierFlagControl     # it made the click a right one
    if mods & AppKit.NSEventModifierFlagShift:
        flags |= MK_SHIFT
    if mods & CONTROLISH:
        flags |= MK_CONTROL
    return flags


def _target(win):
    """The window with the capture gets the mouse, whichever window it is over."""
    cap = GetCapture()
    if cap and cap != win.hwnd:
        other = base.window(cap)
        if other is not None:
            return other
    return win


def _button(win, event, what, button):
    """The button the program hears of: a Control+click's left button is the right one, until it is up."""
    if button == LEFT and what == "down":
        win.control_click = bool(event.modifierFlags() & AppKit.NSEventModifierFlagControl)
    return RIGHT if button == LEFT and win.control_click else button


def _mouse(win, event, what, button):
    button = _button(win, event, what, button)
    if what == "down":
        win.buttons.add(button)
    elif what == "up":
        win.buttons.discard(button)
    target = _target(win)
    x, y = event_pixels(event)
    if what == "move" and button is None:
        if target is win and not win.opaque_at(x - win.x, y - win.y):
            win.pass_through()                 # over a transparent pixel: Windows sends nothing there
            cursor_off()
            return
        if win.last_move == (event.timestamp(), x, y):
            return                             # the same move, via the tracking area and the first responder
        win.last_move = (event.timestamp(), x, y)
        msg = WM_MOUSEMOVE
    elif what == "move":
        msg = WM_MOUSEMOVE
    else:
        down, up, double, _ = BUTTONS[button]
        msg = up if what == "up" else down
        if what == "down" and event.clickCount() % 2 == 0 and target.cls.style & CS_DBLCLKS:
            msg = double
    show_cursor(cursor_of(target))
    flags = mk_flags(event, win)
    if what == "up" and win.control_click and button == RIGHT:
        win.control_click = False
    loop.set_message_time(event_ms(event))
    loop.send(target.hwnd, msg, flags, base.pack(x - target.x, y - target.y))


def _wheel(win, event):
    """Notches of a wheel are WHEEL_DELTA each (the line count Quartz keeps, before acceleration); a touchpad's
    points WHEEL_PER_POINT each, the remainder kept for the next event.  The physical direction counts: away from
    you is positive, whatever natural scrolling does to the content."""
    cg = event.CGEvent()
    if event.hasPreciseScrollingDeltas():
        units = event.scrollingDeltaY() * WHEEL_PER_POINT
    else:
        lines = Quartz.CGEventGetIntegerValueField(cg, Quartz.kCGScrollWheelEventDeltaAxis1) if cg is not None else 0
        units = (lines or event.scrollingDeltaY()) * WHEEL_DELTA
    if event.isDirectionInvertedFromDevice():
        units = -units
    units += win.wheel_rest
    delta = int(units)
    win.wheel_rest = units - delta
    delta = max(-0x8000, min(0x7FFF, delta))
    if not delta:
        return
    target = _target(win)
    x, y = event_pixels(event)
    loop.set_message_time(event_ms(event))
    loop.send(target.hwnd, WM_MOUSEWHEEL, base.pack(mk_flags(event, win), delta), base.pack(x, y))


def _exited(win):
    if not win.buttons:
        win.pass_through()
        cursor_off()
    if win.track_leave and GetCapture() != win.hwnd:
        win.track_leave = False
        loop.PostMessageW(win.hwnd, WM_MOUSELEAVE, 0, 0)


# --------------------------------------------------------------------------- capture
def SetCapture(hwnd):
    h = base.handle(hwnd)
    if base.window(h) is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    prev = GetCapture()
    _state["capture"] = h
    if prev and prev != h:
        loop.send(prev, WM_CAPTURECHANGED, 0, h)
    return prev


def ReleaseCapture():
    prev = GetCapture()
    _state["capture"] = 0
    if prev:
        loop.send(prev, WM_CAPTURECHANGED, 0, 0)
    return 1


def GetCapture():
    h = _state["capture"]
    if h and base.window(h) is None:
        _state["capture"] = h = 0
    return h


def forget(hwnd):
    """A window going away loses the capture, quietly."""
    if _state["capture"] == base.handle(hwnd):
        _state["capture"] = 0


# --------------------------------------------------------------------------- keys, leave, cursor
def GetAsyncKeyState(vk):
    """The mouse buttons and Shift / Control / Option (VK_MENU) as they are now."""
    vk = base.number(vk)
    if vk in PRESSED_BIT:
        down = NSEvent.pressedMouseButtons() & PRESSED_BIT[vk]
    elif vk in MODIFIER:
        down = NSEvent.modifierFlags() & MODIFIER[vk]
    else:
        down = 0
    return KEY_DOWN if down else 0


def TrackMouseEvent(ptme):
    """TME_LEAVE only: one WM_MOUSELEAVE (posted) once the cursor is off the window's opaque pixels."""
    tme = base.deref(ptme)
    if tme is None:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    win = base.window(tme.hwndTrack)
    if win is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    flags = base.number(tme.dwFlags)
    if flags & TME_LEAVE:
        win.track_leave = not flags & TME_CANCEL
    return 1


def GetDoubleClickTime():
    return int(round(NSEvent.doubleClickInterval() * 1000))


def LoadCursorW(hinst, name):
    """A handle for the system cursor asked for (IDC_*), one per name; the NSCursor it is: cursor_of()."""
    key = base.number(name) if not isinstance(name, str) else name
    h = _cursors.get(key)
    if h is None:
        h = _cursors[key] = base.new_handle(Cursor(key))
    return h


def cursor_of(win):
    """The NSCursor of a window's class (the arrow for none, or for one macOS has no likeness of)."""
    c = base.lookup(win.cls.cursor, Cursor) if win is not None else None
    return getattr(AppKit.NSCursor, CURSORS.get(c.name if c is not None else IDC_ARROW, "arrowCursor"))()


def cursor_at(win, x, y):
    """The cursor over client px (x, y) of a window: its class's over an opaque pixel (or while a button is down
    on it), else the arrow."""
    if win.buttons or win.opaque_at(x, y):
        return cursor_of(win)
    return AppKit.NSCursor.arrowCursor()


def show_cursor(cursor):
    if _state["cursor"] is not cursor:
        cursor.set()
        _state["cursor"] = cursor


def cursor_off():
    """The pointer left a window's opaque pixels: the arrow again, if a window had set another cursor."""
    c = _state["cursor"]
    if c is not None:
        _state["cursor"] = None
        if c is not AppKit.NSCursor.arrowCursor():
            AppKit.NSCursor.arrowCursor().set()


def shown_cursor():
    """The cursor a window set last, or None once given back (tests)."""
    return _state["cursor"]
