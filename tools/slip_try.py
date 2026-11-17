# slip_try.py COMBO...: a test pet at Lv.16 with --slip yes plays these combos (high_five, leapfrog, stack) the other way; prints the log lines
import json, os, re, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(T, "tools", "t", "sliphome"); os.makedirs(HOME, exist_ok=True)
for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak"):
    try: os.remove(os.path.join(HOME, f))
    except OSError: pass
need = lambda l: min(int(round(40 * l ** 1.5)), 1080)
json.dump({"xp": sum(need(i) for i in range(1, 16)) + 5, "level_shown": 99,
           "gifts": ["chalk_pink", "dig_4", "frame_dots", "items_2", "chalk_blue", "frame_stars", "slips", "dig_5"],
           "seen": {"high_five": "2026-01-01", "leapfrog": "2026-01-01", "stack": "2026-01-01"}}, open(HOME + "/grow.json", "w"))
json.dump({"x": 1700, "y": 1504, "scale": 1.0, "wanted": 1.0, "slots": [1, 2], "pos": {"1": [1450, 1504, 1.0], "2": [1250, 1504, 1.0]}}, open(HOME + "/state.json", "w"))
open(HOME + "/cursor", "w").write("100 100")
proc = subprocess.Popen(["C:/Python312/pythonw.exe", os.path.join(T, "clawd_pet.pyw"), "--home", HOME, "--debug", "--frames-dir", os.path.join(T, "frames"),
                         "--wander-interval", "999-999", "--extra-interval", "999-999", "--combo-interval", "9999-9999", "--play-interval", "9999",
                         "--keep-place", "--cursor-file", HOME + "/cursor", "--nap-times", "1,2,3", "--slip", "yes"])
log = lambda: open(HOME + "/pet.log", encoding="utf-8", errors="replace").read() if os.path.exists(HOME + "/pet.log") else ""
time.sleep(5)
end = time.time() + 150
while time.time() < end:
    L = log()
    if len(re.findall(r"re-render .* started", L)) <= len(re.findall(r"re-render .* finished", L)): break
    time.sleep(0.5)
time.sleep(1.5)
for name in sys.argv[1:]:
    n = len(log())
    with open(HOME + "/event", "a") as f: f.write("combo:%s\n" % name)
    t = time.time()
    while time.time() - t < 30 and ("combo %s over" % name) not in log()[n:] and "cancelled" not in log()[n:]: time.sleep(0.3)
    time.sleep(7)
    print("=====", name)
    print("\n".join(l[20:] for l in log()[n:].splitlines() if re.search(r"combo|play (slip|stack_flip|leap|stack_hop|high)|hop |landed|grow:|sign up|Traceback|Error", l))[:2500])
proc.terminate()
