"""The circles in the cases circle_test and talk_test leave out: words that make no circle, an error, a sub-agent's
work after the turn, a compaction, a minimised window, a tenth conversation, the row at the screen's edge, waiting
for you a long time (and Esc then), what a restart keeps, a broken talks.json, English, hidden, the signs' numbers.
A --home test pet at the right edge of the screen, fake windows for the conversations, events as the hooks write them.

  1 hello, attention, a sub-agent back, a compaction's end, a word with no conversation: no circle; clawd circles: none
  2 stopped by an error: red, gone a while later
  3 a sub-agent's work after its turn is done: still green, no new circle once it went; its next message: back
  4 a compaction in the middle of a turn: blue all along
  5 its window minimised: a click brings it back
  6 a tenth conversation: no circle; when one goes, its next word takes that number
  7 the row at the screen's right edge, nine circles: all on the screen
  8 waiting for you longer than a silent circle is kept: still orange; an idle one goes; Esc at that question after
    the big one stopped working on it (its transcript): grey
  9 a restart: orange stays orange, green stays green (and goes when its time is up), blue shows idle; one whose
    green was over while the pets were away does not come back
  10 a broken talks.json, or one of odd shapes: the pets start and circles come as ever
  11 English: clawd circles in English; hidden: no row, clawd circles still answers; shown: back
  12 the signs say a number only while there are two or more conversations
"""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/circleedge"
CUR = HOME + "/cursor"
BASH = "D:/git/Git/bin/bash.exe"
DONE_KEEP = 12               # --talk-done-keep (a restart takes about 6 s: a green circle outlives it)
KEEP = 15                    # --talk-keep
BUSY = 8                     # --busy-timeout
os.makedirs(HOME, exist_ok=True)
CLAUDE = HOME + "/claude"    # the pet's CLAUDE_CONFIG_DIR: transcripts of its own
os.makedirs(CLAUDE + "/projects/test", exist_ok=True)
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.FindWindowW.restype = w.HWND
u.MonitorFromWindow.restype = w.HANDLE
WM_LUP = 0x0202
proc = None
res = []
wins = {}


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]


WA = w.RECT()
u.SystemParametersInfoW(0x30, 0, ctypes.byref(WA), 0)        # SPI_GETWORKAREA: the main screen's, less the taskbar
X, Y = WA.right - 30, min(WA.bottom - 120, 1400)              # the big one at the right edge


def start(fresh):
    global proc
    if fresh:
        for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak", "talks.json", "circles.txt"):
            try:
                os.remove(os.path.join(HOME, f))
            except OSError:
                pass
        json.dump({"xp": 0, "level_shown": 99, "chances": 0}, open(HOME + "/grow.json", "w"))
        json.dump({"x": X, "y": Y, "scale": 1.0, "wanted": 1.0, "slots": [1, 2], "lang": "zh",
                   "pos": {"1": [X - 260, Y, 1.0], "2": [X - 460, Y, 1.0]}}, open(HOME + "/state.json", "w"))
    with open(CUR, "w") as f:
        f.write("100 100")
    proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--home", HOME, "--debug", "--frames-dir", FRAMES,
                             "--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999",
                             "--play-interval", "9999", "--keep-place", "--cursor-file", CUR, "--nap-times", "1,2,3",
                             "--talk-keep", str(KEEP), "--talk-done-keep", str(DONE_KEEP),
                             "--cut-quiet", "2", "--attention-timeout", "3", "--busy-timeout", str(BUSY)],
                            env=dict(os.environ, CLAUDE_CONFIG_DIR=CLAUDE, LOCALAPPDATA=HOME + "/local",
                                     APPDATA=HOME + "/roaming", CODEX_HOME=HOME + "/codex"))
    time.sleep(4)
    end = time.time() + 120
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
    event("quit")
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()


def event(line):
    subprocess.run([BASH, "-c", 'echo "%s" >> "%s/event"' % (line, HOME)])


def evs(*lines, gap=0.35):
    for l in lines:
        event(l)
        time.sleep(gap)


