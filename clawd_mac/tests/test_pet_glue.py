# -*- coding: utf-8 -*-
"""clawd_pet.pyw on macOS beyond the shim: where the saves and the scaled sets go (never inside RedCrab.app), start at
login (the pet's own functions and clawd.py, one LaunchAgent), the apps a conversation runs in (by pid), a click on a
circle (the app forward, a terminal's tab by AppleScript, a link opened), the re-render's process group, and
clawd_scale.py stopping by itself once the pet that started it is gone.

Everything under a temporary HOME; no app is activated (activate_pid patched), no osascript or open is run (subprocess
patched), the only processes started are this test's own."""
import importlib.machinery
import importlib.util
import io
import json
import os
import plistlib
import signal
import stat
import struct
import subprocess
import sys
import threading
import time
import types
import zlib

import pytest

from clawd_mac import system

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PET_PATH = os.path.join(ROOT, "clawd_pet.pyw")
CLAWD = os.path.join(ROOT, "clawd.py")
SCALE = os.path.join(ROOT, "clawd_scale.py")
PY = os.path.abspath(sys.executable)
SID = "1a2b3c4d"
TERM, ITERM, GHOSTTY, VSCODE, CLAUDE = 7001, 7002, 7003, 7004, 7005      # pids of apps that are not there
APPS = {TERM: "com.apple.Terminal", ITERM: "com.googlecode.iterm2", GHOSTTY: "com.mitchellh.ghostty",
        VSCODE: "com.microsoft.VSCode", CLAUDE: "com.anthropic.claudefordesktop"}
LINK = "claude://code/continue?session=local_0a1b2c3d"
WAIT = 10.0
GONE_WAIT = 30.0


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A temporary HOME (so LaunchAgents and the saves are under it), and every agent's folder in it too."""
    for k, v in {"HOME": tmp_path, "CLAUDE_CONFIG_DIR": tmp_path / ".claude", "CODEX_HOME": tmp_path / ".codex",
                 "DSH_HOME": tmp_path / ".dsh"}.items():
        monkeypatch.setenv(k, str(v))
    monkeypatch.delenv("CLAWD_HOME", raising=False)
    return tmp_path


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture
def pet(home):
    mod = load(PET_PATH, "clawd_pet_glue")
    mod.set_home(str(home / "pethome"))
    os.makedirs(mod.HOME_DIR)
    return mod


