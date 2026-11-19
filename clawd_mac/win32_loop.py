# -*- coding: utf-8 -*-
"""The NSApplication, the posted messages, GetMessageW and the timers.

The app is made when first needed (a window, a timer, the message loop), not on import: an accessory app (no Dock
icon, no menu bar), kept out of App Nap so its timers keep their pace while every window is hidden, as Windows'
timers do.  GetMessageW pumps NSApp's events until a message has been posted (PostMessageW, PostQuitMessage); the
window procedures meanwhile get their input and timers directly from AppKit's callbacks, as SendMessage would bring
them.  A post from a callback wakes the pump with an application-defined event.  WM_QUIT comes after every message
posted before it is taken, as on Windows.

Timers are NSTimers in NSRunLoopCommonModes that call the window procedure with WM_TIMER themselves: they fire in
GetMessageW's pump, while a popup menu tracks and while a mouse button is held, as Windows' timers do (its modal
loops dispatch them).  While a popup menu tracks, a common-modes timer of the same kind dispatches the posted
messages too (modal(), dispatch_posted()), in order, as Windows' menu loop does; WM_QUIT stays for GetMessageW."""
import collections
import threading
import time

import AppKit
import objc
from AppKit import NSApplication, NSDate, NSEvent, NSRunLoop, NSRunLoopCommonModes, NSTimer
from Foundation import NSMakePoint, NSObject, NSProcessInfo

from clawd_mac import win32_base as base

WM_NULL = 0x0000
WM_QUIT = 0x0012
WM_TIMER = 0x0113
USER_TIMER_MINIMUM = 10     # ms: Windows makes shorter timers this long
WAKE_SUBTYPE = 0x4357       # the application-defined event that wakes GetMessageW for a posted message
WPARAM_MASK = (1 << 64) - 1
NO_NAP = "Clawd: its animation and the event file"

_state = {"app": None, "activity": None, "quit": None, "time": 0, "dispatching": False, "modal": 0}
_queue = collections.deque()   # (hwnd, message, wparam, lparam, time) posted, oldest first
_lock = threading.Lock()
_on_start = []              # called with the app once it is there (the window part's notifications)
_timers = {}                # (hwnd, id) -> NSTimer


def app():
    """The NSApplication, made (accessory, launched, no App Nap) on the first call."""
    a = _state["app"]
    if a is None:
        a = NSApplication.sharedApplication()
        a.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        a.finishLaunching()
        _state["activity"] = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            AppKit.NSActivityUserInitiatedAllowingIdleSystemSleep, NO_NAP)
        _state["app"] = a
        for hook in list(_on_start):
            hook(a)
    return a


def started():
    return _state["app"] is not None


def on_start(hook):
    """hook(app) once the app is there (at once if it is)."""
    _on_start.append(hook)
    if started():
        hook(_state["app"])


# --------------------------------------------------------------------------- message time
def now_ms():
    """Now on the clock of NSEvent.timestamp (seconds since the boot, mach time), in ms, 32 bits."""
    return int(time.monotonic() * 1000) & 0xFFFFFFFF


def set_message_time(ms):
    _state["time"] = int(ms) & 0xFFFFFFFF


def GetMessageTime():
    t = _state["time"]
    return t - (1 << 32) if t >= 1 << 31 else t        # a LONG, as on Windows (the caller masks it)


# --------------------------------------------------------------------------- calling a window procedure
def send(hwnd, msg, wparam=0, lparam=0):
    """The window procedure of hwnd, called now (SendMessage within the thread) -> its result; 0 if hwnd is no
    window of ours or its class has no procedure.  An exception in it is told on stderr, not raised."""
    win = base.window(hwnd)
    proc = win.wndproc if win is not None else None
    if not proc:
        return 0
    try:
        return proc(base.handle(hwnd), msg, int(wparam) & WPARAM_MASK, int(lparam)) or 0
    except Exception:
        base.report("window procedure, message 0x%04X" % msg)
        return 0


def DefWindowProcW(hwnd, msg, wparam, lparam):
    return 0


# --------------------------------------------------------------------------- posted messages
def _wake():
    a = _state["app"]
    if a is None or _state["modal"]:
        return                                 # no loop yet to wake, or a modal one that looks at the queue itself
    ev =NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
        AppKit.NSEventTypeApplicationDefined, NSMakePoint(0, 0), 0, 0.0, 0, None, WAKE_SUBTYPE, 0, 0)
    a.postEvent_atStart_(ev, False)


def PostMessageW(hwnd, msg, wparam, lparam):
    h = base.handle(hwnd)
    if h and base.window(h) is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    with _lock:
        _queue.append((h, base.number(msg), base.number(wparam), base.number(lparam), now_ms()))
    _wake()
    return 1


def PostQuitMessage(code):
    with _lock:
        _state["quit"] = base.number(code)
    _wake()


def _take(quit=True):
    with _lock:
        if _queue:
            return _queue.popleft()
        if quit and _state["quit"] is not None:
            code, _state["quit"] = _state["quit"], None
            return (0, WM_QUIT, code, 0, now_ms())
    return None


def _pump_one(a):
    with objc.autorelease_pool():
        ev = a.nextEventMatchingMask_untilDate_inMode_dequeue_(
            AppKit.NSEventMaskAny, NSDate.distantFuture(), AppKit.NSDefaultRunLoopMode, True)
        if ev is None:
            return
        if ev.type() == AppKit.NSEventTypeApplicationDefined and ev.subtype() == WAKE_SUBTYPE:
            return
        a.sendEvent_(ev)


