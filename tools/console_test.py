"""After a throw the others near come and pat it; far away nobody crosses the screen; picking it up again stops it."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the player's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
PET = os.path.join(T, 'clawd_pet.pyw')
FRAMES = os.path.join(T, 'frames')
HOME = S + "/consolehome"
os.makedirs(HOME, exist_ok=True)
for f in ("event", "state.json", "pet.log"):
    try:
        os.remove(os.path.join(HOME, f))
    except OSError:
        pass
json.dump({"x": 1400, "y": 1504, "scale": 1.0, "wanted": 1.0, "slots": [1, 2], "pos": {"1": [1250, 1504, 1.0], "2": [1130, 1504, 1.0]}}, open(HOME + "/state.json", "w"))
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
WM_MOVE, WM_LDOWN, WM_LUP = 0x0200, 0x0201, 0x0202
proc = subprocess.Popen(["C:/Python312/pythonw.exe", PET, "--grow-quiet", "--home", HOME, "--debug",
                         "--frames-dir", FRAMES, "--wander-interval", "999-999",
                         "--extra-interval", "999-999", "--combo-interval", "9999-9999", "--sleep-after", "9999", "--keep-place",
                         "--return-after", "2-2"])


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


def lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def fling(h, dx, dy, secs, steps=8):
    l, t, r, b = rect(h)
    cx, cy = (l + r) // 2, (t + b) // 2 + 20
    u.PostMessageW(h, WM_LDOWN, 1, lp(cx - l, cy - t))
    time.sleep(0.05)
    for i in range(1, steps + 1):
        tx, ty = cx + dx * i // steps, cy + dy * i // steps
        wl, wt, _, _ = rect(h)
        u.PostMessageW(h, WM_MOVE, 1, lp(tx - wl, ty - wt))
        time.sleep(secs / steps)
    wl, wt, _, _ = rect(h)
    u.PostMessageW(h, WM_LUP, 0, lp(cx + dx - wl, cy + dy - wt))


res = []


def check(n, ok, info=""):
    res.append(ok)
    print(("PASS " if ok else "FAIL ") + n + ("  " + str(info) if info != "" else ""), flush=True)


def reset():
    subprocess.run(["D:/git/Git/bin/bash.exe", "-c", 'echo dismiss >> "%s/event"' % HOME])


time.sleep(4)
P = pets()
check("three pets", len(P) == 3, len(P))
big, mid, small = P

# 1: the smallest thrown a little: the other two come and pat it, then go back
n = len(log())
fling(small, 0, -500, 0.2)
time.sleep(7)
L = log()[n:]
m = re.search(r"combo console: ([\w, ]+)", L)
check("near: a pat for the thrown one", m is not None and "pet0" in m.group(1) and "pet1" in m.group(1), m.group(0) if m else L[-500:])
check("near: pats played", "comfort_" in L)
check("near: the thrown one nods after", "consoled" in L)
time.sleep(8)
L = log()[n:]
check("near: combo over, they walk back", "combo console over" in L)

# 2: thrown across the screen: nobody follows
fling(small, -800, 0, 1.6, steps=32)       # slowly over to the left: a drop there
time.sleep(1.5)
n = len(log())
fling(small, 0, -500, 0.2)                  # then up and down again, far from the others
time.sleep(6)
L = log()[n:]
check("far: thrown and landed", "after a throw" in L)
check("far: nobody walks over", "combo console: pet" not in L, re.findall(r"combo console.*", L))

# 3: the big one thrown a little: the small ones come
time.sleep(2)
n = len(log())
fling(big, 0, -500, 0.2)
time.sleep(6)
L = log()[n:]
m = re.search(r"combo console: ([\w, ]+)", L)
check("big thrown: a small one comes", m is not None and ("pet1" in m.group(1) or "pet2" in m.group(1)), m.group(0) if m else L[-400:])
time.sleep(8)

# 4: picked up during the pat: it is off
n = len(log())
fling(big, 0, -500, 0.2)
deadline = time.time() + 6
while time.time() < deadline and "combo console:" not in log()[n:]:
    time.sleep(0.1)
time.sleep(0.6)
l, t, r, b = rect(big)
cx, cy = (l + r) // 2, (t + b) // 2 + 20
u.PostMessageW(big, WM_LDOWN, 1, lp(cx - l, cy - t))
time.sleep(0.05)
for i in range(1, 6):
    u.PostMessageW(big, WM_MOVE, 1, lp(cx - l + 6 * i, cy - t))
    time.sleep(0.05)
time.sleep(0.3)
u.PostMessageW(big, WM_LUP, 0, lp(cx - l + 30, cy - t))
time.sleep(1)
L = log()[n:]
check("picked up: the pat is off", re.search(r"combo console cancelled \((picked up|dragged)\)", L) is not None, re.findall(r"combo console.*", L))

subprocess.run(["D:/git/Git/bin/bash.exe", "-c", 'echo quit >> "%s/event"' % HOME])
time.sleep(2)
check("no exceptions", "Traceback" not in log())
print("%d/%d passed" % (sum(res), len(res)))
