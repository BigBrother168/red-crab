"""readme_media.py: every README picture again, from the recordings (tools/t/rec, made by rec_scenes.py) and the
frame sets, into docs/media.  Run with the venv.  The screenshots (album, connect, menu) are made by hand: shot.py,
rec_scenes.py menu (see docs/开发记录.md)."""
import os, re, subprocess, sys
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RD = os.path.join(T, "tools", "t", "rec")
OUT = os.path.join(T, "docs", "media")
PY = sys.executable
GIF = os.path.join(T, "tools", "rec_gif.py")
GRID = os.path.join(T, "tools", "media_grid.py")


def marks(name):
    o = subprocess.run([PY, GIF, os.path.join(RD, name), os.path.join(RD, "x.gif"), "--info", "--from", "0", "--to", "0.3"],
                       capture_output=True, text=True).stdout
    return dict((m.group(1), float(m.group(2))) for m in re.finditer(r"mark (\w+)\s+([\d.]+)", o))


def gif(name, out, *args):
    r = subprocess.run([PY, GIF, os.path.join(RD, name), os.path.join(OUT, out)] + list(args), capture_output=True, text=True)
    print(out, (r.stdout or r.stderr).strip().splitlines()[-1])


only = set(sys.argv[1:])
for l in ("zh", "en"):
    if not only or "hero" in only:
        m = marks("hero_" + l)
        gif("hero_" + l, "hero_%s.gif" % l, "--parts", "%.2f-%.2f,%.2f-%.2f" % (m["listen"] - 0.8, m["run"] + 3.2, m["stop"] - 0.3, m["stop"] + 7.5))
    if not only or "circles" in only:
        m = marks("circles_" + l)
        gif("circles_" + l, "circles_%s.gif" % l, "--from", "%.2f" % (m["one"] - 0.5), "--to", "%.2f" % m["end"],
            "--cursor", "%.2f-%.2f:1036,1513" % (m["hover"] + 0.1, m["reply"] - 0.6))
    if not only or "dig" in only:
        m = marks("dig_" + l)
        gif("dig_" + l, "dig_%s.gif" % l, "--parts", "%.2f-%.2f,%.2f-%.2f" % (m["listen"] - 0.5, m["listen"] + 12.4, m["stop"] - 0.3, m["end"] - 1.5))
    if not only or "levelup" in only:
        m = marks("levelup_" + l)
        gif("levelup_" + l, "levelup_%s.gif" % l, "--parts", "%.2f-%.2f,%.2f-%.2f" % (m["listen"] - 0.4, m["listen"] + 6.5, m["stop"] - 0.3, m["stop"] + 19.5))
if not only or "combos" in only:
    m = marks("combos_zh")
    for k, length, x0 in (("high_five", 7.5, 473), ("stack", 9.5, 477), ("leapfrog", 10, 427), ("parade", 12, 552)):
        gif("combos_zh", "combo_%s.gif" % k, "--from", "%.2f" % (m[k] - 0.3), "--to", "%.2f" % (m[k] - 0.3 + length),
            "--scale", "0.5", "--crop", "%d,1111,%d,1562" % (x0, x0 + 860))
if not only or "grids" in only:
    import json
    names = json.load(open(os.path.join(T, "frames", "manifest.json"), encoding="utf-8"))["items"]["names"]
    RAR = {"rare": "8e5bd8", "special": "e0a020", "uncommon": "3b82d6", "common": "a9a39a"}
    work = ["listen:你发了消息:You sent a message", "think:在想:Thinking", "work_read:读文件:Reading files",
            "work_edit:改代码:Editing code", "work_run:跑命令:Running commands", "work_web:查资料:Searching the web",
            "work_compact:整理记忆:Compacting", "work_agent:派帮手:Sending a helper"]
    play = ["play_%s:%s:%s:%s" % (k, names[k]["zh"], names[k]["en"], RAR[names[k]["rarity"]])
            for k in ("rubber_duck", "cube", "moon_lamp", "bottle", "paper_ball", "keycap", "floppy", "leaf")]
            # two rare and two special for a taste (the user, 11-16: the duck, the cube, the moon, the bottle), four common
            # and uncommon below; the other eight rare and special stay a surprise.  media_save.py's family has these ones
    for l in ("zh", "en"):
        for out, cells, extra in (("work_%s.gif" % l, work, ["--hold", "--len", "110"]), ("play_%s.gif" % l, play, ["--len", "112"])):
            r = subprocess.run([PY, GRID, os.path.join(OUT, out), l] + cells + extra, capture_output=True, text=True)
            print(out, (r.stdout or r.stderr).strip().splitlines()[-1])
            try:
                os.remove(os.path.join(OUT, out[:-4] + "_still.png"))
            except OSError:
                pass
