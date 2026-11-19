# -*- coding: utf-8 -*-
"""Synthetic input for tests: NSEvents made in this process and handed to one of our own windows (sendEvent_, a
scroll straight to its view).  Nothing is posted to the system, so the real mouse and the apps of whoever sits at
the screen are left alone.

Points are virtual px on the screen (win32_screen), as the pets see them; an event lands a quarter pixel into the
pixel asked for, so rounding never moves it to the next one.  Timestamps are on NSEvent's clock (time.monotonic)."""
import time

import AppKit
import Quartz
from AppKit import NSEvent
from Foundation import NSMakePoint

from clawd_mac import win32_base as base
from clawd_mac import win32_screen as screen

KINDS = {"left_down": AppKit.NSEventTypeLeftMouseDown, "left_up": AppKit.NSEventTypeLeftMouseUp,
         "left_drag": AppKit.NSEventTypeLeftMouseDragged, "right_down": AppKit.NSEventTypeRightMouseDown,
         "right_up": AppKit.NSEventTypeRightMouseUp, "right_drag": AppKit.NSEventTypeRightMouseDragged,
         "move": AppKit.NSEventTypeMouseMoved}
CONTROL = AppKit.NSEventModifierFlagControl
COMMAND = AppKit.NSEventModifierFlagCommand
SHIFT = AppKit.NSEventModifierFlagShift
NUDGE = 0.25                # px into the pixel asked for


def _event(hwnd, kind, x, y, flags, clicks, when):
    win = base.window(hwnd)
    if win is None:
        raise ValueError("no window %r" % (hwnd,))
    gx, gy = screen.to_points(x + NUDGE, y + NUDGE)
    frame = win.panel.frame()
    loc = NSMakePoint(gx - frame.origin.x, gy - frame.origin.y)
    pressure = 1.0 if kind.endswith(("down", "drag")) else 0.0
    make = getattr(NSEvent, "mouseEventWithType_location_modifierFlags_timestamp_"
                            "windowNumber_context_eventNumber_clickCount_pressure_")
    return win.panel, make(KINDS[kind], loc, flags, time.monotonic() if when is None else when,
                           win.panel.windowNumber(), None, 0, clicks, pressure)


def mouse(hwnd, kind, x, y, flags=0, clicks=1, when=None):
    """A mouse event of kind (KINDS) at screen px (x, y), sent to window hwnd."""
    panel, ev = _event(hwnd, kind, x, y, flags, clicks, when)
    panel.sendEvent_(ev)


def scroll_event(hwnd, x, y, lines, flags=0, when=None):
    """-> (panel, event): a wheel event of `lines` notches at screen px (x, y) for window hwnd, not sent yet.  Quartz
    makes it (NSEvent has no maker for scroll events) out of a mouse event of that window, so it is that window's.
    Whether the window procedure sees `lines` or -lines is the event's isDirectionInvertedFromDevice()."""
    panel, ev = _event(hwnd, "move", x, y, flags, 0, when)
    cg = ev.CGEvent()
    Quartz.CGEventSetType(cg, Quartz.kCGEventScrollWheel)
    Quartz.CGEventSetIntegerValueField(cg, Quartz.kCGScrollWheelEventIsContinuous, 0)
    Quartz.CGEventSetIntegerValueField(cg, Quartz.kCGScrollWheelEventDeltaAxis1, int(lines))
    return panel, NSEvent.eventWithCGEvent_(cg)


def send_scroll(panel, ev):
    """A scroll_event() handed to its window's view.  Not panel.sendEvent_: AppKit routes a scroll to the view that
    its location in the window hits, and on GitHub's macOS 26 runners a Quartz-made one hits none."""
    panel.contentView().scrollWheel_(ev)


def scroll(hwnd, x, y, lines, flags=0, when=None):
    """scroll_event(), sent (send_scroll); -> the event."""
    panel, ev = scroll_event(hwnd, x, y, lines, flags, when)
    send_scroll(panel, ev)
    return ev
