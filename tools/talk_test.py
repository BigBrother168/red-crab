"""The conversations' circles: none for one conversation, a row from two on (its own window, ClawdTalks); an "at"
line says where a conversation is, a click on its circle brings that window to the front; a bye, a window gone or a
long silence takes a circle away.  A --home test pet.  Saves a picture of the row (t/talk_dots.png) if PIL is there."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/talkhome"
CUR = HOME + "/cursor"
BASH = "D:/git/Git/bin/bash.exe"
KEEP = 20                    # --talk-keep (longer than --talk-done-keep: a done circle goes for being done)
os.makedirs(HOME, exist_ok=True)
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.GetForegroundWindow.restype = w.HWND
u.FindWindowW.restype = w.HWND
WM_LDOWN, WM_LUP, WM_CLOSE = 0x0201, 0x0202, 0x0010
proc = None
res = []


def start():
    global proc
    for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak", "grow.json.bad", "grow.json.tmp", "talks.json"):
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
                             "--talk-keep", str(KEEP), "--talk-done-keep", "16"])
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
    print(("PASS " if ok else "FAIL ") + n + ("  " + str(info) if not ok and info != "" else ""), flush=True)


def dots():
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
    return out


def rect(h):
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def shot(name):
    try:
        from PIL import ImageGrab
    except ImportError:
        return
    d = dots()
    if d:
        l, t, r, b = rect(d[0])
        ImageGrab.grab(bbox=(l - 160, t - 220, r + 160, b + 20), all_screens=True).save(os.path.join(S, name))


start()
evs("listen aaaaaaaa", "read aaaaaaaa")
time.sleep(1.5)
d = dots()
check("1 one conversation: one circle", len(d) == 1, d)
w1 = (rect(d[0])[2] - rect(d[0])[0]) if d else 0
evs("listen bbbbbbbb", "edit bbbbbbbb")
time.sleep(1.5)
d = dots()
check("2 two conversations: a row of circles", len(d) == 1, d)
L = log()
check("2 numbered 1 and 2", "aaaaaaaa is number 1" in L and "bbbbbbbb is number 2" in L, L[-500:])
w2 = (rect(d[0])[2] - rect(d[0])[0]) if d else 0
check("2 one conversation's signs had no number, the second's has", "sign up: 在读文件" in L and re.search(r"sign (up|now): ② 在改代码", L), L[-900:])
n = len(L)
evs("listen cccccccc", "stop bbbbbbbb")
time.sleep(1.0)
evs("attention aaaaaaaa")
time.sleep(1.5)
L = log()[n:]
check("3 the signs say whose: ② done, ① waiting", re.search(r"sign (up|now): ② 做完了", L) and re.search(r"sign (up|now): ① ", L), L[-900:])
d = dots()
w3 = (rect(d[0])[2] - rect(d[0])[0]) if d else 0
check("3 a third: the row is wider", w3 > w2 > w1 > 0, (w1, w2, w3))
shot("talk_dots.png")

# a window of ours to jump to
target = subprocess.Popen(["C:/Python312/python.exe", "-c",
                           "import tkinter as t;r=t.Tk();r.title('talk-target');r.geometry('300x120+200+200');r.mainloop()"])
hwnd = None
for _ in range(40):
    time.sleep(0.25)
    hwnd = u.FindWindowW(None, "talk-target")
    if hwnd:
        break
n = len(log())
evs("at cccccccc %d test" % (hwnd or 0))
time.sleep(0.6)
check("4 an at line: where the conversation is", "cccccccc is at window %d (test)" % (hwnd or 0) in log()[n:], log()[n:])
if d:
    l, t, r, b = rect(d[0])
    x, y = (r - l) - (b - t) // 2, (b - t) // 2          # the last circle: number 3
    n = len(log())
    u.PostMessageW(d[0], WM_LDOWN, 1, (y << 16) | x)
    time.sleep(0.05)
    u.PostMessageW(d[0], WM_LUP, 0, (y << 16) | x)
    time.sleep(0.8)
    L = log()[n:]
    check("5 a click on its circle: that window to the front", "circle 3 (cccccccc) clicked: window %d to the front" % (hwnd or 0) in L, L)
    print("   (foreground now: %s, the target: %s%s)" % (u.GetForegroundWindow(), hwnd, "; refused" if "refused" in L else ""))
    u.ShowWindow(hwnd, 0)                                 # closed to the tray: still there, not shown
    time.sleep(0.3)
    n = len(log())
    u.PostMessageW(d[0], WM_LUP, 0, (y << 16) | x)
    time.sleep(0.8)
    L = log()[n:]
    check("5 its window hidden in the tray: seen as hidden (its app's link would bring it)", "circle 3 (cccccccc) clicked: window %d hidden" % (hwnd or 0) in L, L)
    u.ShowWindow(hwnd, 5)
    # DeepSeek Harness only hides its one window: shown again at once, no dsh://open (a second copy of the app, ~2 s)
    evs("at cccccccc %d deepseek" % (hwnd or 0))
    time.sleep(0.4)
    u.ShowWindow(hwnd, 0)
    time.sleep(0.3)
    n = len(log())
    u.PostMessageW(d[0], WM_LUP, 0, (y << 16) | x)
    time.sleep(0.8)
    L = log()[n:]
    check("5 DeepSeek's window in the tray: shown at once, no link", "clicked: window %d shown from the tray" % (hwnd or 0) in L
          and u.IsWindowVisible(hwnd) and "dsh://" not in L, L)
    u.ShowWindow(hwnd, 5)
    n = len(log())
    x = (b - t) // 2                                      # the first: no window known
    u.PostMessageW(d[0], WM_LUP, 0, (y << 16) | x)
    time.sleep(0.6)
    check("5 a circle whose window is not known: nothing", "circle 1 (aaaaaaaa) clicked: its window is not known" in log()[n:], log()[n:])
evs("at cccccccc %d test" % (hwnd or 0))     # a plain window again: DeepSeek may really run here, and while it does
time.sleep(0.4)                               # its conversation stays when its window goes (see 6b)
n = len(log())
target.terminate()
time.sleep(2.5)
check("6 its window gone: the circle goes", "cccccccc: its window is gone, its circle goes" in log()[n:], log()[n:])
check("6 two left: still a row", len(dots()) == 1)
n = len(log())
evs("bye aaaaaaaa")
time.sleep(1.5)
check("7 bye: one left, its circle stays", "aaaaaaaa said bye" in log()[n:] and len(dots()) == 1, log()[n:])
n = len(log())
time.sleep(KEEP + 2)
check("8 its turn over (green) a while: the circle goes", "bbbbbbbb: its turn is over" in log()[n:] and not dots(), log()[n:])
n = len(log())
evs("listen bbbbbbbb")                                    # back: the smallest number free (1), not the 2 it had
time.sleep(1.0)
check("8 back after its circle went: the smallest number free", "bbbbbbbb is number 1" in log()[n:], log()[n:])
evs("at dddddddd 0 test", "hello dddddddd", "listen dddddddd", "listen eeeeeeee")
time.sleep(1.5)
check("9 hidden: no circles", True)
evs("hide")
time.sleep(1.0)
check("9 the family hidden: the circles too", not dots())
evs("show")
time.sleep(1.5)
check("9 shown again: back", len(dots()) == 1)

# 10: the mouse on a circle: the conversation's name over it (this very conversation's, read where its agent keeps it)
evs("listen 652c3cd6")
time.sleep(1.5)
n = len(log())
d = dots()
if d:
    l, t, r, b = rect(d[0])
    for x in range(l + 4, r - 2, 6):          # the cursor (its file) across the row: each circle in turn
        with open(CUR, "w") as f:
            f.write("%d %d" % (x, (t + b) // 2))
        u.PostMessageW(d[0], 0x0200, 0, ((b - t) // 2 << 16) | (x - l))
        time.sleep(0.3)
    time.sleep(1.0)
L = log()[n:]
check("10 the mouse on its circle: the conversation's name", re.search(r"circle \d: 进度检查", L), L[-600:])
check("10 one with no name known: said so", "(no name found)" in L, L[-600:])
shot("talk_tip.png")
with open(CUR, "w") as f:
    f.write("100 100")                         # the mouse goes away
time.sleep(1.0)

# 11: Windows Terminal: the tab you typed in is remembered; a click on the circle selects that tab again
TABS = os.path.join(T, "clawd_tabs.ps1")


def tabs(*args):
    r = subprocess.run(["pwsh", "-NoProfile", "-File", TABS] + list(args), capture_output=True, text=True)
    return r.stdout.strip()


def term_windows():
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def f(h, _):
        buf = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, buf, 64)
        if buf.value == "CASCADIA_HOSTING_WINDOW_CLASS" and u.IsWindowVisible(h):
            out.append(h)
        return True
    u.EnumWindows(cb(f), 0)
    return out


before = set(term_windows())
subprocess.run(["cmd", "/c", "start", "", "wt.exe", "-w", "new", "--title", "talkA", ";", "new-tab", "--title", "talkB"])
wt = None
for _ in range(40):
    time.sleep(0.25)
    new = [h for h in term_windows() if h not in before]
    if new:
        wt = new[0]
        break
check("11 a test terminal of two tabs", wt is not None)
if wt:
    time.sleep(2.0)
    first = None
    u.SetForegroundWindow(wt)
    time.sleep(0.5)
    sel = tabs("selected", str(wt))            # the second tab is the selected one after start: take the first
    ids = []
    r = subprocess.run(["pwsh", "-NoProfile", "-Command",
                        "Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes;"
                        "$w=[Windows.Automation.AutomationElement]::FromHandle([IntPtr]%d);"
                        "$c=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElementIdentifiers]::ControlTypeProperty,[Windows.Automation.ControlType]::TabItem);"
                        "foreach($t in $w.FindAll([Windows.Automation.TreeScope]::Descendants,$c)){[string]::Join('.',$t.GetRuntimeId())}" % wt],
                       capture_output=True, text=True)
    ids = r.stdout.split()
    first = ids[0] if ids else None
    tabs("select", str(wt), first or "")
    time.sleep(0.5)
    fg_ok = u.GetForegroundWindow() == wt
    n = len(log())
    event("listen ffffffff")
    event("at ffffffff %d claude" % wt)    # you typed in its first tab
    time.sleep(3.0)
    L = log()[n:]
    if not fg_ok:
        print("   (the test terminal could not be put in front: the rest of 11 is skipped)")
    else:
        check("11 the tab you typed in is remembered", ("ffffffff is in tab %s of window %d" % (first, wt)) in L, L[-600:])
        tabs("select", str(wt), ids[1])        # you went to the other tab
        time.sleep(0.5)
        n = len(log())
        d = dots()
        if d:
            l, t, r, b = rect(d[0])
            for x in range(4, r - l, 6):       # click each circle till ffffffff's
                u.PostMessageW(d[0], WM_LDOWN, 1, ((b - t) // 2 << 16) | x)
                u.PostMessageW(d[0], WM_LUP, 0, ((b - t) // 2 << 16) | x)
                time.sleep(0.15)
                if "(ffffffff) clicked" in log()[n:]:
                    break
        time.sleep(3.0)
        L = log()[n:]
        check("11 a click on its circle: that tab selected again", "tab selected" in L and tabs("selected", str(wt)) == first, L[-600:])
    u.PostMessageW(wt, WM_CLOSE, 0, 0)
L = log()
event("quit")
time.sleep(2.5)
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
check("no exceptions", "Traceback" not in L, L[-1500:])
print("%d/%d passed" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
