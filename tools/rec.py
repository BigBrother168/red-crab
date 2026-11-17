"""rec.py OUT_DIR [player options...]: run this checkout's player in this process and record what its windows show.

Every UpdateLayeredWindow is copied (the window's bitmap: premultiplied BGRA, and its constant alpha); a thread looks
50 times a second which of the player's windows are shown, where, and in what order (top first).  Only the player's own
windows get in: nothing else on the screen, so it is safe while you use the computer.  Writes OUT_DIR/blobs.bin and
OUT_DIR/index.json when the player quits (an event "quit").  rec_gif.py makes pictures of it.
Run it with C:/Python312/python.exe and a --home (a test home), as the tests run the player."""
import ctypes, ctypes.wintypes as w, importlib.machinery, importlib.util, json, os, sys, threading, time, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.abspath(sys.argv[1])
os.makedirs(out, exist_ok=True)
loader = importlib.machinery.SourceFileLoader("clawd_pet", os.path.join(ROOT, "clawd_pet.pyw"))
spec = importlib.util.spec_from_loader("clawd_pet", loader)
pet = importlib.util.module_from_spec(spec)
sys.modules["clawd_pet"] = pet
loader.exec_module(pet)

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32")


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", w.LONG), ("bmWidth", w.LONG), ("bmHeight", w.LONG), ("bmWidthBytes", w.LONG),
                ("bmPlanes", w.WORD), ("bmBitsPixel", w.WORD), ("bmBits", ctypes.c_void_p)]


class BIH(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD),
                ("biBitCount", w.WORD), ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


class DIBSECTION(ctypes.Structure):
    _fields_ = [("dsBm", BITMAP), ("dsBmih", BIH), ("dsBitfields", w.DWORD * 3), ("dshSection", w.HANDLE),
                ("dsOffset", w.DWORD)]


g32.GetCurrentObject.restype = w.HGDIOBJ
g32.GetCurrentObject.argtypes = [w.HDC, w.UINT]
g32.GetObjectW.argtypes = [w.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
u32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
u32.IsWindowVisible.argtypes = [w.HWND]
ENUM = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
u32.EnumWindows.argtypes = [ENUM, w.LPARAM]

latest = {}            # hwnd -> (blob id, alpha)
blobs = {}             # (crc, len) -> id
meta = []              # id -> [offset, length, w, h]
pending = []           # (id, raw) to compress and write
errors = []
lock = threading.Lock()
T0 = time.perf_counter()
START = time.time()    # the wall clock at T0: rec_scene.mark() times map to the recording's


def snap(hwnd, psize, hsrc, psrc, pblend):
    g32.GdiFlush()
    hb = g32.GetCurrentObject(hsrc, 7)
    ds = DIBSECTION()
    if not hb or not g32.GetObjectW(hb, ctypes.sizeof(ds), ctypes.byref(ds)) or not ds.dsBm.bmBits:
        return
    bw, bh = ds.dsBm.bmWidth, ds.dsBm.bmHeight
    sz = psize._obj
    cx, cy = sz.cx, sz.cy
    sx, sy = (psrc._obj.x, psrc._obj.y) if psrc is not None else (0, 0)
    raw = ctypes.string_at(ds.dsBm.bmBits, bw * bh * 4)
    # the player's bitmaps are all top-down (GetObject reports the height without its sign): no turning over
    if (sx, sy, cx, cy) != (0, 0, bw, bh):
        raw = b"".join(raw[(sy + r) * bw * 4 + sx * 4:(sy + r) * bw * 4 + (sx + cx) * 4] for r in range(cy))
    key = (zlib.crc32(raw), len(raw), cx)
    with lock:
        bid = blobs.get(key)
        if bid is None:
            bid = blobs[key] = len(meta)
            meta.append([0, 0, cx, cy])
            pending.append((bid, raw))
        alpha = pblend._obj.SourceConstantAlpha if pblend is not None else 255
        latest[int(hwnd)] = (bid, alpha)


orig_ulw = pet.UpdateLayeredWindow


def ulw(hwnd, hdst, ppt, psize, hsrc, psrc, key, pblend, flags):
    try:
        snap(hwnd, psize, hsrc, psrc, pblend)
    except Exception as e:
        if len(errors) < 20:
            errors.append(repr(e))
    return orig_ulw(hwnd, hdst, ppt, psize, hsrc, psrc, key, pblend, flags)


pet.UpdateLayeredWindow = ulw
frames = []            # [t, [[bid, x, y, alpha], ...] top first]  -- only when it changed
running = True


def sampler():
    last = None
    order = []

    def cb(h, l):
        if h in latest:
            order.append(h)
        return True
    cbf = ENUM(cb)
    r = w.RECT()
    while running:
        t = time.perf_counter() - T0
        del order[:]
        with lock:
            snapshot = dict(latest)
        u32.EnumWindows(cbf, 0)
        shown = []
        for h in order:
            if u32.IsWindowVisible(h) and h in snapshot and u32.GetWindowRect(h, ctypes.byref(r)):
                bid, a = snapshot[h]
                shown.append([bid, r.left, r.top, a])
        if shown != last:
            frames.append([round(t, 4), shown])
            last = shown
        time.sleep(0.02)


def writer(f):
    off = 0
    while True:
        with lock:
            job = pending[:]
            del pending[:]
        for bid, raw in job:
            z = zlib.compress(raw, 1)
            f.write(z)
            meta[bid][0], meta[bid][1] = off, len(z)
            off += len(z)
        if not job:
            if not running:
                return
            time.sleep(0.05)


bf = open(os.path.join(out, "blobs.bin"), "wb")
th = threading.Thread(target=sampler, daemon=True)
tw = threading.Thread(target=writer, args=(bf,), daemon=True)
th.start()
tw.start()
code = 0
try:
    code = pet.main(sys.argv[2:])
finally:
    running = False
    th.join(2)
    tw.join(30)
    bf.close()
    with open(os.path.join(out, "index.json"), "w") as f:
        json.dump({"frames": frames, "blobs": meta, "errors": errors, "start": START}, f)
    print("recorded %d changes, %d bitmaps, %.0f s; errors %s" % (len(frames), len(meta),
          frames[-1][0] if frames else 0, errors[:3]))
sys.exit(code)
