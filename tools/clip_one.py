# clip_one.py CLIP BODY_PX OUT_PREFIX [EVERY]: render one clip straight from prerender (no frame set):
#   run with the venv (numpy, PIL); env RANGE=a,b picks the frames of the sheet.
#   OUT_PREFIX.gif (the clip on a light background, real speed) and OUT_PREFIX.png (every EVERY-th frame, numbered).
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the checkout this script is in (also a worktree)
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import prerender as R
from PIL import Image, ImageDraw, ImageFont
import numpy as np

name, body_px, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
every = int(sys.argv[4]) if len(sys.argv) > 4 else 4
ref = R.Scale(1920 // 5)
spr, _ = R.C.render(R.make_pose(), ref, SS=R.SS)
sc = R.Scale(int(round(1920 * body_px / (spr.size[0] / ref.s))))
act = next(a for a in R.ACTIONS if a[0] == name)
_, _, ctx, loop, afps, endpoint = act
fps = afps or R.FPS
D = R.ONESHOT_LEN.get(name)
N = int(round(D * fps)) + (1 if endpoint else 0)
frames = []
for k in range(N):
    P, fxs, u, fa = R.frame_inputs(name, ctx, loop, endpoint, k, N, fps)
    frames.append(R.render_frame(sc, P, fxs, u, fa))
boxes = [f.getbbox() for f in frames]
x0 = min(b[0] for b in boxes if b) - 6; y0 = min(b[1] for b in boxes if b) - 6
x1 = max(b[2] for b in boxes if b) + 6; y1 = max(b[3] for b in boxes if b) + 6
crops = []
for f in frames:
    bg = Image.new("RGBA", (x1 - x0, y1 - y0), (238, 232, 218, 255))
    bg.alpha_composite(f.crop((x0, y0, x1, y1)))
    crops.append(bg.convert("RGB"))
crops[0].save(out + ".gif", save_all=True, append_images=crops[1:], duration=int(1000 / fps), loop=0)
rng = os.environ.get("RANGE")
pick = list(range(*map(int, rng.split(",")), every)) if rng else list(range(0, N, every))
font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
w, h = crops[0].size
cols = 8
sheet = Image.new("RGB", (cols * w, ((len(pick) + cols - 1) // cols) * (h + 18)), (255, 255, 255))
d = ImageDraw.Draw(sheet)
for i, k in enumerate(pick):
    x, y = (i % cols) * w, (i // cols) * (h + 18)
    sheet.paste(crops[k], (x, y + 18))
    d.text((x + 4, y), "%d  %.2fs" % (k, k / float(fps)), font=font, fill=(0, 0, 0))
sheet.save(out + ".png")
print(name, N, "frames", fps, "fps", sheet.size)
