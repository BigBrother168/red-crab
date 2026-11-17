"""把玩 checks: a treasure of theirs is taken out (by hand: the menu, the album, clawd do; or by itself while idle),
played with in its own clip (the treasure drawn in) and put away; your hand comes first, work goes on after it.
A --home test pet."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/playhome"
CUR = HOME + "/cursor"       # the cursor is read from here (--cursor-file): the real one never starts a 小剧场
BASH = "D:/git/Git/bin/bash.exe"
os.makedirs(HOME, exist_ok=True)
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
WM_MOVE, WM_LDOWN, WM_LUP = 0x0200, 0x0201, 0x0202
proc = None
runs = 0
res = []
GROW_FILES = ("grow.json", "grow.json.bak", "grow.json.bad", "grow.json.tmp")
# the nine special actions: seen already in most runs (a seed without "acts"), so their finds do not move the numbers
ACTS = ("shy", "dangle", "tumble", "dizzy", "doze", "doze_startle", "doze_up", "shrug_sweat", "surprised")


def gpath(name="grow.json"):
    return HOME + "/" + name


def start(seed=None, slots=(1, 2), extra=(), pre_event=None, raw_grow=None):
    """seed: dict -> grow.json before the start; None -> no grow files; "keep" -> the files stay as they are."""
    global proc
    for f in ("event", "state.json", "pet.log"):
        try:
            os.remove(os.path.join(HOME, f))
        except OSError:
            pass
    if seed != "keep":
        for f in GROW_FILES:
            try:
                os.remove(gpath(f))
            except OSError:
                pass
        if raw_grow is not None:
            for name, text in raw_grow.items():
                with open(gpath(name), "w", encoding="utf-8") as f:
                    f.write(text)
        elif seed is not None:
            seed = dict(seed)
            seed.setdefault("acts", dict((a, "2026-01-01") for a in ACTS))
            seed.setdefault("chances", 0)      # a new family has two; most runs count from none
            json.dump(seed, open(gpath(), "w"))
    st = {"x": 1700, "y": 1504, "scale": 1.0, "wanted": 1.0, "slots": list(slots)}
    if slots:
        st["pos"] = {"1": [1450, 1504, 1.0], "2": [1250, 1504, 1.0]}
    json.dump(st, open(HOME + "/state.json", "w"))
    if pre_event:
        event(pre_event)
    cursor(100, 100)
    proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--home", HOME, "--debug", "--frames-dir", FRAMES,
                             "--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999",
                             "--play-interval", "9999", "--keep-place", "--cursor-file", CUR,
                             "--nap-times", "1,2,3"] + list(extra))
    time.sleep(4)
    end = time.time() + 120                    # the small ones' frame sets may be rendered first
    calm = 0                                   # the small ones render one after another: calm for 2 s, not between two
    while time.time() < end:
        L = log()
        if len(re.findall(r"re-render .* started", L)) <= len(re.findall(r"re-render .* finished", L)) and "Traceback" not in L:
            calm += 1
            if calm >= 4:
                break
        else:
            calm = 0
        time.sleep(0.5)
    time.sleep(1)


def stop():
    global runs
    event("quit")
    time.sleep(2.5)
    runs += 1
    with open(HOME + "/pet_run%d.log" % runs, "w", encoding="utf-8") as f:     # the next start() clears pet.log
        f.write(log())
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def cursor(x, y):
    with open(CUR + ".tmp", "w") as f:
        f.write("%d %d" % (x, y))
    os.replace(CUR + ".tmp", CUR)


def event(line):
    subprocess.run([BASH, "-c", 'echo "%s" >> "%s/event"' % (line, HOME)])


def evs(*lines, gap=0.35):
    for l in lines:
        event(l)
        time.sleep(gap)


def log():
    return open(HOME + "/pet.log", encoding="utf-8", errors="replace").read()


def last_log():
    return open(HOME + "/pet_run%d.log" % runs, encoding="utf-8", errors="replace").read()


def grow():
    try:
        return json.load(open(gpath(), encoding="utf-8"))
    except Exception:
        return None


def pets():
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def f(h, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(32)
        u.GetWindowTextW(h, buf, 32)
        if pid.value == proc.pid and u.IsWindowVisible(h) and buf.value == "Clawd":
            out.append(h)
        return True
    u.EnumWindows(cb(f), 0)
    return sorted(out, key=lambda h: -(rect(h)[2] - rect(h)[0]))     # big, middle, small


def rect(h):
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def check(n, ok, info=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + ("  " + str(info) if (not ok or n.startswith(("persistence", "7 after", "9 the backup", "13 --grow-quiet: XP written"))) and info != "" else ""), flush=True)


def wait_for(pat, n, secs):
    end = time.time() + secs
    while time.time() < end:
        m = re.search(pat, log()[n:])
        if m:
            return m
        time.sleep(0.1)
    return None


def drag(h, dx, secs=0.6, pause=0.3, steps=8):
    """Press on the body, move by dx, wait a moment (else it is a throw), let go."""
    l, t, r, b = rect(h)
    cx, cy = (l + r) // 2, (t + b) // 2 + 20
    u.PostMessageW(h, WM_LDOWN, 1, lp(cx - l, cy - t))
    time.sleep(0.05)
    for i in range(1, steps + 1):
        wl, wt, _, _ = rect(h)
        u.PostMessageW(h, WM_MOVE, 1, lp(cx + dx * i // steps - wl, cy - wt))
        time.sleep(secs / steps)
    time.sleep(pause)
    wl, wt, _, _ = rect(h)
    u.PostMessageW(h, WM_LUP, 0, lp(cx + dx - wl, cy - wt))


def items():
    """the treasure windows on screen now"""
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def f(h, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(32)
        u.GetWindowTextW(h, buf, 32)
        if pid.value == proc.pid and u.IsWindowVisible(h) and buf.value == "ClawdItem":
            out.append(h)
        return True
    u.EnumWindows(cb(f), 0)
    return out




def playing(secs=2.0):
    """the most treasure windows seen on screen within secs"""
    most, end = 0, time.time() + secs
    while time.time() < end:
        most = max(most, len(items()))
        time.sleep(0.1)
    return most


HAVE = {"xp": 0, "level_shown": 99, "items": {"leaf": 1, "shell": 2, "paper_ball": 1, "gold_semicolon": 1}}


def spans(L, who=None):
    """-> [(pet, t0, t1)] of the play_* clips in the log (by the debug lines "petN play <clip>"), times in s."""
    out, open_ = [], {}
    for m in re.finditer(r"^\S+ (\d+):(\d+):(\d+) \[\d+\] (pet\d )?play (\S+) ", L, re.M):
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        pet = (m.group(4) or "pet0 ").strip()
        if pet in open_:
            out.append((pet, open_.pop(pet), t))
        if m.group(5).startswith("play_"):
            open_[pet] = t
    return out


# ---- 1: by hand (as the menu, the album and clawd do send it); the treasure is in the frames ----
start(HAVE)
check("three pets", len(pets()) == 3, len(pets()))
for item in ("leaf", "paper_ball", "shell", "gold_semicolon"):
    n = len(log())
    event("play:%s:1" % item)
    m = wait_for(r"play: pet1 plays with %s \(play_%s, event\)" % (item, item), n, 5)
    m2 = wait_for(r"pet1 play play_%s \[oneshot\]" % item, n, 5)
    seen = playing(2.0)
    check("1 %s: its own clip, the treasure drawn in (no window laid on)" % item, m is not None and m2 is not None and seen == 0,
          (seen, log()[n:][-400:]))
    m3 = wait_for(r"pet1 play idle", n + (m2.end() if m2 else 0), 6)
    check("1 %s: put away, back to idle" % item, m3 is not None, log()[n:][-300:])
    time.sleep(0.5)
n = len(log())
event("play")
m = wait_for(r"play: pet\d plays with (leaf|shell|paper_ball|gold_semicolon) \(play_\w+, event\)", n, 5)
check("1 any one of theirs, by one with nothing to do", m is not None, log()[n:][-400:])
time.sleep(5.5)
n = len(log())
event("play:pebble")
m = wait_for(r"play: pet\d not theirs: pebble", n, 4)
check("1 one they have not found: nothing", m is not None and "play play_pebble" not in log()[n:], log()[n:][-300:])
L1 = log()
stop()
check("run 1: no exceptions", "Traceback" not in L1)
check("1 the treasures' clips are not in the menu's actions (clawd list)", "play_leaf" not in subprocess.run(
    ["C:/Python312/python.exe", os.path.join(T, "clawd.py"), "list"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)

# ---- 2: your hand comes first; work goes on after it ----
start(HAVE)
n = len(log())
event("play:shell:2")
time.sleep(1.6)
p = pets()
drag(p[2], -120)
m = wait_for(r"pet2 play dangle", n, 3)
check("2 picked up while it plays: dangles at once", m is not None, log()[n:][-400:])
time.sleep(2)
n = len(log())
evs("listen bbbb2222", "read bbbb2222")
time.sleep(1.5)
event("play:leaf:0")
m = wait_for(r"play: pet0 plays with leaf \(play_leaf", n, 5)
m2 = wait_for(r"\] play play_leaf", n, 5)
check("2 the big one at work plays when asked", m is not None and m2 is not None, log()[n:][-500:])
m3 = wait_for(r"\] play (work_read|think)", n + (m2.end() if m2 else 0), 8)
check("2 ... and goes back to work after it", m3 is not None, log()[n:][-500:])
evs("stop bbbb2222")
time.sleep(2)
L2 = log()
stop()
check("run 2: no exceptions", "Traceback" not in L2)

# ---- 3: by itself while idle, one of them at a time; none without treasures ----
start(HAVE, extra=["--extra-interval", "1-1.5", "--play-alone", "1"])
n = 0                                          # from its start: the first may come before start() is back
m = wait_for(r"play: pet\d plays with \w+ \(play_\w+, by itself\)", n, 8)
check("3 idle: one takes a treasure out by itself", m is not None, log()[n:][-400:])
time.sleep(14)
L3 = log()
sp = sorted(spans(L3[n:]), key=lambda x: x[1])
overlap = [(a, b) for a, b in zip(sp, sp[1:]) if b[1] < a[2]]
check("3 never two at once (%d plays by themselves)" % len(sp), len(sp) >= 2 and not overlap, (sp, overlap))
stop()
check("run 3: no exceptions", "Traceback" not in L3)
start({"xp": 0, "level_shown": 99}, extra=["--extra-interval", "1-1.5", "--play-alone", "1"])
n = len(log())
event("play")
time.sleep(5)
L4 = log()
check("3 no treasures: none taken out, by hand or by itself", "plays with" not in L4[n:] and "not theirs" in L4[n:], L4[n:][-300:])
stop()
check("run 4: no exceptions", "Traceback" not in L4)

print("%d/%d passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
