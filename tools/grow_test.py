"""Growth checks (养成): XP for turns, fixes, helpers, first finds and play; the level-up waits for a calm moment;
grow.json is kept and read back; a broken file is no reason to stop.  A --home test pet, events by bash echo."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/growhome"
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


# ---- run 1: XP for turns, fixes, helpers, first finds, play (no level-up in the way: level_shown is high) ----
start({"xp": 0, "level_shown": 99})
P = pets()
check("three pets", len(P) == 3, len(P))

n = len(log())
evs("listen aaaa1111", "stop aaaa1111")
m = wait_for(r"grow: turn \d+s, 0 tools", n, 5)
time.sleep(1)
L = log()[n:]
check("1 empty turn: counted, no tools, no XP", m is not None and not re.search(r"grow: \+\d+ turn", L), L[-400:])

n = len(log())
evs("listen bbbb2222", "read bbbb2222", "think bbbb2222", "stop bbbb2222")
m = wait_for(r"grow: \+5 turn \(xp 5, Lv\.1 5/40\)", n, 5)
L = log()[n:]
check("2 turn with a tool: +5", m is not None and re.search(r"grow: turn \d+s, 1 tools", L) is not None, L[-400:])
time.sleep(3)

n = len(log())
evs("listen cccc3333", "run cccc3333", "fail cccc3333", "run cccc3333", "think cccc3333")
m = wait_for(r"grow: \+5 fixed after an error", n, 5)
check("3 fix: +5", m is not None, log()[n:][-400:])
evs("run cccc3333", "fail cccc3333", "run cccc3333", "think cccc3333")
time.sleep(1)
check("3 a second fix in the same turn gives nothing", len(re.findall(r"fixed after an error", log()[n:])) == 1, log()[n:][-400:])
evs("stop cccc3333")
m = wait_for(r"grow: turn \d+s, 4 tools", n, 5)
check("3 that turn's 4 tool ends were counted", m is not None, log()[n:][-400:])
time.sleep(3)

n = len(log())
event("agent_done dddd4444")
m = wait_for(r"grow: \+3 helper back", n, 5)
check("4 agent_done: +3", m is not None, log()[n:][-400:])
time.sleep(4)

# a failed turn: no XP
n = len(log())
evs("listen ffff0000", "run ffff0000", "fail ffff0000", "stopfail ffff0000")
m = wait_for(r"grow: turn \d+s, 1 tools, ended in an error", n, 5)
time.sleep(1)
check("a turn that ended in an error: counted, 0 XP", m is not None and not re.search(r"grow: \+\d+ turn", log()[n:]), log()[n:][-400:])
time.sleep(3)

# 6: first find
n = len(log())
event("combo:high_five")
m = wait_for(r"combo high_five over", n, 30)
check("6 the combo is played", m is not None, log()[n:][-500:])
m2 = wait_for(r"grow: \+20 new: high_five", n, 3)
m3 = wait_for(r"sign up: 新发现：击掌！", n, 6)
check("6 first find: +20 and the sign", m2 is not None and m3 is not None, log()[n:][-500:])
wait_for(r"sign down", n + (m3.end() if m3 else 0), 12)
time.sleep(2.5)
n = len(log())
event("combo:high_five")
wait_for(r"combo high_five over", n, 30)
time.sleep(3)
L = log()[n:]
check("6 the same combo again: nothing new", "new: high_five" not in L and "新发现" not in L, L[-400:])

# play: a drag counts once in 10 s
time.sleep(8)
P = pets()
n = len(log())
drag(P[0], -40)
m = wait_for(r"grow: \+\d+ play: (drag|throw|startle)", n, 4)     # a dozing pet woken by it counts as the play (+2 startle)
check("play: a drag gives XP (1; a throw 2; waking a dozing one 2)", m is not None, log()[n:][-500:])
time.sleep(2)
n = len(log())
P = pets()
drag(P[0], 40)
time.sleep(3)
check("play: a second drag within 10 s gives none", not re.search(r"grow: \+\d+ play:", log()[n:]), log()[n:][-500:])

L1 = log()
stop()
g = grow()
gains = sum(int(x) for x in re.findall(r"grow: \+(\d+) ", L1))
check("persistence: grow.json written on quit, xp = the log's gains", g is not None and g.get("xp") == gains, (g and g.get("xp"), gains))
check("persistence: the combo seen is kept", g is not None and "high_five" in g.get("seen", {}), g and g.get("seen"))
cnt = g and (g["turns"], g["empty_turns"], g["agents"], g["fixes"])
check("persistence: counts (turns 3, empty 1, agents 1, fixes 1)", g is not None and cnt == (3, 1, 1, 1), cnt)
check("run 1: no exceptions", "Traceback" not in L1)

# ---- run 2: the level-up waits for the turn ----
start({"xp": 35, "level_shown": 1})
n = len(log())
evs("listen eeee5555", "read eeee5555", "think eeee5555", "agent_done eeee5555", "agent_done eeee5555")
check("5 XP crossed 40 inside the turn", wait_for(r"grow: \+3 helper back \(xp 41, Lv\.2", n, 5) is not None, log()[n:][-400:])
time.sleep(4)
L = log()[n:]
check("5 no level-up while the big one is busy", "level up shown" not in L, L[-500:])
n2 = len(log())
event("stop eeee5555")
m = wait_for(r"grow: level up shown, Lv\.2", n2, 25)
L = log()[n2:]
check("5 after the stop: level up shown, Lv.2", m is not None and L.find("grow: turn") < L.find("level up shown"), L[-600:])
m1 = wait_for(r"combo celebrate_all: pet0", n2, 3)
m2 = wait_for(r"sign up: 升级啦！Lv\.2", n2, 3)
check("5 the family cheers and the sign goes up", m1 is not None and m2 is not None, log()[n2:][-600:])
wait_for(r"combo celebrate_all over", n2, 25)
time.sleep(10)
L = log()[n2:]
check("5 the level-up's own cheer is no first find", "new: celebrate_all" not in L, L[-400:])
L2 = log()
stop()
g = grow()
check("7 after quit: level_shown 2, xp 46+", g is not None and g["level_shown"] == 2 and g["xp"] >= 46, g and (g["level_shown"], g["xp"]))
check("7 celebrate_all is not marked as seen", g is not None and "celebrate_all" not in g["seen"], g and g["seen"])
xp0 = g["xp"] if g else None
check("run 2: no exceptions", "Traceback" not in L2)

start("keep")
time.sleep(8)
L = log()
check("7 restart: no second level-up for the same level", "level up shown" not in L and "sign up: 升级啦" not in L, L[-400:])
check("7 restart: the window is up and XP was read back", len(pets()) == 3, len(pets()))
stop()
g = grow()
check("7 restart: xp unchanged by a quiet start", g is not None and g["xp"] == xp0, (g and g["xp"], xp0))

# ---- 8: startup replay of the last event gives no XP ----
start({"xp": 0, "level_shown": 99}, pre_event="agent_done aaaa1111")
time.sleep(3)
L = log()
check("8 replayed last event (agent_done): no XP", "helper back" not in L and "grow: +" not in L, L[-400:])
event("agent_done aaaa1111")
m = wait_for(r"grow: \+3 helper back", len(L), 5)
check("8 a live agent_done after it does count", m is not None, log()[len(L):][-300:])
stop()

# ---- 9: a broken grow.json ----
start(raw_grow={"grow.json": "{broken"})
L = log()
check("9 broken grow.json: the pet starts", len(pets()) == 3 and "Traceback" not in L, (len(pets()), L[-300:]))
check("9 logged as unreadable, the broken one kept as .bad", "unreadable" in L and os.path.exists(gpath("grow.json.bad")), L[-300:])
evs("listen aaaa1111", "read aaaa1111", "think aaaa1111", "stop aaaa1111")
wait_for(r"grow: \+5 turn", len(L), 5)
stop()
g = grow()
check("9 a fresh grow.json is written after it", g is not None and g["xp"] == 5, g and g["xp"])

# broken grow.json with a good backup
start(raw_grow={"grow.json": "{broken", "grow.json.bak": json.dumps({"xp": 77, "level_shown": 99, "seen": {"peek": "2026-01-01"}})})
L = log()
check("9 broken + backup: taken from the backup", "taken from the backup" in L and len(pets()) == 3, L[-300:])
stop()
g = grow()
check("9 the backup's XP lives on in the new grow.json", g is not None and g["xp"] == 77 and "peek" in g["seen"], g and (g["xp"], g["seen"]))

# ---- 10: hidden: the level-up waits, comes after show ----
start({"xp": 35, "level_shown": 1})
event("hide")
time.sleep(1.5)
n = len(log())
evs("agent_done hhhh8888", "agent_done hhhh8888")
check("10 hidden: XP crossed 40", wait_for(r"grow: \+3 helper back \(xp 41, Lv\.2", n, 5) is not None, log()[n:][-300:])
time.sleep(5)
check("10 hidden: no level-up", "level up shown" not in log()[n:] and len(pets()) == 0, (len(pets()), log()[n:][-300:]))
n2 = len(log())
event("show")
m = wait_for(r"grow: level up shown, Lv\.2", n2, 25)
check("10 shown again: the level-up comes", m is not None, log()[n2:][-500:])
time.sleep(3)
stop()
check("run 10: no exceptions", "Traceback" not in last_log())

# ---- 11: one pet: it cheers by itself, no family combo ----
start({"xp": 35, "level_shown": 1}, slots=())
check("11 one pet", len(pets()) == 1, len(pets()))
n = len(log())
evs("agent_done oooo9999", "agent_done oooo9999")
m = wait_for(r"grow: level up shown, Lv\.2", n, 25)
m2 = wait_for(r"sign up: 升级啦！Lv\.2", n, 5)
L = log()[n:]
check("11 alone: level up shown and the sign goes up", m is not None and m2 is not None, L[-500:])
check("11 alone: no celebrate_all", "combo celebrate_all" not in L, L[-500:])
check("11 alone: the big one cheers (celebrate)", re.search(r"play celebrate\w* .*level up", L) is not None, L[-500:])
time.sleep(8)
stop()
check("run 11: no exceptions", "Traceback" not in last_log())

# ---- 12: English: both signs ----
start({"xp": 35, "level_shown": 1})
event("lang:en")
time.sleep(1)
n = len(log())
event("combo:high_five")
m = wait_for(r"sign up: New: ", n, 40)
check("12 English: the first-find sign", m is not None, log()[n:][-600:])
m = wait_for(r"sign up: Level up! Lv\.2", n, 30)
check("12 English: the level-up sign (XP 55 crosses Lv.2)", m is not None, log()[n:][-600:])
event("lang:zh")
time.sleep(1)
stop()
check("run 12: no exceptions", "Traceback" not in last_log())

# ---- 13: --grow-quiet ----
start({"xp": 45, "level_shown": 1}, extra=["--grow-quiet"])
time.sleep(6)
check("13 --grow-quiet: no level-up within 6 s", "level up shown" not in log() and "sign up" not in log(), log()[-300:])
n = len(log())
event("combo:high_five")
wait_for(r"combo high_five over", n, 30)
time.sleep(3)
L = log()[n:]
check("13 --grow-quiet: XP still counted, no sign", "grow: +20 new: high_five" in L and "sign up" not in L, L[-400:])
stop()
g = grow()
check("13 --grow-quiet: XP written", g is not None and g["xp"] == 65, g and g["xp"])
check("run 13: no exceptions", "Traceback" not in last_log())

# ---- 14: a 小剧场 does not hold up the level-up: the cheer wakes the one that dozes ----
start({"xp": 39, "level_shown": 1})
n = len(log())
cursor(1450, 1504 - 120)                       # resting over the middle one (feet 1450,1504, 80 px): near enough
m = wait_for(r"pet1 nap: dozes off", n, 10)    # to the big one for the cheer (the smallest is not: it is left out)
check("14 the middle one dozes by the resting cursor", m is not None, log()[n:][-400:])
time.sleep(1.5)
n2 = len(log())
drag(pets()[0], -40)                           # +1 for play: XP 40, Lv.2, while it dozes (the cursor still resting)
m = wait_for(r"grow: level up shown, Lv\.2", n2, 10)
L = log()[n2:]
check("14 level up shown while it dozed", m is not None, L[-800:])
wait_for(r"combo celebrate_all over", n2, 20)
L = log()[n2:]
i_up = L.find("level up shown")
i_shock = L.find("pet1 play doze_startle")
i_cheer = L.find("pet1 play celebrate")
check("14 the cheer wakes it: startled first, then it cheers with them",
      "pet1 nap over (combo)" in L and 0 <= i_up and 0 <= i_shock < i_cheer, L[-1200:])
stop()
check("run 14: no exceptions", "Traceback" not in last_log())

# ---- 15: round 3: a star at the 10th time, a special action's first find, a combo set up by hand ----
start({"xp": 0, "level_shown": 99, "seen": {"high_five": "2026-01-01"}, "combos": {"high_five": 9},
       "acts": {"surprised": "2026-01-01", "dangle": "2026-01-01"}})
n = len(log())
event("combo:high_five")
m = wait_for(r"grow: \+10 star 1: high_five", n, 30)
m2 = wait_for(r"sign up: 击掌 ★ 熟练了！", n, 8)
check("15 the 10th high five: a star, +10 and its sign", m is not None and m2 is not None, log()[n:][-500:])
check("15 a combo from the menu is not 'by hand'", "by hand" not in log()[n:], log()[n:][-300:])
time.sleep(8)
n = len(log())
evs("listen ssss1111", "run ssss1111", "fail ssss1111", "stopfail ssss1111")
m = wait_for(r"grow: \+10 new action: shrug_sweat", n, 6)
m2 = wait_for(r"sign up: 新发现：摊手流汗！", n, 15)
check("15 a special action the first time: +10 and the sign", m is not None and m2 is not None, log()[n:][-500:])
time.sleep(8)
n = len(log())
evs("listen ssss2222", "run ssss2222", "fail ssss2222", "stopfail ssss2222")
time.sleep(3)
check("15 the same action again: nothing new", "new action" not in log()[n:], log()[n:][-300:])
time.sleep(12)                                 # the middle one is back at its place and free
P = pets()
n = len(log())
drag(P[2], 200)                                # the smallest (feet 1250) dropped on the middle one (1450)
m = wait_for(r"combo high_five over", n, 30)
m2 = wait_for(r"grow: \+3 by hand: high_five", n, 3)
check("15 dropped on another: the high five gives +3", m is not None and m2 is not None, log()[n:][-600:])
L15 = log()
stop()
g = grow()
check("15 grow.json: the count, the actions seen (common ones too)",
      g is not None and g["combos"].get("high_five") == 11 and "shrug_sweat" in g["acts"] and "idle" in g["acts"],
      g and (g.get("combos"), sorted(g.get("acts", {}))))
check("15 the parts of combos are not actions", g is not None and not any(k.startswith("high_five") for k in g["acts"]),
      g and sorted(g["acts"]))
check("run 15: no exceptions", "Traceback" not in L15)

# ---- 16: how much of the album is found: a mark, once the album has been opened (album.json) ----
json.dump({"v": 1, "seen": {}}, open(HOME + "/album.json", "w"))
try:
    # the nine special actions seen, and the tower: 10 of 66 cells, past 10 %.  A combo counted apart by who
    # played it (round 7, for a day) is one combo again.
    start({"xp": 0, "level_shown": 99, "combos": {"stack": 2, "stack.two": 1}, "seen": {"stack.two": "2026-11-12"}})
    n = 0
    m = wait_for(r"grow: \+10 album 10% found", n, 10)
    m2 = wait_for(r"sign up: 图鉴收集 10%！", n, 12)
    m3 = wait_for(r"combo celebrate_all: ", n, 6)
    check("16 the album 10 % found: XP, its sign, the family cheers", m is not None and m2 is not None and m3 is not None, log()[-600:])
    time.sleep(8)
    L16 = log()
    stop()
    g = grow()
    check("16 the mark is kept, and only once", g is not None and g.get("album_marks") == [10] and L16.count("album 10% found") == 1,
          g and g.get("album_marks"))
    check("16 the old count of the two-high tower is the tower's again",
          g is not None and g["combos"].get("stack") == 3 and "stack" in g["seen"] and not any("." in k for k in list(g["combos"]) + list(g["seen"])),
          g and (g.get("combos"), g.get("seen")))
    check("run 16: no exceptions", "Traceback" not in L16)
finally:
    os.remove(HOME + "/album.json")

# ---- 17: round 8: the gifts of the levels.  Lv.8 and none given yet: the three made by then are 补发, one sign
# each; a look of the signs the level has brought is taken (and held up), one it has not is not.  Then a level-up
# to Lv.12 holds up its gift after the level's sign.
def xp_at(lv):
    return sum(min(int(round(40 * i ** 1.5)), 1080) for i in range(1, lv))


start({"xp": xp_at(8) + 10, "level_shown": 8})
n = 0
m = wait_for(r"grow: gift frame_dots \(Lv\.7\), 补发", n, 10)
L = log()
check("17 补发: the gifts of Lv.3, 5 and 7, none of those not made yet",
      m is not None and all("grow: gift %s" % g in L for g in ("chalk_pink", "dig_4", "frame_dots")) and "items_2" not in L, L[-600:])
m = wait_for(r"sign up: 补发：彩点外框", n, 30)
L = log()
check("17 补发: a sign for each, in turn", m is not None and L.find("补发：粉色粉笔") < L.find("补发：翻找机会存 4 次") < L.find("补发：彩点外框"), L[-800:])
time.sleep(6)
n = len(log())
event("sign:chalk=pink")
m = wait_for(r"look: chalk=pink", n, 6)
m2 = wait_for(r"sign up: 新牌子！", n, 8)
check("17 a look the level brought: taken and held up", m is not None and m2 is not None, log()[n:][-400:])
n = len(log())
event("sign:chalk=blue")
m = wait_for(r"look: chalk=blue not there \(Lv\.8\)", n, 6)
check("17 a look of Lv.12 at Lv.8: not taken", m is not None, log()[n:][-400:])
time.sleep(2)
L17 = log()
stop()
g = grow()
try:
    st = json.load(open(HOME + "/state.json", encoding="utf-8"))
except Exception:
    st = {}
check("17 grow.json: the gifts given are written down", g is not None and g.get("gifts") == ["chalk_pink", "dig_4", "frame_dots"],
      g and g.get("gifts"))
check("17 state.json: the look is kept", st.get("sign") == {"chalk": "pink"}, st)
check("run 17a: no exceptions", "Traceback" not in L17)
start({"xp": xp_at(12) + 5, "level_shown": 11, "gifts": ["chalk_pink", "dig_4", "frame_dots", "items_2"]})
n = 0
m = wait_for(r"grow: level up shown, Lv\.12", n, 25)
m2 = wait_for(r"sign up: 礼物：蓝色粉笔", n, 30)
L = log()
check("17 a level-up: its gift's sign after the level's", m is not None and m2 is not None and L.find("升级啦") < L.find("礼物：蓝色粉笔")
      and "补发" not in L, L[-800:])
time.sleep(2)
L17 = log()
stop()
g = grow()
check("17 the level's gift written down", g is not None and "chalk_blue" in g.get("gifts", []), g and g.get("gifts"))
check("run 17b: no exceptions", "Traceback" not in L17)

# ---- 18: 小插曲 (the gift of Lv.16): with --slip yes the three combos go the other way; each a find the first time,
# the combo counted as ever; before the level, never.
start({"xp": xp_at(16) + 5, "level_shown": 99, "gifts": ["chalk_pink", "dig_4", "frame_dots", "items_2", "chalk_blue", "frame_stars", "slips", "dig_5"],
       "seen": {"high_five": "2026-01-01", "leapfrog": "2026-01-01", "stack": "2026-01-01"}, "slip_dry": 3}, extra=["--slip", "yes"])
for name, clip, sign in (("high_five", "slip_sit_", "击掌扑空"), ("leapfrog", "slip_roll_", "滚了过去"), ("stack", "stack_flip_", "翻着跟头下来")):
    n = len(log())
    event("combo:" + name)
    m = wait_for(r"combo %s: .*小插曲" % name, n, 10)
    m1 = wait_for(r"play %s" % clip, n, 25)
    m2 = wait_for(r"grow: \+10 new 小插曲: %s" % name, n, 40)
    m3 = wait_for(r"sign up: 新发现：%s！" % sign, n, 15)
    check("18 %s: its 小插曲 plays, a find with its sign" % name, None not in (m, m1, m2, m3), log()[n:][-700:])
    time.sleep(7)
n = len(log())
event("combo:high_five")
m = wait_for(r"combo high_five over", n, 30)
time.sleep(1.5)
check("18 the same one again: played, no new find", m is not None and "new 小插曲" not in log()[n:], log()[n:][-400:])
L18 = log()
stop()
g = grow()
check("18 grow.json: the three kept, the count of dry ones back to 0, the combos counted",
      g is not None and sorted(g.get("slips", {})) == ["high_five", "leapfrog", "stack"] and g.get("slip_dry") == 0
      and g["combos"].get("high_five") == 2 and g["combos"].get("stack") == 1, g and (g.get("slips"), g.get("slip_dry"), g.get("combos")))
check("run 18a: no exceptions", "Traceback" not in L18)
start({"xp": xp_at(15) + 5, "level_shown": 99, "seen": {"high_five": "2026-01-01"}}, extra=["--slip", "yes"])
n = len(log())
event("combo:high_five")
m = wait_for(r"combo high_five over", n, 30)
L18 = log()
stop()
g = grow()
check("18 before its level: the plain high five, nothing counted", m is not None and "小插曲" not in L18[n:] and "slip_sit" not in L18[n:]
      and g is not None and g.get("slip_dry") == 0 and not g.get("slips"), L18[n:][-400:])

# ---- 19: the monument (the gift of Lv.20).  Up to Lv.20 in play: the level's sign, the monument's with a second
# cheer, the gold chalk; the numbers of that day kept, and never changed after.  A family at Lv.20 before the
# monument was made (an update): 补发, the numbers of the day it comes.
BEFORE_20 = ["chalk_pink", "dig_4", "frame_dots", "items_2", "chalk_blue", "frame_stars", "slips", "dig_5", "board_flag"]
start({"xp": xp_at(20) + 5, "level_shown": 19, "gifts": BEFORE_20, "turns": 777, "days": 12, "since": "2026-11-01",
       "items": {"screw": 3, "leaf": 2}, "combos": {"stack": 12, "peek": 30}})
m = wait_for(r"grow: gift monument \(Lv\.20\)", 0, 15)
m1 = wait_for(r"sign up: 礼物：满级纪念碑", 0, 40)
L = log()
m2 = wait_for(r"combo celebrate_all: ", L.find("礼物：满级纪念碑"), 10) if m1 else None
m3 = wait_for(r"sign up: 礼物：金色粉笔", 0, 30)
L19 = log()
check("19 up to Lv.20: the level, the monument's sign with a second cheer, the gold chalk",
      None not in (m, m1, m2, m3) and L19.find("升级啦") < L19.find("礼物：满级纪念碑"), L19[-900:])
stop()
g = grow()
mon = (g or {}).get("monument") or {}
check("19 grow.json: the numbers of that day kept", mon.get("turns") == 777 and mon.get("days") == 12 and mon.get("since") == "2026-11-01"
      and mon.get("things") == 5 and mon.get("kinds") == 2 and mon.get("played") == 42 and mon.get("day") == time.strftime("%Y-%m-%d")
      and "monument" in g.get("gifts", []) and "chalk_gold" in g.get("gifts", []), (mon, g and g.get("gifts")))
check("run 19a: no exceptions", "Traceback" not in L19)
g["turns"] = 900
start(g)
time.sleep(6)
L = log()
stop()
g2 = grow()
check("19 again: no second monument, its numbers as they were", "gift monument" not in L and (g2 or {}).get("monument") == mon,
      (g2 or {}).get("monument"))
start({"xp": xp_at(20) + 5, "level_shown": 20, "gifts": BEFORE_20, "turns": 55})
m = wait_for(r"grow: gift monument \(Lv\.20\), 补发", 0, 15)
m1 = wait_for(r"sign up: 补发：满级纪念碑", 0, 40)
L = log()
stop()
g = grow()
check("19 at Lv.20 before the monument was made: 补发, the numbers of that day", m is not None and m1 is not None
      and ((g or {}).get("monument") or {}).get("turns") == 55 and "Traceback" not in L, (L[-500:], g and g.get("monument")))

# ---- 20: a message in the middle of a turn (插话) is the same turn: one XP, one chance at its end, after enough work ----
start({"xp": 0, "level_shown": 99, "chances": 0}, extra=["--chance-work", "3"])
time.sleep(3)
n = n20 = len(log())
evs("listen a1a1b2b2", "run a1a1b2b2", "think a1a1b2b2")
time.sleep(2)
evs("listen a1a1b2b2", "read a1a1b2b2", "think a1a1b2b2")
time.sleep(2)
evs("stop a1a1b2b2")
m = wait_for(r"grow: turn \d+s, 2 tools", n, 5)
L = log()[n:]
check("20 a message in the middle: one turn of 2 tools, nothing settled before its end",
      m is not None and L.count("grow: turn") == 1 and "interrupted" not in L, L[-600:])
time.sleep(2)
n = len(log())
evs("listen c3c3d4d4", "run c3c3d4d4", "think c3c3d4d4")
time.sleep(4)
evs("cut c3c3d4d4")                    # stopped by you (Esc, as the agent says it): over, but not as a whole
m = wait_for(r"grow: turn \d+s, 1 tools, interrupted", n, 5)
time.sleep(1)
evs("listen e5e5f6f6", "run e5e5f6f6", "think e5e5f6f6", "stop e5e5f6f6")   # a tool counts once it is over
m1 = wait_for(r"grow: turn \d+s, 1 tools\s", n, 5)
time.sleep(1)
evs("listen f7f7a8a8", "run f7f7a8a8", "fail f7f7a8a8", "stopfail f7f7a8a8")
m2 = wait_for(r"grow: turn \d+s, \d+ tools, ended in an error", n, 5)
time.sleep(1)
L20 = log()[n20:]
stop()
g = grow() or {}
check("20 the chances come as the work time goes: in the middle of a turn, in an interrupted one too, up to the 3 kept",
      None not in (m, m1, m2) and g.get("chances") == 3 and "by hand (4 now)" not in L20
      and -1 < L20.find("by hand (1 now)") < L20.find("grow: turn") and -1 < L20.find("by hand (3 now)") < L20.find("interrupted"),
      (m is not None, m1 is not None, m2 is not None, g.get("chances"), g.get("chance_secs"), g.get("turns")))

print("%d/%d passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
