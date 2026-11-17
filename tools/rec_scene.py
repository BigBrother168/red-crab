"""rec_scene.py: helpers to play scenes on a test family and record them with rec.py (README pictures).
A --home test pet (tools/t/rechome), events written to its event file, the cursor read from a file far away (your real
mouse never starts anything).  Scenes are in rec_scenes.py."""
import json, os, re, subprocess, sys, time

T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(T, "tools", "t", "rechome")
CUR = os.path.join(HOME, "cursor")
REC = os.path.join(T, "tools", "rec.py")
ACTS = ("shy", "dangle", "tumble", "dizzy", "doze", "doze_startle", "doze_up", "shrug_sweat", "surprised")
proc = None
OUT = None


def log():
    try:
        return open(os.path.join(HOME, "pet.log"), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def cursor(x, y):
    with open(CUR + ".tmp", "w") as f:
        f.write("%d %d" % (x, y))
    os.replace(CUR + ".tmp", CUR)


def event(line):
    with open(os.path.join(HOME, "event"), "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


def evs(*lines, gap=0.4):
    for l in lines:
        event(l)
        time.sleep(gap)


def start(out, lang="zh", slots=(1, 2), grow=None, pos=None, scale=1.0, extra=(), calm=True):
    """grow: dict for grow.json (acts seen are added), None: a new family.  pos: {slot: x} of the feet."""
    global proc, OUT
    OUT = out
    os.makedirs(out, exist_ok=True)
    try:
        os.remove(os.path.join(out, "marks.txt"))
    except OSError:
        pass
    os.makedirs(HOME, exist_ok=True)
    for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak", "album.json", "talks.json", "circles.txt"):
        try:
            os.remove(os.path.join(HOME, f))
        except OSError:
            pass
    if grow is not None:
        g = dict(grow)
        g.setdefault("acts", dict((a, "2026-01-01") for a in ACTS))
        json.dump(g, open(os.path.join(HOME, "grow.json"), "w"))
    pos = pos or {0: 700, 1: 520, 2: 380}
    y = 1500
    st = {"x": pos[0], "y": y, "scale": scale, "wanted": scale, "slots": list(slots), "lang": lang,
          "pos": dict((str(s), [pos[s], y, scale]) for s in slots)}
    json.dump(st, open(os.path.join(HOME, "state.json"), "w"))
    cursor(50, 50)
    args = ["--home", HOME, "--frames-dir", os.path.join(T, "frames"), "--keep-place", "--cursor-file", CUR]
    if calm:
        args += ["--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999",
                 "--play-interval", "9999"]
    proc = subprocess.Popen(["C:/Python312/python.exe", REC, out] + args + list(extra),
                            stdout=open(os.path.join(HOME, "rec.out"), "w"), stderr=subprocess.STDOUT)
    time.sleep(3)
    end = time.time() + 180
    quiet = 0
    while time.time() < end:
        L = log()
        if "Traceback" in L:
            raise SystemExit("player failed:\n" + L[-2000:])
        if len(re.findall(r"re-render .* started", L)) <= len(re.findall(r"re-render .* finished", L)):
            quiet += 1
            if quiet >= 4:
                break
        else:
            quiet = 0
        time.sleep(0.5)
    time.sleep(1.0)
    return time.time()


def mark(name):
    """A line in the log with the time, to find the moment in the recording."""
    with open(os.path.join(OUT, "marks.txt"), "a") as f:
        f.write("%s %.3f\n" % (name, time.time()))


def stop():
    event("quit")
    try:
        proc.wait(timeout=60)
    except Exception:
        proc.kill()
    print(open(os.path.join(HOME, "rec.out")).read().strip())
