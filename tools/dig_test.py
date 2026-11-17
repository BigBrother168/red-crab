"""翻找 checks: one digs by itself in a long turn and the find is counted when the turn ends; by hand a find takes
a chance earned by work, and with none left it comes up empty; called away, it stands up and nothing is used.
A --home test pet, events by bash echo; --dig-find decides what comes up."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/dighome"
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


# ---- 1: by itself in a long turn; the find is kept till the turn ends ----
start({"xp": 0, "level_shown": 99}, extra=["--dig-every", "3", "--dig-most", "1", "--dig-find", "leaf", "--show-gap", "1"])
check("three pets", len(pets()) == 3, len(pets()))
n = len(log())
evs("listen aaaa1111", "read aaaa1111")
m = wait_for(r"dig: pet\d digs, \d+s into the turn", n, 12)
check("1 a small one digs by itself, a few seconds into the turn", m is not None, log()[n:][-400:])
m = wait_for(r"dig: pet\d found leaf \(common\), kept till the turn ends", n, 14)
check("1 it finds the leaf and keeps it", m is not None, log()[n:][-500:])
seen = 0
end = time.time() + 3
while time.time() < end and seen < 2:
    seen = max(seen, len(items()))
    time.sleep(0.05)
check("1 the find and its glow are on screen (two small windows)", seen == 2, seen)
time.sleep(4)
check("1 put away again", len(items()) == 0, len(items()))
L = log()[n:]
check("1 one dig a turn (--dig-most 1)", len(re.findall(r"dig: pet\d digs", L)) == 1 and "treasure:" not in L, L[-400:])
n2 = len(log())
evs("think aaaa1111", "stop aaaa1111")
m0 = wait_for(r"sign up: 做完了", n2, 5)
m = wait_for(r"pet\d play present .*shows the find", n2, 16)
L = log()[n2:]
check("1 the turn ends: first the done sign, then the finder holds the leaf up",
      m0 is not None and m is not None and L.find("sign up: 做完了") < L.find("play present") and "sign down" in L[:L.find("play present")], L[-600:])
m = wait_for(r"grow: \+20 treasure: leaf x1", n2, 3)
m2 = wait_for(r"sign up: 捡到了：树叶", n2, 8)
check("1 the leaf is theirs: +20 and its sign", m is not None and m2 is not None, log()[n2:][-500:])
check("1 it is on screen again while held up", len(items()) == 2, len(items()))
m = wait_for(r"play: pet\d plays with leaf \(play_\w+, first of its kind\)", n2, 16)
check("1 the first leaf: once it has been shown, it is played with there and then", m is not None and
      log()[n2:].find("sign down") < log()[n2:].find("first of its kind"), log()[n2:][-600:])
time.sleep(6)

# ---- 2: by hand: the turn earned one find; then none is left ----
n = len(log())
event("rummage:1")
m = wait_for(r"dig: pet1 digs by hand \(event\), 1 finds left", n, 5)
m2 = wait_for(r"dig: pet1 found leaf", n, 10)
m3 = wait_for(r"grow: treasure: leaf x2", n, 3)
check("2 by hand: digs at once, finds, counted there and then (a second leaf: no XP)", m is not None and m2 is not None and m3 is not None,
      log()[n:][-500:])
time.sleep(6)
n = len(log())
event("rummage:1")
m = wait_for(r"dig: pet1 found nothing \(no finds left\)", n, 12)
check("2 no chance left: it digs all the same and comes up empty", m is not None and "rummage_none" in log()[n:], log()[n:][-500:])
time.sleep(6)

# ---- 3: called away while it digs: up, nothing used ----
n = len(log())
event("rummage:2")
wait_for(r"pet2 play rummage \[loop\]", n, 6)
time.sleep(0.3)
drag(pets()[2], 30)
m = wait_for(r"dig: pet2 cut short", n, 4)
check("3 picked up while digging: cut short", m is not None and "found" not in log()[n:], log()[n:][-500:])
time.sleep(3)
n = len(log())
event("rummage")
wait_for(r"pet0 digs by hand|dig: pet0 digs", n, 4)
time.sleep(1.2)
evs("listen bbbb2222", "read bbbb2222")
m = wait_for(r"dig: pet0 cut short \(work\)", n, 4)
m2 = wait_for(r"play rummage_up", n, 3)
check("3 the big one digging by hand, work comes: it stands up first", m is not None and m2 is not None, log()[n:][-500:])
time.sleep(2)
L3 = log()
stop()
g = grow()
check("grow.json: two leaves, no chance left", g is not None and g["items"] == {"leaf": 2} and g["chances"] == 0, g and (g.get("items"), g.get("chances")))
check("no exceptions", "Traceback" not in L3)

# ---- 4: no one to dig (one pet): the big one has a find of its own when a long turn ends ----
start({"xp": 0, "level_shown": 99}, slots=(), extra=["--dig-every", "3", "--dig-find", "gear", "--show-gap", "1"])
n = len(log())
evs("listen cccc3333", "read cccc3333")
time.sleep(4)
evs("think cccc3333", "stop cccc3333")
m = wait_for(r"dig: pet0 has a find of its own \(gear\)", n, 5)
m2 = wait_for(r"play pull_out .*shows the find", n, 16)
m3 = wait_for(r"sign up: 捡到了：小齿轮（少见）", n, 10)
check("4 alone: the big one pulls a find out from behind its back, and its sign", m is not None and m2 is not None and m3 is not None,
      log()[n:][-600:])
time.sleep(6)
n = len(log())
evs("listen dddd4444", "read dddd4444", "think dddd4444", "stop dddd4444")
time.sleep(6)
check("4 a short turn: no find", "find of its own" not in log()[n:] and "treasure:" not in log()[n:], log()[n:][-400:])
L4 = log()
stop()
check("run 4: no exceptions", "Traceback" not in L4)

# ---- 5: 交宝贝: a find better than common is carried to the big one; a dig by hand is not held up by what is put away ----
start({"xp": 0, "level_shown": 99, "chances": 1}, extra=["--dig-every", "3", "--dig-most", "1", "--dig-find", "gear", "--show-gap", "1"])
n = len(log())
evs("listen eeee5555", "read eeee5555")
m = wait_for(r"dig: pet(\d) found gear \(uncommon\), kept till the turn ends", n, 16)
check("5 a small one finds the gear and keeps it", m is not None, log()[n:][-400:])
g = grow()
check("5 what is put away is written down at once", g is not None and len(g.get("loot", [])) == 1 and g["loot"][0][0] == "gear", g and g.get("loot"))
time.sleep(4)
other = "2" if m is not None and m.group(1) == "1" else "1"
n1 = len(log())
event("rummage:" + other)
m = wait_for(r"dig: pet%s found gear \(uncommon\)\n" % other, n1, 8)
m1 = wait_for(r"grow: \+20 treasure: gear x1", n1, 2)
check("5 by hand in the same turn, a chance left: it finds one all the same, counted at once", m is not None and m1 is not None, log()[n1:][-500:])
time.sleep(5)
n2 = len(log())
evs("think eeee5555", "stop eeee5555")
m = wait_for(r"dig: pet\d brings gear \(uncommon\) to the big one", n2, 18)
m1 = wait_for(r"grow: treasure: gear x2", n2, 2)
check("5 the turn ends: the finder sets off to the big one with it, and it is theirs from then", m is not None and m1 is not None, log()[n2:][-600:])
seen = 0
end = time.time() + 4
while time.time() < end and seen < 2:
    seen = max(seen, len(items()))
    time.sleep(0.05)
check("5 the find is on its arm on the way (two small windows)", seen == 2, seen)
m = wait_for(r"play take_(left|right)", n2, 10)
m1 = wait_for(r"combo treasure over", n2, 10)
L = log()[n2:]
check("5 the big one takes it and holds it up; played to its end", m is not None and m1 is not None and "combo treasure cancelled" not in L, L[-700:])
m = wait_for(r"sign up: 捡到了：小齿轮（少见）", n2, 10)
check("5 its sign", m is not None, log()[n2:][-500:])
time.sleep(4)
L5 = log()
stop()
g = grow()
check("grow.json: two gears, nothing put away, 交宝贝 is not counted as a combo",
      g is not None and g["items"] == {"gear": 2} and g["loot"] == [] and "treasure" not in g["combos"] and "treasure" not in g["seen"],
      g and (g.get("items"), g.get("loot"), g.get("combos"), g.get("seen")))
check("run 5: no exceptions", "Traceback" not in L5)

# ---- 6: 交宝贝 cut short by work: theirs all the same, held up where it stands; a quit in the middle of a turn loses nothing ----
start({"xp": 0, "level_shown": 99}, extra=["--dig-every", "3", "--dig-most", "1", "--dig-find", "rubber_duck", "--show-gap", "1"])
n = len(log())
evs("listen ffff6666", "read ffff6666")
m = wait_for(r"found rubber_duck \(rare\), kept till the turn ends", n, 16)
time.sleep(4)
n2 = len(log())
evs("think ffff6666", "stop ffff6666")
m = wait_for(r"brings rubber_duck \(rare\) to the big one", n2, 18)
time.sleep(0.5)
evs("listen ffff6666", "read ffff6666")
m1 = wait_for(r"combo treasure cancelled \(event (listen|read)\)", n2, 4)
check("6 work comes while it is on its way: the hand-over is off", m is not None and m1 is not None, log()[n2:][-600:])
m = wait_for(r"play present .*not handed over", n2, 4)
m1 = wait_for(r"sign up: 捡到了：橡皮鸭（稀有）", n2, 10)
L = log()[n2:]
check("6 it holds the duck up where it stands; counted once, and its sign", m is not None and m1 is not None and len(re.findall(r"treasure: rubber_duck x", L)) == 1, L[-700:])
m = wait_for(r"found rubber_duck \(rare\), kept till the turn ends", n2, 25)
check("6 the new turn has a dig of its own", m is not None, log()[n2:][-500:])
L6 = log()
stop()
g = grow()
check("6 a quit in the middle of the turn: the duck is in grow.json", g is not None and [x[0] for x in g.get("loot", [])] == ["rubber_duck"] and g["items"] == {"rubber_duck": 1},
      g and (g.get("loot"), g.get("items")))
start("keep")
m = wait_for(r"rubber_duck was put away when they quit: theirs now", 0, 6)
m1 = wait_for(r"grow: treasure: rubber_duck x2", 0, 3)
check("6 at the next start it is theirs", m is not None and m1 is not None, log()[-500:])
L6 += log()
stop()
g = grow()
check("6 and no longer put away", g is not None and g["loot"] == [] and g["items"] == {"rubber_duck": 2}, g and (g.get("loot"), g.get("items")))
check("run 6: no exceptions", "Traceback" not in L6)

# ---- 7: a new family has two chances; a click on one that digs: a start, digging with gusto, sooner done ----
start(None, extra=["--dig-find", "yes"])
n = len(log())
event("rummage:1")
m = wait_for(r"dig: pet1 digs by hand \(event\), 2 finds left", n, 5)
check("7 a new family: two finds to dig up by hand", m is not None, log()[n:][-300:])
wait_for(r"pet1 play rummage \[loop\]", n, 5)
h = pets()[1]
l, t, r_, b = rect(h)
u.PostMessageW(h, WM_LDOWN, 1, lp((r_ - l) // 2, (b - t) - 30))
time.sleep(0.05)
u.PostMessageW(h, WM_LUP, 0, lp((r_ - l) // 2, (b - t) - 30))
m = wait_for(r"dig: pet1 helped by a click", n, 3)
t_help = time.time()
m1 = wait_for(r"pet1 play rummage_spur", n, 2)
m2 = wait_for(r"pet1 play rummage_fast", n, 3)
m3 = wait_for(r"dig: pet1 found", n, 4)
dt = time.time() - t_help
check("7 a click: a start, then it digs with gusto", m is not None and m1 is not None and m2 is not None, log()[n:][-500:])
check("7 and it is done sooner (%.1f s after the click)" % dt, m3 is not None and dt < 1.8, log()[n:][-500:])
time.sleep(4)
L7 = log()
stop()
check("run 7: no exceptions", "Traceback" not in L7)

# ---- 8: nothing found: it digs again later in the same turn ----
start({"xp": 0, "level_shown": 99}, extra=["--dig-every", "3", "--dig-find", "no", "--show-gap", "1"])
n = len(log())
evs("listen abab8888", "read abab8888")
m = wait_for(r"dig: pet\d found nothing", n, 16)
n1 = n + (m.end() if m is not None else 0)
m1 = wait_for(r"dig: pet\d digs, \d+s into the turn", n1, 20)
check("8 nothing came up: later in the turn it digs again", m is not None and m1 is not None, log()[n:][-500:])
time.sleep(1)
L8 = log()
stop()
check("run 8: no exceptions", "Traceback" not in L8)

# ---- 9: by hand, nothing found: the chance is used all the same, and the next one by hand is sure ----
start({"xp": 0, "level_shown": 99, "chances": 2}, extra=["--dig-find", "no"])
n = len(log())
event("rummage:1")
m = wait_for(r"dig: pet1 found nothing \(a chance used, the next by hand is sure\)", n, 12)
check("9 by hand and empty: a chance is used", m is not None, log()[n:][-500:])
time.sleep(6)
n = len(log())
event("rummage:1")
m = wait_for(r"dig: pet1 found \w+ \(", n, 12)
check("9 the next one by hand finds something", m is not None, log()[n:][-500:])
time.sleep(4)
L9 = log()
stop()
g = grow()
check("9 grow.json: one find, both chances used", g is not None and sum(g["items"].values()) == 1 and g["chances"] == 0 and g["dry_hand"] == 0,
      g and (g.get("items"), g.get("chances"), g.get("dry_hand")))
check("run 9: no exceptions", "Traceback" not in L9)

# ---- 10: 宝贝第二批: before Lv.10 the sure special (保底) is one of the first batch; from Lv.10 the moon lamp (new) ----
OLD = {"bug": 1, "bottle": 1, "biscuit": 1, "hourglass": 1, "plane_model": 1}
XP10 = sum(min(int(round(40 * i ** 1.5)), 1080) for i in range(1, 10)) + 5
for lv, xp in ((1, 0), (10, XP10)):
    start({"xp": xp, "level_shown": 99, "chances": 2, "items": dict(OLD), "dry_special": 39}, extra=["--dig-find", "yes"])
    n = len(log())
    event("rummage:1")
    m = wait_for(r"dig: pet1 found (\w+) \(", n, 12)
    got = m.group(1) if m else None
    if lv == 1:
        check("10 Lv.1: every special there is had (the moon lamp is locked): no sure special, and not the moon lamp",
              got is not None and got != "moon_lamp", log()[n:][-400:])
    else:
        check("10 Lv.10: the sure special is the moon lamp, the one not had yet", got == "moon_lamp", log()[n:][-400:])
    time.sleep(4)
    L10 = log()
    stop()
    check("run 10 (Lv.%d): no exceptions" % lv, "Traceback" not in L10)

# ---- 11: a find they had already does not reset 保底 (no luck lost); a new one does ----
start({"xp": XP10, "level_shown": 99, "chances": 2, "items": dict(OLD), "dry_special": 10}, extra=["--dig-find", "bug"])
n = len(log())
event("rummage:1")
m = wait_for(r"dig: pet1 found bug \(", n, 12)
time.sleep(4)
L11 = log()
stop()
g = grow()
check("11 a special they had: the special 保底 goes on (10 -> 11)", m is not None and g is not None and g.get("dry_special") == 11,
      g and g.get("dry_special"))
check("run 11: no exceptions", "Traceback" not in L11)

# ---- 12: 干活时间: a dig by itself each --dig-every s of the turn's work, dig_cap of the level a turn at most (3 at
# Lv.1); a chance to dig by hand each --chance-work s, in the middle of the turn; none while it waits for you ----
start({"xp": 0, "level_shown": 99, "chances": 0}, extra=["--dig-every", "3", "--dig-find", "leaf", "--chance-work", "4", "--show-gap", "1"])
n = len(log())
evs("listen c1c1c1c1", "read c1c1c1c1")
m = wait_for(r"dig: work earned a chance to dig by hand \(1 now\)", n, 12)
check("12 a chance comes in the middle of the turn, after its work time", m is not None and "grow: turn" not in log()[n:], log()[n:][-500:])
evs("attention c1c1c1c1")
time.sleep(1)
n1 = len(log())
time.sleep(9)
L = log()[n1:]
check("12 while it waits for you: no work time (no chance, no new dig)", "earned a chance" not in L and not re.search(r"dig: pet\d digs", L), L[-600:])
evs("think c1c1c1c1")
m = wait_for(r"dig: work earned a chance to dig by hand \(2 now\)", n1, 12)
check("12 at work again: the clock goes on", m is not None, log()[n1:][-500:])
m = wait_for(r"dig: pet\d digs, \d+s into the turn \(3 of 3\)", n, 40)
time.sleep(8)
L = log()[n:]
check("12 three digs by themselves in the turn, no fourth (Lv.1)", m is not None and "(4 of" not in L, L[-800:])
m = wait_for(r"dig: work earned a chance to dig by hand \(3 now\)", n, 10)
time.sleep(6)
check("12 the chances stop at three", m is not None and "(4 now)" not in log()[n:], log()[n:][-400:])
n2 = len(log())
evs("think c1c1c1c1", "stop c1c1c1c1")
m = wait_for(r"grow: treasure: leaf x3", n2, 60)
L12 = log()
stop()
g = grow() or {}
check("12 the turn ends: its three leaves are handed over", m is not None and g.get("items", {}).get("leaf") == 3 and g.get("loot") == [],
      (g.get("items"), g.get("loot"), L12[-600:]))
check("run 12: no exceptions", "Traceback" not in L12)

print("%d/%d passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
