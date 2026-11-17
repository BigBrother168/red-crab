# Clawd: flat 2D renderer + parametric action library.
# Units are logical pixels of the 1920x1080 canvas; FLOOR_Y is where the feet stand.
import math, copy
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from common import *

BW, BH = 290.0, 230.0        # body size
LEG_L, LEG_W = 58.0, 25.0     # legs
NUB_L, NUB_T = 60.0, 46.0     # nubs (arms)
LEG_X = (-0.37, -0.17, 0.17, 0.37)   # leg centres as fraction of body width
EYE_W, EYE_H = 0.083 * BW, 0.225 * BH
EYE_X, EYE_Y = 0.215 * BW, -0.14 * BH  # eye centre offset from body centre

HOME_X = 1690.0
REST_PANG = -62.0     # resting pointer angle relative to the left nub (pointer tip rests near the floor)
BASE = dict(x=HOME_X, lift=0.0, sx=1.0, sy=1.0, tilt=0.0, eyes='open', eye_open=1.0, look=(0.0, 0.0),
            nubL=(18.0, 1.0), nubR=(-10.0, 1.0), frontL=False, frontR=False, propL='pointer', propR=None,
            propangL=REST_PANG, propangR=0.0, walk=0.0, walkamp=0.0, blush=0.0, thumbR=False, spin=1.0, glasses=False,
            plen=150.0, fingersR=0, wink=False, legx=0.0)

NUB_COL = (207, 108, 77); NUB_HI = (226, 140, 108); LEG_COL = (190, 96, 66); LEG_HI = (206, 112, 80)


def new_pose(**kw):
    p = dict(BASE); p.update(kw); return p


# ------------------------------------------------------------------ geometry
def tilt_pivot(P, bw, feet):
    """Tilting rocks on the foot that would otherwise sink into the floor (near tilt 0 the choice does not show)."""
    side = -1 if P['tilt'] > 0 else 1
    return P['x'] + side * abs(LEG_X[0]) * bw, feet


def geom(P):
    """key points of the pose in logical frame coordinates (before tilt is applied to the drawing we rotate
    the points with the same pivot, so these are final positions)."""
    x = P['x']; feet = FLOOR_Y - P['lift']
    bw, bh = BW * abs(P['sx']) * max(0.05, abs(P['spin'])), BH * P['sy']
    bot = feet - LEG_L - P.get('legx', 0.0); top = bot - bh; cy = (top + bot) / 2
    g = dict(x=x, feet=feet, bot=bot, top=top, cy=cy, bw=bw, bh=bh)
    piv_y = bot - 0.42 * bh
    for side, key in ((-1, 'L'), (1, 'R')):
        ang, ext = P['nub' + key]; a = math.radians(ang)
        d = (side * math.cos(a), -math.sin(a))
        px = x + side * (bw / 2 - 12); g['piv' + key] = (px, piv_y); g['dir' + key] = d
        L = NUB_L * ext
        g['tip' + key] = (px + d[0] * (L - 4), piv_y + d[1] * (L - 4))
    g['head'] = (x, top - 18)
    piv = tilt_pivot(P, bw, feet)
    if abs(P['tilt']) > 1e-3:
        for k in ('pivL', 'pivR', 'tipL', 'tipR', 'head'):
            g[k] = rot_pts([g[k]], piv[0], piv[1], P['tilt'])[0]
    return g


# ------------------------------------------------------------------ drawing
def _body_texture(w, h, k, back=False):
    """shaded rounded body as RGBA (w,h in canvas px)"""
    w = max(4, int(round(w))); h = max(4, int(round(h)))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = xx / max(1, w - 1); v = yy / max(1, h - 1)
    base = np.array(CLAWD['base'], np.float32); hi = np.array(CLAWD['hi'], np.float32); sh = np.array(CLAWD['shade'], np.float32)
    fhi = np.clip(1.05 - (u * 0.95 + v * 1.25), 0, 1) ** 1.6 * 0.95
    fsh = np.clip((u * 0.75 + v * 1.15) - 0.95, 0, 1) ** 1.1 * 1.1
    col = base[None, None] * (1 - fhi[..., None]) + hi[None, None] * fhi[..., None]
    col = col * (1 - np.clip(fsh, 0, 1)[..., None]) + sh[None, None] * np.clip(fsh, 0, 1)[..., None]
    rim = np.clip(1 - v * h / (0.07 * h + 1e-6), 0, 1) ** 2 * 0.35          # soft top rim light
    col = col * (1 - rim[..., None]) + np.array([245, 180, 150], np.float32)[None, None] * rim[..., None]
    if back: col *= 0.92
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')
    m = Image.new('L', (w, h), 0); r = int(0.13 * min(w, h) + 0.5)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    img.putalpha(m)
    return img


