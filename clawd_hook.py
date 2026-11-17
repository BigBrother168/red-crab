"""clawd_hook.py WORD [AGENT] [--at]: one hook of an agent, as a line in the pets' event file.

  WORD AGENT        ->  "WORD <session>"                    (what the pets know: listen, run, stop, ...)
  at AGENT          ->  "at <session> <window> AGENT <entry> <tab>"   (where that conversation is: for the numbered
                         circles; entry: Claude Code's CLAUDE_CODE_ENTRYPOINT, "claude-desktop" or "cli", which says
                         whether a click opens its desktop app or goes to its terminal; tab: WT_SESSION, the Windows
                         Terminal tab it runs in; "-" for none)
  WORD AGENT --at   ->  both lines

  Not you (2026-11-15): a UserPromptSubmit that is Code Mode handing a script's output back to Claude ("source":
  "poll_event") writes nothing, and a SessionStart after a compaction no "at" line: the window in front then may be any
  window (the pets read the Windows Terminal tab you typed in from the one in front).

The agent gives the hook one JSON object on stdin; only the start of it is read, and only the session id is taken
(8 characters of it: the first, or for Codex the last; see session_key).  Nothing else of it is kept: no command, no
file name, no prompt.

Claude Code and Codex run it for every word.  Claude Code runs it in exec form (clawd.py exec_hook: no shell): its
bash one-liners of before wrote nothing where Claude Code finds no Git Bash and runs hooks in PowerShell instead
(2026-11-14, the CLI here).  Standard library only; run it with python -I -S.  It never fails loudly: a hook must
not get in the agent's way.

  ag_start|ag_turn|ag_done|ag_stop antigravity  ->  Antigravity's events, translated here (AG_TOOLS): it waits for
                    each hook and wants a JSON answer, so the whole payload is read and "{}" is printed (an answer
                    that decides nothing).  Only the tool's name and the stop's reason are looked at, besides the id."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def data_home():
    """Where the pets read their events, found as clawd_pet.pyw finds it (default_home): CLAWD_HOME; this folder if
    a save is already here (a copy run from source); else %APPDATA%\\Clawd (an install)."""
    h = os.environ.get("CLAWD_HOME")
    if h:
        return h
    if os.path.exists(os.path.join(HERE, "state.json")) or os.path.exists(os.path.join(HERE, "grow.json")):
        return HERE
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Clawd")


HOME = data_home()
ID_FIELDS = ("session_id", "conversationId", "conversation_id", "thread_id")
SHELLS = ("explorer.exe",)             # an ancestor that is the desktop itself: not the conversation's window


def session_key(raw, agent=""):
    """The 8 characters the pets know a conversation by.  The first 8 of its id; a word before the id
    ("session-1a2b3c4d-...", as DeepSeek Harness names them) is not part of it.  Codex: the last 8, its ids being
    UUIDv7, whose first 8 are the time to about a minute: a conversation, the background jobs Codex runs beside it
    and its sub-agents, started in the same minute, had one key (2026-11-14: a job's end said bye for your
    conversation, which then had no window to go to)."""
    raw = re.sub(r"^[a-z]+[-_](?=[0-9a-f]{8})", "", raw or "", flags=re.I).lower()
    if agent == "codex" and re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", raw):
        return raw[-8:]
    sid = raw[:8]
    return sid if len(sid) == 8 and all(c in "0123456789abcdef-" for c in sid) else ""


def read_head():
    try:
        return os.read(0, 4096)
    except OSError:
        return b""


def session_id(agent="", head=None):
    head = (read_head() if head is None else head).decode("utf-8", "ignore")
    for field in ID_FIELDS:
        m = re.search(r'"%s"\s*:\s*"([^"]*)"' % field, head)
        if m:
            return session_key(m.group(1), agent)
    return ""


def payload(head, wait=1.5, limit=1 << 21):
    """The whole JSON object the agent gave, read on from head till it parses (never till stdin closes: an agent may
    leave it open), or None.  Only for the two words that say where a conversation is."""
    import json
    import threading
    box = [head]

    def more():
        while len(box[0]) < limit:
            try:
                json.loads(box[0].decode("utf-8", "ignore"))
                return
            except ValueError:
                pass
            try:
                chunk = os.read(0, 65536)
            except OSError:
                return
            if not chunk:
                return
            box[0] += chunk

    t = threading.Thread(target=more, daemon=True)
    t.start()
    t.join(wait)
    try:
        d = json.loads(box[0].decode("utf-8", "ignore"))
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def where_fields():
    """-> "<entry> <tab>" from the environment the agent runs its hooks in (Claude Code's CLAUDE_CODE_ENTRYPOINT,
    Windows Terminal's WT_SESSION), "-" for one not there"""
    entry = re.sub(r"[^a-z0-9_-]", "", os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").lower())[:24]
    tab = re.sub(r"[^0-9a-f-]", "", os.environ.get("WT_SESSION", "").lower())[:36]
    return "%s %s" % (entry or "-", tab or "-")


def window():
    """The window this conversation is in: the console's own if it shows, else the nearest ancestor process's
    that has a visible top-level window with a title (the terminal, the editor, the agent's desktop app).  In Git
    Bash's own window (mintty) the line of ancestors breaks (MSYS starts a program through a process gone by then,
    and its pseudo console's host is MSYS's too): then the Git Bash window in front (you just typed there), or the
    only one there is (2026-11-15)."""
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GetConsoleWindow.restype = wintypes.HWND
    h = k32.GetConsoleWindow()
    if h and u32.IsWindowVisible(wintypes.HWND(h)):
        return h
    console = h                                # (hidden: a pseudo console, as in a terminal's tab)

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = wintypes.HANDLE(k32.CreateToolhelp32Snapshot(2, 0))
    pe = PE()
    pe.dwSize = ctypes.sizeof(PE)
    procs = {}
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        procs[pe.th32ProcessID] = (pe.th32ParentProcessID, pe.szExeFile.lower())
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    wins = {}

    def each(hwnd, _):
        if u32.IsWindowVisible(hwnd) and u32.GetWindowTextLengthW(hwnd) and not u32.GetWindow(hwnd, 4):
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            wins.setdefault(pid.value, hwnd)
        return True

    u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(each), 0)
    pid, seen = os.getpid(), set()
    while pid in procs and pid not in seen and len(seen) < 32:
        seen.add(pid)
        parent, exe = procs[pid]
        if exe in SHELLS:
            return 0
        if pid in wins:
            return wins[pid]
        pid = parent
    if pid in procs or not console:
        return 0                               # the line did not break: no window of its own (a background job)
    minttys = [h for p, h in wins.items() if procs.get(p, (0, ""))[1] == "mintty.exe"]
    u32.GetForegroundWindow.restype = wintypes.HWND
    fg = u32.GetForegroundWindow()
    if fg and fg in minttys:
        return fg
    return minttys[0] if len(minttys) == 1 else 0


# ---- Antigravity (~/.gemini/config/hooks.json) ----
# Its hooks run one at a time and the agent waits for each, so it gets one hook per event (matcher "*") and the
# translation is here, from the tool's name (its step type, lower case).  No PreToolUse: Antigravity takes an answer
# without a decision as a denial (it blocked every tool), so a tool shows when it is done (ag_done: its word, then
# think).  It has no "you wrote" event: the first model call after a stop (PreInvocation) is a new turn, which this
# keeps in AG_TURNS: {id: [in a turn, when]}.  A sub-agent shows when it is back (agent_done), never when sent.
AG_TOOLS = (
    ("read", ("view_file", "view_file_outline", "view_content_chunk", "view_code_item", "list_directory", "list_dir",
              "grep_search", "find", "find_by_name", "find_all_references", "code_search", "read_notebook",
              "read_resource", "list_resources")),
    ("edit", ("code_action", "file_change", "propose_code", "write_to_file", "create_file", "edit_file",
              "replace_file_content", "multi_replace_file_content", "edit_notebook", "write_blob", "move",
              "delete_directory")),
    ("run", ("run_command", "send_command_input", "read_terminal", "command_status", "shell_exec", "execute_notebook")),
    ("web", ("search_web", "read_url_content", "open_browser_url", "read_browser_page", "list_browser_pages",
             "click_browser_pixel", "execute_browser_javascript", "browser_subagent")),
)
AG_SUBAGENT = "invoke_subagent"
AG_WEB_PREFIX = ("browser_", "capture_browser_")
AG_FAIL = ("ERROR", "MAX_TOKEN_BUDGET_EXCEEDED")          # a Stop for these: stopped by an error
AG_TURNS = os.path.join(HOME, "ag_turns.json")
AG_STALE = 600.0                                          # a turn with no hook this long never said stop (it crashed)


def ag_tool(name):
    name = (name or "").lower()
    for word, names in AG_TOOLS:
        if name in names:
            return word
    return "web" if name.startswith(AG_WEB_PREFIX) else None


def ag_words(event, data, sid, now):
    """Antigravity's event and payload -> (words to write, whether to add the window line).  Keeps AG_TURNS."""
    import json
    try:
        with open(AG_TURNS, "r", encoding="utf-8") as f:
            turns = json.load(f)
        if not isinstance(turns, dict):
            turns = {}
    except (OSError, ValueError):
        turns = {}
    was = turns.get(sid)
    if not (isinstance(was, list) and len(was) == 2 and isinstance(was[1], (int, float))):
        was = [0, 0]
    in_turn = bool(was[0]) and now - was[1] < AG_STALE
    words, at = [], False
    call = data.get("toolCall")
    tool = str(call.get("name") or "") if isinstance(call, dict) else ""
    if event == "ag_start":
        words, at = ["hello"], True
    elif event == "ag_turn":
        if not in_turn:
            words, at, in_turn = ["listen"], True, True
    elif event == "ag_done":
        if tool.lower() == AG_SUBAGENT:
            words = ["agent_done"]
        else:
            w = ag_tool(tool)
            words = ([w] if w else []) + ["fail" if data.get("error") else "think"]
        in_turn = True
    # (ag_tool, ag_post: the first install's PreToolUse and PostToolUse, gone; such a hook says nothing now)
    elif event == "ag_stop":
        reason = str(data.get("terminationReason") or "").upper()
        if reason == "USER_CANCELED":
            words = ["cut"]                # you stopped it: over without "done" (it worked on till your next message
                                           # or 10 minutes before, 2026-11-14)
        else:
            words = ["stopfail" if reason in AG_FAIL else "stop"]
        in_turn = False
    if sid:
        turns[sid] = [1 if in_turn else 0, now]
        turns = {k: v for k, v in turns.items()
                 if isinstance(v, list) and len(v) == 2 and isinstance(v[1], (int, float)) and now - v[1] < 86400}
        try:
            tmp = AG_TURNS + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(turns, f)
            os.replace(tmp, AG_TURNS)
        except OSError:
            try:
                os.makedirs(HOME, exist_ok=True)       # the pets never ran yet: next time it is kept
            except OSError:
                pass
    return words, at


def ag_main(event):
    """One Antigravity hook.  The whole payload is read (it waits for us to take it)."""
    import json
    import time
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "ignore") or "{}")
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    sid = data.get("conversationId")
    sid = sid[:8].lower() if isinstance(sid, str) else ""
    if not (len(sid) == 8 and all(c in "0123456789abcdef-" for c in sid)):
        return                             # not a payload we know: nothing is said (no turn could be kept for it)
    words, at = ag_words(event, data, sid, time.time())
    lines = ["%s %s" % (w, sid) for w in words]
    if at and sid:
        try:
            hwnd = window() or 0
        except Exception:
            hwnd = 0
        lines.append("at %s %d antigravity" % (sid, hwnd))
    write_lines(lines)


