"""Clawd album (图鉴): a small window that shows what the family has gathered.

Run with:  C:\\Python312\\pythonw.exe clawd_album.pyw [--home DIR] [--frames-dir DIR] [--hi-dir DIR] [--page N]
                                                     [--selftest OUT.json]

A process of its own (tkinter, standard library only): closed, it costs nothing; open, it does not touch the
pets' CPU.  It READS grow.json (the pets write it) and looks again when the file changes; a click on "play it"
appends a word to the event file, the same word `clawd do` writes, and the pets do the rest.  The one file it
writes is album.json in the home: which finds you have already looked at (a red dot on the others).
The lists (actions, combos, levels, labels) come from clawd_pet.pyw itself, so the two cannot drift apart.

Five pages: treasures, combos, actions, family, gifts.  A cell is a picture and a name; the rest (how often, when,
what is missing to the next star, a hint for what is not found yet) is in the bar at the bottom, for the cell
you clicked.  What is not found yet is a dark outline; what was found since you last looked is sealed (an
outline with a red dot) until you click it.  The picked action plays in its snapshot; a combo's snapshot has
all of them in it.  The window can be resized and maximized: everything scales with it.
The gifts are looked at too (album.json v 2, ids gift:<id>): one the level has brought and you have not seen here
has a red dot (the pets' menu counts it: the player's gift_news), the 礼物 page opens on it, its card says where
it shows (GIFT_WHERE).
"""
import os
import sys
import json
import math
import time
import zlib
import struct
import ctypes
import importlib.machinery
import importlib.util
from operator import add
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))       # the program: frames/, frames_hi/


def data_home():
    """What the pets keep, found as clawd_pet.pyw finds it (default_home): CLAWD_HOME; this folder if a save is
    already here (a copy run from source); else %APPDATA%\\Clawd (an install).  The pets start the album with --home."""
    h = os.environ.get("CLAWD_HOME")
    if h:
        return os.path.abspath(h)
    if any(os.path.exists(os.path.join(HERE, n)) for n in ("state.json", "grow.json")):
        return HERE
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Clawd")


def system_lang():
    """zh when Windows shows Chinese, else en: the pets' language while state.json has none yet."""
    try:
        return "zh" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x04 else "en"
    except Exception:
        return "zh"


