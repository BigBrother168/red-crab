"""差事 (docs/差事设计.md): who does what when two things want the same pet.  Pairs of a state and an event:
who wins, the wind-down plays, nothing gets stuck, no errors.  A --home test pet; the cursor comes from a file
(--cursor-file), events by bash echo, clicks by PostMessage."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/chorehome"
CUR = HOME + "/cursor"
BASH = "D:/git/Git/bin/bash.exe"
os.makedirs(HOME, exist_ok=True)
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
WM_LDOWN, WM_LUP = 0x0201, 0x0202
proc = None
runs = 0
res = []
QUIET = ["--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999",
         "--play-interval", "9999", "--mimic-interval", "9999", "--peek-after", "9999", "--sleep-after", "9999"]


def start(extra=(), slots=(1, 2)):
    global proc
    for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak"):
        try:
            os.remove(os.path.join(HOME, f))
        except OSError:
            pass
    st = {"x": 1700, "y": 1504, "scale": 1.0, "wanted": 1.0, "slots": list(slots)}
    if slots:
        st["pos"] = {"1": [1450, 1504, 1.0], "2": [1250, 1504, 1.0]}
    json.dump(st, open(HOME + "/state.json", "w"))
    cursor(100, 100)
    args = list(QUIET)
    for i in range(0, len(extra), 2):          # an option given here replaces the quiet default
        if extra[i] in args:
            j = args.index(extra[i])
            del args[j:j + 2]
    proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--grow-quiet", "--home", HOME, "--debug", "--frames-dir", FRAMES,
                             "--keep-place", "--cursor-file", CUR, "--nap-times", "1,2,3", "--nap-rest", "4",
                             "--nap-alone", "60"] + args + list(extra))
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


def log():
    try:
        return open(HOME + "/pet.log", encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


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


def feet(h):
    """(x, y, body px) from the window: the frames are 188 x 170 at 100 %, the feet at (69, 163)."""
    l, t, r, b = rect(h)
    k = (r - l) / 188.0
    return l + 69 * k, t + 163 * k, 100 * k


def lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def click(h):
    l, t, r, b = rect(h)
    u.PostMessageW(h, WM_LDOWN, 1, lp((r - l) // 2, (b - t) - 40))
    time.sleep(0.1)
    u.PostMessageW(h, WM_LUP, 0, lp((r - l) // 2, (b - t) - 40))


def check(n, ok, info=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + ("  " + str(info) if not ok and info != "" else ""), flush=True)


def wait_for(pat, n, secs):
    end = time.time() + secs
    while time.time() < end:
        m = re.search(pat, log()[n:])
        if m:
            return m
        time.sleep(0.1)
    return None


def secs_of(line_match):
    h, m, s = (int(x) for x in re.match(r"(\d\d):(\d\d):(\d\d)", line_match).groups())
    return h * 3600 + m * 60 + s


def doze_small():
    """Rest the cursor by the smallest one until it dozes; -> log offset before."""
    h = pets()[2]
    fx, fy, px = feet(h)
    n = len(log())
    cursor(fx - 1.8 * px, fy - 0.5 * px)
    m = wait_for(r"pet2 play doze \[loop\]", n, 20)
    return n, m


def away():
    """Wake whoever dozes (the cursor passes near each of them), then far away, and wait out the rest."""
    for h in pets():
        fx, fy, px = feet(h)
        cursor(fx, fy - px)
        time.sleep(0.35)
    cursor(100, 100)
    time.sleep(4.6)


# ===================================================================== run 1: the 小剧场 keeps its pet
start()
P = pets()
check("three pets", len(P) == 3, len(P))
big, midp, small = P

# 1: 小剧场 picked (it looks over, nothing else yet), a tool: the sign goes elsewhere, the 小剧场 goes on
fx, fy, px = feet(small)
n = len(log())
cursor(fx - 1.8 * px, fy - 0.5 * px)
m = wait_for(r"pet2 nap: looks at the cursor", n, 6)
check("1 the cursor rests: pet2 looks over", m is not None, log()[n:][-400:])
event("listen s1")
time.sleep(0.2)
event("read s1")
m = wait_for(r"sign up: ", n, 3)
L = log()[n:]
check("1 a tool's sign while it looks over: not pet2's", m is not None and "pet2 play sign" not in L and "(pet2)" not in L, L[-500:])
m = wait_for(r"pet2 play doze \[loop\]", n, 8)
L = log()[n:]
check("1 ... and it still comes over and dozes", m is not None and "pet2 nap over" not in L, L[-600:])

# 2: it dozes, the turn ends (a short one: one small one hops): not the one dozing
n = len(log())
event("think s1")
time.sleep(0.3)
event("stop s1")
time.sleep(4)
L = log()[n:]
check("2 a turn's end: pet2 dozes on", "pet2 play doze_startle" not in L and "pet2 nap over" not in L, L[-600:])
check("2 ... no hop from pet2 (pet1 hops, or still holds the sign)", "pet2 play hop" not in L, L[-600:])
check("2 ... the 'done' sign is not pet2's", "(pet2)" not in L, L[-600:])

# 3: it dozes, a helper comes back: the note is brought by another one, or the big one nods
n = len(log())
event("listen s2")
time.sleep(0.3)
event("agent s2")
time.sleep(1.5)
event("agent_done s2")
time.sleep(5)
L = log()[n:]
note = re.search(r"combo note: ([^\n]*)", L)
check("3 a helper back: no note from pet2", note is None or "pet2" not in note.group(1), note.group(0) if note else "")
check("3 ... pet2 dozes on", "pet2 play doze_startle" not in L and "pet2 nap over" not in L, L[-600:])
time.sleep(6)

# 4: it dozes, errors pile up: comfort without pet2
n = len(log())
for i in range(3):
    event("fail s2")
    time.sleep(0.5)
time.sleep(4)
L = log()[n:]
comfort = re.search(r"combo comfort: ([^\n]*)", L)
check("4 errors: comfort comes", comfort is not None, L[-600:])
check("4 ... without pet2", comfort is not None and "pet2" not in comfort.group(1), comfort.group(0) if comfort else "")
check("4 ... pet2 dozes on", "pet2 play doze_startle" not in L and "pet2 nap over" not in L, L[-600:])
event("stop s2")
time.sleep(5)

# 5: your hand beats the 小剧场: a combo by hand takes it (with a start first)
n = len(log())
event("combo:celebrate_all")
m = wait_for(r"combo celebrate_all: ([^\n]*)", n, 3)
time.sleep(4)
L = log()[n:]
check("5 a combo by hand: pet2 is in it", m is not None and "pet2" in m.group(1), L[-600:])
check("5 ... startled first", "pet2 play doze_startle" in L, L[-600:])
check("5 ... the log says what was cut short", "chore: pet2 cut short 小剧场 for combo celebrate_all" in L, L[-600:])
time.sleep(3)

# 6: 小剧场 picked again (whoever is nearest now: after the combo they may still be on the way back); a click on
# another one is no business of it; a click on it: your hand
away()
time.sleep(8)                                  # back where they stood
P = pets()
fx, fy, px = feet(P[2])
n = len(log())
cursor(fx - 1.8 * px, fy - 0.5 * px)
m = wait_for(r"(pet\d )?nap: looks at the cursor", n, 10)
tag = (m.group(1) or "") if m else "pet2 "
who = int(tag[3]) if tag else 0
other = P[1] if who != 1 else P[2]
click(other)
time.sleep(1.5)
L = log()[n:]
check("6 a click on another one leaves the 小剧场 alone", m is not None and (tag + "nap over") not in L, (tag, L[-500:]))
m2 = wait_for(re.escape(tag) + r"play doze \[loop\]", n, 8)
check("6 ... it dozes", m2 is not None, log()[n:][-500:])
n = len(log())
click(P[who])
m2 = wait_for(re.escape(tag) + r"play doze_startle", n, 2)
check("6 a click on it: startled (your hand)", m2 is not None, log()[n:][-400:])
time.sleep(2)
stop()
check("run 1: no exceptions", "Traceback" not in log() and "tick (" not in log())

# ===================================================================== run 2: keeping it company, spaced out
start(["--mimic-interval", "2-2", "--show-gap", "6"])
P = pets()
big, midp, small = P
n = len(log())
event("listen s3")
t_end = time.time() + 34
copier_seen = None
while time.time() < t_end:
    event("read s3")                          # the same tool: its sign went up once and is down by the first copy
    for _ in range(10):
        time.sleep(0.2)
        c = re.findall(r"(pet\d) play work_\w+ \[\w+\] for \d+s \(copies\)", log()[n:])
        if c and copier_seen is None:
            copier_seen = c[-1]
            event("attention s3")             # a question while it copies: a fresh board, not in its hands
            time.sleep(1.5)
            break
L = log()[n:]
starts = [secs_of(x) for x in re.findall(r"(\d\d:\d\d:\d\d) \[\d+\] pet\d play work_\w+ \[\w+\] for \d+s \(copies\)", L)]
check("7 a small one copies the big one's tool", len(starts) >= 2, L[-600:])
gaps = [b - a for a, b in zip(starts, starts[1:])]
check("7 ... copies at least 3.5 + 6 s apart (show gap)", gaps and min(gaps) >= 9, gaps)
signs = re.findall(r"sign up: [^\n]*\((pet\d|over the big one)\)", L)
check("8 signs went up while it worked", len(signs) >= 1, L[-600:])
# every sign that went up while one copied: never in the copier's hands
copying, bad, during = set(), [], 0
for line in L.splitlines():
    m = re.search(r"(pet\d) play (\S+)", line)
    if m:
        if "(copies)" in line:
            copying.add(m.group(1))
        elif not m.group(2).startswith("work_"):     # anything else it plays: the copying is over
            copying.discard(m.group(1))
    m = re.search(r"sign up: .*\((pet\d|over the big one)\)", line)
    if m and copying:
        during += 1
        if m.group(1) in copying:
            bad.append(line)
check("8 ... signs went up while one copied", during >= 1, (copier_seen, during))
check("8 ... none in the hands of the one copying", not bad, bad)
event("stop s3")
time.sleep(4)

# 9: click the one that copies: the log says what it was cut short
n = len(log())
event("listen s4")
time.sleep(0.2)
event("read s4")
m = wait_for(r"(pet\d) play work_read \[\w+\] for \d+s \(copies\)", n, 12)
if m:
    h = midp if m.group(1) == "pet1" else small
    click(h)
    time.sleep(1)
L = log()[n:]
check("9 a click on the one that copies: logged as cut short", m is not None and ("chore: %s cut short copying for your hand" % m.group(1)) in L, L[-500:])
event("stop s4")
time.sleep(3)
stop()
check("run 2: no exceptions", "Traceback" not in log() and "tick (" not in log())

# ===================================================================== run 3: one big, one small (scenario B)
start(slots=(1,))
P = pets()
check("two pets", len(P) == 2, len(P))
big, midp = P
fx, fy, px = feet(midp)
n = len(log())
cursor(fx - 1.8 * px, fy - 0.5 * px)
m = wait_for(r"pet1 nap: looks at the cursor", n, 6)
event("listen s5")
time.sleep(0.2)
event("edit s5")
time.sleep(2)
L = log()[n:]
check("10 one small one, it looks over, a tool: the sign over the big one's head", m is not None and "sign up: " in L and "(over the big one)" in L, L[-500:])
m = wait_for(r"pet1 play doze \[loop\]", n, 8)
check("10 ... and it dozes", m is not None and "pet1 nap over" not in log()[n:], log()[n:][-500:])
n = len(log())
event("think s5")
time.sleep(0.3)
event("stop s5")
time.sleep(4)
L = log()[n:]
check("10 a turn's end: it dozes on, the sign over the big one", "pet1 play doze_startle" not in L and "(over the big one)" in L, L[-500:])
fx, fy, px = feet(midp)
n = len(log())
cursor(fx - 1.0 * px, fy - 1.5 * px)
m = wait_for(r"pet1 play doze_startle", n, 2)
check("10 the cursor moves: startled", m is not None, log()[n:][-400:])
time.sleep(2)
stop()
check("run 3: no exceptions", "Traceback" not in log() and "tick (" not in log())
print("%d/%d passed" % (sum(res), len(res)))
