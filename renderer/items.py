# The treasures (宝贝): small flat 2D icons, drawn by code like the rest.  Each is painted in a box of 100 x 100
# units (x right, y down, the centre at 0,0), at any pixel size, with a thin dark rim so that a pale one shows on a
# light desktop as well.  draw_item(name, px) -> RGBA image.  ITEMS: name -> (中文, English, rarity).
import math
from PIL import Image, ImageChops, ImageDraw, ImageFilter

RIM = (66, 50, 58)          # the rim's colour
RIM_W = 3.2                 # ... and width, in units
SS = 4                      # painted this many times bigger, then scaled down
WHITE = (255, 255, 255)


class Pen(object):
    """Paints in units; rot turns the whole icon (degrees, clockwise on screen)."""

    def __init__(self, img, rot=0.0, dx=0.0, dy=0.0, scale=1.0, sx=1.0, sy=1.0):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.scale = scale
        self.k = img.size[0] / 100.0 * scale
        self.c = img.size[0] / 2.0
        a = math.radians(rot)
        self.ca, self.sa = math.cos(a), math.sin(a)
        self.dx, self.dy = dx, dy
        self.sx, self.sy = sx, sy          # stretch along the icon's own axes
        self.lx = self.ly = 0.0            # a shift along them (a part that moves by itself)
        self.late = []                     # painted after the rim, with no rim of their own: f(pen)

    def P(self, x, y):
        x, y = (x + self.lx) * self.sx, (y + self.ly) * self.sy
        return (self.c + (x * self.ca - y * self.sa + self.dx) * self.k, self.c + (x * self.sa + y * self.ca + self.dy) * self.k)

    def upright(self):
        """A pen on the same picture that does not turn, stretch or move with the icon (water, lines on the ground)."""
        return Pen(self.img, scale=self.scale)

    def poly(self, pts, fill):
        self.d.polygon([self.P(x, y) for x, y in pts], fill=fill + (255,) if len(fill) == 3 else fill)

    def ell(self, cx, cy, rx, ry, fill, a=0.0, n=48):
        q = math.radians(a)
        ca, sa = math.cos(q), math.sin(q)
        pts = []
        for i in range(n):
            t = 2 * math.pi * i / n
            x, y = rx * math.cos(t), ry * math.sin(t)
            pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
        self.poly(pts, fill)

    def circ(self, cx, cy, r, fill):
        self.ell(cx, cy, r, r, fill)

    def rr(self, cx, cy, w, h, r, fill, a=0.0, n=6):
        r = min(r, w / 2.0, h / 2.0)
        pts = []
        for qx, qy, a0 in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
            for i in range(n + 1):
                t = math.radians(a0 + 90.0 * i / n)
                pts.append((qx + r * math.cos(t), qy + r * math.sin(t)))
        q = math.radians(a)
        ca, sa = math.cos(q), math.sin(q)
        self.poly([(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts], fill)

    def line(self, pts, w, fill):
        """A stroke with round ends and joints."""
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            if L < 1e-6:
                continue
            nx, ny = -(y1 - y0) / L * w / 2.0, (x1 - x0) / L * w / 2.0
            self.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill)
        for x, y in pts:
            self.circ(x, y, w / 2.0, fill)

    def arc(self, cx, cy, r, a0, a1, w, fill, n=24):
        self.line([(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
                   for i in range(n + 1)], w, fill)

    def star(self, cx, cy, R, r, fill, n=4, rot=-90.0):
        pts = []
        for i in range(2 * n):
            q = math.radians(rot + 180.0 * i / n)
            rad = R if i % 2 == 0 else r
            pts.append((cx + rad * math.cos(q), cy + rad * math.sin(q)))
        self.poly(pts, fill)

    def erase(self, cx, cy, r):
        self.ell(cx, cy, r, r, (0, 0, 0, 0))


def _arc_pts(cx, cy, r, a0, a1, n=10):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


# ---------------------------------------------------------------- common
def _semicolon(p, col, hi, sh, t=0.0):
    hop = -7.0 * abs(math.sin(2 * math.pi * t)) if t < 0.5 else 0.0      # the dot hops twice, then rests
    p.circ(0, 15, 14.5, col)
    p.circ(0, -24 + hop, 14.5, col)
    p.poly([(14.2, 17), (12, 30), (3, 42), (-10, 49), (-13, 45.5), (-4, 37), (-0.5, 27), (-13, 20)], col)
    p.poly([(14.2, 17), (12, 30), (3, 42), (-10, 49), (-6, 43), (3, 35), (7, 26), (8, 16)], sh)
    for cy in (-24 + hop, 15):
        p.ell(-5.5, cy - 5.5, 4.6, 3.6, hi, -35)


def semicolon(p, t=0.0):
    _semicolon(p, (88, 116, 204), (176, 196, 246), (64, 88, 170), t)


def paperclip(p, t=0.0):
    """Springy: pulled long and let go, it wobbles to rest (ITEM_MOTION)."""
    path = ([(15, -22), (15, 24)] + _arc_pts(0, 24, 15, 0, 180) + [(-15, -30)] + _arc_pts(-3.5, -30, 11.5, 180, 360)
            + [(8, 18)] + _arc_pts(0.5, 18, 7.5, 0, 180) + [(-7, -16)])
    p.line(path, 7.6, (132, 150, 184))
    p.line([(x - 1.3, y - 1.3) for x, y in path], 2.6, (224, 232, 246))


def screw(p, t=0.0):
    p.poly([(-9.5, -20), (9.5, -20), (9.5, 22), (0, 44), (-9.5, 22)], (150, 158, 176))
    p.poly([(-9.5, -20), (-3, -20), (-3, 30), (-9.5, 22)], (182, 190, 206))
    for y in (-22 + 10 * t + 10 * i for i in range(6)):          # the thread runs
        if y < -15 or y > 31: continue
        w = 12.5 if y < 20 else 8.5
        p.line([(-w, y + 4), (w, y - 4)], 4.2, (104, 112, 134))
    p.rr(0, -29, 50, 19, 8, (176, 184, 200))
    p.rr(0, -33.5, 40, 6, 3, (222, 228, 238))
    p.rr(0, -24.5, 44, 5, 2.5, (136, 144, 164))
    p.rr(0, -37, 16, 5.5, 2, (98, 106, 128))


def sticky_note(p, t=0.0):
    """Three lines are written on it one after another; the corner lifts and settles."""
    c = 24 + 7 * math.sin(2 * math.pi * t)
    p.rr(0, 0, 78, 78, 5, (255, 224, 104))
    p.rr(0, -31, 78, 16, 5, (246, 204, 78))
    p.poly([(39, 39 - c), (39, 39), (39 - c, 39)], (0, 0, 0, 0))
    p.poly([(39, 39 - c), (39 - c, 39), (41 - c, 41 - c)], (255, 240, 164))
    p.poly([(39, 39 - c), (39 - c, 39), (39 - 0.68 * c, 39 - 0.68 * c)], (232, 190, 70))
    for i, (y, x1) in enumerate(((-9, 20), (5, 9), (19, -4))):
        f = min(1.0, max(0.0, t * 4.2 - i))
        if f > 0.02:
            p.line([(-25, y), (-25 + (x1 + 25) * f, y)], 5.2, (176, 142, 54))


def pencil(p, t=0.0):
    """It writes: a wavy line grows under its tip as it moves along, then a new one."""
    f = min(1.0, t / 0.72)
    x0, x1 = -20.0, 10.0
    xs = [x0 + (x1 - x0) * f * i / 16.0 for i in range(17)]
    if f > 0.03:
        p.line([(x, 44 + 2.6 * math.sin(x / 3.2)) for x in xs], 3.0, (96, 98, 120))
    p.lx = x0 + (x1 - x0) * f
    p.ly = -5 + 1.5 * math.sin(xs[-1] / 3.2)
    p.rr(0, -38, 22, 15, 5.5, (242, 138, 152))
    p.rr(-5, -39, 5, 9, 2.5, (250, 178, 188))
    p.rr(0, -27, 24, 11, 2, (190, 196, 210))
    p.line([(-12, -27), (12, -27)], 2.2, (140, 148, 168))
    p.rr(0, -3, 22, 40, 1.5, (250, 196, 62))
    p.rr(-7, -3, 6, 40, 1, (255, 224, 122))
    p.rr(7.2, -3, 6, 40, 1, (224, 164, 40))
    p.poly([(-11, 16.5), (11, 16.5), (3.6, 37), (-3.6, 37)], (240, 208, 164))
    p.poly([(-11, 16.5), (-4, 16.5), (-1, 37), (-3.6, 37)], (250, 226, 190))
    p.poly([(-3.8, 36), (3.8, 36), (0, 47)], (66, 66, 82))
    p.lx = p.ly = 0.0


def paper_ball(p, t=0.0):
    """Tossed: it rolls once over in two bounces, squashed a little each time it lands (ITEM_MOTION)."""
    rad = (38, 36, 39, 33, 37, 40, 35, 38, 34, 39, 36, 40, 34, 37, 39, 35)
    pts = [(rad[i] * math.cos(math.radians(22.5 * i)), rad[i] * math.sin(math.radians(22.5 * i))) for i in range(16)]
    p.poly(pts, (248, 246, 240))
    p.poly(pts[0:6] + [(-6, 20), (14, 10), (24, -4)], (226, 224, 218))           # the shaded side, below and right
    p.poly([pts[9], pts[10], pts[11], (-8, -16), (-22, -8)], (236, 234, 228))
    for seg in (((-26, -6), (-12, -14), (2, -8), (10, 4)), ((2, -8), (8, -26)), ((10, 4), (-6, 20), (-20, 12)), ((10, 4), (26, 2)),
                ((-6, 20), (-2, 32)), ((-12, -14), (-18, -28))):
        p.line(list(seg), 2.4, (188, 190, 204))


def leaf(p, t=0.0):
    """It comes down as leaves do: swinging from side to side (ITEM_MOTION)."""
    n = 20
    R = [(26 * math.sin(math.pi * i / n) ** 0.75, -44 + 84.0 * i / n) for i in range(n + 1)]
    L = [(-x, y) for x, y in reversed(R)]
    p.poly(R + L, (104, 186, 100))
    p.poly(L + [(0, 40), (0, -44)], (142, 212, 126))
    p.line([(0, -40), (0, 48)], 4.4, (60, 140, 82))
    for y in (-18, -2, 14):
        p.line([(0, y), (15, y - 11)], 2.8, (60, 140, 82))
        p.line([(0, y + 4), (-15, y - 7)], 2.8, (80, 160, 96))


def pebble(p, t=0.0):
    """It skips like a flat stone on water: two hops, a ring spreading where it touched."""
    f = (t % 0.5) / 0.5
    w = p.upright()
    if f < 0.75:
        r = 16 + 30 * f
        w.line([(r * math.cos(2 * math.pi * i / 32), 38 + 0.26 * r * math.sin(2 * math.pi * i / 32)) for i in range(33)],
               3.4 * (1 - f) + 0.6, (126, 190, 236))
    p.ly = -15 * math.sin(math.pi * f)
    p.ell(0, 5, 40, 29, (120, 128, 148), -8)
    p.ell(-2, 1, 37, 25, (156, 164, 180), -8)
    p.ell(-13, -9, 13, 6, (204, 210, 224), -20)
    for x, y, r in ((12, 8, 3.4), (22, -2, 2.4), (-4, 16, 2.6), (2, -6, 2.0)):
        p.circ(x, y, r, (118, 126, 146))
    p.line([(-30, 12), (-14, 22), (10, 24)], 3.0, (190, 196, 210))
    p.ly = 0.0


# ---------------------------------------------------------------- uncommon
def braces(p, t=0.0):
    col, hi = (192, 112, 222), (226, 176, 244)
    for s in (-1, 1):
        pts = [(s * 8, -41), (s * 17, -38), (s * 20, -28), (s * 20, -12), (s * 31, 0), (s * 20, 12), (s * 20, 28), (s * 17, 38), (s * 8, 41)]
        pts = [(x + s * 6, y) for x, y in pts]
        p.line(pts, 9.4, col)
        p.line([(x - 1.4, y - 1.4) for x, y in pts[:4]], 3.0, hi)
    for i, x in enumerate((-8, 0, 8)):                       # the dots light up one after another
        on = int(t * 4) > i
        p.circ(x, 0, 3.6 if on else 2.6, (255, 204, 92) if on else (150, 130, 170))


def gear(p, t=0.0):
    """It turns, one tooth at a tick (ITEM_MOTION)."""
    pts = []
    for i in range(8):
        c = 45.0 * i
        for da, R in ((-15, 31), (-9, 43), (9, 43), (15, 31)):
            q = math.radians(c + da)
            pts.append((R * math.cos(q), R * math.sin(q)))
    p.poly(pts, (104, 138, 192))
    p.circ(0, 0, 31.5, (104, 138, 192))
    p.circ(0, 0, 25, (146, 178, 224))
    p.arc(0, 0, 20, 200, 290, 4.0, (198, 218, 246))
    p.circ(0, 0, 10.5, (58, 70, 100))
    p.circ(0, 0, 6, (0, 0, 0, 0))


def keycap(p, t=0.0):
    d = 6.0 * math.sin(math.pi * min(1.0, t / 0.3)) if t < 0.3 else 0.0           # pressed once a loop
    p.rr(0, 6, 82, 76, 13, (58, 66, 98))
    p.rr(0, -2 + d, 66, 60, 10, (104, 118, 164) if d < 3 else (122, 138, 190))
    p.rr(0, -23 + d, 52, 7, 3.5, (146, 160, 204))
    p.line([(17, -13 + d), (17, 5 + d), (-12, 5 + d)], 6.4, (244, 247, 253))
    p.poly([(-24, 5 + d), (-9, -6.5 + d), (-9, 16.5 + d)], (244, 247, 253))


def floppy(p, t=0.0):
    p.poly([(-39, -34), (-34, -39), (25, -39), (39, -25), (39, 34), (34, 39), (-34, 39), (-39, 34)], (62, 104, 200))
    p.poly([(-39, -34), (-34, -39), (-28, -39), (-28, 39), (-34, 39), (-39, 34)], (48, 84, 172))
    sl = 9.0 * math.sin(math.pi * min(1.0, t / 0.5)) ** 2 if t < 0.5 else 0.0       # the shutter slides open and shut
    p.rr(-1, -25, 42, 26, 2.5, (36, 40, 60))
    p.rr(-1 - sl, -25, 42 - 2 * sl, 26, 2.5, (206, 212, 224))
    p.rr(9 - sl, -25, 10, 18, 2, (62, 104, 200))
    p.rr(2, 17, 56, 36, 3, (248, 248, 242))
    p.rr(2, 3, 56, 7, 1.5, (236, 104, 104))
    for y in (14, 23):
        p.line([(-18, y), (22, y)], 3.2, (168, 176, 198))


def shell(p, t=0.0):
    """A pearl comes up out of it, shines, and goes back in."""
    cx, cy, A, lobe = 0, 30, 66.0, 22.0
    pts = [(-11, cy + 5), (-11, cy - 2)]
    for i in range(61):
        a = -A + 2 * A * i / 60
        R = 55 + 6.0 * abs(math.sin(math.pi * (a + A) / lobe))
        pts.append((cx + R * math.sin(math.radians(a)), cy - R * math.cos(math.radians(a))))
    pts += [(11, cy - 2), (11, cy + 5)]
    p.poly(pts, (252, 204, 188))
    p.poly([q for q in pts if q[0] <= 0] + [(0, cy)], (255, 226, 212))
    for j in range(1, 6):
        a = math.radians(-A + lobe * j)
        p.line([(cx, cy - 4), (cx + 54 * math.sin(a), cy - 54 * math.cos(a))], 3.2, (232, 150, 146))
    k = math.sin(math.pi * min(1.0, max(0.0, (t - 0.12) / 0.62))) ** 0.7
    if k > 0.03:
        y = 20 - 22 * k
        p.circ(0, y, 12 * k, (226, 222, 236))
        p.circ(-0.8, y - 0.8, 10.6 * k, (252, 250, 255))
        p.ell(-4 * k, y - 4 * k, 3.6 * k, 2.6 * k, WHITE, -30)
        if k > 0.8:
            p.star(11, y - 12, 9 * (k - 0.8) * 5, 2.4 * (k - 0.8) * 5, (255, 250, 210))
    p.rr(0, cy + 4, 30, 12, 5.5, (236, 164, 150))


# ---------------------------------------------------------------- rare
def rubber_duck(p, t=0.0):
    """Squeak, squeak: squeezed twice (ITEM_MOTION), little lines by its beak each time; it bobs between."""
    body, sh, hi = (255, 212, 64), (238, 180, 40), (255, 236, 140)
    p.poly([(-34, 4), (-47, -9), (-28, 0)], body)
    p.ell(-5, 17, 37, 25, body)
    p.circ(14, -17, 21, body)
    p.ell(-6, 26, 30, 13, sh)
    p.ell(-5, 17, 37, 21, body)
    p.ell(-9, 16, 18, 11, sh, 12)
    p.ell(-10, 14, 15, 8, body, 12)
    p.ell(8, -27, 9, 5, hi, -25)
    p.ell(38, -11, 12, 6.2, (246, 140, 50))
    p.ell(37, -8.5, 10, 3.6, (226, 112, 36))
    q = _squeak(t)
    if q > 0.45:
        p.line([(17, -21), (25, -21)], 3.4, (40, 32, 36))                  # the eye shut tight
        for a in (-38, -8, 22):
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            p.line([(38 + 12 * ca, -11 + 12 * sa), (38 + 17 * ca, -11 + 17 * sa)], 3.0, (246, 140, 50))
    else:
        p.circ(21, -21, 4.6, (40, 32, 36))
        p.circ(22.4, -22.6, 1.6, WHITE)
    p.circ(25, -9, 4.4, (255, 176, 120))


def gold_semicolon(p, t=0.0):
    _semicolon(p, (248, 194, 62), (255, 240, 170), (214, 148, 30), t)
    for i, (x, y, R) in enumerate(((-30, -34, 12.0), (31, -2, 9.0), (-27, 34, 7.0))):          # the sparkles take turns
        k = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(2 * math.pi * (t + i / 3.0)))
        p.star(x, y, R * k, R * k * 0.28, (255, 236, 150))


