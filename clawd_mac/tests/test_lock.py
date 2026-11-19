# -*- coding: utf-8 -*-
"""clawd_mac.lock: one holder at a time, let go when the holder ends."""
import os
import subprocess
import sys
import textwrap

import pytest

from clawd_mac import lock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def own_lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "lock_dir", lambda: str(tmp_path))
    yield
    for name in list(lock._held):
        lock.release(name)


def holder(tmp_path):
    """A child process that takes the lock "Local\\Test" and waits for a line on stdin."""
    code = textwrap.dedent("""
        import sys
        sys.path.insert(0, %r)
        from clawd_mac import lock
        lock.lock_dir = lambda: %r
        print("got" if lock.acquire("Local\\\\Test") else "busy", flush=True)
        sys.stdin.readline()
    """ % (ROOT, str(tmp_path)))
    p = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    return p, p.stdout.readline().strip()


def test_path_of_makes_mutex_names_safe():
    assert os.path.basename(lock.path_of("Local\\ClawdDesktopPet")) == "Local_ClawdDesktopPet.lock"


def test_acquire_twice_in_one_process_is_fine():
    assert lock.acquire("Local\\Test")
    assert lock.acquire("Local\\Test")
    assert lock.held("Local\\Test")
    assert lock.owner("Local\\Test") is None          # this process: no other one to bring forward


def test_second_process_is_refused_and_sees_the_owner(tmp_path):
    assert lock.acquire("Local\\Test")
    p, said = holder(tmp_path)
    try:
        assert said == "busy"
    finally:
        p.communicate("\n")


def test_lock_is_let_go_when_the_holder_ends(tmp_path):
    p, said = holder(tmp_path)
    try:
        assert said == "got"
        assert lock.held("Local\\Test")
        assert lock.owner("Local\\Test") == p.pid
        assert not lock.acquire("Local\\Test")
    finally:
        p.communicate("\n")
    assert not lock.held("Local\\Test")
    assert lock.acquire("Local\\Test")


def test_release_lets_others_in():
    assert lock.acquire("Local\\Test")
    lock.release("Local\\Test")
    assert not lock.held("Local\\Test")


def test_never_taken_is_not_held():
    assert not lock.held("Local\\Nobody")
    assert lock.owner("Local\\Nobody") is None
