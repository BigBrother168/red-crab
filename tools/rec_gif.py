"""rec_gif.py REC_DIR OUT [options]: pictures from a rec.py recording (run with the venv: numpy, PIL).
  OUT.gif: the windows at each moment, on a plain background.  OUT.png with --at T: one moment, transparent.
  --from S --to S     the part (s from the start of the recording)
  --crop l,t,r,b      screen pixels; default: every window of the part, plus --pad (default 16)
  --bg RRGGBB         background (default f3eee4)    --fps N (default 20)    --scale F (default 1)
  --speed F           faster than real (default 1)   --at T: the PNG's moment
  --parts a-b,c-d     several parts cut together (instead of --from/--to)
  --cursor a-b:x,y    draw a mouse arrow at x,y (screen pixels) from a to b (the pet's cursor is a file in tests)
  --info              print the changes per second and the marks (rec_scene.mark) in the recording's time"""
import json, os, sys, zlib
import numpy as np
from PIL import Image

rec, out = sys.argv[1], sys.argv[2]
opt = {"--from": "0", "--to": "1e9", "--parts": "", "--cursor": "", "--crop": "", "--pad": "16", "--bg": "f3eee4", "--fps": "20", "--scale": "1",
       "--speed": "1", "--at": ""}
flags = set()
a = sys.argv[3:]
i = 0
while i < len(a):
    if a[i] in opt:
        opt[a[i]] = a[i + 1]
        i += 2
    else:
        flags.add(a[i])
        i += 1
idx = json.load(open(os.path.join(rec, "index.json")))
frames, meta = idx["frames"], idx["blobs"]
bf = open(os.path.join(rec, "blobs.bin"), "rb")
cache = {}


def blob(bid):
    b = cache.get(bid)
    if b is None:
        off, ln, w, h = meta[bid]
        bf.seek(off)
        raw = zlib.decompress(bf.read(ln))
        b = cache[bid] = np.frombuffer(raw, np.uint8).reshape(h, w, 4).astype(np.float32) / 255.0
        if len(cache) > 3000:
            cache.clear()
    return b


t0, t1 = float(opt["--from"]), min(float(opt["--to"]), frames[-1][0] if frames else 0)
parts = [tuple(map(float, p.split("-"))) for p in opt["--parts"].split(",")] if opt["--parts"] else [(t0, t1)]
mk = os.path.join(rec, "marks.txt")
if "--info" in flags and os.path.exists(mk):
    for line in open(mk):
        name, wall = line.split()
        print("mark %-20s %.2f" % (name, float(wall) - idx.get("start", 0)))
if "--info" in flags:
    import collections
    per = collections.Counter(int(f[0]) for f in frames)
    print("length %.1f s; changes per second:" % frames[-1][0])
    print(" ".join("%d:%d" % (s, per[s]) for s in range(int(frames[-1][0]) + 1)))
part = [f for f in frames if any(a <= f[0] <= b for a, b in parts)]
if opt["--crop"]:
    L, T, R, B = map(int, opt["--crop"].split(","))
else:
    pad = int(opt["--pad"])
    xs = [(x, y, x + meta[b][2], y + meta[b][3]) for f in part for b, x, y, al in f[1]]
    L, T = min(r[0] for r in xs) - pad, min(r[1] for r in xs) - pad
    R, B = max(r[2] for r in xs) + pad, max(r[3] for r in xs) + pad
print("crop %d,%d,%d,%d (%dx%d)" % (L, T, R, B, R - L, B - T))
bg = np.array([int(opt["--bg"][k:k + 2], 16) for k in (0, 2, 4)], np.float32) / 255.0


def at(t):
    """-> the windows' state at t (the last change at or before it)."""
    j = 0
    lo, hi = 0, len(frames) - 1
    while lo <= hi:
        m = (lo + hi) // 2
        if frames[m][0] <= t:
            j = m
            lo = m + 1
        else:
            hi = m - 1
    return frames[j][1]


def compose(wins, alpha=False):
    H, W = B - T, R - L
    rgb = np.zeros((H, W, 3), np.float32)
    acc = np.zeros((H, W, 1), np.float32)       # coverage (premultiplied over)
    for bid, x, y, ca in reversed(wins):        # bottom first
        b = blob(bid)
        h, w = b.shape[:2]
        x0, y0, x1, y1 = max(x, L), max(y, T), min(x + w, R), min(y + h, B)
        if x0 >= x1 or y0 >= y1:
            continue
        s = b[y0 - y:y1 - y, x0 - x:x1 - x] * (ca / 255.0)
        sa = s[:, :, 3:4]
        rgb[y0 - T:y1 - T, x0 - L:x1 - L] = s[:, :, 2::-1] + rgb[y0 - T:y1 - T, x0 - L:x1 - L] * (1 - sa)
        acc[y0 - T:y1 - T, x0 - L:x1 - L] = sa + acc[y0 - T:y1 - T, x0 - L:x1 - L] * (1 - sa)
    if alpha:
        a = np.clip(acc, 1e-6, 1)
        img = np.concatenate([np.clip(rgb / a, 0, 1), acc], 2)
        return Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGBA")
    img = rgb + bg * (1 - acc)
    return Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


scale = float(opt["--scale"])


def sized(im):
    if scale != 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    return im


if opt["--at"]:
    sized(compose(at(float(opt["--at"])), alpha=True)).save(out)
    print("wrote", out)
    sys.exit(0)
fps, speed = float(opt["--fps"]), float(opt["--speed"])
times = []
for a, b in parts:
    times += [a + k * speed / fps for k in range(int((b - a) * fps / speed))]
arrow = None
if opt["--cursor"]:
    span, xy = opt["--cursor"].split(":")
    ca, cb = map(float, span.split("-"))
    cx, cy = map(int, xy.split(","))
    arrow = (ca, cb, cx - L, cy - T)
ARROW = [(0, 0), (0, 17), (4, 13), (7, 20), (9.5, 19), (6.5, 12), (12, 12)]


def with_arrow(im, t):
    if arrow is None or not arrow[0] <= t <= arrow[1]:
        return im
    from PIL import ImageDraw
    k = 1.6
    pts = [(arrow[2] + x * k, arrow[3] + y * k) for x, y in ARROW]
    ImageDraw.Draw(im).polygon(pts, fill=(255, 255, 255), outline=(20, 20, 20), width=2)
    return im


imgs, durs, last = [], [], None
for t in times:
    wins = at(t)
    on = arrow is not None and arrow[0] <= t <= arrow[1]
    if (wins, on) == last and durs:
        durs[-1] += 1000.0 / fps
        continue
    last = (wins, on)
    imgs.append(sized(with_arrow(compose(wins), t)))
    durs.append(1000.0 / fps)
# one palette for all: from a mosaic of some frames, the background kept exact
pick = imgs[::max(1, len(imgs) // 16)]
mos = Image.new("RGB", (pick[0].width, pick[0].height * len(pick)))
for j, im in enumerate(pick):
    mos.paste(im, (0, j * im.height))
pal = mos.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in imgs]
# (Pillow already stores only what changed from the frame before)
q[0].save(out, save_all=True, append_images=q[1:], duration=[int(round(d)) for d in durs], loop=0, disposal=1)
print("wrote %s: %d frames, %.1f s, %dx%d, %d KB" % (out, len(q), sum(durs) / 1000, q[0].width, q[0].height,
                                                      os.path.getsize(out) // 1024))
