# -*- coding: utf-8 -*-
"""Red Crab: RedCrab.app in a .dmg, for macOS.  Standard library only.

    python installer/build_mac.py [--version 1.0.0] [--arch arm64|x86_64] [--out DIR] [--frames DIR]
                                  [--frames-hi DIR] [--python-tar TARBALL] [--stage-only]

Run it on macOS (codesign, iconutil and hdiutil come with it).  frames/ and frames_hi/ must be rendered first
(prerender.py; they are not in git).  The app is ad-hoc signed, not notarized: the first start needs System Settings
→ Privacy & Security → Open Anyway (on macOS 14 and earlier right-click → Open will do).

  OUT/mac/RedCrab.app/Contents/
      MacOS/RedCrab           a /bin/sh launcher: Resources/python runs Resources/app/clawd_pet.pyw
      Resources/python/       python-build-standalone CPython 3.12 (with Tk) + PyObjC (requirements-mac.txt)
      Resources/app/          the program (build.py's PROGRAM, clawd_mac), frames/, frames_hi/
      Resources/clawd.icns    the icon, made like build.py's clawd.ico
  OUT/RedCrab-<version>-macOS-<arch>.dmg
The Python is downloaded from GitHub once (kept in OUT/dl) and checked against PYTHON_SHA256; PyObjC comes from PyPI.
"""
import argparse
import glob
import importlib.util
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PBS_RELEASE = "20261026"                        # python-build-standalone, released 2026-10-26
PY_VERSION = "3.12.16"
PYTHON_DL = "https://github.com/astral-sh/python-build-standalone/releases/download/%s/" % PBS_RELEASE
PYTHON_TAR = "cpython-%s+%s-%%s-apple-darwin-install_only.tar.gz" % (PY_VERSION, PBS_RELEASE)
PYTHON_SHA256 = {
    "arm64": "fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e",
    "x86_64": "a962e47df522889eaa7ff0d6a56203f1079f68aabb65ffdbe8455f362bc769f3",
}
PBS_ARCH = {"arm64": "aarch64", "x86_64": "x86_64"}
APP_NAME = "Red Crab"
BUNDLE_ID = "io.github.bigbrother168.redcrab"
EXECUTABLE = "RedCrab"
MIN_MACOS = "11.0"
WINDOWS_ONLY = {"clawd_tabs.ps1"}
FRAME_SETS = ["frames", "frames_hi"]
ICON_SIDES = [16, 32, 128, 256, 512]            # the .iconset's points; each also at @2x
STDLIB_TESTS = {"test", "tests", "idle_test"}    # test suites in the standard library and its packages
HDIUTIL_TRIES = 3                               # hdiutil create now and then fails with "Resource busy" on CI
LAUNCHER = """#!/bin/sh
# Red Crab: the bundled Python runs the pet.
res="$(cd "$(dirname "$0")/../Resources" && pwd -P)" || exit 1
exec "$res/python/bin/python3" -I "$res/app/clawd_pet.pyw" "$@"
"""