# ---------------------------------------------------------------- special (what the work of the turn was)
def bug(p, t=0.0, fly=False):
    """A ladybug, its legs and feelers going.  (Played with, flying: its shell open, the wings beating under it.)"""
    dark = (46, 40, 54)
    w = math.sin(4 * math.pi * t)                              # the legs and the feelers go
    for i, ((x0, y0), (x1, y1)) in enumerate((((24, -6), (41, -15)), ((28, 9), (45, 9)), ((24, 24), (39, 35)))):
        dy = 5.0 * w * (1 if i % 2 == 0 else -1)
        p.line([(x0, y0), (x1, y1 + dy)], 4.2, dark)
        p.line([(-x0, y0), (-x1, y1 - dy)], 4.2, dark)
    for s in (-1, 1):
        p.line([(s * 6, -36), (s * 12, -44 + 2 * w * s), (s * 19, -45 + 4 * w * s)], 3.2, dark)
    p.ell(0, -27, 19, 13, dark)
    if fly:
        b = math.sin(2 * math.pi * 10 * t)                     # the wings beat, fast
        for sd in (-1, 1):
            p.ell(sd * 30, 14, 15, 37, (214, 228, 240, 200), sd * (34 + 14 * b))
            p.ell(sd * 30, 14, 11, 32, (240, 248, 255, 170), sd * (34 + 14 * b))
        p.ell(0, 8, 21, 31, dark)
        for sd in (-1, 1):                                    # the two halves of the shell, up and out
            p.ell(sd * 21, 0, 15, 31, (228, 70, 62), sd * 26)
            p.ell(sd * 18, -12, 5, 10, (250, 140, 128), sd * 26)
            for x, y, r in ((24, -2, 5.6), (27, 17, 4.4)):
                p.circ(sd * x, y, r, dark)
    else:
        p.ell(0, 7, 31, 35, (228, 70, 62))
        p.ell(-12, -8, 8, 14, (250, 140, 128), 24)
        p.line([(0, -24), (0, 41)], 3.6, dark)
        for x, y, r in ((13, -6, 6.4), (16, 18, 5.4), (9, 32, 3.6)):
            p.circ(x, y, r, dark)
            p.circ(-x, y, r, dark)
    for s in (-1, 1):
        p.circ(s * 8, -31, 3.4, WHITE)


