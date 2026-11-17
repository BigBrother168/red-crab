# album_sweep.py [CASE ...]: a made-up family at each gift level, the album's selftest on it, then each page captured
#   (PrintWindow: the window need not be in front).  CASE: a level; +"full" the first batch all found, +"new" a gift
#   not looked at yet, +"en" English.  Env: PAGES=12345, SELFTEST=0|1, SIZE=w,h (a small window).  Run with the venv
#   (PIL).  Out: tools/t/sweep/<case>/p1..p5.png and selftest.json, of this checkout's album and frames.
import ctypes, json, os, random, subprocess, sys, time
from ctypes import wintypes
from PIL import Image

ctypes.windll.shcore.SetProcessDpiAwareness(2)
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(T, "tools", "t", "sweep")
sys.path.insert(0, T)
import importlib.machinery, importlib.util
_l = importlib.machinery.SourceFileLoader("album", T + "/clawd_album.pyw")
A = importlib.util.module_from_spec(importlib.util.spec_from_loader("album", _l))
_l.exec_module(A)
P = A.P
man = json.load(open(T + "/frames/manifest.json", encoding="utf-8"))["items"]
NAMES = man["names"]
FIRST = [k for k in NAMES if k not in P.ITEMS_2]
SECOND = list(P.ITEMS_2)


def xp_at(lv):
    return sum(P.grow_need(i) for i in range(1, lv))


