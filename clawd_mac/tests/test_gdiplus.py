# -*- coding: utf-8 -*-
"""clawd_mac.gdiplus: the GDI+ calls of clawd_pet.pyw and clawd_scale.py, called as they call them, drawn by Quartz
into the caller's memory."""
import ctypes
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from clawd_mac import gdiplus as gp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARGB = 0x000E200B
V = ctypes.c_void_p


class RECTF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float), ("Width", ctypes.c_float), ("Height", ctypes.c_float)]


class POINTF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float)]


class StartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", ctypes.c_int), ("SuppressExternalCodecs", ctypes.c_int)]


def ok(st):
    assert st == 0, "GDI+ status %d" % st


class Canvas(object):
    """A w x h PARGB bitmap on our own memory and its Graphics; pixels() reads that memory as an h x w x 4 BGRA
    array."""

    def __init__(self, w, h, smooth=True):
        self.w, self.h = w, h
        self.buf = (ctypes.c_ubyte * (w * h * 4))()
        self.bmp, self.g = V(), V()
        ok(gp.GdipCreateBitmapFromScan0(w, h, w * 4, PARGB, ctypes.addressof(self.buf), ctypes.byref(self.bmp)))
        ok(gp.GdipGetImageGraphicsContext(self.bmp, ctypes.byref(self.g)))
        if smooth:
            ok(gp.GdipSetSmoothingMode(self.g, 4))
            ok(gp.GdipSetTextRenderingHint(self.g, 4))

    def pixels(self):
        return np.frombuffer(bytes(self.buf), np.uint8).reshape(self.h, self.w, 4).astype(int)

    def close(self):
        ok(gp.GdipDeleteGraphics(self.g))
        ok(gp.GdipDisposeImage(self.bmp))


@pytest.fixture
def canvas():
    made = []

    def make(w, h, smooth=True):
        c = Canvas(w, h, smooth)
        made.append(c)
        return c
    yield make
    for c in made:
        c.close()


def fill(c, path, argb):
    brush = V()
    ok(gp.GdipCreateSolidFill(argb, ctypes.byref(brush)))
    ok(gp.GdipFillPath(c.g, brush, path))
    ok(gp.GdipDeleteBrush(brush))


def new_path():
    path = V()
    ok(gp.GdipCreatePath(0, ctypes.byref(path)))
    return path


def polygon(xys):
    pts = (POINTF * len(xys))()
    for i, (x, y) in enumerate(xys):
        pts[i] = POINTF(x, y)
    path = new_path()
    ok(gp.GdipAddPathPolygon(path, pts, len(xys)))
    return path


def rrect(x0, y0, x1, y1, r):
    """As SignBoard._rrect."""
    path = new_path()
    d = 2 * r
    ok(gp.GdipAddPathArc(path, x0, y0, d, d, 180.0, 90.0))
    ok(gp.GdipAddPathArc(path, x1 - d, y0, d, d, 270.0, 90.0))
    ok(gp.GdipAddPathArc(path, x1 - d, y1 - d, d, d, 0.0, 90.0))
    ok(gp.GdipAddPathArc(path, x0, y1 - d, d, d, 90.0, 90.0))
    ok(gp.GdipClosePathFigure(path))
    return path


def ink_box(px, channel=3, level=64):
    ys, xs = np.nonzero(px[:, :, channel] > level)
    return xs.min(), ys.min(), xs.max(), ys.max()


def bgra(argb):
    """ARGB -> the premultiplied BGRA bytes it is in a PARGB bitmap."""
    a = argb >> 24
    return [round((argb >> shift & 255) * a / 255.0) for shift in (0, 8, 16)] + [a]


# ---------------------------------------------------------------------------------------------------- module
def test_import_loads_no_appkit():
    code = "import sys; sys.path.insert(0, %r); import clawd_mac.gdiplus; print('AppKit' in sys.modules)" % ROOT
    out = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_startup_and_shutdown_take_their_token():
    start = len(gp._handles)
    token = ctypes.c_size_t(0)
    ok(gp.GdiplusStartup(ctypes.byref(token), ctypes.byref(StartupInput(1, None, 0, 0)), None))
    assert token.value and len(gp._handles) == start + 1
    assert gp.GdiplusShutdown(token.value) is None
    assert len(gp._handles) == start
    assert gp.GdiplusStartup(ctypes.byref(token), ctypes.byref(StartupInput(9, None, 0, 0)), None) == 17


