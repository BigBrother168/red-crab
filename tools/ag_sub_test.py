"""Antigravity's sub-agents and the circles' numbers (2026-11-15: a sub-agent took a circle of its own; the
conversation that sent it lost its circle while it worked; after a restart a sub-agent came back as a circle).
Read from the real Antigravity records on this machine (~/.gemini/antigravity/conversations): c74c6e7c and
cf3b158d are conversations; 9046b1ab, e940dfcf, d2851501 and 0065f0a0 are sub-agents sent by c74c6e7c.

  1 a sub-agent with its "at" line: no circle; its conversation's turn ends as it is sent out, its work makes that
    conversation blue again, its end green
  2 a sub-agent with no "at" line seen: no circle (looked up in its file), its conversation at work again, then done
  3 a session the records do not know (no "at" line): a circle, the smallest number free; it stays
  4 a Claude conversation: the next number; one goes, the next new one takes its number
  5 a restart with a sub-agent's circle saved (as before the fix): it goes; the others come back; a sub-agent's work
    then makes its conversation blue, its end green
  6 an Antigravity conversation of yours (not a sub-agent): a circle
"""
import ctypes, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/agsub"
CUR = HOME + "/cursor"
BASH = "D:/git/Git/bin/bash.exe"
os.makedirs(HOME, exist_ok=True)
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
proc = None
res = []
wins = []
AGDIR = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "conversations")
PARENT, OTHER = "c74c6e7c", "cf3b158d"
SUB_AT, SUB_NO_AT, SUB_SAVED, SUB_AFTER = "9046b1ab", "e940dfcf", "d2851501", "0065f0a0"


def start(fresh):
    global proc
    if fresh:
        for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak", "talks.json", "circles.txt"):
            try:
                os.remove(os.path.join(HOME, f))
            except OSError:
                pass
        json.dump({"xp": 0, "level_shown": 99, "chances": 0}, open(HOME + "/grow.json", "w"))
        json.dump({"x": 1700, "y": 1400, "scale": 1.0, "wanted": 1.0, "slots": [], "lang": "zh"}, open(HOME + "/state.json", "w"))
    with open(CUR, "w") as f:
        f.write("100 100")
    proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--home", HOME, "--debug", "--frames-dir", FRAMES,
                             "--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999",
                             "--play-interval", "9999", "--keep-place", "--cursor-file", CUR,
                             "--talk-keep", "600", "--talk-done-keep", "120", "--busy-timeout", "600"],
                            env=dict(os.environ, CLAUDE_CONFIG_DIR=HOME + "/claude", LOCALAPPDATA=HOME + "/local",
                                     APPDATA=HOME + "/roaming", CODEX_HOME=HOME + "/codex"))
    time.sleep(5)


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


def circles():
    """{session: (number, state)} as the pet last logged them (--debug)"""
    L = log()
    i, j = L.rfind("circles: "), L.rfind("exit: ")
    if i < 0 or i < j:
        return {}
    out = {}
    for part in L[i:L.find("\n", i)].split()[1:]:
        m = re.match(r"(\d)=(\w+)\((\w{8})\)", part)
        if m:
            out[m.group(3)] = (int(m.group(1)), m.group(2))
    return out


def window(name):
    p = subprocess.Popen(["C:/Python312/python.exe", "-c",
                          "import tkinter as t;r=t.Tk();r.title('%s');r.geometry('260x90+120+120');r.mainloop()" % name])
    wins.append(p)
    for _ in range(40):
        time.sleep(0.25)
        h = u.FindWindowW(None, name)
        if h:
            return h
    return 0


if not all(any(f.startswith(s) for f in os.listdir(AGDIR)) for s in (PARENT, OTHER, SUB_AT, SUB_NO_AT, SUB_SAVED, SUB_AFTER)):
    print("SKIP: the Antigravity records this test reads are not on this machine")
    sys.exit(0)
W = window("agsub-w")
C = window("agsub-claude")
start(True)

# 1 a sub-agent with its "at" line
evs("listen %s" % PARENT, "at %s %d antigravity" % (PARENT, W), "web %s" % PARENT, "think %s" % PARENT)
time.sleep(1.5)
check("1 its conversation: circle 1, at work", circles().get(PARENT) == (1, "busy"), circles())
evs("agent_done %s" % PARENT, "hello %s" % SUB_AT, "at %s %d antigravity" % (SUB_AT, W), "listen %s" % SUB_AT, "stop %s" % PARENT)
time.sleep(2.5)
L = log()
check("1 the sub-agent: told apart, no circle", re.search(r"%s: an Antigravity sub-agent of %s.*no circle" % (SUB_AT, PARENT), L)
      and SUB_AT not in circles(), (circles(), L[-600:]))
