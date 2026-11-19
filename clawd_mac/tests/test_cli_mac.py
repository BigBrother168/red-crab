# -*- coding: utf-8 -*-
"""clawd.py and clawd_hook.py on macOS: hooks on/off for Claude Code, the hook it installs writing its lines, start at
login, App Translocation.  The agents' settings, the saves and LaunchAgents all live under a temporary HOME."""
import importlib.util
import json
import os
import plistlib
import re
import subprocess
import sys

import pytest

from clawd_mac import system

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLAWD = os.path.join(ROOT, "clawd.py")
HOOK = os.path.join(ROOT, "clawd_hook.py")
PY = os.path.abspath(sys.executable)
MARK = "#clawd-event"
SID = "1a2b3c4d"
PROMPT = {"session_id": SID + "-5e6f-4a7b-8c9d-0e1f2a3b4c5d", "hook_event_name": "UserPromptSubmit",
          "prompt": "hello", "cwd": "/tmp"}
AT_LINE = re.compile(r"^at %s (\d+) claude cli (-|[a-z0-9]{1,16})$" % SID)
RUN_TIMEOUT = 30


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A temporary HOME with each agent's settings folder in it; no CLAWD_HOME (the macOS default is under HOME)."""
    if any(os.path.exists(os.path.join(ROOT, n)) for n in ("state.json", "grow.json")):
        pytest.skip("a save beside the program would be the pets' home")
    env = {"HOME": str(tmp_path), "CLAUDE_CONFIG_DIR": str(tmp_path / ".claude"),
           "CODEX_HOME": str(tmp_path / ".codex"), "DSH_HOME": str(tmp_path / ".dsh"), "CLAUDE_CODE_ENTRYPOINT": "cli"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("CLAWD_HOME", raising=False)
    return tmp_path


def settings_path(home):
    return os.path.join(str(home), ".claude", "settings.json")


def clawd(*args):
    """clawd.py run as the agents and the SessionStart hook run it: python -I -S."""
    r = subprocess.run([PY, "-I", "-S", CLAWD] + list(args), capture_output=True, text=True, timeout=RUN_TIMEOUT)
    return r.returncode, r.stdout + r.stderr


def ours(settings):
    return [(ev, h) for ev, groups in settings.get("hooks", {}).items() for g in groups for h in g["hooks"]
            if isinstance(h.get("args"), list) and h["args"][-1:] == [MARK]]


def load_clawd():
    """clawd.py as a fresh module, its places read from the environment now."""
    spec = importlib.util.spec_from_file_location("clawd_under_test", CLAWD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hooks_on_writes_exec_form_entries_for_this_python_and_hook(home):
    user = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say done"}]}]}, "theme": "dark"}
    os.makedirs(os.path.dirname(settings_path(home)))
    with open(settings_path(home), "w") as f:
        json.dump(user, f)

    rc, out = clawd("hooks", "on")
    assert rc == 0, out
    with open(settings_path(home)) as f:
        settings = json.load(f)
    entries = ours(settings)
    assert len(entries) == 17
    for ev, h in entries:
        assert h["command"] == PY
        assert h["args"][:3] == ["-I", "-S", ROOT + "/clawd_hook.py"]
        assert h["async"] is True
        assert ("--at" in h["args"]) == (ev in ("SessionStart", "UserPromptSubmit"))
    assert {"type": "command", "command": "say done"} in [h for g in settings["hooks"]["Stop"] for h in g["hooks"]]
    assert os.path.isfile(settings_path(home) + ".clawd-bak")

    rc, out = clawd("hooks", "off")
    assert rc == 0, out
    with open(settings_path(home)) as f:
        settings = json.load(f)
    assert ours(settings) == []
    assert settings == user


def test_the_installed_hook_writes_its_lines_to_the_macos_home(home):
    rc, out = clawd("hooks", "on")
    assert rc == 0, out
    with open(settings_path(home)) as f:
        settings = json.load(f)
    h = next(h for ev, h in ours(settings) if ev == "UserPromptSubmit")

    r = subprocess.run([h["command"]] + h["args"], input=json.dumps(PROMPT).encode(), capture_output=True,
                       timeout=RUN_TIMEOUT)
    assert r.returncode == 0, r.stderr

    event = os.path.join(str(home), "Library", "Application Support", "Clawd", "event")
    with open(event) as f:
        lines = f.read().splitlines()
    assert lines[0] == "listen " + SID
    assert len(lines) == 2 and AT_LINE.match(lines[1]), lines


def test_hook_where_fields_on_macos(home, monkeypatch):
    spec = importlib.util.spec_from_file_location("clawd_hook_under_test", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    monkeypatch.setattr(hook, "_where", [(4321, "ttys003")])
    assert hook.where_fields() == "cli ttys003"
    assert hook.window() == 4321
    monkeypatch.setattr(hook, "_where", [(0, "")])
    assert hook.where_fields() == "cli -"
    assert hook.HOME == os.path.join(str(home), "Library", "Application Support", "Clawd")


def test_hook_walk_finds_a_number_and_a_tty_or_none():
    spec = importlib.util.spec_from_file_location("clawd_hook_walk", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    app, tab = hook.walk_mac()
    assert isinstance(app, int) and app >= 0
    assert re.match(r"^[a-z0-9]{0,16}$", tab)


@pytest.mark.parametrize("path, want", [
    ("/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal", True),
    ("/Applications/Claude.app/Contents/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper", False),
    ("/Users/me/.local/share/claude/versions/2.1.0", False),
    ("/bin/zsh", False),
])
def test_hook_is_app(path, want):
    spec = importlib.util.spec_from_file_location("clawd_hook_app", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    assert hook.is_app(path) is want


def test_autostart_on_and_off_writes_a_launch_agent(home):
    rc, out = clawd("autostart", "on")
    assert rc == 0, out
    path = os.path.join(str(home), "Library", "LaunchAgents", system.LAUNCH_AGENT_LABEL + ".plist")
    with open(path, "rb") as f:
        assert plistlib.load(f)["ProgramArguments"] == [PY, os.path.join(ROOT, "clawd_pet.pyw")]
    rc, out = clawd("autostart", "off")
    assert rc == 0, out
    assert not os.path.exists(path)


def test_the_cli_uses_the_macos_places(home):
    cl = load_clawd()
    assert cl.HOME == os.path.join(str(home), "Library", "Application Support", "Clawd")
    assert cl.PYTHON == cl.PYTHONW == PY
    assert not cl.is_running()


@pytest.mark.parametrize("args", [["hooks", "on"], ["hooks", "on", "codex"], ["autostart", "on"], ["hooks", "refresh"]])
def test_refuses_to_point_at_a_translocated_copy(home, monkeypatch, capsys, args):
    cl = load_clawd()
    monkeypatch.setattr(cl.macsys, "in_translocation", lambda path: True)
    assert cl.main(args) == 1
    assert "App Translocation" in capsys.readouterr().out
    assert not os.path.exists(settings_path(home))
    assert not os.path.exists(os.path.join(str(home), ".codex", "hooks.json"))
    assert not os.path.exists(system.launch_agent_path())


def test_hooks_off_still_runs_when_translocated(home, monkeypatch):
    cl = load_clawd()
    monkeypatch.setattr(cl.macsys, "in_translocation", lambda path: True)
    assert cl.main(["hooks", "off"]) == 0


def test_help_prints_the_commands(home):
    rc, out = clawd("--help")
    assert rc == 2
    assert "hooks" in out and "autostart" in out
