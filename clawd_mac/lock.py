# -*- coding: utf-8 -*-
"""Named single-instance locks for macOS: what a named mutex (CreateMutexW / OpenMutexW) is on Windows.

A lock is a file under ~/Library/Caches/Clawd/locks, held with flock(2) by the process that has it.  The system
lets go of it when that process ends, however it ends (a crash, kill -9), so a lock is never left behind.  The
holder writes its pid into the file, so a second copy can bring the first one forward.  Standard library only.
"""
import errno
import fcntl
import os
import re

_held = {}           # name -> the open file that holds it (kept open: closing it lets go)


def lock_dir():
    return os.path.join(os.path.expanduser("~"), "Library", "Caches", "Clawd", "locks")


def path_of(name):
    """The file for the lock `name` (a mutex name such as Local\\ClawdDesktopPet: anything not safe in a file name
    becomes _)."""
    return os.path.join(lock_dir(), re.sub(r"[^A-Za-z0-9._-]", "_", name) + ".lock")


def acquire(name):
    """Take the lock `name` for this process: True if it has it now (or had it already), False if another
    process holds it."""
    if name in _held:
        return True
    os.makedirs(lock_dir(), exist_ok=True)
    f = open(path_of(name), "a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        f.close()
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
            return False
        raise
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    _held[name] = f
    return True


def release(name):
    """Let go of the lock `name` if this process holds it."""
    f = _held.pop(name, None)
    if f is not None:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


def held(name):
    """True if any process holds the lock `name` (this one included): what OpenMutexW finding the mutex means."""
    if name in _held:
        return True
    path = path_of(name)
    if not os.path.exists(path):
        return False
    try:
        f = open(path, "r")
    except OSError:
        return False
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        return True
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        f.close()


def owner(name):
    """The pid of the process that holds the lock `name`, or None (not held, or held by this process)."""
    if name in _held or not held(name):
        return None
    try:
        with open(path_of(name), "r") as f:
            pid = int(f.read().strip() or 0)
    except (OSError, ValueError):
        return None
    return pid or None
