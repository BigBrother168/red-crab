# -*- coding: utf-8 -*-
"""GDI+ on macOS: the flat-API subset the pets draw with (clawd_pet.pyw _gdiplus(), clawd_scale.py), over Quartz.

The callers bind these as they bind gdiplus.dll (restype and argtypes are set on the functions and ignored), so the
arguments come as Python values: ints, floats, None, str, ctypes instances, ctypes.byref(x) and arrays.  Each
returns a GDI+ Status (0 Ok); an object is a handle, a non-zero int from the table below, written into the caller's
c_void_p.  CoreGraphics, CoreText and CoreFoundation are called through plain ctypes: no PyObjC (its Quartz package
loads AppKit) and no window server, so this also runs under python -I -S (clawd_scale.py) and on CI.

A bitmap is the caller's memory as it is: premultiplied BGRA, top-down rows (PixelFormat32bppPARGB), and every
drawing call has landed in it when it returns.  A Graphics works in GDI+ coordinates: origin top-left, y down, one
unit a pixel; with the default pixel offset a pixel's centre is on whole coordinates, as in GDI+.
What is not here: wrapping text (every line of the text is one line, NoWrap or not), other wrap modes than Clamp for
images, pixel formats other than 32bppPARGB, private font collections.
"""
import contextlib
import ctypes
import functools
import math
import sys
import traceback

from ctypes import c_bool, c_double, c_int32, c_long, c_size_t, c_uint16, c_uint32, c_void_p

Ok, GenericError, InvalidParameter, OutOfMemory = 0, 1, 2, 3
NotImplemented_ = 6
FontFamilyNotFound = 14
UnsupportedGdiplusVersion = 17

PixelFormat32bppPARGB = 0x000E200B
CompositingModeSourceCopy = 1
WrapModeTileFlipX, WrapModeTileFlipXY, WrapModeClamp = 1, 3, 4
UnitWorld, UnitDisplay, UnitPixel, UnitPoint, UnitInch, UnitDocument, UnitMillimeter = 0, 1, 2, 3, 4, 5, 6
FontStyleBold, FontStyleItalic = 1, 2
StringFormatFlagsMeasureTrailingSpaces, StringFormatFlagsNoClip = 0x0800, 0x4000
DPI = 96.0                                      # a bitmap's Graphics in GDI+: what a point or an inch is in pixels
# px per unit for a font's or a pen's size
UNIT_PX = {UnitWorld: 1.0, UnitDisplay: 1.0, UnitPixel: 1.0, UnitPoint: DPI / 72.0, UnitInch: DPI,
           UnitDocument: DPI / 300.0, UnitMillimeter: DPI / 25.4}
HALF_PIXEL_OFFSET = (2, 4)                      # PixelOffsetModeHighQuality, Half: a pixel's centre at x + 0.5
SMOOTH = (2, 4, 5)                              # SmoothingModeHighQuality, AntiAlias, AntiAlias8x8
TEXT_ALIASED = (1, 2)                           # TextRenderingHintSingleBitPerPixel(GridFit)
# GDI+ InterpolationMode -> CGInterpolationQuality (none 1, low 2, high 3, medium 4)
INTERPOLATION = {0: 4, 1: 2, 2: 3, 3: 2, 4: 4, 5: 1, 6: 4, 7: 3}

# CoreGraphics
BGRA_PREMULTIPLIED = 2 | 2 << 12                # kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Little
BLEND_NORMAL, BLEND_COPY = 0, 17
EXTEND_BOTH = 3                                 # kCGGradientDrawsBeforeStartLocation | AfterEndLocation
UI_FONT_SYSTEM = 2                              # kCTFontUIFontSystem
TRAIT_ITALIC, TRAIT_BOLD = 1, 2
MAX_GRADIENT_PERIODS = 4096


