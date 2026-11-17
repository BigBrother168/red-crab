"""The circles over a conversation's life: numbers, where a click goes, and what is kept when things close and open
again.  A --home test pet (restarted once), fake windows for the conversations, events as the agents' hooks and the
DeepSeek plugin write them.  The other agents' apps are not needed: their windows are stood in for.

  1 three agents: numbers 1 2 3; a click on each goes to its window (DeepSeek's: by its program, not found here)
  2 one done: its circle goes a while later; back without its "at" line yet: the smallest number free, a click still finds its window
  3 the pets restart: the circles come back with their numbers (talks.json), a click still goes there; one whose
    window closed while they were away does not come back
  4 its window closed: the circle goes and its work is over; resumed in another window: no circle lost to the old window, the new one known
  5 bye: gone; back: the smallest number free
  6 Codex: a thread of its own -> a circle; a sub-agent's thread -> its parent's circle; no thread (Codex's own
    background job) -> no circle, after a while unshown
  7 Esc in Claude Code (no hook): quiet and not interrupted -> still at work; its transcript ends with the
    interrupt -> no longer at work, its circle grey ("interrupted") and gone a while later; its next message: back
  8 nine at most
  9 Antigravity's stop button ("cut"): no longer at work, grey, gone a while later; waiting for you mid-turn: orange
    past the big one's sign (--attention-timeout), till its next word; waiting after its turn: not kept orange
  10 Codex's stop button (no hook): its rollout's last turn mark "turn_aborted" -> no longer at work; stopped and
    sent again at once (a new "task_started") -> still at work
  11 Claude: in its desktop app or a terminal, as its hook says (CLAUDE_CODE_ENTRYPOINT on the at line) or else its
    transcript ("entrypoint"); resumed in the other one: moves; clawd circles (circles.txt) tells where a click goes
"""
import ctypes, ctypes.wintypes as w, json, os, re, sqlite3, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/circlehome"
CUR = HOME + "/cursor"
BASH = "D:/git/Git/bin/bash.exe"
DONE_KEEP = 6                # --talk-done-keep
os.makedirs(HOME, exist_ok=True)
CODEX = HOME + "/codex"      # the pet's CODEX_HOME: a thread list of Codex's own (state_5.sqlite) with these threads
# ids end with the keys, as clawd_hook.py keys Codex's (the last 8); all of one minute, as they often are
CODEX_THREADS = [("01a1dcaa-0001-7000-8000-0000cccc3333", "vscode", "c"),
                 ("01a1dcaa-0002-7000-8000-0000dddd4444", "vscode", "d"),
                 ("01a1dcaa-0003-7000-8000-0000ffff0000", "vscode", "the parent"),
                 ("01a1dcaa-0004-7000-8000-0000abab0001",
                  '{"subagent":{"thread_spawn":{"parent_thread_id":"01a1dcaa-0003-7000-8000-0000ffff0000","depth":1}}}', "")]
os.makedirs(CODEX, exist_ok=True)
CLAUDE = HOME + "/claude"    # the pet's CLAUDE_CONFIG_DIR: transcripts of its own (projects/<folder>/<id>.jsonl)
os.makedirs(CLAUDE + "/projects/test", exist_ok=True)
if os.path.exists(CODEX + "/state_5.sqlite"):
    os.remove(CODEX + "/state_5.sqlite")
db = sqlite3.connect(CODEX + "/state_5.sqlite")
ROLL = CODEX + "/rollout-cdcd0010.jsonl"    # step 10's thread keeps its turns here
db.execute("create table threads (id text primary key, source text, title text, rollout_path text)")
db.executemany("insert into threads values (?, ?, ?, '')", CODEX_THREADS)
db.execute("insert into threads values ('01a1dcaa-0005-7000-8000-0000cdcd0010', 'vscode', 'step 10', ?)", (ROLL,))
db.commit()
db.close()
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.FindWindowW.restype = w.HWND
WM_LUP = 0x0202
proc = None
res = []
wins = {}


