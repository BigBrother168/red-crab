# Left edge only: stand 90 px from it, wander until two turns were seen; plus the walk seam check.
import ctypes, json, os, re, struct, subprocess, time, zlib
from ctypes import wintypes as w

S = os.path.dirname(os.path.abspath(__file__))
T = os.path.dirname(S).replace('\\', '/')
HOME = os.path.join(S, 't', 'home2')
os.makedirs(HOME, exist_ok=True)
for n in ('state.json', 'pet.log', 'event'):
    p = os.path.join(HOME, n)
    if os.path.exists(p):
        os.remove(p)

# frames 0 and WALK_SEAM of the walk clips must be pixel-identical
for setname in ('frames', 'frames_hi'):
    for clip in ('walk_left', 'walk_right'):
        data = open(os.path.join(T, setname, clip + '.frames'), 'rb').read()
        off, fr = 0, []
        while off < len(data):
            n = struct.unpack_from('<I', data, off)[0]
            fr.append(data[off + 4:off + 4 + n])
            off += 4 + n
        a, b = zlib.decompress(fr[0]), zlib.decompress(fr[12])
        print(setname, clip, 'frame 0 == frame 12:', a == b,
              'differing bytes: %d of %d' % (sum(x != y for x, y in zip(a, b)), len(a)))

json.dump({'x': 150, 'y': 1500, 'scale': 1.0}, open(os.path.join(HOME, 'state.json'), 'w'))
proc = subprocess.Popen([r'C:\Python312\pythonw.exe', T + '/clawd_pet.pyw', "--grow-quiet",
                         '--home', HOME, '--frames-dir', os.path.join(T, 'frames'), '--debug', '--keep-place',
                         '--wander-interval', '1-2', '--extra-interval', '999-999', '--sleep-after', '9999'])
u = ctypes.WinDLL('user32', use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]


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


def win():
    r = w.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def lp(x, y):
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def log():
    return open(os.path.join(HOME, 'pet.log'), encoding='utf-8', errors='replace').read()


def go_to_window_left(x):
    l, t, r, b = win()
    cx, cy = (l + r) // 2, (t + b) // 2
    u.PostMessageW(hwnd, 0x201, 1, lp(cx - l, cy - t))
    time.sleep(0.05)
    tx = cx + (x - l)
    for _ in range(3):
        wl, wt, _r, _b = win()
        u.PostMessageW(hwnd, 0x200, 1, lp(tx - wl, cy - wt))
        time.sleep(0.05)
    wl, wt, _r, _b = win()
    u.PostMessageW(hwnd, 0x202, 0, lp(tx - wl, cy - wt))
    time.sleep(0.7)


L = 64 - 50                                     # window left when the body is on the left edge, approx
t0 = time.time()
min_left = 10 ** 6
xs = []
done = 0
while time.time() - t0 < 80:
    x = win()[0]
    min_left = min(min_left, x)
    xs.append(x)
    txt = log()
    done = txt.count('play turn_right')
    if done >= 2:
        break
    if txt.rstrip().endswith(tuple(['wander done at x=%d' % v for v in range(0, 2600)])) or x > 90:
        if x > 90 and 'wander' not in txt.splitlines()[-1]:
            go_to_window_left(-64 + 50 + 90)
    time.sleep(0.1)
txt = log()
print('turn_right count', done, 'lowest window left', min_left)
print('edge lines:', re.findall(r'wander reached the edge at x=\d+', txt)[:6])
print('clips:', re.findall(r'play (walk\w*|turn_\w+)', txt)[:16])
with open(os.path.join(HOME, 'event'), 'a', encoding='utf-8', newline='\n') as f:
    f.write('quit\n')
time.sleep(1.0)
if proc.poll() is None:
    proc.kill()
print('errors:', [l for l in txt.splitlines() if 'Traceback' in l or 'tick (' in l][:3])
