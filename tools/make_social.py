"""make_social.py OUT.png: the share picture (1280x640, GitHub's social preview) from frames_hi.  Run with the venv."""
import json, os, struct, sys, zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "frames_hi")
m = json.load(open(os.path.join(D, "manifest.json"), encoding="utf-8"))
W, H = m["width"], m["height"]


def frame(name, k):
    data = open(os.path.join(D, m["actions"][name]["file"]), "rb").read()
    off, i = 0, 0
    while off < len(data):
        (n,) = struct.unpack_from("<I", data, off)
        if i == k:
            a = np.frombuffer(zlib.decompress(data[off + 4:off + 4 + n]), np.uint8).reshape(H, W, 4).astype(np.float32)
            al = a[:, :, 3:4]
            rgb = np.where(al > 0, a[:, :, 2::-1] * 255.0 / np.maximum(al, 1), 0)
            return Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), al], 2).astype(np.uint8), "RGBA")
        off += 4 + n
        i += 1
    raise SystemExit("no frame %d in %s" % (k, name))


def count(name):
    return m["actions"][name].get("count") or 0


out = sys.argv[1]
picks = [a.split(":") for a in (sys.argv[2:] or ["celebrate:22", "celebrate:16", "wave:12"])]
S = 1280, 640
img = Image.new("RGB", S, (246, 240, 230))
dr = ImageDraw.Draw(img)
# a soft warm glow behind the family
glow = Image.new("L", S, 0)
ImageDraw.Draw(glow).ellipse((640, 60, 1300, 700), fill=120)
glow = glow.filter(ImageFilter.GaussianBlur(90))
img.paste(Image.new("RGB", S, (252, 222, 196)), (0, 0), glow)
# the family: big, middle (80%), small (60%), standing on one line
floor = 585
Z = 0.8
fam = [(picks[1], Z * 0.8, 790), (picks[0], Z, 1010), (picks[2], Z * 0.6, 1192)]
foot_y = None
for (name, k), s, fx in fam:
    f = frame(name, int(k))
    f = f.resize((round(W * s), round(H * s)), Image.LANCZOS)
    # the feet: the frame's anchor (same for every frame of the set)
    ax, ay = m["anchor"]["feet_x"], m["anchor"]["feet_y"]
    x, y = round(fx - ax * s), round(floor - ay * s)
    img.paste(f, (x, y), f)
F = r"C:\Windows\Fonts"
big = ImageFont.truetype(os.path.join(F, "seguibl.ttf"), 104)
zh = ImageFont.truetype(os.path.join(F, "msyhbd.ttc"), 60)
line = ImageFont.truetype(os.path.join(F, "seguisb.ttf"), 30)
linezh = ImageFont.truetype(os.path.join(F, "msyh.ttc"), 30)
small = ImageFont.truetype(os.path.join(F, "segoeui.ttf"), 24)
INK, SOFT, RED = (52, 40, 48), (110, 96, 100), (204, 92, 64)
dr.text((84, 118), "Red Crab", font=big, fill=INK)
dr.text((90, 250), "红螃蟹", font=zh, fill=RED)
dr.text((88, 350), "Desktop pets that work along with your AI", font=line, fill=INK)
dr.text((88, 396), "跟着 AI 一起干活的桌面一家三口", font=linezh, fill=INK)
dr.text((88, 486), "Claude Code · Codex · DeepSeek Harness · Antigravity", font=small, fill=SOFT)
dr.text((88, 520), "Windows · free and open source", font=small, fill=SOFT)
# a picture gets shared on its own: say on it whose character this is (the user, 11-16: no needless disputes)
tiny = ImageFont.truetype(os.path.join(F, "msyh.ttc"), 19)
dr.text((88, 574), "Unofficial Clawd fan project, not affiliated with Anthropic", font=tiny, fill=(150, 136, 138))
dr.text((88, 600), "非官方 Clawd 粉丝作品，与 Anthropic 无关", font=tiny, fill=(150, 136, 138))
img.save(out)
print("wrote", out, img.size)