def start(fresh):
    global proc
    if fresh:
        for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak", "talks.json"):
            try:
                os.remove(os.path.join(HOME, f))
            except OSError:
                pass
        json.dump({"xp": 0, "level_shown": 99, "chances": 0}, open(HOME + "/grow.json", "w"))
        json.dump({"x": 1700, "y": 1400, "scale": 1.0, "wanted": 1.0, "slots": [1, 2], "lang": "zh",
                   "pos": {"1": [1450, 1400, 1.0], "2": [1250, 1400, 1.0]}}, open(HOME + "/state.json", "w"))
    with open(CUR, "w") as f:
        f.write("100 100")
    proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--home", HOME, "--debug", "--frames-dir", FRAMES,
                             "--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999",
                             "--play-interval", "9999", "--keep-place", "--cursor-file", CUR, "--nap-times", "1,2,3",
                             "--talk-keep", "600", "--talk-done-keep", str(DONE_KEEP), "--cut-quiet", "2", "--attention-timeout", "3"],
                            env=dict(os.environ, CODEX_HOME=CODEX, CLAUDE_CONFIG_DIR=CLAUDE,
                                     LOCALAPPDATA=HOME + "/local", APPDATA=HOME + "/roaming"))
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
    L = L[L.rfind("exit: ") + 1:]                    # this pet's (its circles from before come back as it starts)
    for m in re.finditer(r"conversation (\w{8})(?: is number (\d)| said bye|: [^\n]*(?:its circle goes|no circle))", L):
        if m.group(2):
            have[m.group(1)] = int(m.group(2))
        else:
            have.pop(m.group(1), None)
    return have


def click(session):
    """a click on that conversation's circle; -> what the log says about it"""
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


A, B, C, D = "aaaa1111", "bbbb2222", "cccc3333", "dddd4444"
start(True)
wa, wc = window("circle-a"), window("circle-c")
evs("listen %s" % A, "at %s %d claude" % (A, wa), "run %s" % A,
    "listen %s" % B, "at %s 0 deepseek" % B, "read %s" % B,
    "listen %s" % C, "at %s %d codex" % (C, wc), "edit %s" % C)
time.sleep(1.2)
have = numbers()
check("1 three agents: numbers 1 2 3 in order", have == {A: 1, B: 2, C: 3}, have)
L = click(A)
check("1 a click: its window", "clicked: window %d to the front" % wa in L, L)
L = click(C)
check("1 another: its window", "clicked: window %d to the front" % wc in L, L)
# (B, DeepSeek's, is not clicked: that would bring up the real DeepSeek window; talk_test covers its tray case)

# 2 done, gone a while later, back before its "at" line
evs("stop %s" % A)
time.sleep(DONE_KEEP + 2.5)
check("2 done: its circle goes a while later", "%s: its turn is over, its circle goes" % A in log(), log()[-600:])
evs("run %s" % C)                                    # the others go on
evs("listen %s" % A)                                 # its next message; its "at" line not yet
time.sleep(0.8)
have = numbers()
check("2 back: the smallest number free (1)", have.get(A) == 1, have)
L = click(A)
check("2 back before its at line: a click still finds its window", "clicked: window %d to the front" % wa in L, L)

# 3 the pets restart: the circles come back
evs("bye %s" % B)                                    # (DeepSeek's: whether it comes back depends on DeepSeek running here)
E = "eeee3333"
we = window("circle-e")
evs("listen %s" % E, "at %s %d claude cli -" % (E, we), "run %s" % E)
time.sleep(0.6)
have = numbers()
stop()
time.sleep(1)
close("circle-e")                                    # closed while the pets were away
talks = json.load(open(HOME + "/talks.json", encoding="utf-8"))
circ = talks.get("circles") or {}
check("3 talks.json keeps the circles and their numbers", all(circ.get(s, {}).get("n") == have[s] for s in (A, C, E)), (circ, have))
start(False)
back = numbers()
check("3 after a restart: the circles back with their numbers", back.get(A) == have[A] and back.get(C) == have[C], (back, have))
check("3 ... not one whose window closed meanwhile", E not in back, back)
evs("listen %s" % C, "run %s" % C)
time.sleep(1.0)
check("3 its next word: the same number", numbers().get(C) == have[C], numbers())
L = click(C)
check("3 after a restart: a click goes to its window", "clicked: window %d to the front" % wc in L, L)

