# -*- coding: utf-8 -*-
"""What else differs on macOS, for clawd.py, the pets, the album and the connect window: where the saves live, the UI
language, starting at login (a LaunchAgent: what the Run key is on Windows), finding and stopping the pet's processes,
the apps a conversation runs in (by pid: what a window handle is to the pets on Windows), bringing an app forward.

Standard library only at import (AppKit only inside the functions that look at apps).  clawd_hook.py does not import
this: it runs on every agent event and keeps its own two-line copy of home_dir.
"""
import os
import plistlib
import re
import signal
import subprocess
import time

APP_DIR_NAME = "Clawd"
LAUNCH_AGENT_LABEL = "io.github.bigbrother168.redcrab"
APP_EXECUTABLE = "RedCrab"                                # RedCrab.app/Contents/MacOS/RedCrab (installer/build_mac.py)
IN_BUNDLE = ".app" + os.sep + "Contents" + os.sep         # in a path: inside an app bundle
TRANSLOCATION = os.sep + "AppTranslocation" + os.sep     # where Gatekeeper runs an app not yet moved out of Downloads
GONE_POLL = 0.05                                          # how often terminate looks whether the process is gone
KILL_WAIT = 1.0                                           # after SIGKILL: how long it may take to go
PS_TIMEOUT = 10.0
DEFAULTS_TIMEOUT = 3.0

_lang = None


def _user_dir(*parts):
    return os.path.join(os.path.expanduser("~"), "Library", *parts)


def home_dir():
    """What the pets keep (event, state, saves): what %APPDATA%\\Clawd is on Windows."""
    return _user_dir("Application Support", APP_DIR_NAME)


def cache_dir():
    """What can be made again (the frame sets scaled to other sizes): what %LOCALAPPDATA%\\Clawd is on Windows."""
    return _user_dir("Caches", APP_DIR_NAME)


# ---- the UI language ----

def _defaults_languages():
    """The output of `defaults read -g AppleLanguages` (the user's languages, in order), or None."""
    try:
        r = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True,
                           timeout=DEFAULTS_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def first_language(text):
    """The first entry of an array as `defaults` prints it ('(\\n    "zh-Hans-CN",\\n    en\\n)'), or ""."""
    for line in (text or "").splitlines():
        item = line.strip().rstrip(",").strip().strip('"')
        if item and item not in ("(", ")"):
            return item
    return ""


def ui_lang():
    """'zh' if the user's first preferred language is Chinese, else 'en' (as GetUserDefaultUILanguage decides it on
    Windows).  From the system's language list; without one (no `defaults`), from LC_ALL / LANG.  Once a process."""
    global _lang
    if _lang is None:
        first = first_language(_defaults_languages())
        if not first:
            first = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
        _lang = "zh" if first.lower().startswith("zh") else "en"
    return _lang


# ---- start at login: a LaunchAgent ----

def launch_agents_dir():
    return _user_dir("LaunchAgents")


def launch_agent_path():
    return os.path.join(launch_agents_dir(), LAUNCH_AGENT_LABEL + ".plist")


def autostart_command():
    """-> the ProgramArguments our LaunchAgent starts (a list), or None (there is none, or it cannot be read)."""
    try:
        with open(launch_agent_path(), "rb") as f:
            d = plistlib.load(f)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    args = d.get("ProgramArguments") if isinstance(d, dict) else None
    if not (isinstance(args, list) and args and all(isinstance(a, str) for a in args)):
        return None
    return list(args)


def autostart_enabled():
    return autostart_command() is not None


def set_autostart(on, program_args=None):
    """Start program_args at each login (on) or not.  Like the Run key on Windows it takes effect at the next login:
    nothing is loaded into launchd now.  -> True if it is so now, False if the file could not be written or removed."""
    path = launch_agent_path()
    if not on:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True
    if not program_args:
        return False
    plist = {"Label": LAUNCH_AGENT_LABEL, "ProgramArguments": [str(a) for a in program_args], "RunAtLoad": True,
             "ProcessType": "Interactive", "LimitLoadToSessionType": "Aqua"}
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "wb") as f:
            plistlib.dump(plist, f)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    return True


def app_bundle(path):
    """The app bundle path is inside of (the outermost one: /Applications/RedCrab.app), or None."""
    p = os.path.abspath(path) + os.sep
    i = p.find(IN_BUNDLE)
    return p[:i + len(".app")] if i >= 0 else None