def bottle(p, t=0.0, cork=True, paper=True):
    """Adrift: it rocks on two little waves that run under it.  (Played with: uncorked, and empty while its message
    is out.)"""
    w = p.upright()
    for j, (y, ph) in enumerate(((38, 0.0), (45, 0.5))):
        w.line([(x, y + 2.6 * math.sin(x / 7.0 + 2 * math.pi * (2 * t + ph))) for x in range(-40 + 6 * j, 41 - 6 * j, 4)], 3.4,
               (120, 190, 236) if j == 0 else (156, 210, 244))
    glass, edge = (178, 226, 234), (120, 188, 204)
    if cork:
        p.rr(0, -45, 17, 11, 3.5, (198, 148, 98))
        p.rr(-3, -46, 5, 6, 2, (224, 182, 134))
    p.rr(0, -28, 21, 24, 4, glass)
    p.rr(0, 11, 46, 66, 15, glass)
    p.rr(0, -38.5, 27, 7.5, 3.5, edge)
    p.rr(0, 41, 40, 6, 3, edge)
    if paper:
        p.rr(2, 12, 21, 42, 6, (253, 247, 230))
        p.rr(7, 12, 6, 42, 3, (232, 222, 196))
        p.rr(2, 12, 23, 7, 1.5, (234, 96, 96))
    p.rr(-15, 9, 5.2, 44, 2.6, (236, 250, 253))
    p.rr(-6, -28, 3.6, 16, 1.8, (236, 250, 253))


def biscuit(p, t=0.0):
    """Somebody is eating it: a bite, another, another (crumbs fall), and then it is whole again."""
    p.rr(0, 0, 86, 60, 7, (206, 156, 88))
    for i in range(7):
        x = -36 + 12 * i
        p.circ(x, -30, 4.6, (206, 156, 88))
        p.circ(x, 30, 4.6, (206, 156, 88))
    for y in (-18, -6, 6, 18):
        p.circ(-43, y, 4.6, (206, 156, 88))
        p.circ(43, y, 4.6, (206, 156, 88))
    p.rr(0, 0, 76, 50, 5, (240, 202, 136))
    p.rr(-2, -18, 66, 7, 3.5, (250, 222, 166))
    for x in (-24, 0, 24):
        for y in (-7, 11):
            p.circ(x, y, 3.8, (188, 136, 74))
    n = int(t * 4)                                             # bites so far
    bites = (((42, -29, 14.5), (29, -35, 9.0)), ((46, -6, 13.0), (36, 2, 8.0)), ((40, 22, 14.0), (26, 30, 9.0)))
    for i in range(min(n, 3)):
        for x, y, r in bites[i]:
            p.erase(x, y, r)
    f = (t * 4) % 1.0
    if 1 <= n <= 3 and f < 0.7:
        x, y, _ = bites[n - 1][0]
        for j in range(3):
            p.circ(min(44.0, x - 8 + 5 * j), y + 4 + 24 * f * f + 4 * j, 2.6 * (1 - 0.6 * f), (206, 156, 88))


def hourglass(p, t=0.0, grains=False):
    """The sand runs out, then the glass is turned over.  (Played with: grains falling down the stream, so that the
    stream is seen to stop when time does.)"""
    wood, wood_hi = (166, 114, 74), (204, 156, 110)
    for s in (-1, 1):
        p.rr(s * 25.5, 0, 4.6, 74, 2.3, (136, 90, 56))
    p.poly([(-21, -35), (21, -35), (21, -22), (4.5, -2), (4.5, 2), (21, 22), (21, 35), (-21, 35), (-21, 22), (-4.5, 2), (-4.5, -2), (-21, -22)],
           (214, 238, 247))
    f = min(1.0, t / 0.72)                                # the sand runs out, then the glass is turned over (ITEM_MOTION)
    top = -19 + 14 * f; hw = 14.5 * (1 - f) + 3.4 * f
    p.poly([(-hw, top), (hw, top), (3.4, -3), (-3.4, -3)], (244, 200, 100))
    pk = 30 - 17 * f
    if f < 1.0 and not grains:
        p.line([(0, -3), (0, 30)], 2.6, (244, 200, 100))
    elif f < 1.0:
        p.line([(0, -3), (0, pk)], 1.6, (248, 220, 150))
        for k in range(3):
            y = -1 + (pk + 1) * ((k / 3.0 + 6.0 * t) % 1.0)
            p.circ(0.6 * (-1) ** k, y, 2.1, (226, 168, 64))
    p.poly([(-20.5, 34.5), (20.5, 34.5), (20.5, 34.5 - 5.5 * f), (0, pk), (-20.5, 34.5 - 5.5 * f)], (244, 200, 100))
    p.poly([(0, pk), (20.5, 34.5 - 5.5 * f), (20.5, 34.5), (4, 34.5)], (222, 170, 70))
    p.line([(-15, -30), (-15, -24)], 3.0, WHITE)
    p.line([(-15, 22), (-15, 28)], 3.0, WHITE)
    for s in (-1, 1):
        p.rr(0, s * 41, 60, 11, 3.5, wood)
        p.rr(0, s * 41 - 2.6, 52, 3.4, 1.7, wood_hi)