def load_pet():
    """clawd_pet.pyw as a module: only its tables and grow_level are used."""
    loader = importlib.machinery.SourceFileLoader("clawd_pet", os.path.join(HERE, "clawd_pet.pyw"))
    spec = importlib.util.spec_from_loader("clawd_pet", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


P = load_pet()
try:
    sys.path.insert(0, HERE)
    from clawd_album_hints import HINTS, HINTS_EN
except Exception:
    HINTS, HINTS_EN = {}, {}

# A scrapbook: a leather cover, a cream page with a stitched edge, index tabs.  Treasures lie in the slots of a
# velvet-lined tray; actions and combos are snapshots taped to the page; the family page is a framed picture and
# a sheet of notes.  Only the bar at the bottom is the family's blackboard (chalk on dark green), for the hints.
PAPER, PAPER_LINE = "#f4ead4", "#dccba4"
COVER, COVER_DARK = "#a8743f", "#7d5229"
INK, INK_DIM, ACCENT = "#4a3b2e", "#9a8a74", "#d2643f"
CARD, CARD_EDGE, SHADOW = "#fffdf6", "#e6dcc4", "#d5c5a0"
VELVET, SLOT = (39, 53, 59), (56, 74, 82)          # the tray, and the hollow of what is not found yet
PHOTO, PHOTO_OFF, SIL_OFF = (207, 227, 220), (200, 192, 176), (168, 159, 142)   # a snapshot; one not taken yet
SEALED = (120, 108, 96)                            # the outline of a find you have not looked at yet
TAPES = ("#f2b8a0", "#a8d5ba", "#f6d98a", "#b8c7ea")
BOARD = (43, 63, 53)
WOOD, WOOD_DARK = "#8a6038", "#5e4026"
CHALK, DIM = "#f2efe6", "#9fb3a8"
MINT, GOLD, RED = "#8fe0b8", "#e0a100", "#e0483a"
RARITY_COL = {"common": "#8a7a66", "uncommon": "#3f7fd0", "rare": "#8a55d6", "special": "#d49a12"}
RARITY_ORDER = ("common", "uncommon", "rare", "special")
RARITY_LABEL = {"common": ("普通", "Common"), "uncommon": ("少见", "Uncommon"), "rare": ("稀有", "Rare"), "special": ("特殊", "Special")}
FONT = "KaiTi"              # a hand that writes in an album (Tk falls back by itself if it is missing)
FONT_EN = "Segoe Print"
BASE_W, BASE_H = 1040, 800  # the page as it is laid out; the window scales it (the smaller of the two ratios)
PAGES = (("items", "宝贝", "Treasures"), ("combos", "组合", "Combos"), ("acts", "动作", "Actions"), ("family", "全家", "Family"),
         ("gifts", "礼物", "Gifts"))
COLLECTED = ("items", "combos", "acts")     # the pages whose cells are "已收集"
# each page's grid: columns, a cell's width and height, and a snapshot's (layout units)
GRID = {"items": {"cols": 9, "cw": 100, "ch": 124},
        "acts": {"cols": 9, "cw": 100, "ch": 132, "pw": 92, "ph": 92},
        "combos": {"cols": 4, "cw": 200, "ch": 179, "pw": 186, "ph": 127}}   # big snapshots: the ten fill the page
ANIM_MS = 90                # the picked action's snapshot plays at about this many ms a frame
REVEAL_STEPS = 6            # a sealed find opens in this many steps ...
REVEAL_MS = 55              # ... this far apart

# The actions' snapshots: the frame of each clip that says it best (picked by how far it is from standing still,
# then by eye); the others: the middle one.
ACT_CLIP = {"tumble": "tumble_right"}
ACT_EXTRA = (("rummage", "翻找", "Rummage"), ("wake_up", "醒来", "Wake up"))
ACT_FRAME = {"shy": 18, "dangle": 32, "tumble_right": 9, "dizzy": 26, "doze": 45, "doze_startle": 5, "doze_up": 15,
             "shrug_sweat": 29, "surprised": 6, "idle": 22, "listen": 29, "think": 20, "nod": 13, "thumbs_up": 11,
             "confused": 24, "aha": 8, "celebrate": 22, "wave": 6, "hop": 6, "head_tilt": 5, "wink": 5,
             "look_at_viewer": 4, "proud": 27, "shake_head": 9, "tiptoe_peek": 14, "sleep": 47, "walk": 20, "land": 1,
             "work_read": 30, "work_edit": 42, "work_run": 12, "work_web": 12, "work_compact": 21, "work_agent": 17,
             "rummage": 19, "wake_up": 5}

# The combos' page: each one you can start yourself (the menu's, the pat after a throw), whoever plays it; no kinds.
COMBO_ORDER = ("celebrate_all", "parade", "comfort", "peek", "wake", "console", "high_five", "note", "leapfrog", "stack")
# A combo's snapshot: all of them in it, as they stand in the combo.  (slot, clip, frame, x, y): x to the right
# and y up from the big one's feet, in the big one's body; slots are drawn in this order (the last in front).
COMBO_PHOTO = {
    "celebrate_all": [(0, "celebrate", 22, 0.0, 0.0), (1, "celebrate", 10, -1.02, 0.0), (2, "celebrate", 16, 0.89, 0.0)],
    "parade": [(0, "walk_right", 20, 0.0, 0.0), (1, "walk_right", 8, -1.05, 0.0), (2, "walk_right", 14, -1.87, 0.0)],
    "comfort": [(0, "shrug_sweat", 29, 0.0, 0.0), (1, "comfort_right", 29, -0.84, 0.0), (2, "comfort_left", 25, 0.73, 0.0)],
    "peek": [(0, "work_run", 30, 0.0, 0.0), (1, "peek_right", 34, -0.9, 0.0)],
    "wake": [(0, "sleep", 47, 0.0, 0.0), (1, "nudge_right", 10, -0.84, 0.0)],
    "console": [(1, "dizzy", 26, 0.0, 0.0), (0, "comfort_right", 29, -0.87, 0.0), (2, "comfort_left", 25, 0.65, 0.0)],
    "high_five": [(0, "high_five_right", 16, 0.0, 0.0), (1, "high_five_up_left", 15, 0.86, 0.0)],
    "note": [(0, "receive_right", 16, 0.0, 0.0), (1, "give_mid_left", 13, 0.863, 0.0)],
    "leapfrog": [(1, "leap_crouch", 10, 0.0, 0.0), (2, "stack_hop", 10, 0.06, 0.56)],
    "stack": [(0, "stack_brace", 20, 0.0, 0.0), (1, "stack_brace", 20, 0.0, 0.714), (2, "stack_top", 12, 0.0, 1.285)],
}
# The 礼物 page (the player's LEVEL_GIFTS): the road from Lv.1 to LEVEL_MAX in three rows, there and back, each
# gift a badge on it (an icon of Segoe Fluent Icons and a colour by its kind), you (the big one) where the level is.
GIFT_ICON = {"chalk": "\ue790", "frame": "\ue91b", "board": "\ue7c1", "dig": "\ue7b8", "items": "\uf158",
             "slips": "\ueb68", "monument": "\ueb95"}
GIFT_COL = {"chalk_pink": "#e3779b", "dig_4": "#5e9c5a", "frame_dots": "#d9a23a", "items_2": "#d49a12", "chalk_blue": "#4d8fd6",
            "frame_stars": "#34457e", "slips": "#3f7fd0", "dig_5": "#5e9c5a", "board_flag": "#2e7a5e",
            "monument": "#a8743f", "chalk_gold": "#d49a12"}
ROUTE_ROWS = ((1, 7), (8, 14), (15, 20))   # levels on each row of the road (the first left to right, then back)
# a gift you have: where it shows (the page, a link on its card); the looks of the signs are down on the same page
GIFT_WHERE = {"items_2": ("items", ("新宝贝在“宝贝”页", "New ones on the Treasures page")),
              "slips": ("combos", ("“组合”页里标着 ✧", "Marked ✧ on the Combos page")),
              "monument": ("family", ("立在“全家”页", "On the Family page"))}
MARKER_H = 38               # you on the road: the big one this tall (taller, it hides the name of the gift a row above)
ICON_FONT = "Segoe Fluent Icons"
ROAD, ROAD_EDGE = "#ead9b4", "#d9c294"   # the road on the 礼物 page: sand, its edge
FAMILY_PHOTO = [(0, "wave", 6, 0.0, 0.0), (1, "celebrate", 22, 1.05, 0.0), (2, "hop", 6, 1.87, 0.0)]
# The monument (the gift of the top level): on the 全家 page in place of the picture, the family at a milestone (矮胖的
# 里程碑, never an upright slab: with two dates on it, that is a gravestone).  In the big one's body from the middle of
# the stone's foot, x to the right, y up: the picture shows MONUMENT_SPAN; the stone, its little flag (the one of the
# banner signs, Lv.18), and the family on and by it, as COMBO_PHOTO.
MONUMENT_SPAN = (-2.05, -0.2, 2.05, 2.05)
MONUMENT_TIERS = ((0.92, 0.12), (0.76, 0.44), (0.85, 0.1))   # the stone: plinth, block, cap (half width, how tall)
PED_TOP_DEPTH = 0.04                      # how much of a top is seen
MONUMENT_STONE = (0.92, 0.85, 0.66 + PED_TOP_DEPTH / 2)   # half its width at the foot, at the top; where they stand
PED_FRONT, PED_SIDE, PED_TOP, PED_EDGE = "#f3ebdc", "#d2c3a6", "#fffaf0", "#a8946e"   # cream marble (veins: they read as cracks)
MONUMENT_FLAG = (0.68, 1.92, 0.62, 0.36)  # its pole (x, how high), the banner (how long, how wide)
MONUMENT_PHOTO = [(1, "celebrate", 10, -1.5, 0.0), (2, "celebrate", 16, 1.5, 0.0), (0, "celebrate", 22, -0.04, 0.68)]
BRASS, BRASS_DARK, BRASS_INK = "#dcbb66", "#9c7a2c", "#5a4214"
FAMILY_RATIOS = getattr(P, "FAMILY_RATIOS", (1.0, 0.8, 0.6))
# where the body is when it stands still, of its body px from the feet: a snapshot never shows it bigger than this
BODY_BOX = (-0.5, -0.76, 0.51, 0.03)


def hexc(rgb):
    return "#%02x%02x%02x" % rgb


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_json(path, d):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------- pictures (standard library only)
def frame_at(path, k):
    """-> record k of a .frames file, unpacked (premultiplied BGRA), or None."""
    try:
        with open(path, "rb") as f:
            for i in range(k + 1):
                head = f.read(4)
                if len(head) < 4:
                    return None
                (n,) = struct.unpack("<I", head)
                if i == k:
                    return zlib.decompress(f.read(n))
                f.seek(n, 1)
    except Exception:
        return None


def frames_all(path, step=1):
    """-> every step-th record of a .frames file, unpacked (a generator: one at a time)."""
    try:
        with open(path, "rb") as f:
            i = 0
            while True:
                head = f.read(4)
                if len(head) < 4:
                    return
                (n,) = struct.unpack("<I", head)
                if i % step == 0:
                    yield zlib.decompress(f.read(n))
                else:
                    f.seek(n, 1)
                i += 1
    except Exception:
        return


_SOLID = bytes(0 if i <= 24 else 1 for i in range(256))


def alpha_box(raw, W, H):
    """-> (x0, y0, x1, y1) of what is drawn in a premultiplied BGRA frame (x1, y1 past it), or None."""
    a = raw[3::4].translate(_SOLID)
    first = a.find(1)
    if first < 0:
        return None
    last = a.rfind(1)
    y0, y1 = first // W, last // W + 1
    x0, x1 = W, 0
    for y in range(y0, y1):
        row = a[y * W:(y + 1) * W]
        i = row.find(1)
        if i >= 0:
            x0 = min(x0, i)
            x1 = max(x1, row.rfind(1) + 1)
    return x0, y0, x1, y1


def shrink(raw, W, x0, y0, w, h, n):
    """A piece of a premultiplied BGRA frame, n x n pixels to one -> (ow, oh, bytearray BGRA premultiplied)."""
    ow, oh = w // n, h // n
    nn, step = n * n, 4 * n
    out = bytearray(ow * oh * 4)
    o = 0
    for oy in range(oh):
        acc = [[0] * ow for _ in range(4)]
        for dy in range(n):
            base = ((y0 + oy * n + dy) * W + x0) * 4
            for dx in range(n):
                b = base + dx * 4
                e = b + ow * step
                for c in range(4):
                    acc[c] = list(map(add, acc[c], raw[b + c:e:step]))
        B, G, R, A = acc
        for x in range(ow):
            out[o] = B[x] // nn
            out[o + 1] = G[x] // nn
            out[o + 2] = R[x] // nn
            out[o + 3] = A[x] // nn
            o += 4
    return ow, oh, out


def resample(ow, oh, buf, tw, th):
    """A premultiplied BGRA picture to tw x th, bilinear (after shrink: only the last bit of the way)."""
    out = bytearray(tw * th * 4)
    sx, sy = ow / float(tw), oh / float(th)
    xs = []
    for x in range(tw):
        u = (x + 0.5) * sx - 0.5
        x0 = int(math.floor(u))
        xs.append((min(max(x0, 0), ow - 1) * 4, min(max(x0 + 1, 0), ow - 1) * 4, u - x0))
    o = 0
    for y in range(th):
        v = (y + 0.5) * sy - 0.5
        y0 = int(math.floor(v))
        fy = v - y0
        r0, r1 = min(max(y0, 0), oh - 1) * ow * 4, min(max(y0 + 1, 0), oh - 1) * ow * 4
        for a, b, fx in xs:
            for c in range(4):
                top = buf[r0 + a + c] + (buf[r0 + b + c] - buf[r0 + a + c]) * fx
                bot = buf[r1 + a + c] + (buf[r1 + b + c] - buf[r1 + a + c]) * fx
                out[o] = int(top + (bot - top) * fy + 0.5)
                o += 1
    return out


def layer(raw, W, H, box, anchor, s, fx, fy):
    """The drawn part (box) of a frame, s px to one (s need not be whole), its anchor (the feet) at (fx, fy) of
    the picture -> a layer (ow, oh, premultiplied BGRA, x, y), or None."""
    ax, ay = anchor
    n = max(1, int(s + 1e-6))
    x0 = ax - ((ax - box[0] + n - 1) // n) * n
    y0 = ay - ((ay - box[1] + n - 1) // n) * n
    while x0 < 0:
        x0 += n
    while y0 < 0:
        y0 += n
    w = (min(W, box[2]) - x0) // n * n
    h = (min(H, box[3]) - y0) // n * n
    if w <= 0 or h <= 0:
        return None
    ow, oh, buf = shrink(raw, W, x0, y0, w, h, n)
    q = n / float(s)
    if abs(q - 1.0) > 0.01:
        tw, th = max(1, int(round(ow * q))), max(1, int(round(oh * q)))
        buf, ow, oh = resample(ow, oh, buf, tw, th), tw, th
    return ow, oh, buf, int(round(fx - (ax - x0) / float(s))), int(round(fy - (ay - y0) / float(s)))


def compose(pw, ph, bg, layers, sil=None):
    """Layers laid on a pw x ph picture of colour bg, in order -> PPM bytes.  sil: only the outline, that colour."""
    canvas = bytearray(bytes(bg) * (pw * ph))
    for ly in layers:
        if ly is None:
            continue
        ow, oh, buf, ox, oy = ly
        for y in range(max(0, -oy), min(oh, ph - oy)):
            row = (y + oy) * pw + ox
            i = y * ow * 4
            for x in range(max(0, -ox), min(ow, pw - ox)):
                p = i + x * 4
                a = buf[p + 3]
                if not a:
                    continue
                j = (row + x) * 3
                k = 255 - a
                if sil is None:
                    canvas[j] = min(255, buf[p + 2] + canvas[j] * k // 255)
                    canvas[j + 1] = min(255, buf[p + 1] + canvas[j + 1] * k // 255)
                    canvas[j + 2] = min(255, buf[p] + canvas[j + 2] * k // 255)
                else:
                    canvas[j] = (sil[0] * a + canvas[j] * k) // 255
                    canvas[j + 1] = (sil[1] * a + canvas[j + 1] * k) // 255
                    canvas[j + 2] = (sil[2] * a + canvas[j + 2] * k) // 255
    return b"P6 %d %d 255\n" % (pw, ph) + bytes(canvas)


def compose_png(pw, ph, layers):
    """Layers laid on a clear pw x ph picture, in order -> PNG bytes with alpha (what is drawn under it shows)."""
    canvas = bytearray(pw * ph * 4)            # premultiplied BGRA, like the layers
    for ly in layers:
        if ly is None:
            continue
        ow, oh, buf, ox, oy = ly
        for y in range(max(0, -oy), min(oh, ph - oy)):
            row = (y + oy) * pw + ox
            i = y * ow * 4
            for x in range(max(0, -ox), min(ow, pw - ox)):
                p = i + x * 4
                a = buf[p + 3]
                if not a:
                    continue
                j = (row + x) * 4
                k = 255 - a
                for c in range(4):
                    canvas[j + c] = min(255, buf[p + c] + canvas[j + c] * k // 255)
    rows = []
    for y in range(ph):
        row = bytearray(b"\x00")
        for x in range(pw):
            j = (y * pw + x) * 4
            a = canvas[j + 3]
            if a:
                row += bytes((min(255, canvas[j + 2] * 255 // a), min(255, canvas[j + 1] * 255 // a), min(255, canvas[j] * 255 // a), a))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", pw, ph, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


def scene_fit(pw, ph):
    """-> (px to one body, x and y of the stone's foot) of the monument's picture: MONUMENT_SPAN in, in the middle."""
    x0, y0, x1, y1 = MONUMENT_SPAN
    u = min(pw / (x1 - x0), ph / (y1 - y0))
    return u, pw / 2.0 - (x0 + x1) / 2.0 * u, ph / 2.0 + (y0 + y1) / 2.0 * u


def blend(a, b, t):
    """Two PPMs of one size, t of the way from a to b."""
    head = a[:a.index(b"255\n") + 4]
    pa, pb = a[len(head):], b[len(head):]
    return head + bytes(x + int((y - x) * t) for x, y in zip(pa, pb))


def png(layer_, w, h):
    """A layer (premultiplied BGRA) as a PNG with alpha, w x h, the layer in the middle (the window's icon)."""
    ow, oh, buf, _, _ = layer_
    ox, oy = (w - ow) // 2, (h - oh) // 2
    rows = []
    for y in range(h):
        row = bytearray(b"\x00")
        for x in range(w):
            sx, sy = x - ox, y - oy
            if 0 <= sx < ow and 0 <= sy < oh:
                p = (sy * ow + sx) * 4
                a = buf[p + 3]
                if a:
                    row += bytes((min(255, buf[p + 2] * 255 // a), min(255, buf[p + 1] * 255 // a), min(255, buf[p] * 255 // a), a))
                    continue
            row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


class Frames(object):
    """The big frames (300 %, else the base ones): one frame of a clip, where its drawing is, as layers."""

    def __init__(self, folder):
        self.dir = folder
        self.man = read_json(os.path.join(folder, "manifest.json"))
        self.W, self.H = int(self.man.get("width") or 0), int(self.man.get("height") or 0)
        a = self.man.get("anchor") or {}
        self.anchor = (int(a.get("feet_x") or 0), int(a.get("feet_y") or 0))
        self.body = float(self.man.get("base_body_px") or 100)
        self.boxes = {}

    def info(self, clip):
        return (self.man.get("actions") or {}).get(clip)

    def count(self, clip):
        info = self.info(clip)
        return max(1, int(info.get("count", 1))) if info else 0

    def raw(self, clip, k):
        info = self.info(clip)
        if not info:
            return None
        return frame_at(os.path.join(self.dir, str(info["file"])), k % self.count(clip))

    def box(self, clip, k, raw):
        key = (clip, k)
        if key not in self.boxes:
            self.boxes[key] = alpha_box(raw, self.W, self.H)
        return self.boxes[key]

    def frame(self, clip, k=None):
        """-> (raw, box, k) of frame k of a clip (None: its picked one), or None."""
        n = self.count(clip)
        if not n:
            return None
        if k is None:
            k = ACT_FRAME.get(clip, n // 2)
        k %= n
        raw = self.raw(clip, k)
        if raw is None:
            return None
        box = self.box(clip, k, raw)
        return (raw, box, k) if box else None

    def fit_one(self, box, pw, ph):
        """-> (n, feet x, feet y): a single pet in a snapshot, its whole drawing in, never bigger than standing still
        in a snapshot of BODY 1.22 to a side; in the middle."""
        b, (ax, ay) = self.body, self.anchor
        x0, y0, x1, y1 = box
        x0, y0 = min(x0, ax + BODY_BOX[0] * b), min(y0, ay + BODY_BOX[1] * b)
        x1, y1 = max(x1, ax + BODY_BOX[2] * b), max(y1, ay + BODY_BOX[3] * b)
        side = max(1.22 * b * max(1.0, float(pw) / ph), (x1 - x0) + 0.1 * b)
        n = max(1, int(math.ceil(max(side / pw, ((y1 - y0) + 0.1 * b) / ph))))
        return n, pw / 2.0 - ((x0 + x1) / 2.0 - ax) / n, ph / 2.0 - ((y0 + y1) / 2.0 - ay) / n

    def scene(self, spec, pw, ph):
        """-> the layers of the family as they stand at the monument (scene_fit: where the stone is), or None."""
        u, sx, sy = scene_fit(pw, ph)
        out = []
        for slot, clip, k, x, y in spec:
            got = self.frame(clip, k)
            if got is None:
                return None
            raw, box, _ = got
            r = FAMILY_RATIOS[slot] if slot < len(FAMILY_RATIOS) else 0.6
            out.append(layer(raw, self.W, self.H, box, self.anchor, self.body / u / r, sx + x * u, sy - y * u))
        return out

    def group(self, spec, pw, ph):
        """-> the layers of a snapshot of a few of them (COMBO_PHOTO), all in and in the middle, or None."""
        b, (ax, ay) = self.body, self.anchor
        parts, ext = [], [1e9, 1e9, -1e9, -1e9]
        for slot, clip, k, x, y in spec:
            got = self.frame(clip, k)
            if got is None:
                return None
            raw, box, _ = got
            r = FAMILY_RATIOS[slot] if slot < len(FAMILY_RATIOS) else 0.6
            X, Y = x * b, -y * b
            ext = [min(ext[0], X + (box[0] - ax) * r), min(ext[1], Y + (box[1] - ay) * r),
                   max(ext[2], X + (box[2] - ax) * r), max(ext[3], Y + (box[3] - ay) * r)]
            parts.append((raw, box, r, X, Y))
        gw, gh = ext[2] - ext[0] + 0.12 * b, ext[3] - ext[1] + 0.12 * b
        nf = max(0.5, gw / pw, gh / ph)
        cx, cy = (ext[0] + ext[2]) / 2.0, (ext[1] + ext[3]) / 2.0
        out = []
        for raw, box, r, X, Y in parts:
            out.append(layer(raw, self.W, self.H, box, self.anchor, nf / r, pw / 2.0 + (X - cx) / nf, ph / 2.0 + (Y - cy) / nf))
        return out


class Album(object):
    def __init__(self, home, frames_dir, hi_dir, page, selftest=None):
        self.home = home
        self.grow_path = os.path.join(home, "grow.json")
        self.event_path = os.path.join(home, "event")
        self.seen_path = os.path.join(home, "album.json")
        hi = hi_dir or os.path.join(os.path.dirname(frames_dir), "frames_hi")
        self.fr = Frames(hi if os.path.isfile(os.path.join(hi, "manifest.json")) else frames_dir)
        self.items_man = self.fr.man.get("items") or {}
        self.lang = str(read_json(os.path.join(home, "state.json")).get("lang") or system_lang())
        self.selftest = selftest
        self.errors = []
        self.root = root = tk.Tk()
        root.report_callback_exception = self.on_error
        root.title(self.t("Clawd 图鉴", "Clawd Album"))
        f = root.winfo_fpixels("1i") / 96.0
        f = min(f, root.winfo_screenheight() * 0.88 / BASE_H, root.winfo_screenwidth() * 0.94 / BASE_W)
        self.f = f
        self.W, self.H = self.S(BASE_W), self.S(BASE_H)
        root.geometry("%dx%d+%d+%d" % (self.W, self.H, (root.winfo_screenwidth() - self.W) // 2,
                                         max(0, (root.winfo_screenheight() - self.H) // 2 - self.S(20))))
        root.minsize(int(BASE_W * 0.55), int(BASE_H * 0.55))
        root.configure(bg=COVER)
        self.cv = tk.Canvas(root, width=self.W, height=self.H, bg=COVER, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.page = PAGES[page][0]
        self.sel = {}                          # page -> the key of the cell that is picked
        self.images = {}                       # (kind, key, state, w, h) -> PhotoImage
        self.todo = []                         # pictures still to make: (cell, x, y)
        self.item_k = 1.0                      # how much the treasures' slots are shrunk (grid_fit)
        self.nudged = set()                    # cells whose second hint was asked for (as long as the window is open)
        self.hit = []                          # (x0, y0, x1, y1, what) of what can be clicked
        self.mtime = None
        self.data = {}
        self.anim = None                       # the picked action / treasure playing in its picture
        self.revealing = None
        self.resize_job = None
        self.seen = self.load_seen()
        self.cv.bind("<Button-1>", self.click)
        self.cv.bind("<Motion>", self.hover)
        root.bind("<Configure>", self.on_configure)
        root.bind("<Escape>", lambda e: root.destroy())
        for i in range(len(PAGES)):
            root.bind(str(i + 1), lambda e, i=i: self.show(PAGES[i][0]))
        self.reload()
        root.after(30, self.dress)
        root.after(1500, self.watch)
        if selftest:
            root.after(200, self.run_selftest)

    # ------------------------------------------------------------------ small things
    def S(self, v):
        return int(round(v * self.f))

    def t(self, zh, en):
        return en if self.lang == "en" else zh

    def font(self, px, bold=False):
        return (FONT_EN if self.lang == "en" else FONT, -max(6, self.S(px * (0.84 if self.lang == "en" else 1.0))), "bold" if bold else "normal")

    def on_error(self, kind, value, tb):
        import traceback
        self.errors.append("".join(traceback.format_exception(kind, value, tb))[-1500:])
        if not self.selftest:
            try:
                with open(os.path.join(self.home, "album.log"), "a", encoding="utf-8") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + self.errors[-1] + "\n")
            except OSError:
                pass

    def dress(self):
        """The title bar in the cover's leather (Windows 11; elsewhere it stays as it is) and Clawd as the icon."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dwm = ctypes.windll.dwmapi

            def colour(h):
                r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
                return ctypes.c_int(r | g << 8 | b << 16)
            self.dressed = all(dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(colour(c)), 4) == 0
                               for attr, c in ((35, COVER), (36, CARD), (34, COVER_DARK)))
        except Exception:
            self.dressed = False
        try:
            got = self.fr.frame("idle", 0)
            if got is not None:
                raw, box, _ = got
                icons = []
                for side in (48, 32, 16):
                    n = max(1, int(math.ceil((box[2] - box[0]) / (side * 0.95))))
                    ly = layer(raw, self.fr.W, self.fr.H, box, self.fr.anchor, n, 0, 0)
                    icons.append(tk.PhotoImage(data=png(ly, side, side), format="png"))
                self.icons = icons
                self.root.iconphoto(True, *icons)
        except Exception:
            pass

    # ------------------------------------------------------------------ what you have looked at
    def load_seen(self):
        d = read_json(self.seen_path)
        seen = d.get("seen")
        # the gifts are looked at too since v 2: in a file of before, the gifts you have count as looked at
        self.gifts_new = not (type(d.get("v")) is int and d["v"] >= 2)
        if isinstance(seen, dict):
            self.seen_new = False
            return dict((k, v) for k, v in seen.items() if isinstance(v, str))
        self.seen_new = True                   # the first time: all there is now counts as looked at
        return {}

    def mark_seen(self, ids):
        today = time.strftime("%Y-%m-%d")
        for i in ids:
            self.seen.setdefault(i, today)
        write_json(self.seen_path, {"v": 2, "seen": self.seen})

    # ------------------------------------------------------------------ what there is
    def reload(self):
        try:
            self.mtime = os.path.getmtime(self.grow_path)
        except OSError:
            self.mtime = None
        d = read_json(self.grow_path)
        for k in ("items", "combos", "acts", "seen", "daily"):
            if not isinstance(d.get(k), dict):
                d[k] = {}
        self.data = d
        self.look = self.read_look()
        self.cells = {"items": self.item_cells(), "combos": self.combo_cells(), "acts": self.act_cells()}
        hints = HINTS_EN if self.lang == "en" else HINTS
        lit = []
        for sections in self.cells.values():   # each cell's own words: a riddle while it is not found, how it comes about once it is
            for _, _, cells in sections:
                for c in cells:
                    riddle, nudge, plain = hints.get(c["id"], ("", "", ""))
                    c["nudge"] = ""
                    c["stat"] = ""
                    if c["lit"]:           # found: the riddle stays, with its answer beside it; the numbers go up beside the name
                        lit.append(c["id"])
                        if riddle and plain:
                            c["stat"] = c["detail"]
                            c["detail"] = "“%s”  →  %s" % (riddle, plain)
                        elif plain:
                            c["detail"] = (plain + "  " + c["detail"]).strip()
                    elif riddle:
                        c["detail"], c["nudge"] = riddle, nudge
        if self.gifts_new:                     # (seen_new or an album.json of v 1): the gifts you have are not news
            self.gifts_new = False
            lv = self.level()[0]
            gifts = ["gift:" + g[1] for g in P.LEVEL_GIFTS if g[0] <= lv]
            if self.seen_new:
                lit += gifts
            else:
                self.mark_seen(gifts)
        if self.seen_new:
            self.seen_new = False
            self.mark_seen(lit)
        for sections in self.cells.values():
            for _, _, cells in sections:
                for c in cells:
                    c["new"] = c["lit"] and c["id"] not in self.seen
        self.show(self.page)

    def watch(self):
        try:
            m = os.path.getmtime(self.grow_path)
        except OSError:
            m = None
        if m != self.mtime:
            self.reload()
        self.root.after(1500, self.watch)

    def cell(self, kind, key, name, lit, **kw):
        c = {"kind": kind, "key": key, "id": "%s:%s" % (kind, key), "name": name, "lit": lit, "sub": "", "detail": "",
             "title": name, "token": None, "col": INK}
        c.update(kw)
        return c

    def item_cells(self):
        """-> [(section title, colour, [cell])]: the treasures, a section for each rarity."""
        names = self.items_man.get("names") or {}
        have = self.data["items"]
        out = []
        locked = getattr(P, "items_locked", lambda lv: ())(self.level()[0])
        later = []                             # the second batch before its gift: a section of its own, all dark
        for rar in RARITY_ORDER:
            cells = []
            for key in self.items_man.get("order") or sorted(names):
                info = names.get(key) or {}
                if info.get("rarity") != rar:
                    continue
                n = have.get(key, 0) if type(have.get(key)) is int else 0
                if key in locked and not n:
                    later.append(self.cell("item", key, "？？？", False, detail=self.t(
                        "第二批的宝贝。等级到 Lv.%d，它们才会出现在翻找里。", "One of the second batch: from Lv.%d on, digs may bring it up.") % self.later_at(),
                        title=self.t("第二批 · 还锁着", "Second batch · locked"), col=RARITY_COL[rar], file=info.get("file")))
                    continue
                name = str(info.get("en" if self.lang == "en" else "zh") or key)
                rl = self.t(*RARITY_LABEL[rar])
                if n:
                    detail = self.t("%s宝贝，有 %d 件。", "A %s treasure; you have %d.") % ((rl, n) if self.lang != "en" else (rl.lower(), n))
                elif rar == "special":
                    detail = self.t("还没找到。翻找时偶尔会出，保底一定出；那天干的活儿也会把它引来……",
                                    "Not found yet. Now and then a dig brings one, and the sure one does; the work of the day may draw it out too...")
                else:
                    detail = self.t("还没找到。多翻翻，总会翻到的……", "Not found yet. Keep digging, it will turn up...")
                cells.append(self.cell("item", key, name if n else "？？？", bool(n), detail=detail,   # how many: in the words below, not on the slot (28 badges were a clutter)
                                       title=name if n else self.t("还没找到的宝贝", "A treasure not found yet"),
                                       token="play:" + key if n else None, col=RARITY_COL[rar], file=info.get("file")))
            if cells:
                out.append((self.t(*RARITY_LABEL[rar]), RARITY_COL[rar], cells))
        if later:
            out.append((self.t("第二批 · Lv.%d 解锁", "Second batch · Lv.%d") % self.later_at(), INK_DIM, later))
        return out

    def later_at(self):
        return next((g[0] for g in P.LEVEL_GIFTS if g[1] == "items_2"), 10)

    def combo_name(self, key):
        if key in P.GROW_NAMES:
            zh, en = P.GROW_NAMES[key]
        else:
            zh, en = key, key
        return self.t(zh, en)

    def combo_cells(self):
        counts, seen = self.data["combos"], self.data["seen"]
        slips = self.data.get("slips") if isinstance(self.data.get("slips"), dict) else {}
        xp = self.data.get("xp")
        slips_on = P.grow_level(xp if type(xp) is int and xp >= 0 else 0)[0] >= P.slips_level()   # 小插曲: the gift is here
        out = []
        for keys in (COMBO_ORDER,):         # one section: a collection, no kinds (the treasures' page has its rarities)
            cells = []
            for key in keys:
                n = counts.get(key, 0) if type(counts.get(key)) is int else 0
                lit = n > 0 or key in seen
                stars = sum(1 for need, _ in P.GROW_STARS if n >= need)
                if lit:
                    nxt = [need for need, _ in P.GROW_STARS if n < need]
                    detail = self.t("演过 %d 次" % n, "Played " + P.plural(n, "time"))
                    detail += self.t("，下一颗星还差 %d 次", ", %d more to the next star") % (nxt[0] - n) if nxt else self.t("，三星了！", ", three stars!")
                    if isinstance(seen.get(key), str):
                        detail += self.t("。第一次看到：%s", ". First seen: %s") % seen[key]
                    if key in P.SLIPS and (slips_on or key in slips):     # its 小插曲: the riddle stays, the answer after it
                        detail += self.t("。偶尔会出点小插曲，多演几次，总会碰上的", ". Now and then it goes another way; play it often enough and it will")
                        if key in slips:
                            detail += self.t(" → %s（%s）", " → %s (%s)") % (self.t(*P.SLIPS[key][1]), slips[key])
                else:
                    detail = self.t("还没见过。它们凑在一起的时候，说不定就来了……", "Not seen yet. When they get together, who knows...")
                if key in P.COMBOS:
                    token = "combo:" + key
                else:
                    token = None               # the pat after a throw: it takes your hand
                cells.append(self.cell("combo", key, self.combo_name(key) if lit else "？？？", lit,
                                       sub=("★" * stars + "☆" * (len(P.GROW_STARS) - stars)) if lit else "", detail=detail,
                                       title=self.combo_name(key) if lit else self.t("还没见过的组合", "A combo not seen yet"),
                                       token=token, col=INK, photo=COMBO_PHOTO.get(key)))   # its stars tell: the name stays ink
                # its 小插曲: a mark of its own in the other corner, the gift's blue (after the stars, in gold, it read as a fourth star)
                cells[-1]["mark"] = ("✦" if key in slips else "✧") if lit and key in P.SLIPS and (slips_on or key in slips) else ""
            out.append((None, INK, cells))
        return out

    def act_cells(self):
        acts = self.data["acts"]
        meta = self.fr.man.get("actions") or {}
        special, common = [], []

        def cell(key, zh, en, hint):
            lit = key in acts
            name = en if self.lang == "en" else zh
            clip = ACT_CLIP.get(key, key)
            playable = clip in meta and clip not in P.INTERNAL_ACTIONS and key not in P.INTERNAL_ACTIONS
            if lit:
                detail = self.t("第一次看到：%s", "First seen: %s") % acts[key] if isinstance(acts.get(key), str) and acts[key] else ""
                if not playable:
                    detail += self.t(" 这个要你动手，它们才会做。", " This one takes your hand.")
            else:
                detail = hint
            return self.cell("act", key, name if lit else "？？？", lit, detail=detail.strip(),
                             title=name if lit else self.t("还没见过的动作", "An action not seen yet"),
                             token=key if playable else None, clip=clip)

        for key, (zh, en) in P.GROW_ACTS.items():
            special.append(cell(key, zh, en, self.t("还没见过。要你逗逗它们才看得到……", "Not seen yet. It takes a little teasing...")))
        order = [a for a in P.ACTION_ORDER if a in meta] + [k for k, _, _ in ACT_EXTRA]
        extra = dict((k, (zh, en)) for k, zh, en in ACT_EXTRA)
        for key in order:
            if key in P.GROW_ACTS:
                continue
            zh, en = extra.get(key) or (str((meta.get(key) or {}).get("label") or key), P.EN_LABELS.get(key, key))
            common.append(cell(key, zh, en, self.t("还没见过。平时多看看它们……", "Not seen yet. Watch them a while...")))
        return [(None, INK, special + common)]     # one section: the count is on the tab

    def read_look(self):
        """How the plain signs look now (state.json "sign"; the pets write it)."""
        look = dict(getattr(P, "SIGN_LOOK_DEFAULT", {}))
        d = read_json(os.path.join(self.home, "state.json")).get("sign")
        if isinstance(d, dict):
            for kind in look:
                if P.look_level(kind, d.get(kind)) is not None:
                    look[kind] = d[kind]
        return look

    def level(self):
        xp = self.data.get("xp")
        return P.grow_level(xp if type(xp) is int else 0)

    def counts(self, page):
        if page == "gifts":
            lv = self.level()[0]
            return sum(1 for g in P.LEVEL_GIFTS if g[0] <= lv), len(P.LEVEL_GIFTS)
        cells = [c for _, _, cs in self.cells[page] for c in cs]
        return sum(1 for c in cells if c["lit"]), len(cells)

    def news(self, page):
        if page == "gifts":
            return self.gift_news()
        return [c for _, _, cs in self.cells.get(page, ()) for c in cs if c.get("new")]

    # ------------------------------------------------------------------ pictures
    def box_px(self, page):
        g = GRID[page]
        return self.S(g["pw"]), self.S(g["ph"])

    def picture(self, c, state=None, k=None):
        """-> the PhotoImage of a cell (made now); None if its frames are missing.  state: "lit", "off" (not found
        yet) or "sealed" (found, not looked at); k: a frame of its clip (the picked action as it plays)."""
        state = state or ("off" if not c["lit"] else ("sealed" if c.get("new") else "lit"))
        if c["kind"] == "item":
            w = h = self.item_px()
        elif c["kind"] == "family":
            w, h = c["w"], c["h"]
        else:
            w, h = self.box_px("combos" if c["kind"] == "combo" else "acts")
        key = (c["kind"], c["key"], state, w, h, k, self.f)
        if key in self.images:
            return self.images[key]
        img = None
        try:
            data = self.picture_data(c, state, w, h, k)
            if data is not None:
                img = tk.PhotoImage(data=data, format="png" if data[:4] == b"\x89PNG" else "ppm")
        except Exception:
            self.on_error(*sys.exc_info())
            img = None
        if k is None:
            self.images[key] = img
        return img

    def picture_data(self, c, state, w, h, k=None):
        fr = self.fr
        sil = None if state == "lit" else (SEALED if state == "sealed" else None)
        if c["kind"] == "item":
            side = int(self.items_man.get("box") or 0)
            if not side or not c.get("file"):
                return None
            raw = frame_at(os.path.join(fr.dir, str(c["file"])), k or 0)
            if raw is None:
                return None
            px = w or self.item_px()
            sil = None if state == "lit" else (SLOT if state == "off" else SEALED)
            ly = layer(raw, side, side, (0, 0, side, side), (0, 0), side / float(px), 0, 0)
            return compose(px, px, VELVET, [ly], sil)
        bg = c.get("bg") or (PHOTO if state == "lit" or c["kind"] == "family" else PHOTO_OFF)
        if state == "off":
            sil = SIL_OFF
        if c.get("scene"):                     # the monument: clear, the stone is drawn under it
            layers = fr.scene(c["scene"], w, h)
            return compose_png(w, h, layers) if layers is not None else None
        if c["kind"] in ("combo", "family"):
            spec = c.get("photo")
            layers = fr.group(spec, w, h) if spec else None
            return compose(w, h, bg, layers, sil) if layers is not None else None
        got = fr.frame(c["clip"], k)
        if got is None:
            return None
        raw, box, kk = got
        if k is not None and c.get("fit"):
            n, fx, fy = c["fit"]               # as it plays: where its picked frame put it
        else:
            n, fx, fy = fr.fit_one(box, w, h)
            if k is None:
                c["fit"] = (n, fx, fy)
        return compose(w, h, bg, [layer(raw, fr.W, fr.H, box, fr.anchor, n, fx, fy)], sil)

    def work(self):
        """One picture a turn of the loop, so the window is there at once and fills in."""
        if not self.todo:
            return
        c, x, y = self.todo.pop(0)
        img = self.picture(c)
        if img is not None:
            self.cv.create_image(x, y, image=img, tags=("pic", "pic:" + c["id"]))
            self.cv.tag_raise("over")
        if self.todo:
            self.root.after(1, self.work)
        else:
            self.start_anim()

    # ------------------------------------------------------------------ the window
    def on_configure(self, e):
        if e.widget is not self.root:
            return
        if (e.width, e.height) != (self.W, self.H):
            if self.resize_job is not None:
                self.root.after_cancel(self.resize_job)
            self.resize_job = self.root.after(120, self.relayout)

    def relayout(self):
        self.resize_job = None
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if w < 50 or h < 50 or (w, h) == (self.W, self.H):
            return
        f = min(w / float(BASE_W), h / float(BASE_H))
        if abs(f - self.f) > 1e-3:
            self.images = {}                   # pictures of the old size: no longer needed
            for sections in self.cells.values():
                for _, _, cells in sections:
                    for c in cells:
                        c.pop("fit", None)
        self.f, self.W, self.H = f, w, h
        self.show(self.page)

    # ------------------------------------------------------------------ drawing
    def round_rect(self, x0, y0, x1, y1, r, **kw):
        pts = (x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0)
        return self.cv.create_polygon(pts, smooth=True, **kw)

    def dot(self, x, y, r, text=""):
        """A red dot: something new is in there."""
        self.cv.create_oval(x - r, y - r, x + r, y + r, fill=RED, outline=CARD, width=max(1, self.S(2)), tags="over")
        if text:
            self.cv.create_text(x, y, text=text, font=("Segoe UI", -max(7, int(r * 1.3)), "bold"), fill=CARD, tags="over")

    def show(self, page):
        if page != self.page:
            self.revealing = None
        self.page = page
        self.anim = None
        if page == "gifts":
            self.gift_pick()                   # what its card shows is looked at: before the tab's red dot is drawn
        cv, S = self.cv, self.S
        cv.delete("all")
        self.hit, self.todo = [], []
        W, H = self.W, self.H
        b = S(12)
        cv.create_rectangle(0, 0, W, H, fill=COVER, outline=COVER_DARK, width=max(1, S(2)))
        self.round_rect(b, b, W - b, H - b, S(10), fill=PAPER, outline=COVER_DARK, width=1)
        cv.create_rectangle(b + S(9), b + S(9), W - b - S(9), H - b - S(9), outline=PAPER_LINE, width=max(1, S(2)), dash=(S(7), S(5)))
        # the index tabs, and how much of it all is found
        x = S(44)
        got = total = 0
        base = S(70)
        for key, zh, en in PAGES:
            label = self.t(zh, en)
            if key != "family":
                g, n = self.counts(key)
                if key in COLLECTED:
                    got, total = got + g, total + n
                label += " %d/%d" % (g, n)
            on = key == page
            item = cv.create_text(x + S(16), S(50), text=label, anchor="w", font=self.font(19 if on else 17, on), fill=CARD if on else INK_DIM)
            x0, y0, x1, y1 = cv.bbox(item)
            tab = self.round_rect(x0 - S(16), S(30) if on else S(36), x1 + S(16), base + S(8), S(9), fill=ACCENT if on else "#e9dcbb",
                                  outline=COVER_DARK if on else PAPER_LINE, width=1)
            cv.tag_lower(tab, item)
            if key != "family" and self.news(key):
                self.dot(x1 + S(12), (S(30) if on else S(36)) + S(4), S(7))
            self.hit.append((x0 - S(16), S(30), x1 + S(16), base, ("page", key)))
            x = x1 + S(28)
        cv.create_rectangle(b + S(12), base, W - b - S(12), base + S(12), fill=PAPER, outline="")
        cv.create_line(S(34), base, W - S(34), base, fill=ACCENT, width=max(2, S(2)))
        cv.create_text(W - S(44), S(50), text=self.t("已收集 %d / %d", "Found %d / %d") % (got, total), anchor="e",
                       font=self.font(16), fill=GOLD if total and got == total else INK_DIM)
        if page == "family":
            self.draw_family()
        elif page == "gifts":
            self.draw_gifts()
        else:
            self.draw_grid(self.cells[page], GRID[page])
            self.draw_info()
            if page == "items":
                self.draw_odds()
            elif page == "combos":
                self.draw_marks()
        later = []                             # a picture made before goes up at once (no flicker when a cell is clicked)
        for c, px, py in self.todo:
            img = self.images.get(self.image_key(c))
            if img is not None:
                cv.create_image(px, py, image=img, tags=("pic", "pic:" + c["id"]))
            else:
                later.append((c, px, py))
        cv.tag_raise("over")
        self.todo = later
        if self.todo:
            self.root.after(1, self.work)
        else:
            self.start_anim()

    def image_key(self, c):
        state = "off" if not c["lit"] else ("sealed" if c.get("new") else "lit")
        if c["kind"] == "item":
            w = h = self.item_px()
        elif c["kind"] == "family":
            w, h = c["w"], c["h"]
        else:
            w, h = self.box_px("combos" if c["kind"] == "combo" else "acts")
        return (c["kind"], c["key"], state, w, h, None, self.f)

    def grid_fit(self, sections, g):
        """-> how much the cells shrink so that all the sections fit above the blackboard (1.0: as they are).
        The sections are packed as draw_grid packs them; titles keep their size."""
        cols, fixed, cells, used = g["cols"], 0.0, 0.0, 0
        for title, _, cs in sections:
            if used and used + 1 + len(cs) <= cols:
                used += 1 + len(cs)
                continue
            rows = (len(cs) - 1) // cols + 1
            fixed += (28 if title is not None else 10) + 6
            cells += rows * (g["ch"] + 8)
            used = len(cs) if len(cs) < cols else 0
        room = BASE_H - 142 - 84
        return max(0.7, min(1.0, (room - fixed) / cells)) if cells else 1.0

    def item_px(self):
        """A treasure's picture in its slot: this many px (the slots shrink when the page is full, grid_fit)."""
        side = int(self.items_man.get("box") or 0) or 60
        n = max(1, int(round(side / (60.0 * self.f))))       # as big as it comes at a whole step down ...
        return max(8, int(round(side / float(n) * self.item_k)))   # ... and shrunk with the slots

    def draw_grid(self, sections, g):
        cv, S = self.cv, self.S
        cols = g["cols"]
        k = self.grid_fit(sections, g) if self.page == "items" else 1.0
        if self.page == "items":
            self.item_k = k
        K = lambda v: S(v * k)                 # inside a cell
        cw, ch, gap = K(g["cw"]), K(g["ch"]), K(8)
        widest, used = 1, 0                    # the widest row as the sections are packed below: the grid is centred on it
        for _, _, cs in sections:
            if used and used + 1 + len(cs) <= cols:
                used += 1 + len(cs)
            else:
                used = len(cs) if len(cs) < cols else 0
            widest = max(widest, used or cols)
        x_left = (self.W - (widest * cw + (widest - 1) * gap)) // 2
        y = S(84)
        self.grid_cells = []                   # where the cells are (what is drawn under the grid keeps clear of them)
        picked = self.sel.get(self.page)
        used = 0                               # cells of the last section in its one row (0: it took whole rows)
        if "pw" in g:
            pw, ph = self.box_px(self.page)
        for title, col, cells in sections:
            got = sum(1 for c in cells if c["lit"])
            done = got == len(cells)
            if used and used + 1 + len(cells) <= cols:     # a short section goes beside the last one
                first = used + 1
            else:
                if used:
                    y += S(28) + ch + gap + S(6)
                first = 0
            left = x_left + first * (cw + gap)
            if title is None:                  # a page of one kind: its count is on the tab
                top = y + S(10)
            else:
                cv.create_text(left + S(2), y + S(12), text="%s  %d/%d" % (title, got, len(cells)) + ("  ✓" if done else ""), anchor="w",
                               font=self.font(17, True), fill=GOLD if done else col)
                top = y + S(28)
            rem = len(cells) % cols           # a page of one kind: its last, short row is centred under the others
            mid_row = (cols - rem) * (cw + gap) // 2 if title is None and rem and len(cells) > cols else 0
            for i, c in enumerate(cells):
                cx = left + (i % cols) * (cw + gap) + (mid_row if i // cols == len(cells) // cols else 0)
                cy = top + (i // cols) * (ch + gap)
                on = picked == c["key"]
                mid = cx + cw // 2
                seed = zlib.crc32(c["key"].encode("utf-8"))
                new = c.get("new")
                name = self.t("新发现！", "New!") if new else c["name"]
                if c["kind"] == "item":        # a slot of the tray, a little label under it
                    x0, y0, x1, y1 = cx + K(5), cy + K(4), cx + cw - K(5), cy + K(94)
                    self.round_rect(x0 + S(2), y0 + S(3), x1 + S(2), y1 + S(3), S(8), fill=SHADOW, outline="")
                    self.round_rect(x0, y0, x1, y1, S(8), fill=hexc(VELVET), outline=ACCENT if on else (c["col"] if c["lit"] else INK_DIM),
                                    width=max(2, S(3)) if on or c["lit"] else 1)
                    self.todo.append((c, mid, (y0 + y1) // 2))
                    c["at"] = (mid, (y0 + y1) // 2)
                    cv.create_text(mid, cy + ch - K(13), text=name, font=self.font(15 if k > 0.92 else 13), fill=RED if new else (INK if c["lit"] else INK_DIM), tags="over")
                    if new:
                        self.dot(x1 - S(2), y0 - S(4) + S(11), S(11), "!")
                    elif c["sub"]:
                        r = S(11)
                        cv.create_oval(x1 - r - S(2), y0 - S(4), x1 + r - S(2), y0 - S(4) + 2 * r, fill=ACCENT, outline=CARD, width=max(1, S(2)), tags="over")
                        cv.create_text(x1 - S(2), y0 - S(4) + r, text=c["sub"], font=("Segoe UI", -S(12), "bold"), fill=CARD, tags="over")
                else:                          # a snapshot taped to the page
                    jit = (seed % 5 - 2) * max(1, S(1))
                    pad = S(5)
                    x0, x1 = mid - pw // 2 - pad, mid - pw // 2 + pw + pad
                    y0 = cy + S(6) + jit
                    y1 = y0 + ph + pad + S(27)
                    cv.create_rectangle(x0 + S(3), y0 + S(3), x1 + S(3), y1 + S(3), fill=SHADOW, outline="")
                    cv.create_rectangle(x0, y0, x1, y1, fill=CARD, outline=ACCENT if on else CARD_EDGE, width=max(2, S(3)) if on else 1)
                    cv.create_rectangle(x0 + pad, y0 + pad, x0 + pad + pw, y0 + pad + ph, fill=hexc(PHOTO if c["lit"] and not new else PHOTO_OFF), outline="")
                    at = (x0 + pad + pw // 2, y0 + pad + ph // 2)
                    self.todo.append((c, at[0], at[1]))
                    c["at"] = at
                    cv.create_text(mid, y1 - S(14), text=name, font=self.font(14 if c["kind"] == "act" else 15),
                                   fill=RED if new else (c["col"] if c["lit"] else INK_DIM), tags="over")
                    lean = S(3) if seed & 1 else -S(3)
                    cv.create_polygon(mid - S(17), y0 - S(5) + lean, mid + S(17), y0 - S(5) - lean, mid + S(17), y0 + S(6) - lean,
                                      mid - S(17), y0 + S(6) + lean, fill=TAPES[seed // 7 % len(TAPES)], outline="", tags="over")
                    if new:
                        self.dot(x1 - S(4), y0 + S(4), S(10), "!")
                    elif c["sub"]:
                        cv.create_text(x1 - pad - S(3), y0 + pad + S(10), text=c["sub"], anchor="e", font=("Segoe UI Symbol", -S(12)),
                                       fill=GOLD, tags="over")
                    if c.get("mark"):
                        cv.create_text(x0 + pad + S(4), y0 + pad + S(10), text=c["mark"], anchor="w", font=("Segoe UI Symbol", -S(14)),
                                       fill=GIFT_COL["slips"], tags="over")
                self.hit.append((cx, cy, cx + cw, cy + ch, ("cell", c)))
                self.grid_cells.append((cx + K(5), cy, cx + cw - K(5), cy + ch - K(4)))     # as drawn, not the margin
            if first + len(cells) < cols and len(cells) <= cols:
                used = first + len(cells)      # room beside it: the next one may take it
            else:
                used = 0
                y = top + ((len(cells) - 1) // cols + 1) * (ch + gap) + S(6)

    def picked_cell(self):
        for _, _, cells in self.cells.get(self.page, ()):
            for one in cells:
                if one["key"] == self.sel.get(self.page):
                    return one
        return None

    def draw_odds(self):
        """Over the blackboard on the treasures' page: how many finds at most until one of at least uncommon / rare /
        special is sure (保底, the player's DIG_DRY).  The odds themselves are not shown: the sure ones are enough."""
        cv, S, d = self.cv, self.S, self.data
        need = getattr(P, "DIG_DRY", {})
        names = self.items_man.get("names") or {}
        locked = getattr(P, "items_locked", lambda lv: ())(self.level()[0])
        have = d["items"]
        def new_left(r):                       # anything not found yet at or above this rarity (that digs may bring)
            at = RARITY_ORDER.index(r)
            return any(k not in have and k not in locked and (info or {}).get("rarity") in RARITY_ORDER
                       and RARITY_ORDER.index(info["rarity"]) >= at for k, info in names.items())
        parts = [(self.t("保底：", "Sure to come: "), INK_DIM)]
        for i, r in enumerate(r for r in RARITY_ORDER if r in need and new_left(r)):
            dry = d.get("dry_" + r) if type(d.get("dry_" + r)) is int else 0
            left = max(1, need[r] - dry)
            label = self.t(*RARITY_LABEL.get(r, (r, r))) + ("" if r == "special" else self.t("以上", " or better"))
            parts.append((self.t("再翻到 %d 件，必有没见过的%s" % (left, label), "a new %s within %s" % (label.lower(), P.plural(left, "find"))),
                          RARITY_COL.get(r, INK)))
            parts.append((self.t("　·　", "  ·  "), INK_DIM))
        if len(parts) > 1:
            parts = parts[:-1]
        elif any(k not in have for k in locked):   # all that digs bring now: the second batch is still to come
            parts = [(self.t("这一批都集齐了！第二批 Lv.%d 加进翻找。", "This batch is complete! The second comes at Lv.%d.") % self.later_at(), ACCENT)]
        else:
            parts = [(self.t("宝贝都集齐了！", "Every treasure found!"), GOLD)]
        x, y = S(48), self.H - S(112) - S(17)
        for text, col in parts:
            item = cv.create_text(x, y, text=text, anchor="w", font=self.font(14), fill=col)
            x = cv.bbox(item)[2]
        if len(parts) > 1:                     # a line of heart: no dig is wasted.  At the end of the line if it fits,
            heart = cv.create_text(self.W - S(48), y, anchor="e", font=self.font(12), fill=INK_DIM,    # else over it if
                                   text=self.t("每一铲都不会白挖，攒够了，没见过的那件总会来找你。",          # the grid
                                               "No dig is wasted: keep at it, and the one you haven't found will come to you."))
            hx0, hy0, hx1, hy1 = cv.bbox(heart)                                                   # leaves room
            if hx0 < x + S(24):
                up = (hx0 + S(4), hy0 - S(24), hx1, hy1 - S(24))      # a few px of the words' own margin may touch
                if any(a[0] < up[2] and up[0] < a[2] and a[1] < up[3] and up[1] < a[3] for a in self.grid_cells):
                    cv.delete(heart)
                else:
                    cv.move(heart, 0, -S(24))

    def draw_marks(self):
        """Over the blackboard on the combos' page: what the blue mark in a photo's corner says (only when one is there)."""
        cv, S = self.cv, self.S
        marks = set(c.get("mark") for _, _, cells in self.cells["combos"] for c in cells) - {"", None}
        x, y = S(48), self.H - S(112) - S(17)
        for mark, words in (("✦", ("碰上过小插曲", "its little surprise seen")), ("✧", ("有小插曲，还没碰上", "has a little surprise, not seen yet"))):
            if mark in marks:
                m = cv.create_text(x, y, text=mark, anchor="w", font=("Segoe UI Symbol", -S(14)), fill=GIFT_COL["slips"])
                w = cv.create_text(cv.bbox(m)[2] + S(4), y, text=self.t(*words), anchor="w", font=self.font(13), fill=INK_DIM)
                x = cv.bbox(w)[2] + S(22)

    def draw_info(self):
        """The little blackboard at the bottom: all about the cell that is picked (chalk, as on their signs)."""
        cv, S = self.cv, self.S
        x0, x1 = S(40), self.W - S(40)
        y0, y1 = self.H - S(112), self.H - S(30)
        cv.create_rectangle(x0 + S(3), y0 + S(4), x1 + S(3), y1 + S(4), fill=SHADOW, outline="")
        cv.create_rectangle(x0, y0, x1, y1, fill=hexc(BOARD), outline=WOOD, width=S(6))
        cv.create_rectangle(x0 + S(3), y0 + S(3), x1 - S(3), y1 - S(3), outline=WOOD_DARK, width=1)
        c = self.picked_cell()
        ym = (y0 + y1) // 2
        news = self.news(self.page)
        if c is None:
            text = self.t("点一格看看。", "Click one to see more.")
            if news:
                text = self.t("有 %d 个新发现还没拆开，点一下红点的那格。", "%d new finds still sealed: click one with a red dot.") % len(news)
            cv.create_text(x0 + S(22), ym, text=text, anchor="w", font=self.font(16), fill=CHALK if news else DIM)
            return
        head = cv.create_text(x0 + S(22), ym - S(22), text=c["title"], anchor="w", font=self.font(18, True), fill=CHALK if c["lit"] else DIM)
        key = (self.page, c["key"])
        if c.get("stat"):                      # one line beside the name: smaller till it ends before the button (or the edge)
            button = (c["lit"] and c["token"]) or (not c["lit"] and c["nudge"] and key not in self.nudged)
            end = x1 - (S(182) if button else S(22))
            for size in (14, 13, 12, 11, 10):
                stat = cv.create_text(cv.bbox(head)[2] + S(18), ym - S(21), text=c["stat"], anchor="w", font=self.font(size), fill=DIM)
                if cv.bbox(stat)[2] <= end or size == 10:
                    break
                cv.delete(stat)
        detail = c["detail"]
        if c["nudge"] and key in self.nudged:
            detail += "  ——" + c["nudge"]
        cv.create_text(x0 + S(22), ym - S(4), text=detail, anchor="nw", font=self.font(15), fill=CHALK,
                       width=x1 - x0 - S(230))
        bx1 = x1 - S(20)
        bx0 = bx1 - S(150)
        if not c["lit"] and c["nudge"] and key not in self.nudged:
            self.round_rect(bx0, ym - S(18), bx1, ym + S(18), S(8), outline=DIM, width=max(1, S(2)), fill=hexc(BOARD))
            cv.create_text((bx0 + bx1) // 2, ym, text=self.t("再给点提示", "One more hint"), font=self.font(16), fill=DIM)
            self.hit.append((bx0, ym - S(18), bx1, ym + S(18), ("nudge", key)))
        if c["lit"] and c["token"]:
            self.round_rect(bx0, ym - S(18), bx1, ym + S(18), S(8), outline=MINT, width=max(1, S(2)), fill=hexc(BOARD))
            cv.create_text((bx0 + bx1) // 2, ym, text=self.t("拿出来玩", "Play with it") if c["kind"] == "item" else self.t("让它们演一遍", "Play it"),
                           font=self.font(16, True), fill=MINT)
            self.hit.append((bx0, ym - S(18), bx1, ym + S(18), ("play", c)))

    def draw_family(self):
        cv, S, d = self.cv, self.S, self.data

        def num(k):
            v = d.get(k)
            return v if type(v) in (int, float) else 0

        level, into, need = P.grow_level(int(num("xp")))
        # a sheet of notes on the left: the level, and what they have been through together
        nx0, ny0 = S(56), S(100)
        nx1, ny1 = nx0 + S(500), self.H - S(40)
        cv.create_rectangle(nx0 + S(4), ny0 + S(4), nx1 + S(4), ny1 + S(4), fill=SHADOW, outline="")
        cv.create_rectangle(nx0, ny0, nx1, ny1, fill=CARD, outline=CARD_EDGE)
        cv.create_polygon(nx0 + S(190), ny0 - S(8), nx0 + S(250), ny0 - S(12), nx0 + S(251), ny0 + S(6), nx0 + S(191), ny0 + S(10), fill=TAPES[2], outline="")
        r = S(40)
        mx, my = nx0 + S(64), ny0 + S(66)
        cv.create_oval(mx - r, my - r, mx + r, my + r, fill="#f6c945", outline=GOLD, width=max(2, S(3)))
        cv.create_oval(mx - r + S(7), my - r + S(7), mx + r - S(7), my + r - S(7), outline=CARD, width=max(1, S(2)), dash=(S(4), S(4)))
        cv.create_text(mx, my, text="Lv.%d" % level, font=("Segoe UI", -S(23), "bold"), fill=INK)
        bx0, bx1 = mx + r + S(24), nx1 - S(30)
        cv.create_text(bx0, my - S(30), text=self.t("全家的等级", "The family's level"), anchor="w", font=self.font(17, True), fill=INK)
        by = my
        top = level >= P.LEVEL_MAX
        self.round_rect(bx0, by - S(9), bx1, by + S(9), S(8), fill=PAPER, outline=INK_DIM, width=1)
        if top or (need > 0 and into > 0):
            frac = 1.0 if top else min(1.0, into / float(need))
            self.round_rect(bx0 + S(3), by - S(6), bx0 + S(3) + max(S(12), int((bx1 - bx0 - S(6)) * frac)), by + S(6), S(6),
                            fill=GOLD if top else ACCENT, outline="")
        if top:
            cv.create_text(bx0, by + S(26), text=self.t("满级了！", "Top level!"), anchor="w", font=self.font(15, True), fill=GOLD)
        else:
            cv.create_text(bx0, by + S(26), text=self.t("再攒 %d 经验，升到 Lv.%d", "%d more XP to Lv.%d") % (need - into, level + 1),
                           anchor="w", font=self.font(15), fill=INK)
            cv.create_text(bx1, by + S(26), text=self.t("这一级 %d/%d", "this level %d/%d") % (into, need), anchor="e", font=self.font(13), fill=INK_DIM)
        gift = P.next_gift(level)               # the next gift: a click away on its page
        gtext = (self.t("下一份礼物：Lv.%d %s  ›", "Next gift: Lv.%d %s  ›") % (gift[0], self.t(*gift[2])) if gift
                 else self.t("礼物全都到手了  ›", "Every gift is yours  ›"))
        gid = cv.create_text(nx0 + S(30), ny0 + S(132), text=gtext, anchor="w", font=self.font(15, True), fill=ACCENT)
        gx0, gy0, gx1, gy1 = cv.bbox(gid)
        self.hit.append((gx0 - S(4), gy0 - S(4), gx1 + S(4), gy1 + S(4), ("page", "gifts")))
        cv.create_text(nx0 + S(30), ny0 + S(160), anchor="w", font=self.font(13), fill=INK_DIM,
                       text=self.t("经验主要来自智能体干完的回合，也来自新发现、星星和陪玩。",
                                   "XP comes mostly from the agent's turns; also from finds, stars and play."))
        hours = num("work_secs")
        played = sum(v for v in d["combos"].values() if type(v) is int)
        stars = sum(1 for v in d["combos"].values() if type(v) is int for need_, _ in P.GROW_STARS if v >= need_)
        cells = len(COMBO_ORDER)
        things = sum(v for v in d["items"].values() if type(v) is int)
        kinds = len([1 for v in d["items"].values() if type(v) is int and v > 0])
        all_kinds = len((self.items_man.get("names") or {})) or kinds
        m = int(hours // 60)
        span = self.t("%d 分钟", "%d min") % m if m < 60 else self.t("%d 小时 %d 分", "%d h %d min") % (m // 60, m % 60)
        rows = (
            (self.t("在一起", "Together"), self.t("第 %d 天", "day %d") % num("days"),
             self.t("从 %s 起，有它们陪着的日子（不用连着）", "days with them since %s, not in a row") % (d.get("since") or "-")),
            (self.t("一起干活", "Work"), self.t("%d 个回合 · %s" % (num("turns"), span), "%s · %s" % (P.plural(num("turns"), "turn"), span)),
             self.t("智能体每干完一轮用过工具的活儿，算一个回合", "each round of work the agent finishes with tools")),
            (self.t("派出的帮手", "Helpers"), self.t("回来了 %d 个", "%d came back") % num("agents"),
             self.t("智能体派出去的帮手，干完回来一个记一个", "helpers the agent sent out, back and done")),
            (self.t("修好的错", "Fixed"), self.t("%d 次" % num("fixes"), P.plural(num("fixes"), "time")),
             self.t("工具出了错，后来又成功了", "a tool failed, then worked")),
            (self.t("陪它们玩", "Play"), self.t("%d 次" % num("plays"), P.plural(num("plays"), "time")),
             self.t("点、拖、扔、逗醒、拿宝贝玩；10 秒内只算一次", "clicks, drags, throws, treasures; once in 10 s")),
            (self.t("组合", "Combos"), self.t("演过 %d 次 · ★ %d/%d", "%d played · ★ %d/%d") % (played, stars, 3 * cells),
             self.t("同一个组合演满 10、30、100 次，各得一颗星", "a star at 10, 30 and 100 times of one combo")),
            (self.t("宝贝", "Treasures"), self.t("%d/%d 种 · 一共 %d 件", "%d/%d kinds · %d in all") % (kinds, all_kinds, things),
             self.t("翻找翻到的；“宝贝”页里能拿出来玩", "dug up; play with them on the Treasures page")),
            (self.t("翻找机会", "Digs left"), self.t("%d 次（最多 %d 次）", "%d (at most %d)") % (num("chances"), P.dig_cap(level)),
             self.t("智能体干活每累计 10 分钟攒 1 次；右键“翻找”用掉", "one each 10 minutes of the agent's work; the menu's Rummage uses one")),
        )
        y = ny0 + S(196)
        step = max(S(44), min(S(58), (ny1 - S(20) - y) // len(rows)))
        for label, value, why in rows:
            cv.create_text(nx0 + S(30), y, text=label, anchor="w", font=self.font(16), fill=INK_DIM)
            cv.create_text(nx0 + S(150), y, text=value, anchor="w", font=self.font(18), fill=INK)
            cv.create_text(nx0 + S(150), y + S(19), text=why, anchor="w", font=self.font(12), fill=INK_DIM)
            cv.create_line(nx0 + S(24), y + S(32), nx1 - S(24), y + S(32), fill="#cfe0ea", width=1)
            y += step
        # the family picture on the right, in a wooden frame (at the top level: the monument, a brass plate under
        # it); under it, the last days of work
        rx0, rx1 = nx1 + S(40), self.W - S(56)
        mon = d.get("monument") if isinstance(d.get("monument"), dict) and d.get("monument") and top else None
        fw, fh = min(rx1 - rx0 - S(24), S(400)), S(196 if mon else 170)
        fx0 = (rx0 + rx1) // 2 - fw // 2
        fy0 = S(126 if mon else 132)
        cv.create_rectangle(fx0 - S(12) + S(5), fy0 - S(12) + S(6), fx0 + fw + S(12) + S(5), fy0 + fh + S(12) + S(6), fill=SHADOW, outline="")
        cv.create_rectangle(fx0 - S(12), fy0 - S(12), fx0 + fw + S(12), fy0 + fh + S(12), fill=WOOD, outline=WOOD_DARK, width=max(1, S(2)))
        cv.create_rectangle(fx0, fy0, fx0 + fw, fy0 + fh, fill=hexc(PHOTO), outline=WOOD_DARK)
        if mon:
            self.draw_stone(fx0, fy0, fw, fh)
            c = {"kind": "family", "key": "monument", "id": "family", "lit": True, "scene": MONUMENT_PHOTO, "w": fw, "h": fh}
            self.todo.append((c, fx0 + fw // 2, fy0 + fh // 2))
            py1 = self.draw_plate(mon, fx0 - S(12), fy0 + fh + S(30), fx0 + fw + S(12))
            self.draw_days(rx0, py1 + S(44), rx1, self.H - S(48))
            return
        c = {"kind": "family", "key": "family", "id": "family", "lit": True, "photo": FAMILY_PHOTO, "w": fw, "h": fh}
        self.todo.append((c, fx0 + fw // 2, fy0 + fh // 2))
        cv.create_text(fx0 + fw // 2, fy0 + fh + S(42), text=self.t("我们一家 · Lv.%d", "The family · Lv.%d") % level, font=self.font(20, True), fill=INK)
        self.draw_days(rx0, fy0 + fh + S(84), rx1, self.H - S(48))

    def draw_stone(self, fx0, fy0, fw, fh):
        """The milestone in the monument's picture (scene_fit), under the family: the ground, the little flag stuck
        in the stone's top (its pole behind it), the stone with the level cut in it, tufts of grass at its foot."""
        cv = self.cv
        u, sx, sy = scene_fit(fw, fh)

        def X(x):
            return fx0 + sx + x * u

        def Y(y):
            return fy0 + sy - y * u
        lw = lambda k: max(1, int(k * u))
        cv.create_rectangle(fx0 + 1, Y(0.02), fx0 + fw - 1, fy0 + fh - 1, fill="#bfd6c9", outline="")    # the ground
        bw, tw, th = MONUMENT_STONE
        cv.create_oval(X(-bw - 0.14), Y(0.08), X(bw + 0.14), Y(-0.1), fill="#a9c3b4", outline="")       # its shadow
        px, top, blen, bwid = MONUMENT_FLAG
        SB = getattr(P, "SignBoard", None)
        wood = self.argb(SB.FRAMES["wood"][0]) if SB else WOOD
        edge = self.argb(SB.FRAMES["wood"][1]) if SB else WOOD_DARK
        slate = self.argb(SB.SLATE) if SB else "#2f4a3e"
        self.draw_pedestal(X, Y, lw)
        cv.create_line(X(px), Y(th - 0.02), X(px), Y(top), fill=WOOD_DARK, width=lw(0.05), capstyle="round")
        b0, b1, a0, a1 = Y(top - 0.06 - bwid), Y(top - 0.06), X(px), X(px + blen)
        notch = 0.3 * (b0 - b1)
        mid = (b0 + b1) / 2.0
        cv.create_polygon(a0, b1, a1, b1, a1 - notch, mid, a1, b0, a0, b0, fill=wood, outline=edge, width=lw(0.015))
        t = 0.05 * u
        cv.create_polygon(a0, b1 + t, a1 - t, b1 + t, a1 - notch - t * 0.6, mid, a1 - t, b0 - t, a0, b0 - t, fill=slate, outline="")
        self.star(a0 + (a1 - notch - a0) * 0.45, mid, 0.1 * u, "#ffd86a")
        for gx, side in ((-bw - 0.02, -1), (bw + 0.02, 1), (-0.55, 1)):       # grass at its foot
            for j, (dx, hh) in enumerate(((-0.06, 0.13), (0.0, 0.19), (0.06, 0.12))):
                cv.create_line(X(gx + dx * 0.4), Y(0.0), X(gx + dx + side * 0.02), Y(hh), fill="#5f8a45" if j == 1 else "#6f9a52",
                               width=lw(0.03), capstyle="round")

    def draw_pedestal(self, X, Y, lw):
        """The stone: cut, three tiers (a plinth, the block with a sunk panel and the level cut in it, a cap slab
        they stand on), each with its top seen a little from above; lit from the upper left, the right sides in shade."""
        cv = self.cv
        y = 0.0
        for i, (hw, h) in enumerate(MONUMENT_TIERS):
            y0, y1 = y, y + h
            if i != 1:                         # the top of the plinth and of the cap: seen a little from above
                back = PED_TOP_DEPTH
                cv.create_polygon(X(-hw), Y(y1), X(hw), Y(y1), X(hw - back), Y(y1 + back), X(-hw + back), Y(y1 + back),
                                  fill=PED_TOP, outline=PED_EDGE, width=1)
            cv.create_rectangle(X(-hw), Y(y1), X(hw), Y(y0), fill=PED_FRONT, outline=PED_EDGE, width=1)
            side = min(0.07, 0.25 * hw)
            cv.create_rectangle(X(hw - side), Y(y1), X(hw), Y(y0), fill=PED_SIDE, outline="")
            cv.create_line(X(-hw) + 1, Y(y1) + 1, X(hw - side), Y(y1) + 1, fill=PED_TOP)             # the lit upper edge
            if i == 1:                         # in the shade of the cap over it
                cv.create_rectangle(X(-hw) + 1, Y(y1), X(hw) - 1, Y(y1 - 0.035), fill=PED_SIDE, outline="")
            else:                              # a band of gold along the plinth's top and the cap's foot
                gy = y1 - 0.025 if i == 0 else y0 + 0.022
                cv.create_line(X(-hw) + 1, Y(gy), X(hw) - 1, Y(gy), fill=GOLD, width=lw(0.022))
            y = y1
        # the panel let into the block: dark green like the flag, a gold rim, the level in gold
        bh0, bh1 = MONUMENT_TIERS[0][1], MONUMENT_TIERS[0][1] + MONUMENT_TIERS[1][1]
        px0, px1, py0, py1 = -0.5, 0.46, bh0 + 0.08, bh1 - 0.1
        SB = getattr(P, "SignBoard", None)
        slate = self.argb(SB.SLATE) if SB else "#2f4a3e"
        cv.create_rectangle(X(px0), Y(py1), X(px1), Y(py0), fill=slate, outline=GOLD, width=lw(0.022))
        u = X(1.0) - X(0.0)
        f = ("Segoe UI", -max(8, int(0.2 * u)), "bold")
        cx, cy = X((px0 + px1) / 2.0), Y((py0 + py1) / 2.0)
        o = max(1, int(0.012 * u))
        cv.create_text(cx + o, cy + o, text="Lv.20", font=f, fill="#1d2e26")
        cv.create_text(cx, cy, text="Lv.20", font=f, fill="#ffd86a")

    def star(self, x, y, r, fill):
        pts = []
        for j in range(10):
            a = math.pi / 5.0 * j
            k = r if j % 2 == 0 else 0.45 * r
            pts += [x + k * math.sin(a), y - k * math.cos(a)]
        self.cv.create_polygon(pts, fill=fill, outline="")

    def draw_plate(self, mon, x0, y0, x1):
        """The brass plate under the monument: the numbers of the day they got there, never changed after.  -> its
        lower edge."""
        cv, S = self.cv, self.S

        def num(k):
            v = mon.get(k)
            return v if type(v) in (int, float) else 0

        def big(v):
            return "{:,}".format(int(v))
        lines = (
            (self.t("我们一起走到了 Lv.20", "Together we got to Lv.20"), 19, True),
            (self.t("%s 出发 · %s 到达", "Set out %s · got there %s") % (mon.get("since") or "-", mon.get("day") or "-"), 14, False),
            (self.t("一起 %d 天 · 干活 %s 个回合 · %d 小时" % (num("days"), big(num("turns")), int(num("work_secs") // 3600)),
                    "%s · %s turns of work · %s" % (P.plural(num("days"), "day"), big(num("turns")),
                                                   P.plural(int(num("work_secs") // 3600), "hour"))), 14, False),
            (self.t("翻到 %s 件宝贝 · 演过 %s 次组合", "%s treasures dug up · %s combos played")
             % (big(num("things")), big(num("played"))), 14, False),
        )
        y1 = y0 + S(140)
        cv.create_rectangle(x0 + S(3), y0 + S(4), x1 + S(3), y1 + S(4), fill=SHADOW, outline="")
        self.round_rect(x0, y0, x1, y1, S(8), fill=BRASS, outline=BRASS_DARK, width=max(1, S(2)))
        self.round_rect(x0 + S(7), y0 + S(7), x1 - S(7), y1 - S(7), S(5), fill="", outline="#c19a45", width=1)
        for sx_, sy_ in ((x0 + S(16), y0 + S(16)), (x1 - S(16), y0 + S(16)), (x0 + S(16), y1 - S(16)), (x1 - S(16), y1 - S(16))):
            r = S(4)
            cv.create_oval(sx_ - r, sy_ - r, sx_ + r, sy_ + r, fill="#b8933f", outline=BRASS_DARK)
            cv.create_line(sx_ - r + 1, sy_, sx_ + r - 1, sy_, fill=BRASS_DARK)
        cx = (x0 + x1) // 2
        y = y0 + S(30)
        for i, (text, px, bold) in enumerate(lines):
            cv.create_text(cx + 1, y + 1, text=text, font=self.font(px, bold), fill="#f1dc9c")      # cut in
            cv.create_text(cx, y, text=text, font=self.font(px, bold), fill=BRASS_INK)
            y += S(34 if i == 0 else 27)
        return y1

    # ------------------------------------------------------------------ the 礼物 page
    def gift_at(self, lv):
        return [g for g in P.LEVEL_GIFTS if g[0] == lv]

    def xp_at(self, lv):
        """XP from Lv.1 to the start of Lv.lv."""
        return sum(P.grow_need(i) for i in range(1, lv))

    def gift_news(self):
        """-> the ids of the gifts the level has brought that you have not looked at here yet (a red dot; the
        pets' menu counts them too: the player's gift_news)."""
        return P.gift_news(self.seen, self.level()[0])

    def gift_pick(self):
        """-> the gift the card shows: the one clicked; else the first you have not looked at yet; else the next one;
        at the top, the monument (the first of the last level).  The gifts of the level shown are looked at."""
        gifts = P.LEVEL_GIFTS
        pick = self.sel.get("gifts")
        if pick not in [g[1] for g in gifts]:
            news = self.gift_news()
            nxt = P.next_gift(self.level()[0])
            pick = news[0] if news else (nxt or self.gift_at(gifts[-1][0])[0])[1]
            self.sel["gifts"] = pick
        lv = next(g[0] for g in gifts if g[1] == pick)
        fresh = ["gift:" + g[1] for g in self.gift_at(lv) if g[1] in self.gift_news()]
        if fresh:
            self.mark_seen(fresh)
        return pick

    def draw_gifts(self):
        """The gift picked (gift_pick) on a card at the top; the road of levels; the signs' looks."""
        cv, S = self.cv, self.S
        level, into, need = self.level()
        xp = self.data.get("xp") if type(self.data.get("xp")) is int else 0
        gifts = P.LEVEL_GIFTS
        nxt = P.next_gift(level)
        pick = self.gift_pick()
        lv, gid, name, line = next(g for g in gifts if g[1] == pick)
        # the card at the top: the gift picked (both of its level, a line each)
        x0, y0, x1, y1 = S(56), S(96), self.W - S(56), S(214)
        cv.create_rectangle(x0 + S(4), y0 + S(4), x1 + S(4), y1 + S(4), fill=SHADOW, outline="")
        cv.create_rectangle(x0, y0, x1, y1, fill=CARD, outline=CARD_EDGE)
        self.gift_badge(x0 + S(66), (y0 + y1) // 2, S(38), gid, level >= lv, lv % 5 == 0)
        tx = x0 + S(126)
        both = self.gift_at(lv)
        ty, ly, step, sy = (S(28), S(60), S(22), y1 - S(22)) if len(both) < 2 else (S(25), S(52), S(21), y1 - S(16))
        title = "Lv.%d  " % lv + "  +  ".join(self.t(*g[2]) for g in both)
        cv.create_text(tx, y0 + ty, text=title, anchor="w", font=self.font(21, True), fill=INK)
        for i, g in enumerate(both):
            cv.create_text(tx, y0 + ly + i * step, text=self.t(*g[3]), anchor="w", font=self.font(14), fill=INK,
                           width=x1 - S(24) - tx)
        if level >= lv:
            state, col = self.t("已经得到了 ✓", "Yours ✓"), GOLD
        else:
            state, col = self.t("还差 %d 经验（现在 Lv.%d）", "%d more XP (Lv.%d now)") % (self.xp_at(lv) - xp, level), INK_DIM
            if pick == (nxt or (0, ""))[1]:
                state = self.t("下一份礼物 · ", "Next gift · ") + state
            prev = max([g[0] for g in gifts if g[0] < lv] + [1])
            a, b = self.xp_at(prev), self.xp_at(lv)
            frac = min(1.0, max(0.0, (xp - a) / float(max(1, b - a))))
            bx0, bx1 = x1 - S(250), x1 - S(26)
            self.round_rect(bx0, sy - S(8), bx1, sy + S(8), S(7), fill=PAPER, outline=INK_DIM, width=1)
            if frac > 0:
                self.round_rect(bx0 + S(3), sy - S(5), bx0 + S(3) + max(S(10), int((bx1 - bx0 - S(6)) * frac)), sy + S(5), S(5),
                                fill=GIFT_COL.get(gid, ACCENT), outline="")
        sid = cv.create_text(tx, sy, text=state, anchor="w", font=self.font(15, True), fill=col)
        for g in (both if level >= lv else ()):  # yours: where it is (a page a click away; a look: down below)
            where = GIFT_WHERE.get(g[1])
            if where and (g[1] != "monument" or self.data.get("monument")):
                lid = cv.create_text(cv.bbox(sid)[2] + S(18), sy, text=self.t(*where[1]) + "  ›", anchor="w",
                                     font=self.font(15, True), fill=ACCENT)
                gx0, gy0, gx1, gy1 = cv.bbox(lid)
                self.hit.append((gx0 - S(4), gy0 - S(4), gx1 + S(4), gy1 + S(4), ("page", where[0])))
                break
            if g[1].split("_")[0] in P.SIGN_LOOKS:
                cv.create_text(cv.bbox(sid)[2] + S(18), sy, text=self.t("在下面的“牌子”里换上  ↓", "Pick it in The signs below  ↓"),
                               anchor="w", font=self.font(14), fill=INK_DIM)
                break
        self.draw_route(level, pick)
        self.draw_workshop(level)

    def gift_badge(self, x, y, r, gid, got, big, picked=False, lv=None, more=0, new=False):
        """A gift as a round badge: filled in its colour once it is yours (a gold tick; a red dot until you have
        looked at it), an outline before.  On the road (lv given) a little tag with its level on its lower edge."""
        cv, S = self.cv, self.S
        col = GIFT_COL.get(gid, ACCENT)
        full = got
        if picked:                             # filled with the card's colour: the road does not show through
            cv.create_oval(x - r - S(7), y - r - S(7), x + r + S(7), y + r + S(7), fill=CARD, outline=ACCENT, width=max(2, S(3)))
        if big:                                # every fifth level: a ring of gold round it
            cv.create_oval(x - r - S(3), y - r - S(3), x + r + S(3), y + r + S(3), fill=CARD, outline=GOLD, width=max(1, S(2)))
        if full:
            cv.create_oval(x - r, y - r, x + r, y + r, fill=col, outline=CARD, width=max(1, S(2)))
        else:
            cv.create_oval(x - r, y - r, x + r, y + r, fill=CARD, outline=col, width=max(1, S(2)))
        icon = GIFT_ICON.get(gid.split("_")[0], "?")
        cv.create_text(x, y - (S(2) if lv else 0), text=icon, font=(ICON_FONT, -int(r * (0.95 if lv else 1.05))),
                       fill=CARD if full else col)
        if full and new:                       # yours, not looked at here yet: a red dot (gone once its card has shown)
            self.dot(x + r - S(2), y - r + S(4), max(S(7), r // 3), "!")
        elif full:                             # a tick: it is yours
            tr_ = max(S(7), r // 3)
            cv.create_oval(x + r - tr_ * 3 // 2, y - r - tr_ // 2, x + r + tr_ // 2, y - r + tr_ * 3 // 2, fill=GOLD, outline=CARD, width=1)
            cv.create_text(x + r - tr_ // 2, y - r + tr_ // 2, text="✓", font=("Segoe UI Symbol", -int(tr_ * 1.3), "bold"), fill=CARD)
        # two gifts at this level (more): both names are under it; a count on the badge was a riddle
        if lv:                                 # its level, on a tag across the lower edge
            tw, th = S(22 if lv < 10 else 26), S(8)
            ty = y + r
            self.round_rect(x - tw, ty - th, x + tw, ty + th, th, fill=col if full else CARD, outline=CARD if full else col,
                            width=max(1, S(1.5)))
            cv.create_text(x, ty, text="Lv.%d" % lv, font=("Segoe UI", -S(11), "bold"), fill=CARD if full else col)

    def road_points(self):
        """-> (the road as one line of points, the index of each level's stop on it).  Three rows, the middle one back
        from right to left, half circles out to the side between them."""
        S = self.S
        xa, xb = S(124), self.W - S(124)
        ys = (S(292), S(400), S(508))
        stops = {}
        for row, (lo, hi) in enumerate(ROUTE_ROWS):
            n = hi - lo
            for i, lv in enumerate(range(lo, hi + 1)):
                x = xa + (xb - xa) * i / float(n)
                stops[lv] = (int(x if row % 2 == 0 else xa + xb - x), ys[row])
        top = getattr(P, "LEVEL_MAX", 20)
        pts, idx = [stops[1]], {1: 0}
        for lv in range(1, top):
            (ax, ay), (bx, by) = stops[lv], stops[lv + 1]
            if ay != by:                       # a turn
                r = (by - ay) / 2.0
                side = 1 if ax > self.W // 2 else -1
                for k in range(1, 24):
                    t = math.pi * k / 24.0
                    pts.append((int(ax + side * r * math.sin(t)), int(ay + r - r * math.cos(t))))
            pts.append((bx, by))
            idx[lv + 1] = len(pts) - 1
        return pts, idx, stops

    def draw_route(self, level, pick):
        """Lv.1 to LEVEL_MAX as a road on the page: a band of sand with a stripe in the accent as far as you have
        come; a dot at each level, a badge where there is a gift; you, standing at your level."""
        cv, S = self.cv, self.S
        top = getattr(P, "LEVEL_MAX", 20)
        pts, idx, stops = self.road_points()
        flat = [v for xy in pts for v in xy]
        news = self.gift_news()
        cv.create_line(*flat, fill=ROAD_EDGE, width=S(20), capstyle="round", joinstyle="round")
        cv.create_line(*flat, fill=ROAD, width=S(15), capstyle="round", joinstyle="round")
        done = pts[:idx[min(level, top)] + 1]
        if len(done) > 1:
            cv.create_line(*[v for xy in done for v in xy], fill=ACCENT, width=S(6), capstyle="round", joinstyle="round")
        for lv in range(1, top + 1):
            x, y = stops[lv]
            here = [g for g in P.LEVEL_GIFTS if g[0] == lv]
            past = level >= lv
            if here:
                big = lv % 5 == 0
                r = S(22 if big else 19)
                ids = [g[1] for g in here]
                self.gift_badge(x, y, r, ids[0], past, big, picked=pick in ids, lv=lv, more=len(here) - 1,
                                new=any(i in news for i in ids))
                for i, g in enumerate(here):
                    cv.create_text(x, y + r + S(22) + i * S(16), text=self.t(*g[2]), font=self.font(11, i == 0 and past),
                                   fill=INK if past else INK_DIM)
                nxt = ids[0] if pick not in ids else ids[(ids.index(pick) + 1) % len(ids)]
                self.hit.append((x - r - S(8), y - r - S(8), x + r + S(8), y + r + S(14 + 16 * len(here)), ("gift", nxt)))
            else:
                r = S(5)
                cv.create_oval(x - r, y - r, x + r, y + r, fill=CARD if past else ROAD, outline=ACCENT if past else ROAD_EDGE,
                               width=max(1, S(2)))
                cv.create_text(x, y + S(22), text=str(lv), font=("Segoe UI", -S(11)), fill=INK_DIM)
        # you are here: the big one, standing on its dot or on top of its badge
        x, y = stops[min(level, top)]
        here = self.gift_at(level)
        feet = y - (S(22 if level % 5 == 0 else 19) - S(2) if here else S(3))     # on a badge: its feet on the rim
        img = self.marker_image(S(MARKER_H))
        if img is not None:
            cv.create_image(x, feet, image=img, anchor="s", tags="over")

    def marker_image(self, h):
        """The big one standing, h px tall, on nothing (a PNG with alpha): it stands on the road, not on a photo."""
        key = ("family", "marker", "lit", h, h, None, self.f)
        if key not in self.images:
            img = None
            try:
                got = self.fr.frame("idle", 0)
                if got is not None:
                    raw, box, _ = got
                    ly = layer(raw, self.fr.W, self.fr.H, box, self.fr.anchor, (box[3] - box[1]) / float(h), 0, 0)
                    if ly is not None:
                        img = tk.PhotoImage(data=png(ly, ly[0], ly[1]), format="png")
            except Exception:
                self.on_error(*sys.exc_info())
            self.images[key] = img
        return self.images[key]

    def draw_workshop(self, level):
        """The signs: one as it looks now, and the chalks, frames and shapes to pick from (those the level has brought)."""
        cv, S = self.cv, self.S
        x0, y0, x1, y1 = S(56), S(588), self.W - S(56), self.H - S(36)
        cv.create_rectangle(x0 + S(4), y0 + S(4), x1 + S(4), y1 + S(4), fill=SHADOW, outline="")
        cv.create_rectangle(x0, y0, x1, y1, fill=CARD, outline=CARD_EDGE)
        cv.create_text(x0 + S(24), y0 + S(24), text=self.t("牌子", "The signs"), anchor="w", font=self.font(18, True), fill=INK)
        cv.create_text(x0 + S(24), y0 + S(50), text=self.t("点一下就换上，它们会举起来给你看。", "Click one: they hold it up to show you."),
                       anchor="w", font=self.font(12), fill=INK_DIM)
        px0, px1 = x0 + S(24), x0 + S(330)
        cv.create_rectangle(px0, y0 + S(66), px1, y1 - S(16), fill="#e9e1cc", outline="")
        self.draw_sign((px0 + px1) // 2, (y0 + S(66) + y1 - S(16)) // 2, self.look, S(22))
        rows = (("chalk", self.t("粉笔", "Chalk"), P.SIGN_CHALKS), ("frame", self.t("外框", "Frame"), P.SIGN_FRAMES),
                ("board", self.t("样式", "Shape"), P.SIGN_BOARDS))
        cx0 = px1 + S(30)
        ry = y0 + S(36)
        step = (y1 - S(26) - ry) // 3
        for kind, label, choices in rows:
            cy = ry + step // 2
            cv.create_text(cx0, cy, text=label, anchor="w", font=self.font(15, True), fill=INK)
            x = cx0 + S(62)
            for row in choices:
                name, lv = row[0], row[1]
                zh, en = row[-1]
                mine = self.look.get(kind) == name
                open_ = level >= lv
                w = S(104)
                self.round_rect(x, cy - S(17), x + w, cy + S(17), S(9), fill=PAPER if open_ else "#ece6d6",
                                outline=ACCENT if mine else (INK_DIM if open_ else PAPER_LINE), width=max(2, S(3)) if mine else 1)
                sw = self.swatch(kind, row)
                cv.create_oval(x + S(10), cy - S(9), x + S(28), cy + S(9), fill=sw if open_ else "#d8cfbb", outline=INK_DIM if open_ else PAPER_LINE)
                cv.create_text(x + S(36), cy, anchor="w", text=self.t(zh, en) if open_ else "Lv.%d" % lv,
                               font=self.font(14, mine), fill=INK if open_ else INK_DIM)
                if mine:
                    cv.create_text(x + w - S(12), cy, text="✓", font=("Segoe UI Symbol", -S(14), "bold"), fill=ACCENT)
                if open_ and not mine:
                    self.hit.append((x, cy - S(17), x + w, cy + S(17), ("look", (kind, name))))
                x += w + S(10)
            ry += step

    @staticmethod
    def argb(v):
        return "#%06x" % (v & 0xFFFFFF)

    def swatch(self, kind, row):
        if kind == "chalk":
            return self.argb(row[2])
        if kind == "frame":
            return self.argb(P.SignBoard.FRAMES[row[0]][0])
        return self.argb(P.SignBoard.SLATE if row[0] == "flag" else P.SignBoard.FRAMES["wood"][0])

    def draw_sign(self, cx, cy, look, px):
        """A sign as the pets hold it up ("做完了！"), in a look: drawn here with the canvas, close to the real one."""
        cv, S = self.cv, self.S
        SB = P.SignBoard
        chalk = next((self.argb(c) for n, _, c, _ in P.SIGN_CHALKS if n == look.get("chalk")), "#f6f4ec")
        wood, edge, nail, deco = SB.FRAMES.get(look.get("frame"), SB.FRAMES["wood"])
        wood, edge = self.argb(wood), self.argb(edge)
        slate = self.argb(SB.SLATE)
        flag = look.get("board") == "flag"
        text = self.t("做完了！", "Done!")
        tid = cv.create_text(0, 0, text=text, anchor="w", font=("Microsoft YaHei UI", -px, "bold"), fill=chalk)
        tw = cv.bbox(tid)[2] - cv.bbox(tid)[0]
        frame, padx, pady = max(3, 0.3 * px), 0.5 * px, 0.26 * px
        isz, igap = 1.05 * px, 0.38 * px
        bh = 2 * frame + 2 * pady + 1.25 * px
        notch = 0.32 * bh if flag else 0.0
        w = 2 * frame + 2 * padx + isz + igap + tw + 2 * notch
        x0, y0, x1, y1 = cx - w / 2.0, cy - bh / 2.0, cx + w / 2.0, cy + bh / 2.0
        shade = max(2, int(0.12 * px))
        if flag:
            def banner(a0, b0, a1, b1, inset):
                mid = (b0 + b1) / 2.0
                k = notch * inset / max(1.0, (b1 - b0) / 2.0 + inset)
                return (a0 + k, b0, a1 - k, b0, a1 - notch, mid, a1 - k, b1, a0 + k, b1, a0 + notch, mid)
            cv.create_polygon(banner(x0 + 1, y0 + shade, x1 - 1, y1 + shade, 0), fill="#b9ad93", outline="")
            cv.create_polygon(banner(x0, y0, x1, y1, 0), fill=wood, outline=edge, width=max(1, int(px / 14)))
            t = frame * 0.62
            cv.create_polygon(banner(x0, y0 + t, x1, y1 - t, t), fill=slate, outline="")
        else:
            r = 0.45 * px
            self.round_rect(x0 + 1, y0 + shade, x1 - 1, y1 + shade, r, fill="#b9ad93", outline="")
            self.round_rect(x0, y0, x1, y1, r, fill=wood, outline=edge, width=max(1, int(px / 14)))
            self.round_rect(x0 + frame, y0 + frame, x1 - frame, y1 - frame, r * 0.4, fill=slate, outline="")
        f2 = frame * (0.31 if flag else 0.5)
        if nail is not None and not flag:
            nr = max(1.0, 0.09 * px)
            for nx in (x0 + frame * 0.55, x1 - frame * 0.55):
                cv.create_oval(nx - nr, y0 + frame * 0.55 - nr, nx + nr, y0 + frame * 0.55 + nr, fill=self.argb(nail), outline="")
        elif deco == "dots":
            dr = max(1.0, 0.12 * px)
            xa, xb = x0 + notch + frame * 0.9, x1 - notch - frame * 0.9
            n = max(2, int((xb - xa) / (0.62 * px)) + 1)
            for row, yy in enumerate((y0 + f2, y1 - f2)):
                for k in range(n):
                    xx = xa + (xb - xa) * k / float(n - 1)
                    cv.create_oval(xx - dr, yy - dr, xx + dr, yy + dr, fill=self.argb(SB.DOTS[(k + 2 * row) % len(SB.DOTS)]), outline="")
        elif deco == "stars":
            spots = ((x0 + notch + f2 * 1.4, y0 + f2), ((x0 + x1) / 2.0, y0 + f2), (x1 - notch - f2 * 1.4, y0 + f2),
                     (x0 + notch + f2 * 1.4, y1 - f2), (x1 - notch - f2 * 1.4, y1 - f2))
            for i, (sx, sy) in enumerate(spots):
                rr = max(1.5, (0.3 if i == 1 else 0.24) * px)
                pts = []
                for j in range(8):
                    a = math.pi / 4.0 * j
                    k = rr if j % 2 == 0 else 0.3 * rr
                    pts += [sx + k * math.sin(a), sy - k * math.cos(a)]
                cv.create_polygon(pts, fill="#ffd86a", outline="")
        ix = x0 + frame + padx + notch
        cv.create_text(ix + isz / 2.0, cy, text="\ue73e", font=(ICON_FONT, -int(isz)), fill="#96e196")
        cv.coords(tid, ix + isz + igap, cy)
        cv.tag_raise(tid)

    def draw_days(self, x0, y0, x1, y1):
        """The last seven days: how long they worked with you each day (a bar), how many turns (over it)."""
        cv, S = self.cv, self.S
        if y1 - y0 < S(120):
            return
        daily = self.data.get("daily") or {}
        days = [time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * i)) for i in range(6, -1, -1)]
        vals = []
        for day in days:
            v = daily.get(day)
            ok = isinstance(v, list) and len(v) >= 2 and all(type(x) in (int, float) for x in v[:2])
            vals.append((v[0], v[1] / 60.0) if ok else (0, 0.0))
        bottom = y1 - S(24)
        top = max(y0 + S(34), bottom - S(230))
        cv.create_text((x0 + x1) // 2, top - S(30), text=self.t("最近 7 天一起干活（分钟）", "The last 7 days at work (minutes)"), font=self.font(15, True), fill=INK)   # right over its bars
        top_v = max([m for _, m in vals] + [1.0])
        n = len(vals)
        slot = (x1 - x0) / float(n)
        bw = max(S(8), int(slot * 0.5))
        cv.create_line(x0, bottom, x1, bottom, fill=PAPER_LINE, width=max(1, S(2)))
        for i, ((turns, mins), day) in enumerate(zip(vals, days)):
            cx = int(x0 + slot * (i + 0.5))
            h = int((bottom - top - S(18)) * mins / top_v)
            today = i == n - 1
            if h > 0:
                self.round_rect(cx - bw // 2, bottom - h, cx + bw // 2, bottom, S(4), fill=ACCENT if today else "#e7a98c", outline="")
            else:                              # a day without work: its place is kept (a low pale stub)
                cv.create_rectangle(cx - bw // 2, bottom - S(4), cx + bw // 2, bottom, fill=PAPER_LINE, outline="")
            if mins >= 0.5:
                cv.create_text(cx, bottom - h - S(9), text="%d" % round(mins), font=self.font(12), fill=INK)
            cv.create_text(cx, bottom + S(12), text=self.t("今天", "today") if today else day[5:].replace("-", "/"), font=self.font(12),
                           fill=INK if today else INK_DIM)

    # ------------------------------------------------------------------ the picked one plays
    def start_anim(self):
        """The picked action plays in its snapshot; the picked treasure turns in its slot."""
        if self.revealing is not None:
            return
        c = self.picked_cell() if self.page in ("acts", "items") else None
        if c is None or not c["lit"] or c.get("new") or "at" not in c:
            self.anim = None
            return
        if c["kind"] == "act":
            info = self.fr.info(c["clip"])
            if not info:
                return
            fps = float(info.get("fps") or self.fr.man.get("fps") or 20)
            step = max(1, int(round(fps * ANIM_MS / 1000.0)))
            count = self.fr.count(c["clip"])
        else:
            fps = float(self.items_man.get("fps") or 12)
            step = 1
            count = int(self.items_man.get("frames") or 1)
        if count <= 1:
            return
        self.anim = {"cell": c, "ks": list(range(0, count, step)), "i": 0, "imgs": {}, "item": None,
                     "ms": max(40, int(1000.0 * step / fps))}
        self.root.after(self.anim["ms"], self.anim_tick, self.anim)

    def anim_tick(self, a):
        if self.anim is not a:
            return
        if self.root.state() == "iconic":      # minimized: nothing to see
            self.root.after(500, self.anim_tick, a)
            return
        k = a["ks"][a["i"] % len(a["ks"])]
        img = a["imgs"].get(k)
        if img is None:
            img = self.picture(a["cell"], "lit", k)
            a["imgs"][k] = img
        if img is not None:
            x, y = a["cell"]["at"]
            if a["item"] is None:
                self.cv.delete("pic:" + a["cell"]["id"])
                a["item"] = self.cv.create_image(x, y, image=img, tags="pic")
                self.cv.tag_raise("over")
            else:
                self.cv.itemconfigure(a["item"], image=img)
        a["i"] += 1
        self.root.after(a["ms"], self.anim_tick, a)

    # ------------------------------------------------------------------ a sealed find is opened
    def reveal(self, c):
        """The outline fills in, a few sparks fly; from now on it is looked at (album.json)."""
        self.mark_seen([c["id"]])
        x, y = c.get("at", (0, 0))
        steps = []
        try:
            sa = self.picture_data(c, "sealed", *self.reveal_size(c))
            c["new"] = False
            sb = self.picture_data(c, "lit", *self.reveal_size(c))
            if sa and sb and len(sa) == len(sb):
                for i in range(1, REVEAL_STEPS + 1):
                    steps.append(tk.PhotoImage(data=blend(sa, sb, i / float(REVEAL_STEPS)), format="ppm"))
        except Exception:
            self.on_error(*sys.exc_info())
        c["new"] = False
        self.revealing = {"cell": c, "steps": steps, "i": 0, "x": x, "y": y, "t": 0}
        self.show(self.page)
        self.root.after(1, self.reveal_tick, self.revealing)

    def reveal_size(self, c):
        if c["kind"] == "item":
            return self.item_px(), self.item_px()
        return self.box_px("combos" if c["kind"] == "combo" else "acts")

    def reveal_tick(self, r):
        if self.revealing is not r:
            return
        cv, S = self.cv, self.S
        c = r["cell"]
        if r["i"] < len(r["steps"]):
            cv.delete("pic:" + c["id"])
            cv.create_image(r["x"], r["y"], image=r["steps"][r["i"]], tags=("pic", "pic:" + c["id"]))
            cv.tag_raise("over")
        cv.delete("spark")
        t = r["i"] / float(REVEAL_STEPS + 3)
        if t < 1.0:
            for j in range(8):
                ang = j * math.pi / 4 + 0.3
                d = S(30) + S(46) * t
                sx, sy = r["x"] + d * math.cos(ang), r["y"] + d * math.sin(ang) * 0.8
                s = S(6) * (1.0 - t) + 1
                cv.create_polygon(sx, sy - s, sx + s * 0.3, sy - s * 0.3, sx + s, sy, sx + s * 0.3, sy + s * 0.3, sx, sy + s,
                                  sx - s * 0.3, sy + s * 0.3, sx - s, sy, sx - s * 0.3, sy - s * 0.3,
                                  fill=GOLD if j % 2 else MINT, outline="", tags=("spark", "over"))
            r["i"] += 1
            self.root.after(REVEAL_MS, self.reveal_tick, r)
        else:
            self.revealing = None
            self.start_anim()

    # ------------------------------------------------------------------ the mouse
    def at(self, e):
        for x0, y0, x1, y1, what in reversed(self.hit):
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return what
        return None

    def hover(self, e):
        self.cv.configure(cursor="hand2" if self.at(e) else "")

    def click(self, e):
        what = self.at(e)
        if what is None:
            return
        kind, arg = what
        if kind == "page":
            self.show(arg)
        elif kind == "cell":
            self.sel[self.page] = arg["key"]
            if arg.get("new"):
                self.reveal(arg)
            else:
                self.show(self.page)
        elif kind == "play":
            self.play(arg)
        elif kind == "nudge":
            self.nudged.add(arg)
            self.show(self.page)
        elif kind == "gift":
            self.sel["gifts"] = arg
            self.show(self.page)
        elif kind == "look":
            self.set_look(*arg)

    def set_look(self, kind, name):
        """A look of the signs picked: the pets take it (they hold one up to show it) and keep it in state.json."""
        self.look[kind] = name
        self.play({"token": "sign:%s=%s" % (kind, name)})
        self.show(self.page)

    def play(self, c):
        """The same word `clawd do` writes: the pets take it as what you asked for."""
        try:
            with open(self.event_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(c["token"] + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ tools/album_test.py
    def run_selftest(self):
        """Every page, every cell clicked, a reveal, a resize, the live snapshot; then the numbers into a file."""
        out = {"steps": []}
        t0 = time.perf_counter()

        def flush():
            while self.todo:
                self.work()
            self.root.update()

        def step(name):
            out["steps"].append(name)

        try:
            out["gift_news_first"] = self.gift_news()       # as it opens: before a card is shown
            flush()
            out["first_page_s"] = round(time.perf_counter() - t0, 2)
            out["dressed"] = bool(getattr(self, "dressed", False))
            out["icon"] = bool(getattr(self, "icons", None))
            t1 = time.perf_counter()
            pictures = {}
            for key, _, _ in PAGES:
                self.show(key)
                flush()
                step("page " + key)
                if key == "family":
                    pictures[key] = sum(1 for k, v in self.images.items() if k[0] == "family" and v is not None)
                    continue
                if key == "gifts":             # every badge on the road clicked once (where the badge is: a level of
                    badges = [h[4][1] for h in self.hit if h[4][0] == "gift"]          # two gifts takes turns), then
                    first_pick, picked = self.sel.get("gifts"), set()                 # a look of the signs
                    for i in range(len(badges)):
                        what = [h[4] for h in self.hit if h[4][0] == "gift"][i]
                        self.click_what(what)
                        flush()
                        picked.add(self.sel.get("gifts"))
                    looks = [h[4][1] for h in self.hit if h[4][0] == "look"]
                    out["gifts"] = {"badges": len(badges), "looks_open": len(looks), "picked": self.sel.get("gifts"),
                                    "first_pick": first_pick, "all_picked": len(picked), "news_left": len(self.gift_news()),
                                    "marker": any(k[1] == "marker" and v is not None for k, v in self.images.items())}
                    if looks:
                        self.click_what(("look", looks[0]))
                        flush()
                        try:
                            with open(self.event_path, "r", encoding="utf-8") as f:
                                out["gifts"]["look_token"] = f.read().splitlines()[-1:]
                        except OSError:
                            out["gifts"]["look_token"] = []
                    continue
                cells = [c for _, _, cs in self.cells[key] for c in cs]
                pictures[key] = [c["id"] for c in cells if self.images.get(self.image_key(c)) is None]
                for c in cells:
                    self.click_cell(c)
                    flush()
            out["all_pages_s"] = round(time.perf_counter() - t1, 2)
            out["missing_pictures"] = pictures
            out["news_after"] = dict((k, len(self.news(k))) for k in COLLECTED)
            out["seen_file"] = read_json(self.seen_path).get("seen", {})
            # the picked action plays
            self.show("acts")
            act = next(c for _, _, cs in self.cells["acts"] for c in cs if c["lit"])
            self.click_cell(act)
            flush()
            k0 = self.anim["i"] if self.anim else -1
            t2 = time.perf_counter()
            while time.perf_counter() - t2 < 1.5:
                self.root.update()
                time.sleep(0.01)
            out["anim_frames"] = (self.anim["i"] - k0) if self.anim else -1
            # play it: the word goes to the event file
            c = self.picked_cell()
            self.play(c)
            try:
                with open(self.event_path, "r", encoding="utf-8") as f:
                    out["event_tail"] = f.read().splitlines()[-1:]
            except OSError:
                out["event_tail"] = []
            # bigger, then smaller
            sizes = []
            for w, h in ((int(BASE_W * 1.5), int(BASE_H * 1.4)), (int(BASE_W * 0.7), int(BASE_H * 0.7))):
                self.root.geometry("%dx%d" % (w, h))
                self.root.update()
                self.relayout()
                flush()
                sizes.append((self.W, self.H, round(self.f, 3), len(self.hit)))
            out["sizes"] = sizes
            out["work_set_mb"], out["private_mb"] = memory()
        except Exception:
            self.on_error(*sys.exc_info())
        out["errors"] = self.errors
        write_json(self.selftest, out)
        self.root.destroy()

    def click_what(self, what):
        class E(object):
            pass
        e = E()
        x0, y0, x1, y1, _ = next(h for h in self.hit if h[4] == what)
        e.x, e.y = (x0 + x1) // 2, (y0 + y1) // 2
        self.click(e)

    def click_cell(self, c):
        class E(object):
            pass
        e = E()
        x0, y0, x1, y1, _ = next(h for h in self.hit if h[4][0] == "cell" and h[4][1]["id"] == c["id"])
        e.x, e.y = (x0 + x1) // 2, (y0 + y1) // 2
        self.click(e)
        while self.revealing is not None:
            self.root.update()
            time.sleep(0.01)


def memory():
    """-> (working set, private bytes) of this process in MB."""
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                           "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                           "PrivateUsage")]
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(k32.GetCurrentProcess()), ctypes.byref(pmc), pmc.cb)
    return round(pmc.WorkingSetSize / 1048576.0, 1), round(pmc.PrivateUsage / 1048576.0, 1)


def main(argv):
    home, frames_dir, hi_dir, page, selftest = data_home(), None, None, 0, None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--home" and i + 1 < len(argv):
            home = os.path.abspath(argv[i + 1]); i += 1
        elif a == "--frames-dir" and i + 1 < len(argv):
            frames_dir = os.path.abspath(argv[i + 1]); i += 1
        elif a == "--hi-dir" and i + 1 < len(argv):
            hi_dir = os.path.abspath(argv[i + 1]); i += 1
        elif a == "--page" and i + 1 < len(argv):
            page = max(0, min(len(PAGES) - 1, int(argv[i + 1]) - 1)); i += 1
        elif a == "--selftest" and i + 1 < len(argv):
            selftest = os.path.abspath(argv[i + 1]); i += 1
        i += 1
    frames_dir = frames_dir or os.path.join(HERE, "frames")
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    name = "ClawdAlbum_%08x" % (zlib.crc32(os.path.normcase(home).encode("utf-8")) & 0xFFFFFFFF)
    mutex = k32.CreateMutexW(None, False, name)
    if k32.GetLastError() == 183:              # one album a home: the one that is open comes to the front
        for title in ("Clawd 图鉴", "Clawd Album"):
            hwnd = u32.FindWindowW(None, title)
            if hwnd:
                u32.ShowWindow(hwnd, 9)
                u32.SetForegroundWindow(hwnd)
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    album = Album(home, frames_dir, hi_dir, page, selftest)
    album.root.mainloop()
    del mutex
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
