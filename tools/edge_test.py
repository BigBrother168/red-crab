# Drives one isolated test pet with posted mouse messages (the real cursor is not touched).
import ctypes, json, os, re, struct, subprocess, sys, time, zlib
from ctypes import wintypes as w

S = os.path.dirname(os.path.abspath(__file__))
T = os.path.dirname(S).replace('\\', '/')
HOME = os.path.join(S, 't', 'home')
os.makedirs(HOME, exist_ok=True)
for n in ('state.json', 'pet.log', 'event'):
    p = os.path.join(HOME, n)
    if os.path.exists(p):
        os.remove(p)
u = ctypes.WinDLL('user32', use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
WM_LDOWN, WM_LUP, WM_MOVE = 0x201, 0x202, 0x200
WA = (0, 0, 2560, 1528)
fails = []


def check(name, ok, detail=''):
    print('%-4s %s %s' % ('ok' if ok else 'FAIL', name, detail))
    if not ok:
        fails.append(name)


def idle_bbox(setdir):
    m = json.load(open(os.path.join(setdir, 'manifest.json'), encoding='utf-8'))
    W, H = m['width'], m['height']
    data = open(os.path.join(setdir, 'idle.frames'), 'rb').read()
    n = struct.unpack_from('<I', data, 0)[0]
    raw = zlib.decompress(data[4:4 + n])
    xs, ys = [], []
    for y in range(H):
        row = raw[y * W * 4 + 3:(y + 1) * W * 4:4]
        if any(row):
            ys.append(y)
            first = next(i for i, a in enumerate(row) if a)
            last = W - 1 - next(i for i, a in enumerate(reversed(row)) if a)
            xs += [first, last]
    return min(xs), min(ys), max(xs), max(ys)


BB = {100: idle_bbox(os.path.join(T, 'frames')), 300: idle_bbox(os.path.join(T, 'frames_hi'))}
proc = subprocess.Popen([r'C:\Python312\pythonw.exe', T + '/clawd_pet.pyw', "--grow-quiet",
                         '--home', HOME, '--frames-dir', os.path.join(T, 'frames'), '--debug', '--keep-place',
                         '--wander-interval', '1-2', '--extra-interval', '999-999', '--sleep-after', '9999'])


def find_hwnd():
    found = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    def f(h, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == proc.pid and u.IsWindowVisible(h):
            found.append(h)
        return True
    u.EnumWindows(cb(f), 0)
    return found[0] if found else None


hwnd = None
for _ in range(100):
    time.sleep(0.1)
    hwnd = find_hwnd()
    if hwnd:
        break
assert hwnd, 'no window'


def rect():
    r = w.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def settled():
    """The window once the pet has caught up with the moves posted so far.  A posted point is relative to the window
    as read here; read while the pet still lags behind, the release lands elsewhere and looks like a throw."""
    a = rect()
    for _ in range(25):
        time.sleep(0.04)
        b = rect()
        if b == a:
            return b
        a = b
    return a


def body(px):
    l, t, r, b = BB[px]
    wl, wt, _, _ = rect()
    return wl + l, wt + t, wl + r + 1, wt + b + 1


def token(t):
    with open(os.path.join(HOME, 'event'), 'a', encoding='utf-8', newline='\n') as f:
        f.write(t + '\n')


def lp(x, y):
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def drag(sx, sy, drop=True, steps=6):
    """Press on the body centre, move so that the press point goes to screen (sx, sy)."""
    l, t, r, b = rect()
    cx, cy = (l + r) // 2, (t + b) // 2
    u.PostMessageW(hwnd, WM_LDOWN, 1, lp(cx - l, cy - t))
    time.sleep(0.05)
    for i in range(1, steps + 1):
        tx, ty = cx + (sx - cx) * i // steps, cy + (sy - cy) * i // steps
        wl, wt, _, _ = rect()
        u.PostMessageW(hwnd, WM_MOVE, 1, lp(tx - wl, ty - wt))
        time.sleep(0.04)
    if drop:
        time.sleep(0.15)                   # a hand that puts it down stops first (else it is a throw)
        wl, wt, _, _ = settled()
        u.PostMessageW(hwnd, WM_LUP, 0, lp(sx - wl, sy - wt))


def inside(b):
    return b[0] >= WA[0] and b[1] >= WA[1] and b[2] <= WA[2] and b[3] <= WA[3]


def logtext():
    return open(os.path.join(HOME, 'pet.log'), encoding='utf-8', errors='replace').read()


def state():
    return json.load(open(os.path.join(HOME, 'state.json'), encoding='utf-8'))


try:
    time.sleep(0.6)
    for px in (100, 300):
        token('size:%d' % px)
        time.sleep(1.0)
        print('--- size', px, 'window', rect())
        # 1. dragged far past each edge: still on screen, mid-drag and after the drop
        for name, (sx, sy), idx, val in (('right', (3000, 700), 2, WA[2]), ('left', (-400, 700), 0, WA[0]),
                                         ('top', (1200, -400), 1, WA[1]), ('bottom', (1200, 1590), 3, WA[3])):
            drag(sx, sy, drop=False)
            time.sleep(0.1)
            mid = body(px)
            check('drag past %s stays inside mid-drag' % name, inside(mid), mid)
            wl, wt, _, _ = settled()
            u.PostMessageW(hwnd, WM_LUP, 0, lp(sx - wl, sy - wt))
            time.sleep(0.6)
            after = body(px)
            check('drop past %s flush with edge' % name, inside(after) and abs(after[idx] - val) <= 1, after)
            time.sleep(0.2)
        # corner
        drag(3000, -400)
        time.sleep(0.6)
        b = body(px)
        check('corner top-right', inside(b) and abs(b[2] - WA[2]) <= 1 and abs(b[1] - WA[1]) <= 1, b)
        # 2. dropped just inside the snap range / outside it
        reach = max(16, min(48, int(px * 0.2)))
        drag(1280, 700)
        time.sleep(0.6)
        cur = body(px)
        off = WA[2] - cur[2] - (reach - 6)          # leaves reach-6 px of gap at the right
        l, t, r, b_ = rect()
        drag((l + r) // 2 + off, (t + b_) // 2)
        time.sleep(0.6)
        b = body(px)
        check('dropped %d px from right edge snaps' % (reach - 6), abs(b[2] - WA[2]) <= 1, b)
        drag(1280, 700)
        time.sleep(0.6)
        cur = body(px)
        off = WA[2] - cur[2] - (reach + 30)
        l, t, r, b_ = rect()
        drag((l + r) // 2 + off, (t + b_) // 2)
        time.sleep(0.6)
        b = body(px)
        check('dropped %d px from right edge stays' % (reach + 30), abs(WA[2] - b[2] - (reach + 30)) <= 1, b)
        s = state()
        l, t, r, b_ = rect()
        print('     state', s, 'window', (l, t))

    # 3. resize on an edge
    token('size:100')
    time.sleep(1.0)
    drag(3000, 1590)
    time.sleep(0.6)
    b = body(100)
    check('bottom-right corner at 100%', abs(b[2] - WA[2]) <= 1 and abs(b[3] - WA[3]) <= 1, b)
    token('size:300')
    time.sleep(1.0)
    b = body(300)
    check('grow to 300% keeps the corner', abs(b[2] - WA[2]) <= 1 and abs(b[3] - WA[3]) <= 1, b)
    token('size:100')
    time.sleep(1.0)
    b = body(100)
    check('shrink to 100% keeps the corner', abs(b[2] - WA[2]) <= 1 and abs(b[3] - WA[3]) <= 1, b)
    drag(1000, 700)
    time.sleep(0.6)
    token('size:300')
    time.sleep(1.0)
    b = body(300)
    check('grow away from edges: stays inside', inside(b), b)
    token('size:100')
    time.sleep(1.0)

    # 4. wander into each side edge, several times
    seen = {}
    drag(3000, 1590)
    time.sleep(0.6)
    t0 = time.time()
    side_right = True
    worst = 0
    log0 = len(logtext())
    while time.time() - t0 < 180:   # random walks: about 1 in 3 reaches the edge, 75 s failed 1 run in 5
        b = body(100)
        worst = max(worst, WA[0] - b[0], b[2] - WA[2], b[3] - WA[3])
        txt = logtext()[log0:]
        nl, nr = txt.count('play turn_left'), txt.count('play turn_right')
        seen = {'turn_left': nl, 'turn_right': nr}
        if nl >= 2:
            break
        # stand 90 px from the edge that still needs a turn, then let it wander
        want_right = nl < 2
        if 'wander done' in txt[-400:] or time.time() - t0 < 1:
            l, t, r, bo = rect()
            bb = body(100)
            target_gap = 90
            dx = (WA[2] - bb[2] - target_gap) if want_right else (WA[0] + target_gap - bb[0])
            if abs(dx) > 1:
                drag((l + r) // 2 + dx, (t + bo) // 2)
                time.sleep(0.7)
        time.sleep(0.25)
    check('walked into the right edge and turned', seen.get('turn_left', 0) >= 2, seen)
    check('body never left the screen while wandering', worst <= 1, 'worst overflow %d px' % worst)
    txt = logtext()
    seq = re.findall(r'play (walk\w*|turn_\w+)', txt[log0:])
    print('     clip order:', seq[:24])
    bad = [i for i in range(len(seq) - 1) if seq[i] == 'turn_left' and seq[i + 1] not in ('walk_left',)
           or seq[i] == 'turn_right' and seq[i + 1] not in ('walk_right',)]
    check('every turn is followed by the walk in the new direction', not bad, bad)
    check('plain walk not used', 'walk' not in seq)

    # 5. internal clips are not event tokens; `walk` still works
    log1 = len(logtext())
    token('turn_left')
    token('walk_right')
    time.sleep(0.5)
    check('internal clips ignored as tokens', 'play turn_left' not in logtext()[log1:] and 'play walk_right' not in logtext()[log1:])

    # 6. saved off-screen state is corrected at startup
    token('quit')
    time.sleep(1.5)
    check('clean exit', proc.poll() is not None, proc.poll())
    json.dump({'x': 2555, 'y': 1520, 'scale': 1.0}, open(os.path.join(HOME, 'state.json'), 'w'))
    proc = subprocess.Popen([r'C:\Python312\pythonw.exe', T + '/clawd_pet.pyw', "--grow-quiet",
                             '--home', HOME, '--frames-dir', os.path.join(T, 'frames'), '--debug', '--keep-place'])
    for _ in range(100):
        time.sleep(0.1)
        hwnd = find_hwnd()
        if hwnd:
            break
    time.sleep(0.6)
    b = body(100)
    check('partly off-screen state fixed at startup', inside(b), b)
finally:
    token('quit')
    time.sleep(1.0)
    if proc.poll() is None:
        proc.kill()
    txt = logtext()
    errs = [l for l in txt.splitlines() if 'Traceback' in l or 'Error' in l or 'tick (' in l]
    check('no errors in test log', not errs, errs[:5])
    print('RESULT:', 'all passed' if not fails else 'FAILED: %s' % fails)