def plane_model(p, t=0.0, stand=True, plane=True, air='late'):
    """On its little stand it banks and swoops, as if it flew.  (Played with: the plane off its stand, and the
    stand alone, each where it is in the whole.)"""
    if stand:
        p.line([(-3, 20), (-3, 41)], 4.6, (166, 122, 84))
        p.rr(-3, 44, 38, 8, 4, (140, 98, 64))
        p.rr(-3, 42, 28, 2.6, 1.3, (186, 144, 100))
    if not plane: return
    a = math.radians(13 * math.sin(2 * math.pi * t)); ca, sa = math.cos(a), math.sin(a)
    oy = -3 * math.cos(4 * math.pi * t)
    R = lambda pts: [(-3 + (x + 3) * ca - (y - 18) * sa, 18 + oy + (x + 3) * sa + (y - 18) * ca) for x, y in pts]
    lines = [R([(x, -22 + 9 * i), (x + 9, -24.6 + 9 * i)]) for i, x in ((i, -30 - 16 * ((3 * t + i / 3.0) % 1.0)) for i in range(3))]
    if air == 'late':                                          # the air going by, light, with no dark rim: on a light
        p.late.append(lambda q: [q.line(ln, 2.8, (150, 192, 240)) for ln in lines])   # desktop a rim made them look solid
    elif air:
        for ln in lines:                                       # the air going by
            p.line(ln, 2.4, (190, 206, 232))
    p.poly(R([(-44, -6), (46, -32), (-10, 8)]), (246, 249, 253))
    p.poly(R([(-10, 8), (46, -32), (-4, 31)]), (204, 216, 236))
    p.poly(R([(-10, 8), (-4, 31), (-17, 15)]), (170, 184, 212))
    p.line(R([(-26, -4), (12, -15)]), 3.4, (120, 170, 236))


# ---------------------------------------------------------------- the second batch (Lv.10, round 9): uncommon
def coffee(p, t=0.0):
    """A mug of coffee: a cylinder seen a little from above (its mouth an ellipse as wide as it), a D-shaped
    handle on the side, steam curling up (light, no rim: drawn late)."""
    body, sh, hi = (236, 116, 92), (200, 84, 66), (252, 170, 148)
    p.arc(26, 10, 14, -78, 78, 8.5, body)                       # the handle, a loop on the side
    p.arc(26, 10, 14, -60, 60, 3.0, sh)
    p.rr(-4, 12, 50, 50, 4, body)                                 # the side of the cylinder ...
    p.ell(-4, 37, 25, 6.5, body)                                  # ... its round foot
    p.ell(-4, 39, 22, 4.5, sh)
    p.rr(18, 12, 6, 48, 3, sh)                                    # shade down the right, light down the left
    p.rr(-21, 12, 7, 44, 3.5, hi)
    p.ell(-4, -13, 25, 7.5, (250, 236, 220))                      # the mouth: the rim, the coffee inside
    p.ell(-4, -12, 21, 5.6, (110, 66, 46))
    p.ell(-9, -13.5, 7, 1.8, (168, 114, 82))
    def steam(q):
        for i, x0 in enumerate((-14, -3, 8)):
            ph = (t + i / 3.0) % 1.0
            a = 1.0 - ph
            if a < 0.12:
                continue
            y0 = -22 - 20 * ph
            pts = [(x0 + 4.5 * math.sin(2 * math.pi * (ph + k / 5.0)), y0 - 3.4 * k) for k in range(6)]
            q.line(pts, 1.4 + 3.0 * a, (206, 212, 228))
    p.late.append(steam)


def usb(p, t=0.0):
    """A USB stick: a plastic body, the metal plug with its two square holes and the tongue inside, a little ring
    hole at the end; the light on it blinks."""
    p.rr(0, -30, 22, 26, 1.5, (200, 208, 220))                    # the metal plug
    p.rr(-6, -36, 5, 5, 0.6, (90, 98, 116))
    p.rr(6, -36, 5, 5, 0.6, (90, 98, 116))
    p.rr(0, -24, 16, 6, 1, (236, 240, 246))                       # the tongue inside, seen through the end
    p.rr(-8, -30, 3, 24, 1, (232, 238, 246))                      # a shine on the metal
    p.rr(0, 10, 30, 56, 8, (60, 104, 204))                        # the body
    p.rr(-9, 8, 8, 46, 4, (104, 148, 232))
    p.rr(9, 12, 5, 46, 2.5, (44, 82, 170))
    p.rr(0, -16, 30, 6, 2, (44, 82, 170))                         # where the plug goes in
    p.circ(0, 30, 3.6, (34, 60, 130))                             # the little ring hole at the end ...
    p.erase(0, 30, 2.2)
    p.rr(0, 12, 8, 4, 2, (210, 230, 255) if (t * 4) % 1.0 < 0.5 else (120, 240, 160))   # ... and the light


def headphones(p, t=0.0):
    """Over-ear headphones: a padded band, sliders down to two big round cups with soft cushions; they bob to a
    beat only they hear, little notes come out (light, drawn late)."""
    beat = abs(_S(2 * t))
    dark, mid, light = (64, 68, 90), (92, 98, 128), (140, 148, 182)
    p.arc(0, 4, 34, 196, 344, 5.5, dark)                          # the steel band
    p.arc(0, 4, 31, 214, 326, 9, mid)                             # the padding on top
    p.arc(0, 4, 29, 228, 312, 3, light)
    for s in (-1, 1):
        x = s * (34 + 1.2 * beat)
        p.line([(s * 33, -6), (x, 6)], 4, dark)                   # the slider
        p.ell(x, 16, 13, 18, (236, 96, 120))                      # the cup
        p.ell(x + s * 2, 13, 6, 10, (255, 160, 178), s * 10)
        p.ell(x - s * 9, 16, 5.5, 16, dark)                       # the cushion facing in
        p.ell(x - s * 10, 16, 3, 12, mid)
    def notes(q):
        for i in range(2):
            ph = (2 * t + i * 0.5) % 1.0
            if ph > 0.8:
                continue
            x, y = (-28 if i == 0 else 28) + (-1 if i == 0 else 1) * 8 * ph, -20 - 22 * ph
            q.ell(x, y, 4.4, 3.2, (255, 214, 110), -25)
            q.line([(x + 3.8, y - 1), (x + 3.8, y - 14)], 2.2, (255, 214, 110))
            q.line([(x + 3.8, y - 14), (x + 9, y - 10)], 2.2, (255, 214, 110))
    p.late.append(notes)


# ---------------------------------------------------------------- rare
def balloon(p, t=0.0, string=True):
    """A red party balloon: round, a short taper at the bottom to the tied knot, a shine at the top left and a
    darker side; a curly string; it bobs.  string=False: no string and no bob (the play draws a long one)."""
    bob = 2.5 * _S(t) if string else 0.0
    sw = 4 * _S(t + 0.25)
    R, cy = 29.0, -13.0 + bob
    def shape(r, dx=0.0, dy=0.0):
        out = []
        for i in range(64):
            a = 2 * math.pi * i / 64
            lo = max(0.0, math.sin(a))                            # the lower half narrows towards the knot
            out.append((dx + r * math.cos(a) * (1.0 - 0.2 * lo ** 2), cy + dy + r * 1.04 * math.sin(a) + 1.2 * lo ** 6))
        return out
    ky = cy + R * 1.04 + 1.0                                      # the neck's bottom: the knot hangs from it
    if string:
        pts = [(0, ky + 3)]
        for k in range(1, 9):                                     # the string, curling as it hangs
            pts.append((sw * k / 8.0 + 3.0 * math.sin(k * 1.4), ky + 3 + 2.9 * k))
        p.line(pts, 1.6, (110, 96, 104))
    p.poly([(-4.0, ky + 4.0), (4.0, ky + 4.0), (0, ky - 3.0)], (190, 40, 54))   # the knot: a small tie ...
    p.ell(0, ky + 4.2, 4.2, 2.0, (190, 40, 54))                   # ... with a rounded lip
    p.poly(shape(R), (206, 42, 58))                               # the darker side shows round the edge ...
    p.poly(shape(R * 0.9, -2.2, -1.8), (234, 64, 78))             # ... the body
    p.poly(shape(R * 0.62, -5.5, -5.0), (244, 92, 104))           # ... lighter towards the light
    p.ell(-11, cy - 12, 6.5, 10.5, (255, 196, 202), -30)          # the shine
    p.ell(-17, cy + 1, 2.4, 3.4, (255, 214, 218), -30)