def family(case):
    lv = int(case.rstrip("abcdefghijklmnopqrstuvwxyz_"))
    full = case.endswith("full")
    rnd = random.Random(lv)
    xp = P.LEVEL_MAX and (xp_at(lv) + (P.grow_need(lv) // 2 if lv < P.LEVEL_MAX else 0))
    first = FIRST[:] ; rnd.shuffle(first)
    n1 = 20 if full else min(len(first), 2 * lv)
    found = first[:n1] if lv > 1 else []
    if lv >= 10:
        second = SECOND[:] ; rnd.shuffle(second)
        found += second[:min(8, lv - 9)]
    items = dict((k, rnd.randint(1, 6)) for k in found)
    combos_order = list(A.COMBO_ORDER)
    nc = min(10, lv // 2 + 1) if lv > 1 else 0
    combos = dict((k, rnd.randint(3, 12 * lv)) for k in combos_order[:nc])
    seen = dict((k, "2026-11-10") for k in combos)
    acts_all = list(P.GROW_ACTS) + ["idle", "wave", "shy", "work_run", "work_read", "work_edit", "think", "nod", "rummage"]
    acts = dict((k, "2026-11-10") for k in acts_all[:min(len(acts_all), 2 + lv)])
    d = {"v": 1, "xp": xp, "level_shown": lv, "since": "2026-11-10", "days": max(1, lv - 4), "turns": 30 * lv, "work_secs": 1500.0 * lv,
         "agents": 3 * lv, "fixes": lv, "plays": 12 * lv, "chances": min(P.dig_cap(lv), 2),
         "items": items, "seen": seen, "combos": combos, "acts": acts,
         "gifts": [g[1] for g in P.LEVEL_GIFTS if g[0] <= lv], "dry_uncommon": 3, "dry_rare": 4, "dry_special": 7,
         "slips": {"stack": "2026-11-12"} if lv >= 18 else {}, "album_marks": [],
         "daily": {time.strftime("%Y-%m-%d"): [9, 3600.0, 2, 300]}}
    if lv >= P.LEVEL_MAX:
        d["monument"] = {"since": "2026-11-10", "day": "2026-11-24", "days": 15, "turns": 1234, "work_secs": 98 * 3600.0,
                         "things": sum(items.values()), "kinds": len(items), "played": sum(combos.values()), "agents": 60, "fixes": 20,
                         "plays": 240, "xp": xp}
    sign = {"chalk": "pink" if lv >= 3 else "white", "frame": "dots" if lv >= 7 else "wood", "board": "flag" if lv >= 18 else "board"}
    state = {"sign": sign, "lang": "en" if "en" in case else "zh"}
    # looked at before: all that is found but the last treasure and the last combo (those two are sealed)
    ids = ["item:" + k for k in found[:-1]] + ["combo:" + k for k in list(combos)[:-1]] + ["act:" + k for k in acts]
    album = {"v": 1, "seen": dict((i, "2026-11-11") for i in ids)}
    if case.endswith("new"):                   # the album keeps the gifts (v 2): those before this level looked at
        album["v"] = 2
        album["seen"].update(("gift:" + g[1], "2026-11-11") for g in P.LEVEL_GIFTS if g[0] < lv)
    return d, state, album


def grab(pid, out):
    u = ctypes.windll.user32
    found = []

    def cb(h, l):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            r = wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 300:
                found.append((h, (r.left, r.top, r.right, r.bottom)))
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    if not found:
        return False
    h = found[0][0]
    if os.environ.get("SIZE"):                 # the window made this small first (w,h in px)
        sw, sh = map(int, os.environ["SIZE"].split(","))
        u.MoveWindow(h, 100, 100, sw, sh, True)
        time.sleep(2.5)
        r_ = wintypes.RECT()
        u.GetWindowRect(h, ctypes.byref(r_))
        found[0] = (h, (r_.left, r_.top, r_.right, r_.bottom))
    l, t, r, b = found[0][1]
    w, hh = r - l, b - t
    g = ctypes.windll.gdi32
    dc = u.GetWindowDC(h)
    mdc = g.CreateCompatibleDC(dc)
    bm = g.CreateCompatibleBitmap(dc, w, hh)
    g.SelectObject(mdc, bm)
    u.PrintWindow(h, mdc, 2)
    buf = ctypes.create_string_buffer(w * hh * 4)

    class BI(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("w", ctypes.c_int32), ("h", ctypes.c_int32), ("p", ctypes.c_uint16), ("bc", ctypes.c_uint16),
                    ("c", ctypes.c_uint32), ("s", ctypes.c_uint32), ("x", ctypes.c_int32), ("y", ctypes.c_int32), ("cu", ctypes.c_uint32), ("ci", ctypes.c_uint32)]
    bi = BI(40, w, -hh, 1, 32, 0, 0, 0, 0, 0, 0)
    g.GetDIBits(mdc, bm, 0, hh, buf, ctypes.byref(bi), 0)
    Image.frombuffer("RGB", (w, hh), buf, "raw", "BGRX", 0, 1).save(out)
    g.DeleteObject(bm); g.DeleteDC(mdc); u.ReleaseDC(h, dc)
    return True


def setup(home, case):
    os.makedirs(home, exist_ok=True)
    for f in os.listdir(home):
        os.remove(os.path.join(home, f))
    d, state, album = family(case)
    json.dump(d, open(home + "/grow.json", "w", encoding="utf-8"))
    json.dump(state, open(home + "/state.json", "w"))
    json.dump(album, open(home + "/album.json", "w"))


cases = sys.argv[1:] or ["1", "3", "5", "7", "9", "9full", "10", "12", "14", "16", "18", "20", "10en", "20en"]
pages = os.environ.get("PAGES", "12345")
for case in cases:
    home = os.path.join(OUT, case)
    setup(home, case)
    if os.environ.get("SELFTEST", "1") == "1":
        p = subprocess.run(["C:/Python312/python.exe", T + "/clawd_album.pyw", "--home", home, "--frames-dir", T + "/frames", "--hi-dir",
                            T + "/frames_hi", "--selftest", home + "/selftest.json"], capture_output=True, text=True, timeout=240)
        o = json.load(open(home + "/selftest.json", encoding="utf-8")) if os.path.exists(home + "/selftest.json") else {}
        print(case, "errors:", o.get("errors"), p.stderr[-300:], "gifts:", o.get("gifts"), "missing:", {k: v for k, v in (o.get("missing_pictures") or {}).items() if v not in ([], 0, 1)})
        setup(home, case)                      # the selftest opened the sealed ones: as they were
    for pg in pages:
        pr = subprocess.Popen(["C:/Python312/python.exe", T + "/clawd_album.pyw", "--home", home, "--frames-dir", T + "/frames",
                               "--hi-dir", T + "/frames_hi", "--page", pg])
        time.sleep(4.5)
        ok = grab(pr.pid, os.path.join(home, "p%s.png" % pg))
        pr.terminate()
        pr.wait()
        if not ok:
            print(case, "page", pg, "not captured")
    print(case, "done")
