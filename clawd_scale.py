# -*- coding: utf-8 -*-
"""Clawd: a frame set scaled to another size.  The pets run this instead of the renderer (prerender.py) when their
size is not one of the sets that come with them, so an install needs no numpy or Pillow.  Standard library only:
GDI+ through ctypes, high-quality bicubic on premultiplied BGRA (as the pets' own live scaling).

    pythonw clawd_scale.py --src DIR --body-px N --out DIR

--src  a frame set: manifest.json (version 2) + <action>.frames; the pets pass frames_hi (300 %) above 100 % and
       frames (100 %) at or below it, so this only ever shrinks.
--out  written to OUT.tmp, flushed, then swapped in (the old set via OUT.old), as prerender.py does.
Every length in px of the manifest is scaled: the canvas, the feet anchor, the sign's place ("top"), the treasure's
place in a clip ("item" x, y; its scale per mille stays), the treasure's box and the glows' sizes; the treasures' and
the glows' own loops are scaled too.  Frames that repeat in a clip are scaled once.  Exit 0 when done; on an error
the traceback goes to stdout (the pets keep it in render.log) and the exit code is 1.
Record format of *.frames (as prerender.py): uint32 LE length L, then zlib.compress(raw) (L bytes), raw being the
whole canvas, premultiplied BGRA, top-down.
"""
import ctypes
import json
import math
import os
import shutil
import struct
import sys
import time
import traceback
import zlib

ZLEVEL = 6                     # the pets inflate one frame a tick; 9 is several times slower here and barely smaller

PixelFormat32bppPARGB = 0x000E200B
CompositingModeSourceCopy = 1
InterpolationModeHighQualityBicubic = 7
PixelOffsetModeHighQuality = 2
FlushIntentionSync = 1
WrapModeClamp = 4
UnitPixel = 2


class _StartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", ctypes.c_int), ("SuppressExternalCodecs", ctypes.c_int)]


class Shrinker(object):
    """One frame of sw x sh -> dw x dh at the factor f, the source's (0, 0) on the target's (0, 0): a length x in
    the source is x * f in the target.  Outside the source only transparency (clamp wrap).  The bitmaps and the
    graphics are made once per size and reused."""

    def __init__(self):
        dll = ctypes.WinDLL("gdiplus")
        P, PP, I, F = ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_float

        def api(name, args):
            fn = getattr(dll, name)
            fn.restype, fn.argtypes = ctypes.c_int, args
            return fn
        self.startup = api("GdiplusStartup", [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(_StartupInput), P])
        self.create_bitmap = api("GdipCreateBitmapFromScan0", [I, I, I, I, P, PP])
        self.graphics_of = api("GdipGetImageGraphicsContext", [P, PP])
        self.set_compositing = api("GdipSetCompositingMode", [P, I])
        self.set_interpolation = api("GdipSetInterpolationMode", [P, I])
        self.set_pixel_offset = api("GdipSetPixelOffsetMode", [P, I])
        self.clear = api("GdipGraphicsClear", [P, ctypes.c_uint32])
        self.draw = api("GdipDrawImageRectRect", [P, P, F, F, F, F, F, F, F, F, I, P, P, P])
        self.flush = api("GdipFlush", [P, I])
        self.delete_graphics = api("GdipDeleteGraphics", [P])
        self.dispose_image = api("GdipDisposeImage", [P])
        self.create_attrs = api("GdipCreateImageAttributes", [PP])
        self.set_wrap = api("GdipSetImageAttributesWrapMode", [P, I, ctypes.c_uint32, I])
        token = ctypes.c_size_t(0)
        self._ok(self.startup(ctypes.byref(token), ctypes.byref(_StartupInput(1, None, 0, 0)), None), "GdiplusStartup")
        self.attrs = ctypes.c_void_p()
        self._ok(self.create_attrs(ctypes.byref(self.attrs)), "GdipCreateImageAttributes")
        self._ok(self.set_wrap(self.attrs, WrapModeClamp, 0, 0), "GdipSetImageAttributesWrapMode")
        self.key = None
        self.src = self.dst = self.g = None

    @staticmethod
    def _ok(st, what):
        if st != 0:
            raise OSError("%s failed (GDI+ status %d)" % (what, st))

    def _configure(self, sw, sh, dw, dh, f):
        if self.g:
            self.delete_graphics(self.g)
        for b in (self.dst, self.src):
            if b:
                self.dispose_image(b)
        self.src_buf = (ctypes.c_ubyte * (sw * sh * 4))()
        self.dst_buf = (ctypes.c_ubyte * (dw * dh * 4))()
        self.src, self.dst, self.g = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        self._ok(self.create_bitmap(sw, sh, sw * 4, PixelFormat32bppPARGB, ctypes.addressof(self.src_buf),
                                    ctypes.byref(self.src)), "GdipCreateBitmapFromScan0")
        self._ok(self.create_bitmap(dw, dh, dw * 4, PixelFormat32bppPARGB, ctypes.addressof(self.dst_buf),
                                    ctypes.byref(self.dst)), "GdipCreateBitmapFromScan0")
        self._ok(self.graphics_of(self.dst, ctypes.byref(self.g)), "GdipGetImageGraphicsContext")
        self._ok(self.set_compositing(self.g, CompositingModeSourceCopy), "GdipSetCompositingMode")
        self._ok(self.set_interpolation(self.g, InterpolationModeHighQualityBicubic), "GdipSetInterpolationMode")
        self._ok(self.set_pixel_offset(self.g, PixelOffsetModeHighQuality), "GdipSetPixelOffsetMode")
        self.key = (sw, sh, dw, dh, f)

    def shrink(self, raw, sw, sh, dw, dh, f):
        if self.key != (sw, sh, dw, dh, f):
            self._configure(sw, sh, dw, dh, f)
        if len(raw) != sw * sh * 4:
            raise ValueError("a frame of %d bytes, expected %d" % (len(raw), sw * sh * 4))
        ctypes.memmove(self.src_buf, raw, len(raw))
        self.clear(self.g, 0)
        self._ok(self.draw(self.g, self.src, 0.0, 0.0, float(dw), float(dh), 0.0, 0.0, dw / f, dh / f,
                           UnitPixel, self.attrs, None, None), "GdipDrawImageRectRect")
        self.flush(self.g, FlushIntentionSync)
        return bytes(self.dst_buf)


