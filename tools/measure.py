"""measure.py CHECKOUT SECS [circles]: idle CPU (% of the whole machine) and memory of a test family of three run from
CHECKOUT (its player, its frames), on a home of its own.  "circles": three conversations first, so the row of
circles is up.  CPU by QueryProcessCycleTime against a 1 s spin of one core (CLAUDE.md: the other counters are off).
Prints the checkout it really ran, so a comparison with main cannot measure the branch twice."""
import ctypes, ctypes.wintypes as w, json, os, re, subprocess, sys, time
ROOT = os.path.abspath(sys.argv[1])
SECS = float(sys.argv[2])
CIRCLES = "circles" in sys.argv[3:]
HOME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "t", "measurehome")
BASH = "D:/git/Git/bin/bash.exe"
os.makedirs(HOME, exist_ok=True)
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = w.HANDLE
k.GetCurrentProcess.restype = w.HANDLE
k.QueryProcessCycleTime.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]


class PMC(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t),
                ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def cycles(h):
    c = ctypes.c_ulonglong()
    k.QueryProcessCycleTime(h, ctypes.byref(c))
    return c.value


def log():
    try:
        return open(HOME + "/pet.log", encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


for f in ("event", "state.json", "pet.log", "grow.json", "grow.json.bak"):
    try:
        os.remove(os.path.join(HOME, f))
    except OSError:
        pass
json.dump({"xp": 0, "level_shown": 99, "chances": 0}, open(HOME + "/grow.json", "w"))
json.dump({"x": 1700, "y": 1400, "scale": 1.0, "wanted": 1.0, "slots": [1, 2], "lang": "zh",
           "pos": {"1": [1450, 1400, 1.0], "2": [1250, 1400, 1.0]}}, open(HOME + "/state.json", "w"))
proc = subprocess.Popen(["C:/Python312/pythonw.exe", os.path.join(ROOT, "clawd_pet.pyw"), "--home", HOME,
                         "--frames-dir", os.path.join(ROOT, "frames"), "--keep-place"])
time.sleep(5)
end = time.time() + 180
while time.time() < end:
    L = log()
    if len(re.findall(r"re-render .* started", L)) <= len(re.findall(r"re-render .* finished", L)):
        break
    time.sleep(1)
if CIRCLES:
    for s in ("aaaaaaaa", "bbbbbbbb", "cccccccc"):
        for word in ("listen", "stop"):
            subprocess.run([BASH, "-c", 'echo "%s %s" >> "%s/event"' % (word, s, HOME)])
            time.sleep(0.4)
time.sleep(25)                                 # the reactions over, the signs down
me = k.GetCurrentProcess()
c0, t0 = cycles(me), time.perf_counter()
while time.perf_counter() - t0 < 1.0:
    pass
per_sec = cycles(me) - c0                      # one core flat out for 1 s
h = k.OpenProcess(0x1000 | 0x0400 | 0x0010, False, proc.pid)
a, ta = cycles(h), time.perf_counter()
time.sleep(SECS)
b, tb = cycles(h), time.perf_counter()
pmc = PMC()
pmc.cb = ctypes.sizeof(PMC)
ctypes.WinDLL("psapi").GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
cores = os.cpu_count()
print("ran %s%s: %.3f%% of the machine (%d cores), working set %.1f MB, private %.1f MB"
      % (ROOT, " with circles" if CIRCLES else "", 100.0 * (b - a) / (tb - ta) / per_sec / cores, cores,
         pmc.WorkingSetSize / 1048576.0, pmc.PrivateUsage / 1048576.0))
L = log()
print("  log: %d lines, circles lines: %d, tracebacks: %d" % (L.count("\n"), L.count("is number"), L.count("Traceback")))
subprocess.run([BASH, "-c", 'echo "quit" >> "%s/event"' % HOME])
try:
    proc.wait(timeout=8)
except Exception:
    proc.kill()
