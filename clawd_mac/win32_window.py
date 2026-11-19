# -*- coding: utf-8 -*-
"""Windows: classes, the NSPanels behind HWNDs, where they are and in what order, what a layered window shows
(UpdateLayeredWindow) and which of its pixels take the mouse.

Every window is a borderless non-activating NSPanel that never becomes key or main: clear, no shadow, on all
Spaces (also beside a full-screen app), out of Mission Control's cycle, not hidden with its app.  WS_EX_TOPMOST
puts it on the floating level, above normal windows.  Its rectangle is kept in virtual px (win32_screen) and the
panel's frame follows from it, so GetWindowRect gives back exactly what was set.

A layered window shows the last picture UpdateLayeredWindow gave it: the bitmap selected into hdcSrc, copied into a
CGImage (premultiplied BGRA: kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Little, sRGB) that is its
layer's contents, with layer.contentsScale = S; SourceConstantAlpha is the panel's alphaValue.  A copy of the pixels
stays for hit-testing: a poll (HIT_HZ, only while visible layered windows are there) lets each window take the mouse
where its pixel under the cursor has alpha > 0 and lets it through elsewhere (ignoresMouseEvents), never switching
while a button is down on it.  WS_EX_TRANSPARENT windows never take the mouse."""
import math

import AppKit
import objc
import Quartz
from AppKit import NSColor, NSEvent, NSNotificationCenter, NSPanel, NSTimer, NSRunLoop, NSRunLoopCommonModes
from AppKit import NSWorkspace
from Foundation import NSData, NSMakeRect, NSObject

from clawd_mac import win32_base as base
from clawd_mac import win32_gdi as gdi
from clawd_mac import win32_input as mouse
from clawd_mac import win32_loop as loop
from clawd_mac import win32_screen as screen

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
SW_HIDE = 0
SW_MINIMIZED = (2, 6, 7, 11)  # SW_SHOWMINIMIZED, SW_MINIMIZE, SW_SHOWMINNOACTIVE, SW_FORCEMINIMIZE: hidden here
HWND_TOP, HWND_BOTTOM, HWND_TOPMOST, HWND_NOTOPMOST = 0, 1, -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER = 0x0001, 0x0002, 0x0004
SWP_SHOWWINDOW, SWP_HIDEWINDOW = 0x0040, 0x0080
WM_DESTROY = 0x0002
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_DISPLAYCHANGE = 0x007E
CW_USEDEFAULT = -0x80000000
DISPLAY_BITS = 32
HIT_HZ = 40                 # the hit-test poll: how often the windows look at the pixel under the cursor
ATOM_FIRST = 0xC000
STYLE = AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel
BEHAVIOUR = (AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorStationary
             | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary | AppKit.NSWindowCollectionBehaviorIgnoresCycle)
BITMAP_INFO = Quartz.kCGImageAlphaPremultipliedFirst | Quartz.kCGBitmapByteOrder32Little

_classes = {}               # class name, casefolded -> WindowClass
_state = {"poll": None, "poller": None, "observer": None, "foreground": 0, "srgb": None}


class WindowClass(object):
    def __init__(self, name, style, wndproc, cursor, atom):
        self.name, self.style, self.wndproc, self.cursor, self.atom = name, style, wndproc, cursor, atom


class ClawdMacPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


