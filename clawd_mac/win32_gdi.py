# -*- coding: utf-8 -*-
"""GDI's part: memory DCs and the DIB sections the pets draw into.

CreateDIBSection makes a shim-owned ctypes buffer of w*h*4 bytes (32-bit BGRA, premultiplied as the pets write it)
and writes its address into ppvBits; it stays alive until DeleteObject.  The program memmoves its rows into it,
clawd_mac/gdiplus.py draws into it by address, and UpdateLayeredWindow copies out of it (pixels()) whatever bitmap
is selected into the DC it is given.  Rows are top-down for a negative biHeight (what the pets use), bottom-up
otherwise, as in Windows.  CreateBitmap makes the other kind the tray's icons use: rows top-down, each a whole
number of WORDs, 1 bpp (an icon's mask) or 32 bpp; it is never what a layered window shows.  Standard library
only."""
import ctypes

from clawd_mac import win32_base as base

BITS_PER_PIXEL = 32
MONO_BITS = 1               # CreateBitmap's other depth: an icon's mask


class Bitmap(object):
    """A DIB section (or a CreateBitmap one): its buffer, and the DC it is selected into (a bitmap is in one DC at a
    time).  stride is a row's bytes: w * 4 at 32 bpp, a whole number of WORDs at 1 bpp."""

    def __init__(self, w, h, top_down, stock=False, bpp=BITS_PER_PIXEL):
        self.w, self.h, self.top_down, self.stock, self.bpp = w, h, top_down, stock, bpp
        self.stride = w * 4 if bpp == BITS_PER_PIXEL else (w + 15) // 16 * 2
        self.buf = (ctypes.c_ubyte * (self.stride * h))()
        self.address = ctypes.addressof(self.buf)
        self.dc = 0


class DC(object):
    """A memory DC: what is selected into it (at first the stock 1 x 1 bitmap, as in Windows)."""

    def __init__(self, selected):
        self.selected = selected


_stock = []                 # [the handle of the stock bitmap], made once


def _stock_bitmap():
    if not _stock:
        _stock.append(base.new_handle(Bitmap(1, 1, True, stock=True)))
    return _stock[0]


def CreateCompatibleDC(hdc):
    return base.new_handle(DC(_stock_bitmap()))


def DeleteDC(hdc):
    dc = base.lookup(hdc, DC)
    if dc is None:
        return base.fail(base.ERROR_INVALID_HANDLE)
    bmp = base.lookup(dc.selected, Bitmap)
    if bmp is not None and not bmp.stock:
        bmp.dc = 0
    base.release(hdc)
    return 1


def CreateDIBSection(hdc, pbmi, usage, ppv_bits, section, offset):
    """32-bit DIBs only, in memory of the shim's own (no file mapping)."""
    bmi = base.deref(pbmi)
    hdr = bmi.bmiHeader if bmi is not None else None
    if hdr is None or base.handle(section):
        return base.fail(base.ERROR_INVALID_PARAMETER)
    w, h = int(hdr.biWidth), int(hdr.biHeight)
    if int(hdr.biBitCount) != BITS_PER_PIXEL or w <= 0 or h == 0:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    bmp = Bitmap(w, abs(h), h < 0)
    out = base.deref(ppv_bits)
    if out is not None:
        out.value = bmp.address
    return base.new_handle(bmp)


def CreateBitmap(w, h, planes, bpp, bits):
    """One plane of 1 or 32 bpp, rows top-down and WORD-aligned (as Windows reads lpBits); bits None: zeros."""
    w, h, planes, bpp = (base.number(v) for v in (w, h, planes, bpp))
    if planes != 1 or bpp not in (MONO_BITS, BITS_PER_PIXEL) or w <= 0 or h <= 0:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    bmp = Bitmap(w, h, True, bpp=bpp)
    src = base.deref(bits)
    if isinstance(src, ctypes._SimpleCData):
        src = src.value                        # c_void_p(address)
    elif isinstance(src, bytearray):
        src = bytes(src)
    if src:
        n = len(bmp.buf)
        if isinstance(src, (bytes, ctypes.Array)):
            n = min(n, ctypes.sizeof(src) if isinstance(src, ctypes.Array) else len(src))
        ctypes.memmove(bmp.buf, src, n)
    return base.new_handle(bmp)


def SelectObject(hdc, hobj):
    """Bitmaps only: -> the bitmap selected before, or 0 (no DC, no bitmap, or a bitmap in another DC)."""
    dc = base.lookup(hdc, DC)
    bmp = base.lookup(hobj, Bitmap)
    hdc, hobj = base.handle(hdc), base.handle(hobj)
    if dc is None or bmp is None or (bmp.dc and bmp.dc != hdc):
        return base.fail(base.ERROR_INVALID_PARAMETER)
    old = dc.selected
    before = base.lookup(old, Bitmap)
    if before is not None and not before.stock:
        before.dc = 0
    dc.selected = hobj
    if not bmp.stock:
        bmp.dc = hdc
    return old


def DeleteObject(hobj):
    """A bitmap still selected into a DC is not deleted (0), as in Windows; the stock one never is (1)."""
    bmp = base.lookup(hobj, Bitmap)
    if bmp is None or bmp.dc:
        return base.fail(base.ERROR_INVALID_PARAMETER)
    if not bmp.stock:
        base.release(hobj)
        bmp.buf = None
        bmp.address = 0
    return 1


def GdiFlush():
    return 1                                   # nothing is batched


def pixels(hdc, x, y, w, h):
    """The w x h rectangle at (x, y) of the bitmap selected into hdc, as top-down BGRA bytes; None if there is none
    or the rectangle is not inside it."""
    dc = base.lookup(hdc, DC)
    bmp = base.lookup(dc.selected, Bitmap) if dc is not None else None
    if bmp is None or bmp.stock or not bmp.address or bmp.bpp != BITS_PER_PIXEL:
        return None
    if x < 0 or y < 0 or w < 0 or h < 0 or x + w > bmp.w or y + h > bmp.h:
        return None
    stride = bmp.w * 4
    if bmp.top_down and x == 0 and w == bmp.w:
        return ctypes.string_at(bmp.address + y * stride, h * stride)
    rows = []
    for r in range(y, y + h):
        row = r if bmp.top_down else bmp.h - 1 - r
        rows.append(ctypes.string_at(bmp.address + row * stride + x * 4, w * 4))
    return b"".join(rows)


def rows(hbm):
    """(w, h, bpp, its rows top-down as bytes) of a bitmap (the tray's icons copy them), or None."""
    bmp = base.lookup(hbm, Bitmap)
    if bmp is None or bmp.stock or not bmp.address:
        return None
    data = ctypes.string_at(bmp.address, bmp.stride * bmp.h)
    if not bmp.top_down:
        data = b"".join(data[r * bmp.stride:(r + 1) * bmp.stride] for r in range(bmp.h - 1, -1, -1))
    return bmp.w, bmp.h, bmp.bpp, data
