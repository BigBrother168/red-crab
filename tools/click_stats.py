"""click_stats.py [SINCE] [--home DIR]: every click on a conversation circle in the pets' log (pet.log and
pet.log.1 in DIR, by default the folder above this one), sorted by what the pet did, by agent:

  link claude / link codex ...   it opened that conversation's own link
  already the conversation open  a Claude desktop conversation taken for the one on screen: no link
  tab selected                   a Windows Terminal tab selected again
  window only                    only its window brought up (right for DeepSeek, Antigravity and other terminals;
                                 for a Claude desktop or Codex desktop conversation it did NOT get you there)
  window not known               no window to go to

with how often the same circle was clicked again within 6 s (a click that did not get you there, most likely,
though you may also just be clicking about).  Then the clicks that look wrong, by conversation and pet run (a run is
one start of the pets: the number in [ ] in the log), and "a Claude link to B, then A taken for the one open"
orders (a stale focus would show there; a /btw side question and its own conversation are one, by design).
Only reads the log.  SINCE: "2026-11-14" or "2026-11-14 18:33:34" (default: today)."""
import collections, datetime, os, re, sys

REPEAT = 6.0                 # s: the same circle clicked again this soon
AHEAD = 3.0                  # s after a click its link / tab line may come (links open in a thread of their own)

args = sys.argv[1:]
home = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if "--home" in args:
    i = args.index("--home")
    home = args[i + 1]
    del args[i:i + 2]
since = args[0] if args else datetime.date.today().isoformat()
since = (since + " 00:00:00")[:19] if len(since) == 10 else since

lines = []
for f in ("pet.log.1", "pet.log"):
    try:
        lines += open(os.path.join(home, f), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        pass
rx_click = re.compile(r"^(\S+ \S+) \[(\d+)\] circle (\d) \(([0-9a-f]{8})\) clicked: (.*)$")
rx_after = re.compile(r"^(\S+ \S+) \[(\d+)\] circle (\d): (opened (\w+)://|already the conversation open|the same link a moment ago"
                      r"|tab selected|tab not found|not found: just its window|tab closed: just its window|shown from the tray)")
rx_where = re.compile(r"conversation ([0-9a-f]{8}) is at window \S+ \((\w+)\)")


def when(l):
    try:
        return datetime.datetime.strptime(l[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


agent = {}
clicks = []                  # (time, pet run, circle, conversation, what the pet did)
for i, l in enumerate(lines):
    m = rx_where.search(l)
    if m:
        agent[m.group(1)] = m.group(2)
    if l[:19] < since:
        continue
    m = rx_click.match(l)
    if not m:
        continue
    t = when(l)
    what = m.group(5)
    out = "window only" if "to the front" in what else ("window not known" if "not known" in what else what[:30])
    for l2 in lines[i + 1:i + 80]:
        t2 = when(l2)
        if t2 is None:
            continue
        if (t2 - t).total_seconds() > AHEAD:
            break
        m2 = rx_after.match(l2)
        if m2 and m2.group(3) == m.group(3) and m2.group(2) == m.group(2):
            out = ("link " + m2.group(5)) if m2.group(5) else m2.group(4)
            break
        m3 = rx_click.match(l2)
        if m3 and m3.group(3) == m.group(3) and m3.group(2) == m.group(2):
            break            # the same circle clicked again first
    clicks.append((t, m.group(2), m.group(3), m.group(4), out))

kinds = collections.Counter()
again = collections.Counter()
for j, (t, run, n, s, out) in enumerate(clicks):
    key = (agent.get(s, "?"), out)
    kinds[key] += 1
    for t2, run2, n2, s2, out2 in clicks[j + 1:j + 6]:
        if (t2 - t).total_seconds() > REPEAT:
            break
        if s2 == s and run2 == run:
            again[key] += 1
            break
starts = [(l[:19], m.group(1)) for l in lines for m in [re.match(r"^\S+ \S+ \[(\d+)\] start v2", l)] if m]
print("clicks since %s: %d   (log: %s)" % (since, len(clicks), home))
print("%-12s %-32s %6s %9s" % ("agent", "what the pet did", "clicks", "again<6s"))
for key, c in kinds.most_common():
    print("%-12s %-32s %6d %8d%%" % (key[0], key[1], c, round(100.0 * again[key] / c)))

print()
print("clicks that did not get there (a Claude or Codex conversation, no link and not the one open):")
by = collections.defaultdict(list)
for t, run, n, s, out in clicks:
    if agent.get(s) in ("claude", "codex") and out in ("window only", "window not known"):
        by[(s, agent.get(s), run, out)].append(t)
if not by:
    print("  none")
for (s, a, run, out), ts in sorted(by.items(), key=lambda x: x[1][0]):
    print("  %s %-7s run %-6s %-16s %3d clicks  %s - %s" % (s, a, run, out, len(ts), ts[0].strftime("%H:%M:%S"), ts[-1].strftime("%H:%M:%S")))
print("  (Claude in a terminal other than Windows Terminal can only get its window: such a conversation shows here too)")

print()
print("a Claude link to B, then another conversation A clicked within 60 s:")
res = collections.Counter()
for j, (t, run, n, s, out) in enumerate(clicks):
    if agent.get(s) != "claude" or out != "link claude":
        continue
    for t2, run2, n2, s2, out2 in clicks[j + 1:]:
        if run2 != run or (t2 - t).total_seconds() > 60:
            break
        if agent.get(s2) == "claude" and s2 != s:
            res[out2] += 1
            if out2.startswith("already"):
                print("  A taken for the one open: %s link to %s -> %s %s (a /btw of A, or a stale focus)"
                      % (t.strftime("%H:%M:%S"), s, t2.strftime("%H:%M:%S"), s2))
            break
print("  %s" % (dict(res) or "none"))

print()
print("pet runs since then: " + ", ".join("%s at %s" % (r, t[11:]) for t, r in starts if t >= since[:19]) or "none")