def write_lines(lines):
    """One write to the event file: whole lines also beside other hooks.  The home is made if the pets never ran."""
    if not lines:
        return
    data = ("\n".join(lines) + "\n").encode("ascii", "ignore")
    for _ in range(2):
        try:
            with open(os.path.join(HOME, "event"), "ab") as f:
                f.write(data)
            return
        except OSError:
            try:
                os.makedirs(HOME, exist_ok=True)
            except OSError:
                return


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("#")]
    also_at = "--at" in args
    args = [a for a in args if a != "--at"]
    word = args[0].lower() if args else ""
    agent = re.sub(r"[^a-z0-9_-]", "", args[1].lower())[:16] if len(args) > 1 else ""
    if not re.match(r"^[a-z_]{1,24}$", word):
        return 0
    if word.startswith("ag_"):
        ag_main(word)
        return 0
    head = read_head()
    sid = session_id(agent, head)
    if also_at and word in ("listen", "hello"):
        source = (payload(head) or {}).get("source")
        if word == "listen" and source == "poll_event":
            return 0                           # Code Mode handing Claude a script's output: not you, no new turn
        if word == "hello" and source == "compact":
            also_at = False                    # a compaction, maybe while you are in another window
    lines = []
    if word != "at":
        lines.append("%s %s" % (word, sid))
    if (word == "at" or also_at) and sid:
        try:
            hwnd = window() or 0
        except Exception:
            hwnd = 0
        lines.append("at %s %d %s %s" % (sid, hwnd, agent or "-", where_fields()))
    write_lines(lines)
    return 0


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception:
        pass
    if sys.argv[1:2] and sys.argv[1].startswith("ag_"):
        try:
            sys.stdout.write("{}")             # Antigravity reads a JSON answer from every hook: nothing to say
            sys.stdout.flush()
        except Exception:
            pass
    sys.exit(0)
