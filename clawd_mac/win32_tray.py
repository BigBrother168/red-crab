# -*- coding: utf-8 -*-
"""The notification area's icon, as a status item in the menu bar: Shell_NotifyIconW and the icons it shows
(CreateIconIndirect, LoadIconW, DestroyIcon).

One NSStatusItem (variable length) per (hWnd, uID): NIM_ADD makes it (failing if it is there, as on Windows),
NIM_MODIFY changes it, NIM_DELETE takes it out of the menu bar.  NIF_ICON sets its picture, NIF_TIP its tooltip,
NIF_MESSAGE the message a click posts to hWnd: (uCallbackMessage, uID, the mouse message).  Clicks are macOS's:
a click (left, right or Control+click) opens the icon's menu, so it posts WM_RBUTTONUP, the message the program
opens its tray menu on; Option+click is Windows' left click (WM_LBUTTONUP).  A TrackPopupMenu soon after such a
click opens the menu under the status item, at its left edge, as a menu bar's menus open (menu_anchor()).  The
system draws the status items (macOS 26 and later: in a process of its own), so the item's window here is not where
it shows: its left edge is where the pointer was at the click less how far into the button the click was, and the
menu's top is the bottom of the menu bar of the screen the pointer was on.

An icon keeps its colour bitmap's pixels (32 bpp, straight alpha as Windows' icons have them, rows top-down) and its
mask (1 bpp: a set bit is transparent, used only where the colour bitmap has no alpha at all), copied at
CreateIconIndirect: the program deletes both bitmaps right after.  In the menu bar it is an NSImage of its own
pixels, sized to the bar (its thickness less TRAY_PADDING_PT), not a template: Clawd keeps its colours."""
import time

import AppKit
import Quartz
from AppKit import NSBitmapImageRep, NSEvent, NSImage, NSScreen, NSStatusBar
from Foundation import NSData, NSMakeSize, NSObject

from clawd_mac import win32_base as base
from clawd_mac import win32_gdi as gdi
from clawd_mac import win32_loop as loop

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
TRAY_PADDING_PT = 4         # the icon's height is the menu bar's thickness less this
MENU_AFTER_CLICK = 0.5      # s: a TrackPopupMenu this soon after a status item's click opens under it
ICON_BITMAP_INFO = Quartz.kCGImageAlphaFirst | Quartz.kCGBitmapByteOrder32Little     # BGRA, straight alpha
CLICKS = AppKit.NSEventMaskLeftMouseUp | AppKit.NSEventMaskRightMouseUp
MOUSE_EVENTS = (AppKit.NSEventTypeLeftMouseDown, AppKit.NSEventTypeLeftMouseUp, AppKit.NSEventTypeRightMouseDown,
                AppKit.NSEventTypeRightMouseUp)

_items = {}                 # (hwnd, uID) -> StatusItem
_stock = {}                 # LoadIconW's name -> its handle (shared: DestroyIcon leaves it)
_state = {"click": None, "target": None}    # click: (when, (hwnd, uID), anchor) of the last status item click


# --------------------------------------------------------------------------- icons
class Icon(object):
    """An HICON: w x h pixels (top-down BGRA, straight alpha), or for a stock one (pixels None) the app's icon."""

    def __init__(self, w, h, pixels, stock=False):
        self.w, self.h, self.pixels, self.stock = w, h, pixels, stock
        self._image = None

    def image(self):
        """The NSImage the menu bar shows (made once)."""
        if self._image is None:
            self._image = _bar_image(self)
        return self._image