def read_records(path):
    with open(path, "rb") as fh:
        data = fh.read()
    out, off = [], 0
    while off + 4 <= len(data):
        (n,) = struct.unpack_from("<I", data, off)
        off += 4
        if n == 0 or off + n > len(data):
            break
        out.append(data[off:off + n])
        off += n
    return out


def scale_file(sh_, src, dst, sw, sh, dw, dh, f):
    """Every record of src scaled into dst; -> the number of frames."""
    done = {}
    parts = []
    for blob in read_records(src):
        z = done.get(blob)
        if z is None:
            z = zlib.compress(sh_.shrink(zlib.decompress(blob), sw, sh, dw, dh, f), ZLEVEL)
            done[blob] = z
        parts.append(struct.pack("<I", len(z)))
        parts.append(z)
    with open(dst, "wb") as fh:
        fh.write(b"".join(parts))
        fh.flush()
        os.fsync(fh.fileno())
    return len(parts) // 2


def set_stamp(d):
    """Which frames a set is: the manifest's bytes and every .frames file's name and size (as clawd_pet.pyw
    set_stamp).  A scaled set keeps its source's as "source_stamp": new art in an update makes it be scaled again."""
    import hashlib
    h = hashlib.sha1()
    with open(os.path.join(d, "manifest.json"), "rb") as fh:
        h.update(fh.read())
    for n in sorted(os.listdir(d)):
        if n.endswith(".frames"):
            h.update(("%s:%d;" % (n, os.path.getsize(os.path.join(d, n)))).encode("utf-8"))
    return h.hexdigest()


def px(v, f):
    return int(round(v * f))


