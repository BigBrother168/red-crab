# album_shot.py HOME OUT.png PAGE(1-5): open this checkout's album on a home, grab its window, close it.
#   HOME: use a COPY of grow.json / state.json / album.json (the album writes album.json).  Run with the venv (PIL).
#   The real pets may stand beside the window and get into the picture: they are not part of the album.
import ctypes, os, subprocess, sys, time
from ctypes import wintypes
from PIL import ImageGrab

ctypes.windll.shcore.SetProcessDpiAwareness(2)
home, out, page = sys.argv[1], sys.argv[2], sys.argv[3]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the checkout this script is in (also a worktree)
p = subprocess.Popen(["C:/Python312/python.exe", os.path.join(ROOT, "clawd_album.pyw"), "--home", home,
                      "--frames-dir", os.path.join(ROOT, "frames"), "--hi-dir", os.path.join(ROOT, "frames_hi"), "--page", page])
time.sleep(4.0)
u = ctypes.windll.user32
found = []


def cb(h, l):
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if pid.value == p.pid and u.IsWindowVisible(h):
        r = wintypes.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        if r.right - r.left > 300:
            found.append((h, (r.left, r.top, r.right, r.bottom)))
    return True


u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
print(found)
if found:
    u.SetForegroundWindow(found[0][0])
    time.sleep(0.6)
    ImageGrab.grab(bbox=found[0][1], all_screens=True).save(out)
p.terminate()                                  # by its pid: never by the window's title (the real pets' is "Clawd")
