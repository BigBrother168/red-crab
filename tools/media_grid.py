"""media_grid.py OUT.gif LANG CLIP:标签:label ...: clips of a frame set in a grid of cards, each with its words under it
(README pictures; run with the venv).  Every clip plays at its real speed and holds its last frame until the picture
starts again.  Options: --cols N  --frames DIR (default frames)  --len FRAMES (default: the longest clip)
--loops N (play each clip N times, default 1)  --crop l,t,r,b (of the frame; default: what any clip draws on)
--hold: the player's holds (work, listen, think) go intro -> hold, repeated as long as --len allows -> outro"""
import json, os, struct, sys, zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out, lang = sys.argv[1], sys.argv[2]
args = sys.argv[3:]
HOLD_LOOP = {"work_read": 24, "work_edit": 24, "work_run": 24, "work_compact": 24}     # as in clawd_pet.pyw
HOLDS = ("think", "listen", "work_read", "work_edit", "work_run", "work_web", "work_compact")
opt = {"--cols": "4", "--frames": os.path.join(ROOT, "frames"), "--len": "0", "--loops": "1", "--crop": ""}
cells = []
i = 0
while i < len(args):
    if args[i] == "--hold":
        opt["--hold"] = "1"
        i += 1
    elif args[i] in opt:
        opt[args[i]] = args[i + 1]
        i += 2
    else:
        cells.append(args[i].split(":"))
        i += 1
d = opt["--frames"]
m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
W, H = m["width"], m["height"]


def frames(name):
    data = open(os.path.join(d, m["actions"][name]["file"]), "rb").read()
    off, r = 0, []
    while off < len(data):
        (n,) = struct.unpack_from("<I", data, off)
        a = np.frombuffer(zlib.decompress(data[off + 4:off + 4 + n]), np.uint8).reshape(H, W, 4).astype(np.float32)
        al = a[:, :, 3:4]
        rgb = np.where(al > 0, a[:, :, 2::-1] * 255.0 / np.maximum(al, 1), 0)      # premultiplied BGRA -> RGBA
        r.append(Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), al], 2).astype(np.uint8), "RGBA"))
        off += 4 + n
    return r


clips = [frames(c[0]) for c in cells]
loops = int(opt["--loops"])
L = int(opt["--len"]) or max(len(f) for f in clips) * loops


def order(name, n):
    """-> the frame numbers to show, at most L: a hold repeated as the player does, else the clip --loops times."""
    if not opt.get("--hold") or name not in HOLDS:
        return [k % n for k in range(min(L, n * loops))]
    a, b = int(n * 0.2), int(n * 0.82)
    p = HOLD_LOOP.get(name)
    if p:
        k = max(1, (L - n) // p + 1)
        return list(range(a)) + list(range(a, a + p)) * k + list(range(a + p, n))
    span = b - a
    trip = list(range(b - 1, a - 1, -1)) + list(range(a + 1, b + 1))
    m = max(0, (L - n) // (2 * span))
    return list(range(b + 1)) + trip * m + list(range(b + 1, n))
if opt["--crop"]:
    cx0, cy0, cx1, cy1 = map(int, opt["--crop"].split(","))
else:
    boxes = [f.getbbox() for c in clips for f in c]
    boxes = [b for b in boxes if b]
    cx0, cy0 = max(0, min(b[0] for b in boxes) - 6), max(0, min(b[1] for b in boxes) - 6)
    cx1, cy1 = min(W, max(b[2] for b in boxes) + 6), min(H, max(b[3] for b in boxes) + 6)
cw, ch = cx1 - cx0, cy1 - cy0
font = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc" if lang == "zh" else r"C:\Windows\Fonts\seguisb.ttf", 17)
PAD, GAP, LAB = 10, 12, 34
cols = int(opt["--cols"])
rows = (len(cells) + cols - 1) // cols
CW, CH = cw + 2 * PAD, ch + PAD + LAB
BG, CARD, EDGE, INK = (244, 239, 230), (255, 252, 246), (230, 220, 202), (60, 50, 66)
IW, IH = cols * CW + (cols + 1) * GAP, rows * CH + (rows + 1) * GAP
base = Image.new("RGB", (IW, IH), BG)
dr = ImageDraw.Draw(base)
spots = []
for k, c in enumerate(cells):
    x = GAP + (k % cols) * (CW + GAP)
    y = GAP + (k // cols) * (CH + GAP)
    dr.rounded_rectangle((x, y, x + CW - 1, y + CH - 1), 14, fill=CARD, outline=EDGE, width=1)
    text = c[1] if lang == "zh" else c[2]
    tw = dr.textlength(text, font=font)
    dot = 14 if len(c) > 3 else 0              # a 4th part: a dot of that colour before the words (rarity)
    tx, ty = x + (CW - tw - dot) / 2 + dot, y + PAD + ch + 4
    if dot:
        col = tuple(int(c[3][k:k + 2], 16) for k in (0, 2, 4))
        dr.ellipse((tx - dot, ty + 8, tx - dot + 9, ty + 17), fill=col)
    dr.text((tx, ty), text, font=font, fill=INK)
    spots.append((x + PAD, y + PAD))
orders = [order(cells[k][0], len(c)) for k, c in enumerate(clips)]
imgs = []
for t in range(L):
    im = base.copy()
    for k, c in enumerate(clips):
        seq = orders[k]
        f = c[seq[t]] if t < len(seq) else c[-1]
        cell = f.crop((cx0, cy0, cx1, cy1))
        im.paste(cell, spots[k], cell)
    imgs.append(im)
pick = imgs[::max(1, len(imgs) // 12)]
dots = sorted(set(c[3] for c in cells if len(c) > 3))   # the rarity dots: few pixels, so the palette would lose them
mos = Image.new("RGB", (IW, IH * len(pick) + 24 * len(dots)))
for j, im in enumerate(pick):
    mos.paste(im, (0, j * IH))
for j, hx in enumerate(dots):
    mos.paste("#" + hx, (0, IH * len(pick) + 24 * j, IW, IH * len(pick) + 24 * (j + 1)))
pal = mos.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in imgs]
fps = 20
q[0].save(out, save_all=True, append_images=q[1:], duration=int(1000 / fps), loop=0, disposal=1)
imgs[len(imgs) // 2].save(out[:-4] + "_still.png")
print("wrote %s: %d frames, %dx%d, %d KB" % (out, len(q), IW, IH, os.path.getsize(out) // 1024))