def scale_set(src_dir, body_px, out_dir):
    with open(os.path.join(src_dir, "manifest.json"), "rb") as fh:
        m = json.loads(fh.read().decode("utf-8-sig"))
    src_px = float(m.get("base_body_px") or 100)
    f = body_px / src_px
    if not 0.05 <= f <= 1.0:
        raise ValueError("%s px from a %s px set: this only shrinks" % (body_px, src_px))
    sw, sh = int(m["width"]), int(m["height"])
    dw, dh = max(1, int(math.ceil(sw * f))), max(1, int(math.ceil(sh * f)))
    shrinker = Shrinker()
    tmp = out_dir + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    out = dict(m)
    out.pop("renderer", None)                    # not rendered: a scaled set is never re-rendered from
    out.update(width=dw, height=dh, base_body_px=int(round(body_px)), scaled_from=int(round(src_px)),
               source_stamp=set_stamp(src_dir))
    a = m.get("anchor")
    if isinstance(a, dict) and "feet_x" in a and "feet_y" in a:
        out["anchor"] = {"feet_x": round(a["feet_x"] * f, 2), "feet_y": round(a["feet_y"] * f, 2)}
    actions = {}
    for name, info in (m.get("actions") or {}).items():
        info = dict(info)
        if isinstance(info.get("item"), list):
            info["item"] = [[px(e[0], f), px(e[1], f)] + list(e[2:]) if isinstance(e, list) and len(e) >= 2 else e
                            for e in info["item"]]
        if isinstance(info.get("top"), list) and len(info["top"]) == 2:
            info["top"] = [px(info["top"][0], f), px(info["top"][1], f)]
        info["count"] = scale_file(shrinker, os.path.join(src_dir, info["file"]), os.path.join(tmp, info["file"]),
                                   sw, sh, dw, dh, f)
        actions[name] = info
    out["actions"] = actions
    it = m.get("items")
    if isinstance(it, dict) and isinstance(it.get("box"), int):
        it = json.loads(json.dumps(it))
        box = it["box"]
        it["box"] = max(1, px(box, f))
        fb = it["box"] / float(box)
        for info in (it.get("names") or {}).values():
            scale_file(shrinker, os.path.join(src_dir, info["file"]), os.path.join(tmp, info["file"]),
                       box, box, it["box"], it["box"], fb)
        for info in (it.get("auras") or {}).values():
            side = int(info["size"])
            info["size"] = max(1, px(side, f))
            scale_file(shrinker, os.path.join(src_dir, info["file"]), os.path.join(tmp, info["file"]),
                       side, side, info["size"], info["size"], info["size"] / float(side))
        out["items"] = it
    with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
        fh.flush()
        os.fsync(fh.fileno())
    swap_into_place(tmp, out_dir)


def swap_into_place(tmp, dst):
    """As prerender.py: the old set out of the way (OUT.old), the new one in; if something holds the old one open,
    file by file with the manifest last."""
    old = dst + ".old"
    if os.path.isdir(old):
        shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(dst):
        ok = False
        for _ in range(15):
            try:
                os.replace(dst, old)
                ok = True
                break
            except OSError:
                time.sleep(0.2)
        if not ok:
            names = sorted(os.listdir(tmp), key=lambda n: n == "manifest.json")
            for n in names:
                os.replace(os.path.join(tmp, n), os.path.join(dst, n))
            keep = set(names)
            for n in os.listdir(dst):
                if n not in keep and n.endswith(".frames"):
                    os.remove(os.path.join(dst, n))
            shutil.rmtree(tmp, ignore_errors=True)
            return
    for attempt in range(15):                  # a scanner or indexer can hold a just-written file for a moment
        try:
            os.replace(tmp, dst)
            break
        except OSError:
            if attempt == 14:
                if os.path.isdir(old) and not os.path.exists(dst):
                    os.replace(old, dst)       # keep the previous set
                raise
            time.sleep(0.2)
    shutil.rmtree(old, ignore_errors=True)


def main(argv):
    args = {}
    i = 1
    while i < len(argv):
        if argv[i] in ("--src", "--body-px", "--out") and i + 1 < len(argv):
            args[argv[i]] = argv[i + 1]
            i += 1
        i += 1
    if set(args) != {"--src", "--body-px", "--out"}:
        print(__doc__)
        return 2
    t0 = time.time()
    try:
        scale_set(os.path.abspath(args["--src"]), float(args["--body-px"]), os.path.abspath(args["--out"]))
    except Exception:
        traceback.print_exc(file=sys.stdout)
        return 1
    print("scaled to %s px in %.1f s" % (args["--body-px"], time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