def GetMessageW(pmsg, hwnd, lo, hi):
    """Pumps NSApp's events until a message is posted -> 0 for WM_QUIT, else 1.  The filters are not looked at (the
    pets pass None, 0, 0)."""
    a = app()
    m = _take()
    while m is None:
        _pump_one(a)
        m = _take()
    msg = base.deref(pmsg)
    if msg is not None:
        msg.hwnd = m[0] or None
        msg.message = m[1]
        msg.wParam = m[2] & WPARAM_MASK
        msg.lParam = m[3]
        msg.time = m[4]
    return 0 if m[1] == WM_QUIT else 1


def TranslateMessage(pmsg):
    return 0                                   # no keyboard input: nothing to translate


def DispatchMessageW(pmsg):
    """The message to its window's procedure; one for no window (or a window gone since) is dropped."""
    msg = base.deref(pmsg)
    if msg is None:
        return 0
    set_message_time(msg.time)
    if not base.handle(msg.hwnd):
        return 0
    return send(msg.hwnd, msg.message, msg.wParam, msg.lParam)


def dispatch_posted():
    """What a modal loop does with the queue: every message posted so far to its window procedure, in order (one
    for no window is dropped); WM_QUIT is not taken.  Not again from inside one of those calls.  -> True if a quit
    waits (the modal loop should end, as Windows' menu loop ends on WM_QUIT)."""
    if not _state["dispatching"]:
        _state["dispatching"] = True
        try:
            m = _take(quit=False)
            while m is not None:
                set_message_time(m[4])
                if m[0]:
                    send(m[0], m[1], m[2], m[3])
                m = _take(quit=False)
        finally:
            _state["dispatching"] = False
    with _lock:
        return _state["quit"] is not None


def pending():
    """How many posted messages wait (tests)."""
    with _lock:
        return len(_queue)


# --------------------------------------------------------------------------- timers
class ClawdMacTimerTarget(NSObject):
    """What an NSTimer calls: WM_TIMER into the window procedure of (hwnd, id)."""

    def fire_(self, timer):
        try:
            with objc.autorelease_pool():
                _fire(self.key, timer)
        except Exception:
            base.report("timer %r" % (self.key,))


def _fire(key, timer):
    h, tid = key
    if _timers.get(key) is not timer:          # killed or set again since this fire was due
        return
    if base.window(h) is None:
        kill(key)
        return
    set_message_time(now_ms())
    send(h, WM_TIMER, tid, 0)


def kill(key):
    t = _timers.pop(key, None)
    if t is not None:
        t.invalidate()
    return t is not None


def kill_all(hwnd):
    """Every timer of a window (DestroyWindow)."""
    h = base.handle(hwnd)
    for key in [k for k in _timers if k[0] == h]:
        kill(key)


def SetTimer(hwnd, id_event, ms, timer_proc):
    """Per (hwnd, id); setting one again replaces it.  Window timers only (the pets have no others); a timer
    procedure is not called (WM_TIMER goes to the window)."""
    h = base.handle(hwnd)
    if base.window(h) is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    app()
    tid = base.number(id_event)
    key = (h, tid)
    kill(key)
    target = ClawdMacTimerTarget.alloc().init()
    target.key = key
    secs = max(base.number(ms), USER_TIMER_MINIMUM) / 1000.0
    t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(secs, target, "fire:", None, True)
    _timers[key] = t
    NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
    return tid or 1


def KillTimer(hwnd, id_event):
    if kill((base.handle(hwnd), base.number(id_event))):
        return 1
    return base.fail(base.ERROR_INVALID_PARAMETER)


def timers():
    """The (hwnd, id) of every timer set (tests)."""
    return sorted(_timers)


# --------------------------------------------------------------------------- modal loops
class ClawdMacModalTick(NSObject):
    """What modal()'s timer calls."""

    def fire_(self, timer):
        try:
            with objc.autorelease_pool():
                self.fn()
        except Exception:
            base.report("modal loop")


def modal(fn):
    """A modal loop (a menu) begins: fn() every USER_TIMER_MINIMUM ms from the common run loop modes (the menu's
    tracking mode among them), and no wake events meanwhile (fn looks at the queue; an application-defined event
    that comes while a menu tracks can close it) -> a function that ends it."""
    _state["modal"] += 1
    target = ClawdMacModalTick.alloc().init()
    target.fn = fn
    t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(USER_TIMER_MINIMUM / 1000.0, target, "fire:",
                                                                         None, True)
    NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)

    def end():
        t.invalidate()
        _state["modal"] -= 1
    return end


def run_for(secs):
    """Pump NSApp's events for secs (tests: timers and input run meanwhile; posted messages wait)."""
    a = app()
    end = time.monotonic() + secs
    while True:
        left = end - time.monotonic()
        if left <= 0:
            return
        with objc.autorelease_pool():
            ev = a.nextEventMatchingMask_untilDate_inMode_dequeue_(
                AppKit.NSEventMaskAny, NSDate.dateWithTimeIntervalSinceNow_(left), AppKit.NSDefaultRunLoopMode, True)
            if ev is not None and not (ev.type() == AppKit.NSEventTypeApplicationDefined
                                       and ev.subtype() == WAKE_SUBTYPE):
                a.sendEvent_(ev)