# 4 a window closed while its circle is up: the circle goes
wd = window("circle-d")
evs("listen %s" % D, "at %s %d codex" % (D, wd), "run %s" % D)
time.sleep(0.8)
close("circle-d")
time.sleep(2.0)
check("4 its window closed: the circle goes", "%s: its window is gone, its circle goes" % D in log(), log()[-500:])
check("4 its window closed mid-turn, no bye: not at work any more", "%s: its window is gone: not at work any more" % D in log(), log()[-500:])
# ... and closed while its circle was away (done), then resumed in another window: back, the old window forgotten
evs("stop %s" % C)
time.sleep(DONE_KEEP + 2.5)
check("4 done: its circle went", C not in numbers(), numbers())
close("circle-c")
wc2 = window("circle-c2")
n = len(log())
evs("listen %s" % C, "run %s" % C)                  # resumed elsewhere, before its at line
time.sleep(2.2)
L = log()[n:]
have = numbers()
check("4 resumed: a circle (the old window forgotten, not the circle)", C in have and "its window is gone" not in L, L)
evs("at %s %d codex" % (C, wc2))
time.sleep(0.6)
L = click(C)
check("4 resumed: its new window", "clicked: window %d to the front" % wc2 in L, L)

# 5 bye, and back
evs("bye %s" % A)
time.sleep(0.8)
check("5 bye: its circle goes", A not in numbers(), numbers())
free = min(set(range(1, 10)) - set(numbers().values()))
evs("listen %s" % A, "at %s %d claude" % (A, wa), "run %s" % A)
time.sleep(0.8)
have = numbers()
check("5 back after bye: the smallest number free (%d)" % free, have.get(A) == free, have)

# 6 Codex: yours, a sub-agent's, its own background job
F, SUBA, JOB = "ffff0000", "abab0001", "9999aaaa"
wf = window("circle-f")
n = len(log())
evs("listen %s" % F, "at %s %d codex" % (F, wf), "run %s" % F,
    "listen %s" % SUBA, "at %s %d codex" % (SUBA, wf), "run %s" % SUBA,
    "listen %s" % JOB, "at %s %d codex" % (JOB, wf), "hello %s" % JOB, "think %s" % JOB)
time.sleep(1.5)
have = numbers()
check("6 Codex: its conversation has a circle", F in have, have)
check("6 Codex: a sub-agent's thread: no circle, its parent's", SUBA not in have and
      "%s: a Codex sub-agent of %s, no circle" % (SUBA, F) in log()[n:], log()[n:])
evs("stop %s" % SUBA)                                # a sub-agent done: its parent goes on
time.sleep(9.0)                                      # CODEX_WAIT
L = log()[n:]
have = numbers()
check("6 Codex: no thread of its own: its background job, no circle", JOB not in have and
      "%s: Codex's own background job, no circle" % JOB in L, L)
check("6 Codex: the parent still at work after its sub-agent's stop", F in have and "%s: its turn is over" % F not in L, L)
evs("think %s" % JOB)                                # its later words: nothing
time.sleep(0.8)
check("6 Codex: the job's later words make no circle", JOB not in numbers(), numbers())
evs("bye %s" % F)
time.sleep(0.6)
close("circle-f")

# 7 Esc in Claude Code: no hook; its transcript ends with the interrupt
G = "aaaa7777"
TR = CLAUDE + "/projects/test/%s-0000-4000-8000-000000000000.jsonl" % G


