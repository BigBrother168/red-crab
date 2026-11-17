"""shot.py OUT.png WAIT_S [--size WxH] [--click X,Y] -- COMMAND...: start a window (the album, the connect window), wait, take a picture of
its biggest window with PrintWindow (the window's own pixels: nothing that covers it on the screen gets in), close it.
Run with the venv (PIL).  The process is ended by its pid, never by a window title."""
import ctypes, ctypes.wintypes as w, subprocess, sys, time
from PIL import Image

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u, g = ctypes.windll.user32, ctypes.windll.gdi32
a = sys.argv[1:]
cut = a.index("--")
out, wait = a[0], float(a[1])
size = click = None
if "--size" in a[:cut]:
    size = tuple(map(int, a[a.index("--size") + 1].split("x")))
if "--click" in a[:cut]:                       # x,y in the picture (as an earlier shot of it shows them)
    click = tuple(map(int, a[a.index("--click") + 1].split(",")))
cmd = a[cut + 1:]
p = subprocess.Popen(cmd)
time.sleep(wait)


def windows():
    found = []

    def cb(h, l):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == p.pid and u.IsWindowVisible(h):
            r = w.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), h, r))
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)(cb), 0)
    return sorted(found, key=lambda x: -x[0])


ws = windows()
if not ws:
    p.terminate()
    raise SystemExit("no window")
_, h, r = ws[0]
if size:
    u.SetWindowPos(h, 0, 0, 0, size[0], size[1], 0x0002 | 0x0004 | 0x0010)    # NOMOVE NOZORDER NOACTIVATE
    time.sleep(1.5)
    u.GetWindowRect(h, ctypes.byref(r))
if click:
    ext = w.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(ext), ctypes.sizeof(ext))
    sx, sy = ext.left + click[0], ext.top + click[1]
    target = h
    while True:                                # the deepest child there (no matter what covers it on the screen)
        pt = w.POINT(sx, sy)
        u.ScreenToClient(target, ctypes.byref(pt))
        c = u.ChildWindowFromPointEx(target, pt, 1)     # CWP_SKIPINVISIBLE
        if not c or c == target:
            break
        target = c
    pt = w.POINT(sx, sy)
    u.ScreenToClient(target, ctypes.byref(pt))
    lp = (pt.y << 16) | (pt.x & 0xFFFF)
    u.PostMessageW(target, 0x0200, 0, lp)
    time.sleep(0.2)
    u.PostMessageW(target, 0x0201, 1, lp)
    time.sleep(0.1)
    u.PostMessageW(target, 0x0202, 0, lp)
    time.sleep(1.5)
# the client area only would lose the title bar: take the whole window, then cut off the invisible resize border
W, H = r.right - r.left, r.bottom - r.top
hdc = u.GetWindowDC(h)
mdc = g.CreateCompatibleDC(hdc)
bmp = g.CreateCompatibleBitmap(hdc, W, H)
g.SelectObject(mdc, bmp)
ok = u.PrintWindow(h, mdc, 2)                  # PW_RENDERFULLCONTENT


class BIH(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD),
                ("biBitCount", w.WORD), ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


bi = BIH(ctypes.sizeof(BIH), W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
buf = ctypes.create_string_buffer(W * H * 4)
g.GetDIBits(mdc, bmp, 0, H, buf, ctypes.byref(bi), 0)
img = Image.frombuffer("RGBA", (W, H), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")
# the frame: DWM's extended bounds are the visible window (Windows 11 has an invisible border around it)
ext = w.RECT()
ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(ext), ctypes.sizeof(ext))
img = img.crop((ext.left - r.left, ext.top - r.top, ext.right - r.left, ext.bottom - r.top))
img.save(out)
g.DeleteObject(bmp)
g.DeleteDC(mdc)
u.ReleaseDC(h, hdc)
print("PrintWindow", ok, "->", out, img.size)
p.terminate()