def test_callers_may_set_restype_and_argtypes():
    gp.GdipFlush.restype, gp.GdipFlush.argtypes = ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]
    assert gp.GdipFlush(V(12345), 1) == gp.InvalidParameter


# ---------------------------------------------------------------------------------------------------- bitmaps
def test_bitmap_wraps_caller_memory_and_drawing_lands_in_it(canvas):
    c = canvas(40, 30, smooth=False)
    ok(gp.GdipSetPixelOffsetMode(c.g, 4))                         # half: pixel i is [i, i + 1]
    path = polygon([(10, 5), (20, 5), (20, 15), (10, 15)])
    fill(c, path, 0xFF2E5440)
    ok(gp.GdipDeletePath(path))
    px = c.pixels()                                               # read straight from the caller's buffer
    assert px[5, 10].tolist() == bgra(0xFF2E5440) and px[14, 19].tolist() == bgra(0xFF2E5440)
    # top-left origin, y down
    assert px[4, 10, 3] == 0 and px[15, 10, 3] == 0 and px[5, 9, 3] == 0 and px[5, 20, 3] == 0


def test_bitmap_with_no_memory_of_its_own_measures(canvas):
    probe, g = V(), V()
    ok(gp.GdipCreateBitmapFromScan0(1, 1, 4, PARGB, None, ctypes.byref(probe)))
    ok(gp.GdipGetImageGraphicsContext(probe, ctypes.byref(g)))
    ok(gp.GdipGraphicsClear(g, 0xFFFFFFFF))
    ok(gp.GdipDeleteGraphics(g))
    ok(gp.GdipDisposeImage(probe))


def test_clear_is_premultiplied_whatever_the_compositing(canvas):
    c = canvas(8, 6)
    ok(gp.GdipGraphicsClear(c.g, 0xFF00FF00))
    ok(gp.GdipGraphicsClear(c.g, 0x80FF0000))                    # not over the green: in its place
    assert (c.pixels() == np.array(bgra(0x80FF0000))).all()
    ok(gp.GdipGraphicsClear(c.g, 0))
    assert not c.pixels().any()


# ---------------------------------------------------------------------------------------------------- images
def blob(w, h, margin):
    """A smooth premultiplied BGRA picture with a transparent margin round it."""
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    cx, cy = w / 2.0, h / 2.0
    r = np.hypot((xx - cx) / (w / 2.0 - margin), (yy - cy) / (h / 2.0 - margin))
    a = np.clip(1.4 - r * 1.4, 0, 1) ** 1.5
    rgb = [0.5 + 0.5 * np.sin(xx / 7.0), 0.5 + 0.5 * np.cos(yy / 9.0), np.full_like(xx, 0.8)]
    out = np.stack([rgb[2] * a, rgb[1] * a, rgb[0] * a, a], axis=-1)
    return np.round(out * 255).astype(np.uint8)


def reference(src, dw, dh, box, pad=8):
    """Pillow bicubic of each premultiplied channel on its own (as GDI+ scales premultiplied pixels), the source in
    a transparent border (clamp: transparent outside it; Pillow takes no box beyond the image)."""
    src = np.pad(src, ((pad, pad), (pad, pad), (0, 0)))
    box = tuple(v + pad for v in box)
    chans = [np.asarray(Image.fromarray(src[:, :, k].astype(np.float32), "F").resize((dw, dh), Image.BICUBIC, box=box))
             for k in range(4)]
    return np.clip(np.stack(chans, axis=-1), 0, 255)


