# usage: make_preview.py SET_DIR OUT_BASE -- labelled still sheet (PNG) and animated grid (GIF) of the work clips.
import json, os, struct, sys, zlib
from PIL import Image, ImageDraw, ImageFont

d, out = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(d, 'manifest.json'), encoding='utf-8'))
W, H = m['width'], m['height']
CLIPS = ['listen', 'think', 'work_read', 'work_edit', 'work_run', 'work_web', 'work_compact', 'work_agent']
ft = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 20)


def frames(name):
    data = open(os.path.join(d, m['actions'][name]['file']), 'rb').read()
    off, r = 0, []
    while off < len(data):
        (n,) = struct.unpack_from('<I', data, off)
        r.append(zlib.decompress(data[off + 4:off + 4 + n]))
        off += 4 + n
    return r


def cell(raw, label):
    im = Image.new('RGB', (W, H + 30), (238, 240, 244))
    fr = Image.frombuffer('RGBA', (W, H), raw, 'raw', 'BGRA', 0, 1).copy()
    im.paste(fr, (0, 30), fr)
    ImageDraw.Draw(im).text((8, 2), label, font=ft, fill=(50, 54, 70))
    return im


clips = {n: frames(n) for n in CLIPS}
cols = 4
rows = (len(CLIPS) + cols - 1) // cols
# stills: the middle of each clip (the agent clip: when the plane is flying)
sheet = Image.new('RGB', (cols * W, rows * (H + 30)), (238, 240, 244))
for i, n in enumerate(CLIPS):
    f = clips[n]
    k = int(len(f) * 0.72) if n == 'work_agent' else len(f) // 2
    sheet.paste(cell(f[k], m['actions'][n]['label']), ((i % cols) * W, (i // cols) * (H + 30)))
sheet.save(out + '.png')
# animation: every clip loops in its own cell
L = 48
imgs = []
for t in range(L):
    g = Image.new('RGB', (cols * W, rows * (H + 30)), (238, 240, 244))
    for i, n in enumerate(CLIPS):
        f = clips[n]
        g.paste(cell(f[t * len(f) // L], m['actions'][n]['label']), ((i % cols) * W, (i // cols) * (H + 30)))
    imgs.append(g.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
imgs[0].save(out + '.gif', save_all=True, append_images=imgs[1:], duration=50, loop=0, disposal=1)
for n in CLIPS:
    f = clips[n]
    print('%-13s %3d frames, first==last: %s' % (n, len(f), f[0] == f[-1]))
print('all first+last frames equal (one plain pose):', len({clips[n][0] for n in CLIPS} | {clips[n][-1] for n in CLIPS}) == 1)
print('size', os.path.getsize(out + '.gif') // 1024, 'KB gif')