def robot(p, t=0.0):
    """A little tin wind-up robot: a box head with a face plate and antenna, a body with a dial, short arms and
    legs; the key in its back (seen at the side) turns, and it marches on the spot."""
    stp = _S(2 * t)
    y = -1.6 * abs(stp)
    body, dark, light = (164, 180, 204), (112, 126, 152), (210, 222, 238)
    for s in (-1, 1):                                             # the legs, taking turns
        lift = 3 if (s > 0) == (stp > 0) else 0
        p.rr(s * 8, 40 - lift, 10, 12, 2, dark)
        p.rr(s * 8, 46 - lift, 13, 4, 2, (84, 94, 118))
    a = 360 * t                                                   # the wind-up key in its side: a brass shaft and a
    k = 0.35 + 0.65 * abs(math.cos(math.radians(a)))             # big butterfly handle with two holes, turning
    gold, gold_d = (240, 190, 70), (190, 140, 40)
    p.rr(-25, 21 + y, 14, 5, 2, gold_d)
    for dy in (-8.5, 8.5):
        p.ell(-36, 21 + y + dy, 6.5 * k + 1.0, 8.5, gold)
        if k > 0.55:
            p.erase(-36, 21 + y + dy * 1.05, 2.4 * k)
    p.circ(-33, 21 + y, 4, gold_d)
    p.rr(0, 21 + y, 34, 26, 5, body)                              # the body, a dial on it
    p.rr(-7, 19 + y, 8, 20, 3, light)
    p.circ(3, 21 + y, 5.4, (250, 250, 250))
    p.line([(3, 21 + y), (3 + 4 * math.cos(math.radians(a)), 21 + y + 4 * math.sin(math.radians(a)))], 1.6, (236, 90, 80))
    for s in (-1, 1):
        p.rr(s * 21, 22 + y, 7, 16, 3, dark)                      # the arms, a claw at each
        p.rr(s * 21, 31 + y, 9, 4, 2, (84, 94, 118))
    p.rr(0, -10 + y, 42, 30, 7, body)                             # the head
    p.rr(-9, -13 + y, 14, 20, 5, light)
    p.rr(0, -8 + y, 32, 15, 5, (46, 52, 70))                      # the face plate, two eyes, a grille mouth
    for s in (-1, 1):
        p.circ(s * 8, -10 + y, 3.6, (120, 230, 255))
        p.circ(s * 8 - 1, -11 + y, 1.2, WHITE)
    for x in (-4, 0, 4):
        p.line([(x, -3 + y), (x, -1 + y)], 1.4, (120, 230, 255))
    for s in (-1, 1):
        p.rr(s * 22, -10 + y, 4, 10, 2, dark)                     # bolts on the sides of the head
    p.line([(0, -25 + y), (0, -33 + y)], 2.6, dark)               # the antenna
    p.circ(0, -35 + y, 4.2, (255, 196, 80))


def _mix(a, b, f):
    return tuple(int(round(x + (y - x) * f)) for x, y in zip(a, b))


TOP_RX, TOP_FACE, TOP_BAND, TOP_TIP = 30.0, -26.0, -12.0, 34.0   # the top: its crown's radius, the face, the band's foot, the point
TOP_E = 0.3                       # seen from this far above: its round face this flat (sin of the angle)
TOP_RED, TOP_RED_D, TOP_GOLD, TOP_TEAL = (214, 40, 50), (150, 22, 36), (255, 194, 58), (28, 164, 156)
TOP_RINGS = ((1.0, (214, 40, 50)), (0.8, (252, 128, 40)), (0.62, (255, 204, 60)), (0.45, (84, 180, 82)), (0.3, (56, 112, 216)))
TOP_WOOD, TOP_WOOD_D, TOP_WOOD_L = (222, 156, 92), (172, 108, 58), (248, 204, 146)
CORD, CORD_L = (124, 74, 52), (168, 112, 82)   # the whip's cord


def _top_hw(y):
    """The top's half width at height y on its cone (below the crown's band)."""
    s = min(1.0, max(0.0, (y - TOP_BAND) / (TOP_TIP - TOP_BAND)))
    return 4.0 + (TOP_RX - 4.0) * (1.0 - s ** 1.4)


def _top(p, phase=0.0, blur=0.0, lean=0.0, wound=0.0, x0=0.0):
    """A lacquered wooden whip top, upright on its steel point: rainbow rings round its face (three white dots on the
    gold one go round with it), a deep red crown with gold lines, a wooden cone with a gold and a teal ring.  phase:
    how far it has turned (turns); blur 0..1: spinning too fast to see (the dots and lines run into rings and a sheen;
    the rings stay rings, as on a real one); lean: tipped towards you (sin, + shows more of its face); wound 0..1:
    the whip's cord wound round its cone."""
    e = min(0.55, max(0.06, TOP_E + lean))
    ys = [TOP_BAND + (TOP_TIP - TOP_BAND) * i / 16.0 for i in range(17)]
    p.poly([(x0 + _top_hw(y), y) for y in ys] + [(x0 - _top_hw(y), y) for y in reversed(ys)], TOP_WOOD)   # the cone
    p.poly([(x0 + 0.38 * _top_hw(y), y) for y in ys] + [(x0 + _top_hw(y), y) for y in reversed(ys)], TOP_WOOD_D)
    p.poly([(x0 - 0.64 * _top_hw(y), y) for y in ys[:13]] + [(x0 - 0.4 * _top_hw(y), y) for y in reversed(ys[:13])], TOP_WOOD_L)
    def ring(y0, y1, col, n=20):                                     # a band round the cone, between two heights
        top = [(x0 + _top_hw(y0) * math.sin(a), y0 + _top_hw(y0) * e * math.cos(a)) for a in
               (math.pi * (i / float(n) - 0.5) for i in range(n + 1))]
        bot = [(x0 + _top_hw(y1) * math.sin(a), y1 + _top_hw(y1) * e * math.cos(a)) for a in
               (math.pi * (i / float(n) - 0.5) for i in range(n + 1))]
        p.poly(top + list(reversed(bot)), col)
    ring(TOP_BAND + 1.5, TOP_BAND + 4.0, TOP_GOLD)
    ring(TOP_BAND + 9.0, TOP_BAND + 15.0, TOP_TEAL)
    ring(TOP_BAND + 10.2, TOP_BAND + 11.4, (120, 220, 208))
    ring(TOP_BAND + 24.0, TOP_BAND + 26.0, TOP_RED)
    p.circ(x0, TOP_TIP + 3.6, 4.6, (150, 156, 172))                  # the steel point
    p.circ(x0 - 1.4, TOP_TIP + 2.4, 1.7, (226, 232, 242))
    if wound > 0.0:                                                  # the cord wound round it, coil under coil
        n = max(1, int(math.ceil(6 * wound - 1e-6)))
        for j in range(n):
            y = TOP_BAND + 5.0 + 3.6 * j
            rx = _top_hw(y) + 1.4
            pts = [(x0 + rx * math.sin(a), y + rx * e * math.cos(a) + 2.2 * math.sin(a)) for a in
                   (math.pi * (i / 14.0 - 0.5) for i in range(15))]
            p.line(pts, 3.4, CORD)
            p.line([(x, y_ - 0.9) for x, y_ in pts[3:12]], 1.1, CORD_L)
    # the crown: deep red, lit from the left, gold lines going round with it (a sheen when it spins fast)
    def band(c0, c1, col):
        steps = max(2, int(10 * (c1 - c0)))
        arc = [c0 + (c1 - c0) * i / float(steps) for i in range(steps + 1)]
        p.poly([(x0 + TOP_RX * math.sin(a), TOP_FACE + TOP_RX * e * math.cos(a)) for a in arc] +
               [(x0 + TOP_RX * math.sin(a), TOP_BAND + TOP_RX * e * math.cos(a)) for a in reversed(arc)], col)
    def shade(col, a):
        f = 1.08 - 0.26 * (math.sin(a) + 0.25)
        return tuple(max(0, min(255, int(v * f))) for v in col)
    for i in range(12):
        c0, c1 = math.pi * (i / 12.0 - 0.5), math.pi * ((i + 1) / 12.0 - 0.5)
        band(c0, c1, shade(_mix(TOP_RED, TOP_GOLD, 0.1 * blur), 0.5 * (c0 + c1)))
    for k in range(6):
        mid = 2 * math.pi * (phase + k / 6.0)
        mid = (mid + math.pi) % (2 * math.pi) - math.pi
        for m in (mid, mid - 2 * math.pi, mid + 2 * math.pi):
            c0, c1 = max(m - 0.1, -math.pi / 2), min(m + 0.1, math.pi / 2)
            if c1 > c0:
                band(c0, c1, shade(_mix(TOP_GOLD, _mix(TOP_RED, TOP_GOLD, 0.1), blur), 0.5 * (c0 + c1)))
    if blur > 0.3:                                                   # streaks of the spin across it
        for q in (0.3, 0.68):
            y = TOP_FACE + (TOP_BAND - TOP_FACE) * q
            p.line([(x0 + TOP_RX * 0.95 * math.sin(a), y + TOP_RX * e * math.cos(a)) for a in
                    (math.pi * (i / 12.0 - 0.5) for i in range(1, 11))], 1.2, _mix(TOP_RED, (255, 214, 150), 0.55 * (blur - 0.3) / 0.7))
    p.line([(x0 + TOP_RX * math.sin(a), TOP_BAND + TOP_RX * e * math.cos(a)) for a in
            (math.pi * (i / 16.0 - 0.5) for i in range(17))], 1.4, TOP_RED_D)   # its lower edge
    # the face: rainbow rings, a gold rim, three dots going round, a wooden knob in the middle
    for r, col in TOP_RINGS:
        p.ell(x0, TOP_FACE, TOP_RX * r, TOP_RX * e * r, col)
    p.line([(x0 + TOP_RX * math.sin(a), TOP_FACE + TOP_RX * e * math.cos(a)) for a in
            (math.pi * (i / 16.0 - 0.5) for i in range(17))], 1.4, TOP_GOLD)   # the rim at the front
    rd = 0.71
    if blur < 0.5:
        for k in range(3):
            a = 2 * math.pi * (phase + k / 3.0)
            p.ell(x0 + TOP_RX * rd * math.sin(a), TOP_FACE + TOP_RX * e * rd * math.cos(a), 2.6, 2.6 * e + 0.7,
                  _mix(WHITE, (255, 204, 60), 1.6 * blur))
    else:
        p.line([(x0 + TOP_RX * rd * math.sin(a), TOP_FACE + TOP_RX * e * rd * math.cos(a)) for a in
                (2 * math.pi * i / 28.0 for i in range(29))], 1.3, _mix((255, 204, 60), WHITE, 0.3 + 0.5 * (blur - 0.5)))
    p.ell(x0, TOP_FACE - 1.2, 5.0, 5.0 * e + 1.4, (164, 104, 56))   # a little wooden knob in the middle
    p.ell(x0 - 1.3, TOP_FACE - 2.2, 2.0, 1.2, (232, 186, 130))


