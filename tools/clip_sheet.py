# usage: clip_sheet.py OUT.png SET_DIR [SET_DIR ...] -- film strips, one block per frame set; env CLIPS=a,b,c picks the clips (default: work_*).
import json, os, struct, sys, zlib
from PIL import Image, ImageDraw, ImageFont

CLIPS = os.environ.get('CLIPS', 'work_read,work_edit,work_run,work_web,work_compact,work_agent').split(',')
FRACS = (0.08, 0.16, 0.3, 0.5, 0.7, 0.86, 0.94)
ft = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 16)
blocks = []
for d in sys.argv[2:]:
    m = json.load(open(os.path.join(d, 'manifest.json'), encoding='utf-8'))
    W, H = m['width'], m['height']
    im = Image.new('RGB', (W * len(FRACS) + 90, H * len(CLIPS)), (238, 240, 244))
    dr = ImageDraw.Draw(im)
    for r, n in enumerate(CLIPS):
        data = open(os.path.join(d, m['actions'][n]['file']), 'rb').read()
        off, fr = 0, []
        while off < len(data):
            (k,) = struct.unpack_from('<I', data, off)
            fr.append(data[off + 4:off + 4 + k])
            off += 4 + k
        dr.text((4, r * H + 4), m['actions'][n]['label'] + '\n%dpx' % m['base_body_px'], font=ft, fill=(50, 54, 70))
        for c, f in enumerate(FRACS):
            raw = zlib.decompress(fr[int(f * len(fr))])
            p = Image.frombuffer('RGBA', (W, H), raw, 'raw', 'BGRA', 0, 1).copy()
            im.paste(p, (90 + c * W, r * H), p)
    blocks.append(im)
sheet = Image.new('RGB', (max(b.width for b in blocks), sum(b.height for b in blocks)), (238, 240, 244))
y = 0
for b in blocks:
    sheet.paste(b, (0, y))
    y += b.height
sheet.save(sys.argv[1])
print(sheet.size)
