"""Conversations in Nook (an AI terminal app that draws its own tabs and panes): the "at" line's fifth word
(NOOK_TERMINAL), kept across a restart, and where a click on such a circle goes: Nook, at that terminal, never the
Codex desktop app.  No pets shown, nothing clicked, Nook not started: the player's own functions on a stand-in family
(a visible window stands in for Nook's, nook_exe told so)."""
import ctypes, importlib.machinery, importlib.util, os, sys, tempfile, types

T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_l = importlib.machinery.SourceFileLoader("pet", os.path.join(T, "clawd_pet.pyw"))
_s = importlib.util.spec_from_loader("pet", _l)
pet = importlib.util.module_from_spec(_s)
_l.exec_module(pet)
fails = []


def check(name, ok, detail=''):
    print('%s %s %s' % ('ok  ' if ok else 'FAIL', name, detail), flush=True)
    if not ok:
        fails.append(name)


# the "at" line: up to five words after the session
tok, sid, more = pet.parse_token(b"at abcdef12 133700 codex - - 26284-3\n")
check('at line: its fifth word, the Nook terminal', (tok, sid, more) == ("at", "abcdef12", ("133700", "codex", "-", "-", "26284-3")), repr(more))
tok, sid, more = pet.parse_token(b"at abcdef12 133700 claude cli dbec3e68\n")
check('at line from elsewhere: as before', more == ("133700", "claude", "cli", "dbec3e68"), repr(more))

# a real visible window to stand in for Nook's
user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = ctypes.c_void_p
fg = user32.GetForegroundWindow() or 0
check('window_exe: the program of a window', bool(fg) and os.path.isfile(pet.window_exe(fg)), pet.window_exe(fg))
check('nook_exe: not Nook', pet.nook_exe(fg) == "" or os.path.basename(pet.window_exe(fg)).lower() == "nook.exe")
NOOK = r"C:\Apps\Nook\Nook.exe"
real_nook_exe = pet.nook_exe
pet.nook_exe = lambda h: NOOK if h == fg else real_nook_exe(h)


def family():
    f = types.SimpleNamespace(talk_where={}, talk_entry={}, talk_wt={}, talk_nook={}, talk_tab={}, talks={},
                              titles=types.SimpleNamespace(where={}, link=lambda *a: "codex://threads/x",
                                                           claude_kind=lambda s: None),
                              link_last=("", 0.0))
    f.talk_agent = lambda s, now=None: pet.Family.talk_agent(f, s, now)
    f._claude_kind = lambda s, now: pet.Family._claude_kind(f, s, now)
    f._codex_sort = lambda s, now: None
    f._link_moving = lambda link, now: False
    f._places_now = lambda: pet.Family._places_now(f)
    f._circles_back = lambda circles: None
    return f


f = family()
pet.Family.talk_event(f, "at", "abcdef12", (str(fg), "codex", "-", "-", "26284-3"), 0.0)
check('at line in Nook: its window and terminal kept', f.talk_where.get("abcdef12") == (fg, "codex") and f.talk_nook.get("abcdef12") == "26284-3",
      repr((f.talk_where, f.talk_nook)))
w = pet.Family._way(f, "abcdef12", 0.0)
check('Codex in Nook: to its terminal in Nook, no codex:// link', w["code"] == "nook" and w["nook"] == "26284-3" and w["exe"] == NOOK
      and w["link"] is None and w["kind"] == "term", repr(w))
check('... in words', pet.Family._way_text(f, w) == "切到它在 Nook 里的终端" and pet.Family._kind_text(f, w).endswith("(Nook)"),
      pet.Family._way_text(f, w) + " / " + pet.Family._kind_text(f, w))

f.talk_entry["c1aude00"] = "cli"
pet.Family.talk_event(f, "at", "c1aude00", (str(fg), "claude", "cli", "-"), 0.0)
w = pet.Family._way(f, "c1aude00", 0.0)
check('Claude in Nook, its terminal not told (an older hook): Nook all the same', w["code"] == "nook" and not w["nook"], repr(w))
check('... in words', pet.Family._way_text(f, w).startswith("拉 Nook 的窗口"), pet.Family._way_text(f, w))

pet.Family.talk_event(f, "at", "abcdef12", (str(fg), "codex", "-", "-", "26284-7"), 0.0)
check('a new terminal (resumed in another): the new one', f.talk_nook.get("abcdef12") == "26284-7")

# a restart: talks.json keeps the terminal
pet.HOME_DIR = tempfile.mkdtemp(prefix="clawd_nook_")
pet.Family._places_save(f)
g = family()
pet.Family._places_load(g)
check('after a restart: its Nook terminal still known', g.talk_nook.get("abcdef12") == "26284-7", repr(g.talk_nook))

pet.Family.talk_event(f, "bye", "abcdef12", (), 0.0)
check('bye: forgotten', "abcdef12" not in f.talk_nook)

print("all ok" if not fails else "FAILED: %s" % ", ".join(fails))
sys.exit(1 if fails else 0)