def spin_top(p, t=0.0):
    """陀螺: a wooden whip top turning slowly on its point, its whip leaning behind it (a short stick, the cord
    hanging from its end in a loose curl)."""
    p.line([(36, 44), (26, -30)], 5.8, (112, 72, 42))                # the whip's stick
    p.line([(34.8, 38), (27.2, -24)], 1.6, (170, 124, 82))
    p.circ(26, -31, 3.8, (96, 60, 34))
    _top(p, phase=t, x0=-12.0)
    cord = [(26, -31), (33, -29), (39, -22), (43, -11), (44, 1), (42, 13), (43, 25), (47, 34)]   # it hangs in a loose curve
    p.line(cord, 3.2, CORD)
    p.line([(x - 0.7, y) for x, y in cord[2:6]], 1.0, CORD_L)


def _face(p, pts, cols, n=3):
    """A face of the cube: pts the four corners in turn, cols n x n colours."""
    (ax, ay), (bx, by), (cx_, cy_), (dx, dy) = pts
    def at(u, v):
        x0, y0 = ax + (bx - ax) * u, ay + (by - ay) * u
        x1, y1 = dx + (cx_ - dx) * u, dy + (cy_ - dy) * u
        return x0 + (x1 - x0) * v, y0 + (y1 - y0) * v
    p.poly([at(0, 0), at(1, 0), at(1, 1), at(0, 1)], (34, 34, 40))
    g = 0.09
    for i in range(n):
        for j in range(n):
            u0, u1, v0, v1 = (i + g) / n, (i + 1 - g) / n, (j + g) / n, (j + 1 - g) / n
            p.poly([at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)], cols[j * n + i])


CUBE = [(232, 64, 70), (255, 146, 54), (255, 216, 66), (84, 196, 104), (64, 132, 232), (246, 246, 246)]


CUBE_FACES = ('U', 'F', 'R', 'B', 'L')   # top, and the four sides round it
CUBE_NORMAL = {'F': (0.0, 1.0), 'R': (1.0, 0.0), 'B': (0.0, -1.0), 'L': (-1.0, 0.0)}   # (x, z) of each side
CUBE_GOAL = {'U': CUBE[5], 'F': CUBE[0], 'R': CUBE[4], 'B': CUBE[1], 'L': CUBE[3]}   # solved: white top, red, blue ...
CUBE_H = 25.5                     # half its edge (box units)
CUBE_YAW = -45.0                  # degrees: at rest a corner to the front (the left side is F, the right R)
CUBE_PITCH = math.asin(0.527)     # seen from this far above (the top a flat diamond, as an isometric icon)
CUBE_ROWS = [('U', 1), ('F', 2), ('R', 0), ('L', 1), ('U', 0), ('B', 2), ('F', 1), ('R', 2), ('U', 2), ('L', 0),
             ('B', 1), ('F', 0), ('R', 1), ('B', 0), ('L', 2)]   # solving: the rows in their order
CUBE_STEPS = 12                   # ... over this many steps (a quarter turn each in the play)


def _cube_mix(seed, f, k):
    return CUBE[(seed * 7 + f * 5 + k * 3 + (k * k) % 5) % 6]


