# -*- coding: utf-8 -*-
"""Popup menus: built as Win32 builds them (CreatePopupMenu, AppendMenuW), shown by TrackPopupMenu as a modal
NSMenu whose top-left corner is at the point it is given (or, just after a click on a status item, under that item,
as the menu bar's menus open); it returns the id of the item chosen, or 0.  As in a Win32 menu's modal loop, timers
keep firing meanwhile (they are in the common run loop modes, which include the menu's tracking mode) and posted
messages are dispatched (win32_loop.modal), in order; a WM_QUIT posted meanwhile closes the menu and stays for
GetMessageW.  One menu at a time: TrackPopupMenu while one tracks fails (1446), as on Windows.

Labels: '&&' is '&', a single '&' (the accelerator's mark) goes, and so does a tab and what follows it."""
import re

import AppKit
from AppKit import NSMenu, NSMenuItem
from Foundation import NSMakePoint, NSObject

from clawd_mac import win32_base as base
from clawd_mac import win32_loop as loop
from clawd_mac import win32_screen as screen
from clawd_mac import win32_tray as tray

MF_GRAYED = 0x0001
MF_DISABLED = 0x0002
MF_CHECKED = 0x0008
MF_POPUP = 0x0010
MF_SEPARATOR = 0x0800
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100
WM_COMMAND = 0x0111

_state = {"tracking": None}


class Menu(object):
    """A popup menu: its items as (flags, id or submenu handle, label), in order."""

    def __init__(self):
        self.items = []


class ClawdMacMenuChooser(NSObject):
    """The target of every item of one TrackPopupMenu: remembers the id chosen."""

    def choose_(self, item):
        self.chosen = int(item.tag())


def label(s):
    return re.sub(r"&(&?)", r"\1", (s or "").split("\t", 1)[0])


def CreatePopupMenu():
    return base.new_handle(Menu())


def AppendMenuW(hmenu, flags, id_new_item, item):
    menu = base.lookup(hmenu, Menu)
    flags = base.number(flags)
    item_id = base.handle(id_new_item)
    if menu is None or (flags & MF_POPUP and base.lookup(item_id, Menu) is None):
        return base.fail(base.ERROR_INVALID_MENU_HANDLE)
    menu.items.append((flags, item_id, None if flags & MF_SEPARATOR else base.text(item)))
    return 1


def DestroyMenu(hmenu):
    """Its submenus go with it, as on Windows."""
    menu = base.lookup(hmenu, Menu)
    if menu is None:
        return base.fail(base.ERROR_INVALID_MENU_HANDLE)
    base.release(hmenu)
    for flags, item_id, _ in menu.items:
        if flags & MF_POPUP:
            DestroyMenu(item_id)
    return 1


def _build(menu, chooser):
    ns = NSMenu.alloc().initWithTitle_("")
    ns.setAutoenablesItems_(False)
    for flags, item_id, text in menu.items:
        if flags & MF_SEPARATOR:
            ns.addItem_(NSMenuItem.separatorItem())
            continue
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label(text), None, "")
        sub = base.lookup(item_id, Menu) if flags & MF_POPUP else None
        if sub is not None:
            item.setSubmenu_(_build(sub, chooser))
        else:
            item.setTarget_(chooser)
            item.setAction_("choose:")
            item.setTag_(item_id)
        item.setEnabled_(not flags & (MF_GRAYED | MF_DISABLED))
        if flags & MF_CHECKED:
            item.setState_(AppKit.NSControlStateValueOn)
        ns.addItem_(item)
    return ns


def _track(ns, x, y):
    """ns up until it closes: at virtual px (x, y), or under the status item just clicked (highlighted meanwhile).
    Posted messages are dispatched meanwhile; those posted as it closed too, before it returns."""
    anchor = tray.menu_anchor()
    px, py = anchor[:2] if anchor is not None else screen.to_points(x, y)
    button = anchor[2] if anchor is not None else None
    _state["tracking"] = ns
    stop = loop.modal(lambda: loop.dispatch_posted() and ns.cancelTracking())
    if button is not None:
        button.highlight_(True)
    try:
        ns.popUpMenuPositioningItem_atLocation_inView_(None, NSMakePoint(px, py), None)
    finally:
        stop()
        _state["tracking"] = None
        if button is not None:
            button.highlight_(False)
    loop.dispatch_posted()


def TrackPopupMenu(hmenu, flags, x, y, reserved, hwnd, prect):
    """Modal: -> with TPM_RETURNCMD the id chosen or 0; else 1 if one was chosen (posted to hwnd as WM_COMMAND,
    unless TPM_NONOTIFY), 0 if not."""
    menu = base.lookup(hmenu, Menu)
    if menu is None:
        return base.fail(base.ERROR_INVALID_MENU_HANDLE)
    if _state["tracking"] is not None:
        return base.fail(base.ERROR_POPUP_ALREADY_ACTIVE)
    loop.app()
    flags = base.number(flags)
    chooser = ClawdMacMenuChooser.alloc().init()
    chooser.chosen = 0
    ns = _build(menu, chooser)
    _track(ns, base.number(x), base.number(y))
    cmd = chooser.chosen
    if flags & TPM_RETURNCMD:
        return cmd
    if cmd and not flags & TPM_NONOTIFY:
        loop.PostMessageW(hwnd, WM_COMMAND, cmd, 0)
    return 1 if cmd else 0


def tracking():
    """The NSMenu TrackPopupMenu shows now, or None (tests choose from it or cancel it)."""
    return _state["tracking"]