def scale(src, dw, dh, box, compositing=1):
    """As Scaler: src (BGRA) through GdipDrawImageRectRect onto a cleared dw x dh target; -> the target."""
    sh, sw = src.shape[:2]
    src_buf = (ctypes.c_ubyte * src.size).from_buffer_copy(src.tobytes())
    dst = Canvas(dw, dh, smooth=False)
    img, attrs = V(), V()
    try:
        ok(gp.GdipCreateBitmapFromScan0(sw, sh, sw * 4, PARGB, ctypes.addressof(src_buf), ctypes.byref(img)))
        ok(gp.GdipCreateImageAttributes(ctypes.byref(attrs)))
        ok(gp.GdipSetImageAttributesWrapMode(attrs, 4, 0, 0))
        ok(gp.GdipSetCompositingMode(dst.g, compositing))
        ok(gp.GdipSetInterpolationMode(dst.g, 7))
        ok(gp.GdipSetPixelOffsetMode(dst.g, 2))
        ok(gp.GdipGraphicsClear(dst.g, 0))
        x, y, w, h = box
        ok(gp.GdipDrawImageRectRect(dst.g, img, 0.0, 0.0, float(dw), float(dh), x, y, w, h, 2, attrs, None, None))
        ok(gp.GdipFlush(dst.g, 1))
        return dst.pixels()
    finally:
        gp.GdipDisposeImageAttributes(attrs)
        gp.GdipDisposeImage(img)
        dst.close()