def say(*rows):
    with open(TR, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


open(TR, "w").close()
say({"type": "user", "message": {"role": "user", "content": "do it"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Bash"}]}},
    {"type": "last-prompt"})
wg = window("circle-g")
n = len(log())
evs("listen %s" % G, "at %s %d claude" % (G, wg), "run %s" % G)
time.sleep(5.0)                                      # quiet 2 s, looked at: a command running
check("7 quiet, not interrupted: still at work", "%s: interrupted" % G not in log()[n:] and G in numbers(), log()[n:])
say({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}},
    {"type": "last-prompt"}, {"type": "cost-state"})
time.sleep(6.5)                                      # the next look (every 5 s)
L = log()[n:]
check("7 its transcript ends with your Esc: not at work any more", "%s: interrupted (its transcript says so" % G in L, L)
time.sleep(DONE_KEEP + 2.0)
check("7 its circle goes a while later, as a done one", "%s: its turn is over, its circle goes" % G in log()[n:], log()[n:])
say({"type": "user", "message": {"role": "user", "content": "go on"}})
evs("listen %s" % G, "run %s" % G)
time.sleep(0.8)
check("7 its next message: a circle again", G in numbers(), numbers())
evs("bye %s" % G)
time.sleep(0.5)
close("circle-g")

# 8 nine at most
more = ["%s%04d" % ("eeee", i) for i in range(8)]
for s in more:
    evs("listen %s" % s, "run %s" % s, gap=0.15)
time.sleep(1.0)
have = numbers()
check("8 nine circles at most", len(have) == 9 and sorted(have.values()) == list(range(1, 10)), have)



def state(session):
    """the circle's state as the pet last logged it (--debug)"""
    L = log()
    i = L.rfind("circles: ")
    if i < 0:
        return None
    line = L[i:L.find("\n", i)]
    for part in line.split()[1:]:
        if part.endswith("(%s)" % session):
            return part.split("=", 1)[1].split("(", 1)[0]
    return None


# 9 Antigravity's stop button; waiting for you
for s in more:
    evs("bye %s" % s, gap=0.1)
evs("bye %s" % A, "bye %s" % C, gap=0.1)
time.sleep(0.8)
AG, W, W2 = "abcd0009", "abcd000a", "abcd000b"
n = len(log())
evs("listen %s" % AG, "run %s" % AG)
time.sleep(0.8)
check("9 Antigravity at work: busy", state(AG) == "busy", state(AG))
evs("cut %s" % AG)
time.sleep(0.8)
L = log()[n:]
check("9 Antigravity's stop button: not at work any more", "%s: interrupted (its agent says so" % AG in L, L)
check("9 ... its circle grey (interrupted)", state(AG) == "cut", state(AG))
time.sleep(DONE_KEEP + 2.0)
check("9 ... and gone a while later", "%s: its turn is over, its circle goes" % AG in log()[n:], log()[n:])
evs("listen %s" % W, "run %s" % W, "attention %s" % W)
time.sleep(0.8)
check("9 asked for a permission mid-turn: orange", state(W) == "wait", state(W))
time.sleep(4.5)                                      # past the big one's sign (3 s here)
check("9 ... still orange after the big one's sign is down", state(W) == "wait", state(W))
evs("think %s" % W)
time.sleep(0.8)
check("9 ... its next word: blue again", state(W) == "busy", state(W))
evs("listen %s" % W2, "run %s" % W2, "stop %s" % W2)
time.sleep(0.5)
evs("attention %s" % W2)                             # Claude Code's "waiting for your input" after its turn
time.sleep(3.8)                                      # the sign (3 s) down, its green (6 s) not yet gone
check("9 waiting after its turn is done: not kept orange", state(W2) == "done", state(W2))



def roll(*kinds):
    with open(ROLL, "a", encoding="utf-8") as f:
        for k in kinds:
            if k in ("task_started", "task_complete", "turn_aborted", "token_count"):
                f.write(json.dumps({"timestamp": "x", "type": "event_msg", "payload": {"type": k}}) + "\n")
            else:
                f.write(json.dumps({"timestamp": "x", "type": "response_item", "payload": {"type": k}}) + "\n")


# 10 Codex's stop button
X = "cdcd0010"
open(ROLL, "w").close()
roll("task_started", "message", "function_call")
n = len(log())
evs("listen %s" % X, "at %s 0 codex" % X, "run %s" % X)
time.sleep(5.0)
check("10 Codex quiet, at a command: still at work", "%s: interrupted" % X not in log()[n:] and state(X) == "busy", state(X))
roll("token_count", "message", "turn_aborted", "task_started", "message")    # stopped, and sent again at once
time.sleep(6.5)
check("10 stopped and sent again at once: still at work", "%s: interrupted" % X not in log()[n:] and state(X) == "busy", state(X))
roll("token_count", "turn_aborted")                  # stopped
time.sleep(6.5)
L = log()[n:]
check("10 Codex's rollout says turn_aborted: not at work any more", "%s: interrupted (its transcript says so" % X in L, L)
check("10 ... its circle grey", state(X) == "cut", state(X))
evs("bye %s" % X)

# 11 Claude: desktop app or terminal, told
H1, H2, H3 = "aaaa0011", "aaaa0012", "aaaa0013"
DESK = HOME + "/local/Claude-Data/claude-code-sessions/acc/org"
os.makedirs(DESK, exist_ok=True)
json.dump({"sessionId": "local_test11", "cliSessionId": H1 + "-0000-4000-8000-000000000000", "title": "desk one",
           "lastFocusedAt": 5}, open(DESK + "/local_test11.json", "w"))
for s, entry in ((H1, "claude-desktop"), (H3, "cli")):
    with open(CLAUDE + "/projects/test/%s-0000-4000-8000-000000000000.jsonl" % s, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "entrypoint": entry, "message": {"role": "user", "content": "hi"}}) + "\n")