class Window(object):
    """An HWND: its class, its rectangle (virtual px), its panel, view and layer, and for hit-testing the pixels it
    shows last (top-down BGRA, pw x ph)."""

    is_window = True

    def __init__(self, cls, title, ex_style, style, rect):
        self.cls, self.title, self.ex_style, self.style = cls, title or "", ex_style, style
        self.x, self.y, self.w, self.h = rect
        self.hwnd = 0
        self.alive = True
        self.dying = False
        self.visible = False
        self.layered = bool(ex_style & WS_EX_LAYERED)
        self.transparent = bool(ex_style & WS_EX_TRANSPARENT)
        self.pixels, self.pw, self.ph, self.alpha = None, 0, 0, 255
        self.ignoring = True
        self.buttons = set()                   # mouse buttons down on it now (from its events)
        self.control_click = False             # the left button down on it now came with Control: a right click
        self.track_leave = False               # TrackMouseEvent(TME_LEAVE) asked for one WM_MOUSELEAVE
        self.wheel_rest = 0.0
        self.last_move = None                  # (time, x, y) of the last hover move sent: one event can come twice
        self.panel = self.view = self.layer = None

    @property
    def wndproc(self):
        return self.cls.wndproc

    def opaque_at(self, x, y):
        """Does the pixel at client (x, y) take the mouse: inside the picture and alpha > 0."""
        if self.pixels is None or self.transparent or not self.alpha or not (0 <= x < self.w and 0 <= y < self.h):
            return False
        if (self.pw, self.ph) != (self.w, self.h):     # resized by SetWindowPos since: the layer stretches it
            x, y = x * self.pw // max(self.w, 1), y * self.ph // max(self.h, 1)
        if not (0 <= x < self.pw and 0 <= y < self.ph):
            return False
        return self.pixels[(y * self.pw + x) * 4 + 3] > 0

    def set_ignoring(self, ignore):
        ignore = ignore or self.transparent
        if ignore != self.ignoring and self.panel is not None:
            self.panel.setIgnoresMouseEvents_(ignore)
            self.ignoring = ignore

    def pass_through(self):
        if not self.buttons:
            self.set_ignoring(True)


# --------------------------------------------------------------------------- classes
def RegisterClassExW(pwc):
    wc = base.deref(pwc)
    name = base.text(wc.lpszClassName) if wc is not None else None
    if not name:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    key = name.casefold()
    if key in _classes:
        return base.fail(base.ERROR_CLASS_ALREADY_EXISTS)
    proc = wc.lpfnWndProc
    atom = ATOM_FIRST + len(_classes)
    _classes[key] = WindowClass(name, base.number(wc.style), proc if proc else None, base.handle(wc.hCursor), atom)
    return atom


def _class(name):
    if isinstance(name, str):
        return _classes.get(name.casefold())
    atom = base.number(name)
    return next((c for c in _classes.values() if c.atom == atom), None)


def UnregisterClassW(name, hinst):
    cls = _class(base.text(name) if not isinstance(name, int) else name)
    if cls is None:
        return base.fail(base.ERROR_CLASS_DOES_NOT_EXIST)
    del _classes[cls.name.casefold()]
    return 1


# --------------------------------------------------------------------------- windows
def _srgb():
    if _state["srgb"] is None:
        _state["srgb"] = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    return _state["srgb"]


def _make_panel(win):
    loop.app()
    s = screen.scale()
    p = ClawdMacPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        screen.frame_of(win.x, win.y, win.w, win.h), STYLE, AppKit.NSBackingStoreBuffered, False)
    p.setOpaque_(False)
    p.setBackgroundColor_(NSColor.clearColor())
    p.setHasShadow_(False)
    p.setLevel_(AppKit.NSFloatingWindowLevel if win.ex_style & WS_EX_TOPMOST else AppKit.NSNormalWindowLevel)
    p.setHidesOnDeactivate_(False)
    p.setReleasedWhenClosed_(False)
    p.setCanHide_(False)
    p.setCollectionBehavior_(BEHAVIOUR)
    p.setIgnoresMouseEvents_(True)            # until the hit-test sees an opaque pixel under the cursor
    p.setAcceptsMouseMovedEvents_(True)
    p.setTitle_(win.title)
    view = mouse.ClawdMacView.alloc().initWithFrame_(NSMakeRect(0, 0, win.w / s, win.h / s))
    layer = Quartz.CALayer.layer()
    layer.setContentsGravity_(Quartz.kCAGravityResize)
    layer.setContentsScale_(s)
    layer.setOpaque_(False)
    view.setLayer_(layer)                      # layer-hosting: AppKit never draws over its contents
    view.setWantsLayer_(True)
    layer.setFrame_(view.bounds())
    view.win = win
    p.setContentView_(view)
    p.makeFirstResponder_(view)                # moves the window gets (not only its tracking area's) go to the view
    win.panel, win.view, win.layer = p, view, layer