def _alpha_from_mask(color, mask, w, h):
    """A colour bitmap without alpha: opaque where the mask's bit is clear, transparent where it is set."""
    out = bytearray(color)
    stride = (w + 15) // 16 * 2
    for y in range(h):
        for x in range(w):
            bit = mask[y * stride + x // 8] & (0x80 >> (x % 8)) if mask is not None else 0
            out[(y * w + x) * 4 + 3] = 0 if bit else 255
    return bytes(out)


def CreateIconIndirect(piconinfo):
    """An icon of a 32-bpp colour bitmap (a DIB section or a CreateBitmap one) and its mask, both copied."""
    info = base.deref(piconinfo)
    color = gdi.rows(info.hbmColor) if info is not None else None
    if color is None or color[2] != gdi.BITS_PER_PIXEL:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    w, h, _, pixels = color
    mask = gdi.rows(info.hbmMask)
    if not any(pixels[3::4]):                  # no alpha at all: the mask says what shows (as Windows reads it)
        bits = mask[3] if mask is not None and mask[2] == gdi.MONO_BITS and mask[:2] == (w, h) else None
        pixels = _alpha_from_mask(pixels, bits, w, h)
    return base.new_handle(Icon(w, h, pixels))


def LoadIconW(hinst, name):
    """The system's icons (IDI_APPLICATION and the others): the app's icon, one shared handle per name.  Icons of a
    module's resources: there are none."""
    if base.handle(hinst):
        return base.fail(base.ERROR_FILE_NOT_FOUND)
    key = name if isinstance(name, str) else base.number(name)
    h = _stock.get(key)
    if h is None:
        h = _stock[key] = base.new_handle(Icon(0, 0, None, stock=True))
    return h


def DestroyIcon(hicon):
    """A shared (stock) icon stays; a status item showing an icon keeps its picture."""
    icon = base.lookup(hicon, Icon)
    if icon is None:
        return base.fail(base.ERROR_INVALID_HANDLE)
    if not icon.stock:
        base.release(hicon)
    return 1


def _side():
    return max(NSStatusBar.systemStatusBar().thickness() - TRAY_PADDING_PT, 1)


def _bar_image(icon):
    side = _side()
    if icon.stock:
        app_icon = loop.app().applicationIconImage() or NSImage.imageNamed_(AppKit.NSImageNameApplicationIcon)
        image = app_icon.copy()
        image.setSize_(NSMakeSize(side, side))
        return image
    data = NSData.alloc().initWithBytes_length_(icon.pixels, len(icon.pixels))
    provider = Quartz.CGDataProviderCreateWithCFData(data)
    srgb = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    cg = Quartz.CGImageCreate(icon.w, icon.h, 8, 32, icon.w * 4, srgb, ICON_BITMAP_INFO, provider, None, True,
                              Quartz.kCGRenderingIntentDefault)
    size = NSMakeSize(side * icon.w / float(max(icon.w, icon.h)), side * icon.h / float(max(icon.w, icon.h)))
    rep = NSBitmapImageRep.alloc().initWithCGImage_(cg)
    rep.setSize_(size)
    image = NSImage.alloc().initWithSize_(size)
    image.addRepresentation_(rep)
    image.setTemplate_(False)
    return image


# --------------------------------------------------------------------------- status items
class StatusItem(object):
    """One icon in the menu bar: its NSStatusItem, and the message its clicks post (0: none)."""

    def __init__(self, key, ns):
        self.key, self.ns, self.message = key, ns, 0


class ClawdMacTrayTarget(NSObject):
    """What every status item's button calls on a click."""

    def clicked_(self, button):
        try:
            clicked(button, AppKit.NSApp().currentEvent())
        except Exception:
            base.report("status item click")


def _target():
    if _state["target"] is None:
        _state["target"] = ClawdMacTrayTarget.alloc().init()
    return _state["target"]


def _make(key):
    loop.app()
    ns = NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSVariableStatusItemLength)
    button = ns.button()
    button.setTarget_(_target())
    button.setAction_("clicked:")
    button.sendActionOn_(CLICKS)
    button.setImagePosition_(AppKit.NSImageOnly)
    return StatusItem(key, ns)


def _apply(item, nid, flags):
    button = item.ns.button()
    if flags & NIF_MESSAGE:
        item.message = base.number(nid.uCallbackMessage)
    if flags & NIF_ICON:
        icon = base.lookup(nid.hIcon, Icon)
        button.setImage_(icon.image() if icon is not None else None)
    if flags & NIF_TIP:
        button.setToolTip_(base.text(nid.szTip) or None)