def load_windows_build():
    """installer/build.py: its PROGRAM list and icon code are shared, not copied."""
    spec = importlib.util.spec_from_file_location("redcrab_build", os.path.join(HERE, "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


WIN = load_windows_build()
say = WIN.say


def run(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode:
        raise SystemExit("failed (exit %d): %s" % (r.returncode, " ".join(cmd)))
    return r


# ---------------------------------------------------------------- Python (python-build-standalone)
def python_tar(dl_dir, arch, given):
    name = PYTHON_TAR % PBS_ARCH[arch]
    url = PYTHON_DL + urllib.parse.quote(name)
    path = given or os.path.join(dl_dir, name)
    if not os.path.isfile(path):
        os.makedirs(dl_dir, exist_ok=True)
        say("downloading", url)
        urllib.request.urlretrieve(url, path + ".part")
        os.replace(path + ".part", path)
    got = WIN.sha256(path)
    if got != PYTHON_SHA256[arch]:
        raise SystemExit("%s: sha256 %s, expected %s (%s)" % (path, got, PYTHON_SHA256[arch], arch))
    return path


def extract_python(tar_path, resources):
    """The tarball's python/ becomes Resources/python."""
    with tarfile.open(tar_path) as t:
        bad = [m.name for m in t.getmembers() if m.name.split("/")[0] != "python"]
        if bad:
            raise SystemExit("%s: unexpected member %s" % (tar_path, bad[0]))
        t.extractall(resources, filter="data")
    return os.path.join(resources, "python")


def add_pyobjc(py):
    exe = os.path.join(py, "bin", "python3")
    run([exe, "-I", "-c", "import tkinter, _tkinter"])
    run([exe, "-I", "-m", "pip", "install", "--quiet", "--no-compile", "--only-binary=:all:",
         "--disable-pip-version-check", "--no-warn-script-location", "-r", os.path.join(ROOT, "requirements-mac.txt")])
    run([exe, "-I", "-B", "-c", "import AppKit, Quartz, CoreText, tkinter"])


def slim_python(py):
    """No test suites, IDLE, ensurepip wheels or stray __pycache__ (precompile() makes them again)."""
    lib = os.path.join(py, "lib", "python3.12")
    gone = [os.path.join(lib, "idlelib"), os.path.join(lib, "ensurepip", "_bundled")]
    gone += glob.glob(os.path.join(py, "bin", "idle3*"))
    for d in [lib] + [os.path.join(lib, n) for n in os.listdir(lib) if n != "site-packages"]:
        if os.path.isdir(d):
            gone += [os.path.join(d, n) for n in os.listdir(d) if n in STDLIB_TESTS]
    for root, dirs, _ in os.walk(py):
        gone += [os.path.join(root, n) for n in dirs if n == "__pycache__"]
    for p in gone:
        if os.path.islink(p) or os.path.isfile(p):
            os.remove(p)
        elif os.path.isdir(p):
            shutil.rmtree(p)


def precompile(py, app):
    """Byte-compile the Python and the program with the bundled Python, so the app never writes into its (signed)
    bundle.  checked-hash: the .pyc holds a hash of its source instead of its mtime, so copies that change mtimes (the
    .dmg, Finder) keep the caches valid, and an edited source is still noticed."""
    run([os.path.join(py, "bin", "python3"), "-I", "-B", "-m", "compileall", "-q", "-j", "0",
         "--invalidation-mode", "checked-hash", os.path.join(py, "lib"), app])


# ---------------------------------------------------------------- the program and its frames
def copy_program(app):
    os.makedirs(app)
    for n in WIN.PROGRAM:
        if n not in WINDOWS_ONLY:
            shutil.copy2(os.path.join(ROOT, n), app)
    pkg = os.path.join(ROOT, "clawd_mac")
    if os.path.isdir(pkg):
        shutil.copytree(pkg, os.path.join(app, "clawd_mac"),
                        ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))


def copy_frames(src, dst):
    """The *.frames and the manifest without "renderer" (the build machine's paths), as build.py does."""
    os.makedirs(dst)
    for f in glob.glob(os.path.join(src, "*.frames")):
        shutil.copy2(f, dst)
    with open(os.path.join(src, "manifest.json"), "rb") as f:
        m = json.loads(f.read().decode("utf-8-sig"))
    m.pop("renderer", None)
    with open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- the icon, from idle frame 0 of frames_hi
def make_icns(resources, frames_dir):
    raw, w, h = WIN.first_frame(frames_dir)
    pngs = {}
    for s in sorted(set(ICON_SIDES + [2 * s for s in ICON_SIDES])):
        pngs[s] = WIN.png(WIN.shrink_square(raw, w, h, s), s, s)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "clawd.iconset")
        os.makedirs(iconset)
        for s in ICON_SIDES:
            for name, side in (("icon_%dx%d.png" % (s, s), s), ("icon_%dx%d@2x.png" % (s, s), 2 * s)):
                with open(os.path.join(iconset, name), "wb") as f:
                    f.write(pngs[side])
        run(["iconutil", "-c", "icns", "-o", os.path.join(resources, "clawd.icns"), iconset])


# ---------------------------------------------------------------- the bundle
def bundle_version(version):
    """CFBundleVersion: the version's leading numbers (0.0.42-ci -> 0.0.42)."""
    m = re.match(r"\d+(\.\d+)*", version)
    if not m:
        raise SystemExit("--version %r: it must start with a number, like 1.0.0 or 0.0.42-ci" % version)
    return m.group(0)


def write_bundle_files(contents, version):
    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": EXECUTABLE,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": bundle_version(version),
        "CFBundleIconFile": "clawd",
        "LSMinimumSystemVersion": MIN_MACOS,
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    }
    with open(os.path.join(contents, "Info.plist"), "wb") as f:
        plistlib.dump(info, f)
    macos = os.path.join(contents, "MacOS")
    os.makedirs(macos)
    launcher = os.path.join(macos, EXECUTABLE)
    with open(launcher, "w", encoding="utf-8", newline="\n") as f:
        f.write(LAUNCHER)
    os.chmod(launcher, 0o755)


