# -*- coding: utf-8 -*-
"""clawd_mac.system: the saves' places, the UI language, the LaunchAgent, the pet's processes, App Translocation.
Every path under a temporary HOME: the real LaunchAgents folder and saves are never touched."""
import os
import plistlib
import subprocess
import sys
import textwrap
import time

import pytest

from clawd_mac import system

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")

FIND_WAIT = 5.0


@pytest.fixture(autouse=True)
def own_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(system, "_lang", None)
    return tmp_path


def test_home_and_cache_dirs(own_home):
    assert system.home_dir() == os.path.join(str(own_home), "Library", "Application Support", "Clawd")
    assert system.cache_dir() == os.path.join(str(own_home), "Library", "Caches", "Clawd")


DEFAULTS_ZH = '(\n    "zh-Hans-CN",\n    "en-US"\n)\n'
DEFAULTS_EN = '(\n    "en-US",\n    "zh-Hans-CN"\n)\n'


@pytest.mark.parametrize("out, want", [(DEFAULTS_ZH, "zh"), (DEFAULTS_EN, "en"), ('(\n    en,\n    zh\n)\n', "en")])
def test_ui_lang_follows_the_first_preferred_language(monkeypatch, out, want):
    monkeypatch.setattr(system, "_defaults_languages", lambda: out)
    assert system.ui_lang() == want


@pytest.mark.parametrize("env, want", [({"LANG": "zh_CN.UTF-8"}, "zh"), ({"LANG": "en_US.UTF-8"}, "en"),
                                       ({"LC_ALL": "zh_TW.UTF-8", "LANG": "en_US.UTF-8"}, "zh"), ({}, "en")])
def test_ui_lang_without_defaults_reads_the_environment(monkeypatch, env, want):
    monkeypatch.setattr(system, "_defaults_languages", lambda: None)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert system.ui_lang() == want


def test_ui_lang_is_read_once_a_process(monkeypatch):
    calls = []
    monkeypatch.setattr(system, "_defaults_languages", lambda: calls.append(1) or DEFAULTS_ZH)
    assert system.ui_lang() == "zh"
    assert system.ui_lang() == "zh"
    assert len(calls) == 1


def test_first_language_of_nothing_is_empty():
    assert system.first_language(None) == ""
    assert system.first_language("(\n)\n") == ""


def test_launch_agent_path_is_in_the_users_launch_agents(own_home):
    want = os.path.join(str(own_home), "Library", "LaunchAgents", "io.github.bigbrother168.redcrab.plist")
    assert system.launch_agent_path() == want


def test_set_autostart_on_and_off(own_home):
    args = ["/opt/py/bin/python3", "/Applications/RedCrab.app/Contents/Resources/clawd_pet.pyw"]
    assert not system.autostart_enabled()
    assert system.autostart_command() is None

    assert system.set_autostart(True, args)
    with open(system.launch_agent_path(), "rb") as f:
        plist = plistlib.load(f)
    assert plist == {"Label": system.LAUNCH_AGENT_LABEL, "ProgramArguments": args, "RunAtLoad": True,
                     "ProcessType": "Interactive", "LimitLoadToSessionType": "Aqua"}
    assert system.autostart_command() == args
    assert system.autostart_enabled()

    assert system.set_autostart(False)
    assert not os.path.exists(system.launch_agent_path())
    assert not system.autostart_enabled()
    assert system.set_autostart(False)                 # already off: still fine


def test_set_autostart_on_needs_a_command():
    assert not system.set_autostart(True, [])
    assert not os.path.exists(system.launch_agent_path())


def test_a_broken_launch_agent_reads_as_none():
    os.makedirs(system.launch_agents_dir())
    with open(system.launch_agent_path(), "w") as f:
        f.write("not a plist")
    assert system.autostart_command() is None


def test_set_autostart_says_false_when_it_cannot_write(own_home):
    os.makedirs(os.path.join(str(own_home), "Library"))
    with open(system.launch_agents_dir(), "w") as f:     # a file where the folder should be
        f.write("")
    assert not system.set_autostart(True, ["/bin/true"])


def start_script(path, body):
    """A child running the script at path (as the pet runs: python <script>), once it says it is ready."""
    with open(path, "w") as f:
        f.write(textwrap.dedent(body))
    p = subprocess.Popen([sys.executable, str(path)], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "ready"
    return p


def found(script):
    end = time.monotonic() + FIND_WAIT
    while time.monotonic() < end:
        pids = system.pet_processes(str(script))
        if pids:
            return pids
        time.sleep(0.1)
    return []


SLEEPER = """
    import time
    print("ready", flush=True)
    time.sleep(60)
"""
STUBBORN = """
    import signal, time
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("ready", flush=True)
    time.sleep(60)
"""


def test_pet_processes_finds_the_script_and_terminate_ends_it(tmp_path):
    pet = tmp_path / "clawd_pet.pyw"
    p = start_script(pet, SLEEPER)
    try:
        pids = found(pet)
        assert pids == [p.pid]
        assert os.getpid() not in pids
        assert system.pet_processes(str(tmp_path / "clawd_album.pyw")) == []
        assert system.terminate(p.pid)
        assert p.poll() is not None
        assert system.pet_processes(str(pet)) == []
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()


def test_terminate_kills_what_does_not_end_by_itself(tmp_path):
    p = start_script(tmp_path / "clawd_pet.pyw", STUBBORN)
    try:
        t0 = time.monotonic()
        assert system.terminate(p.pid, timeout=0.3)
        assert time.monotonic() - t0 < 0.3 + system.KILL_WAIT + 1.0
        assert p.poll() is not None
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()


def ended_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_terminate_of_a_process_already_gone_is_true():
    assert system.terminate(ended_pid())


def test_activate_pid_of_no_app_is_false():
    assert system.activate_pid(ended_pid()) is False
    assert system.activate_pid("not a pid") is False


@pytest.mark.parametrize("path, want", [
    ("/private/var/folders/x1/abc/T/AppTranslocation/5D3C-11AA/d/RedCrab.app/Contents/Resources", True),
    ("/private/var/folders/x1/abc/T/AppTranslocation", True),
    ("/Applications/RedCrab.app/Contents/Resources", False),
    ("/Users/me/Downloads/MyAppTranslocationNotes/clawd", False),
])
def test_in_translocation(path, want):
    assert system.in_translocation(path) is want
