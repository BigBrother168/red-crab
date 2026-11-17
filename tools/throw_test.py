"""Throw checks on a --home test pet, with posted mouse messages (like tools/edge_test.py)."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/throwhome"
os.makedirs(HOME, exist_ok=True)
for f in ("event", "state.json", "pet.log"):
    try:
        os.remove(os.path.join(HOME, f))
    except OSError:
        pass
json.dump({"scale": 1.0, "slots": []}, open(HOME + "/state.json", "w"))
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
WM_MOVE, WM_LDOWN, WM_LUP = 0x0200, 0x0201, 0x0202
proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--grow-quiet", "--home", HOME, "--debug",
                         "--frames-dir", FRAMES, "--wander-interval", "999-999",
                         "--extra-interval", "999-999", "--sleep-after", "9999"])
BASH = "D:/git/Git/bin/bash.exe"


def tok(t):
    subprocess.run([BASH, "-c", 'echo %s >> "%s/event"' % (t, HOME)], check=True)


def log():
    return open(HOME + "/pet.log", encoding="utf-8", errors="replace").read()


def find():
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def f(h, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == proc.pid and u.IsWindowVisible(h):
            out.append(h)
        return True
    u.EnumWindows(cb(f), 0)
    return out[0] if out else None


def rect():
    r = w.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def feet():
    m = re.findall(r"feet=\((\d+), (\d+)\)|landed at \((\d+), (\d+)\) after a throw", log())
    return m


def fling(dx, dy, secs, steps=8, pause=0.0, start=None):
    """Press on the body centre, move by (dx, dy) in secs, maybe pause, let go."""
    l, t, r, b = rect()
    cx, cy = (l + r) // 2, (t + b) // 2 + 20
    if start:
        cx, cy = start
    u.PostMessageW(hwnd, WM_LDOWN, 1, lp(cx - l, cy - t))
    time.sleep(0.05)
    for i in range(1, steps + 1):
        tx, ty = cx + dx * i // steps, cy + dy * i // steps
        wl, wt, _, _ = rect()
        u.PostMessageW(hwnd, WM_MOVE, 1, lp(tx - wl, ty - wt))
        time.sleep(secs / steps)
    if pause:
        time.sleep(pause)
    wl, wt, _, _ = rect()
    u.PostMessageW(hwnd, WM_LUP, 0, lp(cx + dx - wl, cy + dy - wt))


res = []


def check(n, ok, info=""):
    res.append(ok)
    print(("PASS " if ok else "FAIL ") + n + ("  " + str(info) if info != "" else ""), flush=True)


def wa():
    r = w.RECT()
    u.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)
    return r


time.sleep(3)
hwnd = find()
W = wa()
FLOOR = W.bottom - 24


def last_land():
    m = re.findall(r"landed at \((\d+), (\d+)\) after a throw", log())
    return tuple(map(int, m[-1])) if m else None


def n_thrown():
    return log().count("thrown (")


# put it in the middle of the screen first (a slow drag)
fling(-900, -600, 0.8, steps=16, pause=0.3)
time.sleep(1)
check("slow drag + pause: no throw", n_thrown() == 0)
l, t, r, b = rect()
check("stays where it was put (mid-air)", t < W.bottom - 500, (l, t, r, b))

# 1: a quick fling up and to the right
n = len(log())
fling(500, -300, 0.2)
time.sleep(3.5)
L = log()[n:]
check("fling: thrown", "thrown (" in L, L[:200])
check("two bounces", "bounce 1" in L and "bounce 2" in L)
p = last_land()
check("lands on the floor line", p is not None and abs(p[1] - FLOOR) <= 1, (p, FLOOR))
check("then squash and dizzy", "play squash" in L and "play dizzy" in L)
check("area follows", True)

# 2: hard to the right wall from the floor
n = len(log())
fling(1500, -500, 0.15)
time.sleep(4)
L = log()[n:]
l, t, r, b = rect()
p = last_land()
check("hard fling right: lands", "after a throw" in L, L[-300:])
check("stays on screen", p is not None and p[0] < W.right, (p, (l, t, r, b), W.right))

# 3: caught in the air, a click lets it fall on
n = len(log())
fling(-600, -900, 0.18)
time.sleep(0.25)
l, t, r, b = rect()
cx, cy = (l + r) // 2, (t + b) // 2 + 20
u.PostMessageW(hwnd, WM_LDOWN, 1, lp(cx - l, cy - t))
time.sleep(0.15)
l, t, _, _ = rect()
time.sleep(0.4)
l2, t2, _, _ = rect()
check("caught: holds still", (l2, t2) == (l, t), ((l, t), (l2, t2)))
u.PostMessageW(hwnd, WM_LUP, 0, lp(cx - l, cy - t))
time.sleep(2.5)
L = log()[n:]
check("let go in the air: falls on", "let go in the air" in L and "after a throw" in L.split("let go in the air")[-1])

# 4: thrown while at work: works again after
n = len(log())
tok("read")
time.sleep(1)
fling(300, -400, 0.15)
time.sleep(6)
L = log()[n:]
after = L.split("after a throw")[-1] if "after a throw" in L else ""
check("at work: thrown and lands", "thrown (" in L and "after a throw" in L)
check("at work: back to the work clip", "play work_read" in after, after[:400])
tok("stop")
time.sleep(2)

# 5: hide while in the air
n = len(log())
fling(-400, -700, 0.15)
time.sleep(0.2)
tok("hide")
time.sleep(0.6)
tok("show")
time.sleep(1)
l, t, r, b = rect()
check("hidden in the air: shown again standing", "fly" not in log()[n:].split("shown (")[-1][:50] and b <= W.bottom + 60, (l, t, r, b))
tok("quit")
time.sleep(2)
check("no exceptions", "Traceback" not in log())
print("%d/%d passed" % (sum(res), len(res)))
