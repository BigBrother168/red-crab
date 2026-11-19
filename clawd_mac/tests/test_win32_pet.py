# -*- coding: utf-8 -*-
"""clawd_pet.pyw itself on clawd_mac.win32, in this process: main() runs its message loop while NSTimers hand its
window synthetic NSEvents (nothing is posted to the system): a drag moves it, a right-click opens its menu (once
closed, once with an item chosen that then acts), Control+wheel makes it bigger, and `quit` in the event file ends
it with 0."""
import ctypes
import importlib.machinery
import importlib.util
import json
import os
import traceback

import pytest
from AppKit import NSRunLoop, NSRunLoopCommonModes, NSTimer

from clawd_mac import lock
from clawd_mac import win32
from clawd_mac import win32_loop as loop
from clawd_mac import win32_menu as menu
from clawd_mac import win32_synthetic as synth
from clawd_mac import win32_window as window

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PET_PATH = os.path.join(ROOT, "clawd_pet.pyw")
FRAMES = os.environ.get("CLAWD_TEST_FRAMES", os.path.join(ROOT, "frames"))
DRAG = (-400, -300)         # px the drag takes it (far from every edge it could snap to)
DRAG_STEPS = 6
STEP_SECS = 0.08
STILL_SECS = 0.25           # before letting go: a drop, not a throw (the pet's THROW_STALE_SECS is 0.08)
WHEEL_LINES = 12            # 1.1 ** 12 > 3: one notch burst to the largest size, which frames_hi has as it is
MENU_SECS = 0.4             # the menu is up this long before a timer closes it
GIVE_UP_SECS = 90.0

win32.install()


def later(secs, fn, keep):
    def fire(timer):                                  # a void block: what fn returns is dropped
        fn()

    t = NSTimer.timerWithTimeInterval_repeats_block_(secs, False, fire)
    NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
    keep.append(t)
    return t


def gdiplus_there():
    try:
        return importlib.util.find_spec("clawd_mac.gdiplus") is not None
    except ImportError:
        return False


def tracebacks(text):
    """The ERROR blocks of pet.log, each as one string."""
    blocks, cur = [], None
    for line in text.splitlines():
        if " ERROR in " in line:
            cur = [line]
            blocks.append(cur)
        elif cur is not None and not line[:1].isdigit():   # its lines, up to the next log line (a date)
            cur.append(line)
        else:
            cur = None
    return ["\n".join(b) for b in blocks]