def CreateWindowExW(ex_style, class_name, title, style, x, y, w, h, parent, menu, hinst, param):
    cls = _class(class_name if isinstance(class_name, int) else base.text(class_name))
    if cls is None:
        return base.fail(base.ERROR_CANNOT_FIND_WND_CLASS)
    rect = [base.number(v) for v in (x, y, w, h)]
    rect = [0 if v == CW_USEDEFAULT else v for v in rect]
    win = Window(cls, base.text(title), base.number(ex_style), base.number(style) & 0xFFFFFFFF, rect)
    _make_panel(win)
    win.hwnd = base.new_handle(win)
    if win.style & WS_VISIBLE:
        _show(win)
    return win.hwnd


def DestroyWindow(hwnd):
    """WM_DESTROY to its procedure (the window is still a window meanwhile), then it is gone with its timers."""
    win = base.window(hwnd)
    if win is None or win.dying:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    win.dying = True
    h = win.hwnd
    loop.kill_all(h)
    mouse.forget(h)
    loop.send(h, WM_DESTROY, 0, 0)
    win.alive = False
    win.view.win = None
    win.panel.orderOut_(None)
    win.panel.close()
    base.release(h)
    if _state["foreground"] == h:
        _state["foreground"] = 0
    _hit_update()
    return 1


def _show(win):
    win.panel.orderFrontRegardless()
    win.visible = True
    _hit_update()


def _hide(win):
    win.panel.orderOut_(None)
    win.visible = False
    win.set_ignoring(True)
    if win.track_leave:                        # the cursor is off it now
        win.track_leave = False
        loop.PostMessageW(win.hwnd, mouse.WM_MOUSELEAVE, 0, 0)
    _hit_update()


def ShowWindow(hwnd, cmd):
    """-> 1 if it was visible.  SW_HIDE (and minimizing) hides, every other command shows without activating."""
    win = base.window(hwnd)
    if win is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    was = win.visible
    cmd = base.number(cmd)
    if cmd == SW_HIDE or cmd in SW_MINIMIZED:
        if was:
            _hide(win)
    elif not was:
        _show(win)
    return 1 if was else 0


def _place(win, x, y, w, h):
    moved, sized = (x, y) != (win.x, win.y), (w, h) != (win.w, win.h)
    if not moved and not sized:
        return
    win.x, win.y, win.w, win.h = x, y, w, h
    frame = screen.frame_of(x, y, w, h)
    if sized:
        win.panel.setFrame_display_(frame, False)
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(True)
        win.layer.setFrame_(win.view.bounds())
        Quartz.CATransaction.commit()
    else:
        win.panel.setFrameOrigin_(frame.origin)


def _order(win, after):
    """Windows' z-order on the panels of one level: HWND_TOP / HWND_TOPMOST to its front, HWND_BOTTOM to its back,
    a window: right behind it.  Only visible panels have a place to take."""
    if not win.visible:
        return
    if after in (HWND_TOP, HWND_TOPMOST):
        win.panel.orderFrontRegardless()
    elif after == HWND_BOTTOM:
        win.panel.orderWindow_relativeTo_(AppKit.NSWindowBelow, 0)
    elif after != HWND_NOTOPMOST:
        other = base.window(after)
        if other is not None and other.visible and other is not win:
            win.panel.orderWindow_relativeTo_(AppKit.NSWindowBelow, other.panel.windowNumber())


def SetWindowPos(hwnd, after, x, y, cx, cy, flags):
    win = base.window(hwnd)
    if win is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    flags = base.number(flags)
    nx, ny = (win.x, win.y) if flags & SWP_NOMOVE else (base.number(x), base.number(y))
    nw, nh = (win.w, win.h) if flags & SWP_NOSIZE else (base.number(cx), base.number(cy))
    _place(win, nx, ny, nw, nh)
    if flags & SWP_HIDEWINDOW and win.visible:
        _hide(win)
    if flags & SWP_SHOWWINDOW and not win.visible:
        _show(win)
    if not flags & SWP_NOZORDER:
        _order(win, base.handle(after))
    return 1