check("1 its conversation's turn over as it went out: green", circles().get(PARENT) == (1, "done"), circles())
evs("web %s" % SUB_AT, "think %s" % SUB_AT)
time.sleep(1.5)
check("1 the sub-agent at work: its conversation blue again, still the only circle",
      circles() == {PARENT: (1, "busy")}, circles())
evs("stop %s" % SUB_AT)
time.sleep(1.5)
check("1 the sub-agent done: its conversation green", circles() == {PARENT: (1, "done")}, (circles(), log()[-400:]))

# 2 a sub-agent with no "at" line seen
evs("web %s" % SUB_NO_AT, "think %s" % SUB_NO_AT)
time.sleep(2)
L = log()
check("2 no \"at\" line: looked up in its file, no circle, its conversation blue",
      "%s: an Antigravity sub-agent of %s (from its file)" % (SUB_NO_AT, PARENT) in L and circles() == {PARENT: (1, "busy")},
      (circles(), L[-500:]))
evs("stop %s" % SUB_NO_AT)
time.sleep(1.5)
check("2 its end: its conversation green", circles() == {PARENT: (1, "done")}, circles())

# 3 a session the records do not know
evs("listen deadbeef", "run deadbeef")
time.sleep(3)
check("3 not in Antigravity's records: a circle of its own, number 2, kept", circles().get("deadbeef") == (2, "busy"), circles())

# 4 a Claude conversation; numbers taken and given back
evs("listen 5c5c5c5c", "at 5c5c5c5c %d claude" % C, "read 5c5c5c5c")
time.sleep(1.5)
check("4 a Claude conversation: number 3", circles().get("5c5c5c5c") == (3, "busy"), circles())
evs("bye deadbeef")
time.sleep(1)
evs("listen 6d6d6d6d", "at 6d6d6d6d %d claude" % C, "run 6d6d6d6d")
time.sleep(1.5)
c = circles()
check("4 one goes, the next new one takes its number (2)", "deadbeef" not in c and c.get("6d6d6d6d") == (2, "busy"), c)

# 5 a restart with a sub-agent's circle saved
stop()
time.sleep(1)
d = json.load(open(HOME + "/talks.json", encoding="utf-8"))
d["circles"][SUB_SAVED] = {"n": 4, "end": None, "wait": False, "end_at": None, "seen": time.time()}
d["where"][SUB_SAVED] = [W, "", "TkTopLevel", "", ""]      # a click on it had remembered its app's window, no agent
json.dump(d, open(HOME + "/talks.json", "w", encoding="utf-8"))
start(False)
time.sleep(2)
c = circles()
L = log()
check("5 restarted: the sub-agent's saved circle goes", "%s: an Antigravity sub-agent of %s (from its file)" % (SUB_SAVED, PARENT) in L
      and SUB_SAVED not in c, (c, L[-600:]))
check("5 ... the others back with their numbers", c.get(PARENT, (0,))[0] == 1 and c.get("6d6d6d6d", (0,))[0] == 2
      and c.get("5c5c5c5c", (0,))[0] == 3, c)
evs("web %s" % SUB_AFTER, "think %s" % SUB_AFTER)
time.sleep(2)
check("5 a sub-agent at work after the restart: its conversation blue, no circle of its own",
      circles().get(PARENT) == (1, "busy") and SUB_AFTER not in circles(), circles())
evs("stop %s" % SUB_AFTER)
time.sleep(1.5)
check("5 ... its end: its conversation green", circles().get(PARENT) == (1, "done"), circles())

# 6 an Antigravity conversation of yours
evs("hello %s" % OTHER, "at %s %d antigravity" % (OTHER, W), "listen %s" % OTHER, "web %s" % OTHER, "think %s" % OTHER)
time.sleep(2.5)
check("6 an Antigravity conversation of yours: a circle (number 4)", circles().get(OTHER) == (4, "busy"), circles())

L = log()
stop()
for p in wins:
    p.terminate()
check("no exceptions", "Traceback" not in L, L[L.find("Traceback"):][:800] if "Traceback" in L else "")
print("%d/%d passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