def Shell_NotifyIconW(message, pnid):
    nid = base.deref(pnid)
    if nid is None:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    message = base.number(message)
    key = (base.handle(nid.hWnd), base.number(nid.uID))
    item = _items.get(key)
    if message == NIM_ADD:
        if base.window(key[0]) is None:
            return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
        if item is not None:
            return base.fail(base.ERROR_ALREADY_EXISTS)
        item = _items[key] = _make(key)
    elif message in (NIM_MODIFY, NIM_DELETE):
        if item is None:
            return base.fail(base.ERROR_FILE_NOT_FOUND)
        if message == NIM_DELETE:
            _remove(key)
            return 1
    else:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    _apply(item, nid, base.number(nid.uFlags))
    return 1


def _remove(key):
    item = _items.pop(key, None)
    if item is not None:
        NSStatusBar.systemStatusBar().removeStatusItem_(item.ns)
        if _state["click"] is not None and _state["click"][1] == key:
            _state["click"] = None


# --------------------------------------------------------------------------- clicks
def click_message(event):
    """The mouse message a click on a status item is to the program: WM_LBUTTONUP for Option+click (Windows' left
    click: hide or show), else WM_RBUTTONUP (the menu)."""
    if event is None:
        return WM_RBUTTONUP                    # performClick: a plain click
    mods = event.modifierFlags()
    right = event.type() in (AppKit.NSEventTypeRightMouseUp, AppKit.NSEventTypeRightMouseDown)
    if not right and mods & AppKit.NSEventModifierFlagOption and not mods & AppKit.NSEventModifierFlagControl:
        return WM_LBUTTONUP
    return WM_RBUTTONUP


def clicked(button, event):
    item = next((it for it in _items.values() if it.ns.button() is button), None)
    if item is None:
        return
    if base.window(item.key[0]) is None:       # its window is gone: so is the icon (Windows drops it on a hover)
        _remove(item.key)
        return
    _state["click"] = (time.monotonic(), item.key, anchor(button, event))
    if item.message:
        loop.PostMessageW(item.key[0], item.message, item.key[1], click_message(event))


def _pointer():
    return NSEvent.mouseLocation()


def _on(p, r):
    """p in r, its edges in: the pointer at the very top of a screen is in its menu bar."""
    return r.origin.x <= p.x <= r.origin.x + r.size.width and r.origin.y <= p.y <= r.origin.y + r.size.height


def anchor(button, event):
    """(x, y): the top-left corner, in Cocoa points, of a menu that opens from a click on a status item: the item's
    left edge (where the pointer is less how far into the button the click was), the menu bar's bottom."""
    at = _pointer()
    into = 0.0
    if event is not None and event.type() in MOUSE_EVENTS and event.window() is button.window():
        into = button.convertPoint_fromView_(event.locationInWindow(), None).x
        into = min(max(into, 0.0), button.bounds().size.width)
    screens = list(NSScreen.screens() or [])
    sc = next((sc for sc in screens if _on(at, sc.frame())), screens[0] if screens else None)
    if sc is None:
        return at.x - into, at.y
    top = sc.frame().origin.y + sc.frame().size.height
    bar = max(top - (sc.visibleFrame().origin.y + sc.visibleFrame().size.height),
              NSStatusBar.systemStatusBar().thickness())
    return at.x - into, top - bar


def menu_anchor():
    """(x, y, button): where a menu opened now goes (anchor()) and the button it opens from, if a status item was
    clicked within MENU_AFTER_CLICK; else None.  Taken once."""
    click, _state["click"] = _state["click"], None
    if click is None or time.monotonic() - click[0] > MENU_AFTER_CLICK or click[1] not in _items:
        return None
    return click[2] + (_items[click[1]].ns.button(),)


# --------------------------------------------------------------------------- for tests
def status_item(hwnd, uid):
    """The NSStatusItem of (hwnd, uID), or None."""
    item = _items.get((base.handle(hwnd), int(uid)))
    return item.ns if item is not None else None