for s in more:
    evs("bye %s" % s, gap=0.05)
w1, w2, w3 = window("circle-h1"), window("circle-h2"), window("circle-h3")
evs("listen %s" % H1, "at %s %d claude claude-desktop -" % (H1, w1), "run %s" % H1,
    "listen %s" % H2, "at %s %d claude cli -" % (H2, w2), "run %s" % H2,
    "listen %s" % H3, "at %s %d claude" % (H3, w3), "run %s" % H3)    # an older at line: its transcript tells


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


def line_of(rep, s):
    rows = rep.splitlines()
    for i, r in enumerate(rows):
        if "(%s)" % s in r:
            return r + " / " + (rows[i + 1] if i + 1 < len(rows) else "")
    return ""


time.sleep(0.8)
rep = report()
r1, r2, r3 = line_of(rep, H1), line_of(rep, H2), line_of(rep, H3)
check("11 its hook says desktop: Claude 桌面版, its link (or the one open)", "桌面版" in r1 and ("链接" in r1 or "正开着" in r1), rep)
check("11 its hook says cli: Claude 终端, its window, no link", "终端" in r2 and "终端窗口" in r2 and "链接" not in r2, rep)
check("11 no word from its hook: its transcript says cli", "终端" in r3 and "链接" not in r3, rep)
L = click(H2)
check("11 a click on the terminal one: its window, the way said", "clicked: window %d to the front" % w2 in L
      and "way: Claude terminal" in L and "opened" not in L, L)
evs("at %s %d claude cli -" % (H1, w3))              # the desktop one resumed in a terminal
time.sleep(0.6)
r1 = line_of(report(), H1)
check("11 resumed in a terminal: now a terminal's", "终端" in r1 and "链接" not in r1, r1)
check("11 ... said in the log", "%s: now in cli (was claude-desktop)" % H1 in log(), log()[-400:])

stop()
for name in list(wins):
    close(name)
print("%d/%d passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