def pet_log(pet):
    try:
        with open(pet.LOG_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def agent_args():
    with open(system.launch_agent_path(), "rb") as f:
        return plistlib.load(f)["ProgramArguments"]


# ---- the saves and the scaled sets ----

def test_home_and_cache_outside_an_app_bundle(pet, home, monkeypatch):
    src = home / "red-crab"
    src.mkdir()
    monkeypatch.setattr(pet, "HERE", str(src))
    assert pet.default_home() == (system.home_dir(), str(src))         # the sets beside the program

    (src / "grow.json").write_text("{}")
    assert pet.default_home() == (str(src), str(src))                  # a copy run from source keeps its save

    (src / "grow.json").unlink()
    src.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert pet.default_home() == (system.home_dir(), system.cache_dir())
    finally:
        src.chmod(stat.S_IRWXU)

    monkeypatch.setenv("CLAWD_HOME", str(home / "elsewhere"))
    assert pet.default_home() == (str(home / "elsewhere"),) * 2


def test_home_and_cache_inside_an_app_bundle_write_nothing_there(pet, home, monkeypatch):
    app = home / "Applications" / "RedCrab.app" / "Contents" / "Resources" / "app"
    app.mkdir(parents=True)
    for n in ("state.json", "grow.json"):                              # even a save there is not taken
        (app / n).write_text("{}")
    tried = []
    monkeypatch.setattr(pet, "HERE", str(app))
    monkeypatch.setattr(pet, "writable", lambda d: tried.append(d) or True)
    assert pet.default_home() == (system.home_dir(), system.cache_dir())
    assert tried == []                                                 # its folder not even tried for writing
    assert sorted(os.listdir(str(app))) == ["grow.json", "state.json"]


# ---- start at login ----

def test_pet_command_in_and_outside_an_app_bundle():
    pet_in_app = "/Applications/RedCrab.app/Contents/Resources/app/clawd_pet.pyw"
    assert system.pet_command(pet_in_app, "/x/python3") == ["/Applications/RedCrab.app/Contents/MacOS/RedCrab"]
    from_source = "/src/red-crab/clawd_pet.pyw"
    assert system.pet_command(from_source, "/x/python3") == ["/x/python3", from_source]
    assert system.app_bundle("/A/RedCrab.app/Contents/Resources/python/Py.app/Contents/MacOS/x") == "/A/RedCrab.app"
    assert system.app_bundle("/A/RedCrab.app/Contents") == "/A/RedCrab.app"
    assert system.app_bundle("/src/my.app.d/clawd_pet.pyw") is None


def test_autostart_on_and_off_through_the_pet(pet, home):
    assert not pet.autostart_enabled()
    pet.set_autostart(True)
    assert pet.autostart_enabled()
    assert agent_args() == [PY, PET_PATH] == pet.autostart_command()
    assert system.launch_agent_path().startswith(str(home))

    system.set_autostart(True, ["/old/python3", "/old/clawd_pet.pyw"])  # the program moved: the tray points it here
    pet.Tray._refresh_autostart()
    assert agent_args() == [PY, PET_PATH]
    assert "open at login: entry updated to %s %s" % (PY, PET_PATH) in pet_log(pet)

    pet.set_autostart(False)
    assert not pet.autostart_enabled()
    assert not os.path.exists(system.launch_agent_path())


def test_autostart_never_points_into_app_translocation(pet, monkeypatch):
    moved = "/private/var/folders/xy/T/AppTranslocation/1234-ABCD/d/RedCrab.app/Contents/MacOS/RedCrab"
    monkeypatch.setattr(pet, "autostart_command", lambda: [moved])
    pet.set_autostart(True)
    assert not pet.autostart_enabled()
    assert "App Translocation" in pet_log(pet)


def test_autostart_menu_item_and_tray_tip_in_macos_words(pet, monkeypatch):
    monkeypatch.setattr(pet, "LANG", "zh")
    assert pet.autostart_label() == "登录时打开"
    monkeypatch.setattr(pet, "LANG", "en")
    assert pet.autostart_label() == "Open at Login"
    tray = pet.Tray.__new__(pet.Tray)
    tray.family = types.SimpleNamespace(grow=types.SimpleNamespace(level=1), hidden=set(), opts={"home": None})
    assert "click" not in tray._tip() and tray._tip().startswith("Clawd Lv.1")
    tray.family.hidden = {"user"}
    assert tray._tip().endswith("(hidden)")


def test_autostart_on_and_off_through_clawd_py(home, monkeypatch, capsys):
    clawd = load(CLAWD, "clawd_glue")
    assert clawd.autostart_mac(["on"]) == 0
    assert agent_args() == [clawd.PYTHON, clawd.PET]
    bundled = "/Applications/RedCrab.app/Contents/Resources/app/clawd_pet.pyw"
    monkeypatch.setattr(clawd, "PET", bundled)
    assert clawd.autostart_mac(["on"]) == 0
    assert agent_args() == ["/Applications/RedCrab.app/Contents/MacOS/RedCrab"]
    assert clawd.autostart_command() == "/Applications/RedCrab.app/Contents/MacOS/RedCrab"
    assert clawd.autostart_mac(["off"]) == 0
    assert not system.autostart_enabled()
    capsys.readouterr()


# ---- apps by pid ----

def dead_pid():
    p = subprocess.Popen([PY, "-I", "-c", "pass"])
    p.wait()
    return p.pid


def test_pid_helpers_with_this_process_and_a_dead_one():
    from clawd_mac import win32_loop
    win32_loop.app()                                     # this process an app (accessory: no Dock icon, no window)
    me = os.getpid()
    assert system.app_alive(me)
    bid = system.app_bundle_id(me)
    assert bid is None or isinstance(bid, str)
    gone = dead_pid()
    assert not system.app_alive(gone)
    assert system.app_bundle_id(gone) is None
    for nothing in (0, None, -1, "x"):
        assert not system.app_alive(nothing)
    front = system.frontmost_pid()
    assert isinstance(front, int) and front >= 0
    # Finder always runs, as a regular app; this process is not one (accessory), so its name finds nothing
    finder = system.find_app(["FINDER"])
    assert finder and system.app_bundle_id(finder) == "com.apple.finder"
    assert system.find_app([os.path.basename(PY)]) != me
    assert system.find_app(["no such app 9f3e"]) is None


def test_app_window_and_app_running_use_the_apps_names(pet, monkeypatch):
    asked = []
    monkeypatch.setattr(system, "find_app", lambda names: asked.append(list(names)) or CLAUDE)
    assert pet.app_window("claude") == CLAUDE
    assert pet.app_running("codex")
    assert pet.app_window("dsh") == CLAUDE
    assert asked == [["claude"], ["chatgpt", "codex"], ["deepseek harness"]]
    assert pet.app_window("https") is None


# ---- a click on a circle ----

class Titles(object):
    def __init__(self, kind, link):
        self.where, self.kind, self._link = {}, kind, link

    def claude_kind(self, session):
        return self.kind

    def link(self, session, agent, now):
        return self._link

    def open_now(self, session):
        return False


class Proc(object):
    """What subprocess.Popen gives the pets for osascript: done at once, with this output."""

    def __init__(self, out, rc):
        self.stdout, self.returncode = io.BytesIO(out.encode()), rc

    def poll(self):
        return self.returncode

    def kill(self):
        pass


class Desk(object):
    """The apps there are (APPS), what is activated and what is run, all patched."""

    def __init__(self, monkeypatch, front=0, claude_runs=True):
        self.activated, self.popen, self.opened = [], [], []
        self.out, self.opened_now = ("ok", 0), threading.Event()
        monkeypatch.setattr(system, "app_alive", lambda pid: pid in APPS)
        monkeypatch.setattr(system, "app_bundle_id", lambda pid: APPS.get(pid))
        monkeypatch.setattr(system, "activate_pid", lambda pid: self.activated.append(pid) or True)
        monkeypatch.setattr(system, "frontmost_pid", lambda: front)
        monkeypatch.setattr(system, "find_app", lambda names: CLAUDE if claude_runs and "claude" in names else None)
        monkeypatch.setattr(subprocess, "Popen", self.fake_popen)
        monkeypatch.setattr(subprocess, "run", self.fake_run)

    def fake_popen(self, cmd, **kw):
        self.popen.append((cmd, kw))
        return Proc(*self.out)

    def fake_run(self, cmd, **kw):
        self.opened.append((cmd, kw))
        self.opened_now.set()
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


def family(pet, where, kind=None, link=None, tty=""):
    fam = pet.Family.__new__(pet.Family)
    fam.opts = {"debug": True}
    fam.titles = Titles(kind, link)
    fam.talks = {SID: {"n": 1, "end": None, "seen": 0.0}}
    fam.talk_where, fam.talk_tab, fam.talk_entry = {SID: where}, {}, {}
    fam.talk_wt = {SID: tty} if tty else {}
    fam.link_last, fam.link_q = (None, -1e9), None
    fam.tab_job = fam.tab_next = fam.tab_click = fam.tab_shells = None
    fam.tab_refused = False
    return fam


@pytest.mark.parametrize("pid, script_has", [(TERM, ('application id "com.apple.Terminal"', "tabs of w")),
                                              (ITERM, ('application id "com.googlecode.iterm2"', "sessions of t"))])
def test_a_terminal_conversation_brings_its_app_and_chooses_its_tab(pet, monkeypatch, pid, script_has):
    desk = Desk(monkeypatch)
    fam = family(pet, (pid, "claude"), kind="cli", tty="ttys013")
    fam.talk_jump(SID, 1.0)
    assert desk.activated == [pid]
    (cmd, kw), = desk.popen
    assert cmd[0] == "/usr/bin/osascript" and cmd[1] == "-e" and cmd[3:] == ["/dev/ttys013"]
    assert all(s in cmd[2] for s in script_has) and "ttys013" not in cmd[2]
    assert kw.get("start_new_session") is True and "creationflags" not in kw
    fam.tab_done()
    assert fam.tab_job is None
    assert desk.activated == [pid]                          # the tab chosen: nothing more to bring
    assert "circle 1: tab selected" in pet_log(pet)


def test_no_such_tab_or_refused_falls_back_to_the_app(pet, monkeypatch):
    desk = Desk(monkeypatch, front=GHOSTTY)
    fam = family(pet, (TERM, "claude"), kind="cli", tty="ttys013")
    desk.out = ("gone", 0)
    fam.talk_jump(SID, 1.0)
    fam.tab_done()
    assert desk.activated == [TERM, TERM]
    assert "circle 1: tab not found: just its window" in pet_log(pet)
    desk.out = ("execution error: Not authorized to send Apple events to Terminal. (-1743)", 1)
    for i in range(2):
        fam.talk_jump(SID, 10.0 + i)
        fam.tab_done()
    assert desk.activated == [TERM] * 6
    assert pet_log(pet).count("Automation refused") == 1


def test_other_terminals_and_apps_are_brought_forward_whole(pet, monkeypatch):
    desk = Desk(monkeypatch)
    for pid in (GHOSTTY, VSCODE):
        family(pet, (pid, "claude"), kind="cli", tty="ttys013").talk_jump(SID, 1.0)
    assert desk.activated == [GHOSTTY, VSCODE] and desk.popen == []
    gone = family(pet, (4242, "claude"), kind="cli", tty="ttys013")     # its app is not there any more
    gone.talk_jump(SID, 1.0)
    assert desk.activated == [GHOSTTY, VSCODE]
    assert "its window is not known" in pet_log(pet)


def test_a_desktop_conversation_brings_its_app_and_opens_its_link(pet, monkeypatch):
    desk = Desk(monkeypatch)
    family(pet, (CLAUDE, "claude"), kind="desk", link=LINK).talk_jump(SID, 1.0)
    assert desk.activated == [CLAUDE]
    assert desk.opened_now.wait(WAIT)
    (cmd, kw), = desk.opened
    assert cmd == ["/usr/bin/open", LINK] and kw.get("start_new_session") is True


def test_a_claude_link_with_no_window_known_finds_the_app(pet, monkeypatch):
    desk = Desk(monkeypatch)
    fam = family(pet, (None, "claude"), kind="desk", link=LINK)
    fam.talk_jump(SID, 1.0)
    assert desk.activated == [CLAUDE] and fam.talk_where[SID] == (CLAUDE, "claude")
    assert desk.opened_now.wait(WAIT) and desk.opened[0][0] == ["/usr/bin/open", LINK]


def test_a_claude_link_with_the_app_not_running_is_opened(pet, monkeypatch):
    desk = Desk(monkeypatch, claude_runs=False)
    family(pet, (None, "claude"), kind="desk", link=LINK).talk_jump(SID, 1.0)
    assert desk.activated == []
    assert desk.opened_now.wait(WAIT) and desk.opened[0][0] == ["/usr/bin/open", LINK]


def test_places_kept_over_a_restart_only_for_the_same_app(pet, monkeypatch):
    Desk(monkeypatch)
    fam = family(pet, (TERM, "claude"), kind="cli", tty="ttys013")
    fam.talks = {}
    fam._places_save()
    with open(os.path.join(pet.HOME_DIR, "talks.json"), encoding="utf-8") as f:
        assert json.load(f)["where"][SID][:3] == [TERM, "claude", pet.TERMINAL_CLASS]
    again = family(pet, (None, ""))
    again.talks, again.talk_where, again.talk_wt = {}, {}, {}
    again._places_load()
    assert again.talk_where[SID] == (TERM, "claude") and again.talk_wt[SID] == "ttys013"
    monkeypatch.setitem(APPS, TERM, "com.example.other")                # that pid is another app's now
    again._places_load()
    assert again.talk_where[SID] == (None, "claude")


def test_tab_osascript_only_for_a_tab_terminal_and_a_device(pet):
    cmd = pet.tab_osascript("com.apple.Terminal", "ttys013")
    assert cmd[:2] == ["/usr/bin/osascript", "-e"] and cmd[3:] == ["/dev/ttys013"]
    assert pet.tab_osascript("com.googlecode.iterm2", "ttys2")[3:] == ["/dev/ttys2"]
    for bid, tty in (("com.mitchellh.ghostty", "ttys013"), (None, "ttys013"), ("com.apple.Terminal", ""),
                     ("com.apple.Terminal", "ttys013; beep"), ("com.apple.Terminal", "../disk0")):
        assert pet.tab_osascript(bid, tty) is None


# ---- the re-render's process group ----

def test_a_render_runs_niced_in_its_own_group_and_is_ended_with_it(pet, tmp_path, monkeypatch):
    monkeypatch.setattr(pet, "RENDER_TERM_WAIT", 0.5)
    stubborn = ("import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('up', flush=True); "
                "time.sleep(60)")
    with open(str(tmp_path / "render.log"), "wb") as logf:
        proc = pet.start_render_mac([PY, "-I", "-c", stubborn], logf, dict(os.environ))
        try:
            end = time.time() + WAIT
            log = tmp_path / "render.log"
            while b"up" not in log.read_bytes() and time.time() < end:      # the child's own line, past nice's exec
                time.sleep(0.02)
            said = log.read_bytes().decode("utf-8", "replace")
            assert os.getpgid(proc.pid) == proc.pid != os.getpgid(0)
            nice = min(os.getpriority(os.PRIO_PROCESS, 0) + 10, 20)
            assert os.getpriority(os.PRIO_PROCESS, proc.pid) == nice, "render.log: %r" % said
            t0 = time.time()
            pet.stop_render_mac(proc)                       # SIGTERM ignored: SIGKILL after RENDER_TERM_WAIT
            assert proc.poll() == -signal.SIGKILL
            assert time.time() - t0 < 3.0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


# ---- clawd_scale.py ----

def frame_set(d, frames=200, side=256):
    os.makedirs(d)
    parts = []
    for i in range(frames):                                  # each frame its own (repeats are scaled once)
        z = zlib.compress(bytes((i, 255 - i, 7, 255)) * (side * side), 1)
        parts += [struct.pack("<I", len(z)), z]
    with open(os.path.join(d, "idle.frames"), "wb") as f:
        f.write(b"".join(parts))
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump({"version": 2, "width": side, "height": side, "base_body_px": 100,
                   "actions": {"idle": {"file": "idle.frames", "count": frames}}}, f)
    return d


# a short-lived parent: starts clawd_scale.py, says its pid, and goes as soon as the scaling has begun (OUT.tmp)
PARENT = r"""
import os, subprocess, sys, time
scale, src, out, log = sys.argv[1:5]
with open(log, "wb") as f:
    p = subprocess.Popen([sys.executable, "-I", scale, "--src", src, "--body-px", "50", "--out", out],
                         stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT)
print(p.pid, flush=True)
end = time.time() + 30
while not os.path.isdir(out + ".tmp") and p.poll() is None and time.time() < end:
    time.sleep(0.002)
"""


def test_clawd_scale_ends_when_the_pet_that_started_it_goes(tmp_path):
    # big enough to take about a second when nobody stops it: its parent is gone long before it could be done
    src = frame_set(str(tmp_path / "frames"), frames=240, side=1024)
    out, log = str(tmp_path / "frames_custom"), str(tmp_path / "render.log")
    r = subprocess.run([PY, "-I", "-c", PARENT, SCALE, src, out, log], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    pid = int(r.stdout.strip())
    end = time.time() + GONE_WAIT
    try:
        while time.time() < end:
            os.kill(pid, 0)
            time.sleep(0.05)
        pytest.fail("clawd_scale.py still runs %.0f s after its parent went" % GONE_WAIT)
    except ProcessLookupError:
        pass
    finally:
        try:
            os.kill(pid, signal.SIGKILL)                     # (only if the test failed: it is this test's own)
        except ProcessLookupError:
            pass
    with open(log, encoding="utf-8") as f:
        text = f.read()
    assert "is gone: stopped after" in text and "(pid 1)" not in text, text    # its parent was there at its start
    assert not os.path.exists(os.path.join(out, "manifest.json"))


def test_clawd_scale_with_its_parent_there_scales_the_set(tmp_path):
    src, out = frame_set(str(tmp_path / "frames"), frames=8, side=64), str(tmp_path / "frames_custom")
    r = subprocess.run([PY, "-I", SCALE, "--src", src, "--body-px", "50", "--out", out], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    with open(os.path.join(out, "manifest.json")) as f:
        m = json.load(f)
    assert (m["width"], m["height"], m["base_body_px"]) == (32, 32, 50)