# --------------------------------------------------------------------------- Quartz through ctypes
class CGPoint(ctypes.Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", c_double), ("height", c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


class CGAffineTransform(ctypes.Structure):
    _fields_ = [("a", c_double), ("b", c_double), ("c", c_double), ("d", c_double), ("tx", c_double),
                ("ty", c_double)]


class CFRange(ctypes.Structure):
    _fields_ = [("location", c_long), ("length", c_long)]


_FRAMEWORK = "/System/Library/Frameworks/%s.framework/%s"
_CF, _CG, _CT = [ctypes.CDLL(_FRAMEWORK % (n, n)) for n in ("CoreFoundation", "CoreGraphics", "CoreText")]
P, D, Z = c_void_p, c_double, c_size_t
# (library, name, restype, argtypes)
_SIGNATURES = (
    (_CF, "CFRelease", None, [P]),
    (_CF, "CFStringCreateWithCharacters", P, [P, P, c_long]),
    (_CF, "CFStringGetLength", c_long, [P]),
    (_CF, "CFStringGetCharacters", None, [P, CFRange, P]),
    (_CF, "CFDictionaryCreate", P, [P, P, P, c_long, P, P]),
    (_CF, "CFDictionaryGetValue", P, [P, P]),
    (_CF, "CFSetCreate", P, [P, P, c_long, P]),
    (_CF, "CFArrayGetCount", c_long, [P]),
    (_CF, "CFArrayGetValueAtIndex", P, [P, c_long]),
    (_CF, "CFAttributedStringCreate", P, [P, P, P]),
    (_CG, "CGColorSpaceCreateDeviceRGB", P, []),
    (_CG, "CGBitmapContextCreate", P, [P, Z, Z, Z, Z, P, c_uint32]),
    (_CG, "CGContextRelease", None, [P]),
    (_CG, "CGContextFlush", None, [P]),
    (_CG, "CGContextSaveGState", None, [P]),
    (_CG, "CGContextRestoreGState", None, [P]),
    (_CG, "CGContextTranslateCTM", None, [P, D, D]),
    (_CG, "CGContextScaleCTM", None, [P, D, D]),
    (_CG, "CGContextSetBlendMode", None, [P, c_int32]),
    (_CG, "CGContextSetShouldAntialias", None, [P, c_bool]),
    (_CG, "CGContextSetInterpolationQuality", None, [P, c_int32]),
    (_CG, "CGContextSetRGBFillColor", None, [P, D, D, D, D]),
    (_CG, "CGContextSetRGBStrokeColor", None, [P, D, D, D, D]),
    (_CG, "CGContextSetLineWidth", None, [P, D]),
    (_CG, "CGContextSetLineJoin", None, [P, c_int32]),
    (_CG, "CGContextSetLineCap", None, [P, c_int32]),
    (_CG, "CGContextSetMiterLimit", None, [P, D]),
    (_CG, "CGContextFillRect", None, [P, CGRect]),
    (_CG, "CGContextClearRect", None, [P, CGRect]),
    (_CG, "CGContextClipToRect", None, [P, CGRect]),
    (_CG, "CGContextAddPath", None, [P, P]),
    (_CG, "CGContextFillPath", None, [P]),
    (_CG, "CGContextEOFillPath", None, [P]),
    (_CG, "CGContextStrokePath", None, [P]),
    (_CG, "CGContextClip", None, [P]),
    (_CG, "CGContextEOClip", None, [P]),
    (_CG, "CGContextGetClipBoundingBox", CGRect, [P]),
    (_CG, "CGContextDrawImage", None, [P, CGRect, P]),
    (_CG, "CGContextDrawLinearGradient", None, [P, P, CGPoint, CGPoint, c_uint32]),
    (_CG, "CGDataProviderCreateWithData", P, [P, P, Z, P]),
    (_CG, "CGDataProviderRelease", None, [P]),
    (_CG, "CGImageCreate", P, [Z, Z, Z, Z, Z, P, c_uint32, P, P, c_bool, c_int32]),
    (_CG, "CGImageRelease", None, [P]),
    (_CG, "CGGradientCreateWithColorComponents", P, [P, P, P, Z]),
    (_CG, "CGGradientRelease", None, [P]),
    (_CG, "CGPathCreateMutable", P, []),
    (_CG, "CGPathRelease", None, [P]),
    (_CG, "CGPathMoveToPoint", None, [P, P, D, D]),
    (_CG, "CGPathAddLineToPoint", None, [P, P, D, D]),
    (_CG, "CGPathAddCurveToPoint", None, [P, P, D, D, D, D, D, D]),
    (_CG, "CGPathAddEllipseInRect", None, [P, P, CGRect]),
    (_CG, "CGPathAddPath", None, [P, P, P]),
    (_CG, "CGPathCloseSubpath", None, [P]),
    (_CG, "CGPathIsEmpty", c_bool, [P]),
    (_CT, "CTFontDescriptorCreateWithAttributes", P, [P]),
    (_CT, "CTFontDescriptorCreateMatchingFontDescriptor", P, [P, P]),
    (_CT, "CTFontDescriptorCopyAttribute", P, [P, P]),
    (_CT, "CTFontCreateWithFontDescriptor", P, [P, D, P]),
    (_CT, "CTFontCreateUIFontForLanguage", P, [c_uint32, D, P]),
    (_CT, "CTFontCreateCopyWithSymbolicTraits", P, [P, D, P, c_uint32, c_uint32]),
    (_CT, "CTFontGetSize", D, [P]),
    (_CT, "CTFontGetAscent", D, [P]),
    (_CT, "CTFontGetDescent", D, [P]),
    (_CT, "CTFontGetLeading", D, [P]),
    (_CT, "CTFontCreatePathForGlyph", P, [P, c_uint16, P]),
    (_CT, "CTLineCreateWithAttributedString", P, [P]),
    (_CT, "CTLineGetTypographicBounds", D, [P, P, P, P]),
    (_CT, "CTLineGetTrailingWhitespaceWidth", D, [P]),
    (_CT, "CTLineGetGlyphRuns", P, [P]),
    (_CT, "CTRunGetGlyphCount", c_long, [P]),
    (_CT, "CTRunGetGlyphs", None, [P, CFRange, P]),
    (_CT, "CTRunGetPositions", None, [P, CFRange, P]),
    (_CT, "CTRunGetAttributes", P, [P]),
)


class _Quartz(object):
    """The C functions above as attributes, and the framework constants this module uses."""

    def __init__(self):
        for lib, name, restype, argtypes in _SIGNATURES:
            fn = getattr(lib, name)
            fn.restype, fn.argtypes = restype, argtypes
            setattr(self, name, fn)
        self.font_attr = P.in_dll(_CT, "kCTFontAttributeName").value
        self.family_attr = P.in_dll(_CT, "kCTFontFamilyNameAttribute").value
        self.dict_keys = ctypes.addressof(ctypes.c_char.in_dll(_CF, "kCFTypeDictionaryKeyCallBacks"))
        self.dict_values = ctypes.addressof(ctypes.c_char.in_dll(_CF, "kCFTypeDictionaryValueCallBacks"))
        self.set_values = ctypes.addressof(ctypes.c_char.in_dll(_CF, "kCFTypeSetCallBacks"))
        self.rgb = self.CGColorSpaceCreateDeviceRGB()     # every bitmap, colour and gradient: no colour matching


q = _Quartz()


def _release(ref):
    if ref:
        q.CFRelease(ref)


def _cfstr(text):
    data = text.encode("utf-16-le")
    buf = (c_uint16 * max(1, len(data) // 2))()
    ctypes.memmove(buf, data, len(data))
    return q.CFStringCreateWithCharacters(None, buf, len(data) // 2)


def _pystr(cfstr):
    n = q.CFStringGetLength(cfstr)
    buf = (c_uint16 * max(1, n))()
    q.CFStringGetCharacters(cfstr, CFRange(0, n), buf)
    return bytes(buf)[:2 * n].decode("utf-16-le")


def _cfdict(pairs):
    keys = (P * len(pairs))(*[k for k, _ in pairs])
    values = (P * len(pairs))(*[v for _, v in pairs])
    return q.CFDictionaryCreate(None, keys, values, len(pairs), q.dict_keys, q.dict_values)


def _rect(x, y, w, h):
    return CGRect(CGPoint(x, y), CGSize(w, h))


def _rgba(argb):
    """An ARGB int -> (r, g, b, a) in 0..1, not premultiplied (Quartz premultiplies as it draws)."""
    argb &= 0xFFFFFFFF
    return ((argb >> 16) & 255) / 255.0, ((argb >> 8) & 255) / 255.0, (argb & 255) / 255.0, (argb >> 24) / 255.0


# --------------------------------------------------------------------------- startup, handles, arguments
class _Fail(Exception):
    """Ends an API call with this GDI+ status."""

    def __init__(self, status):
        Exception.__init__(self, status)
        self.status = status


_handles = {}                                    # handle -> its object; a handle is never used twice
_last_handle = [0x10000]


def _api(fn):
    """A GDI+ function: its status (Ok when it returns None); an error of this module's own is reported on stderr
    and is GenericError, as GDI+ never raises."""
    @functools.wraps(fn)
    def call(*args):
        try:
            st = fn(*args)
            return Ok if st is None else st
        except _Fail as e:
            return e.status
        except Exception:
            if sys.stderr is not None:
                sys.stderr.write("clawd_mac.gdiplus %s:\n%s" % (fn.__name__, traceback.format_exc()))
            return GenericError
    return call


def _new(obj, out):
    """obj in the table; its handle into the out parameter."""
    _last_handle[0] += 1
    h = _last_handle[0]
    _handles[h] = obj
    try:
        _set_value(out, h)
    except Exception:
        del _handles[h]
        _close(obj)
        raise _Fail(InvalidParameter)


def _close(obj):
    close = getattr(obj, "close", None)
    if close is not None:
        close()


def _handle(arg):
    if arg is None or isinstance(arg, int):
        return arg or 0
    return getattr(arg, "value", None) or 0             # c_void_p, c_size_t


def _get(arg, cls):
    obj = _handles.get(_handle(arg))
    if not isinstance(obj, cls):
        raise _Fail(InvalidParameter)
    return obj


def _delete(arg, cls):
    obj = _get(arg, cls)
    del _handles[_handle(arg)]
    _close(obj)


def _target(arg):
    """What a byref(x), a pointer(x) or x itself is about."""
    if hasattr(arg, "_obj"):
        return arg._obj
    if hasattr(arg, "contents"):
        return arg.contents
    return arg


def _set_value(out, value):
    if out is None:
        raise _Fail(InvalidParameter)
    _target(out).value = value


def _address(mem):
    """The address of caller memory: an int, a c_void_p, a ctypes array or byref(array); 0 for None."""
    if mem is None or isinstance(mem, int):
        return mem or 0
    mem = _target(mem)
    if isinstance(mem, (c_void_p, c_size_t)):
        return mem.value or 0
    return ctypes.addressof(mem)


def _points(arg, count):
    pts = _target(arg)
    return [(float(pts[i].X), float(pts[i].Y)) for i in range(count)]


def _rectf(arg):
    r = _target(arg)
    return float(r.X), float(r.Y), float(r.Width), float(r.Height)


def _text(text, length):
    text = text or ""
    return text if length is None or length < 0 else text[:length]


class _Token(object):
    pass


@_api
def GdiplusStartup(token, startup_input, output):
    version = _target(startup_input).GdiplusVersion if startup_input is not None else 0
    if version not in (1, 2, 3):
        raise _Fail(UnsupportedGdiplusVersion)
    _new(_Token(), token)


def GdiplusShutdown(token):
    if isinstance(_handles.get(_handle(token)), _Token):
        del _handles[_handle(token)]


# --------------------------------------------------------------------------- bitmaps and graphics
class _Bitmap(object):
    """w x h premultiplied BGRA at addr, stride bytes a row, top-down; own memory when the caller gave none."""

    def __init__(self, w, h, stride, addr):
        self.own = None
        if not addr:
            stride = w * 4
            self.own = (ctypes.c_ubyte * (stride * h))()
            addr = ctypes.addressof(self.own)
        self.w, self.h, self.stride, self.addr = w, h, stride, addr

    def cgimage(self):
        """A CGImage over the memory as it is now, not a copy (the caller releases it before the memory changes)."""
        provider = q.CGDataProviderCreateWithData(None, self.addr, self.stride * self.h, None)
        if not provider:
            raise _Fail(OutOfMemory)
        try:
            image = q.CGImageCreate(self.w, self.h, 8, 32, self.stride, q.rgb, BGRA_PREMULTIPLIED, provider, None,
                                    True, 0)
        finally:
            q.CGDataProviderRelease(provider)
        if not image:
            raise _Fail(OutOfMemory)
        return image

    def close(self):
        self.own = None


class _Graphics(object):
    """A bitmap context on a bitmap's memory, its CTM turned to y down, and the GDI+ state that is set on it."""

    def __init__(self, bitmap):
        self.bitmap = bitmap
        self.ctx = q.CGBitmapContextCreate(bitmap.addr, bitmap.w, bitmap.h, 8, bitmap.stride, q.rgb,
                                           BGRA_PREMULTIPLIED)
        if not self.ctx:
            raise _Fail(OutOfMemory)
        q.CGContextTranslateCTM(self.ctx, 0.0, float(bitmap.h))
        q.CGContextScaleCTM(self.ctx, 1.0, -1.0)
        self.compositing = 0
        self.interpolation = 0
        self.pixel_offset = 0
        self.smoothing = 0
        self.text_hint = 0

    def close(self):
        if self.ctx:
            q.CGContextRelease(self.ctx)
            self.ctx = None


@contextlib.contextmanager
def _drawing(g, antialias):
    """One drawing call: the Graphics' compositing and pixel offset in force; flushed into the bitmap after."""
    ctx = g.ctx
    q.CGContextSaveGState(ctx)
    try:
        if g.pixel_offset not in HALF_PIXEL_OFFSET:      # a pixel's centre on whole coordinates
            q.CGContextTranslateCTM(ctx, 0.5, 0.5)
        q.CGContextSetBlendMode(ctx, BLEND_COPY if g.compositing == CompositingModeSourceCopy else BLEND_NORMAL)
        q.CGContextSetShouldAntialias(ctx, bool(antialias))
        yield ctx
    finally:
        q.CGContextRestoreGState(ctx)
        q.CGContextFlush(ctx)


@_api
def GdipCreateBitmapFromScan0(width, height, stride, pixel_format, scan0, out):
    if width <= 0 or height <= 0:
        raise _Fail(InvalidParameter)
    if pixel_format != PixelFormat32bppPARGB:
        raise _Fail(NotImplemented_)
    addr = _address(scan0)
    if addr and stride < width * 4:
        raise _Fail(InvalidParameter)
    _new(_Bitmap(int(width), int(height), int(stride), addr), out)


@_api
def GdipDisposeImage(image):
    _delete(image, _Bitmap)


@_api
def GdipGetImageGraphicsContext(image, out):
    _new(_Graphics(_get(image, _Bitmap)), out)


@_api
def GdipDeleteGraphics(graphics):
    _delete(graphics, _Graphics)


def _set_mode(graphics, attr, value, allowed):
    if value not in allowed:
        raise _Fail(InvalidParameter)
    setattr(_get(graphics, _Graphics), attr, value)


@_api
def GdipSetCompositingMode(graphics, mode):
    _set_mode(graphics, "compositing", mode, (0, 1))


@_api
def GdipSetInterpolationMode(graphics, mode):
    _set_mode(graphics, "interpolation", mode, tuple(INTERPOLATION))


@_api
def GdipSetPixelOffsetMode(graphics, mode):
    _set_mode(graphics, "pixel_offset", mode, (0, 1, 2, 3, 4))


@_api
def GdipSetSmoothingMode(graphics, mode):
    _set_mode(graphics, "smoothing", mode, (0, 1, 2, 3, 4, 5))


@_api
def GdipSetTextRenderingHint(graphics, hint):
    _set_mode(graphics, "text_hint", hint, (0, 1, 2, 3, 4, 5))


@_api
def GdipGraphicsClear(graphics, argb):
    """Every pixel this colour, whatever the compositing mode."""
    g = _get(graphics, _Graphics)
    ctx, whole = g.ctx, _rect(0.0, 0.0, g.bitmap.w, g.bitmap.h)
    q.CGContextSaveGState(ctx)
    try:
        q.CGContextSetBlendMode(ctx, BLEND_COPY)
        if (argb & 0xFFFFFFFF) >> 24 == 0:
            q.CGContextClearRect(ctx, whole)
        else:
            q.CGContextSetRGBFillColor(ctx, *_rgba(argb))
            q.CGContextFillRect(ctx, whole)
    finally:
        q.CGContextRestoreGState(ctx)
        q.CGContextFlush(ctx)


@_api
def GdipFlush(graphics, intention):
    q.CGContextFlush(_get(graphics, _Graphics).ctx)


# --------------------------------------------------------------------------- image drawing
class _ImageAttributes(object):
    wrap = WrapModeClamp


@_api
def GdipCreateImageAttributes(out):
    _new(_ImageAttributes(), out)


@_api
def GdipDisposeImageAttributes(attrs):
    _delete(attrs, _ImageAttributes)


@_api
def GdipSetImageAttributesWrapMode(attrs, wrap, argb, clamp):
    a = _get(attrs, _ImageAttributes)
    if wrap != WrapModeClamp:
        raise _Fail(NotImplemented_)
    a.wrap = wrap


@_api
def GdipDrawImageRectRect(graphics, image, dstx, dsty, dstw, dsth, srcx, srcy, srcw, srch, src_unit, attrs,
                          callback, callback_data):
    """The source rectangle (fractional, in pixels) scaled onto the target one: the whole bitmap drawn by the one
    affine map, clipped to the target.  Outside the source only transparency (clamp).  Quartz scales up exactly but
    puts a picture it shrinks only at some fractions of a pixel (0, 1/8, 1/4, 1/2, 3/4, 7/8): up to ~0.18 px off,
    the same for every frame of a size."""
    g, bmp = _get(graphics, _Graphics), _get(image, _Bitmap)
    if attrs:
        _get(attrs, _ImageAttributes)
    if src_unit != UnitPixel:
        raise _Fail(NotImplemented_)
    if not srcw or not srch:
        raise _Fail(InvalidParameter)
    if not dstw or not dsth:
        return
    kx, ky = float(dstw) / srcw, float(dsth) / srch
    cgimage = bmp.cgimage()
    try:
        with _drawing(g, True) as ctx:
            q.CGContextSetInterpolationQuality(ctx, INTERPOLATION.get(g.interpolation, 4))
            target = _rect(dstx, dsty, dstw, dsth)
            q.CGContextClipToRect(ctx, target)
            if g.compositing == CompositingModeSourceCopy:
                q.CGContextClearRect(ctx, target)        # SourceCopy: what the source does not cover is cleared
            q.CGContextTranslateCTM(ctx, dstx - srcx * kx, dsty - srcy * ky + bmp.h * ky)
            q.CGContextScaleCTM(ctx, kx, -ky)
            q.CGContextDrawImage(ctx, _rect(0.0, 0.0, bmp.w, bmp.h), cgimage)
    finally:
        q.CGImageRelease(cgimage)


# --------------------------------------------------------------------------- paths
class _Path(object):
    """A CGMutablePath in GDI+ coordinates, its fill mode (0 alternate: even-odd, 1 winding) and whether its last
    figure is still open (an arc then goes on from it with a line, as in GDI+)."""

    def __init__(self, fill_mode):
        self.cg = q.CGPathCreateMutable()
        if not self.cg:
            raise _Fail(OutOfMemory)
        self.fill_mode = fill_mode
        self.open = False

    def to(self, x, y):
        """The next point of the open figure, or the first of a new one."""
        if self.open:
            q.CGPathAddLineToPoint(self.cg, None, x, y)
        else:
            q.CGPathMoveToPoint(self.cg, None, x, y)
            self.open = True

    def close(self):
        if self.cg:
            q.CGPathRelease(self.cg)
            self.cg = None


def _ellipse_angle(deg, rx, ry):
    """GDI+ angles on an ellipse are where the ray at that angle meets it; -> the ellipse's parameter (radians)."""
    a = math.radians(deg)
    t = math.atan2(rx * math.sin(a), ry * math.cos(a))
    return t + 2.0 * math.pi * round((a - t) / (2.0 * math.pi))     # the turn a is on (t is in its quadrant)


def _arc_curves(path, cx, cy, rx, ry, t0, sweep):
    """The arc from parameter t0 by sweep (radians; positive: clockwise on the screen, y down) as cubic Béziers of
    at most 90 degrees each."""
    n = max(1, int(math.ceil(abs(sweep) / (math.pi / 2.0) - 1e-9)))
    step = sweep / n
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    path.to(cx + rx * math.cos(t0), cy + ry * math.sin(t0))
    for i in range(n):
        a, b = t0 + i * step, t0 + (i + 1) * step
        q.CGPathAddCurveToPoint(path.cg, None,
                                cx + rx * (math.cos(a) - k * math.sin(a)), cy + ry * (math.sin(a) + k * math.cos(a)),
                                cx + rx * (math.cos(b) + k * math.sin(b)), cy + ry * (math.sin(b) - k * math.cos(b)),
                                cx + rx * math.cos(b), cy + ry * math.sin(b))


@_api
def GdipCreatePath(fill_mode, out):
    if fill_mode not in (0, 1):
        raise _Fail(InvalidParameter)
    _new(_Path(fill_mode), out)


@_api
def GdipDeletePath(path):
    _delete(path, _Path)


@_api
def GdipAddPathArc(path, x, y, width, height, start_angle, sweep_angle):
    """The arc of the ellipse in the box, from start_angle by sweep_angle degrees (clockwise on the screen); joined
    to the open figure by a line."""
    p = _get(path, _Path)
    if width <= 0 or height <= 0:
        raise _Fail(InvalidParameter)
    rx, ry = width / 2.0, height / 2.0
    t0 = _ellipse_angle(start_angle, rx, ry)
    if abs(sweep_angle) >= 360.0:
        sweep = math.copysign(2.0 * math.pi, sweep_angle)
    else:
        sweep = _ellipse_angle(start_angle + sweep_angle, rx, ry) - t0
    _arc_curves(p, x + rx, y + ry, rx, ry, t0, sweep)


@_api
def GdipAddPathEllipse(path, x, y, width, height):
    p = _get(path, _Path)
    q.CGPathAddEllipseInRect(p.cg, None, _rect(x, y, width, height))
    p.open = False


@_api
def GdipAddPathPolygon(path, points, count):
    p = _get(path, _Path)
    if count < 2:
        raise _Fail(InvalidParameter)
    p.open = False
    for x, y in _points(points, count):
        p.to(x, y)
    q.CGPathCloseSubpath(p.cg)
    p.open = False


@_api
def GdipClosePathFigure(path):
    p = _get(path, _Path)
    if p.open:
        q.CGPathCloseSubpath(p.cg)
    p.open = False


# --------------------------------------------------------------------------- brushes and pens
class _Brush(object):
    pass


class _SolidBrush(_Brush):
    def __init__(self, argb):
        self.argb = argb


class _LineBrush(_Brush):
    """A linear gradient from c1 at p1 to c2 at p2, repeated beyond them (flipped every other time for the flip
    wrap modes; clamp: the end colours go on)."""

    def __init__(self, p1, p2, c1, c2, wrap):
        self.p1, self.p2, self.c1, self.c2, self.wrap = p1, p2, c1, c2, wrap

    def _t(self, x, y):
        dx, dy = self.p2[0] - self.p1[0], self.p2[1] - self.p1[1]
        return ((x - self.p1[0]) * dx + (y - self.p1[1]) * dy) / (dx * dx + dy * dy)

    def _at(self, t):
        return (self.p1[0] + (self.p2[0] - self.p1[0]) * t, self.p1[1] + (self.p2[1] - self.p1[1]) * t)

    def stops(self, box):
        """-> (t0, t1, [(t, argb)]) covering box (x, y, w, h)."""
        if self.wrap == WrapModeClamp:
            return 0.0, 1.0, [(0.0, self.c1), (1.0, self.c2)]
        x, y, w, h = box
        ts = [self._t(px, py) for px in (x, x + w) for py in (y, y + h)]
        k0 = int(math.floor(min(ts)))
        k1 = max(k0 + 1, int(math.ceil(max(ts))))
        k1 = min(k1, k0 + MAX_GRADIENT_PERIODS)
        flip = self.wrap in (WrapModeTileFlipX, WrapModeTileFlipXY)
        stops = []
        for k in range(k0, k1):
            first, last = (self.c2, self.c1) if flip and k % 2 else (self.c1, self.c2)
            stops += [(float(k), first), (k + 1.0, last)]
        return float(k0), float(k1), stops

    def draw(self, ctx, box):
        """Fills box (clipped already) with the gradient."""
        t0, t1, stops = self.stops(box)
        comps = (c_double * (4 * len(stops)))(*[c for _, argb in stops for c in _rgba(argb)])
        locs = (c_double * len(stops))(*[(t - t0) / (t1 - t0) for t, _ in stops])
        gradient = q.CGGradientCreateWithColorComponents(q.rgb, comps, locs, len(stops))
        if not gradient:
            raise _Fail(OutOfMemory)
        try:
            q.CGContextDrawLinearGradient(ctx, gradient, CGPoint(*self._at(t0)), CGPoint(*self._at(t1)), EXTEND_BOTH)
        finally:
            q.CGGradientRelease(gradient)


class _Pen(object):
    def __init__(self, argb, width):
        self.argb, self.width = argb, width


@_api
def GdipCreateSolidFill(argb, out):
    _new(_SolidBrush(argb), out)


@_api
def GdipCreateLineBrush(point1, point2, color1, color2, wrap, out):
    (p1,), (p2,) = _points([_target(point1)], 1), _points([_target(point2)], 1)
    if p1 == p2 or wrap not in (0, 1, 2, 3, 4):
        raise _Fail(InvalidParameter)
    _new(_LineBrush(p1, p2, color1, color2, wrap), out)


@_api
def GdipDeleteBrush(brush):
    _delete(brush, _Brush)


@_api
def GdipCreatePen1(argb, width, unit, out):
    if unit not in UNIT_PX or width < 0:
        raise _Fail(InvalidParameter)
    _new(_Pen(argb, width * UNIT_PX[unit]), out)


@_api
def GdipDeletePen(pen):
    _delete(pen, _Pen)


def _fill(ctx, brush, cgpath, even_odd):
    """cgpath filled with the brush in the drawing state of ctx."""
    q.CGContextAddPath(ctx, cgpath)
    if isinstance(brush, _SolidBrush):
        q.CGContextSetRGBFillColor(ctx, *_rgba(brush.argb))
        (q.CGContextEOFillPath if even_odd else q.CGContextFillPath)(ctx)
        return
    (q.CGContextEOClip if even_odd else q.CGContextClip)(ctx)
    clip = q.CGContextGetClipBoundingBox(ctx)
    brush.draw(ctx, (clip.origin.x, clip.origin.y, clip.size.width, clip.size.height))


@_api
def GdipFillPath(graphics, brush, path):
    g, b, p = _get(graphics, _Graphics), _get(brush, _Brush), _get(path, _Path)
    if q.CGPathIsEmpty(p.cg):
        return
    with _drawing(g, g.smoothing in SMOOTH) as ctx:
        _fill(ctx, b, p.cg, p.fill_mode == 0)


@_api
def GdipDrawPath(graphics, pen, path):
    """The outline: the pen's width centred on it, mitred joins (limit 10), flat caps; never thinner than 1 px."""
    g, pn, p = _get(graphics, _Graphics), _get(pen, _Pen), _get(path, _Path)
    if q.CGPathIsEmpty(p.cg):
        return
    with _drawing(g, g.smoothing in SMOOTH) as ctx:
        q.CGContextAddPath(ctx, p.cg)
        q.CGContextSetRGBStrokeColor(ctx, *_rgba(pn.argb))
        q.CGContextSetLineWidth(ctx, max(1.0, pn.width))
        q.CGContextSetLineJoin(ctx, 0)
        q.CGContextSetLineCap(ctx, 0)
        q.CGContextSetMiterLimit(ctx, 10.0)
        q.CGContextStrokePath(ctx)


# --------------------------------------------------------------------------- fonts and text
UI_FONT = None                                  # in ALIASES: the system's UI font (it has no family name to find)
ALIASES = {"microsoft yahei ui": ("PingFang SC", "Hiragino Sans GB"),
           "microsoft yahei": ("PingFang SC", "Hiragino Sans GB"),
           "segoe ui": (UI_FONT, "Helvetica Neue"),
           "segoe fluent icons": (), "segoe mdl2 assets": ()}     # no icon font: the caller's fallback runs


class _FontFamily(object):
    """A family by name (its font descriptor) or the system UI font (descriptor None)."""

    def __init__(self, descriptor):
        self.descriptor = descriptor

    @classmethod
    def find(cls, name):
        """-> the family, or None when this Mac has none of that name."""
        if name is UI_FONT:
            probe = q.CTFontCreateUIFontForLanguage(UI_FONT_SYSTEM, 12.0, None)
            _release(probe)
            return cls(None) if probe else None
        cfname = _cfstr(name)
        attrs = _cfdict([(q.family_attr, cfname)])
        wanted = q.CTFontDescriptorCreateWithAttributes(attrs)
        mandatory = q.CFSetCreate(None, (P * 1)(q.family_attr), 1, q.set_values)
        found = q.CTFontDescriptorCreateMatchingFontDescriptor(wanted, mandatory)
        for ref in (mandatory, wanted, attrs, cfname):
            _release(ref)
        if not found:
            return None
        family = q.CTFontDescriptorCopyAttribute(found, q.family_attr)
        same = bool(family) and _pystr(family).lower() == name.lower()
        _release(family)
        if not same:
            _release(found)
            return None
        return cls(found)

    def ctfont(self, px, style):
        """A CTFont of this family, px pixels to the em, bold and/or italic as the GDI+ style says."""
        if self.descriptor is None:
            font = q.CTFontCreateUIFontForLanguage(UI_FONT_SYSTEM, px, None)
        else:
            font = q.CTFontCreateWithFontDescriptor(self.descriptor, px, None)
        if not font:
            raise _Fail(OutOfMemory)
        traits = (TRAIT_BOLD if style & FontStyleBold else 0) | (TRAIT_ITALIC if style & FontStyleItalic else 0)
        if traits:
            styled = q.CTFontCreateCopyWithSymbolicTraits(font, 0.0, None, traits, traits)
            if styled:
                _release(font)
                font = styled
        return font

    def close(self):
        _release(self.descriptor)
        self.descriptor = None


class _Font(object):
    def __init__(self, family, px, style):
        self.ct = family.ctfont(px, style)

    def close(self):
        _release(self.ct)
        self.ct = None


class _StringFormat(object):
    def __init__(self, flags):
        self.flags, self.align, self.line_align = flags, 0, 0


_DEFAULT_FORMAT = _StringFormat(0)


@_api
def GdipCreateFontFamilyFromName(name, collection, out):
    """The Windows families the pets ask for are mapped to macOS faces; a real macOS family name is taken as it is;
    anything else (the icon fonts too) is FontFamilyNotFound."""
    if collection is not None:
        raise _Fail(NotImplemented_)
    if not name:
        raise _Fail(InvalidParameter)
    for candidate in ALIASES.get(name.lower(), (name,)):
        family = _FontFamily.find(candidate)
        if family is not None:
            _new(family, out)
            return
    raise _Fail(FontFamilyNotFound)


@_api
def GdipDeleteFontFamily(family):
    _delete(family, _FontFamily)


@_api
def GdipCreateFont(family, em_size, style, unit, out):
    if unit not in UNIT_PX or em_size <= 0:
        raise _Fail(InvalidParameter)
    _new(_Font(_get(family, _FontFamily), em_size * UNIT_PX[unit], style), out)


@_api
def GdipDeleteFont(font):
    _delete(font, _Font)


@_api
def GdipCreateStringFormat(flags, language, out):
    _new(_StringFormat(flags), out)


@_api
def GdipDeleteStringFormat(fmt):
    _delete(fmt, _StringFormat)


@_api
def GdipSetStringFormatAlign(fmt, align):
    _set_alignment(fmt, "align", align)


@_api
def GdipSetStringFormatLineAlign(fmt, align):
    _set_alignment(fmt, "line_align", align)


def _set_alignment(fmt, attr, align):
    if align not in (0, 1, 2):                    # StringAlignmentNear, Center, Far
        raise _Fail(InvalidParameter)
    setattr(_get(fmt, _StringFormat), attr, align)


def _format(fmt):
    return _DEFAULT_FORMAT if fmt is None or not _handle(fmt) else _get(fmt, _StringFormat)


def _ctline(text, ctfont):
    """A CTLine of text in ctfont (CoreText's fallback fonts where it has no glyph); the caller releases it."""
    cftext = _cfstr(text)
    attrs = _cfdict([(q.font_attr, ctfont)])
    astr = q.CFAttributedStringCreate(None, cftext, attrs)
    line = q.CTLineCreateWithAttributedString(astr)
    for ref in (astr, attrs, cftext):
        _release(ref)
    if not line:
        raise _Fail(OutOfMemory)
    return line


class _Layout(object):
    """text in ctfont laid out in the rectangle as GDI+ does with a default (not typographic) string format: 1/6 em
    of padding either side of a line, lines the font's line spacing apart, aligned with the format's alignment
    (a zero width or height: aligned on the point instead).  lines: [(CTLine, x, baseline)], box: (x, y, w, h)
    as MeasureString gives it.  close() releases the lines."""

    def __init__(self, text, ctfont, rect, fmt):
        x, y, w, h = rect
        texts = text.replace("\r\n", "\n").split("\n") if text else []
        em = q.CTFontGetSize(ctfont)
        pad = em / 6.0
        ascent = q.CTFontGetAscent(ctfont)
        spacing = ascent + q.CTFontGetDescent(ctfont) + q.CTFontGetLeading(ctfont)
        total = spacing * len(texts)
        top = y + (h - total if h > 0 else -total) * fmt.line_align / 2.0
        self.lines, widths = [], []
        try:
            for i, t in enumerate(texts):
                line = _ctline(t, ctfont)
                self.lines.append((line, 0.0, top + i * spacing + ascent))
                width = q.CTLineGetTypographicBounds(line, None, None, None)
                if not fmt.flags & StringFormatFlagsMeasureTrailingSpaces:
                    width -= q.CTLineGetTrailingWhitespaceWidth(line)
                widths.append(width)
        except Exception:
            self.close()
            raise
        lefts = [self._left(x, w, pad, lw, fmt.align) for lw in widths]
        self.lines = [(line, left, base) for (line, _, base), left in zip(self.lines, lefts)]
        self.box = (min(lefts) - pad, top, max(widths) + 2 * pad, total) if texts else (x, y, 0.0, 0.0)

    @staticmethod
    def _left(x, w, pad, width, align):
        if w > 0:
            return x + (pad, (w - width) / 2.0, w - pad - width)[align]
        return x + (pad, -width / 2.0, -pad - width)[align]

    def outlines(self, cgpath):
        """Every glyph's outline into cgpath, in GDI+ coordinates (y down)."""
        for line, left, baseline in self.lines:
            runs = q.CTLineGetGlyphRuns(line)
            for i in range(q.CFArrayGetCount(runs)):
                _run_outlines(cgpath, q.CFArrayGetValueAtIndex(runs, i), left, baseline)

    def close(self):
        for line, _, _ in self.lines:
            _release(line)
        self.lines = []


def _run_outlines(cgpath, run, left, baseline):
    n = q.CTRunGetGlyphCount(run)
    if n <= 0:
        return
    glyphs, positions = (c_uint16 * n)(), (CGPoint * n)()
    q.CTRunGetGlyphs(run, CFRange(0, 0), glyphs)
    q.CTRunGetPositions(run, CFRange(0, 0), positions)
    font = q.CFDictionaryGetValue(q.CTRunGetAttributes(run), q.font_attr)
    for k in range(n):
        flip = CGAffineTransform(1.0, 0.0, 0.0, -1.0, left + positions[k].x, baseline - positions[k].y)
        glyph = q.CTFontCreatePathForGlyph(font, glyphs[k], ctypes.byref(flip))
        if glyph:                                     # a colour emoji has no outline
            q.CGPathAddPath(cgpath, None, glyph)
            q.CGPathRelease(glyph)


@contextlib.contextmanager
def _laid_out(text, ctfont, layout_rect, fmt):
    layout = _Layout(text, ctfont, layout_rect, fmt)
    try:
        yield layout
    finally:
        layout.close()


@_api
def GdipMeasureString(graphics, text, length, font, layout_rect, fmt, bounding_box, codepoints_fitted,
                      lines_filled):
    _get(graphics, _Graphics)
    text = _text(text, length)
    with _laid_out(text, _get(font, _Font).ct, _rectf(layout_rect), _format(fmt)) as layout:
        box, count = layout.box, len(layout.lines)
    out = _target(bounding_box)
    out.X, out.Y, out.Width, out.Height = box
    if codepoints_fitted is not None:
        _set_value(codepoints_fitted, len(text))
    if lines_filled is not None:
        _set_value(lines_filled, count)


@_api
def GdipDrawString(graphics, text, length, font, layout_rect, fmt, brush):
    """The text's glyphs filled with the brush (a gradient too), clipped to the layout rectangle unless the format
    says NoClip or the rectangle has no size."""
    g, b, f = _get(graphics, _Graphics), _get(brush, _Brush), _format(fmt)
    rect = _rectf(layout_rect)
    cgpath = q.CGPathCreateMutable()
    try:
        with _laid_out(_text(text, length), _get(font, _Font).ct, rect, f) as layout:
            layout.outlines(cgpath)
        if q.CGPathIsEmpty(cgpath):
            return
        with _drawing(g, g.text_hint not in TEXT_ALIASED) as ctx:
            if not f.flags & StringFormatFlagsNoClip and rect[2] > 0 and rect[3] > 0:
                q.CGContextClipToRect(ctx, _rect(*rect))
            _fill(ctx, b, cgpath, False)
    finally:
        q.CGPathRelease(cgpath)


@_api
def GdipAddPathString(path, text, length, family, style, em_size, layout_rect, fmt):
    """The text's glyph outlines as figures of the path, em_size pixels to the em, laid out as DrawString does."""
    p = _get(path, _Path)
    if em_size <= 0:
        raise _Fail(InvalidParameter)
    font = _Font(_get(family, _FontFamily), float(em_size), style)
    try:
        with _laid_out(_text(text, length), font.ct, _rectf(layout_rect), _format(fmt)) as layout:
            layout.outlines(p.cg)
    finally:
        font.close()
    p.open = False
