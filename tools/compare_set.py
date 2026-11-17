# usage: compare_set.py LIVE_DIR NEW_DIR [SHEET.png] -- old actions byte-identical? canvas/anchor same?
import json, os, struct, sys, zlib
from PIL import Image

live, new = sys.argv[1], sys.argv[2]
ml = json.load(open(os.path.join(live, 'manifest.json'), encoding='utf-8'))
mn = json.load(open(os.path.join(new, 'manifest.json'), encoding='utf-8'))
for k in ('version', 'fps', 'width', 'height', 'base_body_px', 'anchor', 'renderer'):
    print('%-13s %s %s' % (k, 'same' if ml.get(k) == mn.get(k) else 'DIFF', mn.get(k)))
same = diff = 0
for name, a in ml['actions'].items():
    x = open(os.path.join(live, a['file']), 'rb').read()
    y = open(os.path.join(new, mn['actions'][name]['file']), 'rb').read()
    if x == y and a == mn['actions'][name]:
        same += 1
    else:
        diff += 1
        print('DIFF', name, len(x), len(y))
print('old actions identical: %d, different: %d' % (same, diff))
extra = [n for n in mn['actions'] if n not in ml['actions']]
print('new actions:', {n: (mn['actions'][n]['count'], os.path.getsize(os.path.join(new, mn['actions'][n]['file'])) // 1024) for n in extra}, '(frames, KB)')


def blobs(path):
    data = open(path, 'rb').read()
    off = 0
    while off < len(data):
        (n,) = struct.unpack_from('<I', data, off)
        off += 4
        yield data[off:off + n]
        off += n


W, H, px = mn['width'], mn['height'], mn['base_body_px']
fx, fy = mn['anchor']['feet_x'], mn['anchor']['feet_y']
for n in extra:
    L, T, R, B = W, H, 0, 0
    for b in blobs(os.path.join(new, mn['actions'][n]['file'])):
        bb = Image.frombuffer('RGBA', (W, H), zlib.decompress(b), 'raw', 'BGRA', 0, 1).getchannel('A').getbbox()
        L, T, R, B = min(L, bb[0]), min(T, bb[1]), max(R, bb[2]), max(B, bb[3])
    print('%-11s left %.3f right %.3f up %.3f' % (n, (fx - L) / px, (R - fx) / px, (fy - T) / px))

# seams: turn_X first == walk_(opposite of X) frame 0, turn_X last == walk_X frame 0
fr = {n: list(blobs(os.path.join(new, mn['actions'][n]['file']))) for n in extra}
def px_eq(a, b):
    return zlib.decompress(a) == zlib.decompress(b)
print('turn_left  start==walk_right[0]', px_eq(fr['turn_left'][0], fr['walk_right'][0]), ' end==walk_left[0]', px_eq(fr['turn_left'][-1], fr['walk_left'][0]))
print('turn_right start==walk_left[0] ', px_eq(fr['turn_right'][0], fr['walk_left'][0]), ' end==walk_right[0]', px_eq(fr['turn_right'][-1], fr['walk_right'][0]))

if len(sys.argv) > 3:
    rows = [('walk_left', 6), ('walk_right', 6), ('turn_left', 6)]
    sheet = Image.new('RGB', (W * 6, H * len(rows)), (235, 235, 235))
    for r, (n, c) in enumerate(rows):
        lst = fr[n]
        for i in range(c):
            f = lst[i * (len(lst) - 1) // (c - 1)]
            im = Image.frombuffer('RGBA', (W, H), zlib.decompress(f), 'raw', 'BGRA', 0, 1).copy()
            sheet.paste(im, (i * W, r * H), im)
    sheet.save(sys.argv[3])