def log():
    try:
        return open(HOME + "/pet.log", encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def check(n, ok, info=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + ("  " + str(info)[-700:] if not ok and info != "" else ""), flush=True)


def row():
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def f(h, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(32)
        u.GetWindowTextW(h, buf, 32)
        if pid.value == proc.pid and u.IsWindowVisible(h) and buf.value == "ClawdTalks":
            out.append(h)
        return True
    u.EnumWindows(cb(f), 0)
    return out[0] if out else None


def numbers():
    """the numbers shown, from the log: who has which now"""
    have = {}
    L = log()
    L = L[L.rfind("exit: ") + 1:]
    for m in re.finditer(r"conversation (\w{8})(?: is number (\d)| said bye|: [^\n]*(?:its circle goes|no circle))", L):
        if m.group(2):
            have[m.group(1)] = int(m.group(2))
        else:
            have.pop(m.group(1), None)
    return have


def state(session):
    """the circle's state as the pet last logged it (--debug); None: no circle"""
    L = log()
    i = L.rfind("circles: ")
    j = L.rfind("exit: ")
    if i < 0 or i < j:
        return None
    line = L[i:L.find("\n", i)]
    for part in line.split()[1:]:
        if part.endswith("(%s)" % session):
            return part.split("=", 1)[1].split("(", 1)[0]
    return None


def click(session):
    have = numbers()
    order = sorted(have.values())
    h = row()
    if session not in have or h is None:
        return "(no circle for %s: %s)" % (session, have)
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    k = order.index(have[session])
    x, y = int((k + 0.5) * (r.right - r.left) / len(order)), (r.bottom - r.top) // 2
    n = len(log())
    u.PostMessageW(h, WM_LUP, 0, (y << 16) | x)
    time.sleep(0.8)
    return log()[n:]


def window(name):
    p = subprocess.Popen(["C:/Python312/python.exe", "-c",
                          "import tkinter as t;r=t.Tk();r.title('%s');r.geometry('260x90+120+120');r.mainloop()" % name])
    for _ in range(40):
        time.sleep(0.25)
        h = u.FindWindowW(None, name)
        if h:
            wins[name] = (p, h)
            return h
    return 0


def close(name):
    p, h = wins.pop(name)
    p.terminate()
    p.wait(5)


def report():
    path = HOME + "/circles.txt"
    if os.path.exists(path):
        os.remove(path)
    event("circles")
    for _ in range(30):
        time.sleep(0.2)
        if os.path.exists(path):
            time.sleep(0.1)
            return open(path, encoding="utf-8").read()
    return ""


def transcript(session, *rows, new=False):
    with open(CLAUDE + "/projects/test/%s-0000-4000-8000-000000000000.jsonl" % session, "w" if new else "a",
              encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def byes(*sessions):
    for s in sessions:
        event("bye %s" % s)
        time.sleep(0.1)
    time.sleep(0.8)


start(True)

# 1 words that make no circle
n = len(log())
evs("hello aaaa0001", "attention aaaa0002", "agent_done aaaa0003", "compact_end aaaa0004", "run", "read -")
time.sleep(0.8)
check("1 hello, attention, a sub-agent back, a compaction's end, a word of no conversation: no circle",
      not numbers() and row() is None, (numbers(), log()[n:]))
check("1 clawd circles: none now", "现在没有圆圈" in report())

# 2 stopped by an error
E1 = "eeee0002"
evs("listen %s" % E1, "run %s" % E1, "stopfail %s" % E1)
time.sleep(0.8)
check("2 stopped by an error: red", state(E1) == "error", state(E1))
time.sleep(DONE_KEEP + 2.0)
check("2 ... gone a while later", "%s: its turn is over, its circle goes" % E1 in log(), log()[-400:])

# 3 a sub-agent's work after the turn is done
G1 = "eeee0003"
evs("listen %s" % G1, "run %s" % G1, "stop %s" % G1)
time.sleep(0.6)
evs("run %s" % G1, "think %s" % G1)                   # a background sub-agent of that conversation at work
time.sleep(0.8)
check("3 a sub-agent at work after the turn: its circle still green", state(G1) == "done", state(G1))
time.sleep(DONE_KEEP + 2.0)
check("3 ... and gone when its time is up", G1 not in numbers(), numbers())
evs("read %s" % G1, "think %s" % G1)
time.sleep(0.8)
check("3 the sub-agent's later work: no new circle", G1 not in numbers(), numbers())
evs("listen %s" % G1)
time.sleep(0.6)
check("3 its next message: a circle again", G1 in numbers() and state(G1) == "busy", (numbers(), state(G1)))
byes(G1)

# 4 a compaction in the middle of a turn
K1 = "eeee0004"
evs("listen %s" % K1, "run %s" % K1, "compact %s" % K1)
time.sleep(0.6)
c1 = state(K1)
evs("compact_end %s" % K1)
time.sleep(0.6)
check("4 a compaction mid-turn: blue while it compacts and after", c1 == "busy" and state(K1) == "busy", (c1, state(K1)))
byes(K1)

# 5 its window minimised
M1 = "eeee0005"
wm = window("edge-m")
evs("listen %s" % M1, "at %s %d claude cli -" % (M1, wm), "run %s" % M1)
time.sleep(0.6)
u.ShowWindow(wm, 6)                                   # SW_MINIMIZE
time.sleep(0.5)
was = u.IsIconic(wm)
L = click(M1)
time.sleep(0.4)
check("5 its window minimised: a click brings it back", was and not u.IsIconic(wm) and
      "clicked: window %d to the front" % wm in L, (was, u.IsIconic(wm), L))
byes(M1)
close("edge-m")

# 6 a tenth conversation; 7 the row at the edge
nine = ["eeee01%02d" % i for i in range(9)]
TEN = "eeee0110"
for s in nine + [TEN]:
    evs("listen %s" % s, "run %s" % s, gap=0.15)
time.sleep(1.0)
have = numbers()
check("6 ten conversations: nine circles, the tenth none", len(have) == 9 and TEN not in have, have)
h = row()
r = w.RECT()
if h:
    u.GetWindowRect(h, ctypes.byref(r))
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    u.GetMonitorInfoW(u.MonitorFromWindow(h, 2), ctypes.byref(mi))
    wa = mi.rcWork
    print("   (the row %d..%d, %d..%d; its screen's work area %d..%d, %d..%d; the big one's x %d)"
          % (r.left, r.right, r.top, r.bottom, wa.left, wa.right, wa.top, wa.bottom, X))
    check("7 at the screen's right edge, nine circles: all on the screen", wa.left <= r.left and r.right <= wa.right
          and wa.top <= r.top and r.bottom <= wa.bottom, (r.left, r.right, wa.left, wa.right))
else:
    check("7 at the screen's right edge, nine circles: all on the screen", False, "no row")
k = have.get(nine[4])
byes(nine[4])
evs("think %s" % TEN)                                 # the tenth goes on working
time.sleep(0.8)
check("6 one goes: the tenth's next word takes its number (%s)" % k, numbers().get(TEN) == k, numbers())
byes(*[s for s in nine if s != nine[4]] + [TEN])

# 8 waiting for you a long time
W1, I1 = "eeee0008", "eeee0018"
transcript(W1, {"type": "user", "message": {"role": "user", "content": "do it"}},
           {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Bash"}]}}, new=True)
ww = window("edge-w")
n = len(log())
evs("listen %s" % W1, "at %s %d claude cli -" % (W1, ww), "run %s" % W1, "attention %s" % W1,
    "listen %s" % I1, "run %s" % I1, "think %s" % I1)      # its tool over, then nothing (a running one: at work on)
time.sleep(KEEP + 3.0)
L = log()[n:]
check("8 the big one stopped working on them (its %d s for a turn that says nothing)" % BUSY,
      L.count("busy timed out") >= 2, L)
check("8 an idle one silent longer than a circle is kept: gone", "%s: long silent, its circle goes" % I1 in L, L)
check("8 waiting for you longer than that: still there, orange", W1 in numbers() and state(W1) == "wait", (state(W1), L))
transcript(W1, {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user for tool use]"}]}})
time.sleep(7.0)
L = log()[n:]
check("8 Esc at that question then (its transcript): not waiting, grey", "%s: interrupted" % W1 in L and state(W1) == "cut", (state(W1), L[-600:]))
byes(W1)
close("edge-w")

# 9 a restart: what it keeps
O1, D1, B1, X1 = "eeee0009", "eeee0019", "eeee0029", "eeee0039"
wo, wd, wb = window("edge-o"), window("edge-d"), window("edge-b")
evs("listen %s" % O1, "at %s %d claude cli -" % (O1, wo), "run %s" % O1, "attention %s" % O1,
    "listen %s" % B1, "at %s %d claude cli -" % (B1, wb), "run %s" % B1,
    "listen %s" % D1, "at %s %d claude cli -" % (D1, wd), "run %s" % D1, "stop %s" % D1)
time.sleep(1.2)
before = (state(O1), state(D1), state(B1))
stop()
time.sleep(0.5)
talks = json.load(open(HOME + "/talks.json", encoding="utf-8"))
wall = time.time()
talks["where"][X1] = list(talks["where"][D1])         # its window still there, but its green was over meanwhile
talks["circles"][X1] = {"n": 8, "end": "done", "wait": False, "end_at": wall - 100, "seen": wall - 100}
json.dump(talks, open(HOME + "/talks.json", "w", encoding="utf-8"))
start(False)
time.sleep(0.5)
after = (state(O1), state(D1), state(B1))
check("9 before a restart: orange, green, blue", before == ("wait", "done", "busy"), before)
check("9 after it: orange stays orange, green stays green, blue shows idle", after == ("wait", "done", "idle"), after)
check("9 ... not one whose green was over while the pets were away", X1 not in numbers(), numbers())
time.sleep(DONE_KEEP)
check("9 the green one goes when its time is up", D1 not in numbers(), numbers())
check("9 the orange one from before the restart: goes as a silent one would (what it did meanwhile, nobody said)",
      O1 not in numbers(), numbers())
byes(O1, B1, D1)
for nm in ("edge-o", "edge-d", "edge-b"):
    close(nm)

# 10 a broken talks.json
for i, broken in enumerate(("{not json", json.dumps({"where": {"aaaa0010": 5}, "tab": [], "circles": [1]}),
                            json.dumps({"where": {}, "circles": {"bbbb0010": "x", "cccc0010": {"n": "one"}, "dddd0010": {"n": 99}}}))):
    stop()
    open(HOME + "/talks.json", "w").write(broken)
    start(False)
    Z = "eeee10%02d" % i
    evs("listen %s" % Z, "run %s" % Z)
    time.sleep(0.8)
    check("10 talks.json %s: the pets start, a conversation gets circle 1" % ("not JSON", "of odd shapes", "with odd circles")[i],
          proc.poll() is None and numbers().get(Z) == 1 and row() is not None, (proc.poll(), numbers()))
    byes(Z)

# 11 English; hidden
L1 = "eeee0011"
evs("listen %s" % L1, "run %s" % L1, "lang:en")
time.sleep(0.8)
rep = report()
check("11 English: clawd circles in English", "a click:" in rep and "working" in rep and "点了" not in rep, rep)
evs("lang:zh", "hide")
time.sleep(0.8)
check("11 hidden: no row", row() is None)
check("11 hidden: clawd circles still answers", "(%s)" % L1 in report())
evs("show")
time.sleep(1.5)
check("11 shown again: the row back", row() is not None)
byes(L1)

# 12 the signs' numbers
S1, S2 = "eeee0012", "eeee0022"
n = len(log())
evs("listen %s" % S1, "read %s" % S1, gap=0.6)
evs("listen %s" % S2, "edit %s" % S2, gap=0.6)
time.sleep(0.6)
L = log()[n:]
check("12 one conversation: its sign has no number", re.search(r"sign (up|now): 在读文件", L), L[-800:])
check("12 two: the second's sign has its number", re.search(r"sign (up|now): [\u2460-\u2468] 在改代码", L), L[-800:])
byes(S2)
time.sleep(4.5)                                       # a tool's sign just down: none for SIGN_GAP (4 s)
n = len(log())
evs("run %s" % S1, gap=0.8)
L = log()[n:]
check("12 back to one: no number again", re.search(r"sign (up|now): 在跑命令", L), L[-800:])
byes(S1)

L = log()
check("no exceptions (a broken talks.json is one line in the log)", "Traceback" not in L and "talks.json not read" in L,
      [L[m.start():m.start() + 400] for m in re.finditer("Traceback", L)])
stop()
for name in list(wins):
    close(name)
print("%d/%d passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
