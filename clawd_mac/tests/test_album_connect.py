# -*- coding: utf-8 -*-
"""The album (clawd_album.pyw) and the connect window (clawd_connect.pyw) on macOS: their Windows faces mapped to Mac
ones, one window at a time (a second start brings the open one forward by its pid and ends with 0), the memory and the
language helpers, where the album keeps its home, the window coming to the front once.  No Tk window is made here: the
second starts end before Tk, and the rest is plain functions (their own self-tests show the windows)."""
import importlib.machinery
import importlib.util
import os
import py_compile
import subprocess
import sys
import time
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALBUM = os.path.join(ROOT, "clawd_album.pyw")
CONNECT = os.path.join(ROOT, "clawd_connect.pyw")
SECOND_START_SECS = 3.0
HOLDER_READY_SECS = 10.0

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def album():
    return load("clawd_album_under_test", ALBUM)


@pytest.fixture(scope="module")
def connect():
    return load("clawd_connect_under_test", CONNECT)


class FakeTk(object):
    """What mac_font / mac_face ask a widget: the Tk default font's family."""

    def call(self, *args):
        assert args == ("font", "actual", "TkDefaultFont", "-family")
        return ".AppleSystemUIFont"


class FakeWidget(object):
    tk = FakeTk()


class FakeRoot(object):
    """A root that records its <Map> binding, for mac_front."""

    def __init__(self):
        self.bound = {}

    def bind(self, seq, fn):
        self.bound[seq] = fn

    def unbind(self, seq):
        self.bound.pop(seq, None)


# ---- both files compile and import on macOS

@pytest.mark.parametrize("path", [ALBUM, CONNECT])
def test_compiles(path, tmp_path):
    py_compile.compile(path, cfile=str(tmp_path / "out.pyc"), doraise=True)


def test_both_import_on_darwin(album, connect):
    assert album.MAC and connect.MAC
    assert callable(album.mac_main) and callable(connect.mac_main)


# ---- the fonts

@pytest.mark.parametrize("win, mac", [
    (("Microsoft YaHei UI", -18, "bold"), ("PingFang SC", -18, "bold")),
    (("Microsoft YaHei", -14), ("PingFang SC", -14)),
    (("Segoe UI", -11), (".AppleSystemUIFont", -11)),
    (("Segoe UI Symbol", -14, "bold"), (".AppleSystemUIFont", -14, "bold")),
    (("Consolas", -12), ("Menlo", -12)),
    (("Segoe UI Emoji", -20), ("Apple Color Emoji", -20)),
    (("KaiTi", -17, "normal"), ("Kaiti SC", -17, "normal")),
    (("Segoe Print", -14, "bold"), ("Noteworthy", -14, "bold")),
    (("Segoe Fluent Icons", -30), ("Apple Symbols", -30)),
])
def test_album_maps_windows_faces(album, win, mac):
    assert album.mac_font(win, FakeWidget()) == mac


@pytest.mark.parametrize("font", [("Helvetica", -12), ("PingFang SC", -14, "bold"), "TkDefaultFont", None, ()])
def test_album_leaves_other_fonts(album, font):
    assert album.mac_font(font, FakeWidget()) == font


def test_album_icons_become_symbols(album):
    icons = set(album.GIFT_ICON.values()) | {"\ue73e"}    # the gifts' icons and the sign's tick
    assert icons <= set(album.MAC_ICONS)
    for sym in album.MAC_ICONS.values():                          # none left in the private use area
        assert len(sym) == 1 and not 0xE000 <= ord(sym) <= 0xF8FF


@pytest.mark.parametrize("win, mac", [("Microsoft YaHei UI", "PingFang SC"), ("Segoe UI", ".AppleSystemUIFont"),
                                      ("Consolas", "Menlo"), ("Helvetica Neue", "Helvetica Neue")])
def test_connect_maps_windows_faces(connect, win, mac):
    assert connect.mac_face(win, FakeWidget()) == mac


# ---- memory, language, home

def test_memory_is_ru_maxrss_in_mb(album):
    import resource
    work, private = album.memory()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576.0
    assert work == private and 1.0 < work <= rss + 0.1


