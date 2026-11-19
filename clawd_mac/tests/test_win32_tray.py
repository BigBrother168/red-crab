# -*- coding: utf-8 -*-
"""clawd_mac.win32's tray icon (a status item in the menu bar), Control+click, the cursor, and posted messages while
a menu tracks.  The calls are clawd_pet.pyw's own (its structures, its _api bindings, Tray._icon); clicks are
performClick or NSEvents made in this process and handed to our own windows, never anything posted to the system."""
import ctypes
import os
import time

import AppKit
import pytest
import Quartz
from AppKit import NSEvent, NSScreen, NSStatusBar
from Foundation import NSMakePoint

from clawd_mac import win32_base as base
from clawd_mac import win32_input as mouse
from clawd_mac import win32_loop as loop
from clawd_mac import win32_menu as menu
from clawd_mac import win32_synthetic as synth
from clawd_mac import win32_tray as tray
from clawd_mac import win32_window as window
from test_win32 import Kit, later, lo_hi, load_pet, picture, place

WM_USER = 0x0400
UID = 1
RED, BLUE = (0, 0, 255, 255), (255, 0, 0, 255)     # BGRA, straight alpha as an icon has it
MENU_LEVEL = Quartz.CGWindowLevelForKey(Quartz.kCGPopUpMenuWindowLevelKey)
NEAR_PT = 6                 # how close the menu's corner is to the status item's (AppKit's own inset)


@pytest.fixture(scope="module")
def pet():
    return load_pet("clawd_pet_for_tray_tests")


@pytest.fixture
def kit(pet):
    k = Kit(pet)
    yield k
    for key in list(tray._items):
        tray._remove(key)
    k.close()


def icon_pixels(s, corner):
    """s x s pixels, top-down: blue, but the top-left one `corner`."""
    px = bytearray(bytes(BLUE) * (s * s))
    px[0:4] = bytes(corner)
    return bytes(px)