@pytest.mark.parametrize("sw, dw, box", [
    (96, 40, (0.0, 0.0, 96.0, 96.0)),                        # down, whole
    (96, 41, (1.37, -0.62, 96.0 * 41 / 40.0, 96.0 * 41 / 40.0)),   # down, a fractional source rectangle
    (24, 61, (0.4, 0.25, 24.0, 24.0)),                       # up
])
def test_draw_image_rect_rect_scales_like_bicubic(sw, dw, box):
    src = blob(sw, sw, margin=sw // 6)
    got = scale(src, dw, dw, box)
    x, y, w, h = box
    want = reference(src, dw, dw, (x, y, x + w, y + h))
    diff = np.abs(got - want)
    assert diff.mean() < 1.5, diff.mean()
    assert diff.max() < 24, diff.max()
    assert (got[:, :, :3] <= got[:, :, 3:] + 1).all()                       # still premultiplied


def centroid_x(px):
    a = px[:, :, 3].astype(float)
    return (np.arange(a.shape[1]) * a).sum() / a.sum()


@pytest.mark.parametrize("dw", [300, 160, 96, 40])
def test_draw_image_follows_a_fractional_source_offset(dw):
    """Up, exactly.  Down, Quartz puts the picture only at a few fractions of a target pixel of its own (measured:
    0, 1/8, 1/4, 1/2, 3/4, 7/8), up to 0.18 px off: the same for every frame of a size, so the pet does not jitter,
    but its anchor is not exactly on a whole pixel as with GDI+."""
    src = blob(192, 192, margin=30)
    k = dw / 192.0
    base = centroid_x(scale(src, dw, dw, (0.0, 0.0, 192.0, 192.0)))
    for s in (0.1, 0.25, 0.5, 0.75, 1.3):
        moved = base - centroid_x(scale(src, dw, dw, (s, 0.0, 192.0, 192.0)))
        assert abs(moved - s * k) <= (0.02 if k > 1 else 0.2), (s, moved, s * k)


def test_draw_image_moves_by_the_fractional_source_rectangle():
    """A whole-pixel shift of the source rectangle moves the picture by exactly that many target pixels."""
    src = blob(64, 64, margin=10)
    a = scale(src, 32, 32, (0.0, 0.0, 64.0, 64.0))
    b = scale(src, 32, 32, (-4.0, -6.0, 64.0, 64.0))                       # 2 and 3 target pixels right and down
    assert np.abs(b[3:, 2:] - a[:-3, :-2]).max() <= 2


def test_clamp_is_transparent_outside_the_source():
    src = np.full((20, 20, 4), 255, np.uint8)                              # opaque white to its edges
    got = scale(src, 40, 40, (-5.0, -5.0, 20.0, 20.0))                       # the source at 10..50 of a 40 x 40 target
    assert got[:8, :, 3].max() == 0 and got[:, :8, 3].max() == 0
    assert got[14:, 14:, 3].min() == 255


def test_source_copy_replaces_and_source_over_blends():
    src = np.zeros((8, 8, 4), np.uint8)
    src[...] = (0, 0, 64, 128)                                             # half-transparent red, premultiplied
    for mode, want in ((1, [0, 0, 64, 128]), (0, [0, 127, 64, 255])):
        dst = Canvas(8, 8, smooth=False)
        img = V()
        src_buf = (ctypes.c_ubyte * src.size).from_buffer_copy(src.tobytes())
        ok(gp.GdipCreateBitmapFromScan0(8, 8, 32, PARGB, ctypes.addressof(src_buf), ctypes.byref(img)))
        ok(gp.GdipGraphicsClear(dst.g, 0xFF00FF00))
        ok(gp.GdipSetCompositingMode(dst.g, mode))
        ok(gp.GdipSetPixelOffsetMode(dst.g, 2))
        ok(gp.GdipDrawImageRectRect(dst.g, img, 0.0, 0.0, 8.0, 8.0, 0.0, 0.0, 8.0, 8.0, 2, None, None, None))
        px = dst.pixels()
        ok(gp.GdipDisposeImage(img))
        dst.close()
        assert np.abs(px[4, 4] - np.array(want)).max() <= 1, (mode, px[4, 4])


# ---------------------------------------------------------------------------------------------------- paths
def test_arcs_turn_clockwise_on_the_screen(canvas):
    c = canvas(40, 40)
    path = new_path()
    ok(gp.GdipAddPathArc(path, 0.0, 0.0, 40.0, 40.0, 0.0, 90.0))          # from the right to the bottom
    ok(gp.GdipClosePathFigure(path))                                       # the chord closes it: a segment
    fill(c, path, 0xFFFFFFFF)
    ok(gp.GdipDeletePath(path))
    px = c.pixels()
    assert px[33, 33, 3] == 255 and px[6, 33, 3] == 0 and px[33, 6, 3] == 0 and px[6, 6, 3] == 0


def test_rounded_rectangle_filled_solid(canvas):
    c = canvas(60, 40)
    path = rrect(5.0, 5.0, 55.0, 35.0, 10.0)
    fill(c, path, 0xFF966840)
    ok(gp.GdipDeletePath(path))
    px = c.pixels()
    assert px[20, 30].tolist() == bgra(0xFF966840)                         # inside
    assert px[20, 7].tolist() == bgra(0xFF966840)                          # inside, along the left edge
    assert px[6, 6, 3] == 0 and px[33, 53, 3] == 0                         # the corners are round
    assert px[2, 30, 3] == 0 and px[38, 30, 3] == 0 and px[20, 58, 3] == 0   # outside
    assert 0 < px[5, 30, 3] < 255                                          # antialiased: pixel centres on whole coords


def test_rounded_rectangle_filled_with_a_mirrored_gradient(canvas):
    c = canvas(80, 20)
    path = rrect(0.0, 0.0, 80.0, 20.0, 4.0)
    ink = V()
    ok(gp.GdipCreateLineBrush(ctypes.byref(POINTF(20, 0)), ctypes.byref(POINTF(40, 0)), 0xFFFF0000, 0xFF0000FF, 3,
                              ctypes.byref(ink)))
    ok(gp.GdipFillPath(c.g, ink, path))
    ok(gp.GdipDeleteBrush(ink))
    ok(gp.GdipDeletePath(path))
    px = c.pixels()
    red, blue = px[10, :, 2], px[10, :, 0]                                 # pixel i: GDI+ x = i (default offset)
    # Quartz looks a gradient up in a table of its own: within a few levels, the turns exactly on p1 and p2
    assert red[20] >= 245 and blue[20] <= 10 and red[20] == red.max()      # c1 at p1
    assert blue[40] >= 245 and red[40] <= 10 and blue[40] == blue.max()    # c2 at p2
    assert abs(red[30] - 128) < 12 and abs(blue[30] - 128) < 12            # half way
    assert red[60] >= 245 and blue[1] >= 235 and blue[1] > blue[3]         # flipped beyond: c1 again at 60, c2 at 0
    assert abs(red[50] - 128) < 12 and red[45] < red[55]                   # going back to c1 after p2
    assert px[0, 0, 3] < 128                                               # its corner still round


def test_ellipse_and_polygon_paths(canvas):
    c = canvas(50, 50)
    path = new_path()
    ok(gp.GdipAddPathEllipse(path, 5.0, 5.0, 40.0, 40.0))
    fill(c, path, 0xFFFFFFFF)
    ok(gp.GdipDeletePath(path))
    px = c.pixels()
    assert px[25, 25, 3] == 255 and px[7, 7, 3] == 0 and px[25, 46, 3] == 0


@pytest.mark.parametrize("width", [2.0, 6.0])
def test_draw_path_stroke_width(canvas, width):
    c = canvas(60, 60, smooth=False)
    ok(gp.GdipSetPixelOffsetMode(c.g, 4))
    path = polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    pen = V()
    ok(gp.GdipCreatePen1(0xFFFFFFFF, width, 2, ctypes.byref(pen)))
    ok(gp.GdipDrawPath(c.g, pen, path))
    ok(gp.GdipDeletePen(pen))
    ok(gp.GdipDeletePath(path))
    column = c.pixels()[:, 30, 3]
    assert (column > 128).sum() == 2 * width                               # top and bottom edges, centred on the line
    assert column[30] == 0


# ---------------------------------------------------------------------------------------------------- text
@pytest.fixture
def text_kit():
    made = {}
    fam, font, fmt = V(), V(), V()
    ok(gp.GdipCreateFontFamilyFromName("Microsoft YaHei UI", None, ctypes.byref(fam)))
    ok(gp.GdipCreateFont(fam, 24.0, 1, 2, ctypes.byref(font)))
    ok(gp.GdipCreateStringFormat(0x1000, 0, ctypes.byref(fmt)))
    made.update(fam=fam, font=font, fmt=fmt)
    yield made
    ok(gp.GdipDeleteStringFormat(fmt))
    ok(gp.GdipDeleteFont(font))
    ok(gp.GdipDeleteFontFamily(fam))


def measure(c, text, font, fmt):
    box = RECTF()
    ok(gp.GdipMeasureString(c.g, text, len(text), font, ctypes.byref(RECTF(0, 0, 4000, 1000)), fmt, ctypes.byref(box),
                            None, None))
    return box


def test_draw_string_centred_in_its_rectangle(canvas, text_kit):
    c = canvas(200, 60)
    ok(gp.GdipSetStringFormatAlign(text_kit["fmt"], 1))
    ok(gp.GdipSetStringFormatLineAlign(text_kit["fmt"], 1))
    ink = V()
    ok(gp.GdipCreateSolidFill(0xFFF6F4EC, ctypes.byref(ink)))
    ok(gp.GdipDrawString(c.g, "Hello", 5, text_kit["font"], ctypes.byref(RECTF(20, 10, 160, 40)), text_kit["fmt"],
                         ink))
    ok(gp.GdipDeleteBrush(ink))
    x0, y0, x1, y1 = ink_box(c.pixels())
    assert 20 <= x0 and x1 < 180 and 10 <= y0 and y1 < 50
    assert abs((x0 + x1) / 2.0 - 100) <= 3                                 # centred across
    assert abs((y0 + y1) / 2.0 - 30) <= 5                                  # and about the middle (caps sit high)


def test_draw_string_near_starts_after_the_padding(canvas, text_kit):
    c = canvas(200, 60)
    ok(gp.GdipSetStringFormatLineAlign(text_kit["fmt"], 1))
    ink = V()
    ok(gp.GdipCreateLineBrush(ctypes.byref(POINTF(0, 0)), ctypes.byref(POINTF(40, 0)), 0xFFFFE07A, 0xFF8CBEF0, 3,
                              ctypes.byref(ink)))
    ok(gp.GdipDrawString(c.g, "Hello", 5, text_kit["font"], ctypes.byref(RECTF(20, 0, 170, 60)), text_kit["fmt"],
                         ink))
    ok(gp.GdipDeleteBrush(ink))
    x0, _, _, _ = ink_box(c.pixels())
    assert 20 + 24 / 6.0 - 1 <= x0 <= 20 + 24 / 6.0 + 4                   # 1/6 em in, as GDI+


def test_draw_string_renders_cjk(canvas, text_kit):
    c = canvas(200, 60)
    ok(gp.GdipSetStringFormatLineAlign(text_kit["fmt"], 1))
    box = measure(c, u"想一想？", text_kit["font"], text_kit["fmt"])
    ink = V()
    ok(gp.GdipCreateSolidFill(0xFFFFFFFF, ctypes.byref(ink)))
    ok(gp.GdipDrawString(c.g, u"想一想？", 4, text_kit["font"], ctypes.byref(RECTF(0, 0, box.Width + 4, 60)),
                         text_kit["fmt"], ink))
    ok(gp.GdipDeleteBrush(ink))
    px = c.pixels()
    assert (px[:, :, 3] > 128).sum() > 300
    x0, _, x1, _ = ink_box(px)
    assert x1 - x0 > 3 * 24 * 0.8                                          # four wide glyphs, not boxes or one


def test_add_path_string_outlines_in_the_rectangle(canvas, text_kit):
    c = canvas(100, 100)
    path = new_path()
    fmt = V()
    ok(gp.GdipCreateStringFormat(0x1000, 0, ctypes.byref(fmt)))
    ok(gp.GdipSetStringFormatAlign(fmt, 1))
    ok(gp.GdipSetStringFormatLineAlign(fmt, 1))
    ok(gp.GdipAddPathString(path, u"想", 1, text_kit["fam"], 0, 40.0, ctypes.byref(RECTF(30, 30, 60, 60)), fmt))
    ok(gp.GdipDeleteStringFormat(fmt))
    fill(c, path, 0xFF8CBEF0)
    pen = V()
    ok(gp.GdipCreatePen1(0xFF8CBEF0, 2.0, 2, ctypes.byref(pen)))
    ok(gp.GdipDrawPath(c.g, pen, path))
    ok(gp.GdipDeletePen(pen))
    ok(gp.GdipDeletePath(path))
    x0, y0, x1, y1 = ink_box(c.pixels())
    assert 28 <= x0 and x1 <= 91 and 28 <= y0 and y1 <= 91
    assert abs((x0 + x1) / 2.0 - 60) <= 3 and abs((y0 + y1) / 2.0 - 60) <= 6
    assert x1 - x0 > 25


def test_measure_string_grows_with_the_text_and_the_size(canvas, text_kit):
    c = canvas(1, 1)
    short = measure(c, "Read", text_kit["font"], text_kit["fmt"])
    longer = measure(c, "Reading files", text_kit["font"], text_kit["fmt"])
    big = V()
    ok(gp.GdipCreateFont(text_kit["fam"], 36.0, 1, 2, ctypes.byref(big)))
    bigger = measure(c, "Read", big, text_kit["fmt"])
    pt = V()
    ok(gp.GdipCreateFont(text_kit["fam"], 18.0, 1, 3, ctypes.byref(pt)))   # 18 pt = 24 px at 96 dpi
    in_points = measure(c, "Read", pt, text_kit["fmt"])
    ok(gp.GdipDeleteFont(big))
    ok(gp.GdipDeleteFont(pt))
    assert 0 < short.Width < longer.Width
    assert bigger.Width > short.Width * 1.3 and bigger.Height > short.Height * 1.3
    assert abs(in_points.Width - short.Width) < 0.01
    assert 24 <= short.Height <= 40
    assert measure(c, "", text_kit["font"], text_kit["fmt"]).Width == 0


@pytest.mark.parametrize("name", ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC",
                                  "Helvetica Neue"])
