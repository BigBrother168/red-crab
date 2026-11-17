# Non-native size: scaled display (disp != 1) on the right edge, then the re-render and hot swap.
import ctypes, json, os, struct, subprocess, time, zlib
from ctypes import wintypes as w

S = os.path.dirname(os.path.abspath(__file__))
T = os.path.dirname(S).replace('\\', '/')
HOME = os.path.join(S, 't', 'home3')
os.makedirs(HOME, exist_ok=True)
if os.path.exists(os.path.join(HOME, 'pet.log')):
    os.remove(os.path.join(HOME, 'pet.log'))     # an old 're-rendered' line must not end the wait below
json.dump({'x': 1200, 'y': 800, 'scale': 1.0}, open(os.path.join(HOME, 'state.json'), 'w'))
proc = subprocess.Popen([r'C:\Python312\pythonw.exe', T + '/clawd_pet.pyw', "--grow-quiet",
                         '--home', HOME, '--frames-dir', os.path.join(T, 'frames'), '--debug', '--keep-place',
                         '--wander-interval', '999-999', '--extra-interval', '999-999', '--sleep-after', '9999'])
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


def token(t):
    with open(os.path.join(HOME, 'event'), 'a', encoding='utf-8', newline='\n') as f:
        f.write(t + '\n')


def state():
    return json.load(open(os.path.join(HOME, 'state.json'), encoding='utf-8'))


def right_gap(setdir, px_scale=1.0):
    """Gap between the idle body's right side and the screen, from the saved feet point."""
    m = json.load(open(os.path.join(setdir, 'manifest.json'), encoding='utf-8'))
    W, H = m['width'], m['height']
    data = open(os.path.join(setdir, 'idle.frames'), 'rb').read()
    n = struct.unpack_from('<I', data, 0)[0]
    raw = zlib.decompress(data[4:4 + n])
    right = max(x for y in range(H) for x in range(W) if raw[(y * W + x) * 4 + 3])
    return m, (right + 1 - m['anchor']['feet_x']) * px_scale


time.sleep(0.6)
token('size:150')
time.sleep(0.4)                                  # before the re-render starts: scaled from frames_hi
l, t, r, b = win()
cx, cy = (l + r) // 2, (t + b) // 2
u.PostMessageW(hwnd, 0x201, 1, lp(cx - l, cy - t))
time.sleep(0.05)
for _ in range(3):
    wl, wt, _r, _b = win()
    u.PostMessageW(hwnd, 0x200, 1, lp(3000 - wl, cy - wt))
    time.sleep(0.05)
wl, wt, _r, _b = win()
u.PostMessageW(hwnd, 0x202, 0, lp(3000 - wl, cy - wt))
time.sleep(0.5)
m, reach = right_gap(os.path.join(T, 'frames_hi'), 0.5)
x_scaled = state()['x']
print('scaled display: feet x %d, body right at about %.1f (screen 2560)' % (x_scaled, x_scaled + reach))

deadline = time.time() + 45
custom = os.path.join(HOME, 'frames_custom')
while time.time() < deadline:
    txt = open(os.path.join(HOME, 'pet.log'), encoding='utf-8', errors='replace').read()
    if 're-rendered' in txt:
        break
    time.sleep(0.3)
time.sleep(0.5)
m, reach = right_gap(custom)
acts = m['actions']
print('re-rendered set: body %dpx, %d actions, turn/walk clips present: %s'
      % (m['base_body_px'], len(acts), all(k in acts for k in ('walk_left', 'walk_right', 'turn_left', 'turn_right'))))
x = win()[0] + m['anchor']['feet_x']
print('after swap: feet x %d (saved %d), body right at %d (screen 2560)' % (x, state()['x'], x + reach))
token('walk')
time.sleep(1.5)
txt = open(os.path.join(HOME, 'pet.log'), encoding='utf-8', errors='replace').read()
print('walk clip on the new set:', [l.split(' play ')[1][:30] for l in txt.splitlines() if ' play walk' in l][-1:])
print('log lines with errors:', [l for l in txt.splitlines() if 'Traceback' in l or 'tick (' in l or 'failed' in l][:3])
token('quit')
time.sleep(1.0)
if proc.poll() is None:
    proc.kill()
print('exit code', proc.poll())