def nid_of(pet, hwnd, flags, icon=0, tip="", message=0):
    """A NOTIFYICONDATAW as Tray._nid fills it."""
    nid = pet.NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(pet.NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = UID
    nid.uFlags = flags
    nid.uCallbackMessage = message
    nid.hIcon = icon
    nid.szTip = tip
    return nid


def add(pet, hwnd, icon, tip="Clawd"):
    nid = nid_of(pet, hwnd, pet.NIF_MESSAGE | pet.NIF_ICON | pet.NIF_TIP, icon, tip, pet.WM_TRAY)
    assert pet.Shell_NotifyIconW(pet.NIM_ADD, ctypes.byref(nid))
    return tray.status_item(hwnd, UID)


def rgba_at(image, x, y):
    """The pixel of the image's own bitmap (top-left origin) as 0..255 RGBA, in its own colour space (sRGB)."""
    c = image.representations()[0].colorAtX_y_(x, y)
    return tuple(int(round(v * 255)) for v in (c.redComponent(), c.greenComponent(), c.blueComponent(),
                                               c.alphaComponent()))


def posted(pet, rec):
    """Every message posted so far, dispatched (GetMessageW until the quit posted after them)."""
    pet.PostQuitMessage(0)
    msg = pet.MSG()
    while pet.GetMessageW(ctypes.byref(msg), None, 0, 0):
        pet.DispatchMessageW(ctypes.byref(msg))
    return rec.calls


def shown(win):
    """Whether the middle of a window is on a screen.  A status item the menu bar does not show has its window off
    every screen (at y = -30 on GitHub's macOS 26 runners)."""
    f = win.frame()
    mid = NSMakePoint(f.origin.x + f.size.width / 2, f.origin.y + f.size.height / 2)
    return any(tray._on(mid, sc.frame()) for sc in NSScreen.screens())


def click_button(button, kind_down, kind_up, flags):
    """A click on a status item's button: its mouse-up waits in our own app's queue, its mouse-down is handed to the
    button's window (whose tracking then takes the up)."""
    win = button.window()
    loc = button.convertPoint_toView_(NSMakePoint(4, 4), None)
    make = getattr(NSEvent, "mouseEventWithType_location_modifierFlags_timestamp_"
                            "windowNumber_context_eventNumber_clickCount_pressure_")
    up = make(kind_up, loc, flags, time.monotonic(), win.windowNumber(), None, 0, 1, 0.0)
    down = make(kind_down, loc, flags, time.monotonic(), win.windowNumber(), None, 0, 1, 1.0)
    AppKit.NSApp().postEvent_atStart_(up, True)
    win.sendEvent_(down)


# --------------------------------------------------------------------------- icons and status items
def test_an_icon_becomes_a_status_item_that_changes_and_goes(kit, pet):
    s = pet.GetSystemMetrics(pet.SM_CXSMICON)
    icon = pet.Tray._icon(icon_pixels(s, RED), s)
    dim = pet.Tray._icon(icon_pixels(s, (0, 0, 255, 102)), s)
    hwnd = kit.window(0, 0, 0, 0, ex=pet.WS_EX_TOOLWINDOW)
    item = add(pet, hwnd, icon)
    button = item.button()
    assert str(button.toolTip()) == "Clawd"
    image = button.image()
    side = NSStatusBar.systemStatusBar().thickness() - tray.TRAY_PADDING_PT
    assert (image.size().width, image.size().height) == (side, side) and not image.isTemplate()
    rep = image.representations()[0]
    assert (rep.pixelsWide(), rep.pixelsHigh()) == (s, s)          # the icon's own pixels, drawn at the bar's size
    assert rgba_at(image, 0, 0) == (255, 0, 0, 255) and rgba_at(image, 1, 0) == (0, 0, 255, 255)
    again = nid_of(pet, hwnd, pet.NIF_ICON, icon)
    ctypes.set_last_error(0)
    assert not pet.Shell_NotifyIconW(pet.NIM_ADD, ctypes.byref(again)) and ctypes.get_last_error() == 183
    mod = nid_of(pet, hwnd, pet.NIF_ICON | pet.NIF_TIP, dim, "Clawd (hidden)")
    assert pet.Shell_NotifyIconW(pet.NIM_MODIFY, ctypes.byref(mod))
    assert tray.status_item(hwnd, UID) is item and str(button.toolTip()) == "Clawd (hidden)"
    assert button.image() is not image and rgba_at(button.image(), 0, 0)[3] == 102    # straight alpha kept
    assert pet.Shell_NotifyIconW(pet.NIM_DELETE, ctypes.byref(nid_of(pet, hwnd, 0)))
    assert tray.status_item(hwnd, UID) is None
    assert not pet.Shell_NotifyIconW(pet.NIM_MODIFY, ctypes.byref(mod))
    assert not pet.Shell_NotifyIconW(pet.NIM_DELETE, ctypes.byref(mod))
    assert pet.DestroyIcon(icon) and pet.DestroyIcon(dim) and not pet.DestroyIcon(icon)


def test_icons_of_a_mask_and_the_generic_one(kit, pet):
    s = 16
    color = pet.CreateBitmap(s, s, 1, 32, ctypes.create_string_buffer(bytes((10, 20, 30, 0)) * (s * s)))
    mask_bits = bytearray(2 * s)
    mask_bits[0] = 0x80                                  # the top-left pixel is transparent, the others show
    mask = pet.CreateBitmap(s, s, 1, 1, ctypes.create_string_buffer(bytes(mask_bits), len(mask_bits)))
    icon = pet.CreateIconIndirect(ctypes.byref(pet.ICONINFO(True, 0, 0, mask, color)))
    assert icon and pet.DeleteObject(color) and pet.DeleteObject(mask)
    pixels = base.lookup(icon, tray.Icon).pixels        # still there: the icon copied them
    assert pixels[0:4] == bytes((10, 20, 30, 0)) and pixels[4:8] == bytes((10, 20, 30, 255))
    assert pet.DestroyIcon(icon)
    assert not pet.CreateIconIndirect(ctypes.byref(pet.ICONINFO(True, 0, 0, 0, 0)))
    app = pet.LoadIconW(None, pet.IDI_APPLICATION)
    assert app and pet.LoadIconW(None, pet.IDI_APPLICATION) == app
    assert pet.DestroyIcon(app) and base.lookup(app, tray.Icon) is not None     # shared: it stays
    hwnd = kit.window(0, 0, 0, 0, ex=pet.WS_EX_TOOLWINDOW)
    image = add(pet, hwnd, app).button().image()
    side = NSStatusBar.systemStatusBar().thickness() - tray.TRAY_PADDING_PT
    assert image is not None and image.size().height == side


# --------------------------------------------------------------------------- clicks and the menu under the item
def test_clicks_post_wm_tray_as_the_tray_menu_and_option_click_as_the_left_click(kit, pet):
    s = pet.GetSystemMetrics(pet.SM_CXSMICON)
    icon = pet.Tray._icon(icon_pixels(s, RED), s)
    hwnd = kit.window(0, 0, 0, 0, ex=pet.WS_EX_TOOLWINDOW)
    button = add(pet, hwnd, icon).button()
    loop.run_for(0.2)                                    # the menu bar lays it out
    button.performClick_(None)
    left, right = AppKit.NSEventTypeLeftMouseDown, AppKit.NSEventTypeLeftMouseUp
    click_button(button, left, right, AppKit.NSEventModifierFlagOption)
    click_button(button, left, right, AppKit.NSEventModifierFlagControl)
    click_button(button, AppKit.NSEventTypeRightMouseDown, AppKit.NSEventTypeRightMouseUp, 0)
    got = [(c[2], c[3]) for c in posted(pet, kit.rec) if c[0] == hwnd and c[1] == pet.WM_TRAY]
    assert got == [(UID, pet.WM_RBUTTONUP), (UID, pet.WM_LBUTTONUP), (UID, pet.WM_RBUTTONUP),
                   (UID, pet.WM_RBUTTONUP)]
    pet.DestroyIcon(icon)


def test_the_menu_after_a_status_item_click_opens_under_it(kit, pet, monkeypatch):
    s = pet.GetSystemMetrics(pet.SM_CXSMICON)
    icon = pet.Tray._icon(icon_pixels(s, RED), s)
    hwnd = kit.window(0, 0, 0, 0, ex=pet.WS_EX_TOOLWINDOW)
    button = add(pet, hwnd, icon).button()
    loop.run_for(0.2)
    if not shown(button.window()):
        f = button.window().frame()
        pet.DestroyIcon(icon)
        pytest.skip("the menu bar does not show the status item: its window is off every screen, at %r"
                    % ((f.origin.x, f.origin.y, f.size.width, f.size.height),))
    primary = NSScreen.screens()[0]
    h0 = primary.frame().size.height
    bar = max(h0 - (primary.visibleFrame().origin.y + primary.visibleFrame().size.height),
              NSStatusBar.systemStatusBar().thickness())
    monkeypatch.setattr(tray, "_pointer", lambda: NSMakePoint(500.0, h0 - 5))      # the pointer on the item
    assert tray.menu_anchor() is None                    # no click yet
    left, right = AppKit.NSEventTypeLeftMouseDown, AppKit.NSEventTypeLeftMouseUp
    click_button(button, left, right, 0)                 # 4 pt into the button
    assert tray._state["click"][2] == (496.0, h0 - bar)  # the item's left edge, the menu bar's bottom
    m = pet.CreatePopupMenu()
    pet.AppendMenuW(m, pet.MF_STRING, 11, "Wave")
    seen = {}

    def look():
        seen["lit"] = bool(button.isHighlighted())
        seen["menus"] = [w["kCGWindowBounds"] for w in
                         Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0)
                         if w["kCGWindowOwnerPID"] == os.getpid() and w["kCGWindowLayer"] == MENU_LEVEL]
        menu.tracking().cancelTracking()
    later(0.3, look)
    assert pet.TrackPopupMenu(m, pet.TPM_RETURNCMD | pet.TPM_NONOTIFY, 0, 0, 0, hwnd, None) == 0
    (bounds,) = seen["menus"]
    assert seen["lit"] and not button.isHighlighted()
    assert abs(bounds["X"] - 496) <= NEAR_PT and abs(bounds["Y"] - bar) <= NEAR_PT    # Quartz: y from the top
    assert tray.menu_anchor() is None                    # taken by that menu
    button.performClick_(None)
    time.sleep(tray.MENU_AFTER_CLICK + 0.1)
    assert tray.menu_anchor() is None                    # too long ago: the menu opens at the point given
    posted(pet, kit.rec)                                 # the clicks' WM_TRAY
    pet.DestroyMenu(m)
    pet.DestroyIcon(icon)