def test_known_families_are_found(name):
    fam = V()
    ok(gp.GdipCreateFontFamilyFromName(name, None, ctypes.byref(fam)))
    assert fam.value
    ok(gp.GdipDeleteFontFamily(fam))


@pytest.mark.parametrize("name", ["Segoe Fluent Icons", "Segoe MDL2 Assets", "No Such Font 123"])
def test_icon_and_unknown_families_are_not_found(name):
    fam = V()
    assert gp.GdipCreateFontFamilyFromName(name, None, ctypes.byref(fam)) == gp.FontFamilyNotFound
    assert not fam.value


# ---------------------------------------------------------------------------------------------------- handles
def test_every_handle_is_deleted(canvas, text_kit):
    start = len(gp._handles)
    c = Canvas(64, 32)
    ok(gp.GdipSetCompositingMode(c.g, 0))
    path = rrect(1.0, 1.0, 63.0, 31.0, 6.0)
    fill(c, path, 0xFF966840)
    pen = V()
    ok(gp.GdipCreatePen1(0xFF6E4A2C, 2.0, 2, ctypes.byref(pen)))
    ok(gp.GdipDrawPath(c.g, pen, path))
    ok(gp.GdipDeletePen(pen))
    ok(gp.GdipDeletePath(path))
    attrs = V()
    ok(gp.GdipCreateImageAttributes(ctypes.byref(attrs)))
    ok(gp.GdipDisposeImageAttributes(attrs))
    c.close()
    assert len(gp._handles) == start
    assert gp.GdipDeletePath(path) == gp.InvalidParameter                  # gone: not a handle any more