def GetWindowRect(hwnd, prect):
    win = base.window(hwnd)
    r = base.deref(prect)
    if win is None or r is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE if win is None else base.ERROR_INVALID_PARAMETER)
    r.left, r.top, r.right, r.bottom = win.x, win.y, win.x + win.w, win.y + win.h
    return 1


def IsWindow(hwnd):
    return 1 if base.window(hwnd) is not None else 0


def IsWindowVisible(hwnd):
    win = base.window(hwnd)
    return 1 if win is not None and win.visible else 0


def IsIconic(hwnd):
    return 0                                   # nothing is ever minimized


def GetClassNameW(hwnd, buf, size):
    win = base.window(hwnd)
    if win is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    name = win.cls.name[:max(base.number(size) - 1, 0)]
    buf.value = name
    return len(name)


def GetWindowTextLengthW(hwnd):
    win = base.window(hwnd)
    return len(win.title) if win is not None else base.fail(base.ERROR_INVALID_WINDOW_HANDLE)


def SetForegroundWindow(hwnd):
    """Our windows only (they never take the keyboard: it is remembered, that is all)."""
    win = base.window(hwnd)
    if win is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    _state["foreground"] = win.hwnd
    return 1


def GetForegroundWindow():
    """One of ours only while this app is the active one (it hardly ever is); other apps' windows are not seen."""
    h = _state["foreground"]
    if h and base.window(h) is not None and loop.started() and loop.app().isActive():
        return h
    return 0


# --------------------------------------------------------------------------- the picture
def UpdateLayeredWindow(hwnd, hdc_dst, ppt_dst, psize, hdc_src, ppt_src, color_key, pblend, flags):
    win = base.window(hwnd)
    if win is None:
        return base.fail(base.ERROR_INVALID_WINDOW_HANDLE)
    if not win.layered:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    pos, size, src, blend = (base.deref(a) for a in (ppt_dst, psize, ppt_src, pblend))
    x, y = (int(pos.x), int(pos.y)) if pos is not None else (win.x, win.y)
    w, h = (int(size.cx), int(size.cy)) if size is not None else (win.w, win.h)
    alpha = int(blend.SourceConstantAlpha) if blend is not None else 255
    pixels = None
    if base.handle(hdc_src):
        sx, sy = (int(src.x), int(src.y)) if src is not None else (0, 0)
        pixels = gdi.pixels(hdc_src, sx, sy, w, h)
        if pixels is None:
            return base.fail(base.ERROR_INVALID_PARAMETER)
    _place(win, x, y, w, h)
    if pixels is not None:
        _present(win, pixels, w, h)
    if alpha != win.alpha:
        win.panel.setAlphaValue_(alpha / 255.0)
        win.alpha = alpha
    return 1


def _image(pixels, w, h):
    if not w or not h:
        return None
    data = NSData.alloc().initWithBytes_length_(pixels, len(pixels))
    provider = Quartz.CGDataProviderCreateWithCFData(data)
    return Quartz.CGImageCreate(w, h, 8, 32, w * 4, _srgb(), BITMAP_INFO, provider, None, False,
                                Quartz.kCGRenderingIntentDefault)


def _present(win, pixels, w, h):
    image = _image(pixels, w, h)
    Quartz.CATransaction.begin()
    Quartz.CATransaction.setDisableActions_(True)
    win.layer.setContents_(image)
    Quartz.CATransaction.commit()
    win.pixels, win.pw, win.ph = pixels, w, h


# --------------------------------------------------------------------------- hit-testing
class ClawdMacHitPoller(NSObject):
    def poll_(self, timer):
        try:
            with objc.autorelease_pool():
                _poll()
        except Exception:
            base.report("hit-test poll")


def _hit_windows():
    return [w for w in base.objects(Window) if w.alive and w.visible and w.layered and not w.transparent]