def cube(p, t=0.0, mode='icon'):
    """A puzzle cube, drawn in 3D: seen from above a corner, turned round its upright axis (yaw).  icon: at rest,
    mixed up, its colours change twice a loop (being turned); spin: the colours all flicker; solved: one colour a
    face and a sparkle; turning: t is how many turns it has made (the play spins it): a quarter turn, a row more in
    its colour (CUBE_ROWS, CUBE_STEPS), the rest still mixed up and mixed anew; at t = 0 it is the icon at t = 0,
    at t = CUBE_STEPS / 4 solved but for the sparkle, at rest again (whole turns)."""
    yaw = CUBE_YAW
    if mode == 'solved':
        cols = dict((f, [CUBE_GOAL[f]] * 9) for f in CUBE_FACES)
    elif mode == 'turning':
        yaw = CUBE_YAW - 360.0 * t
        step = min(CUBE_STEPS, int(math.floor(t * 4.0 + 1e-6)))
        done = set(CUBE_ROWS[:int(step * len(CUBE_ROWS) / CUBE_STEPS)])
        cols = dict((f, [CUBE_GOAL[f] if (f, k // 3) in done else _cube_mix(step, i, k) for k in range(9)])
                    for i, f in enumerate(CUBE_FACES))
    else:
        seed = int(t * (12 if mode == 'spin' else 2))
        cols = dict((f, [_cube_mix(seed, i, k) for k in range(9)]) for i, f in enumerate(CUBE_FACES))
    h = CUBE_H
    cy_, sy_ = math.cos(CUBE_PITCH), math.sin(CUBE_PITCH)
    q = math.radians(yaw)
    cq, sq = math.cos(q), math.sin(q)
    def turn(x, z):
        return x * cq + z * sq, -x * sq + z * cq
    def screen(x, y, z):
        x_, z_ = turn(x, z)
        return x_, -y * cy_ + z_ * sy_
    faces = []
    for f in ('F', 'R', 'B', 'L'):
        nx, nz = CUBE_NORMAL[f]
        tx, tz = turn(nx, nz)
        if tz <= 0.02: continue                                   # facing away
        rx, rz = nz, -nx                                          # its right, seen from outside
        c = (nx * h, nz * h)
        pts = [screen(c[0] - rx * h, h, c[1] - rz * h), screen(c[0] + rx * h, h, c[1] + rz * h),
               screen(c[0] + rx * h, -h, c[1] + rz * h), screen(c[0] - rx * h, -h, c[1] - rz * h)]
        shade = 0.78 - 0.12 * tx                                  # lit from the left
        faces.append((pts, [tuple(int(v * shade) for v in col) for col in cols[f]]))
    for pts, cl in faces:
        _face(p, pts, cl)
    top = [screen(-h, h, -h), screen(h, h, -h), screen(h, h, h), screen(-h, h, h)]
    _face(p, top, cols['U'])
    if mode == 'solved':
        p.star(28, -32, 12, 3.4, (255, 250, 210))


# ---------------------------------------------------------------- special
def moon_lamp(p, t=0.0, lit=True, part='all'):
    """A crescent moon on a little wooden stand, glowing softly, a sleepy face on it; two tiny stars twinkle by it.
    lit=False: off, grey.  part: 'moon' (no stand: it floats off it in the play) or 'stand' (the stand alone)."""
    glow = 0.5 + 0.5 * _S(t) if lit else 0.0
    if part != 'moon':
        p.rr(0, 40, 46, 9, 4, (150, 102, 66))                     # the stand
        p.rr(0, 35, 10, 8, 2, (124, 84, 54))
        p.rr(0, 24, 4.5, 18, 2, (124, 84, 54))
    if part == 'stand':
        return
    moon = (255, 236, 150) if lit else (214, 206, 176)
    p.circ(2, -8, 30, moon)                                       # the crescent: a disc, a bite out of it
    p.erase(16, -16, 25)
    if lit:
        p.ell(-14, -10, 5, 9, (255, 248, 210), 20)
    p.circ(-10, 2, 2.6, (230, 196, 110))                          # a sleepy face on it
    p.arc(-13, -12, 3.6, 20, 160, 1.8, (180, 140, 80))
    if part == 'moon':                                            # up in its night sky: its own stars there
        return
    for i, (x, y, R) in enumerate(((26, -30, 9.0), (34, 4, 6.0))):
        k = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(2 * math.pi * (t + i * 0.45)))
        p.star(x, y, R * k * (0.6 + 0.4 * glow) if lit else R * 0.5, R * k * 0.28, (255, 246, 190) if lit else (200, 196, 180))


ITEMS = {  # name: (中文, English, rarity, painter, turn)
    'semicolon': ('分号', 'Semicolon', 'common', semicolon, 0), 'paperclip': ('回形针', 'Paperclip', 'common', paperclip, 32),
    'screw': ('小螺丝', 'Screw', 'common', screw, -28), 'sticky_note': ('便利贴', 'Sticky note', 'common', sticky_note, -7),
    'pencil': ('铅笔头', 'Pencil stub', 'common', pencil, 40), 'paper_ball': ('纸团', 'Paper ball', 'common', paper_ball, 0),
    'leaf': ('树叶', 'Leaf', 'common', leaf, 36), 'pebble': ('小石子', 'Pebble', 'common', pebble, 0),
    'braces': ('花括号', 'Braces', 'uncommon', braces, 0), 'gear': ('小齿轮', 'Gear', 'uncommon', gear, 12),
    'keycap': ('迷你键帽', 'Keycap', 'uncommon', keycap, -6), 'floppy': ('旧软盘', 'Floppy disk', 'uncommon', floppy, 6),
    'shell': ('贝壳', 'Shell', 'uncommon', shell, -8),
    'rubber_duck': ('橡皮鸭', 'Rubber duck', 'rare', rubber_duck, 0), 'gold_semicolon': ('金色分号', 'Golden semicolon', 'rare', gold_semicolon, 0),
    'bug': ('被抓住的小虫', 'Caught bug', 'special', bug, -24), 'bottle': ('漂流瓶', 'Message bottle', 'special', bottle, 38),
    'biscuit': ('压缩饼干', 'Hardtack', 'special', biscuit, -8), 'hourglass': ('沙漏', 'Hourglass', 'special', hourglass, 0),
    'plane_model': ('纸飞机模型', 'Paper plane model', 'special', plane_model, 0),
}
ITEMS['bug_fly'] = ('被抓住的小虫', 'Caught bug', 'special', lambda p, t=0.0: bug(p, t, fly=True), -24)
ITEMS['plane_model_play'] = ('纸飞机模型', 'Paper plane model', 'special', lambda p, t=0.0: plane_model(p, t, air='late'), 0)
ITEMS['plane_model_stand'] = ('纸飞机模型', 'Paper plane model', 'special', lambda p, t=0.0: plane_model(p, t, plane=False), 0)
ITEMS['plane_model_plane'] = ('纸飞机模型', 'Paper plane model', 'special', lambda p, t=0.0: plane_model(p, t, stand=False, air='late'), 0)
ITEMS['hourglass_play'] = ('沙漏', 'Hourglass', 'special', lambda p, t=0.0: hourglass(p, t, grains=True), 0)
ITEMS['bottle_open'] = ('漂流瓶', 'Message bottle', 'special', lambda p, t=0.0: bottle(p, t, cork=False), 38)
ITEMS['bottle_empty'] = ('漂流瓶', 'Message bottle', 'special', lambda p, t=0.0: bottle(p, t, cork=False, paper=False), 38)
ORDER = ['semicolon', 'paperclip', 'screw', 'sticky_note', 'pencil', 'paper_ball', 'leaf', 'pebble', 'braces', 'gear', 'keycap',
         'floppy', 'shell', 'rubber_duck', 'gold_semicolon', 'bug', 'bottle', 'biscuit', 'hourglass', 'plane_model']
ITEMS_B2 = {  # name: (中文, English, rarity, painter, turn)
    'coffee': ('咖啡杯', 'Coffee mug', 'uncommon', coffee, 0), 'usb': ('U 盘', 'USB stick', 'uncommon', usb, 24),
    'headphones': ('耳机', 'Headphones', 'uncommon', headphones, 0),
    'balloon': ('气球', 'Balloon', 'rare', balloon, 0),
    'robot': ('发条小机器人', 'Wind-up robot', 'rare', robot, 0), 'cube': ('魔方', "Puzzle cube", 'rare', cube, 0),
    'spin_top': ('陀螺', 'Spinning top', 'rare', spin_top, 0),
    'moon_lamp': ('小月亮夜灯', 'Moon lamp', 'special', moon_lamp, 0),
}
ORDER_B2 = ['coffee', 'usb', 'headphones', 'balloon', 'robot', 'cube', 'spin_top', 'moon_lamp']
ITEM_MOTION_B2 = {
    'usb': lambda t: (4 * _S(t), 0, 0), 'balloon': lambda t: (4 * _S(t), 0, 0),
    'moon_lamp': lambda t: (1.5 * _S(t), 0, 0),
}
ORDER += ORDER_B2           # in the frames from the start; the pets dig them up only from Lv.10 (the gift items_2)
ITEMS.update(ITEMS_B2)
ITEMS['balloon_free'] = ('气球', 'Balloon', 'rare', lambda p, t=0.0: balloon(p, t, string=False), 0)
ITEMS['cube_spin'] = ('魔方', "Puzzle cube", 'rare', lambda p, t=0.0: cube(p, t, 'spin'), 0)
ITEMS['cube_turning'] = ('魔方', "Puzzle cube", 'rare', lambda p, t=0.0: cube(p, t, 'turning'), 0)
ITEMS['cube_solved'] = ('魔方', "Puzzle cube", 'rare', lambda p, t=0.0: cube(p, t, 'solved'), 0)
ITEMS['spin_top_run'] = ('陀螺', 'Spinning top', 'rare', lambda p, t=(0.0, 0.0, 0.0, 0.0): _top(p, *t), 0)   # t from the play:
                                                                                     # (turned, blur, lean, wound)
ITEMS['moon_lamp_off'] = ('小月亮夜灯', 'Moon lamp', 'special', lambda p, t=0.0: moon_lamp(p, t, lit=False), 0)
ITEMS['moon_lamp_moon'] = ('小月亮夜灯', 'Moon lamp', 'special', lambda p, t=0.0: moon_lamp(p, t, part='moon'), 0)
ITEMS['moon_lamp_stand'] = ('小月亮夜灯', 'Moon lamp', 'special', lambda p, t=0.0: moon_lamp(p, t, part='stand'), 0)
LOOP_FRAMES = 24            # each treasure has a little loop of its own, this many frames (2 s at 12 a second)


def _S(t):
    return math.sin(2 * math.pi * t)


def _squeak(t):
    """The rubber duck is squeezed twice early in its loop: 0..1."""
    return max(math.sin(math.pi * min(1.0, max(0.0, (t - 0.08) / 0.16))), math.sin(math.pi * min(1.0, max(0.0, (t - 0.3) / 0.16))))


def _boing(t):
    return math.sin(6 * math.pi * t) * max(0.0, 1.0 - t / 0.72)


def _land(t):
    """the paper ball touches down at t = 0 and 0.5: 1 there, 0 in the air"""
    return max(0.0, 1.0 - 4.0 * abs(math.sin(2 * math.pi * t)))


def _tick(t, n=8):
    """a turn in steps: each tick a quick move and a rest (the gear: one tooth)"""
    f = (t * n) % 1.0
    return (int(t * n) + (1 - (1 - min(1.0, f / 0.45)) ** 3)) / float(n)


# how the whole icon moves in its loop: t -> (turn in degrees, dx, dy[, stretch x, stretch y]), all periodic.
# What is the treasure's own (the pencil writes, the pearl comes up, a bite is taken) is in its painter.
ITEM_MOTION = {
    'paperclip': lambda t: (0, 0, 0, 1 - 0.1 * _boing(t), 1 + 0.2 * _boing(t)),
    'screw': lambda t: (3 * _S(2 * t), 0, 0), 'sticky_note': lambda t: (2.5 * _S(t), 0, 0),
    'paper_ball': lambda t: (360 * t, 7 * _S(t), -9 * abs(_S(t)), 1 + 0.08 * _land(t), 1 - 0.1 * _land(t)),
    'leaf': lambda t: (22 * _S(t), 10 * _S(t), 4 * math.cos(4 * math.pi * t)),
    'gear': lambda t: (360 * _tick(t), 0, 0), 'shell': lambda t: (3 * _S(t), 0, 0),
    'rubber_duck': lambda t: (5 * _S(t), 0, 2.5 * math.cos(4 * math.pi * t), 1 + 0.12 * _squeak(t), 1 - 0.16 * _squeak(t)),
    'bug': lambda t: (7 * _S(t), 2 * _S(t), 0), 'bottle': lambda t: (9 * _S(t), 0, 2.5 * math.cos(2 * math.pi * t)),
    'bottle_open': lambda t: (9 * _S(t), 0, 2.5 * math.cos(2 * math.pi * t)),
    'bottle_empty': lambda t: (9 * _S(t), 0, 2.5 * math.cos(2 * math.pi * t)),
    'biscuit': lambda t: (2 * _S(4 * t), 0, 0), 'floppy': lambda t: (3 * _S(t), 0, 0),
    'hourglass': lambda t: (180 * (0.5 - 0.5 * math.cos(math.pi * (t - 0.76) / 0.24)) if t > 0.76 else 0, 0, 0),
}
ITEM_MOTION.update(ITEM_MOTION_B2)
# what glows round a find held up, by how rare it is: (the glow, the rays, how many rays, sparkles going round)
AURA = {'common': ((236, 240, 248), None, 0, 3), 'uncommon': ((96, 176, 255), (150, 206, 255), 6, 0),
        'rare': ((196, 120, 255), (226, 176, 255), 8, 6), 'special': ((255, 196, 60), (255, 226, 120), 12, 4)}   # gold is the highest
AURA_BOX = 2.3              # the aura's image is this many icon boxes wide


def draw_item(name, px, rim=True, t=0.0, shine=True):
    """-> the icon as an RGBA image px x px (straight alpha) at phase t (0..1) of its loop: it moves a little, and
    a glint of light runs across it once."""
    n = max(8, int(px)) * SS
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    paint, turn = ITEMS[name][3], ITEMS[name][4]
    mv = tuple(ITEM_MOTION.get(name, lambda t: (0, 0, 0))(t)) + (1.0, 1.0)
    pen = Pen(img, rot=turn + mv[0], scale=0.84, dx=mv[1], dy=mv[2], sx=mv[3], sy=mv[4])
    paint(pen, t)
    if shine and 0.3 <= t < 0.62:                              # the glint: a slanted band of light, only on the icon
        f = (t - 0.3) / 0.32
        band = Image.new('L', (n, n), 0)
        x = (-0.35 + 1.7 * f) * n
        w = 0.13 * n
        ImageDraw.Draw(band).polygon([(x, 0), (x + w, 0), (x + w - 0.4 * n, n), (x - 0.4 * n, n)], fill=150)
        band = band.filter(ImageFilter.GaussianBlur(0.02 * n))
        glint = Image.new('RGBA', (n, n), (255, 255, 255, 0))
        glint.putalpha(ImageChops.multiply(band, img.getchannel('A')))
        img.alpha_composite(glint)
    if rim:
        k = n / 100.0
        r = max(1, int(round(RIM_W * k)))
        grown = img.getchannel('A').filter(ImageFilter.MaxFilter(2 * r + 1))
        grown = grown.filter(ImageFilter.GaussianBlur(max(0.6, 0.35 * r))).point(lambda v: min(255, int(v * 1.6)))
        back = Image.new('RGBA', (n, n), RIM + (0,))
        back.putalpha(grown)
        back.alpha_composite(img)
        img = back
    if pen.late:
        q = Pen(img, rot=turn + mv[0], scale=0.84, dx=mv[1], dy=mv[2], sx=mv[3], sy=mv[4])
        for f in pen.late: f(q)
    return img.resize((max(8, int(px)),) * 2, Image.LANCZOS)


def draw_aura(rarity, px, t=0.0):
    """-> what glows behind a find of this rarity, AURA_BOX icon boxes wide (px: the icon's box), at phase t: a
    soft glow in the rarity's colour, rays that turn (one step of their pattern a loop) and sparkles going round."""
    glow, ray, n_rays, n_sp = AURA[rarity]
    N = max(8, int(round(px * AURA_BOX))) * 2
    c = N / 2.0
    u = N / (100.0 * AURA_BOX)                                 # px per icon unit
    img = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    lay = Image.new('L', (N, N), 0)
    d = ImageDraw.Draw(lay)
    R = (50 if rarity == 'common' else 62) * u * (1 + 0.05 * _S(t))
    d.ellipse((c - R, c - R, c + R, c + R), fill=(120 if rarity == 'common' else 170))
    lay = lay.filter(ImageFilter.GaussianBlur(14 * u))
    g = Image.new('RGBA', (N, N), glow + (0,))
    g.putalpha(lay)
    img.alpha_composite(g)
    if n_rays:
        lay = Image.new('L', (N, N), 0)
        d = ImageDraw.Draw(lay)
        for i in range(n_rays):
            q = 2 * math.pi * (i + 2 * t) / n_rays
            long_ = i % 2 == 0
            r0, r1 = 44 * u, (104 if long_ else 80) * u * (1 + 0.06 * _S(t + (0.5 if long_ else 0)))
            hw0, hw1 = 0.05, (0.15 if rarity == 'special' else 0.12)
            d.polygon([(c + r0 * math.cos(q - hw0), c + r0 * math.sin(q - hw0)), (c + r1 * math.cos(q - hw1), c + r1 * math.sin(q - hw1)),
                       (c + r1 * math.cos(q + hw1), c + r1 * math.sin(q + hw1)), (c + r0 * math.cos(q + hw0), c + r0 * math.sin(q + hw0))], fill=215)
        lay = lay.filter(ImageFilter.GaussianBlur(1.2 * u))
        g = Image.new('RGBA', (N, N), ray + (0,))
        g.putalpha(lay)
        img.alpha_composite(g)
    d = ImageDraw.Draw(img)
    for i in range(n_sp):
        q = 2 * math.pi * (i + t) / n_sp + 0.4
        rr = (70 if rarity == 'common' else 92) * u
        x, y = c + rr * math.cos(q), c + rr * 0.92 * math.sin(q)
        k = (0.5 + 0.5 * abs(math.sin(2 * math.pi * (t * 2 + i * 0.37)))) * (9 if rarity == 'common' else 13) * u
        col = (255, 255, 255) if rarity != 'special' else (255, 246, 200)
        pts = []
        for j in range(8):
            a = math.radians(-90 + 45 * j)
            r_ = k if j % 2 == 0 else k * 0.3
            pts.append((x + r_ * math.cos(a), y + r_ * math.sin(a)))
        d.polygon(pts, fill=col + (255,))
    return img.resize((N // 2, N // 2), Image.LANCZOS)