def test_system_lang_is_the_macos_one(album, monkeypatch):
    for lang in ("en", "zh"):
        monkeypatch.setattr(album.macsys, "ui_lang", lambda lang=lang: lang)
        assert album.system_lang() == lang


def test_home_beside_the_script_when_a_save_is_there(album, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAWD_HOME", raising=False)
    (tmp_path / "grow.json").write_text("{}")
    monkeypatch.setattr(album, "HERE", str(tmp_path))
    assert album.data_home() == str(tmp_path)


def test_home_not_inside_an_app(album, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAWD_HOME", raising=False)
    inside = tmp_path / "RedCrab.app" / "Contents" / "Resources"
    inside.mkdir(parents=True)
    (inside / "state.json").write_text("{}")
    monkeypatch.setattr(album, "HERE", str(inside))
    assert album.data_home() == album.macsys.home_dir()


def test_home_default_and_clawd_home(album, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAWD_HOME", raising=False)
    monkeypatch.setattr(album, "HERE", str(tmp_path))                   # no save here
    assert album.data_home().endswith(os.path.join("Library", "Application Support", "Clawd"))
    monkeypatch.setenv("CLAWD_HOME", str(tmp_path / "h"))
    assert album.data_home() == str(tmp_path / "h")


# ---- to the front, once

@pytest.mark.parametrize("name", ["album", "connect"])
def test_front_once_when_shown(name, album, connect, monkeypatch):
    mod = album if name == "album" else connect
    calls = []
    monkeypatch.delenv("CLAWD_NO_ACTIVATE", raising=False)
    monkeypatch.setattr(mod.macsys, "activate_pid", lambda pid: calls.append(pid) or True)
    root = FakeRoot()
    mod.mac_front(root)
    root.bound["<Map>"](None)
    assert calls == [os.getpid()] and "<Map>" not in root.bound


@pytest.mark.parametrize("name", ["album", "connect"])
def test_no_front_with_clawd_no_activate(name, album, connect, monkeypatch):
    mod = album if name == "album" else connect
    monkeypatch.setenv("CLAWD_NO_ACTIVATE", "1")
    root = FakeRoot()
    mod.mac_front(root)
    assert root.bound == {}


# ---- one window at a time

HOLDER = """import sys
sys.path.insert(0, sys.argv[1])
from clawd_mac import lock
if not lock.acquire(sys.argv[2]):
    sys.exit(3)
print("held", flush=True)
sys.stdin.read()
"""

SECOND = """import runpy, sys
sys.path.insert(0, sys.argv[1])
from clawd_mac import system
system.activate_pid = lambda pid: print("ACTIVATE %r" % (pid,), flush=True) or True
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def album_lock(home):
    return "ClawdAlbum_%08x" % (zlib.crc32(os.path.normcase(home).encode("utf-8")) & 0xFFFFFFFF)


@pytest.mark.parametrize("name", ["album", "connect"])
def test_second_start_brings_the_first_forward(name, tmp_path):
    user, home = tmp_path / "user", tmp_path / "home"         # HOME elsewhere: the lock files go there too
    user.mkdir()
    home.mkdir()
    env = dict(os.environ, HOME=str(user), CLAWD_HOME=str(home), CLAWD_NO_ACTIVATE="1",
               CLAUDE_CONFIG_DIR=str(user / ".claude"), CODEX_HOME=str(user / ".codex"), DSH_HOME=str(user / ".dsh"))
    script, lock_name = (ALBUM, album_lock(str(home))) if name == "album" else (CONNECT, "Local\\ClawdConnect")
    holder = subprocess.Popen([sys.executable, "-I", "-c", HOLDER, ROOT, lock_name], env=env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True)
    second = None
    try:
        assert holder.stdout.readline().strip() == "held"
        t0 = time.monotonic()
        second = subprocess.Popen([sys.executable, "-I", "-c", SECOND, ROOT, script, "--home", str(home)], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = second.communicate(timeout=SECOND_START_SECS)
        took = time.monotonic() - t0
        assert second.returncode == 0, err
        assert out.strip() == "ACTIVATE %r" % holder.pid
        assert took < SECOND_START_SECS
    finally:
        for p in (second, holder):
            if p is not None and p.poll() is None:
                p.kill()
                p.wait()
