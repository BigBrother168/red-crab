# -*- coding: utf-8 -*-
r"""Red Crab: Setup.exe.  Standard library only.

    python installer/build.py [--version 1.0.1] [--out DIR] [--embed-zip ZIP] [--iscc ISCC.exe] [--stage-only]

Run it with a full CPython 3.12 for Windows (64-bit) that has Tk (C:\Python312 here; actions/setup-python in CI):
its _tkinter, Tcl/Tk and tkinter package are copied into the embedded Python, which has none (the album and the
connect window need them).  frames/ and frames_hi/ must be rendered first (prerender.py; they are not in git).

  OUT\stage\       what is installed: the program, frames/, frames_hi/, clawd.ico, python\ (embedded + Tk)
  OUT\RedCrab-Setup-<version>.exe
The embedded Python is downloaded from python.org once (kept in OUT\dl) and checked against EMBED_SHA256.
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY_VERSION = "3.12.10"
EMBED_URL = "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (PY_VERSION, PY_VERSION)
EMBED_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
PROGRAM = ["clawd.py", "clawd_pet.pyw", "clawd_hook.py", "clawd_album.pyw", "clawd_album_hints.py",
           "clawd_connect.pyw", "clawd_dsh.mjs", "clawd_scale.py", "clawd_tabs.ps1",
           "LICENSE", "README.md", "README.en.md", "GUIDE.md", "GUIDE.en.md", "CHANGELOG.md"]
FRAME_SETS = ["frames", "frames_hi"]
TCL_DIRS = ["tcl8", "tcl8.6", "tk8.6"]          # Tcl, Tk and the Tcl modules Tk loads (msgcat); not tix, nmake, .lib
TCL_SKIP = {"demos", "images"}                  # Tk's demo programs
TK_DLLS = ["_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "zlib1.dll"]


def say(*a):
    print(*a, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def embed_zip(dl_dir, given):
    path = given or os.path.join(dl_dir, os.path.basename(EMBED_URL))
    if not os.path.isfile(path):
        os.makedirs(dl_dir, exist_ok=True)
        say("downloading", EMBED_URL)
        urllib.request.urlretrieve(EMBED_URL, path + ".part")
        os.replace(path + ".part", path)
    got = sha256(path)
    if got != EMBED_SHA256:
        raise SystemExit("%s: sha256 %s, expected %s" % (path, got, EMBED_SHA256))
    return path


def copy_tree(src, dst, skip=()):
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if n in skip or n == "__pycache__"
                                                       or n.endswith((".lib", ".sh"))])


def make_python(stage, zip_path):
    """The embedded Python, with Tk from the Python running this (same 3.12)."""
    py = os.path.join(stage, "python")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(py)
    base = sys.base_prefix
    if sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise SystemExit("run this with a 64-bit Python 3.12 (Tk is copied from it); this is %s" % sys.version)
    for n in TK_DLLS:
        s = os.path.join(base, "DLLs", n)
        if os.path.isfile(s):
            shutil.copy2(s, py)
        elif n != "zlib1.dll":
            raise SystemExit("no %s in %s: a Python with Tk is needed" % (n, base))
    for d in TCL_DIRS:
        copy_tree(os.path.join(base, "tcl", d), os.path.join(py, "tcl", d), TCL_SKIP)
    copy_tree(os.path.join(base, "Lib", "tkinter"), os.path.join(py, "tkinter"), {"test"})
    lic = os.path.join(py, "licenses")
    os.makedirs(lic)
    shutil.copy2(os.path.join(py, "LICENSE.txt"), os.path.join(lic, "Python-LICENSE.txt"))
    shutil.copy2(os.path.join(HERE, "tcl-license.terms"), os.path.join(lic, "Tcl-license.terms"))   # not in Python's
    shutil.copy2(os.path.join(base, "tcl", "tk8.6", "license.terms"), os.path.join(lic, "Tk-license.terms"))
    return py


# ---------------------------------------------------------------- the icon, from idle frame 0 of frames_hi
def first_frame(set_dir, action="idle"):
    with open(os.path.join(set_dir, "manifest.json"), "rb") as f:
        m = json.loads(f.read().decode("utf-8-sig"))
    with open(os.path.join(set_dir, m["actions"][action]["file"]), "rb") as f:
        n = struct.unpack("<I", f.read(4))[0]
        raw = zlib.decompress(f.read(n))
    return raw, int(m["width"]), int(m["height"])


def shrink_square(raw, w, h, side_out):
    """The body's box (alpha > 0) as a square, box-filtered to side_out; premultiplied BGRA in, straight RGBA out."""
    xs = [x for y in range(h) for x in range(w) if raw[(y * w + x) * 4 + 3] > 8]
    ys = [y for y in range(h) for x in range(w) if raw[(y * w + x) * 4 + 3] > 8]
    l, r, t, b = min(xs), max(xs), min(ys), max(ys)
    side = max(r - l + 1, b - t + 1) * 1.04
    x0, y0 = (l + r + 1 - side) / 2.0, (t + b + 1 - side) / 2.0
    k = side / side_out
    out = bytearray(side_out * side_out * 4)
    for j in range(side_out):
        ya, yb = int(y0 + j * k), max(int(y0 + (j + 1) * k), int(y0 + j * k) + 1)
        for i in range(side_out):
            xa, xb = int(x0 + i * k), max(int(x0 + (i + 1) * k), int(x0 + i * k) + 1)
            acc = [0, 0, 0, 0]
            n = (yb - ya) * (xb - xa)
            for y in range(max(ya, 0), min(yb, h)):
                row = y * w * 4
                for x in range(max(xa, 0), min(xb, w)):
                    p = row + x * 4
                    acc[0] += raw[p]; acc[1] += raw[p + 1]; acc[2] += raw[p + 2]; acc[3] += raw[p + 3]
            a = acc[3] / n
            q = (j * side_out + i) * 4
            if a > 0:
                out[q] = min(255, int(round(acc[2] / n * 255 / a)))
                out[q + 1] = min(255, int(round(acc[1] / n * 255 / a)))
                out[q + 2] = min(255, int(round(acc[0] / n * 255 / a)))
                out[q + 3] = int(round(a))
    return bytes(out)