# --------------------------------------------------------------------------- Control+click, the cursor
def test_control_click_is_a_right_click(kit, pet):
    x, y = place()
    hw, _, _ = kit.layered(x, y, 32, 32, picture(32, 32, 32))
    synth.mouse(hw, "left_down", x + 3, y + 4, flags=synth.CONTROL)
    synth.mouse(hw, "left_drag", x + 5, y + 4, flags=synth.CONTROL)
    synth.mouse(hw, "left_up", x + 5, y + 4)             # Control let go first: still the right button's up
    synth.mouse(hw, "left_down", x + 6, y + 6)
    synth.mouse(hw, "left_up", x + 6, y + 6)
    got = [(m, wp, lo_hi(lp)) for h, m, wp, lp in kit.rec.calls if h == hw and 0x200 <= m <= 0x20A]
    assert got == [(pet.WM_RBUTTONDOWN, mouse.MK_RBUTTON, (3, 4)), (pet.WM_MOUSEMOVE, mouse.MK_RBUTTON, (5, 4)),
                   (pet.WM_RBUTTONUP, 0, (5, 4)), (pet.WM_LBUTTONDOWN, mouse.MK_LBUTTON, (6, 6)),
                   (pet.WM_LBUTTONUP, 0, (6, 6))]


def test_the_class_cursor_over_opaque_pixels_and_the_arrow_elsewhere(kit, pet):
    x, y = place()
    hw, _, _ = kit.layered(x, y, 32, 32, picture(32, 32, 16))
    win = base.window(hw)
    hand, arrow = AppKit.NSCursor.pointingHandCursor(), AppKit.NSCursor.arrowCursor()
    assert mouse.cursor_at(win, 4, 4) is hand and mouse.cursor_at(win, 20, 4) is arrow
    synth.mouse(hw, "move", x + 4, y + 5)
    assert mouse.shown_cursor() is hand
    synth.mouse(hw, "move", x + 20, y + 5)
    assert mouse.shown_cursor() is None                  # given back: the arrow
    window.hit_test([win], x + 4, y + 4)                 # the pet under a still pointer
    assert mouse.shown_cursor() is hand
    window.hit_test([win], x + 24, y + 4)
    assert mouse.shown_cursor() is None
    for idc, name in ((32646, "openHandCursor"), (32512, "arrowCursor"), (32515, "arrowCursor")):
        win.cls.cursor = pet.LoadCursorW(None, idc)
        assert mouse.cursor_of(win) is getattr(AppKit.NSCursor, name)()