def _hit_update():
    """The poll runs while visible layered windows are there, and only then."""
    need = bool(_hit_windows())
    timer = _state["poll"]
    if need and timer is None:
        if _state["poller"] is None:
            _state["poller"] = ClawdMacHitPoller.alloc().init()
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1.0 / HIT_HZ, _state["poller"],
                                                                                  "poll:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
        _state["poll"] = timer
    elif not need and timer is not None:
        timer.invalidate()
        _state["poll"] = None


def polling():
    """Is the hit-test poll running (tests)."""
    return _state["poll"] is not None


def _poll():
    wins = _hit_windows()
    if not wins:
        _hit_update()
        return
    loc = NSEvent.mouseLocation()
    x, y = screen.to_pixels(loc.x, loc.y)
    hit_test(wins, int(math.floor(x)), int(math.floor(y)))


def hit_test(wins, x, y):
    """Each window takes the mouse where its pixel under (x, y) is opaque; one with a button down on it or the
    capture keeps what it has.  A window that wanted to hear of the cursor leaving now does.  The cursor follows:
    the class's onto the opaque pixels (also of a window moving under a still pointer), the arrow off them."""
    cap = mouse.GetCapture()
    took = left = None
    for win in wins:
        if win.buttons or cap == win.hwnd:
            continue
        over = win.opaque_at(x - win.x, y - win.y)
        if over == win.ignoring:               # it takes the mouse now, or lets go of it
            took, left = (win, left) if over else (took, win)
        win.set_ignoring(not over)
        if win.track_leave and not over:
            win.track_leave = False
            loop.PostMessageW(win.hwnd, mouse.WM_MOUSELEAVE, 0, 0)
    if took is not None:
        mouse.show_cursor(mouse.cursor_of(took))
    elif left is not None:
        mouse.cursor_off()


# --------------------------------------------------------------------------- the system
class ClawdMacObserver(NSObject):
    def screensChanged_(self, note):
        try:
            screens_changed()
        except Exception:
            base.report("screen change")

    def powerOff_(self, note):
        try:
            power_off()
        except Exception:
            base.report("power off")


def _observe(app):
    obs = _state["observer"] = ClawdMacObserver.alloc().init()
    NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
        obs, "screensChanged:", AppKit.NSApplicationDidChangeScreenParametersNotification, None)
    NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
        obs, "powerOff:", AppKit.NSWorkspaceWillPowerOffNotification, None)


loop.on_start(_observe)


def _top_level():
    return [w for w in base.objects(Window) if w.alive]


def screens_changed():
    """The panels where their rectangles are in the new arrangement (the primary's height may have changed), then
    WM_DISPLAYCHANGE to every top-level window."""
    screen.changed()
    for win in _top_level():
        win.panel.setFrame_display_(screen.frame_of(win.x, win.y, win.w, win.h), False)
    l, t, r, b = screen.screens()[0].frame
    for win in _top_level():
        loop.send(win.hwnd, WM_DISPLAYCHANGE, DISPLAY_BITS, base.pack(r - l, b - t))


def power_off():
    """The user logs out (or shuts down): WM_QUERYENDSESSION, then WM_ENDSESSION(1), to every top-level window."""
    wins = _top_level()
    for win in wins:
        loop.send(win.hwnd, WM_QUERYENDSESSION, 0, 0)
    for win in wins:
        if win.alive:
            loop.send(win.hwnd, WM_ENDSESSION, 1, 0)


# --------------------------------------------------------------------------- for tests
def find_windows(title=None):
    """The hwnds of the live windows (with this title), oldest first."""
    return [w.hwnd for w in _top_level() if title is None or w.title == title]


def panel_of(hwnd):
    win = base.window(hwnd)
    return win.panel if win is not None else None


def presented(hwnd):
    """(w, h, BGRA bytes) read back from the window's layer contents, or None."""
    win = base.window(hwnd)
    image = win.layer.contents() if win is not None else None
    if image is None:
        return None
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image))
    return Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image), bytes(data)