def png(rgba, w, h):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    rows = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def make_icon(stage, frames_dir):
    raw, w, h = first_frame(frames_dir)
    sizes = [256, 64, 48, 32, 24, 16]
    pngs = [png(shrink_square(raw, w, h, s), s, s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    dirs = b""
    for s, p in zip(sizes, pngs):
        dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(p), off)
        off += len(p)
    with open(os.path.join(stage, "clawd.ico"), "wb") as f:
        f.write(head + dirs + b"".join(pngs))
    side = 58                                   # the wizard's small picture (top right), 100 % DPI
    with open(os.path.join(os.path.dirname(stage), "wizard_small.png"), "wb") as f:
        f.write(png(shrink_square(raw, w, h, side), side, side))


# ---------------------------------------------------------------- Inno Setup
def find_iscc(given):
    if given:
        return given
    for p in [shutil.which("iscc"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
              os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Inno Setup 6", "ISCC.exe"),
              os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Inno Setup 6", "ISCC.exe")]:
        if p and os.path.isfile(p):
            return p
    raise SystemExit("ISCC.exe not found: install Inno Setup 6 (winget install JRSoftware.InnoSetup)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="1.0.1")
    ap.add_argument("--out", default=os.path.join(ROOT, "build"))
    ap.add_argument("--embed-zip")
    ap.add_argument("--iscc")
    ap.add_argument("--stage-only", action="store_true")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    stage = os.path.join(out, "stage")
    for d in FRAME_SETS:
        if not os.path.isfile(os.path.join(ROOT, d, "manifest.json")):
            raise SystemExit("%s\\ is not rendered (prerender.py)" % d)
    zip_path = embed_zip(os.path.join(out, "dl"), a.embed_zip)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    for n in PROGRAM:
        shutil.copy2(os.path.join(ROOT, n), stage)
    for d in FRAME_SETS:
        os.makedirs(os.path.join(stage, d))
        for f in glob.glob(os.path.join(ROOT, d, "*.frames")):
            shutil.copy2(f, os.path.join(stage, d))
        with open(os.path.join(ROOT, d, "manifest.json"), "rb") as f:
            m = json.loads(f.read().decode("utf-8-sig"))
        m.pop("renderer", None)                 # the build machine's paths; nothing reads it any more
        with open(os.path.join(stage, d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
    say("program and frames copied")
    make_python(stage, zip_path)
    say("python with Tk ready")
    make_icon(stage, os.path.join(ROOT, "frames_hi"))
    say("icon made")
    if a.stage_only:
        return 0
    cmd = [find_iscc(a.iscc), "/Q", "/DAppVersion=" + a.version, "/DStage=" + stage, "/DOutDir=" + out,
           "/DSmallImage=" + os.path.join(out, "wizard_small.png"), os.path.join(HERE, "redcrab.iss")]
    say(" ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode:
        return r.returncode
    exe = os.path.join(out, "RedCrab-Setup-%s.exe" % a.version)
    say("%s  %.1f MB  sha256 %s" % (exe, os.path.getsize(exe) / 1048576.0, sha256(exe)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