# --------------------------------------------------------------------------- posted messages while a menu tracks
def test_messages_posted_while_a_menu_tracks_are_dispatched_before_it_returns(kit, pet):
    x, y = place()
    hw = kit.window(x, y, 10, 10)
    m = pet.CreatePopupMenu()
    pet.AppendMenuW(m, pet.MF_STRING, 11, "Wave")
    seen = {}

    def post():
        pet.PostMessageW(hw, WM_USER + 1, 1, 0)
        pet.PostMessageW(hw, WM_USER + 2, 2, 0)

    def look():
        seen["got"] = [c[1] for c in kit.rec.calls if c[1] > WM_USER]
        ctypes.set_last_error(0)
        seen["nested"] = (pet.TrackPopupMenu(m, pet.TPM_RETURNCMD, x, y, 0, hw, None), ctypes.get_last_error())
        pet.PostMessageW(hw, WM_USER + 3, 3, 0)          # posted as it closes: still before it returns
        menu.tracking().cancelTracking()
    later(0.2, post)
    later(0.4, look)
    assert pet.TrackPopupMenu(m, pet.TPM_RETURNCMD | pet.TPM_NONOTIFY, x, y, 0, hw, None) == 0
    assert seen["got"] == [WM_USER + 1, WM_USER + 2]
    assert seen["nested"] == (0, base.ERROR_POPUP_ALREADY_ACTIVE)
    assert [c[1] for c in kit.rec.calls if c[1] > WM_USER] == [WM_USER + 1, WM_USER + 2, WM_USER + 3]
    assert loop.pending() == 0
    safety = later(3.0, lambda: menu.tracking() and menu.tracking().cancelTracking())
    later(0.2, lambda: pet.PostQuitMessage(7))           # a quit closes the menu and waits for GetMessageW
    start = time.monotonic()
    assert pet.TrackPopupMenu(m, pet.TPM_RETURNCMD | pet.TPM_NONOTIFY, x, y, 0, hw, None) == 0
    assert time.monotonic() - start < 2.0
    safety.invalidate()
    msg = pet.MSG()
    assert pet.GetMessageW(ctypes.byref(msg), None, 0, 0) == 0 and msg.wParam == 7
    pet.DestroyMenu(m)