def _draw_eyes(img, P, k, bw, bh):
    """eyes drawn into body texture coordinates"""
    d = ImageDraw.Draw(img); W, H = img.size; cx0, cy0 = W / 2, H / 2
    st = P['eyes']; lx, ly = P['look']; eo = clamp(P['eye_open'], 0.0, 1.0)
    sxw = bw / BW
    ew, eh = EYE_W * k * sxw, EYE_H * k * (bh / BH)
    col = CLAWD['eye']; lw = max(2, int(0.033 * BW * k))
    for side in (-1, 1):
        ex = cx0 + side * EYE_X * k * sxw + lx * 0.045 * BW * k * sxw
        ey = cy0 + EYE_Y * k * (bh / BH) + ly * 0.05 * BH * k
        if P.get('wink') and side == 1 and st in ('open', 'wide', 'half'):
            w_, h_ = ew * 1.9, eh * 0.42
            pts = [(ex - w_ / 2, ey + h_ / 2), (ex, ey - h_ / 2), (ex + w_ / 2, ey + h_ / 2)]
            d.line(pts, fill=col, width=lw, joint='curve')
            for px_, py_ in pts: d.ellipse((px_ - lw / 2, py_ - lw / 2, px_ + lw / 2, py_ + lw / 2), fill=col)
            continue
        if st in ('open', 'wide', 'half'):
            w_ = ew * (1.22 if st == 'wide' else 1.0); h_ = eh * (1.12 if st == 'wide' else 1.0)
            hh = h_ * (0.5 if st == 'half' else 1.0) * max(0.1, eo)
            y0 = ey + h_ / 2 - hh if st == 'half' else ey - hh / 2
            if hh < h_ * 0.16:  # closed line
                d.rounded_rectangle((ex - w_ * 0.75, ey - lw / 2, ex + w_ * 0.75, ey + lw / 2), lw // 2, fill=col)
                continue
            d.rounded_rectangle((ex - w_ / 2, y0, ex + w_ / 2, y0 + hh), int(min(w_, hh) * 0.28), fill=col)
            if hh > h_ * 0.4:
                gw, gh = w_ * 0.32, h_ * (0.17 if st != 'wide' else 0.2)
                gx, gy = ex + w_ * 0.08, y0 + h_ * 0.09
                d.rounded_rectangle((gx, gy, gx + gw, gy + gh), int(gw * 0.4), fill=(255, 255, 255))
                if st == 'wide':
                    d.ellipse((ex - w_ * 0.3, y0 + hh * 0.7, ex - w_ * 0.3 + gw * 0.7, y0 + hh * 0.7 + gw * 0.7), fill=(255, 255, 255))
        elif st == 'happy':      # ^ ^
            w_, h_ = ew * 1.9, eh * 0.42
            d.line([(ex - w_ / 2, ey + h_ / 2), (ex, ey - h_ / 2), (ex + w_ / 2, ey + h_ / 2)], fill=col, width=lw, joint='curve')
            for px_, py_ in ((ex - w_ / 2, ey + h_ / 2), (ex + w_ / 2, ey + h_ / 2), (ex, ey - h_ / 2)):
                d.ellipse((px_ - lw / 2, py_ - lw / 2, px_ + lw / 2, py_ + lw / 2), fill=col)
        elif st == 'sad':        # \  /  from the inside: the outer ends hang down
            w_, h_ = ew * 1.7, eh * 0.4
            pts = [(ex - side * w_ / 2, ey - h_ / 2), (ex + side * w_ / 2, ey + h_ / 2)]
            d.line(pts, fill=col, width=lw)
            for px_, py_ in pts: d.ellipse((px_ - lw / 2, py_ - lw / 2, px_ + lw / 2, py_ + lw / 2), fill=col)
        elif st == 'squeeze':    # >  <
            w_, h_ = ew * 1.6, eh * 0.62; s = -side
            pts = [(ex - s * w_ / 2, ey - h_ / 2), (ex + s * w_ / 2, ey), (ex - s * w_ / 2, ey + h_ / 2)]
            d.line(pts, fill=col, width=lw, joint='curve')
            for px_, py_ in pts: d.ellipse((px_ - lw / 2, py_ - lw / 2, px_ + lw / 2, py_ + lw / 2), fill=col)
        elif st in ('closed', 'flat'):
            w_ = ew * 1.7
            if st == 'flat':
                d.rounded_rectangle((ex - w_ / 2, ey - lw / 2, ex + w_ / 2, ey + lw / 2), lw // 2, fill=col)
            else:   # content arcs (u-shape)
                bb = (ex - w_ / 2, ey - w_ * 0.45, ex + w_ / 2, ey + w_ * 0.35)
                d.arc(bb, 20, 160, fill=col, width=lw)
        elif st == 'spiral':
            r0 = eh * 0.5; pts = []
            for i in range(60):
                a = i / 59 * 2.6 * 2 * math.pi; r = r0 * (0.12 + 0.88 * i / 59)
                pts.append((ex + r * math.cos(a * side), ey + r * math.sin(a * side)))
            d.line(pts, fill=col, width=max(2, int(lw * 0.7)), joint='curve')
        elif st == 'star':
            r = eh * 0.55
            d.polygon(star_poly(ex, ey, r, r * 0.45), fill=(255, 226, 110), outline=col)
            d.line(star_poly(ex, ey, r, r * 0.45) + [star_poly(ex, ey, r, r * 0.45)[0]], fill=col, width=max(2, lw // 2))
        elif st == 'dot':
            r = ew * 0.45; d.ellipse((ex - r, ey - r, ex + r, ey + r), fill=col)
    if P['blush'] > 0.01:
        a = int(110 * clamp(P['blush'], 0, 1)); ov = Image.new('RGBA', img.size, (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
        for side in (-1, 1):
            bx = cx0 + side * (EYE_X + 0.075 * BW) * k * sxw; by = cy0 + 0.1 * BH * k * (bh / BH)
            rw, rh = 0.06 * BW * k * sxw, 0.035 * BH * k
            od.ellipse((bx - rw, by - rh, bx + rw, by + rh), fill=(255, 140, 140, a))
        img.alpha_composite(ov)
    if P['glasses']:
        for side in (-1, 1):
            ex = cx0 + side * EYE_X * k * sxw; ey = cy0 + EYE_Y * k * (bh / BH); r = eh * 0.72
            d.ellipse((ex - r, ey - r, ex + r, ey + r), outline=(245, 242, 232), width=max(2, lw // 2))
        d.line([(cx0 - EYE_X * k * sxw + eh * 0.72, cy0 + EYE_Y * k * (bh / BH)), (cx0 + EYE_X * k * sxw - eh * 0.72, cy0 + EYE_Y * k * (bh / BH))],
               fill=(245, 242, 232), width=max(2, lw // 2))


def _prop_polys(kind, tip, d, k_ang, plen=150.0):
    """polygons (list of (pts, fill)) for a held prop at nub tip, direction d rotated by k_ang degrees"""
    a = math.atan2(-d[1], d[0]) + math.radians(k_ang)   # screen angle (up positive)
    ux, uy = math.cos(a), -math.sin(a); vx, vy = -uy, ux
    tx, ty = tip; out = []

    def rect(c0, c1, w, fill):  # rectangle from along-distance c0..c1, width w, centred on axis
        pts = [(tx + ux * c0 + vx * w / 2, ty + uy * c0 + vy * w / 2), (tx + ux * c1 + vx * w / 2, ty + uy * c1 + vy * w / 2),
               (tx + ux * c1 - vx * w / 2, ty + uy * c1 - vy * w / 2), (tx + ux * c0 - vx * w / 2, ty + uy * c0 - vy * w / 2)]
        out.append((pts, fill))
    if kind == 'pointer':
        L = max(60.0, plen)
        if L > 170:   # telescopic pointer: thinner inner segment
            rect(-10, 150, 11, (196, 150, 104)); rect(-10, 150, 4, (222, 182, 136))
            rect(146, L, 7, (206, 166, 120)); rect(146, L, 2.5, (232, 200, 160))
        else:
            rect(-10, L, 11, (196, 150, 104)); rect(-10, L, 4, (222, 182, 136))
        rect(L, L + 26, 12, (226, 72, 72))
    elif kind == 'chalk':
        rect(-4, 30, 12, (246, 243, 232)); rect(26, 30, 12, (225, 222, 210))
    elif kind == 'eraser':
        # block held perpendicular: centred on tip + small offset along axis
        cx_, cy_ = tx + ux * 22, ty + uy * 22
        for (o0, o1, fill) in ((-18, 4, (186, 134, 92)), (4, 18, (58, 58, 70))):
            pts = [(cx_ + ux * o0 + vx * 40, cy_ + uy * o0 + vy * 40), (cx_ + ux * o1 + vx * 40, cy_ + uy * o1 + vy * 40),
                   (cx_ + ux * o1 - vx * 40, cy_ + uy * o1 - vy * 40), (cx_ + ux * o0 - vx * 40, cy_ + uy * o0 - vy * 40)]
            out.append((pts, fill))
    return out


def render(P, sc, SS=2):
    """returns (sprite RGBA at output scale, (x0,y0) output-pixel position of its top-left)"""
    k = sc.s * SS
    g = geom(dict(P, tilt=0.0))  # unrotated geometry
    piv = tilt_pivot(P, g['bw'], g['feet'])
    # canvas window in logical coords
    xl, xr, yt, yb = P['x'] - 430, P['x'] + 430, FLOOR_Y - 700, FLOOR_Y + 40
    for key in ('L', 'R'):
        if P['prop' + key] == 'pointer':
            gk = geom(P); tx_, ty_ = gk['tip' + key]; L_ = P.get('plen', 150.0) + 40
            xl, xr = min(xl, tx_ - L_), max(xr, tx_ + L_); yt = min(yt, ty_ - L_)
    ox, oy = xl, yt
    Wc, Hc = int((xr - xl) * k), int((yb - yt) * k)
    cv = Image.new('RGBA', (Wc, Hc), (0, 0, 0, 0)); dr = ImageDraw.Draw(cv)
    T = lambda pts: [((px - ox) * k, (py - oy) * k) for px, py in rot_pts(pts, piv[0], piv[1], P['tilt'])]
    # shadow (not tilted, on the floor)
    shw = BW * 0.55 * (1 - clamp(P['lift'] / 260, 0, 0.6)); sha = int(70 * (1 - clamp(P['lift'] / 200, 0, 0.7)) * P.get('shadow', 1.0))
    for i, f_ in enumerate((1.0, 0.82, 0.62) if sha > 0 else ()):     # shadow < 1: the window itself is in the air
        dr.ellipse(((P['x'] - shw * f_ - ox) * k, (FLOOR_Y - 13 * f_ - oy) * k, (P['x'] + shw * f_ - ox) * k, (FLOOR_Y + 13 * f_ - oy) * k),
                   fill=(10, 8, 20, int(sha * (0.45 + 0.3 * i))))
    spin = P['spin']; bw, bh = g['bw'], g['bh']
    # legs
    ph = P['walk'] * 2 * math.pi; amp = P['walkamp']
    for i, fx in enumerate(LEG_X):
        lift = 0.0; dx = 0.0
        if amp > 0:
            s_ = math.sin(ph + (0 if i in (0, 2) else math.pi)); lift = max(0.0, s_) * 13 * amp; dx = math.cos(ph + (0 if i in (0, 2) else math.pi)) * 6 * amp
        lx = P['x'] + fx * bw + dx; top_ = g['bot'] - 6; bot_ = g['feet'] - lift
        dr.polygon(T(rrect_poly(lx, (top_ + bot_) / 2, LEG_W * max(0.3, abs(spin)) if abs(spin) < 1 else LEG_W, bot_ - top_, 6)), fill=LEG_COL)
        dr.polygon(T(rrect_poly(lx - LEG_W * 0.18, (top_ + bot_) / 2 - 2, LEG_W * 0.28, bot_ - top_ - 10, 3)), fill=LEG_HI)

    def nub(key):
        ang, ext = P['nub' + key]; d = g['dir' + key]; px, py = g['piv' + key]; L = NUB_L * ext
        c0, c1 = -18.0, L; cx_, cy_ = px + d[0] * (c0 + c1) / 2, py + d[1] * (c0 + c1) / 2
        a = math.degrees(math.atan2(-d[1], d[0]))
        dr.polygon(T(rrect_poly(cx_, cy_, c1 - c0, NUB_T * max(0.4, min(1, abs(spin) * 1.5)), 12, a)), fill=NUB_COL)
        # top highlight sliver
        hx, hy = cx_ + (-d[1]) * (-NUB_T * 0.28) * (1 if key == 'R' else -1), cy_ + d[0] * (-NUB_T * 0.28) * (1 if key == 'R' else -1)
        dr.polygon(T(rrect_poly(hx, hy, (c1 - c0) * 0.7, NUB_T * 0.16, 4, a)), fill=NUB_HI)
        if key == 'R' and P['thumbR']:
            tx_, ty_ = g['tipR']; perp = (d[1], -d[0]) if d[0] >= 0 else (-d[1], d[0])
            # thumb points "up" relative to the screen
            perp = (0.0, -1.0)
            dr.polygon(T(rrect_poly(tx_ - d[0] * 12 + perp[0] * 22, ty_ - d[1] * 12 + perp[1] * 30, 20, 34, 8, a)), fill=NUB_COL)
        if key == 'R' and P.get('fingersR', 0) > 0:
            n_ = min(5, int(P['fingersR'])); tx_, ty_ = g['tipR']; perp = (-d[1], d[0])
            for i_ in range(n_):
                off = (i_ - (n_ - 1) / 2) * 13.0; a_ = a + (i_ - (n_ - 1) / 2) * -9.0; r_ = math.radians(a_)
                cx_f, cy_f = tx_ + perp[0] * off + math.cos(r_) * 12, ty_ + perp[1] * off - math.sin(r_) * 12
                dr.polygon(T(rrect_poly(cx_f, cy_f, 44, 13, 5, a_)), fill=NUB_COL)
        prop = P['prop' + key]
        if prop:
            for pts, fill in _prop_polys(prop, g['tip' + key], d, P['propang' + key] * (1 if key == 'R' else -1), P.get('plen', 150.0)):
                dr.polygon(T(pts), fill=fill)
    if not P['frontL']: nub('L')
    if not P['frontR']: nub('R')
    # body with eyes, rotated as one image
    bwk, bhk = bw * k, bh * k
    tex = _body_texture(bwk, bhk, k, back=spin < 0)
    if spin > 0.25: _draw_eyes(tex, P, k, bw, bh)
    bcx, bcy = P['x'], (g['top'] + g['bot']) / 2
    if abs(P['tilt']) > 1e-3:
        tex = tex.rotate(P['tilt'], resample=Image.BICUBIC, expand=True)
        bcx, bcy = rot_pts([(bcx, bcy)], piv[0], piv[1], P['tilt'])[0]
    cv.alpha_composite(tex, (int(round((bcx - ox) * k - tex.size[0] / 2)), int(round((bcy - oy) * k - tex.size[1] / 2))))
    dr = ImageDraw.Draw(cv)
    if P['frontL']: nub('L')
    if P['frontR']: nub('R')
    bb = cv.getbbox()
    if bb is None: return Image.new('RGBA', (1, 1)), (0, 0)
    x0, y0, x1, y1 = bb; x0 -= x0 % SS; y0 -= y0 % SS
    x1 = min(Wc, x1 + (-x1) % SS); y1 = min(Hc, y1 + (-y1) % SS)
    cv = cv.crop((x0, y0, x1, y1))
    out = cv.resize((max(1, (x1 - x0) // SS), max(1, (y1 - y0) // SS)), Image.LANCZOS)
    return out, (int(round(ox * sc.s + x0 / SS)), int(round(oy * sc.s + y0 / SS)))


# ------------------------------------------------------------------ idle / talk layers
def blink_amount(t, seed=0):
    """eye openness 0..1 with a blink every ~3-5 s; about one blink in three is a double blink"""
    k = int(t // 4.0); start = k * 4.0 + 0.4 + 2.8 * hrand('blink', seed, k)
    for st_ in ((start, start + 0.3) if hrand('blink2', seed, k) < 0.33 else (start,)):
        u = (t - st_) / 0.16
        if 0 <= u <= 1: return abs(1 - 2 * u) ** 0.8
    return 1.0


# where a passing glance goes: board, up at the board, viewer's right, slightly up
GLANCES = ((-0.8, -0.45), (-0.55, -0.8), (0.5, 0.1), (-0.15, -0.6))


def apply_idle(P, t):
    br = math.sin(2 * math.pi * t / 3.3)
    P['sy'] *= 1 + 0.013 * br; P['sx'] *= 1 - 0.007 * br
    aL, eL = P['nubL']; aR, eR = P['nubR']
    P['nubL'] = (aL + 3 * math.sin(2 * math.pi * t / 3.3 + 0.6), eL); P['nubR'] = (aR + 3 * math.sin(2 * math.pi * t / 3.3 + 1.4), eR)
    if P['eyes'] in ('open', 'wide', 'half'):
        P['eye_open'] = min(P['eye_open'], blink_amount(t))
    gl = math.sin(2 * math.pi * t / 9.7) * math.sin(2 * math.pi * t / 4.1)
    lx, ly = P['look']; lx += 0.25 * gl
    # slow weight shift, so a long stretch never looks frozen
    P['tilt'] += 1.3 * math.sin(2 * math.pi * t / 8.3)
    # a short glance somewhere every ~6 s (pure function of t, like everything here)
    W = 6.3; k = int(t // W); st_ = k * W + 0.5 + 3.8 * hrand('glance', k); u = t - st_
    if 0 <= u <= 0.95:
        e = env_in_out(u, 0.95, 0.18, 0.22); gx, gy = GLANCES[int(hrand('glance2', k) * len(GLANCES))]
        lx += gx * e; ly += gy * e
    P['look'] = (lx, ly)
    # now and then a little shuffle of the feet
    if P['walkamp'] == 0:
        W = 10.7; k = int(t // W); st_ = k * W + 1.0 + 7.0 * hrand('shuffle', k); u = t - st_
        if 0 <= u <= 0.6:
            P['walk'] = u / 0.6; P['walkamp'] = 0.45 * bump(u, 0, 0.6)


# talking style by tone: (gesture size, constant head cock towards the board)
TALK_STYLE = {'兴奋': (1.35, 0.0), '强调': (1.1, 1.0), '鼓励': (1.15, -1.0), '轻松': (1.05, -0.6), '提问': (1.0, 2.6), '讲解': (0.9, 0.0), '提醒': (0.85, 0.8), '总结': (0.8, 0.0)}


def apply_talk(P, env, env_slow, t, gestures=1.0, tone=None):
    """gestures: 0..1 weight (engine fades it around actions so the arms do not jump when an action starts or ends)"""
    P['lift'] += 7 * env
    P['sy'] *= 1 + 0.035 * env; P['sx'] *= 1 - 0.018 * env
    if gestures > 0:
        amp, cock = TALK_STYLE.get(tone, (1.0, 0.0)); on = min(1.0, env_slow * 2.2) * gestures; env_slow = env_slow * gestures
        aL, eL = P['nubL']; aR, eR = P['nubR']
        P['nubR'] = (aR + 6 * gestures + amp * 26 * env_slow * (0.6 + 0.4 * math.sin(2 * math.pi * t / 2.3)), eR)
        P['nubL'] = (aL + 3 * gestures + amp * 14 * env_slow * (0.5 + 0.5 * math.sin(2 * math.pi * t / 3.1 + 1.0)), eL)
        # gesture phrases: every 2.7 s pick one, cross-faded through neutral so it never pops
        W = 2.7; k = int(t // W); ph = t - k * W; w = env_in_out(ph, W, 0.45, 0.45) * on * amp; kind = int(hrand('talk', k) * 5)
        aL, eL = P['nubL']; aR, eR = P['nubR']; lx, ly = P['look']
        if kind == 1:      # both nubs open
            aR += 16 * w; aL += 12 * w; eR *= 1 + 0.06 * w; eL *= 1 + 0.04 * w
        elif kind == 2:    # right nub beats
            aR += 24 * w * (0.65 + 0.35 * math.sin(2 * math.pi * t / 0.85)); eR *= 1 + 0.08 * w
        elif kind == 3:    # lean towards the board
            P['tilt'] += 2.4 * w; lx -= 0.4 * w; ly -= 0.2 * w
        elif kind == 4:    # lean back, towards the viewer
            P['tilt'] -= 2.2 * w; aR += 10 * w
        P['tilt'] += cock * on
        P['nubL'] = (aL, eL); P['nubR'] = (aR, eR); P['look'] = (lx, ly)


# ------------------------------------------------------------------ action library
# Each action: fn(P, u, D, ctx) -> list of fx tuples. u = seconds since start, D = duration.
# ctx: dict with optional 'target' (x,y), 'side' (-1/+1), 'text', 'x0','x1' (walk), 'board_pt'.
ACTIONS = {}


def action(name, dur, sfx=None, desc='', feel='', talk_ok=True):
    def deco(fn):
        ACTIONS[name] = dict(fn=fn, dur=dur, sfx=sfx or [], desc=desc, feel=feel, talk_ok=talk_ok); return fn
    return deco


def _side_to(P, target):
    return 1 if target[0] >= P['x'] else -1


def _aim(P, side, target, lo=-40, hi=80):
    g = geom(P); px, py = g['pivR' if side > 0 else 'pivL']
    dx, dy = abs(target[0] - px), py - target[1]
    return clamp(math.degrees(math.atan2(dy, max(1.0, dx))), lo, hi)


def walk_pose(P, u, D, x0, x1):
    e = smooth(u / D) if D > 0 else 1.0
    P['x'] = lerp(x0, x1, e)
    dist = abs(P['x'] - x0); P['walk'] = dist / 130.0
    sp = (smooth(min(1, (u + 1e-3) / D)) - smooth(max(0, (u - 0.05)) / D)) if D > 0 else 0
    P['walkamp'] = clamp(env_in_out(u, D, 0.12, 0.12) * 1.0, 0, 1)
    P['lift'] += 5 * abs(math.sin(math.pi * P['walk'])) * P['walkamp']
    dirn = 1 if x1 >= x0 else -1
    P['tilt'] += -3.5 * dirn * P['walkamp']
    P['look'] = (0.85 * dirn * P['walkamp'], 0.0)
    P['nubL'] = (P['nubL'][0] + 12 * math.sin(2 * math.pi * P['walk']) * P['walkamp'], P['nubL'][1])
    P['nubR'] = (P['nubR'][0] - 12 * math.sin(2 * math.pi * P['walk']) * P['walkamp'], P['nubR'][1])


@action('enter_walk', 2.2, desc='从画面外走进来', feel='有人来上课了')
def a_enter(P, u, D, ctx):
    walk_pose(P, u, D, ctx.get('x0', -260), ctx.get('x1', 1690)); return []


@action('exit_walk', 2.2, desc='走出画面', feel='下课了')
def a_exit(P, u, D, ctx):
    walk_pose(P, u, D, ctx.get('x0', 1690), ctx.get('x1', 2200)); return []


@action('walk_to', 1.0, desc='走到某个位置（四条腿交替+上下颠）', feel='老师换个位置讲')
def a_walk(P, u, D, ctx):
    walk_pose(P, u, D, ctx['x0'], ctx['x1']); return []


@action('idle', 3.0, desc='待机呼吸、眨眼、左右看', feel='放松')
def a_idle(P, u, D, ctx):
    return []


@action('talk', 3.0, desc='说话：音量包络驱动弹跳和手势', feel='它在跟我说话')
def a_talk(P, u, D, ctx):
    return []


def aim_left(P, target, ext=1.25):
    """nub-L angle and pointer length so that the pointer tip lands on target (logical coords)."""
    P2 = dict(P); P2['nubL'] = (P['nubL'][0], ext); P2['tilt'] = 0.0; g = geom(P2); px, py = g['pivL']
    # the whole sprite is rotated by tilt around the feet when drawn, so aim at the un-rotated target
    target = rot_pts([target], P['x'], g['feet'], -P['tilt'])[0]
    dx, dy = target[0] - px, target[1] - py
    ang = math.degrees(math.atan2(-dy, -dx))          # L nub direction = (-cos a, -sin a)
    ang = clamp(ang, -30, 95)
    r = math.hypot(dx, dy); L = clamp(r - NUB_L * ext - 6 - 22, 110, 1200)
    return ang, L


@action('point_at', 2.0, desc='用常驻的教棍（可伸缩）指向黑板目标', feel='看这里')
def a_point(P, u, D, ctx):
    tgt = ctx['target']; e = env_in_out(u, D, 0.3, 0.35)
    P['tilt'] += 2.5 * e
    ang, L = aim_left(P, tgt)
    a0, e0 = P['nubL']
    P['nubL'] = (lerp(a0, ang, e), lerp(e0, 1.25, e)); P['propangL'] = lerp(REST_PANG, 0.0, e)
    P['plen'] = lerp(150.0, L, e)
    P['look'] = (-0.9 * e, -0.6 * e)
    if 0.45 < u < 0.85:       # little double tap
        P['plen'] += 10 * math.sin((u - 0.45) / 0.2 * math.pi) ** 2 * e
    return []


@action('knock_board', 1.7, sfx=[(0.40, 'knock'), (0.64, 'knock'), (0.88, 'knock'), (1.06, 'pop')],
        desc='敲黑板！教棍对准重点、蓄力、咚咚咚三下（冲击圈、粉笔灰、“敲黑板！重点！”印章、聚光）',
        feel='注意，这句是重点')
def a_knock(P, u, D, ctx):
    tap = ctx['tap']; fx = []
    taps = (0.40, 0.64, 0.88)
    e = smooth(u / 0.25) * (1 - smooth((u - 1.25) / 0.4))
    P['tilt'] += 3 * e
    ang, L = aim_left(P, tap, 1.2)
    a0, e0 = P['nubL']
    hit = max(bump(u, tp - 0.09, tp + 0.07) for tp in taps) if u < 1.05 else 0.0
    P['nubL'] = (lerp(a0, ang + 4 * hit, e), lerp(e0, 1.2, e)); P['propangL'] = lerp(REST_PANG, 0.0, e)
    P['plen'] = lerp(150.0, L - 8 + 22 * hit, e)
    P['look'] = (-0.9 * e, -0.6 * e)
    P['eyes'] = 'squeeze' if hit > 0.25 else 'open'
    P['sx'] *= 1 + 0.03 * hit; P['sy'] *= 1 - 0.03 * hit
    if u > 1.05: P['lift'] += 10 * bump(u, 1.05, 1.4)
    for tp in taps:
        if tp <= u < tp + 0.6: fx.append(('impact', u - tp, tap))
    if u >= 1.0: fx.append(('stamp', u - 1.0))
    return fx


@action('write_on_board', 1.5, sfx=[(0.0, 'chalk')], desc='举起粉笔在黑板上写字/画图（够不着就小跳）', feel='老师在写板书')
def a_write(P, u, D, ctx):
    tgt = ctx.get('target', (P['x'] - 300, 400)); side = 1; key = 'R'
    e = env_in_out(u, D, 0.2, 0.25)
    ang = 55.0
    P['nub' + key] = (lerp(P['nub' + key][0], ang + 4 * math.sin(2 * math.pi * 5.5 * u), e), lerp(1.0, 1.3, e))
    P['prop' + key] = 'chalk' if e > 0.05 else None
    P['look'] = (-0.8 * e, -0.7 * e); P['tilt'] += 2.0 * e
    if tgt[1] < 420:
        P['lift'] += 16 * abs(math.sin(2 * math.pi * 1.3 * u)) * e
    return []


@action('draw_diagram', 2.0, sfx=[(0.0, 'chalk')], desc='在黑板上一笔一笔画示意图', feel='一步步搭出来')
def a_draw(P, u, D, ctx):
    return a_write(P, u, D, ctx)


@action('think', 2.0, desc='想一想：眼睛半眯看左上，小手托“下巴”，冒出思考泡泡', feel='先别急，想一想')
def a_think(P, u, D, ctx):
    e = env_in_out(u, D, 0.35, 0.3)
    P['eyes'] = 'half' if e > 0.4 else P['eyes']; P['look'] = (-0.8 * e, -0.9 * e); P['tilt'] += 5 * e
    P['nubR'] = (lerp(P['nubR'][0], 150, e), lerp(1.0, 0.95, e)); P['frontR'] = e > 0.5
    return [('bubble', u, ctx.get('text', '…'), e)]


@action('aha', 1.3, sfx=[(0.2, 'ding')], desc='恍然大悟：跳起来、眼睛睁大、头上亮灯泡和感叹号', feel='原来如此！')
def a_aha(P, u, D, ctx):
    k_ = bump(u, 0.0, 0.3); P['sy'] *= 1 - 0.1 * k_; P['sx'] *= 1 + 0.06 * k_
    j = bump(u, 0.15, 0.7); P['lift'] += 60 * j
    P['eyes'] = 'wide'; e = env_in_out(u, D, 0.15, 0.3)
    P['nubL'] = (lerp(P['nubL'][0], 60, e), 1.1); P['nubR'] = (lerp(P['nubR'][0], 60, e), 1.1)
    if 0.7 < u < 0.85: P['sy'] *= 1 - 0.06 * bump(u, 0.7, 0.85)
    return [('bulb', u)]


@action('confused', 2.0, desc='困惑：歪头、蚊香眼、冒问号、流汗', feel='这里确实容易晕')
def a_confused(P, u, D, ctx):
    e = env_in_out(u, D, 0.3, 0.3)
    P['tilt'] += 7 * math.sin(2 * math.pi * u / 1.6) * e; P['eyes'] = 'spiral' if e > 0.3 else P['eyes']
    P['nubL'] = (lerp(P['nubL'][0], 25, e), 1.0); P['nubR'] = (lerp(P['nubR'][0], 25, e), 1.0)
    return [('qmarks', u, e), ('sweat', u, e)]


@action('shrug_sweat', 1.8, desc='摊手流汗：这部分有点难', feel='难点被老实承认了')
def a_shrug(P, u, D, ctx):
    e = env_in_out(u, D, 0.3, 0.3)
    P['nubL'] = (lerp(P['nubL'][0], 42, e), lerp(1, 1.15, e)); P['nubR'] = (lerp(P['nubR'][0], 42, e), lerp(1, 1.15, e))
    P['sy'] *= 1 - 0.05 * e; P['sx'] *= 1 + 0.03 * e; P['eyes'] = 'flat' if e > 0.4 else P['eyes']; P['look'] = (0, 0.4 * e)
    P['lift'] += 6 * bump(u, 0.2, 0.5)
    return [('sweat', u, e)]


@action('nod', 1.0, desc='点头（身体上下点两下，眯眼笑）', feel='对，就是这样')
def a_nod(P, u, D, ctx):
    d = bump(u, 0.05, 0.4) + bump(u, 0.45, 0.8)
    P['sy'] *= 1 - 0.06 * d; P['sx'] *= 1 + 0.03 * d; P['look'] = (P['look'][0], 0.6 * d)
    P['eyes'] = 'happy' if 0.05 < u < 0.85 else P['eyes']; return []


@action('thumbs_up', 1.5, sfx=[(0.25, 'sparkle')], desc='竖大拇指 + 粉笔对勾', feel='做得好 / 这样就对了')
def a_thumbs(P, u, D, ctx):
    e = env_in_out(u, D, 0.2, 0.3)
    P['nubR'] = (lerp(P['nubR'][0], 35, e), lerp(1.0, 1.2, e)); P['thumbR'] = e > 0.4
    P['eyes'] = 'happy' if e > 0.4 else P['eyes']; P['blush'] = max(P['blush'], e); P['tilt'] += -4 * e
    return [('check', u)]


@action('celebrate', 2.2, sfx=[(0.15, 'pop'), (0.35, 'sparkle')], desc='庆祝：跳起转圈、星星眼、粉笔彩屑', feel='太棒了，你做到了！')
def a_celebrate(P, u, D, ctx):
    j = bump(u, 0.1, 0.95); P['lift'] += 85 * j
    if 0.2 < u < 0.85: P['spin'] = math.cos(2 * math.pi * (u - 0.2) / 0.65)
    e = env_in_out(u, D, 0.15, 0.4)
    P['nubL'] = (lerp(P['nubL'][0], 70, e), 1.15); P['nubR'] = (lerp(P['nubR'][0], 70, e), 1.15)
    P['eyes'] = 'star'; P['blush'] = e
    if u > 0.95: P['sy'] *= 1 - 0.07 * bump(u, 0.95, 1.15)
    return [('confetti', u)]


@action('quiz_ask', 3.6, desc='提问：歪头、举手等你，黑板上 3 秒倒计时，再揭晓答案', feel='轮到我动脑了')
def a_quiz(P, u, D, ctx):
    e = env_in_out(u, D, 0.3, 0.3)
    P['look'] = (0, 0); P['tilt'] += 8 * e; P['eyes'] = 'open'
    P['nubR'] = (lerp(P['nubR'][0], 75 + 6 * math.sin(2 * math.pi * u / 1.3), e), lerp(1.0, 1.2, e))
    P['look'] = (-0.3 * math.sin(2 * math.pi * u / 3.0) * e, -0.2 * e)
    return []


@action('erase_board', 1.4, sfx=[(0.05, 'whoosh'), (0.6, 'whoosh')], desc='拿板擦大幅擦黑板（粉笔灰+呼呼声），用作换板过场', feel='翻篇，下一块黑板')
def a_erase(P, u, D, ctx):
    e = env_in_out(u, D, 0.15, 0.2)
    sw = math.sin(2 * math.pi * 2.0 * u)
    P['nubR'] = (lerp(P['nubR'][0], 50 + 30 * sw, e), lerp(1.0, 1.35, e)); P['propR'] = None
    P['look'] = (0.6 * e, -0.7 * e); P['eyes'] = 'squeeze' if 0.2 < u < D - 0.2 else 'open'
    P['lift'] += 8 * abs(sw) * e; P['tilt'] += -3 * sw * e
    return []


@action('wave', 1.6, desc='挥手打招呼/再见', feel='友好')
def a_wave(P, u, D, ctx):
    e = env_in_out(u, D, 0.2, 0.3)
    P['nubR'] = (lerp(P['nubR'][0], 70 + 22 * math.sin(2 * math.pi * 2.2 * u), e), lerp(1.0, 1.15, e))
    P['eyes'] = 'happy' if e > 0.4 else P['eyes']; P['blush'] = e * 0.8; P['tilt'] += -4 * e; return []


@action('listen', 2.0, desc='听同学提问：转向左下（画外的同学）、歪头、右手拢在“耳边”，最后轻轻点一下头；不说话、不弹跳',
        feel='嗯，你问得好，我在听')
def a_listen(P, u, D, ctx):
    # engine adds this automatically for shots with speaker "student"; D = the student's line + a little
    e = env_in_out(u, D, 0.3, 0.35)
    P['look'] = (-0.75 * e, 0.3 * e); P['tilt'] += 7 * e; P['eyes'] = 'open'
    P['nubR'] = (lerp(P['nubR'][0], 112, e), lerp(1.0, 0.92, e)); P['frontR'] = e > 0.5
    d = bump(u, max(0.0, D - 0.75), max(0.05, D - 0.25))     # a small nod as the question ends
    P['sy'] *= 1 - 0.05 * d; P['sx'] *= 1 + 0.025 * d
    return []


@action('look_at_viewer', 1.0, desc='看向观众', feel='在跟我说')
def a_look(P, u, D, ctx):
    e = env_in_out(u, D, 0.15, 0.2)
    P['look'] = (P['look'][0] * (1 - e), P['look'][1] * (1 - e)); P['sy'] *= 1 + 0.025 * e; P['sx'] *= 1 - 0.012 * e; P['tilt'] *= 1 - e
    P['nubR'] = (lerp(P['nubR'][0], 25, e), P['nubR'][1])
    return []


@action('hop', 0.8, sfx=[(0.1, 'pop')], desc='开心小跳（数字上涨时，头顶飘出 +x%）', feel='又进步了！')
def a_hop(P, u, D, ctx):
    P['sy'] *= 1 - 0.08 * bump(u, 0.0, 0.2)
    P['lift'] += 38 * bump(u, 0.1, 0.55); P['eyes'] = 'happy'; P['blush'] = 0.7
    P['nubL'] = (P['nubL'][0] + 30 * bump(u, 0.05, 0.6), 1.05); P['nubR'] = (P['nubR'][0] + 30 * bump(u, 0.05, 0.6), 1.05)
    return [('float_text', u, ctx.get('text', ''))] if ctx.get('text') else []


# gaps filled 2026-11-04 (no sound effects on purpose, they stay sparse; none of these leaves the safe area)
@action('lean_board', 2.0, desc='身体朝黑板探过去看，右手往后撑；能和教棍同时用', feel='我也凑近看看')
def a_lean(P, u, D, ctx):
    e = env_in_out(u, D, 0.35, 0.35)
    P['tilt'] += 8 * e; P['look'] = (lerp(P['look'][0], -0.9, e), lerp(P['look'][1], -0.5, e))
    P['nubR'] = (lerp(P['nubR'][0], -25, e), lerp(P['nubR'][1], 0.9, e)); P['sy'] *= 1 + 0.015 * e
    return []


@action('surprised', 1.1, desc='吓一跳：一缩、一蹦、眼睛睁大、双手一扬、旁边一个“！”', feel='哇，这么多！')
def a_surprised(P, u, D, ctx):
    k_ = bump(u, 0.0, 0.16); P['sy'] *= 1 - 0.08 * k_; P['sx'] *= 1 + 0.05 * k_
    j = bump(u, 0.07, 0.5); P['lift'] += 42 * j; P['sy'] *= 1 + 0.06 * j; P['sx'] *= 1 - 0.03 * j
    e = env_in_out(u, D, 0.08, 0.35)
    if u < D - 0.2: P['eyes'] = 'wide'
    P['nubL'] = (lerp(P['nubL'][0], 62, e), lerp(P['nubL'][1], 1.1, e)); P['nubR'] = (lerp(P['nubR'][0], 62, e), lerp(P['nubR'][1], 1.1, e))
    P['look'] = (P['look'][0] * (1 - e), P['look'][1] * (1 - e))
    return [('exclaim', u, D)]


@action('count_fingers', lambda ctx: 0.5 + 0.8 * (ctx.get('n', 3) - ctx.get('from', 1) + 1),
        desc='右手举起来数数，一个节拍多伸一根手指，旁边飘数字。n 数到几，from 从几开始（默认 1）；一二三分散在一句里时写多条，from=n', feel='第一、第二、第三')
def a_count(P, u, D, ctx):
    n = int(ctx.get('n', 3)); n0 = int(ctx.get('from', 1)); e = env_in_out(u, D, 0.2, 0.25)
    steps = max(1, n - n0 + 1); stepd = max(0.2, (D - 0.5) / steps); i = int(clamp((u - 0.15) / stepd, 0, steps - 1)); cur = n0 + i
    uu = u - 0.15 - i * stepd; beat = bump(uu, 0, 0.38) if uu >= 0 else 0.0
    ang = clamp(50 + (P['x'] - 1560) * 0.13, 50, 68)   # near the right edge of the canvas the hand stays higher
    P['nubR'] = (lerp(P['nubR'][0], ang + 7 * beat, e), lerp(P['nubR'][1], 1.14 + 0.05 * beat, e * e)); P['frontR'] = False
    P['fingersR'] = cur if e > 0.7 else 0; P['sy'] *= 1 - 0.018 * beat; P['tilt'] += -2.5 * e
    P['look'] = (lerp(P['look'][0], 0.35, e), lerp(P['look'][1], -0.25, e))
    return [('digit', max(0.0, uu), cur, e)] if e > 0.2 else []


@action('tiptoe_peek', 1.6, desc='踮起脚看黑板上面：腿伸长、身子拉高、眼睛往左上看，会比平时高约 35 像素', feel='上面写的什么？')
def a_tiptoe(P, u, D, ctx):
    e = env_in_out(u, D, 0.3, 0.3)
    P['legx'] = 28 * e + 2.5 * e * math.sin(2 * math.pi * u / 0.55); P['sy'] *= 1 + 0.04 * e; P['sx'] *= 1 - 0.022 * e
    P['look'] = (lerp(P['look'][0], -0.8, e), lerp(P['look'][1], -0.95, e))
    P['nubR'] = (lerp(P['nubR'][0], -12, e), P['nubR'][1])
    return []


@action('head_tilt', 1.2, desc='歪一下头、看着观众（side=1 往黑板那边歪）', feel='嗯？你说呢？')
def a_head_tilt(P, u, D, ctx):
    e = env_in_out(u, D, 0.22, 0.3)
    P['tilt'] += ctx.get('side', -1) * 7.5 * e; P['look'] = (P['look'][0] * (1 - e), lerp(P['look'][1], -0.15, e))
    P['nubR'] = (lerp(P['nubR'][0], 26, e), P['nubR'][1])
    return []


@action('wink', 1.1, desc='冲观众眨一只眼，小小歪头，脸有点红', feel='悄悄告诉你')
def a_wink(P, u, D, ctx):
    e = env_in_out(u, D, 0.18, 0.25)
    P['wink'] = 0.22 < u < D - 0.22; P['tilt'] += -4.5 * e; P['blush'] = max(P['blush'], 0.75 * e)
    P['look'] = (P['look'][0] * (1 - e), P['look'][1] * (1 - e)); P['nubR'] = (lerp(P['nubR'][0], 48, e), P['nubR'][1])
    return []


@action('answer_react', 1.3, desc='听完同学提问后的反应：转回来看观众，小蹦一下，右手抬起，眯眼笑', feel='好问题，我来答')
def a_answer(P, u, D, ctx):
    e = env_in_out(u, D, 0.25, 0.3)
    P['look'] = (-0.6 * bump(u, 0.0, 0.6), 0.0)
    P['eyes'] = 'happy' if 0.28 < u < D - 0.25 else P['eyes']; P['lift'] += 17 * bump(u, 0.12, 0.5); P['blush'] = max(P['blush'], 0.5 * e)
    P['nubR'] = (lerp(P['nubR'][0], 64 + 9 * math.sin(2 * math.pi * u / 0.6), e), lerp(P['nubR'][1], 1.18, e)); P['tilt'] += -3.5 * e
    return []


@action('beat', 1.2, desc='右手连压两下强调（说到重点时用，比敲黑板轻得多）', feel='这句记一下')
def a_beat(P, u, D, ctx):
    e = env_in_out(u, D, 0.2, 0.25); k_ = D / 1.2
    chop = bump(u, 0.25 * k_, 0.52 * k_) + bump(u, 0.62 * k_, 0.9 * k_)
    P['nubR'] = (lerp(P['nubR'][0], 60 - 36 * chop, e), lerp(P['nubR'][1], 1.15, e))
    P['sy'] *= 1 - 0.03 * chop; P['sx'] *= 1 + 0.015 * chop; P['tilt'] += 1.8 * chop
    P['look'] = (P['look'][0] * (1 - e), lerp(P['look'][1], 0.12, e))
    return []


@action('shake_head', 1.2, desc='摇头：眼睛和身子左右摆（“不是”“不能”）', feel='不对，不是这样')
def a_shake(P, u, D, ctx):
    e = env_in_out(u, D, 0.15, 0.25); sw = math.sin(2 * math.pi * 2.0 * u / max(0.5, D / 1.2))
    P['look'] = (0.85 * sw * e, 0.05); P['tilt'] += 4.5 * sw * e
    P['sx'] *= 1 - 0.012 * abs(sw) * e; P['nubR'] = (lerp(P['nubR'][0], 5, e), P['nubR'][1])
    return []


@action('proud', 1.8, desc='双手叉腰、挺胸、满足地眯眼（“一句话”收尾、讲完一节）', feel='这一关拿下了')
def a_proud(P, u, D, ctx):
    e = env_in_out(u, D, 0.3, 0.3)
    P['nubL'] = (lerp(P['nubL'][0], -32, e), lerp(P['nubL'][1], 0.72, e)); P['nubR'] = (lerp(P['nubR'][0], -32, e), lerp(P['nubR'][1], 0.72, e))
    P['propangL'] = lerp(P['propangL'], -35, e); P['sy'] *= 1 + 0.035 * e; P['sx'] *= 1 - 0.018 * e; P['lift'] += 7 * bump(u, 0.15, 0.55)
    P['look'] = (P['look'][0] * (1 - e), P['look'][1] * (1 - e))
    if 0.25 * D < u < 0.82 * D: P['eyes'] = 'closed'
    return []


@action('present', 1.6, desc='左手连教棍朝黑板一摆（不伸长、不越过板书）', feel='请看黑板')
def a_present(P, u, D, ctx):
    e = env_in_out(u, D, 0.3, 0.35)
    P['nubL'] = (lerp(P['nubL'][0], 34, e), lerp(P['nubL'][1], 1.18, e)); P['propangL'] = lerp(P['propangL'], -22, e)
    P['tilt'] += 4.5 * e; P['look'] = (lerp(P['look'][0], -0.85, e), lerp(P['look'][1], -0.45, e))
    P['nubR'] = (lerp(P['nubR'][0], 4, e), P['nubR'][1])
    return []


# what counts as "reacting" in the first moments of the answer after a student's line (build.py check)
REACTIONS = {'answer_react', 'aha', 'surprised', 'nod', 'thumbs_up', 'head_tilt', 'shake_head', 'wink', 'hop', 'beat'}
# walk_to stays inside this x range: left of it Clawd would stand on the level chip, right of it past the home spot
WALK_MIN, WALK_MAX = 860.0, 1700.0
WALK_SPEED = 360.0


def action_dur(name, ctx=None):
    d = ACTIONS[name]['dur']
    return d(ctx or {}) if callable(d) else d


# ------------------------------------------------------------------ fx drawn around Clawd
def draw_fx(img, sc, P, fxs, t):
    """fx tuples produced by actions; drawn in output pixels on img (RGBA)."""
    if not fxs: return
    g = geom(P); d = ImageDraw.Draw(img)
    S = sc.f
    Wi = lambda v: max(1, int(round(sc.f(v))))
    hx, hy = g['head']
    for fx in fxs:
        kind = fx[0]
        if kind == 'bubble':
            _, u, text, e = fx
            if e < 0.05: continue
            bx, by = min(hx + 85, LW - 130), hy - 40
            s_ = ease_out_back(min(1, u / 0.35))
            r = 34 * s_
            for (ox_, oy_, rr) in ((-30, 34, 7), (-14, 22, 10)):
                cx_, cy_ = bx + ox_ * s_, by + oy_ * s_; d.ellipse((S(cx_ - rr), S(cy_ - rr), S(cx_ + rr), S(cy_ + rr)), fill=(250, 248, 240))
            d.rounded_rectangle((S(bx - r * 1.5), S(by - r * 0.8), S(bx + r * 1.5), S(by + r * 0.8)), S(r * 0.7), fill=(250, 248, 240))
            if text == '…':
                n = int((u * 3) % 4)
                for i in range(n):
                    cx_ = bx - 20 + i * 20; d.ellipse((S(cx_ - 7), S(by - 7), S(cx_ + 7), S(by + 7)), fill=(60, 60, 70))
            else:
                f = font('yaheib', S(38)); tw = d.textlength(text, font=f)
                d.text((S(bx) - tw / 2, S(by - 26)), text, font=f, fill=(60, 60, 70))
        elif kind == 'qmarks':
            _, u, e = fx
            for i in range(3):
                ph = (u * 0.7 + i / 3) % 1.0; a = int(255 * e * bump(ph, 0, 1))
                if a < 10: continue
                qx = hx + (-110 + 110 * i); qy = hy - 30 - 120 * ph
                f = font('kai', S(64 - 8 * i)); d.text((S(qx), S(qy)), '?', font=f, fill=CH['b'] + (a,), stroke_width=Wi(2), stroke_fill=CH['b'] + (a,))
        elif kind == 'sweat':
            _, u, e = fx
            if e < 0.1: continue
            sx_ = g['x'] + g['bw'] / 2 - 30; sy_ = g['top'] + 25 + 18 * ((u * 0.8) % 1.0)
            a = int(230 * e)
            d.polygon([(S(sx_), S(sy_ - 26)), (S(sx_ - 13), S(sy_ + 4)), (S(sx_ + 13), S(sy_ + 4))], fill=(150, 210, 255, a))
            d.ellipse((S(sx_ - 13), S(sy_ - 9), S(sx_ + 13), S(sy_ + 17)), fill=(150, 210, 255, a))
            d.ellipse((S(sx_ - 6), S(sy_ - 2), S(sx_), S(sy_ + 5)), fill=(240, 250, 255, a))
        elif kind == 'bulb':
            _, u = fx
            if u < 0.15: continue
            s_ = ease_out_back(min(1, (u - 0.15) / 0.25)); a = int(255 * min(1, (1.3 - u) / 0.3)) if u > 1.0 else 255
            bx, by = hx + 10, hy - 105
            r = 38 * s_
            for i in range(8):
                ang = i * math.pi / 4 + 0.2; r0, r1 = r * 1.35, r * 1.35 + 26 * s_
                d.line([(S(bx + r0 * math.cos(ang)), S(by + r0 * math.sin(ang))), (S(bx + r1 * math.cos(ang)), S(by + r1 * math.sin(ang)))], fill=(255, 220, 90, a), width=Wi(7))
            d.ellipse((S(bx - r), S(by - r), S(bx + r), S(by + r)), fill=(255, 226, 110, a))
            d.rectangle((S(bx - r * 0.45), S(by + r * 0.75), S(bx + r * 0.45), S(by + r * 1.25)), fill=(190, 190, 200, a))
            f = font('yaheib', S(44 * s_ + 1)); d.text((S(bx - 8 * s_), S(by - 30 * s_)), '!', font=f, fill=(200, 90, 40, a))
        elif kind == 'confetti':
            _, u = fx
            cols = [CH['y'], CH['p'], CH['b'], CH['g'], CH['o'], CH['w']]
            for i in range(46):
                r1, r2, r3 = hrand('cf', i, 1), hrand('cf', i, 2), hrand('cf', i, 3)
                vx = (r1 - 0.5) * 900; vy = -500 - 500 * r2
                tt = u - 0.12
                if tt < 0: continue
                px_ = hx + vx * tt; py_ = hy - 40 + vy * tt + 900 * tt * tt
                a = int(255 * clamp((D_CONF - tt) / 0.6, 0, 1))
                if a < 8: continue
                ang = tt * (6 + 10 * r3); w_, h_ = 16, 8
                pts = rrect_poly(px_, py_, w_, h_, 2, math.degrees(ang))
                d.polygon([(S(x), S(y)) for x, y in pts], fill=cols[i % len(cols)] + (a,))
        elif kind == 'check':
            _, u = fx
            if u < 0.2: continue
            p = clamp((u - 0.2) / 0.35, 0, 1); cx_, cy_ = min(g['tipR'][0] + 90, LW - 62), g['tipR'][1] - 110
            pts = [(cx_ - 40, cy_), (cx_ - 12, cy_ + 32), (cx_ + 46, cy_ - 40)]
            L1 = math.dist(pts[0], pts[1]); L2 = math.dist(pts[1], pts[2]); L = (L1 + L2) * p
            seg = [pts[0]]
            if L <= L1: seg.append((lerp(pts[0][0], pts[1][0], L / L1), lerp(pts[0][1], pts[1][1], L / L1)))
            else:
                seg.append(pts[1]); q = (L - L1) / L2; seg.append((lerp(pts[1][0], pts[2][0], q), lerp(pts[1][1], pts[2][1], q)))
            d.line([(S(x), S(y)) for x, y in seg], fill=CH['g'] + (255,), width=Wi(12), joint='curve')
        elif kind == 'countdown':
            _, u, filled, e = fx
            if e < 0.05: continue
            bx, by = hx + 190, hy - 110
            s_ = ease_out_back(min(1, u / 0.35))
            w_, h_ = 230 * s_, 120 * s_
            d.polygon([(S(bx - 80), S(by + 40)), (S(bx - 125), S(by + 95)), (S(bx - 40), S(by + 50))], fill=(250, 248, 240))
            d.rounded_rectangle((S(bx - w_ / 2), S(by - h_ / 2), S(bx + w_ / 2), S(by + h_ / 2)), S(30 * s_), fill=(250, 248, 240))
            f = font('yaheib', S(40 * s_ + 1)); tx = '想一想？'; tw = d.textlength(tx, font=f)
            d.text((S(bx) - tw / 2, S(by - 48 * s_)), tx, font=f, fill=(70, 60, 80))
            for i in range(3):
                cx_ = bx - 44 + 44 * i; cy_ = by + 30 * s_; r = 12 * s_
                if i < filled: d.ellipse((S(cx_ - r), S(cy_ - r), S(cx_ + r), S(cy_ + r)), fill=(217, 119, 87))
                else: d.ellipse((S(cx_ - r), S(cy_ - r), S(cx_ + r), S(cy_ + r)), outline=(170, 160, 170), width=Wi(4))
        elif kind == 'zz':
            _, u, e = fx
            for i in range(2):
                ph = (u * 0.6 + i * 0.5) % 1.0; a = int(230 * e * bump(ph, 0, 1))
                if a < 10: continue
                f = font('kai', S(46 - 10 * i)); d.text((S(hx + 120 + 40 * ph), S(hy - 40 - 90 * ph)), '~' if i == 0 else 'z', font=f, fill=CH['w'] + (a,))
        elif kind == 'float_text':
            _, u, text = fx
            a = int(255 * clamp((0.8 - u) / 0.3, 0, 1) if u > 0.5 else 255)
            f = font('kai', S(60)); tw = d.textlength(text, font=f)
            d.text((S(hx) - tw / 2, S(hy - 90 - 80 * ease_out(u / 0.8))), text, font=f, fill=CH['y'] + (a,), stroke_width=Wi(2), stroke_fill=CH['y'] + (a,))
        elif kind == 'impact':   # knock impact at the nub tip
            _, uu, tp_ = fx
            tx, ty = tp_
            if uu < 0.25:
                r = 20 + 90 * ease_out(uu / 0.25); a = int(220 * (1 - uu / 0.25))
                d.ellipse((S(tx - r), S(ty - r), S(tx + r), S(ty + r)), outline=CH['w'] + (a,), width=Wi(5))
            for i in range(9):
                r1, r2 = hrand('dust', i, int(tx)), hrand('dust', i, 7)
                ang = -math.pi / 2 + (r1 - 0.5) * 2.6; sp = 120 + 160 * r2
                px_ = tx + math.cos(ang) * sp * uu; py_ = ty + math.sin(ang) * sp * uu + 160 * uu * uu
                a = int(200 * clamp(1 - uu / 0.6, 0, 1)); rr = 5 + 6 * r2
                d.ellipse((S(px_ - rr), S(py_ - rr), S(px_ + rr), S(py_ + rr)), fill=(235, 235, 225, a))
        elif kind == 'exclaim':
            _, u, D_ = fx
            s_ = ease_out_back(min(1, u / 0.18)); a = int(255 * clamp((D_ - u) / 0.3, 0, 1))
            f = font('yaheib', S(84 * s_ + 1)); ex_ = min(hx + 165, LW - 48)
            d.text((S(ex_), S(g['top'] + 8 - 92 * s_)), '!', font=f, fill=CH['y'] + (a,))
        elif kind == 'digit':
            _, uu, n_, e = fx
            a = int(255 * e * clamp((1.0 - uu) / 0.3, 0, 1) * smooth(uu / 0.1)); tx_, ty_ = g['tipR']
            if a >= 10:
                f = font('kai', S(62)); txt_ = str(n_); tw = d.textlength(txt_, font=f)
                d.text((min(S(tx_ - 8), S(LW - 40) - tw), S(ty_ - 112 - 16 * ease_out(uu / 0.5))), txt_, font=f, fill=CH['y'] + (a,), stroke_width=Wi(1.5), stroke_fill=CH['y'] + (a,))
        elif kind == 'hl_ring':
            pass   # drawn by the board layer (needs the target bbox)
        elif kind == 'stamp':
            pass   # drawn by the board layer at the stamp position


D_CONF = 1.9


def run_action(name, P, u, ctx, D=None):
    A = ACTIONS[name]; D = D if D is not None else A['dur']
    return A['fn'](P, u, D, ctx) or []


# ------------------------------------------------------------------ contact sheet
SHEET = [
    ('idle', '待机呼吸·眨眼', [0.2, 1.3, 2.2], {}),
    ('talk', '说话（音量驱动）', [0.1, 0.5, 0.9], {'talk': True}),
    ('enter_walk', '走进/走出/走到', [0.4, 0.75, 1.1], {'x0': 1300, 'x1': 1700}),
    ('point_at', '教鞭指点', [0.15, 0.6, 1.2], {'target': (1300, 380)}),
    ('knock_board', '敲黑板！', [0.2, 0.42, 0.88, 1.25], {'tap': (700, 520)}),
    ('write_on_board', '写板书（小跳够高处）', [0.3, 0.6, 1.0], {'target': (1350, 300)}),
    ('think', '想一想', [0.15, 0.8, 1.4], {}),
    ('aha', '恍然大悟', [0.12, 0.35, 0.55], {}),
    ('confused', '困惑', [0.4, 0.9, 1.4], {}),
    ('shrug_sweat', '摊手流汗', [0.2, 0.7, 1.2], {}),
    ('nod', '点头', [0.2, 0.4, 0.62], {}),
    ('thumbs_up', '点赞 + 对勾', [0.15, 0.5, 0.9], {}),
    ('celebrate', '庆祝转圈', [0.3, 0.5, 0.9], {}),
    ('quiz_ask', '考考你（3 秒计时）', [0.3, 1.5, 2.6], {}),
    ('erase_board', '擦黑板（过场）', [0.2, 0.45, 0.7], {}),
    ('wave', '挥手', [0.3, 0.55, 0.8], {}),
    ('listen', '听同学提问', [0.4, 1.0, 1.75], {}),
    ('hop', '开心小跳 +x%', [0.1, 0.3, 0.5], {'text': '+9%'}),
    ('lean_board', '探身看黑板', [0.3, 1.0, 1.8], {}),
    ('surprised', '吓一跳', [0.05, 0.28, 0.7], {}),
    ('count_fingers', '数手指（n=3）', [0.3, 1.1, 1.9], {'n': 3}),
    ('tiptoe_peek', '踮脚看', [0.2, 0.8, 1.4], {}),
    ('head_tilt', '歪头', [0.15, 0.6, 1.05], {}),
    ('wink', '眨一只眼', [0.1, 0.5, 0.95], {}),
    ('answer_react', '听完同学后的反应', [0.1, 0.3, 0.8], {}),
    ('beat', '压手强调', [0.2, 0.38, 0.76], {}),
    ('shake_head', '摇头', [0.15, 0.45, 0.75], {}),
    ('proud', '叉腰挺胸', [0.2, 0.9, 1.5], {}),
    ('present', '朝黑板一摆', [0.2, 0.8, 1.4], {}),
    ('look_at_viewer', '看向观众', [0.1, 0.5, 0.9], {}),
]


def contact_sheet(path, out_w=1920):
    """grid of keyframes for every action, on a chalkboard look"""
    sc = Scale(out_w); cols = 3; cell_w, cell_h = 620, 330
    rows = math.ceil(len(SHEET) / cols)
    Wt, Ht = cols * cell_w + 40, rows * cell_h + 150
    sheet = Image.new('RGBA', (Wt, Ht), (32, 52, 45, 255)); d = ImageDraw.Draw(sheet)
    d.text((30, 28), 'Clawd 动作模块 · 关键帧一览', font=font('kai', 64), fill=CH['y'] + (255,))
    d.text((Wt - 760, 50), '每格 3~4 个关键帧（从左到右）· 2D 扁平版', font=font('kai', 34), fill=CH['w'] + (255,))
    mini = Scale(int(out_w * 0.36))   # render Clawd small to test readability at small size
    for idx, (name, label, us, ctx) in enumerate(SHEET):
        r, c = divmod(idx, cols); X0, Y0 = 20 + c * cell_w, 130 + r * cell_h
        d.rounded_rectangle((X0 + 6, Y0 + 6, X0 + cell_w - 6, Y0 + cell_h - 6), 18, outline=(90, 120, 105), width=3, fill=(38, 62, 54))
        d.text((X0 + 22, Y0 + 14), label, font=font('kai', 38), fill=CH['w'] + (255,))
        d.text((X0 + cell_w - 22 - d.textlength(name, font=font('yahei', 22)), Y0 + 24), name, font=font('yahei', 22), fill=CH['b'] + (255,))
        n = len(us); sub_w = (cell_w - 30) / n
        for j, u in enumerate(us):
            P = new_pose(x=960.0)
            c2 = dict(ctx)
            if 'target' in c2: c2['target'] = (960 + (c2['target'][0] - 1690), c2['target'][1])
            if name == 'enter_walk': c2 = {'x0': 760, 'x1': 1160}
            D = action_dur(name, c2)
            fxs = run_action(name, P, u, c2, D)
            apply_idle(P, u + 0.5) if name == 'idle' else None
            if ctx.get('talk'): apply_talk(P, [0.2, 0.9, 0.5][j], [0.3, 0.8, 0.6][j], u)
            fr = Image.new('RGBA', (mini.W, mini.H), (0, 0, 0, 0))
            spr, (sx_, sy_) = render(P, mini, SS=3)
            paste_rgba(fr, spr, sx_, sy_)
            draw_fx(fr, mini, P, fxs, u)
            # crop around Clawd
            cx, cy = mini(P['x']), mini(FLOOR_Y - 230)
            cw, chh = int(sub_w * 1.0), cell_h - 70
            crop = fr.crop((int(cx - cw / 2 * 1.25), int(cy - chh * 0.72), int(cx + cw / 2 * 1.25), int(cy + chh * 0.6)))
            crop = crop.resize((int(sub_w), int(sub_w * crop.size[1] / crop.size[0])), Image.LANCZOS)
            if crop.size[1] > chh: crop = crop.crop((0, crop.size[1] - chh, crop.size[0], crop.size[1]))
            sheet.alpha_composite(crop, (int(X0 + 15 + j * sub_w), int(Y0 + cell_h - 12 - crop.size[1])))
            d.line([(X0 + 20 + j * sub_w, Y0 + cell_h - 30), (X0 + 10 + (j + 1) * sub_w, Y0 + cell_h - 30)], fill=(120, 150, 135), width=2)
    sheet.convert('RGB').save(path)
    return path


if __name__ == '__main__':
    import sys
    print(contact_sheet(sys.argv[1] if len(sys.argv) > 1 else 'clawd_actions_sheet.png'))