def sign(bundle):
    run(["codesign", "--force", "--deep", "--sign", "-", bundle])
    run(["codesign", "--verify", "--deep", "--strict", bundle])


def make_dmg(stage, dmg):
    os.symlink("/Applications", os.path.join(stage, "Applications"))
    if os.path.exists(dmg):
        os.remove(dmg)
    cmd = ["hdiutil", "create", "-quiet", "-volname", APP_NAME, "-srcfolder", stage, "-ov", "-format", "UDZO", dmg]
    for i in range(HDIUTIL_TRIES):
        if subprocess.run(cmd).returncode == 0:
            return
        say("hdiutil create failed (try %d of %d)" % (i + 1, HDIUTIL_TRIES))
        time.sleep(5)
    raise SystemExit("failed: " + " ".join(cmd))


def size_mb(path):
    if os.path.isfile(path):
        return os.path.getsize(path) / 1048576.0
    return sum(os.path.getsize(os.path.join(r, n)) for r, _, fs in os.walk(path) for n in fs
               if not os.path.islink(os.path.join(r, n))) / 1048576.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--arch", choices=sorted(PYTHON_SHA256), default=platform.machine())
    ap.add_argument("--out", default=os.path.join(ROOT, "build"))
    ap.add_argument("--frames", default=os.path.join(ROOT, "frames"))
    ap.add_argument("--frames-hi", default=os.path.join(ROOT, "frames_hi"))
    ap.add_argument("--python-tar")
    ap.add_argument("--stage-only", action="store_true")
    a = ap.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("run this on macOS (codesign, iconutil and hdiutil)")
    bundle_version(a.version)
    if a.arch not in PYTHON_SHA256:
        raise SystemExit("--arch: arm64 or x86_64 (this machine is %s)" % a.arch)
    frame_sets = {"frames": os.path.abspath(a.frames), "frames_hi": os.path.abspath(a.frames_hi)}
    for name, d in frame_sets.items():
        if not os.path.isfile(os.path.join(d, "manifest.json")):
            raise SystemExit("%s/ (%s) is not rendered: no manifest.json (prerender.py)" % (name, d))
    out = os.path.abspath(a.out)
    tar_path = python_tar(os.path.join(out, "dl"), a.arch, a.python_tar)
    stage = os.path.join(out, "mac")
    if os.path.lexists(stage):
        shutil.rmtree(stage)
    bundle = os.path.join(stage, "RedCrab.app")
    contents = os.path.join(bundle, "Contents")
    resources = os.path.join(contents, "Resources")
    os.makedirs(resources)
    write_bundle_files(contents, a.version)
    app = os.path.join(resources, "app")
    copy_program(app)
    for name, d in frame_sets.items():
        copy_frames(d, os.path.join(app, name))
    say("program and frames copied")
    py = extract_python(tar_path, resources)
    add_pyobjc(py)
    slim_python(py)
    precompile(py, app)
    say("python %s (%s) with Tk and PyObjC ready, byte-compiled" % (PY_VERSION, a.arch))
    make_icns(resources, frame_sets["frames_hi"])
    say("icon made")
    sign(bundle)
    say("%s  %.1f MB  ad-hoc signed" % (bundle, size_mb(bundle)))
    if a.stage_only:
        return 0
    dmg = os.path.join(out, "RedCrab-%s-macOS-%s.dmg" % (a.version, a.arch))
    make_dmg(stage, dmg)
    say("%s  %.1f MB  sha256 %s" % (dmg, size_mb(dmg), WIN.sha256(dmg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