class Run(object):
    """The steps, one NSTimer after another; a step that fails writes `quit` so main() ends anyway."""

    def __init__(self, mod, home):
        self.mod, self.home = mod, home
        self.timers, self.errors, self.seen = [], [], {}
        self.steps = self.script()

    def state(self):
        with open(os.path.join(self.home, "state.json"), encoding="utf-8") as f:
            return json.load(f)

    def event(self, line):
        with open(os.path.join(self.home, "event"), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def next(self):
        try:
            wait = next(self.steps)
        except StopIteration:
            return
        except Exception:
            self.errors.append(traceback.format_exc())
            self.event("quit")
            return
        later(wait, self.next, self.timers)

    def give_up(self):
        self.errors.append("main() still running after %d s" % GIVE_UP_SECS)
        loop.PostQuitMessage(0)

    def spot(self, hwnd):
        """A screen px over an opaque pixel of the window, the one nearest its middle."""
        w, h, raw = window.presented(hwnd)
        r = self.mod.RECT()
        self.mod.GetWindowRect(hwnd, ctypes.byref(r))
        best = min((abs(x - w // 2) + abs(y - h // 2), x, y) for y in range(0, h, 2) for x in range(0, w, 2)
                   if raw[(y * w + x) * 4 + 3] > 200)
        return r.left + best[1], r.top + best[2]

    def menu_closed(self):
        ns = menu.tracking()
        self.seen["menu"] = [str(it.title()) for it in ns.itemArray()] if ns is not None else None
        if ns is not None:
            ns.cancelTracking()

    def menu_language(self):
        """Choose the language not in use from 语言 / Language."""
        ns = menu.tracking()
        langs = [it.submenu() for it in ns.itemArray() if it.submenu() is not None and
                 "English" in [str(s.title()) for s in it.submenu().itemArray()]][0]
        i = [int(it.state()) for it in langs.itemArray()].index(0)
        self.seen["lang"] = str(langs.itemArray()[i].title())
        langs.performActionForItemAtIndex_(i)
        ns.cancelTracking()

    def script(self):
        mod = self.mod
        for _ in range(100):
            pets = window.find_windows(title="Clawd")
            if pets and window.presented(pets[0]) and os.path.exists(os.path.join(self.home, "state.json")):
                break
            yield 0.1
        hwnd, = window.find_windows(title="Clawd")
        yield 1.0                                # its start settles
        # a drag, and a drop
        self.seen["before"] = self.state()
        x, y = self.spot(hwnd)
        r0 = mod.RECT()
        mod.GetWindowRect(hwnd, ctypes.byref(r0))
        synth.mouse(hwnd, "left_down", x, y)
        for i in range(1, DRAG_STEPS + 1):
            yield STEP_SECS
            synth.mouse(hwnd, "left_drag", x + DRAG[0] * i // DRAG_STEPS, y + DRAG[1] * i // DRAG_STEPS)
        yield STILL_SECS
        synth.mouse(hwnd, "left_up", x + DRAG[0], y + DRAG[1])
        r1 = mod.RECT()
        mod.GetWindowRect(hwnd, ctypes.byref(r1))
        self.seen["moved"] = (r1.left - r0.left, r1.top - r0.top)
        yield 0.5
        self.seen["dropped"] = self.state()
        # its menu, closed without a choice
        x, y = self.spot(hwnd)
        later(MENU_SECS, self.menu_closed, self.timers)
        synth.mouse(hwnd, "right_down", x, y)
        synth.mouse(hwnd, "right_up", x, y)      # TrackPopupMenu: back once the timer closed it
        yield 0.3
        # its menu again: the other language
        self.seen["lang_before"] = mod.LANG
        later(MENU_SECS, self.menu_language, self.timers)
        synth.mouse(hwnd, "right_down", x, y)
        synth.mouse(hwnd, "right_up", x, y)
        yield 0.3
        self.seen["lang_after"] = mod.LANG
        self.seen["lang_state"] = self.state().get("lang", "zh")
        # Control + wheel away from you: bigger
        x, y = self.spot(hwnd)
        panel, ev = synth.scroll_event(hwnd, x, y, WHEEL_LINES, flags=synth.CONTROL)
        if ev.isDirectionInvertedFromDevice():
            panel, ev = synth.scroll_event(hwnd, x, y, -WHEEL_LINES, flags=synth.CONTROL)
        synth.send_scroll(panel, ev)
        yield 0.5
        self.seen["bigger"] = self.state()
        self.event("quit")


@pytest.fixture
def pet_module(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "lock_dir", lambda: str(tmp_path / "locks"))
    loader = importlib.machinery.SourceFileLoader("clawd_pet_on_mac", PET_PATH)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("clawd_pet_on_mac", loader))
    loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not os.path.isfile(os.path.join(FRAMES, "manifest.json")), reason="no frames at " + FRAMES)
def test_the_pet_runs_drags_shows_its_menu_grows_and_quits(tmp_path, pet_module):
    home = str(tmp_path / "home")
    run = Run(pet_module, home)
    later(0.2, run.next, run.timers)
    later(GIVE_UP_SECS, run.give_up, run.timers)
    try:
        rc = pet_module.main(["--home", home, "--frames-dir", FRAMES, "--debug"])
    finally:
        for t in run.timers:
            t.invalidate()
        loop.PostQuitMessage(0)                  # what main() left posted goes (its windows are gone)
        msg = pet_module.MSG()
        while pet_module.GetMessageW(ctypes.byref(msg), None, 0, 0):
            pass
    with open(os.path.join(home, "pet.log"), encoding="utf-8") as f:
        log = f.read()
    assert not run.errors, "\n".join(run.errors) + "\n--- pet.log:\n" + log
    assert rc == 0
    assert window.find_windows() == []
    # the drag took it DRAG away, and it stays there (a drop: no throw, no snap)
    assert run.seen["moved"] == DRAG
    before, dropped = run.seen["before"], run.seen["dropped"]
    assert dropped["y"] - before["y"] == DRAG[1], (before, dropped)
    assert dropped["x"] < before["x"] - 300, (before, dropped)
    assert "a drop" in log and "dropped (release)" in log
    # the menu: up, then closed (0); then up with the other language chosen, which the pet then speaks
    assert run.seen["menu"] and "语言 / Language" in run.seen["menu"]
    assert "menu -> 0" in log
    want = "en" if run.seen["lang_before"] == "zh" else "zh"
    assert run.seen["lang"] == dict(pet_module.LANGS)[want]
    assert run.seen["lang_after"] == want and run.seen["lang_state"] == want
    assert "menu -> %d" % (pet_module.ID_LANG_BASE + [c for c, _ in pet_module.LANGS].index(want)) in log
    # Control + wheel: the largest size
    assert run.seen["bigger"]["scale"] == pet_module.SCALE_MAX
    assert "size 100% -> 300% (ctrl+wheel)" in log
    # and nothing went wrong on the way, but the growth sign wanting GDI+ while clawd_mac.gdiplus is not there yet
    blocks = tracebacks(log)
    bad = [b for b in blocks if gdiplus_there() or "clawd_mac.gdiplus" not in b]
    assert not bad, "\n\n".join(bad)
    assert log.count("Traceback") == sum(b.count("Traceback") for b in blocks), log
