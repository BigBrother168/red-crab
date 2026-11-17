"""鼠标小剧场: the cursor rests near one of them -> it looks over, comes closer, dozes; a move startles it.
The cursor is read from a file (--cursor-file): the test never moves the real one."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/naphome"
CUR = HOME + "/cursor"
BASH = "D:/git/Git/bin/bash.exe"
os.makedirs(HOME, exist_ok=True)
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
WM_LDOWN, WM_LUP = 0x0201, 0x0202
proc = None


def start(extra=()):
    global proc
    for f in ("event", "state.json", "pet.log"):
        try:
            os.remove(os.path.join(HOME, f))
        except OSError:
            pass
    json.dump({"x": 1700, "y": 1504, "scale": 1.0, "wanted": 1.0, "slots": [1, 2],
               "pos": {"1": [1450, 1504, 1.0], "2": [1250, 1504, 1.0]}}, open(HOME + "/state.json", "w"))
    cursor(100, 100)
    proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--grow-quiet", "--home", HOME, "--debug", "--frames-dir", FRAMES,
                             "--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999",
                             "--play-interval", "9999", "--keep-place", "--cursor-file", CUR,
                             "--nap-times", "1,2,3", "--nap-rest", "4", "--nap-alone", "2"] + list(extra))
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


runs = 0


def stop():
    global runs
    event("quit")
    time.sleep(2)
    runs += 1
    with open(HOME + "/pet_run%d.log" % runs, "w", encoding="utf-8") as f:     # the next start() clears pet.log
        f.write(log())


def cursor(x, y):
    with open(CUR + ".tmp", "w") as f:
        f.write("%d %d" % (x, y))
    os.replace(CUR + ".tmp", CUR)


def event(line):
    subprocess.run([BASH, "-c", 'echo "%s" >> "%s/event"' % (line, HOME)])


def log():
    return open(HOME + "/pet.log", encoding="utf-8", errors="replace").read()


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


def feet_x(tag):
    """The feet's x from the last 'walk to' / position lines is not logged: use the window's middle instead."""
    return None


def mid(h):
    l, t, r, b = rect(h)
    return (l + r) // 2


def lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


res = []


def check(n, ok, info=""):
    res.append(ok)
    print(("PASS " if ok else "FAIL ") + n + ("  " + str(info) if info != "" else ""), flush=True)


def wait_for(pat, n, secs):
    end = time.time() + secs
    while time.time() < end:
        m = re.search(pat, log()[n:])
        if m:
            return m
        time.sleep(0.1)
    return None


def feet(h):
    """(x, y, body px) from the window: the frames are 188 x 170 at 100 %, the feet at (69, 163)."""
    l, t, r, b = rect(h)
    k = (r - l) / 188.0
    return l + 69 * k, t + 163 * k, 100 * k


def doze_near(h, tag, dx, dy=0.5):
    """Rest the cursor dx body px beside its feet (dy body px up) and wait until it dozes."""
    fx, fy, px = feet(h)
    n = len(log())
    x0 = mid(h)
    cursor(fx + dx * px, fy - dy * px)
    m = wait_for(r"\] " + re.escape(tag) + r"play doze \[loop\]", n, 20)
    return n, m, x0


def away():
    """Wake whoever dozes (the cursor passes near each of them), then far away, and wait out the rest."""
    for h in pets():
        fx, fy, px = feet(h)
        cursor(fx, fy - px)
        time.sleep(0.35)
    cursor(100, 100)
    time.sleep(4.6)


start()
P = pets()
check("three pets", len(P) == 3, len(P))
big, midp, small = P

# 1: the cursor rests by the smallest: looks, comes closer, dozes off
n, m, x0 = doze_near(small, "pet2 ", -1.8)
L = log()[n:]
check("looks over to the cursor's side first", re.search(r"pet2 nap: looks at the cursor", L) is not None and "pet2 play nap_look_left" in L, L[-600:])
check("comes closer", "pet2 nap: comes closer" in L)
check("sits down, then dozes", "pet2 play doze_in" in L and m is not None)
x1 = mid(small)
check("came towards the cursor, not past it", x0 - 108 <= x1 < x0, (x0, x1))
check("not more than half a body", x0 - x1 <= 0.5 * 60 + 4, x0 - x1)
check("the others do not doze", "pet0 nap" not in L and "pet1 nap" not in L and re.search(r"(?<!pet\d )nap:", L) is None)
time.sleep(4)
L = log()[n:]
check("stays dozing while the cursor rests", "startled" not in L and "nap over" not in L)

# 2: the cursor moves: startled awake, back to idle
n = len(log())
fx, fy, px = feet(small)
cursor(fx - 1.0 * px, fy - 1.5 * px)
m = wait_for(r"pet2 play doze_startle", n, 1.5)
check("a move of the cursor near it startles it", m is not None, log()[n:][-400:])
m = wait_for(r"pet2 play idle", n, 3)
check("then idle again", m is not None)

# 3: rests right after: not again before the rest is over (4 s in the test)
n = len(log())
fx, fy, px = feet(small)
cursor(fx - 1.8 * px, fy - 0.5 * px)
time.sleep(2.5)
check("no 小剧场 again at once", "nap:" not in log()[n:], log()[n:][-300:])
time.sleep(5)
check("after the rest: again", "nap: looks at the cursor" in log()[n:])

# 4: the cursor moves before it dozes: it is over, no doze
n = len(log())
away()
n = len(log())
doze_tag = None
fx, fy, px = feet(big)
cursor(fx + 1.5 * px, fy - 0.5 * px)
m = wait_for(r"\] nap: looks at the cursor", n, 3)
cursor(fx + 1.5 * px, fy - 5 * px)
time.sleep(4)
L = log()[n:]
check("moved early: over without a doze", m is not None and "nap over (the cursor moved)" in L and "play doze_in" not in L, L[-500:])

# 5: far from all of them: nothing
n = len(log())
cursor(300, 300)
time.sleep(5)
check("far away: nothing", "nap:" not in log()[n:])

# 6: the big one dozes, a tool event comes: startled, then the work clip
away()
n, m, _ = doze_near(big, "", 1.5)
check("the big one dozes", m is not None and re.search(r"\] nap: dozes off", log()[n:]) is not None, log()[n:][-500:])
n = len(log())
event("read abcd1234")
m = wait_for(r"\] play doze_startle", n, 2)
m2 = wait_for(r"\] play work_read", n, 4)
check("an event startles it, then it works", m is not None and m2 is not None and m.start() < m2.start(), log()[n:][-500:])
event("stop abcd1234")
time.sleep(4)

# 7: a small one dozes, a tool event comes: the sign does not go to the dozing one
away()
n, m, _ = doze_near(small, "pet2 ", -1.8)
check("small dozes again", m is not None, log()[n:][-500:])
n = len(log())
event("run efgh5678")
time.sleep(3)
L = log()[n:]
check("the sign is not given to the dozing one", "pet2 play sign" not in L and "pet2 play doze_startle" not in L, L[-600:])
event("stop efgh5678")
time.sleep(1)
L = log()[n:]
# the end of the turn: a small one hops, maybe the dozing one -> startled first (either is fine), no exceptions
time.sleep(4)

# 8: click on a dozing one: startled
away()
n, m, _ = doze_near(midp, "pet1 ", 0.0, 1.6)
check("middle dozes", m is not None, log()[n:][-400:])
n = len(log())
l, t, r, b = rect(midp)
u.PostMessageW(midp, WM_LDOWN, 1, lp((r - l) // 2, (b - t) - 40))
time.sleep(0.1)
u.PostMessageW(midp, WM_LUP, 0, lp((r - l) // 2, (b - t) - 40))
m = wait_for(r"pet1 play doze_startle \[oneshot\] \(startled \(clicked\)\)", n, 2)
check("a click startles it", m is not None, log()[n:][-400:])
time.sleep(2)

# 9: hidden while dozing: shown again awake
away()
n, m, _ = doze_near(small, "pet2 ", -1.8)
check("small dozes (before hide)", m is not None, log()[n:][-500:])
n = len(log())
event("hide")
time.sleep(1.5)
event("show")
time.sleep(1.5)
L = log()[n:]
after = L[L.find("shown"):] if "shown" in L else ""
check("hidden and shown: awake, not straight back into it", "pet2 play idle" in after and "nap:" not in after, L[-500:])

# 11: 打瞌睡 by hand (menu / clawd do): the cursor moving does not wake it, it gets up by itself after ~8 s
away()
n = len(log())
event("doze")
m = wait_for(r"\] play doze \[loop\]", n, 4)
check("by hand: dozes", m is not None and re.search(r"\] play doze_in", log()[n:]) is not None, log()[n:][-400:])
for i in range(6):                             # the cursor wanders about
    cursor(200 + 90 * i, 300 + 40 * i)
    time.sleep(0.7)
m = wait_for(r"\] play doze_up \[oneshot\] \(dozed enough\)", n, 9)
L = log()[n:]
check("by hand: the cursor does not wake it, it gets up by itself", m is not None and "startled" not in L, L[-500:])
t_doze = re.search(r"(\d\d):(\d\d):(\d\d) \[\d+\] play doze \[loop\]", L)
t_up = re.search(r"(\d\d):(\d\d):(\d\d) \[\d+\] play doze_up", L)
secs = lambda g: int(g.group(1)) * 3600 + int(g.group(2)) * 60 + int(g.group(3))
check("by hand: about two nods long", t_doze is not None and t_up is not None and 7 <= secs(t_up) - secs(t_doze) <= 9,
      (t_doze.group(0) if t_doze else None, t_up.group(0) if t_up else None))
time.sleep(2)
n = len(log())
event("doze")
m = wait_for(r"\] play doze \[loop\]", n, 4)
l, t, r, b = rect(big)
u.PostMessageW(big, WM_LDOWN, 1, lp((r - l) // 2, (b - t) - 40))
time.sleep(0.1)
u.PostMessageW(big, WM_LUP, 0, lp((r - l) // 2, (b - t) - 40))
m = wait_for(r"\] play doze_startle \[oneshot\] \(startled \(clicked\)\)", n, 2)
check("by hand: a click startles it", m is not None, log()[n:][-400:])
time.sleep(2)

# 12: 打瞌睡 by hand while the big one works: it dozes, the next work event wakes it with a start
n = len(log())
event("read abcd1234")
time.sleep(3)
event("doze")
m = wait_for(r"\] play doze \[loop\]", n, 4)
time.sleep(1)
check("by hand while busy: dozes (no start at once)", m is not None and re.search(r"\] play doze_startle", log()[n:]) is None, log()[n:][-500:])
event("edit abcd1234")
m = wait_for(r"\] play doze_startle \[oneshot\] \(startled \(work\)\)", n, 2)
m2 = wait_for(r"\] play work_edit", n, 4)
check("by hand while busy: the next work event wakes it, then work", m is not None and m2 is not None, log()[n:][-500:])
event("stop abcd1234")
time.sleep(4)

# 13: the dozing small one is sent home (clawd 2), then the cursor moves: no trouble
away()
n, m, _ = doze_near(small, "pet2 ", -1.8)
check("small dozes (before clawd 2)", m is not None, log()[n:][-400:])
n = len(log())
event("family:2")
time.sleep(1.5)
cursor(500, 500)
time.sleep(1.5)
L = log()[n:]
check("sent home while dozing, then the cursor moves: no error", "Traceback" not in L and "tick (" not in L and len(pets()) == 2, L[-500:])
event("family:3")
time.sleep(4)

# 14: the cursor goes elsewhere: it dozes on, then gets up by itself (2 s in the test)
away()
small = pets()[2]
n, m, _ = doze_near(small, "pet2 ", -1.8)
check("dozes (before the cursor goes elsewhere)", m is not None, log()[n:][-400:])
n = len(log())
cursor(300, 300)
time.sleep(1.5)
L = log()[n:]
check("a move far away does not wake it", "startled" not in L and "dozes on" in L, L[-400:])
m = wait_for(r"pet2 play doze_up \[oneshot\] \(dozed enough\)", n, 9)
check("then it gets up by itself", m is not None, log()[n:][-400:])
time.sleep(2)
stop()
check("no exceptions", "Traceback" not in log())

# 10: dozing long enough: falls asleep for real with the family
start(["--sleep-after", "25"])
P = pets()
big, midp, small = P
n, m, _ = doze_near(small, "pet2 ", -1.8)
check("dozes (sleep run)", m is not None)
m = wait_for(r"pet2 fell asleep while dozing", n, 30)
check("dozing turns into sleep", m is not None, log()[n:][-500:])
time.sleep(1)
check("plays sleep", re.search(r"pet2 play sleep", log()[n:]) is not None)
stop()
check("no exceptions (sleep run)", "Traceback" not in log())
print("%d/%d passed" % (sum(res), len(res)))