def pet_command(pet_path, python):
    """What starts the pet at login (the LaunchAgent's ProgramArguments): RedCrab.app's own launcher when the pet is
    the app's (its Python is inside it, and the login item is the app), else python with the script."""
    bundle = app_bundle(pet_path)
    if bundle:
        return [os.path.join(bundle, "Contents", "MacOS", APP_EXECUTABLE)]
    return [python, pet_path]


# ---- the pet's processes ----

def _runs(command, paths):
    """Does this command line (as ps shows it: the arguments joined by spaces) have one of paths as an argument?"""
    return any(re.search(r"(?:^|\s)" + re.escape(p) + r"(?:\s|$)", command) for p in paths)


def pet_processes(script_path):
    """-> the pids of the processes whose command line runs script_path (never this one), from one ps call; None if
    ps could not be run."""
    paths = {os.path.abspath(script_path), os.path.realpath(script_path)}
    try:
        r = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True,
                           timeout=PS_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    me, pids = os.getpid(), []
    for line in r.stdout.splitlines():
        pid, _, command = line.strip().partition(" ")
        if pid.isdigit() and int(pid) != me and _runs(command.strip(), paths):
            pids.append(int(pid))
    return pids


def _gone(pid):
    """Has pid ended?  A child of ours that ended is reaped here (else it stays a zombie, which kill(0) still finds)."""
    try:
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return True
    except OSError:
        pass                                   # not a child of ours
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _wait_gone(pid, timeout):
    end = time.monotonic() + timeout
    while True:
        if _gone(pid):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(GONE_POLL)


def terminate(pid, timeout=3.0):
    """Ask pid to end (SIGTERM), and end it (SIGKILL) if it has not after timeout seconds.  -> True if it is gone
    (or was already), False if it could not be ended (another user's, say)."""
    for sig, wait in ((signal.SIGTERM, timeout), (signal.SIGKILL, KILL_WAIT)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        if _wait_gone(pid, wait):
            return True
    return False


# ---- apps, by pid: where a conversation is (clawd_hook.py's "at" line says the pid of the app it runs in) ----

def _app(pid):
    """The NSRunningApplication of pid, running (not terminated), or None."""
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    import AppKit
    app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    return None if app is None or app.isTerminated() else app


def app_alive(pid):
    """Is pid an app that runs?  What IsWindow is for a conversation's window on Windows."""
    try:
        return _app(pid) is not None
    except Exception:
        return False


def app_bundle_id(pid):
    """The bundle id of the app with this pid ("com.apple.Terminal"), or None (gone, or none)."""
    try:
        app = _app(pid)
        bid = app.bundleIdentifier() if app is not None else None
    except Exception:
        return None
    return str(bid) if bid else None


def frontmost_pid():
    """The pid of the app in front (the one that has the menu bar), or 0."""
    try:
        import AppKit
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        return int(app.processIdentifier()) if app is not None else 0
    except Exception:
        return 0


def find_app(names):
    """-> the pid of a running regular app (one in the Dock) whose executable or shown name is one of names (case does
    not matter: "claude" finds Claude.app), or None.  A command-line program of that name is not an app: never taken."""
    want = set(n.lower() for n in names)
    try:
        import AppKit
        regular = AppKit.NSApplicationActivationPolicyRegular
        for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            if app.isTerminated() or app.activationPolicy() != regular:
                continue
            url = app.executableURL()
            exe = os.path.basename(str(url.path())) if url is not None else ""
            if exe.lower() in want or str(app.localizedName() or "").lower() in want:
                return int(app.processIdentifier())
    except Exception:
        return None
    return None


def activate_pid(pid):
    """Bring the app with this pid to the front, all its windows.  -> False if it is not an app or it failed."""
    try:
        import AppKit
        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if app is None:
            return False
        opts = AppKit.NSApplicationActivateAllWindows | AppKit.NSApplicationActivateIgnoringOtherApps
        return bool(app.activateWithOptions_(opts))
    except Exception:
        return False


def in_translocation(path):
    """Is path inside an App Translocation mount?  Gatekeeper runs an app downloaded and not yet moved from a random
    read-only place that is gone at the next start: nothing lasting (a hook, a LaunchAgent) may point there."""
    return TRANSLOCATION in os.path.abspath(path) + os.sep
