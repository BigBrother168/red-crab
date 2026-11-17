# Shared constants/helpers. Logical canvas is 1920x1080; everything is drawn at output scale S = OUT_W/1920.
import os, math, hashlib, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
LW, LH = 1920, 1080
FONT_DIR = r'C:\Windows\Fonts'
FONTS = {
    'kai': os.path.join(FONT_DIR, 'simkai.ttf'),
    'stkai': os.path.join(FONT_DIR, 'STKAITI.TTF'),
    'yahei': os.path.join(FONT_DIR, 'msyh.ttc'),
    'yaheib': os.path.join(FONT_DIR, 'msyhbd.ttc'),
    'hei': os.path.join(FONT_DIR, 'simhei.ttf'),
}
# chalk colours (on dark slate)
CH = {
    'w': (240, 238, 228), 'y': (255, 214, 102), 'p': (255, 158, 170), 'b': (140, 200, 255),
    'g': (150, 226, 150), 'o': (255, 170, 110), 'r': (255, 110, 110), 'd': (175, 185, 180),
}
CLAWD = dict(base=(217, 119, 87), hi=(234, 154, 123), shade=(196, 98, 63), eye=(26, 20, 18))
FLOOR_Y = 955          # logical y of Clawd feet (board content stays above y~660, Clawd top ~667)
BOARD = dict(x0=60, y0=22, x1=1860, y1=712, frame=18)   # outer frame; inner slate = inset by frame


class Scale:
    def __init__(self, out_w):
        self.W = out_w; self.H = int(round(out_w * 9 / 16)); self.s = out_w / LW

    def __call__(self, v):
        return int(round(v * self.s))

    def f(self, v):
        return v * self.s


_font_cache = {}


def font(name, size_px):
    key = (name, int(size_px))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONTS[name], max(6, int(size_px)))
    return _font_cache[key]


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, u):
    return a + (b - a) * u


def smooth(u):
    u = clamp(u, 0.0, 1.0); return u * u * (3 - 2 * u)


def ease_out(u):
    u = clamp(u, 0.0, 1.0); return 1 - (1 - u) ** 3


def ease_in(u):
    u = clamp(u, 0.0, 1.0); return u ** 3


def ease_out_back(u, k=1.70158):
    u = clamp(u, 0.0, 1.0); u -= 1; return 1 + (k + 1) * u ** 3 + k * u ** 2


def bump(u, a, b):
    """0 outside [a,b], smooth 0->1->0 inside"""
    if u <= a or u >= b: return 0.0
    v = (u - a) / (b - a); return math.sin(math.pi * v)


def env_in_out(u, D, tin=0.25, tout=0.25):
    """1 inside the action, smooth ramps at both ends"""
    if D <= 0: return 0.0
    a = smooth(u / tin) if tin > 0 else 1.0
    b = smooth((D - u) / tout) if tout > 0 else 1.0
    return min(a, b)


def hrand(*keys):
    """deterministic pseudo random in [0,1) from keys"""
    h = hashlib.md5(('|'.join(map(str, keys))).encode()).digest()
    return int.from_bytes(h[:4], 'little') / 2 ** 32


def rrect_poly(cx, cy, w, h, r, ang=0.0, n=6):
    """rounded rectangle centred at (cx,cy), rotated by ang degrees (counter-clockwise on screen), as polygon pts"""
    r = min(r, w / 2, h / 2); pts = []
    for (qx, qy, a0) in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n); pts.append((qx + r * math.cos(a), qy + r * math.sin(a)))
    ca, sa = math.cos(math.radians(-ang)), math.sin(math.radians(-ang))
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def rot_pts(pts, cx, cy, ang):
    ca, sa = math.cos(math.radians(-ang)), math.sin(math.radians(-ang))
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def star_poly(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for k in range(2 * n):
        r = r_out if k % 2 == 0 else r_in; a = math.radians(rot + 180 * k / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def load_json(p):
    with open(p, encoding='utf-8') as f: return json.load(f)


def paste_rgba(dst, src, x, y, opacity=1.0):
    """alpha-composite src (RGBA) onto dst (RGBA) at integer pixel position, clipping safely"""
    x, y = int(round(x)), int(round(y))
    if opacity < 1.0:
        if opacity <= 0.003: return
        a = src.getchannel('A').point(lambda v: int(v * opacity)); src = src.copy(); src.putalpha(a)
    W, H = dst.size; w, h = src.size
    sx0, sy0 = max(0, -x), max(0, -y); dx0, dy0 = max(0, x), max(0, y)
    w2, h2 = min(w - sx0, W - dx0), min(h - sy0, H - dy0)
    if w2 <= 0 or h2 <= 0: return
    if sx0 or sy0 or w2 != w or h2 != h: src = src.crop((sx0, sy0, sx0 + w2, sy0 + h2))
    dst.alpha_composite(src, (dx0, dy0))
