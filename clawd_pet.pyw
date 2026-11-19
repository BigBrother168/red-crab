# -*- coding: utf-8 -*-
"""
Clawd desktop pet - player, v2.

Pure standard library (ctypes / zlib / json / os / time / random / struct; subprocess and
shutil are imported only when a custom size is re-rendered or cleaned up).
Run with:  C:\\Python312\\pythonw.exe clawd_pet.pyw [--frames-dir DIR] [--debug]

Window   : Win32 layered popup (per-pixel alpha via UpdateLayeredWindow), topmost, no taskbar
           button, never takes focus; fully transparent pixels are click-through.
Frames   : <dir>/manifest.json (v1 or v2) + <action>.frames, kept zlib-compressed in memory
           (LRU capped, one buffer per action); one frame per tick is inflated and copied into a
           DIB section or, while the current size has no native set, into a buffer that GDI+
           scales (premultiplied alpha, SourceCopy, clamp wrap) into the DIB.
Sets     : frames/ (<dir>, 100 %), frames_hi/ (sibling of <dir>, one-time 300 % master),
           frames_custom/ (at most one, the last re-rendered size; re-rendered if it lacks a clip of
           the base set, i.e. it is from before new clips came).  Without a native set the
           player draws frames/ at or below 100 % and frames_hi/ above it, so the display factor
           is never > 1; only if frames_hi/ is missing or unusable does it stretch the current set.
           Sets line up by the alpha centroid of idle frame 0, not by the rounded manifest anchors
           (about 1 px apart between sets), so a swap at the same size does not move Clawd.
Size     : state.json "scale" 0.5..3.0 (Ctrl+wheel over Clawd, menu 大小, event size:<pct>).
           Resized at once with the feet kept in place; ~1.5 s after the last change clawd_scale.py
           ("re-render" in the log) scales frames/ (at or below 100 %) or frames_hi/ (above) down to a native
           set in frames_custom (hidden, below-normal priority, in a kill-on-close Job Object; on macOS under nice, in
           a process group of its own that is ended with it, and it stops by itself once the pet is gone), which is
           hot-swapped in.  No renderer: an install has no numpy (prerender.py only makes frames/ and frames_hi/).
           100 % and (with frames_hi/) 300 % are native: no re-render, frames_custom is deleted.
IME      : disabled for this process (ImmDisableIME); else a third-party IME such as Sogou gets
           loaded into it at some point and adds ~50 MB, for a window that takes no text.
Events   : <home>/event is append-only (a token and maybe a session id per line, UTF-8 or UTF-16);
           read from a remembered offset every ~150 ms (os.stat first).  Tokens: action names, Claude Code
           tokens listen think read edit run web agent agent_done compact compact_end stop fail
           stopfail attention hello bye, quit, size:<pct>, family:<n>, combo:<name>, lang:<zh|en>.
Work     : a tool's clip (work_*) is the busy clip while it runs and for TOOL_LINGER_SECS after, then think;
           it shows at least WORK_MIN_SECS;
           if tools change faster, only the latest is shown.  Stop, failures and attention cut in.
           Tool events after the turn's stop come from background agents: those keep Clawd busy
           only for BACKGROUND_BUSY_SECS after the last one, as no stop will follow them.
Mouse    : click -> wave/hop, double-click -> celebrate, 3 clicks within 2 s -> shy,
           drag (own capture-based drag, no system move loop, so no outline) -> dangle,
           release -> land, hover -> look_at_viewer (<= 1 per 10 s), Ctrl+wheel -> size,
           right-click -> menu.
Life     : idle extras every 6-15 s, wander every 30-70 s (50 %), sleep after 5 min alone.
Activity : quiet / normal / lively (state.json "activity", menus, token activity:<name>) scales the waits of the idle
           extras, walks, combos of their own and company at work by 2 / 1 / 0.6; quiet starts no combos of its own.
Edges    : the idle body stays inside the work area of its monitor (taskbar excluded), also while
           dragged, after a resize and when the display changes.  Dropped close to an edge, it glides
           onto that edge; on an edge it stays there across resizes.  Walking into a side edge it
           treads until the feet line up, turns around (turn_left/turn_right) and walks back.
           The walk has a direction (walk_left/walk_right); sets without these clips fall back to
           the plain walk.  Effects reaching outside the idle body may still be cut off at an edge.
Family   : up to three pets in one process (slots 0, 1, 2; slot 0 is the big one).  Their sizes keep
           the ratios FAMILY_RATIOS and change together; the smallest stops at SCALE_MIN and the
           others stop with it, the size asked for is remembered ("wanted").  Slot 0 follows the
           events.  The others live on their own, quieter while it works, sleep with it, and only
           show a short reaction to the events that do not come by the dozen (FOLLOWER_RULES).
           Each has its own re-rendered set (frames_custom, frames_custom_1, frames_custom_2),
           rendered one at a time.  Token family:<n> or the menu changes the number of pets.
Combos   : actions of several pets, run by Family: they walk to each other (also at a slant), then
           play in sync.  They come by themselves every 2-4 minutes when all are idle, while the big
           one works long (peek) or sleeps (wake), after turns, at failures (comfort) and when a
           sub-agent is done (a small one brings the big one a note, which it reads without stopping
           work); or from the menu, combo:<name>, or dropping one pet on another (on its head: a tower).
           A clip under way is never cut, except that a tower that breaks up comes down at once.
Chores   : (差事, docs/差事设计.md) Family.chore() reads what each one is up to off its state, ranked (R_*): your hand >
           work, questions and the sign > the whole family's cheer (a long turn, a level-up) > the cursor's 小剧场 (from
           the moment it is picked) > a reaction sent to one (comfort, a note, a pat) > a small reaction > games of their
           own > keeping the big one company > idle life.  Only a higher rank takes one; the others look for another
           pet or let it be: a sign goes to a small one with nothing to do or over the big one's head, a small reaction
           never wakes a doze.  Taken, it winds down first (a start, the stick down, the copied tool's outro);
           your hand takes it at once.  pet.log says what was cut short by what.  The shows of their own (games,
           copying, coming to watch) keep SHOW_GAP x the activity pace between them.
Tower    : (stack) the bigger ones brace (stack_brace, the head does not move), the smaller ones jump
           up (stack_hop: the window flies on an arc between HOP_TAKEOFF and HOP_LAND), the top one
           cheers, and they jump down again.  One up there is drawn in front of the one below, and is
           saved where it jumped up from.  Dragged, clicked, resized or at work: it comes down.
Note     : (note) carry_start, walk_carry, carry_hold, then give and receive start on one clock, so the
           note changes hands at the same moment in both windows.
Leapfrog : (leapfrog) the bigger one ducks (leap_crouch), the smaller one flies over its head on a high
           stack_hop arc, started on the ducking one's clock; then the other way round.  The two small
           ones if they are free, else the big one with a small one.  In the air it is drawn in front.
Company  : while the big one works, a small one now and then copies its tool for a few seconds, or
           comes over to watch; every 2-4 minutes the two small ones play a game by themselves
           (leapfrog, a high five, a note), near where they are.  After a combo the small ones walk
           back to where they stood, also while the big one works; only one that came to watch stays
           until the work is done.
Depth    : the lower the feet on the screen, the nearer: that pet is drawn in front, so one can stand
           behind another.  Only two on one row (feet at about the same height) count as colliding:
           they do not walk into each other, and if they overlap the smaller one walks aside.
Tray     : an icon in the notification area (Tray, on a hidden window titled ClawdTray): a click hides or shows
           the family, its menu has hide/show, back to the corner, the album, activity, connect AI, start with
           Windows, the releases page in the browser (RELEASES_URL) and quit; re-added on TaskbarCreated.
Hidden   : (token hide/show, the tray, the pet menu) the windows are hidden, nothing is drawn; the big one still
           reads the events (busy, questions), the timers tick slowly, signs, combos and reactions stop.  Shown
           again, each plays what it is up to now.  clawd do <action/combo> shows them first.  Not kept over a restart.
Treasures: (翻找, 养成第 4 轮) clips rummage_in / rummage (a loop) / rummage_found / rummage_none / rummage_up; Pet.dig while one
           digs, Family.dig_tick starts one small pet each DIG_EVERY s of a turn's work time (dig_cap of the level a
           turn at most, a show like the others, rank R_RUMMAGE), Family.dig_by_hand any of them at once (the menu, clawd do rummage; rank R_HAND, the next work
           event ends it through rummage_up).  What comes up: Family.dig_result (Grow.roll: rarity, dry runs, new ones
           first; a special treasure for what the turn's work was).  By itself: Family.loot, counted when the turn
           ends; by hand: at once, for one of the chances work earns (one each DIG_CHANCE_WORK s of work time,
           Family.work_tick; "chances", "chance_secs" in grow.json).  The treasure is not in the pets' frames: ItemOverlay lays its icon (its
           own little loop) over the arm's tip and its glow, in the rarity's colour, behind the pet, where the clip's "item" list in the manifest says.
Play     : (把玩, 养成第 7 轮) Family.play_item: a treasure they have is taken out from behind the back, played with and
           put away: its own clip play_<treasure>, with the treasure drawn into the frames (held by the arm's tip, behind
           the body while the arm is behind the back, of the pet's size); in a frame set from before those, its way in
           PLAY_WAY (play_look / play_toss / play_listen / play_show) with the treasure laid on like a find.  By hand (the menu's 把玩, token play[:<treasure>] from the album and clawd do): R_HAND, at once;
           by itself: now and then an idle extra (PLAY_ALONE_CHANCE), only while all is quiet, one of them at a time.
Growth   : (养成, class Grow, <home>/grow.json) one pool of XP for the family (GROW_XP): a turn that used tools,
           a fix after a failed tool, a sub-agent back, a combo played to its end the first time, a little for
           play (at most once in GROW_PLAY_GAP).  Every combo played to its end is counted ("combos"): a star at
           each of GROW_STARS (XP, a mint board); one you set up by hand (dropped on another, patted after a
           throw) a little XP, once in GROW_HAND_GAP.  Every clip that begins is written down once ("acts",
           Family.grow_act); the nine of GROW_ACTS are finds (XP, a mint board).  A new level: once the big one is calm after the turn's reaction,
           celebrate_all (or a solo cheer) and a gold board; a first find: a mint board after the combo.  Growth
           boards rank with the tool boards, so work boards take their place.  Saved at most once a minute (at
           once on a level, on the way out), the day before's file kept as grow.json.bak; one writer per file.
State    : <home>/state.json {"x","y","scale","wanted","slots","pos"}; x/y is the FEET point of the
           big one on screen, scale its size, slots the other pets shown, pos their feet points;
           "hidden" while hidden (for clawd status).
Instance : named mutex Local\\ClawdDesktopPet; a second copy exits at once.
Errors   : <home>/pet.log (size capped).
Home     : <home> (default_home): CLAWD_HOME if set; this script's folder if a save (state.json, grow.json) is
           already there; else %APPDATA%\\Clawd, with the scaled frame sets (frames_custom*, render.log) beside
           this script if it can write there, else in %LOCALAPPDATA%\\Clawd.  --home DIR puts all of it in DIR.
           On macOS ~/Library/Application Support/Clawd and ~/Library/Caches/Clawd, never inside RedCrab.app.
           frames/ and frames_hi/ stay beside this script.  A scaled set keeps its source's set_stamp and is
           scaled again when that changes (an update with new art).

Test-only options:
  --debug                 log every action change / event to pet.log
  --home DIR              use DIR instead of the home for event/state/log/frames_custom
                          (with its own mutex); frames/frames_hi still come from --frames-dir;
                          no tray icon unless --tray
  --tray                  a tray icon also for a --home instance
  --extra-interval A-B    idle extras interval in s (default 6-15)
  --wander-interval A-B   wander check interval in s (default 30-70)
  --sleep-after S         fall asleep after S s without interaction (default 300)
  --combo-interval A-B    s between combos of their own while idle (default 120-240)
  --peek-after S          s the big one works before a small one comes to watch (default 15)
  --wake-after A-B        s asleep before a small one may wake the big one (default 240-720)
  --mimic-interval A-B    s between a small one copying the big one's tool (default 30-60)
  --return-after A-B      s after a combo before the small ones walk back (default 4-10)
  --play-interval A-B     s between games of the two small ones while the big one works (default 120-240)
  --play-after S          s the big one works before the first game (default 30)
  --show-gap S            s between two shows of their own (games, copying, watching) at normal activity (default 20)
  --grow-quiet            XP is counted, but no growth board and no level-up cheer (tests of other things)
  --dig-every S           s of a turn's work time for each dig by itself (default 120; with --debug: never, unless given)
  --dig-find X            every dig finds something (yes), nothing (no) or this treasure (tests)
  --slip X                the 小插曲 of a combo always (yes) or never (no) (tests)
  --dig-most N            digs by itself a turn at most (default: the chances that can be kept at the level)
  --chance-work S         s of work time for a chance to dig by hand (default 600; with --debug: each whole turn one, unless given)
  --play-alone P          the chance an idle extra is a treasure taken out to play with (default 0.08)
  --dump-dir DIR          write the presented bitmap (raw BGRA) after every resize and on
                          the token "dump" (only accepted together with this option)
"""
import colorsys
import ctypes
import json
import math
import os
import random
import re
import struct
import sys
import time
import traceback
import zlib

MAC = sys.platform == "darwin"
if MAC:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from clawd_mac import win32 as _mac_win32  # Win32 over AppKit: clawd_mac/README.md
    _mac_win32.install()
    from clawd_mac import system as macsys     # what the shim does not do: saves, login item, apps by pid, links

# --------------------------------------------------------------------------- paths
HERE = os.path.dirname(os.path.abspath(__file__))       # the program: scripts, frames/, frames_hi/
BASE_FRAMES_DIR = os.path.join(HERE, "frames")
SCALE_SCRIPT = os.path.join(HERE, "clawd_scale.py")     # makes the sets of other sizes (no renderer in an install)
APP_DIR_NAME = "Clawd"
HOME_DIR = CACHE_DIR = EVENT_PATH = STATE_PATH = GROW_PATH = LOG_PATH = CUSTOM_DIR = RENDER_LOG = None


def default_home():
    """-> (home, cache).  The home holds what the pets keep (event, state, saves, log): CLAWD_HOME if set; the
    program's folder if a save is already there (a copy run from source, as before); else %APPDATA%\\Clawd (an install,
    whose folder holds only the program).  clawd.py, clawd_hook.py, clawd_album.pyw and clawd_dsh.mjs look the same
    way.  The cache (the frame sets scaled to other sizes) beside an %APPDATA% home is the program's folder when it
    can be written to (an install on D: leaves C: alone), else %LOCALAPPDATA%\\Clawd (an install for all users, in
    Program Files); with any other home, the home itself.  On macOS ~/Library/Application Support/Clawd and
    ~/Library/Caches/Clawd (clawd_mac.system), and never inside RedCrab.app: a file written there breaks its
    signature (so there no save is looked for, and its folder is not even tried for writing)."""
    h = os.environ.get("CLAWD_HOME")
    if h:
        return h, h
    bundled = MAC and macsys.app_bundle(HERE) is not None
    if not bundled and any(os.path.exists(os.path.join(HERE, n)) for n in ("state.json", "grow.json")):
        return HERE, HERE
    if MAC:
        return macsys.home_dir(), (HERE if not bundled and writable(HERE) else macsys.cache_dir())
    roam = os.environ.get("APPDATA") or os.path.expanduser("~")
    if writable(HERE):
        return os.path.join(roam, APP_DIR_NAME), HERE
    return os.path.join(roam, APP_DIR_NAME), os.path.join(os.environ.get("LOCALAPPDATA") or roam, APP_DIR_NAME)


def writable(d):
    """A file can be made in d (Program Files without admin rights: no)."""
    p = os.path.join(d, "clawd-write-test.tmp")
    try:
        os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return os.path.isfile(p)               # one left behind by a crash: written once, so writable
    try:
        os.remove(p)
    except OSError:
        pass
    return True


def set_home(home, cache=None):
    global HOME_DIR, CACHE_DIR, EVENT_PATH, STATE_PATH, GROW_PATH, LOG_PATH, CUSTOM_DIR, RENDER_LOG
    HOME_DIR = os.path.abspath(home)
    CACHE_DIR = os.path.abspath(cache or home)
    EVENT_PATH = os.path.join(HOME_DIR, "event")
    STATE_PATH = os.path.join(HOME_DIR, "state.json")
    GROW_PATH = os.path.join(HOME_DIR, "grow.json")
    LOG_PATH = os.path.join(HOME_DIR, "pet.log")
    CUSTOM_DIR = os.path.join(CACHE_DIR, "frames_custom")
    RENDER_LOG = os.path.join(CACHE_DIR, "render.log")


set_home(*default_home())
MUTEX_NAME = "Local\\ClawdDesktopPet"
CLASS_NAME = "ClawdDesktopPetWindow"

# --------------------------------------------------------------------------- behaviour
ACTION_ORDER = [
    "idle", "listen", "think", "nod", "thumbs_up", "confused", "shrug_sweat", "aha",
    "celebrate", "wave", "hop", "surprised", "head_tilt", "wink", "look_at_viewer",
    "proud", "shake_head", "tiptoe_peek", "sleep", "doze", "walk", "dangle", "land", "shy",
    "work_read", "work_edit", "work_run", "work_web", "work_compact", "work_agent",
]
LANGS = (("zh", "中文"), ("en", "English"))
LANG = "zh"                 # state.json "lang", the menu or token lang:<code>
# how often they find something to do by themselves: idle extras, walks, combos of their own, company at work.
# Not the work clips, signs, reactions to events or what the user asks for.  Quiet: no combos of their own at all.
ACTIVITIES = (("quiet", "安静", "Quiet"), ("normal", "正常", "Normal"), ("lively", "活泼", "Lively"))
ACTIVITY_PACE = {"quiet": 2.0, "normal": 1.0, "lively": 0.6}   # x the waits between them
ACTIVITY = "normal"         # state.json "activity", the menu or token activity:<name>


def proto_strings(b, wanted):
    """-> the strings (ASCII) of these top-level fields of a protobuf message, None where absent (or not readable)."""
    got = {}
    i, n = 0, len(b)
    try:
        while i < n:
            key = sh = 0
            while True:
                c = b[i]; i += 1; key |= (c & 0x7f) << sh; sh += 7
                if c < 0x80:
                    break
            f, wt = key >> 3, key & 7
            if wt == 0:
                while b[i] & 0x80:
                    i += 1
                i += 1
            elif wt == 2:
                size = sh = 0
                while True:
                    c = b[i]; i += 1; size |= (c & 0x7f) << sh; sh += 7
                    if c < 0x80:
                        break
                if f in wanted and f not in got:
                    got[f] = b[i:i + size].decode("ascii", "replace")
                i += size
            elif wt == 5:
                i += 4
            elif wt == 1:
                i += 8
            else:
                break
    except IndexError:
        pass
    return tuple(got.get(f) for f in wanted)


def paced(rng):
    k = ACTIVITY_PACE[ACTIVITY]
    return (rng[0] * k, rng[1] * k)
EN_LABELS = {
    "idle": "Idle", "listen": "Listening", "think": "Thinking", "nod": "Nod", "thumbs_up": "Thumbs up",
    "confused": "Confused", "shrug_sweat": "Shrug", "aha": "Aha", "celebrate": "Celebrate", "wave": "Wave",
    "hop": "Happy hop", "surprised": "Startled", "head_tilt": "Head tilt", "wink": "Wink",
    "look_at_viewer": "Look at you", "proud": "Hands on hips", "shake_head": "Shake head",
    "tiptoe_peek": "Tiptoe peek", "sleep": "Sleep", "walk": "Walk", "work_read": "Magnifier",
    "work_edit": "Typing", "work_run": "Terminal", "work_web": "Telescope", "work_compact": "Tidy up memory",
    "work_agent": "Paper plane", "dangle": "Dangle", "land": "Land", "shy": "Shy", "wake_up": "Wake up", "dizzy": "Dizzy", "doze": "Doze",
}
EN_COMBOS = {"high_five": "High five", "celebrate_all": "Family cheer", "peek": "Come and look", "wake": "Nudge awake",
             "parade": "Parade", "comfort": "Comfort", "stack": "Tower", "note": "Pass a note", "leapfrog": "Leapfrog"}


def tr(zh, en):
    return en if LANG == "en" else zh


def plural(n, word):
    """English words with a count: 1 find, 2 finds (the album and clawd.py use it too)."""
    return "%d %s" % (n, word if n == 1 else word + "s")


DEFAULT_LABELS = {
    "idle": "待机", "listen": "认真听", "think": "想一想", "nod": "点头",
    "thumbs_up": "点赞", "confused": "困惑", "shrug_sweat": "摊手流汗",
    "aha": "恍然大悟", "celebrate": "庆祝", "wave": "挥手", "hop": "开心小跳",
    "surprised": "吓一跳", "head_tilt": "歪头", "wink": "眨眼",
    "look_at_viewer": "看向你", "proud": "叉腰", "shake_head": "摇头",
    "tiptoe_peek": "踮脚看", "sleep": "睡觉", "walk": "走路", "dangle": "被拎起来",
    "land": "落地", "shy": "害羞", "work_read": "放大镜", "work_edit": "打字",
    "work_run": "跑命令", "work_web": "望远镜", "work_compact": "整理记忆", "work_agent": "纸飞机",
}
IDLE_NAME = "idle"
TOOL_CLIPS = {"read": "work_read", "edit": "work_edit", "run": "work_run", "web": "work_web"}
WORK_HOLDS = ("work_read", "work_edit", "work_run", "work_web", "work_compact")
SIGN_CLIPS = ("sign_left", "sign_right")       # a small one holds up a stick; the player puts the board on top
HOLD_ACTIONS = ("think", "listen") + WORK_HOLDS + SIGN_CLIPS   # one-shots shown as intro -> hold -> outro
# holds that repeat exactly after this many frames loop forward; the others ping-pong (run backwards,
# flying code and terminal output would look wrong).  Matches WORK_LOOP in prerender.py.  A sign is
# still while held: any frame of it will do, so it leaves straight from the end of the still part.
HOLD_LOOP_FRAMES = {"work_read": 24, "work_edit": 24, "work_run": 24, "work_compact": 24, "sign_left": 1, "sign_right": 1}
# what a sign says (zh, en); "stop" adds how long the turn took
SIGN_TEXTS = {"read": ("在读文件", "Reading"), "edit": ("在改代码", "Editing"), "run": ("在跑命令", "Running"),
              "web": ("在查资料", "Searching"), "agent": ("派了帮手", "Helper sent"),
              "compact": ("整理记忆中", "Tidying memory"), "attention": ("等你回复", "Your turn"),
              "stop": ("做完了！", "Done!"), "stopfail": ("出错停下了", "Stopped: error"),
              "think": ("在想…", "Thinking…"), "look": ("新牌子！", "New look!"),
              "hint": ("右键点我有菜单", "Right-click me: a menu")}
SIGN_TOOLS = ("read", "edit", "run", "web", "agent")
SIGN_RANK = {"read": 1, "edit": 1, "run": 1, "web": 1, "agent": 1, "think": 1, "compact": 2, "stop": 2, "stopfail": 2,
             "attention": 3, "levelup": 1, "discover": 1, "gift": 1, "look": 1, "hint": 1}
                            # the growth signs (words in args), a new look of the signs and the first start's hint:
                            # any work sign takes their place
SIGN_LOOK_SECS = 3.0        # a new look (chosen in the 图鉴) is held up this long
FIRST_START_AFTER = 2.0     # s after the very first start (no state.json yet): the hint sign and the connect window
SIGN_HINT_SECS = 10.0       # the hint is held up this long
GIFT_AFTER = 1.0            # s after a level-up's sign is down before its gift's
SIGN_TOOL_SECS = 3.0        # a tool's sign is held this long (from when it is up) ...
SIGN_DONE_SECS = 4.0        # ... the end of a turn or an error this long; a question and a compact as long as they last
SIGN_THINK_AFTER = 8.0      # s of thinking with no tool (or since your message) before "thinking..." goes up ...
SIGN_THINK_EVERY = 30.0     # ... and again this often while it goes on
SIGN_GAP = 4.0              # s after a tool's sign is down before another one goes up (the others: at once)
SIGN_FADE_SECS = 0.15       # the board fades in once the stick is up and out before it comes down
ITEM_TITLE = "ClawdItem"    # a find at an arm's tip, and its glow (two small windows of their own)
SIGN_TITLE = "ClawdSign"    # the board's window (tests leave it out when they count the pets)
# graceful fallbacks while a frame set lacks the v2 actions
SHOT_FALLBACK = {"dangle": "surprised", "land": "nod", "shy": "wink", "sleep": "idle", "walk": "idle"}
IDLE_EXTRAS = ("wink", "look_at_viewer", "tiptoe_peek", "hop", "proud")
CLICK_ACTIONS = ("wave", "hop")
DOUBLE_CLICK_ACTION = "celebrate"
SEMANTIC = ("listen", "think", "stop", "fail", "stopfail", "attention", "hello", "bye",
            "agent", "agent_done", "compact", "compact_end") + tuple(TOOL_CLIPS)
WANDER = "\x00wander"                  # internal marker in the idle-extra slot
PLAY_ALONE = "\x00play"                # ... and for playing with a treasure by itself
# played by the walk logic only: not in the menu, not accepted as event tokens
COMBO_CLIPS = ("high_five_left", "high_five_right", "high_five_up_left", "high_five_up_right", "nudge_left", "nudge_right", "peek_left", "peek_right", "comfort_left", "comfort_right",
               "stack_brace", "stack_hop", "stack_top", "carry_start_left", "carry_start_right", "walk_carry_left", "walk_carry_right",
               "carry_hold_left", "carry_hold_right", "leap_crouch", "slip_sit_left", "slip_sit_right", "slip_roll_left",
               "slip_roll_right", "stack_flip_left", "stack_flip_right") + tuple("%s_%s%s" % (a, k, d) for a in ("give", "receive")
                                                              for k in ("", "mid_", "small_") for d in ("left", "right"))
THROW_CLIPS = ("tumble_left", "tumble_right", "squash")   # in the air, and each hit on the floor
DOZE_CLIPS = ("doze_in", "doze", "doze_startle", "doze_up", "doze_sleep")   # 鼠标小剧场: sits down, dozes, startled awake (by hand: gets up)
NAP_LOOKS = ("nap_look_left", "nap_look_right")   # ... first it looks over to the cursor's side
DIG_CLIPS = ("rummage_in", "rummage", "rummage_found", "rummage_none", "rummage_up")   # 翻找: down, digging (a loop), a find, nothing, cut short
PLAY_CLIPS = ("play_look", "play_toss", "play_listen", "play_show")   # 把玩: four ways to play with a treasure, for now shared
ITEM_CLIPS = ("rummage_found", "pull_out", "present") + PLAY_CLIPS   # a find is held in these: the manifest says where, frame by frame
DIG_MORE = ("rummage_spur", "rummage_fast")    # you lend a hand: a start, and it digs harder (a frame set without them digs as before)
DIG_ALL = DIG_CLIPS + DIG_MORE
DIG_LOOP_CLIPS = ("rummage", "rummage_fast")
# 交宝贝: a find carried to the big one and handed over (as a note is; the find itself is the player's overlay)
BRING_CLIPS = tuple(n + d for d in ("left", "right") for n in ("bring_start_", "bring_hold_", "walk_bring_", "hand_mid_", "hand_small_", "take_"))
INTERNAL_ACTIONS = ("walk_left", "walk_right", "turn_left", "turn_right", "wake_up") + COMBO_CLIPS + SIGN_CLIPS + THROW_CLIPS + ("doze_in", "doze_startle", "doze_up", "doze_sleep") + NAP_LOOKS + DIG_ALL + BRING_CLIPS + ("pull_out", "present") + PLAY_CLIPS



def internal(name):
    """Not one to ask for by name (the menu's actions, clawd do): a part of something else, or a treasure's play."""
    return name in INTERNAL_ACTIONS or name.startswith("play_")


HOLD_RANGE = (0.2, 0.82)    # fractions of a hold action ping-ponged while it lasts
BUSY_TIMEOUT = 600.0        # s; safety net if a turn never reports stop
BUSY_TOOL_TIMEOUT = 3600.0  # ... but while a tool it began has not ended (a long command says nothing meanwhile) it
                            # works on up to this long after its last event (round 9; Esc and a closed window are seen
                            # by themselves: the transcript, the window)
BACKGROUND_BUSY_SECS = 20.0 # s; busy after the last tool event of a background agent (no stop follows)
WORK_MIN_SECS = 2.5         # a work clip shows at least this long before the next one
TOOL_LINGER_SECS = 6.0      # a tool's clip stays this long after the tool ended: a search takes a moment, the answer long
ATTENTION_TIMEOUT = 120.0
FAIL_WINDOW, FAIL_MIN, CONFUSED_COOLDOWN = 60.0, 2, 30.0
FINISH_REACTIONS = ((20.0, "hop"), (120.0, "thumbs_up"), (float("inf"), "celebrate"))
MANUAL_LOOP_SECS = 8.0      # manual sleep / walk / dangle ... then back to normal
MANUAL_HOLD_SECS = 3.0      # manual think / listen from the menu
EXTRA_RANGE = (6.0, 15.0)
EXTRA_SEAM_WAIT = 3.0       # s to wait for a seamless idle frame before an extra
WANDER_RANGE = (30.0, 70.0)
WANDER_CHANCE = 0.5
WANDER_DIST = (60.0, 200.0) # px at scale 1
WANDER_AREA = 1.2           # of its body, each way: a walk of its own stays this near where the user put it
WALK_CLIP_SPEED = 40.0      # px/s at scale 1 that the walk clip was drawn for; faster walks play it faster
WANDER_SPEED = 64.0         # px/s at scale 1 of a walk of its own
WALK_SEAM = 12              # walk frames between poses equal to frame 0, where a turn can join
SNAP_FRACTION = 0.2         # dropped this close to an edge (fraction of the body px) ...
SNAP_MIN, SNAP_MAX = 16, 48 # ... limited to this many px: snap onto it
GLIDE_SECS = 0.18           # the snap is a short glide, not a jump
# thrown: let go while the cursor still moves fast, it flies, bounces off the sides, falls to the bottom line
THROW_SAMPLE_SECS = 0.05    # the cursor's speed over the last this long of its moves (a fling is a short push)
THROW_KEEP_MS = 300         # the drag's trail keeps this much
THROW_STALE_SECS = 0.08     # the cursor stood still this long before the release: a drop (a touchpad stops first)
THROW_MIN_SPEED = 0.8       # x the work area's height per second; slower is a drop (the user's softest fling: 0.75)
THROW_MAX_SPEED = 3.2       # x the work area's height per second; faster is cut down to this
THROW_GRAVITY = 2.6         # x the work area's height per second squared
THROW_WALL = 0.55           # what is left of the speed off a side or the top
THROW_BOUNCES = ((0.30, 0.55), (0.12, 0.5))   # each bounce: (height, x its body), what is left of the sideways speed
THROW_MAX_SECS = 5.0        # in the air at most this long (safety)
THROW_TICK_MS = 15          # the timer while it flies: the window moves smoothly
LAND_CLIPS = ("squash", "land")     # each hit on the floor: the first one there is
DIZZY_CLIPS = ("dizzy", "confused") # then a moment dizzy
FLUSH_PX = 3                # this close to an edge counts as being on it (kept across resizes)
THUMB_REACH = 0.36          # thumbs_up reaches this far (of the body px) past the idle body's right
HOVER_COOLDOWN = 10.0
SLEEP_AFTER = 300.0
SHY_CLICKS, SHY_WINDOW = 3, 2.0
# 鼠标小剧场: the cursor rests near one of them; it looks over, comes a little closer, sits down and dozes off.
# The cursor moving on startles it awake.  A reaction to the user (not one of their own pastimes): the same at
# every activity level, and not counted as an interaction (the family still falls asleep after SLEEP_AFTER).
NAP_TICK = 0.25             # s between cursor reads (not while hidden)
NAP_STILL_PX = 6            # the cursor this near where it stopped: still (a hand on the mouse trembles a little)
NAP_NEAR = 3.0              # of its body px, from the middle of its body: the cursor is near this one
NAP_TIMES = (3.0, 5.0, 8.0)     # s of a still cursor: looks over, comes closer, sits down and dozes
NAP_STEP = 0.5              # of its body px: how much closer it comes (never past the cursor, never out of its area)
NAP_PACE = 1.6              # of WALK_CLIP_SPEED: an unhurried few steps
NAP_REST = 15.0             # s after a startle before the next 小剧场 (one each time the cursor stops, at most)
NAP_ALONE = 40.0            # s it dozes on once the cursor has gone elsewhere (a move far away does not wake it), then gets up
DOZE_MANUAL_LOOPS = 2       # 打瞌睡 from the menu or clawd do: this many nods (~8 s), then it stretches and gets up
DRAG_THRESHOLD = 4          # px
DRAG_POLL_MS = 15           # fallback cursor poll while dragging (only if capture is lost)
MARGIN = 24                 # px from the work-area corner
SCALE_MIN, SCALE_MAX = 0.5, 3.0
FAMILY_RATIOS = (1.0, 0.8, 0.6)   # size of each slot, of the big one's
# what the big one did -> (clip of the others, one of them at random or all).  Tool events are not here:
# they come by the dozen, and the work is the big one's to show.  The longer the turn, the bigger the joy.
FOLLOWER_RULES = {
    "listen": ("look_at_viewer", "one"), "attention": ("wave", "one"),
    "agent": ("tiptoe_peek", "one"), "agent_done": ("nod", "one"),
    "stopfail": ("surprised", "all"), "hello": ("wave", "all"), "bye": ("wave", "all"),
    ("stop", "hop"): ("hop", "one"), ("stop", "thumbs_up"): ("hop", "all"), ("stop", "celebrate"): ("celebrate", "all"),
    ("fail", "surprised"): ("surprised", "one"), ("fail", "confused"): ("surprised", "all"),
}
FOLLOWER_STAGGER = 0.25     # s between the reactions, so they do not jump as one
FOLLOWER_COOLDOWN = 3.0     # s; the same event again this soon gets no reaction
QUIET_EXTRA_CHANCE = 0.5    # of the idle extras a small one still does while the big one works
COMBOS = {"high_five": "击掌", "celebrate_all": "全家庆祝", "peek": "凑过来看", "wake": "拱醒", "parade": "排排走", "comfort": "一起安慰",
          "stack": "叠罗汉", "note": "传纸条", "leapfrog": "跳山羊"}
# the 图鉴's cells (clawd_album.pyw shows the same): the treasures of the frame set, these combos (each one you can
# start yourself: the menu's, and the pat after a throw; who plays it does not matter), the nine special actions, the
# menu's actions and these two.  How much of it is found: at these marks the family cheers once (XP).
ALBUM_COMBOS = tuple(COMBOS) + ("console",)
ALBUM_ACTS_EXTRA = ("rummage", "wake_up")
ALBUM_MARKS = ((10, 10), (25, 20), (50, 30), (75, 40), (100, 60))     # % found, XP

# 等级礼物 (养成规划 第四节): what a level brings, up to LEVEL_MAX (no more after it).  (level, id, its name, a line
# about it), each in Chinese and English.  The 图鉴's 礼物 page shows the whole road; a level-up holds up its gift
# after the level's sign, and one reached before the gift was there (an old family, a new version) is 补发 once.
# GIFTS_LATER: on the road already, given once they are made (none left).  The monument: the numbers of the day the
# family got there, kept (grow.json "monument", MONUMENT_KEYS) and never changed after; the 图鉴's 全家 page shows it.
LEVEL_MAX = 20
LEVEL_GIFTS = (
    (3, "chalk_pink", ("粉色粉笔", "Pink chalk"), ("牌子上的字可以换成粉色。", "The words on the signs can be pink.")),
    (5, "dig_4", ("翻找机会存 4 次", "Keep 4 digs"), ("翻找机会最多能存 4 次，原来是 3 次。", "Up to 4 digs can be kept (3 before).")),
    (7, "frame_dots", ("彩点外框", "Dotted frame"), ("牌子的木框可以换成一圈彩色小圆点。", "The signs' frame can be one of coloured dots.")),
    (10, "items_2", ("宝贝第二批", "More treasures"), ("一批新宝贝加进翻找里。", "A new batch of treasures to dig up.")),
    (12, "chalk_blue", ("蓝色粉笔", "Blue chalk"), ("牌子上的字可以换成蓝色。", "The words on the signs can be blue.")),
    (14, "frame_stars", ("星星外框", "Starry frame"), ("牌子的框可以换成缀着星星的深蓝色。", "The signs' frame can be deep blue with stars.")),
    (16, "slips", ("意外的小插曲", "Little surprises"), ("击掌偶尔扑个空，跳山羊偶尔一个跟头滚过去，叠罗汉偶尔翻着跟头下来。碰上算新发现。", "A high five may miss, a leapfrog may roll over, the tower's top may flip down. Each is a find.")),
    (16, "dig_5", ("翻找机会存 5 次", "Keep 5 digs"), ("翻找机会最多能存 5 次。", "Up to 5 digs can be kept.")),
    (18, "board_flag", ("小旗牌子", "Banner signs"), ("牌子可以换成两头剪了燕尾的小旗。", "The signs can be little banners with forked ends.")),
    (20, "monument", ("满级纪念碑", "The monument"), ("全家庆祝，图鉴里立一块碑，刻着你们一起走过的日子。", "The family cheers; a monument in the album keeps the days you went through together.")),
    (20, "chalk_gold", ("金色粉笔", "Gold chalk"), ("牌子上的字可以换成金色。", "The words on the signs can be gold.")),
)
GIFTS_LATER = ()
MONUMENT_KEYS = ("since", "day", "days", "turns", "work_secs", "things", "kinds", "played", "agents", "fixes", "plays", "xp")
# 小插曲 (the gift "slips"): from its level on, a combo now and then goes another way.  combo -> (its clip, its name).
# Each is a find the first time (a sign, XP like a special action's); the combo counts as played all the same.
SLIPS = {"high_five": ("slip_sit", ("击掌扑空", "A high five missed")),
         "leapfrog": ("slip_roll", ("滚了过去", "Head over heels")),
         "stack": ("stack_flip", ("翻着跟头下来", "Down with a flip"))}
SLIP_CHANCE = 0.1           # of these combos that go the other way ...
SLIP_DRY = 12               # ... and after this many in a row that did not, the next one does
FLIP_OFF, FLIP_LAND = 0.35, 1.05     # s into stack_flip: in the air between these (stack_hop: HOP_TAKEOFF, HOP_LAND)
ROLL_OFF, ROLL_LAND = 0.12, 0.92     # s into slip_roll: turning over and over, the window flies between these
ROLL_FAR, FLIP_FAR = 0.55, 0.35      # of its body: turning, it is wider (corner to corner) and comes down this much
                                     # farther on than a plain jump would, clear of the one it went over or stood on


def slips_level():
    return next((g[0] for g in LEVEL_GIFTS if g[1] == "slips"), 0)
ITEMS_2 = ("coffee", "usb", "headphones", "balloon", "robot", "cube", "spin_top", "moon_lamp")
                            # 宝贝第二批 (round 9): in the frames from the start, dug up only from the level of the gift items_2
# how the plain signs look (the growth signs keep their own): (name, the level it comes with, colour, its name)
SIGN_CHALKS = (("white", 1, 0xFFF6F4EC, ("白", "White")), ("pink", 3, 0xFFFFBCD4, ("粉", "Pink")),
               ("blue", 12, 0xFFA8D8FF, ("蓝", "Blue")), ("gold", 20, 0xFFFFD764, ("金", "Gold")))
SIGN_FRAMES = (("wood", 1, ("原木", "Wood")), ("dots", 7, ("彩点", "Dots")), ("stars", 14, ("星星", "Stars")))
SIGN_BOARDS = (("board", 1, ("木牌", "Board")), ("flag", 18, ("小旗", "Banner")))
SIGN_LOOKS = {"chalk": SIGN_CHALKS, "frame": SIGN_FRAMES, "board": SIGN_BOARDS}
SIGN_LOOK_DEFAULT = {"chalk": "white", "frame": "wood", "board": "board"}


def dig_cap(level):
    """How many digs can be kept at this level (DIG_CHANCES, one more with each dig_ gift)."""
    return DIG_CHANCES + sum(1 for lv, gid, _, _ in LEVEL_GIFTS if gid.startswith("dig_") and level >= lv)


def next_gift(level):
    """-> (level, id, name, line) of the next gift after this level that is not given yet, or None at the top."""
    return next((g for g in LEVEL_GIFTS if g[0] > level), None)


def gift_news(seen, level):
    """-> the gifts this level has brought that the 图鉴 has not shown yet (its album.json "seen": ids gift:<id>)."""
    return [g[1] for g in LEVEL_GIFTS if g[0] <= level and "gift:" + g[1] not in seen]


def items_locked(level):
    """-> the treasures not to be dug up yet at this level (the second batch before its gift)."""
    at = next((g[0] for g in LEVEL_GIFTS if g[1] == "items_2"), 0)
    return ITEMS_2 if level < at else ()


def look_level(kind, name):
    """-> the level a sign look comes with, or None if there is no such look."""
    return next((row[1] for row in SIGN_LOOKS.get(kind, ()) if row[0] == name), None)


COMBO_IDLE = (("high_five", 0.22), ("parade", 0.17), ("stack", 0.13), ("note", 0.13), ("celebrate_all", 0.08), ("comfort", 0.12),
              ("leapfrog", 0.15))   # what they do by themselves, how often
# 养成 (growth, grow.json): one pool of XP for the whole family; work gives more, play less.  No caps a day:
# only an empty turn gives nothing, and play counts once in GROW_PLAY_GAP however fast the clicks come.
GROW_XP = {"turn": 5, "turn_minute": 2, "agent_done": 3, "fix": 5, "discover": 20,
           "click": 1, "drag": 1, "throw": 2, "startle": 2, "act": 10, "hand": 3, "item": 20, "treasure": 1}
GROW_STARS = ((10, 10), (30, 15), (100, 30))    # a combo played this many times: a star, and this much XP
GROW_HAND_GAP = 60.0        # s: a combo you set up yourself (dropped on one, thrown and patted) counts once in this long
GROW_ACT_AFTER = 1.5        # s after a special action begins before its "new" sign
# 干活时间 (work time, Family.work_tick): what counts is the time a turn is at work (Pet.at_work): from its message on,
# not while it waits for you (its circle orange), not past WORK_QUIET of silence unless a tool of it still runs, not
# a helper's after the turn's stop.  A turn's own work time gives its XP (Grow.turn) and its digs by themselves;
# the time any turn that has used a tool is at work (counted once however many are) earns the digs by hand.
# (2026-11-16, the user: smooth whatever the turns are like; it was counted per turn, one chance and one find a turn.)
WORK_QUIET = 300.0          # s without a word from a turn after which it is not at work (unless a tool of it runs)
WORK_TICK_MAX = 5.0         # s: a longer gap between two ticks (the computer slept) counts nothing
# 翻找 (rummaging) and the treasures.  By itself: in a turn that has used a tool, each DIG_EVERY s of its work time
# a small one that is free digs once, at most dig_cap of the level a turn (the user: as many as the chances kept);
# the find is shown, put away, and counted when the turn ends; what no small one got to, the big one pulls out
# itself when the turn ends.  Asked for by hand, any of them digs at once: counted there and then, and each dig
# that gets to its end takes one of the chances earned by work (one each DIG_CHANCE_WORK s of work time, at once,
# DIG_CHANCES at most), find or no find; after one that came up empty the next by hand is sure.  With none left
# it digs all the same and comes up empty.  Cut short: nothing is used.
DIG_EVERY = 120.0           # s of a turn's work time for each dig by itself in it
DIG_LOOPS = (3, 4)          # it digs this many loops by itself ...
DIG_HAND_LOOPS = 2          # ... and this many when asked
DIG_SELF_LUCK = 0.4         # by itself: the chance of a find (the user: a few digs a turn, each likelier)
DIG_HAND_LUCK = 0.6         # by hand, with a chance left
DIG_HELP = 0.25             # a click on one that digs: this much likelier to find, and the better of two draws
DIG_CHANCES = 3             # chances kept at most
DIG_CHANCE_WORK = 600.0     # s of work time for one more chance to dig by hand, given at once; what is over is kept
DIG_START_CHANCES = 2       # ... and a new family has this many: the first dig you ask for is not bound to come up empty
DIG_HELP_HALF = 0.5         # a click on one that digs: what is left of the digging takes this much of the time ...
DIG_HELP_MIN = 0.7          # ... but this long at least: two strokes of digging with gusto are seen
HAND_RARITIES = ("uncommon", "rare", "special")    # 交宝贝: a find like this is carried to the big one when the turn is over ...
HAND_CHEER = ("rare", "special")                   # ... and for one like this all of them cheer
HAND_SIGN_WAIT = 8.0        # s: its sign at the latest (the walk may take long); it goes up when the big one holds the find high ...
HAND_SIGN_HIGH = 1.2        # ... this long after the hand-over begins
HAND_SHOW_SECS = 1.0        # the hand-over came to nothing: this long for a calm moment to hold it up where it stands, else not at all
DIG_RARITY = (("common", 0.62), ("uncommon", 0.25), ("rare", 0.09), ("special", 0.04))   # each find, by hand or by itself
DIG_DRY = {"uncommon": 8, "rare": 20, "special": 40}   # 保底: this many finds in a row with nothing new of at least that,
                            # the next is a new one of at least that (one they had already does not reset it)
                            # (the 图鉴 shows how many are left); a special one also comes from the turn's work (DIG_SPECIAL)
DIG_OWNED = 0.5             # one you have already is this much less likely than one you have not
DIG_SIGN_AFTER = 2.1        # s after a find by hand before its sign: it is held up by then
DIG_SHOW_AFTER = 0.6        # s after the turn's "done" sign is down before the turn's find is shown
DIG_SHOW_SIGN = 0.5         # s into that showing before its sign
FIRST_PLAY_WAIT = 40.0      # s after a first find's sign is due: it is played with by then, or not at all
DIG_SHOW_WAIT = 20.0        # s it waits for a moment to show it; then it is counted without the showing
# what the turn's work turns a find into (the special treasures): the mark -> the treasure, first one not yet owned
PLAY_WAY = {"semicolon": "play_toss", "screw": "play_toss", "paper_ball": "play_toss", "pebble": "play_toss", "gear": "play_toss",
            "paperclip": "play_look", "sticky_note": "play_look", "pencil": "play_look", "leaf": "play_look", "braces": "play_look",
            "floppy": "play_look", "bug": "play_look", "biscuit": "play_look",
            "keycap": "play_listen", "shell": "play_listen", "bottle": "play_listen", "hourglass": "play_listen",
            "rubber_duck": "play_show", "gold_semicolon": "play_show", "plane_model": "play_show",
            "coffee": "play_look", "usb": "play_toss", "headphones": "play_listen",
            "balloon": "play_show", "robot": "play_show", "cube": "play_toss", "spin_top": "play_show", "moon_lamp": "play_show"}
                            # 把玩: the way each treasure is played with (a clip play_<treasure> of its own comes first)
PLAY_ALONE_CHANCE = 0.08    # of the idle extras that are a treasure taken out to play with (idle, one of them at a time)
PLAY_ALONE_LIVELY = 1.2     # x that while lively (its extras come 1/0.6 as often): about twice as often as normal (round 9,
                            # the user: normal about every 6 minutes, lively every 3; quiet every 12 by its pace alone)
DIG_SPECIAL = (("fix", "bug"), ("web", "bottle"), ("compact", "biscuit"), ("long", "hourglass"), ("agent", "plane_model"),
               ("night", "moon_lamp"))
DIG_NIGHT = (23, 5)         # a find from this hour to that one (local time) is a find of a "night" turn
DIG_LONG = 1200.0           # s: a turn this long is "long"
DIG_SPECIAL_NEW = 0.4       # a find in a turn with that work (by itself): the special one it draws, if you do not have it yet ...
DIG_SPECIAL_AGAIN = 0.2     # ... or if you have it already; else the find is drawn as any other (DIG_RARITY)
RARITY_NAMES = {"common": ("", ""), "uncommon": ("少见", "uncommon"), "rare": ("稀有", "rare"), "special": ("特殊", "special")}
GROW_PLAY_GAP = 10.0        # s: play counts at most once in this long
GROW_SAVE_SOON = 2.0        # s: ... and this often while the album is open (it shows what is in the file)
GROW_SAVE_EVERY = 60.0      # s: grow.json is written at most this often (at once on a new level, and on the way out)
GROW_DAILY_KEEP = 120       # days of numbers a day kept in grow.json (turns, time at work: to tune the pace)
GROW_LEVELUP_SECS = 6.0     # the level-up sign is up this long ...
GROW_DISCOVER_SECS = 5.0    # ... a first-seen combo's this long
GROW_SIGN_GAP = 1.0         # s after any sign is down before one of these goes up
GROW_DISCOVER_AFTER = 0.6   # s after the combo is over before its "new" sign
GROW_AFTER_STOP = 1.5       # s after a turn's end before a level-up: the turn's own reaction first
GROW_BAR_SECS = 0.9         # the bar on these signs fills this long
GROW_PHASES = 30            # steps of the chalk's shimmer (one each GROW_PHASE_SECS): the board is drawn again at each
GROW_PHASE_SECS = 0.08
# what a first-seen combo is called on its sign (zh, en); "console" is the pat after a throw, not in the menu
GROW_NAMES = dict(((k, (v, EN_COMBOS.get(k, k))) for k, v in COMBOS.items()), console=("扔完拍拍", "Pat after a throw"))
# the actions seen (grow.json "acts"): clip -> what it counts as (left and right are one; the parts of combos and
# the sign's stick are not actions of their own).  The nine that take you, or something out of the ordinary, are
# finds (a sign and XP the first time); the others are only written down for the 图鉴.
GROW_ACT_KEYS = {"rummage_in": "rummage", "rummage_found": "rummage", "rummage_none": "rummage", "rummage_up": "rummage",
                 "rummage_spur": "rummage", "rummage_fast": "rummage",
                 "tumble_left": "tumble", "tumble_right": "tumble", "squash": "tumble", "walk_left": "walk",
                 "walk_right": "walk", "turn_left": "walk", "turn_right": "walk", "doze_in": "doze", "doze_sleep": "sleep"}
GROW_ACTS = {"shy": ("害羞", "Shy"), "dangle": ("被拎起来", "Dangle"), "tumble": ("被扔出去", "Thrown"),
             "dizzy": ("晕乎乎", "Dizzy"), "doze": ("打瞌睡", "Doze"), "doze_startle": ("一激灵", "With a start"),
             "doze_up": ("伸懒腰起来", "Stretch"), "shrug_sweat": ("摊手流汗", "Shrug"), "surprised": ("吓一跳", "Startled")}
# the big one at work: now and then the two small ones play by themselves (without it), near where they are
PLAY_AT_WORK = (("leapfrog", 0.45), ("high_five", 0.35), ("note", 0.2))
PLAY_EVERY = (120.0, 240.0) # s between two games ...
PLAY_AFTER = 30.0           # ... and the big one works this long before the first
PARADE_SECS = 4.2           # s each way: a whole number of steps (WALK_SEAM), so that the legs can join the turn
PARADE_DIST = 1.6           # of the big one's body: how far they walk
COMFORT_WALK_SECS = 1.8     # they do not take their time for this
COMFORT_STAGGER = 0.3       # s between the two that pat
COMBO_EVERY = (120.0, 240.0)  # s between combos of their own while idle
COMBO_RETRY = 5.0           # s until the next try when it is not the moment
COMBO_PEEK_AFTER = 15.0     # s the big one works before a small one comes to watch: at a command or a web page ...
COMBO_PEEK_ANY = 3          # ... and at anything else after this many times as long
COMBO_PEEK_EVERY = (45.0, 90.0)
WATCHED_CLIPS = ("work_run", "work_web")
MIMIC_CLIPS = ("work_read", "work_edit", "work_run", "work_web")
MIMIC_EVERY = (20.0, 45.0)  # s between a small one copying the big one's tool ...
MIMIC_SECS = 3.5            # ... for this long
MIMIC_AFTER = 4.0           # s of work before the first
SHOW_GAP = 20.0             # s after one show of their own (a game, copying, coming to watch) before the next, x ACTIVITY_PACE
# 差事 (docs/差事设计.md): what each pet is up to, ranked; a lower number wins.  Family.chore() reads it off the pet's
# state, so nothing is ever left claimed; one from the cursor's 小剧场 counts from the moment it is picked.
R_HAND = 10                 # your hand: drag, throw, click, menu, clawd do, a combo by hand
R_WORK = 20                 # the big one at work or at a question; the one holding up a sign
R_ALL = 30                  # a reaction for the whole family (a long turn's cheer, a level-up): may wake a doze
R_NAP = 35                  # 小剧场: looks over, comes closer, dozes
R_EVENT = 45                # a reaction sent to one or two (comfort, a note, a pat after a throw)
R_RUMMAGE = 50              # (养成第 4 轮)
R_REACT = 55                # a small reaction (a jump, a look): never wakes a doze, never takes a sign's holder
R_PLAY = 60                 # games of their own (at work and when idle)
R_WATCH = 70                # keeping the big one company: copying its tool, coming over to watch
R_BASE = 80                 # idle life: extras, walks, the walk back, sleep
R_FREE = 90
RETURN_AFTER = (3.0, 7.0)   # s after a combo before the small ones walk back to where they stood
RETURN_WALK_SECS = 4.5
RETURN_PACE = 3.2           # of WALK_CLIP_SPEED: back home, or aside out of another one's way
ROW_TOLERANCE = 0.25        # of the larger body: feet this close in height stand on one row, others one behind the other
OVERLAP = 0.38              # of the two bodies together: this close on one row counts as a collision
OVERLAP_PATIENCE = 1.5      # s of overlap before the smaller one walks aside (time to go on dragging, for one)
COMBO_WAKE_AFTER = (240.0, 720.0)  # s asleep before a small one may wake the big one ...
COMBO_WAKE_CHANCE = 0.5     # ... which it does in this many of the naps
COMBO_FIVE_CHANCE = 0.3     # of the middling turns that end in a high five ...
COMBO_STACK_CHANCE = 0.15   # ... or in a tower
COMBO_QUEUE_SECS = 10.0     # a high five asked for by a turn's end waits this long for them to be idle, then it is off
COMBO_WALK_SECS = 1.3       # however far: a combo does not start with a long march
COMBO_WAKE_WALK_SECS = 2.6
COMBO_WAKE_PACE = 4.0       # of WALK_CLIP_SPEED: a little less hurry to wake one than to a combo
COMBO_RUSH_SECS = 1.2       # ... and after a long turn they run
COMBO_SPEED = 4.6           # of WALK_CLIP_SPEED: they trot over (the legs go faster too, see GAIT_RANGE)
GAIT_RANGE = (0.8, 4.6)     # the walk clip plays this many times as fast as normal at most: legs keep up with the feet
COMBO_MAX_SECS = 30.0       # safety net
COMBO_NEAR = 4.0            # of the big body: a combo they start themselves walks no farther (by hand: any way)
COMBO_SYNC_WAIT = 3.0       # s to wait for a clip under way before playing together
HIGH_FIVE_BIG, HIGH_FIVE_SMALL = 0.64, 0.34  # feet apart at the contact, of the two body px; measured on the clips
NUDGE_REACH = 0.55
STACK_HEAD = 0.7142         # feet to the top of the head in stack_brace, of the body px; measured on the clips
STACK_SINK = 0              # px the feet of the one on top go into the head below (the rounding already gives ~1 px)
HOP_TAKEOFF, HOP_LAND = 0.35, 0.75   # s into stack_hop: in the air between these, the window flies
HOP_ARC = 0.3               # of the hopper's body: how high the arc goes above the straight line ...
HOP_ARC_UP = 0.4            # ... plus this much of the height climbed
LEAP_HOP_AT = 0.05          # s into leap_crouch when the other one's stack_hop starts: in the air while it is down
LEAP_ARC = (0.8, 0.1)       # 跳山羊 arc: of the crouching one's body (its head is ~0.65 down there) + of the jumper's
LEAP_GAP = 0.45             # of the two bodies together: feet apart before and after a jump
STACK_GAP = 0.1             # of the larger body: between the base and one about to climb on it
NOTE_K = (0.4826, 0.4760, 0.4152)   # per slot, of its body px: feet apart at the hand-over is the sum of both; measured
NOTE_KIND = ("", "mid_", "small_")    # per slot: give_/receive_ clips drawn so the note meets at one height on the screen
NOTE_WALK_SECS = 2.5
NOTE_SYNC_WAIT = 3.0        # s the one with the note waits for the other one to take it
NOTE_COOLDOWN = 30.0        # s between notes for sub-agents that are done: they come in bunches
NOTE_TO_BIG = 0.7           # of the notes by themselves that go to the big one
SIBLING_GAP = 0.15          # of the larger body: the room kept between two walking pets
SCALE_SNAP = 0.03           # |scale - 1| below this snaps to exactly 100 %
DISP_SNAP = 0.012           # display factor this close to 1 is shown 1:1
WHEEL_STEP = 1.1            # per wheel notch
SIZE_PRESETS = (50, 75, 100, 150, 200, 300)
RERENDER_DELAY = 1.5        # s after the last size change
RENDER_TIMEOUT = 1800.0
DEFAULT_BODY_PX = 100
V1_ANCHOR = (64, 160)       # feet inside the v1 156x168 canvas (state.json v1 migration)
CACHE_BUDGET = 10 * 1024 * 1024   # compressed frame bytes kept in memory (idle always kept)
HI_DIR_NAME = "frames_hi"   # 300 % master, next to the base frames directory
POLL_INTERVAL = 0.15        # s between event-file polls
HIDDEN_TICK_MS = 1000       # the small ones' timer while the family is hidden (re-render polls only)
WATCH_INTERVAL = 5.0        # s between manifest checks (frames regenerated while running)
EVENT_STALE = 3.0
EVENT_TRUNC_SIZE = 16 * 1024
EVENT_TRUNC_IDLE = 2.0
EVENT_PARTIAL_WAIT = 0.3    # a line without newline is taken after this long
EVENT_MAX_READ = 64 * 1024
EVENT_MAX_BACKLOG = 8 * 1024
LOG_MAX = 256 * 1024        # bytes; pet.log rotates to pet.log.1 beyond this
MAX_CONSECUTIVE_ERRORS = 40

KIND_LOOP, KIND_HOLD, KIND_ONESHOT = "loop", "hold", "oneshot"

# --------------------------------------------------------------------------- logging
_last_log = {"msg": None, "t": 0.0, "suppressed": 0}


def log(msg):
    try:
        os.makedirs(HOME_DIR, exist_ok=True)
        try:
            if os.path.getsize(LOG_PATH) > LOG_MAX:
                os.replace(LOG_PATH, LOG_PATH + ".1")
        except OSError:
            pass
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s [%d] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), msg))
    except Exception:
        pass


def log_exc(where):
    """Log the current exception; identical tracebacks are rate limited."""
    tb = traceback.format_exc()
    now = time.monotonic()
    if tb == _last_log["msg"] and now - _last_log["t"] < 30.0:
        _last_log["suppressed"] += 1
        return
    extra = ""
    if _last_log["suppressed"]:
        extra = " (previous error repeated %d more times)" % _last_log["suppressed"]
    _last_log.update(msg=tb, t=now, suppressed=0)
    log("ERROR in %s%s\n%s" % (where, extra, tb.rstrip()))


def _ms_since(t0, t1):
    """ms from t0 to t1, both GetMessageTime values (they wrap after 49 days)."""
    return (t1 - t0) & 0xFFFFFFFF


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# --------------------------------------------------------------------------- Win32 types
BOOL = ctypes.c_int
INT = ctypes.c_int
UINT = ctypes.c_uint
DWORD = ctypes.c_uint32
LONG = ctypes.c_long
SHORT = ctypes.c_short
BYTE = ctypes.c_ubyte
WORD = ctypes.c_uint16
ATOM = ctypes.c_uint16
WPARAM = ctypes.c_size_t        # pointer sized, unsigned
LPARAM = ctypes.c_ssize_t       # pointer sized, signed
LRESULT = ctypes.c_ssize_t
UINT_PTR = ctypes.c_size_t
ULONG_PTR = ctypes.c_size_t
HANDLE = ctypes.c_void_p
HWND = HMENU = HDC = HBITMAP = HGDIOBJ = HINSTANCE = HICON = HCURSOR = HBRUSH = HANDLE
HMONITOR = HANDLE
LPVOID = ctypes.c_void_p
LPCWSTR = ctypes.c_wchar_p

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", LONG), ("cy", LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", HWND), ("message", UINT), ("wParam", WPARAM), ("lParam", LPARAM),
                ("time", DWORD), ("pt", POINT), ("lPrivate", DWORD)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", UINT), ("style", UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", INT), ("cbWndExtra", INT), ("hInstance", HINSTANCE),
                ("hIcon", HICON), ("hCursor", HCURSOR), ("hbrBackground", HBRUSH),
                ("lpszMenuName", LPCWSTR), ("lpszClassName", LPCWSTR), ("hIconSm", HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", DWORD), ("biWidth", LONG), ("biHeight", LONG),
                ("biPlanes", WORD), ("biBitCount", WORD), ("biCompression", DWORD),
                ("biSizeImage", DWORD), ("biXPelsPerMeter", LONG), ("biYPelsPerMeter", LONG),
                ("biClrUsed", DWORD), ("biClrImportant", DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", BYTE), ("BlendFlags", BYTE),
                ("SourceConstantAlpha", BYTE), ("AlphaFormat", BYTE)]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", DWORD), ("dwFlags", DWORD), ("hwndTrack", HWND), ("dwHoverTime", DWORD)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", DWORD)]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", DWORD),
                ("Affinity", ULONG_PTR), ("PriorityClass", DWORD), ("SchedulingClass", DWORD)]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", ctypes.c_ulonglong * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong), ("TotalPageFaultCount", DWORD),
                ("TotalProcesses", DWORD), ("ActiveProcesses", DWORD),
                ("TotalTerminatedProcesses", DWORD)]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", BOOL), ("SuppressExternalCodecs", BOOL)]


class RECTF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float), ("Width", ctypes.c_float), ("Height", ctypes.c_float)]


class POINTF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", DWORD), ("hWnd", HWND), ("uID", UINT), ("uFlags", UINT),
                ("uCallbackMessage", UINT), ("hIcon", HICON), ("szTip", ctypes.c_wchar * 128),
                ("dwState", DWORD), ("dwStateMask", DWORD), ("szInfo", ctypes.c_wchar * 256),
                ("uVersion", UINT), ("szInfoTitle", ctypes.c_wchar * 64), ("dwInfoFlags", DWORD),
                ("guidItem", BYTE * 16), ("hBalloonIcon", HICON)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", BOOL), ("xHotspot", DWORD), ("yHotspot", DWORD),
                ("hbmMask", HBITMAP), ("hbmColor", HBITMAP)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


def _api(dll, name, restype, argtypes, optional=False):
    try:
        fn = getattr(dll, name)
    except AttributeError:
        if optional:
            return None
        raise
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


# kernel32
CreateMutexW = _api(kernel32, "CreateMutexW", HANDLE, [LPVOID, BOOL, LPCWSTR])
OpenMutexW = _api(kernel32, "OpenMutexW", HANDLE, [DWORD, BOOL, LPCWSTR])
CloseHandle = _api(kernel32, "CloseHandle", BOOL, [HANDLE])
GetModuleHandleW = _api(kernel32, "GetModuleHandleW", HINSTANCE, [LPCWSTR])
CreateJobObjectW = _api(kernel32, "CreateJobObjectW", HANDLE, [LPVOID, LPCWSTR])
SetInformationJobObject = _api(kernel32, "SetInformationJobObject", BOOL, [HANDLE, INT, LPVOID, DWORD])
QueryInformationJobObject = _api(kernel32, "QueryInformationJobObject", BOOL,
                                 [HANDLE, INT, LPVOID, DWORD, LPVOID])
AssignProcessToJobObject = _api(kernel32, "AssignProcessToJobObject", BOOL, [HANDLE, HANDLE])
TerminateJobObject = _api(kernel32, "TerminateJobObject", BOOL, [HANDLE, UINT])
NtResumeProcess = _api(ctypes.WinDLL("ntdll"), "NtResumeProcess", LONG, [HANDLE])

# user32
SetProcessDpiAwarenessContext = _api(user32, "SetProcessDpiAwarenessContext", BOOL,
                                     [HANDLE], optional=True)
SetProcessDPIAware = _api(user32, "SetProcessDPIAware", BOOL, [], optional=True)
RegisterClassExW = _api(user32, "RegisterClassExW", ATOM, [ctypes.POINTER(WNDCLASSEXW)])
UnregisterClassW = _api(user32, "UnregisterClassW", BOOL, [LPCWSTR, HINSTANCE])
CreateWindowExW = _api(user32, "CreateWindowExW", HWND,
                       [DWORD, LPCWSTR, LPCWSTR, DWORD, INT, INT, INT, INT,
                        HWND, HMENU, HINSTANCE, LPVOID])
DestroyWindow = _api(user32, "DestroyWindow", BOOL, [HWND])
DefWindowProcW = _api(user32, "DefWindowProcW", LRESULT, [HWND, UINT, WPARAM, LPARAM])
GetMessageW = _api(user32, "GetMessageW", BOOL, [ctypes.POINTER(MSG), HWND, UINT, UINT])
TranslateMessage = _api(user32, "TranslateMessage", BOOL, [ctypes.POINTER(MSG)])
DispatchMessageW = _api(user32, "DispatchMessageW", LRESULT, [ctypes.POINTER(MSG)])
PostQuitMessage = _api(user32, "PostQuitMessage", None, [INT])
PostMessageW = _api(user32, "PostMessageW", BOOL, [HWND, UINT, WPARAM, LPARAM])
SetTimer = _api(user32, "SetTimer", UINT_PTR, [HWND, UINT_PTR, UINT, LPVOID])
KillTimer = _api(user32, "KillTimer", BOOL, [HWND, UINT_PTR])
ShowWindow = _api(user32, "ShowWindow", BOOL, [HWND, INT])
SetWindowPos = _api(user32, "SetWindowPos", BOOL, [HWND, HWND, INT, INT, INT, INT, UINT])
GetWindowRect = _api(user32, "GetWindowRect", BOOL, [HWND, ctypes.POINTER(RECT)])
UpdateLayeredWindow = _api(user32, "UpdateLayeredWindow", BOOL,
                           [HWND, HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE), HDC,
                            ctypes.POINTER(POINT), DWORD, ctypes.POINTER(BLENDFUNCTION), DWORD])
LoadCursorW = _api(user32, "LoadCursorW", HCURSOR, [HINSTANCE, LPVOID])
GetCursorPos = _api(user32, "GetCursorPos", BOOL, [ctypes.POINTER(POINT)])
SetCapture = _api(user32, "SetCapture", HWND, [HWND])
GetCapture = _api(user32, "GetCapture", HWND, [])
ReleaseCapture = _api(user32, "ReleaseCapture", BOOL, [])
GetAsyncKeyState = _api(user32, "GetAsyncKeyState", SHORT, [INT])
GetSystemMetrics = _api(user32, "GetSystemMetrics", INT, [INT])
TrackMouseEvent = _api(user32, "TrackMouseEvent", BOOL, [ctypes.POINTER(TRACKMOUSEEVENT)])
GetDoubleClickTime = _api(user32, "GetDoubleClickTime", UINT, [])
GetMessageTime = _api(user32, "GetMessageTime", LONG, [])
CreatePopupMenu = _api(user32, "CreatePopupMenu", HMENU, [])
AppendMenuW = _api(user32, "AppendMenuW", BOOL, [HMENU, UINT, UINT_PTR, LPCWSTR])
TrackPopupMenu = _api(user32, "TrackPopupMenu", BOOL,
                      [HMENU, UINT, INT, INT, INT, HWND, ctypes.POINTER(RECT)])
DestroyMenu = _api(user32, "DestroyMenu", BOOL, [HMENU])
SetForegroundWindow = _api(user32, "SetForegroundWindow", BOOL, [HWND])
IsWindow = _api(user32, "IsWindow", BOOL, [HWND])
IsIconic = _api(user32, "IsIconic", BOOL, [HWND])
GetForegroundWindow = _api(user32, "GetForegroundWindow", HWND, [])
GetClassNameW = _api(user32, "GetClassNameW", INT, [HWND, ctypes.c_wchar_p, INT])
TERMINAL_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"     # a Windows Terminal window (all of them are one process)
TERMINAL_CLASSES = (TERMINAL_CLASS, "ConsoleWindowClass", "mintty")    # ... the old console, Git Bash's own window


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(64)
    return buf.value if hwnd and GetClassNameW(hwnd, buf, 64) else ""


# A conversation's window, as its "at" line says it (clawd_hook.py): on Windows a window handle; on macOS the pid of
# the app it runs in (where_mac), never one of the shim's handles (unrelated numbers), so there it goes to no window
# call: the talk_window_* below say what each call means for an app.  Terminal and iTerm2 are what Windows Terminal is
# (a tab can be chosen in them: TERMINAL_CLASS); the other terminals and every other app are brought forward whole.
MAC_TAB_TERMINALS = {"com.apple.Terminal": "Terminal", "com.googlecode.iterm2": "iTerm2"}
MAC_TERMINALS = ("com.mitchellh.ghostty", "com.github.wez.wezterm", "net.kovidgoyal.kitty", "org.alacritty",
                 "dev.warp.", "co.zeit.hyper")         # bundle ids (their start): Ghostty, WezTerm, kitty, ..., Hyper
MAC_TERMINAL_CLASS = "terminal"                      # (talk_window_class of one of those)
MAC_TTY = re.compile(r"^ttys?[0-9]{1,6}$")             # an "at" line's tab on macOS: its terminal's device


def talk_window_alive(w):
    """IsWindow; on macOS: its app runs."""
    if MAC:
        return macsys.app_alive(w)
    return IsWindow(w)


def talk_window_class(w):
    """window_class; on macOS: TERMINAL_CLASS (Terminal, iTerm2), MAC_TERMINAL_CLASS (another terminal) or the app's
    bundle id ("" when it is gone): kept in talks.json, so a pid that is another app's by now is not taken back."""
    if not MAC:
        return window_class(w)
    bid = macsys.app_bundle_id(w) or ""
    if bid in MAC_TAB_TERMINALS:
        return TERMINAL_CLASS
    if bid.lower().startswith(tuple(t.lower() for t in MAC_TERMINALS)):
        return MAC_TERMINAL_CLASS
    return bid


def talk_is_terminal(w):
    """A terminal's window (its conversation stays there: no app link)."""
    if MAC:
        return talk_window_class(w) in (TERMINAL_CLASS, MAC_TERMINAL_CLASS)
    return window_class(w) in TERMINAL_CLASSES


def talk_terminal_name(w):
    """The terminal whose tab a click chooses, as the texts name it."""
    if MAC:
        return MAC_TAB_TERMINALS.get(macsys.app_bundle_id(w) or "", "Terminal")
    return "Windows Terminal"


def talk_window_visible(w):
    """IsWindowVisible; on macOS: its app runs (nothing of it is in a tray: activate_pid shows a hidden app again)."""
    if MAC:
        return macsys.app_alive(w)
    return bool(user32.IsWindowVisible(w))


def talk_window_show(w):
    """A window its app hid (DeepSeek's, to its tray) shown again; on macOS there is none such (talk_window_visible)."""
    if not MAC:
        ShowWindow(w, SW_SHOW)


def talk_window_restore(w):
    """Minimised: back; on macOS activate_pid does that (talk_window_front)."""
    if not MAC and IsIconic(w):
        ShowWindow(w, SW_RESTORE)


def talk_window_front(w):
    """-> True if it was brought to the front; on macOS its app, all its windows (clawd_mac.system.activate_pid)."""
    if MAC:
        return macsys.activate_pid(w)
    return SetForegroundWindow(w)


def tab_shells():
    """The PowerShell programs to run clawd_tabs.ps1 with, best first.  Not found by PATH: pets started from Claude's
    desktop app have PowerShell 7's package folder first on it (C:\\Program Files\\WindowsApps\\Microsoft.PowerShell_...),
    and the pwsh.exe in there cannot run without its package ("an error occurred while creating the pipeline", exit 1):
    not one tab was read from 2026-11-13 to 11-15, and nothing said so.  The Store install's alias first, then an
    installed PowerShell 7, then Windows PowerShell (always there)."""
    local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    out = [os.path.join(local, "Microsoft", "WindowsApps", "pwsh.exe")]
    for pf in (os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles")):
        if pf:
            out.append(os.path.join(pf, "PowerShell", "7", "pwsh.exe"))
    out.append(os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe"))
    seen = []
    for p in out:
        if p.lower() not in [s.lower() for s in seen] and os.path.exists(p):
            seen.append(p)
    return seen


# macOS: the tab of a terminal device chosen, its window to the front, by AppleScript (what clawd_tabs.ps1 "select"
# is for Windows Terminal).  The device comes as the script's argument, never as part of the script.  Prints ok, or
# gone (no such tab now); macOS asks the user once whether the pets may control that app (refused: error -1743).
TAB_SCRIPTS_MAC = {
    "com.apple.Terminal": """on run argv
    tell application id "com.apple.Terminal"
        repeat with w in windows
            repeat with t in tabs of w
                if tty of t is (item 1 of argv) then
                    if miniaturized of w then set miniaturized of w to false
                    set selected of t to true
                    set index of w to 1
                    activate
                    return "ok"
                end if
            end repeat
        end repeat
    end tell
    return "gone"
end run""",
    "com.googlecode.iterm2": """on run argv
    tell application id "com.googlecode.iterm2"
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if tty of s is (item 1 of argv) then
                        select w
                        select t
                        select s
                        activate
                        return "ok"
                    end if
                end repeat
            end repeat
        end repeat
    end tell
    return "gone"
end run"""}
TAB_WAIT_MAC = 60.0         # s: the first time, macOS asks the user before the script may run (tab_done waits)


def tab_osascript(bundle_id, tty):
    """-> the osascript command that chooses the tab of this tty ("ttys013") in that terminal app, or None."""
    script = TAB_SCRIPTS_MAC.get(bundle_id)
    if script is None or not MAC_TTY.match(tty or ""):
        return None
    return ["/usr/bin/osascript", "-e", script, "/dev/" + tty]


# Every agent the pets know, in one place (the agent's name is what its "at" lines say; clawd.py AGENTS installs them):
#   label   how the circle's name says whose it is (with circles of several agents)
#   scheme  its desktop app's link scheme;  exes: that app's programs (app_window, app_running)
#   kinds   where TalkTitles finds its conversations' names (so a conversation is known as its own before an "at")
#   open    one app, one window for all its conversations and no link to one of them: this link only shows it
#   hides   it hides its one window to the tray (rather than closing it): a click shows it again at once
AGENT_INFO = {
    "claude": {"label": "Claude", "scheme": "claude", "exes": ("claude.exe",), "kinds": ("desk", "cli")},
    "codex": {"label": "Codex", "scheme": "codex", "exes": ("chatgpt.exe", "codex.exe"),
              "kinds": ()},              # its name index is where any conversation not found elsewhere is looked for
                                         # (a thread is named there a while after it starts): it says nothing of whose
    "deepseek": {"label": "DeepSeek", "scheme": "dsh", "exes": ("deepseek harness.exe",), "kinds": ("dsh",),
                 "open": "dsh://open", "hides": True},
    "antigravity": {"label": "Antigravity", "scheme": "antigravity", "exes": ("antigravity.exe",), "kinds": ("ag",),
                    "open": "antigravity://open"},
}
APP_EXES = {a["scheme"]: a["exes"] for a in AGENT_INFO.values()}          # a link's scheme -> its desktop app
KIND_AGENT = {k: name for name, a in AGENT_INFO.items() for k in a["kinds"]}


def app_names(exes):
    """macOS: the apps' names for their Windows programs ("deepseek harness.exe" -> "deepseek harness": the app's
    executable or shown name, case not looked at; clawd_mac.system.find_app)."""
    return [e[:-len(".exe")] if e.lower().endswith(".exe") else e for e in exes]


OPEN_TIMEOUT = 15.0         # s: macOS, /usr/bin/open handing a link to its app


def open_url(url):
    """A page or an app's link (https:, claude:, codex:, dsh:, antigravity:) opened by the system: os.startfile, on
    macOS /usr/bin/open (no shell).  OSError if it did not open."""
    if not MAC:
        os.startfile(url)
        return
    import subprocess
    try:
        r = subprocess.run(["/usr/bin/open", url], stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=OPEN_TIMEOUT, **child_kw())
    except subprocess.SubprocessError as e:
        raise OSError(str(e))
    if r.returncode:
        raise OSError((r.stderr or b"").decode("utf-8", "replace").strip() or "exit %d" % r.returncode)


def child_kw(flags=0):
    """A child process's Popen arguments: on Windows its creationflags; on macOS none (Python refuses them there) and
    a session of its own, so a Ctrl+C or a closed terminal where the pets were started does not reach it."""
    if MAC:
        return {"start_new_session": True}
    return {"creationflags": flags} if flags else {}


def app_window(scheme):
    """The main window of the desktop app a claude://, codex:// or dsh:// link opens (by its program's name), or None.
    The command-line programs of the same name have no window of their own, so they are never taken.  On macOS the
    app's pid (a conversation's "window" there: talk_window_*)."""
    exes = APP_EXES.get(scheme)
    if not exes:
        return None
    if MAC:
        return macsys.find_app(app_names(exes))
    k32 = ctypes.windll.kernel32
    found = []

    def each(h, _):
        if user32.IsWindowVisible(h) and user32.GetWindowTextLengthW(h) and not user32.GetWindow(h, 4):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            hp = k32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
            if hp:
                n = ctypes.c_ulong(520)
                path = ctypes.create_unicode_buffer(520)
                if k32.QueryFullProcessImageNameW(hp, 0, path, ctypes.byref(n)):
                    if os.path.basename(path.value).lower() in exes and window_class(h) == "Chrome_WidgetWin_1":
                        found.append(h)
                k32.CloseHandle(hp)
        return not found

    try:
        user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(each), 0)
    except Exception:
        log_exc("the app's window")
    return found[0] if found else None


def app_running(scheme):
    """True if the desktop app a link of this scheme opens is running, with or without a window (in its tray)."""
    exes = APP_EXES.get(scheme)
    if not exes:
        return False
    if MAC:
        return macsys.find_app(app_names(exes)) is not None

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_ulong),
                    ("cntThreads", ctypes.c_ulong), ("th32ParentProcessID", ctypes.c_ulong),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snap = k32.CreateToolhelp32Snapshot(2, 0)              # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return False
    found = False
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(pe))
        while ok and not found:
            found = pe.szExeFile.lower() in exes
            ok = k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(pe))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snap))
    return found


SW_RESTORE = 9
SW_SHOW = 5
SystemParametersInfoW = _api(user32, "SystemParametersInfoW", BOOL,
                             [UINT, UINT, ctypes.POINTER(RECT), UINT])
MonitorFromPoint = _api(user32, "MonitorFromPoint", HMONITOR, [POINT, DWORD])
GetMonitorInfoW = _api(user32, "GetMonitorInfoW", BOOL, [HMONITOR, ctypes.POINTER(MONITORINFO)])
RegisterWindowMessageW = _api(user32, "RegisterWindowMessageW", UINT, [LPCWSTR])
CreateIconIndirect = _api(user32, "CreateIconIndirect", HICON, [ctypes.POINTER(ICONINFO)])
DestroyIcon = _api(user32, "DestroyIcon", BOOL, [HICON])
LoadIconW = _api(user32, "LoadIconW", HICON, [HINSTANCE, LPVOID])

# shell32
Shell_NotifyIconW = _api(shell32, "Shell_NotifyIconW", BOOL, [DWORD, ctypes.POINTER(NOTIFYICONDATAW)])

# gdi32
CreateCompatibleDC = _api(gdi32, "CreateCompatibleDC", HDC, [HDC])
DeleteDC = _api(gdi32, "DeleteDC", BOOL, [HDC])
CreateDIBSection = _api(gdi32, "CreateDIBSection", HBITMAP,
                        [HDC, ctypes.POINTER(BITMAPINFO), UINT, ctypes.POINTER(LPVOID),
                         HANDLE, DWORD])
SelectObject = _api(gdi32, "SelectObject", HGDIOBJ, [HDC, HGDIOBJ])
DeleteObject = _api(gdi32, "DeleteObject", BOOL, [HGDIOBJ])
GdiFlush = _api(gdi32, "GdiFlush", BOOL, [])
CreateBitmap = _api(gdi32, "CreateBitmap", HBITMAP, [INT, INT, UINT, UINT, LPVOID])

# constants
ERROR_ALREADY_EXISTS = 183
ERROR_CLASS_ALREADY_EXISTS = 1410
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020        # the sign's board: clicks go through it
IDC_HAND = 32649
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0
SPI_GETWORKAREA = 0x0030
SPI_SETWORKAREA = 0x002F
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2
MA_NOACTIVATE = 3
TME_LEAVE = 0x00000002
MK_CONTROL = 0x0008
VK_LBUTTON, VK_RBUTTON, VK_CONTROL = 0x01, 0x02, 0x11
SM_SWAPBUTTON = 23
WHEEL_DELTA = 120
CREATE_NO_WINDOW = 0x08000000
CREATE_SUSPENDED = 0x00000004
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
JobObjectBasicAccountingInformation = 1
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_SETTINGCHANGE = 0x001A
WM_MOUSEACTIVATE = 0x0021
WM_DISPLAYCHANGE = 0x007E
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A
WM_CAPTURECHANGED = 0x0215
WM_ENTERSIZEMOVE = 0x0231
WM_MOUSELEAVE = 0x02A3
WM_DPICHANGED = 0x02E0

MF_STRING = 0x0000
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008
MF_POPUP = 0x0010
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100

TIMER_ANIM = 1
TIMER_DRAG = 2
ID_RESET = 2
ID_QUIT = 3
ID_DISMISS = 4
ID_HIDE = 5                 # hide or show the family
ID_DIG = 7                  # 翻找, asked for by hand
ID_ALBUM = 8                # 图鉴: the album window (clawd_album.pyw, a process of its own)
ID_CONNECT = 9              # 连接 AI…: the window that connects the agents (clawd_connect.pyw, a process of its own)
ID_PLAY_ANY = 599           # 把玩: any treasure ...
ID_PLAY_BASE = 600          # ... or this one (+ its place in the manifest's order)
ID_AUTOSTART = 6            # the tray menu's 开机自启
ID_RELEASES = 1             # the tray menu's 去看看新版本: opens RELEASES_URL (nothing here goes online by itself)
RELEASES_URL = "https://github.com/BigBrother168/red-crab/releases"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"           # HKCU: this user only
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"   # Task Manager's switch
AUTOSTART_NAME = "Clawd"
WM_TRAY = 0x8001            # WM_APP + 1: the tray icon's callback
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
SM_CXSMICON = 49
IDI_APPLICATION = 32512
TRAY_TITLE = "ClawdTray"    # the tray icon's hidden window
ID_FAMILY_BASE = 10
ID_COMBO_BASE = 20
ID_LANG_BASE = 40
ID_ACTIVITY_BASE = 45
ID_SIZE_BASE = 50
ID_ACTION_BASE = 100

# GDI+
PixelFormat32bppPARGB = 0x000E200B
CompositingModeSourceCopy = 1
InterpolationModeHighQualityBicubic = 7
PixelOffsetModeHighQuality = 2
FlushIntentionSync = 1
WrapModeClamp = 4
UnitPixel = 2


def disable_ime():
    """No IME in this process, before its first window: it takes no text input, yet an installed
    third-party IME otherwise gets loaded into it sooner or later (measured with Sogou: +50 MB)."""
    try:
        _api(ctypes.WinDLL("imm32"), "ImmDisableIME", BOOL, [DWORD])(0xFFFFFFFF)     # -1: all threads
    except Exception:
        log_exc("disable_ime")


def set_dpi_awareness():
    # Per-monitor v2 so the frames are shown 1:1 at native pixels.
    try:
        if SetProcessDpiAwarenessContext and SetProcessDpiAwarenessContext(-4):
            return
    except Exception:
        pass
    try:
        if ctypes.WinDLL("shcore").SetProcessDpiAwareness(2) == 0:
            return
    except Exception:
        pass
    try:
        if SetProcessDPIAware:
            SetProcessDPIAware()
    except Exception:
        pass


# --------------------------------------------------------------------------- GDI+ scaler
class _NS(object):
    pass


_GP = None


def _gdiplus():
    """GDI+ flat API, loaded on first use only (100 % size never loads gdiplus.dll)."""
    global _GP
    if _GP is None:
        dll = ctypes.WinDLL("gdiplus")
        P, PP, ST = ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int
        ns = _NS()
        ns.Startup = _api(dll, "GdiplusStartup", ST, [ctypes.POINTER(ULONG_PTR),
                                                      ctypes.POINTER(GdiplusStartupInput), P])
        ns.Shutdown = _api(dll, "GdiplusShutdown", None, [ULONG_PTR])
        ns.CreateBitmapFromScan0 = _api(dll, "GdipCreateBitmapFromScan0", ST,
                                        [INT, INT, INT, INT, P, PP])
        ns.GetImageGraphicsContext = _api(dll, "GdipGetImageGraphicsContext", ST, [P, PP])
        ns.SetCompositingMode = _api(dll, "GdipSetCompositingMode", ST, [P, INT])
        ns.SetInterpolationMode = _api(dll, "GdipSetInterpolationMode", ST, [P, INT])
        ns.SetPixelOffsetMode = _api(dll, "GdipSetPixelOffsetMode", ST, [P, INT])
        ns.GraphicsClear = _api(dll, "GdipGraphicsClear", ST, [P, DWORD])
        F = ctypes.c_float
        ns.DrawImageRectRect = _api(dll, "GdipDrawImageRectRect", ST, [P, P, F, F, F, F, F, F, F, F, INT, P, P, P])
        ns.CreateImageAttributes = _api(dll, "GdipCreateImageAttributes", ST, [PP])
        ns.SetImageAttributesWrapMode = _api(dll, "GdipSetImageAttributesWrapMode", ST, [P, INT, DWORD, BOOL])
        ns.DisposeImageAttributes = _api(dll, "GdipDisposeImageAttributes", ST, [P])
        ns.Flush = _api(dll, "GdipFlush", ST, [P, INT])
        ns.DeleteGraphics = _api(dll, "GdipDeleteGraphics", ST, [P])
        ns.DisposeImage = _api(dll, "GdipDisposeImage", ST, [P])
        # the sign's board: a rounded path, a brush, a pen, a font and a string format
        RF = ctypes.POINTER(RECTF)
        ns.SetSmoothingMode = _api(dll, "GdipSetSmoothingMode", ST, [P, INT])
        ns.SetTextRenderingHint = _api(dll, "GdipSetTextRenderingHint", ST, [P, INT])
        ns.CreatePath = _api(dll, "GdipCreatePath", ST, [INT, PP])
        ns.AddPathArc = _api(dll, "GdipAddPathArc", ST, [P, F, F, F, F, F, F])
        ns.AddPathEllipse = _api(dll, "GdipAddPathEllipse", ST, [P, F, F, F, F])
        ns.AddPathString = _api(dll, "GdipAddPathString", ST, [P, ctypes.c_wchar_p, INT, P, INT, F, RF, P])
        ns.ClosePathFigure = _api(dll, "GdipClosePathFigure", ST, [P])
        ns.DeletePath = _api(dll, "GdipDeletePath", ST, [P])
        ns.FillPath = _api(dll, "GdipFillPath", ST, [P, P, P])
        ns.DrawPath = _api(dll, "GdipDrawPath", ST, [P, P, P])
        ns.CreateSolidFill = _api(dll, "GdipCreateSolidFill", ST, [DWORD, PP])
        ns.DeleteBrush = _api(dll, "GdipDeleteBrush", ST, [P])
        ns.CreatePen1 = _api(dll, "GdipCreatePen1", ST, [DWORD, F, INT, PP])
        ns.DeletePen = _api(dll, "GdipDeletePen", ST, [P])
        ns.CreateFontFamilyFromName = _api(dll, "GdipCreateFontFamilyFromName", ST, [ctypes.c_wchar_p, P, PP])
        ns.DeleteFontFamily = _api(dll, "GdipDeleteFontFamily", ST, [P])
        ns.CreateFont = _api(dll, "GdipCreateFont", ST, [P, F, INT, INT, PP])
        ns.DeleteFont = _api(dll, "GdipDeleteFont", ST, [P])
        ns.CreateStringFormat = _api(dll, "GdipCreateStringFormat", ST, [INT, ctypes.c_ushort, PP])
        ns.DeleteStringFormat = _api(dll, "GdipDeleteStringFormat", ST, [P])
        ns.SetStringFormatAlign = _api(dll, "GdipSetStringFormatAlign", ST, [P, INT])
        ns.SetStringFormatLineAlign = _api(dll, "GdipSetStringFormatLineAlign", ST, [P, INT])
        ns.MeasureString = _api(dll, "GdipMeasureString", ST, [P, ctypes.c_wchar_p, INT, P, RF, P, RF, P, P])
        ns.DrawString = _api(dll, "GdipDrawString", ST, [P, ctypes.c_wchar_p, INT, P, RF, P, P])
        PF = ctypes.POINTER(POINTF)
        ns.CreateLineBrush = _api(dll, "GdipCreateLineBrush", ST, [PF, PF, DWORD, DWORD, INT, PP])
        ns.AddPathPolygon = _api(dll, "GdipAddPathPolygon", ST, [P, PF, INT])
        _GP = ns
    return _GP


class Scaler(object):
    """Scales one premultiplied BGRA frame into the DIB with GDI+.

    Source: a persistent ctypes buffer wrapped as a PARGB bitmap.  Target: a PARGB bitmap
    wrapping the DIB section's own bits, drawn with SourceCopy after a clear, so the DIB
    receives correctly premultiplied, high-quality bicubic pixels.  Outside the source there is
    only transparency (clamp wrap); a mirroring wrap would reflect frames that reach the canvas
    edge back in.  The source rectangle is fractional, to put the anchor exactly on a target
    pixel (a fractional target rectangle does not work: GDI+ shifts x the wrong way).  All
    objects are created once per size and reused every tick."""

    def __init__(self):
        self.gp = _gdiplus()
        inp = GdiplusStartupInput(1, None, 0, 0)
        tok = ULONG_PTR(0)
        st = self.gp.Startup(ctypes.byref(tok), ctypes.byref(inp), None)
        if st != 0:
            raise OSError("GdiplusStartup failed (status %d)" % st)
        self.token = tok.value
        self.src_buf = None
        self.src = self.dst = self.g = None
        self.nbytes = 0
        self.dw = self.dh = 0
        self.src_rect = (0.0, 0.0, 0.0, 0.0)
        attrs = ctypes.c_void_p()
        self._chk(self.gp.CreateImageAttributes(ctypes.byref(attrs)), "GdipCreateImageAttributes")
        self.attrs = attrs
        self._chk(self.gp.SetImageAttributesWrapMode(attrs, WrapModeClamp, 0, 0),
                  "GdipSetImageAttributesWrapMode")

    @staticmethod
    def _chk(st, what):
        if st != 0:
            raise OSError("%s failed (GDI+ status %d)" % (what, st))

    def configure(self, sw, sh, dst_bits, dw, dh, src_rect):
        """src_rect: the (x, y, w, h) of the source that fills the whole dw x dh target."""
        self.release()
        gp = self.gp
        self.nbytes = sw * sh * 4
        self.src_buf = (ctypes.c_ubyte * self.nbytes)()
        src = ctypes.c_void_p()
        self._chk(gp.CreateBitmapFromScan0(sw, sh, sw * 4, PixelFormat32bppPARGB,
                                           ctypes.addressof(self.src_buf), ctypes.byref(src)),
                  "GdipCreateBitmapFromScan0(src)")
        self.src = src
        dst = ctypes.c_void_p()
        self._chk(gp.CreateBitmapFromScan0(dw, dh, dw * 4, PixelFormat32bppPARGB, dst_bits,
                                           ctypes.byref(dst)), "GdipCreateBitmapFromScan0(dst)")
        self.dst = dst
        g = ctypes.c_void_p()
        self._chk(gp.GetImageGraphicsContext(dst, ctypes.byref(g)), "GdipGetImageGraphicsContext")
        self.g = g
        self._chk(gp.SetCompositingMode(g, CompositingModeSourceCopy), "GdipSetCompositingMode")
        self._chk(gp.SetInterpolationMode(g, InterpolationModeHighQualityBicubic),
                  "GdipSetInterpolationMode")
        self._chk(gp.SetPixelOffsetMode(g, PixelOffsetModeHighQuality), "GdipSetPixelOffsetMode")
        self.dw, self.dh = dw, dh
        self.src_rect = src_rect

    def draw(self, raw):
        ctypes.memmove(self.src_buf, raw, self.nbytes)
        gp = self.gp
        gp.GraphicsClear(self.g, 0)
        x, y, w, h = self.src_rect
        st = gp.DrawImageRectRect(self.g, self.src, 0.0, 0.0, self.dw, self.dh, x, y, w, h,
                                  UnitPixel, self.attrs, None, None)
        gp.Flush(self.g, FlushIntentionSync)
        self._chk(st, "GdipDrawImageRectRect")

    def release(self):
        gp = self.gp
        if self.g:
            gp.DeleteGraphics(self.g)
        if self.dst:
            gp.DisposeImage(self.dst)
        if self.src:
            gp.DisposeImage(self.src)
        self.g = self.dst = self.src = None
        self.src_buf = None

    def shutdown(self):
        try:
            self.release()
            if self.attrs:
                self.gp.DisposeImageAttributes(self.attrs)
                self.attrs = None
        finally:
            if self.token:
                self.gp.Shutdown(self.token)
                self.token = None


class SignBoard(object):
    """The board on a sign's stick: its own small layered window, click-through, drawn with GDI+ at the size it is
    shown, so the words read the same for every pet and every size.  Drawn again only when the words or the size
    change; fades in and out with the window's constant alpha."""

    WOOD, WOOD_EDGE, SLATE, CHALK, SHADE = 0xFF966840, 0xFF6E4A2C, 0xFF2E5440, 0xFFF6F4EC, 0x38000000
    FONTS = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")
    ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
    # kind -> (glyph in Segoe Fluent Icons, its chalk colour)
    ICONS = {"read": ("\ue721", 0xFF8CBEF0), "edit": ("\ue70f", 0xFFC8AAF0), "run": ("\ue756", 0xFFDCE2EC),
             "web": ("\ue774", 0xFF8CBEF0), "agent": ("\ue724", 0xFF78DCCD), "compact": ("\ue8f1", 0xFFF0C878),
             "stop": ("\ue73e", 0xFF96E196), "attention": ("\uea8f", 0xFFFFBE78), "stopfail": ("\ue783", 0xFFFF8C8C),
             "think": ("\ue82f", 0xFFFFE07A), "levelup": ("\ue735", 0xFFFFD24A), "discover": ("\uf133", 0xFF8FF0C8),
             "look": ("\ue790", 0xFFFFC8DC), "gift": (None, 0xFFFFB3C8)}      # a gift: a little box drawn (no glyph for it)
    # the growth signs are boards of their own: kind -> (frame, its edge, slate, nails, bar, the chalk's two
    # colours; None: a rainbow that goes round).  A level-up is gold on a night sky with sparkles on the frame,
    # a first find mint on deep teal; both shimmer, and a bar under the words fills up.
    GROW_STYLE = {"levelup": (0xFFE2B33C, 0xFF9C6E12, 0xFF2B2452, None, 0xFFFFD24A, None),
                  "discover": (0xFF5E9C93, 0xFF3C6E66, 0xFF1E3A40, 0xFFD8F4EE, 0xFF8FF0C8, (0xFFB4F5DC, 0xFFA8D8FF)),
                  "gift": (0xFFE58FA7, 0xFFAE5470, 0xFF3C2142, 0xFFFFF0F4, 0xFFFFB3C8, (0xFFFFD6E2, 0xFFFFF1B8))}
    # the looks of a plain sign (SIGN_LOOKS): a frame -> (its colour, its edge, nails or None, what is on it); the
    # banner's cloth is the slate, its hems the frame's colour
    FRAMES = {"wood": (0xFF966840, 0xFF6E4A2C, 0xFFC8CAD2, None),
              "dots": (0xFFF3E3C3, 0xFFC9A66B, None, "dots"),
              "stars": (0xFF34457E, 0xFF1F2B55, None, "stars")}
    DOTS = (0xFFFF8FB1, 0xFFFFD45E, 0xFF79C2FF, 0xFF7FE0B0)

    def __init__(self, family):
        self.family = family
        self.gp = None
        self.token = None
        self.hwnd = None
        self.memdc = self.hbmp = self.stock = None
        self.bits = None
        self.w = self.h = 0
        self.lift = 0                          # px of shadow under the board
        self.key = None                        # (kind, text, font px) drawn now
        self.alpha = 0.0
        self.shown = False
        self.t = None
        self.pos = None
        self.broken = False

    def _start(self):
        self.gp = _gdiplus()
        inp = GdiplusStartupInput(1, None, 0, 0)
        tok = ULONG_PTR(0)
        if self.gp.Startup(ctypes.byref(tok), ctypes.byref(inp), None) != 0:
            raise OSError("GdiplusStartup failed")
        self.token = tok.value
        self.memdc = CreateCompatibleDC(None)
        ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT
        self.hwnd = CreateWindowExW(ex, CLASS_NAME, SIGN_TITLE, WS_POPUP, 0, 0, 1, 1, None, None, self.family.hinst, None)
        if not self.hwnd or not self.memdc:
            raise ctypes.WinError(ctypes.get_last_error())

    def _family(self, names):
        fam = ctypes.c_void_p()
        for name in names:
            if self.gp.CreateFontFamilyFromName(name, None, ctypes.byref(fam)) == 0:
                return fam
        return None

    def _rrect(self, x0, y0, x1, y1, r):
        gp = self.gp
        path = ctypes.c_void_p()
        gp.CreatePath(0, ctypes.byref(path))
        d = 2 * max(0.5, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
        gp.AddPathArc(path, x0, y0, d, d, 180.0, 90.0)
        gp.AddPathArc(path, x1 - d, y0, d, d, 270.0, 90.0)
        gp.AddPathArc(path, x1 - d, y1 - d, d, d, 0.0, 90.0)
        gp.AddPathArc(path, x0, y1 - d, d, d, 90.0, 90.0)
        gp.ClosePathFigure(path)
        return path

    def _banner(self, x0, y0, x1, y1, notch, inset=0.0):
        """A banner with forked ends (a V cut into each): inset keeps the cut's lines (its cloth inside the hems)."""
        pts = (POINTF * 6)()
        mid = (y0 + y1) / 2.0
        k = notch * inset / max(1.0, (y1 - y0) / 2.0 + inset)          # along the cut, inside by as much as the hem
        for i, (x, y) in enumerate(((x0 + k, y0), (x1 - k, y0), (x1 - notch, mid), (x1 - k, y1), (x0 + k, y1), (x0 + notch, mid))):
            pts[i] = POINTF(x, y)
        path = ctypes.c_void_p()
        self.gp.CreatePath(0, ctypes.byref(path))
        self.gp.AddPathPolygon(path, pts, 6)
        return path

    def _fill(self, g, path, argb):
        brush = ctypes.c_void_p()
        self.gp.CreateSolidFill(argb, ctypes.byref(brush))
        self.gp.FillPath(g, brush, path)
        self.gp.DeleteBrush(brush)

    def _stroke(self, g, path, argb, width):
        pen = ctypes.c_void_p()
        self.gp.CreatePen1(argb, float(width), UnitPixel, ctypes.byref(pen))
        self.gp.DrawPath(g, pen, path)
        self.gp.DeletePen(pen)

    def _draw(self, kind, text, px, deco=None):
        """A little blackboard in a wooden frame: the kind's icon in coloured chalk, the words in white chalk.
        Measure, size the window's bitmap to it, paint it."""
        if kind in self.GROW_STYLE and deco is not None:
            try:
                self._draw_grow(kind, text, px, deco)
                return
            except Exception:
                log_exc("growth sign; a plain one instead")    # the other signs must not go with it
        gp = self.gp
        tfam = self._family(self.FONTS)
        if tfam is None:
            raise OSError("no font for the sign")
        ifam = self._family(self.ICON_FONTS)
        glyph, icol = self.ICONS.get(kind, (None, 0))
        if ifam is None:
            glyph = None
        font = ctypes.c_void_p()
        gp.CreateFont(tfam, float(px), 1, UnitPixel, ctypes.byref(font))         # 1: bold
        fmt = ctypes.c_void_p()
        gp.CreateStringFormat(0x1000, 0, ctypes.byref(fmt))       # no wrap
        gp.SetStringFormatAlign(fmt, 0)
        gp.SetStringFormatLineAlign(fmt, 1)
        try:
            probe = ctypes.c_void_p()                              # measure on a 1 x 1 bitmap of its own
            gp.CreateBitmapFromScan0(1, 1, 4, PixelFormat32bppPARGB, None, ctypes.byref(probe))
            g = ctypes.c_void_p()
            gp.GetImageGraphicsContext(probe, ctypes.byref(g))
            gp.SetTextRenderingHint(g, 4)
            box = RECTF()
            gp.MeasureString(g, text, len(text), font, ctypes.byref(RECTF(0, 0, 4000, 1000)), fmt, ctypes.byref(box), None, None)
            gp.DeleteGraphics(g)
            gp.DisposeImage(probe)
            look = self.family.look
            chalk = next((c for n, _, c, _ in SIGN_CHALKS if n == look.get("chalk")), self.CHALK)
            wood, edge, nail_c, deco = self.FRAMES.get(look.get("frame"), self.FRAMES["wood"])
            flag = look.get("board") == "flag"
            frame = max(3.0, 0.3 * px)                             # the wooden frame (a banner: its hems)
            padx, pady = 0.5 * px, 0.26 * px
            isz = 1.05 * px if glyph else 0.0                      # the icon, and the room after it
            igap = 0.38 * px if glyph else 0.0
            shade = max(2, int(round(0.12 * px)))                  # a soft shadow under it
            bh = int(math.ceil(2 * frame + 2 * pady + max(box.Height, 1.25 * px))) + 2
            notch = 0.32 * bh if flag else 0.0                     # a banner's forked ends
            w = int(math.ceil(2 * frame + 2 * padx + isz + igap + box.Width + 2 * notch)) + 2
            h = bh + shade
            self._dib(w, h)
            bmp = ctypes.c_void_p()
            gp.CreateBitmapFromScan0(w, h, w * 4, PixelFormat32bppPARGB, self.bits, ctypes.byref(bmp))
            g = ctypes.c_void_p()
            gp.GetImageGraphicsContext(bmp, ctypes.byref(g))
            gp.GraphicsClear(g, 0)
            gp.SetSmoothingMode(g, 4)                              # antialias
            gp.SetTextRenderingHint(g, 4)                          # antialias: right with alpha, unlike ClearType
            r = 0.45 * px
            x0, y0, x1, y1 = 1.0, 1.0, w - 1.0, bh - 1.0
            if flag:
                for dy, col, inset in ((shade, self.SHADE, 0.0), (0.0, wood, 0.0), (0.0, self.SLATE, frame * 0.62)):
                    path = self._banner(x0 + 1 if dy else x0, y0 + dy + inset, x1 - 1 if dy else x1, y1 + dy - inset, notch, inset)
                    self._fill(g, path, col)
                    if col == wood:
                        self._stroke(g, path, edge, max(1.0, px / 14.0))
                    gp.DeletePath(path)
            else:
                path = self._rrect(x0 + 1, y0 + shade, x1 - 1, y1 + shade, r)
                self._fill(g, path, self.SHADE)
                gp.DeletePath(path)
                path = self._rrect(x0, y0, x1, y1, r)
                self._fill(g, path, wood)
                self._stroke(g, path, edge, max(1.0, px / 14.0))
                gp.DeletePath(path)
                path = self._rrect(x0 + frame, y0 + frame, x1 - frame, y1 - frame, r * 0.4)
                self._fill(g, path, self.SLATE)
                gp.DeletePath(path)
            f2 = frame * (0.31 if flag else 0.5)                    # the middle of the frame (of a hem)
            if nail_c is not None and not flag:                    # two nails in the frame's top corners
                nr = max(1.0, 0.09 * px)
                for nx in (x0 + frame * 0.55, x1 - frame * 0.55):
                    path = ctypes.c_void_p()
                    gp.CreatePath(0, ctypes.byref(path))
                    gp.AddPathEllipse(path, nx - nr, y0 + frame * 0.55 - nr, 2 * nr, 2 * nr)
                    self._fill(g, path, nail_c)
                    gp.DeletePath(path)
            elif deco == "dots":                                   # a row of coloured dots along the top and the bottom
                dr = max(1.0, 0.12 * px)
                xa, xb = x0 + notch + frame * 0.9, x1 - notch - frame * 0.9
                n = max(2, int((xb - xa) / (0.62 * px)) + 1)
                for row, yy in enumerate((y0 + f2, y1 - f2)):
                    for k in range(n):
                        xx = xa + (xb - xa) * k / float(n - 1)
                        path = ctypes.c_void_p()
                        gp.CreatePath(0, ctypes.byref(path))
                        gp.AddPathEllipse(path, xx - dr, yy - dr, 2 * dr, 2 * dr)
                        self._fill(g, path, self.DOTS[(k + 2 * row) % len(self.DOTS)])
                        gp.DeletePath(path)
            elif deco == "stars":                                  # stars in the corners and on the top
                spots = ((x0 + notch + f2 * 1.4, y0 + f2), ((x0 + x1) / 2.0, y0 + f2), (x1 - notch - f2 * 1.4, y0 + f2),
                         (x0 + notch + f2 * 1.4, y1 - f2), (x1 - notch - f2 * 1.4, y1 - f2))
                for i, (sx, sy) in enumerate(spots):
                    self._star(g, sx, sy, max(1.5, (0.3 if i == 1 else 0.24) * px), 0xFFFFD86A)
            cx = x0 + frame + padx + notch
            cy0, ch = y0 + frame, y1 - y0 - 2 * frame
            if glyph:                                              # the icon as a path: filled and outlined, so it reads bold
                path = ctypes.c_void_p()
                gp.CreatePath(0, ctypes.byref(path))
                ifmt = ctypes.c_void_p()
                gp.CreateStringFormat(0x1000, 0, ctypes.byref(ifmt))
                gp.SetStringFormatAlign(ifmt, 1)
                gp.SetStringFormatLineAlign(ifmt, 1)
                gp.AddPathString(path, glyph, 1, ifam, 0, float(isz),
                                 ctypes.byref(RECTF(cx - 0.2 * px, cy0, isz + 0.4 * px, ch)), ifmt)
                gp.DeleteStringFormat(ifmt)
                self._fill(g, path, icol)
                self._stroke(g, path, icol, max(1.0, 0.07 * px))
                gp.DeletePath(path)
            ink = ctypes.c_void_p()
            gp.CreateSolidFill(chalk, ctypes.byref(ink))
            gp.DrawString(g, text, len(text), font, ctypes.byref(RECTF(cx + isz + igap, cy0 + 0.04 * px, box.Width + 4, ch)), fmt, ink)
            gp.DeleteBrush(ink)
            gp.Flush(g, FlushIntentionSync)
            gp.DeleteGraphics(g)
            gp.DisposeImage(bmp)
            self.lift = shade
        finally:
            gp.DeleteStringFormat(fmt)
            gp.DeleteFont(font)
            gp.DeleteFontFamily(tfam)
            if ifam is not None:
                gp.DeleteFontFamily(ifam)

    @staticmethod
    def _hsv(h, s, v):
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
        return 0xFF000000 | int(r * 255) << 16 | int(g * 255) << 8 | int(b * 255)

    def _star(self, g, x, y, r, argb):
        """A four-pointed sparkle."""
        pts = (POINTF * 8)()
        for i in range(8):
            a = math.pi / 4.0 * i
            k = r if i % 2 == 0 else 0.3 * r
            pts[i] = POINTF(x + k * math.sin(a), y - k * math.cos(a))
        path = ctypes.c_void_p()
        self.gp.CreatePath(0, ctypes.byref(path))
        self.gp.AddPathPolygon(path, pts, 8)
        self._fill(g, path, argb)
        self.gp.DeletePath(path)

    def _gift_box(self, g, x, y, size, argb, phase):
        """A present: a box with its lid, a ribbon down the middle, a bow on top that bobs a little (phase)."""
        gp = self.gp
        s = size / 2.0
        bob = 0.04 * size * math.sin(2.0 * math.pi * phase / GROW_PHASES)
        ribbon = 0xFFFFF1B8
        for x0, y0, x1, y1, col, r in ((x - 0.78 * s, y - 0.22 * s, x + 0.78 * s, y + 0.86 * s, argb, 0.1 * s),     # the box
                                       (x - 0.92 * s, y - 0.5 * s, x + 0.92 * s, y - 0.16 * s, argb, 0.1 * s),      # its lid
                                       (x - 0.13 * s, y - 0.5 * s, x + 0.13 * s, y + 0.86 * s, ribbon, 0.02 * s)):   # the ribbon
            path = self._rrect(x0, y0, x1, y1, r)
            self._fill(g, path, col)
            gp.DeletePath(path)
        for side in (-1, 1):                       # the bow: two loops leaning out
            path = ctypes.c_void_p()
            gp.CreatePath(0, ctypes.byref(path))
            gp.AddPathEllipse(path, x + (0.04 if side > 0 else -0.6) * s, y - 0.86 * s + bob, 0.56 * s, 0.38 * s)
            self._stroke(g, path, ribbon, max(1.0, 0.13 * s))
            gp.DeletePath(path)

    def _draw_grow(self, kind, text, px, deco):
        """A level-up or a first find: the icon and the words in chalk that shimmers, under them a bar that fills
        (deco: its fill 0..1, the shimmer's step, the words after the bar)."""
        fill, phase, label = deco
        frame_c, edge_c, slate_c, nail_c, bar_c, chalk = self.GROW_STYLE[kind]
        gp = self.gp
        tfam = self._family(self.FONTS)
        if tfam is None:
            raise OSError("no font for the sign")
        ifam = self._family(self.ICON_FONTS)
        glyph, icol = self.ICONS[kind]
        if ifam is None:
            glyph = None
        boxed = kind == "gift"                     # its icon is a little box, drawn
        font, small, fmt = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        gp.CreateFont(tfam, float(px), 1, UnitPixel, ctypes.byref(font))
        gp.CreateFont(tfam, float(max(9.0, 0.62 * px)), 1, UnitPixel, ctypes.byref(small))   # never too small to read
        gp.CreateStringFormat(0x1000, 0, ctypes.byref(fmt))
        gp.SetStringFormatAlign(fmt, 0)
        gp.SetStringFormatLineAlign(fmt, 1)
        try:
            probe = ctypes.c_void_p()
            gp.CreateBitmapFromScan0(1, 1, 4, PixelFormat32bppPARGB, None, ctypes.byref(probe))
            g = ctypes.c_void_p()
            gp.GetImageGraphicsContext(probe, ctypes.byref(g))
            gp.SetTextRenderingHint(g, 4)
            box, lbox = RECTF(), RECTF()
            gp.MeasureString(g, text, len(text), font, ctypes.byref(RECTF(0, 0, 4000, 1000)), fmt, ctypes.byref(box), None, None)
            gp.MeasureString(g, label, len(label), small, ctypes.byref(RECTF(0, 0, 4000, 1000)), fmt, ctypes.byref(lbox), None, None)
            gp.DeleteGraphics(g)
            gp.DisposeImage(probe)
            frame = max(3.0, 0.3 * px)
            padx, pady = 0.5 * px, 0.24 * px
            isz = 1.05 * px if glyph or boxed else 0.0
            igap = 0.38 * px if glyph or boxed else 0.0
            row1_w = isz + igap + box.Width
            row1_h = max(box.Height, 1.25 * px)
            barh = max(3.0, 0.28 * px)
            lgap = 0.3 * px
            row2_h = max(lbox.Height, barh)
            rgap = 0.1 * px
            inner_w = max(row1_w, 4.0 * px + lgap + lbox.Width)     # the bar at least this long
            shade = max(2, int(round(0.12 * px)))
            m = int(math.ceil(0.3 * px)) if nail_c is None else 0     # room round the board for the sparkles
            w = int(math.ceil(2 * frame + 2 * padx + inner_w)) + 2 + 2 * m
            bh = int(math.ceil(2 * frame + 2 * pady + row1_h + rgap + row2_h)) + 2 + 2 * m
            h = bh + shade
            self._dib(w, h)
            bmp = ctypes.c_void_p()
            gp.CreateBitmapFromScan0(w, h, w * 4, PixelFormat32bppPARGB, self.bits, ctypes.byref(bmp))
            g = ctypes.c_void_p()
            gp.GetImageGraphicsContext(bmp, ctypes.byref(g))
            gp.GraphicsClear(g, 0)
            gp.SetSmoothingMode(g, 4)
            gp.SetTextRenderingHint(g, 4)
            r = 0.45 * px
            x0, y0, x1, y1 = 1.0 + m, 1.0 + m, w - 1.0 - m, bh - 1.0 - m
            path = self._rrect(x0 + 1, y0 + shade, x1 - 1, y1 + shade, r)
            self._fill(g, path, self.SHADE)
            gp.DeletePath(path)
            path = self._rrect(x0, y0, x1, y1, r)
            self._fill(g, path, frame_c)
            self._stroke(g, path, edge_c, max(1.0, px / 14.0))
            gp.DeletePath(path)
            path = self._rrect(x0 + frame, y0 + frame, x1 - frame, y1 - frame, r * 0.4)
            self._fill(g, path, slate_c)
            gp.DeletePath(path)
            t = 2.0 * math.pi * phase / GROW_PHASES
            if nail_c is not None:
                nr = max(1.0, 0.09 * px)
                for nx in (x0 + frame * 0.55, x1 - frame * 0.55):
                    path = ctypes.c_void_p()
                    gp.CreatePath(0, ctypes.byref(path))
                    gp.AddPathEllipse(path, nx - nr, y0 + frame * 0.55 - nr, 2 * nr, 2 * nr)
                    self._fill(g, path, nail_c)
                    gp.DeletePath(path)
            else:                                      # sparkles in the frame's corners and on its top, twinkling in turn
                f2 = frame * 0.5
                spots = ((x0 + f2, y0 + f2), (x1 - f2, y0 + f2), ((x0 + x1) / 2.0, y0 + f2), (x0 + f2, y1 - f2), (x1 - f2, y1 - f2))
                for i, (sx, sy) in enumerate(spots):
                    k = 0.5 + 0.5 * math.sin(2 * t + i * 1.9)
                    self._star(g, sx, sy, max(1.5, (0.28 + 0.3 * k) * px), 0xFFFFF6C8)
            cx = x0 + frame + padx + (inner_w - row1_w) / 2.0
            top = y0 + frame + pady
            if glyph:
                path = ctypes.c_void_p()
                gp.CreatePath(0, ctypes.byref(path))
                ifmt = ctypes.c_void_p()
                gp.CreateStringFormat(0x1000, 0, ctypes.byref(ifmt))
                gp.SetStringFormatAlign(ifmt, 1)
                gp.SetStringFormatLineAlign(ifmt, 1)
                gp.AddPathString(path, glyph, 1, ifam, 0, float(isz), ctypes.byref(RECTF(cx - 0.2 * px, top, isz + 0.4 * px, row1_h)), ifmt)
                gp.DeleteStringFormat(ifmt)
                self._fill(g, path, icol)
                self._stroke(g, path, icol, max(1.0, 0.07 * px))
                gp.DeletePath(path)
            elif boxed:
                self._gift_box(g, cx + isz / 2.0, top + row1_h / 2.0, isz, icol, phase)
            # the words: a gradient that slides along them, so the chalk shimmers
            tx = cx + isz + igap
            span = max(2.0 * px, 0.6 * box.Width)
            off = 2.0 * span * phase / GROW_PHASES
            if chalk is None:
                hue = float(phase) / GROW_PHASES
                c1, c2 = self._hsv(hue, 0.38, 1.0), self._hsv(hue + 0.33, 0.38, 1.0)
            else:
                c1, c2 = chalk
            ink = ctypes.c_void_p()
            gp.CreateLineBrush(ctypes.byref(POINTF(tx - off, 0)), ctypes.byref(POINTF(tx - off + span, 0)), c1, c2, 3, ctypes.byref(ink))
            gp.DrawString(g, text, len(text), font, ctypes.byref(RECTF(tx, top + 0.04 * px, box.Width + 4, row1_h)), fmt, ink)
            gp.DeleteBrush(ink)
            # the bar and what it says after it
            bx0 = x0 + frame + padx
            bw = inner_w - lgap - lbox.Width
            ry = top + row1_h + rgap
            by = ry + (row2_h - barh) / 2.0
            path = self._rrect(bx0, by, bx0 + bw, by + barh, barh / 2.0)
            self._fill(g, path, 0x60000000)
            gp.DeletePath(path)
            if fill > 0:
                path = self._rrect(bx0, by, bx0 + max(barh, bw * min(1.0, fill)), by + barh, barh / 2.0)
                self._fill(g, path, bar_c)
                gp.DeletePath(path)
            ink = ctypes.c_void_p()
            gp.CreateSolidFill(bar_c, ctypes.byref(ink))
            gp.DrawString(g, label, len(label), small, ctypes.byref(RECTF(bx0 + bw + lgap, ry, lbox.Width + 4, row2_h)), fmt, ink)
            gp.DeleteBrush(ink)
            gp.Flush(g, FlushIntentionSync)
            gp.DeleteGraphics(g)
            gp.DisposeImage(bmp)
            self.lift = shade + m              # the board's foot, not the bitmap's, on the point it is shown at
        finally:
            gp.DeleteStringFormat(fmt)
            gp.DeleteFont(font)
            gp.DeleteFont(small)
            gp.DeleteFontFamily(tfam)
            if ifam is not None:
                gp.DeleteFontFamily(ifam)

    def _dib(self, w, h):
        if self.hbmp and w == self.w and h == self.h:      # the same size (a growth sign's next step): cleared and used again
            GdiFlush()
            ctypes.memset(self.bits, 0, w * h * 4)
            return
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bits = LPVOID()
        hbmp = CreateDIBSection(self.memdc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not hbmp or not bits.value:
            raise ctypes.WinError(ctypes.get_last_error())
        GdiFlush()
        old = SelectObject(self.memdc, hbmp)
        if self.stock is None:
            self.stock = old
        if self.hbmp:
            DeleteObject(self.hbmp)
        self.hbmp, self.bits, self.w, self.h = hbmp, bits.value, w, h
        ctypes.memset(self.bits, 0, w * h * 4)

    def update(self, now, kind, text, px, at, visible, sink=0.28, deco=None):
        """at: (x, y) on the screen of the stick's top (or the point over a head), or None; sink: how much of
        the board is below it; deco: what moves on a growth sign (drawn again when it changes).
        -> True while it is still shown (fading out included)."""
        if self.broken:
            return False
        dt = 0.0 if self.t is None else min(now - self.t, 0.2)
        self.t = now
        want = 1.0 if (visible and text and at is not None) else 0.0
        if want == 0.0 and self.alpha == 0.0:
            if self.shown:
                ShowWindow(self.hwnd, SW_HIDE)
                self.shown = False
            self.t = None
            return False
        try:
            if self.hwnd is None:
                self._start()
            look = tuple(sorted(self.family.look.items()))
            if want and (kind, text, px, deco, look) != self.key:
                self._draw(kind, text, px, deco)
                self.key = (kind, text, px, deco, look)
            if not self.key:
                return False
            step = dt / SIGN_FADE_SECS
            self.alpha = min(1.0, self.alpha + step) if want else max(0.0, self.alpha - step)
            if want and not self.shown:
                self.alpha = max(self.alpha, 0.2)
            if at is not None:
                bh = self.h - self.lift            # the stick goes in behind the board's lower part
                x, y = int(round(at[0] - self.w / 2.0)), int(round(at[1] - (1.0 - sink) * bh))
                wa = self.family.leader._work_area(int(at[0]), int(at[1]))
                x = clamp(x, wa.left, wa.right - self.w)
                y = clamp(y, wa.top, wa.bottom - self.h)
                self.pos = (x, y)
            if self.pos is None:
                return False
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, int(round(255 * self.alpha)), AC_SRC_ALPHA)
            UpdateLayeredWindow(self.hwnd, None, ctypes.byref(POINT(*self.pos)), ctypes.byref(SIZE(self.w, self.h)),
                                self.memdc, ctypes.byref(POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
            if not self.shown:
                ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
                SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                self.shown = True
            if self.alpha == 0.0:
                ShowWindow(self.hwnd, SW_HIDE)
                self.shown = False
                return False
            return True
        except Exception:
            log_exc("sign board; no more signs")
            self.broken = True
            self.destroy()
            return False

    def raise_top(self):
        if self.shown and self.hwnd:
            SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def destroy(self):
        try:
            if self.hwnd:
                DestroyWindow(self.hwnd)
            if self.memdc:
                if self.stock:
                    SelectObject(self.memdc, self.stock)
                DeleteDC(self.memdc)
            if self.hbmp:
                DeleteObject(self.hbmp)
            if self.token:
                self.gp.Shutdown(self.token)
        except Exception:
            log_exc("sign board cleanup")
        self.hwnd = self.memdc = self.hbmp = self.stock = self.token = None
        self.shown = False

    def hide_now(self):
        """Gone at once, no fade (the family is hidden)."""
        self.alpha = 0.0
        self.t = None
        if self.shown and self.hwnd:
            ShowWindow(self.hwnd, SW_HIDE)
        self.shown = False


TALKS_TITLE = "ClawdTalks"  # the conversations' numbered circles (tests leave it out when they count the pets)
TALK_KEEP = 1800.0          # s without a word from a conversation that is not at work: its circle goes.  Not one
                            # waiting for you mid-turn (orange): that one stays till its next word, however long you
                            # take (README; 2026-11-15: it went after these 30 minutes, gone when you came back to it),
                            # but for one back from before a restart (what it did meanwhile, nobody said)
TALK_DONE_KEEP = 60.0       # s a circle stays green (done) or red (an error) after the turn, then it goes (用户 2026-11-13)
CUT_QUIET = 15.0            # s a Claude Code turn at work says nothing before its transcript is looked at: Esc / the
                            # stop button sends no hook (no Stop), and the big one worked on up to BUSY_TIMEOUT
                            # (2026-11-14: 3 of 12 interrupts in a week, 10 minutes each)
CUT_PEEK = 5.0              # s between looks while it stays quiet
TALK_MAX = 9                # circles at most
LINK_SETTLE = 4.0           # s after a link of an app is opened in which that app's "the one open" is not to be trusted
                            # (2026-11-14: ③ clicked, its link on its way; ④ clicked a second later and taken for the
                            # one open, no link; then ③'s link came and the app stayed there, not at ④)
CODEX_WAIT = 8.0            # s a Codex conversation not (yet) in Codex's thread list waits for it, unshown; then it is
                            # taken for one of Codex's own background jobs (2026-11-14: its memory work, a read-only job)
TALK_SHOW_FROM = 1          # circles from the first conversation on (用户 2026-11-13: "有一个也显示")
TALK_MARK_FROM = 2          # the signs say a number only when there are several
TALK_COL = {"cut": 0xFF98A0AA, "busy": 0xFF4F8FE0, "wait": 0xFFF09A2E, "done": 0xFF52B565, "error": 0xFFE5574F, "idle": 0xFF4F8FE0}
# "idle" (no end seen and the big one not at work on it: back after a restart, quiet over BUSY_TIMEOUT) looks as "busy":
# the conversation may well be at work still (Antigravity thinking says nothing); grey is only for one you stopped
# (round 9, the user: no "闲着").  It goes after TALK_KEEP silent as before


class TalkDots(SignBoard):
    """The conversations at the family's feet: a row of numbered circles in a small window of its own, one a
    conversation, its colour what it is at (at work, waiting for you, done, stopped on an error).  Only when there
    are TALK_SHOW_FROM or more.  A click on one brings that conversation's window to the front (the window its hook
    told us: an "at" line).  Drawn again only when a number or a colour changes; moved only when the big one moves."""

    def __init__(self, family):
        SignBoard.__init__(self, family)
        self.cells = []                        # (x0, x1, session) across the window
        self.put = None                        # (key, pos) as it is on the screen
        self.hover = False                     # the mouse is (maybe) on the row: the ticks look where, till it is off

    def _start(self):
        self.gp = _gdiplus()
        inp = GdiplusStartupInput(1, None, 0, 0)
        tok = ULONG_PTR(0)
        if self.gp.Startup(ctypes.byref(tok), ctypes.byref(inp), None) != 0:
            raise OSError("GdiplusStartup failed")
        self.token = tok.value
        self.memdc = CreateCompatibleDC(None)
        ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE       # not click-through
        self.hwnd = CreateWindowExW(ex, CLASS_NAME, TALKS_TITLE, WS_POPUP, 0, 0, 1, 1, None, None, self.family.hinst, None)
        if not self.hwnd or not self.memdc:
            raise ctypes.WinError(ctypes.get_last_error())

    def _draw_dots(self, dots, d):
        """dots: ((number, state, session), ...) left to right; d: a circle's diameter in px."""
        gp = self.gp
        gap = max(2, int(round(0.3 * d)))
        shade = max(1, int(round(0.1 * d)))
        w = len(dots) * d + (len(dots) - 1) * gap + 2
        h = d + shade + 2
        self._dib(w, h)
        fam = self._family(("Segoe UI", "Microsoft YaHei UI"))
        if fam is None:
            raise OSError("no font for the circles")
        font = ctypes.c_void_p()
        gp.CreateFont(fam, float(0.66 * d), 1, UnitPixel, ctypes.byref(font))
        fmt = ctypes.c_void_p()
        gp.CreateStringFormat(0x1000, 0, ctypes.byref(fmt))
        gp.SetStringFormatAlign(fmt, 1)
        gp.SetStringFormatLineAlign(fmt, 1)
        try:
            bmp = ctypes.c_void_p()
            gp.CreateBitmapFromScan0(w, h, w * 4, PixelFormat32bppPARGB, self.bits, ctypes.byref(bmp))
            g = ctypes.c_void_p()
            gp.GetImageGraphicsContext(bmp, ctypes.byref(g))
            gp.GraphicsClear(g, 0)
            gp.SetSmoothingMode(g, 4)
            gp.SetTextRenderingHint(g, 4)
            self.cells = []
            edge = max(1.0, d / 12.0)
            ink = ctypes.c_void_p()
            gp.CreateSolidFill(0xFFFFFFFF, ctypes.byref(ink))
            for i, (n, state, session) in enumerate(dots):
                x = 1.0 + i * (d + gap)
                for dy, col in ((shade, self.SHADE), (0.0, TALK_COL.get(state, TALK_COL["idle"]))):
                    path = ctypes.c_void_p()
                    gp.CreatePath(0, ctypes.byref(path))
                    gp.AddPathEllipse(path, x + edge / 2, 1.0 + dy + edge / 2, d - edge, d - edge)
                    self._fill(g, path, col)
                    if not dy:
                        self._stroke(g, path, 0xFFFFFFFF, edge)
                    gp.DeletePath(path)
                text = str(n)
                gp.DrawString(g, text, len(text), font, ctypes.byref(RECTF(x - d, 1.0 + 0.04 * d, 3.0 * d, float(d))), fmt, ink)
                self.cells.append((int(x), int(x + d), session))
            gp.DeleteBrush(ink)
            gp.Flush(g, FlushIntentionSync)
            gp.DeleteGraphics(g)
            gp.DisposeImage(bmp)
        finally:
            gp.DeleteStringFormat(fmt)
            gp.DeleteFont(font)
            gp.DeleteFontFamily(fam)

    def show(self, dots, d, at):
        """at: (x, y) on the screen of the middle of the row's top edge; dots empty or at None: gone."""
        if self.broken:
            return
        if not dots or at is None:
            if self.shown:
                self.hide_now()
            return
        try:
            if self.hwnd is None:
                self._start()
            key = (dots, d)
            if key != self.key:
                self._draw_dots(dots, d)
                self.key = key
            x, y = int(round(at[0] - self.w / 2.0)), int(round(at[1]))
            wa = self.family.leader._work_area(int(at[0]), int(at[1]))
            pos = (clamp(x, wa.left, wa.right - self.w), clamp(y, wa.top, wa.bottom - self.h))
            if self.put != (key, pos) or not self.shown:
                blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
                UpdateLayeredWindow(self.hwnd, None, ctypes.byref(POINT(*pos)), ctypes.byref(SIZE(self.w, self.h)),
                                    self.memdc, ctypes.byref(POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
                self.put = (key, pos)
            if not self.shown:
                ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
                SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                self.shown = True
        except Exception:
            log_exc("the conversations' circles; no more of them")
            self.broken = True
            self.destroy()

    def at_x(self, lparam=None, x=None):
        if x is None:
            x = ctypes.c_short(lparam & 0xFFFF).value
        return next(((session, (x0 + x1) // 2) for x0, x1, session in self.cells if x0 <= x <= x1), (None, None))

    def handle(self, msg, wparam, lparam):
        if msg == WM_LBUTTONUP:
            session = self.at_x(lparam)[0]
            if session:
                self.family.talk_jump(session, time.perf_counter())
            return 0
        if msg == WM_MOUSEMOVE:                # the mouse came onto the row: from now on each tick looks where it is
            self.hover = True
            return 0
        if msg in (WM_LBUTTONDOWN, WM_LBUTTONDBLCLK, WM_RBUTTONDOWN, WM_RBUTTONUP):
            return 0
        return None


class TalkTitles(object):
    """A conversation's name as its agent shows it, read where the agent keeps it (only while the mouse is over its
    circle; again when that file changes, so a rename shows at once).  From the first 8 characters of its id:
      Claude desktop app: its session's own file (claude-code-sessions/.../local_*.json, "title"; "cliSessionId" is
                          the id the hooks get)
      Claude Code in a terminal: the last "custom-title" (a rename) or else "ai-title" line near the end of its
                          transcript (~/.claude/projects/*/<id>.jsonl)
      Codex: the last line of ~/.codex/session_index.jsonl for that id ("thread_name"); before a thread is named
             there, its first message as Codex keeps it in its thread list (~/.codex/state_<n>.sqlite, "threads").
             A Codex conversation's 8 characters are the END of its id (clawd_hook.py session_key); an older event
             line's, the start: both are looked for
      DeepSeek Harness: its session's cached view, ~/.dsh/storages/session_projcache/sessions/session-<id>.json
                          (record.rows.title.val; DSH_HOME moves ~/.dsh)
      Antigravity: ~/.gemini/antigravity/conversation_summaries.db (SQLite, read only: conversation_id, title)
    Never anything else of those files; nothing is written."""

    TAIL = 262144                              # bytes of a transcript's end looked through for its title

    def __init__(self):
        home = os.path.expanduser("~")
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        roaming = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        # the Store build keeps them under Local\Claude-Data\<app> (Claude-3p: the build for other providers); an
        # install from the website keeps an Electron app's data under Roaming\Claude
        self.desk_roots = [os.path.join(local, d) for d in ("Claude-Data", "Claude-3p", "Claude")] + [os.path.join(roaming, "Claude")]
        if MAC:                                # its data on macOS: ~/Library/Application Support/Claude
            self.desk_roots = [os.path.join(home, "Library", "Application Support", "Claude")]
        self.projects = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude"), "projects")
        self.codex_home = os.environ.get("CODEX_HOME") or os.path.join(home, ".codex")
        self.codex_index = os.path.join(self.codex_home, "session_index.jsonl")
        self.codex_db = None                   # its thread list, once found (state_5.sqlite in Codex 2026-11)
        self.dsh_views = os.path.join((os.environ.get("DSH_HOME") or "").strip() or os.path.join(home, ".dsh"),
                                      "storages", "session_projcache", "sessions")
        self.ag_db = os.path.join(home, ".gemini", "antigravity", "conversation_summaries.db")
        self.where = {}                        # session -> (kind, path) once found
        self.entry = {}                        # session -> Claude Code's entrypoint as its hook said ("at" line):
                                               # "claude-desktop", "cli", ... (the Family's talk_entry: one dict)
        self.ent_memo = {}                     # transcript -> (mtime, the last entrypoint it records)
        self.trans = {}                        # session -> its Claude Code transcript, once found (interrupted)
        self.rolls = {}                        # session -> its Codex rollout, once found (codex_cut)
        self.memo = {}                         # path -> (mtime, {session: title}) for what was read
        self.scanned = -1e9                    # when the desktop app's files were last looked through

    @staticmethod
    def _mtime(path):
        try:
            # a SQLite database in WAL mode takes its writes in <name>-wal first
            return max(os.stat(path).st_mtime_ns, os.stat(path + "-wal").st_mtime_ns if os.path.exists(path + "-wal") else 0)
        except OSError:
            return None

    def _ag_title(self, session):
        """-> (found, title) from Antigravity's conversation list (sqlite3 only loaded for this)."""
        import sqlite3
        db = sqlite3.connect("file:%s?mode=ro" % self.ag_db.replace("\\", "/"), uri=True, timeout=0.5)
        try:
            row = db.execute("select title from conversation_summaries where conversation_id like ? limit 1",
                             (session + "%",)).fetchone()
        finally:
            db.close()
        return (row is not None, row[0] if row and isinstance(row[0], str) else None)

    def ag_root(self, session):
        """Antigravity (2026-11-15: each sub-agent it sends runs as a conversation of its own, with hooks, and took a
        circle of its own): -> "" for a conversation of yours, the 8 characters of its root conversation for a
        sub-agent, None while it cannot be told (its file not written yet).  Told by its own file,
        conversations/<id>.db, table trajectory_metadata_blob: a protobuf whose field 5 is the conversation that
        sent it and 6 the root (on one of yours: no 5, and 6 is itself).  Read only; sqlite3 only loaded for this."""
        import glob, sqlite3
        files = glob.glob(os.path.join(os.path.dirname(self.ag_db), "conversations", session + "*.db"))
        if not files:
            return None
        roots = []
        for f in files[:4]:
            db = sqlite3.connect("file:%s?mode=ro" % f.replace("\\", "/"), uri=True, timeout=0.5)
            try:
                row = db.execute("select data from trajectory_metadata_blob limit 1").fetchone()
            finally:
                db.close()
            if row is None or not isinstance(row[0], bytes):
                return None
            parent, root = proto_strings(row[0], (5, 6))
            roots.append(root[:8] if parent and root and not root.startswith(session) else "")
        return "" if "" in roots else roots[0]

    def codex_threads(self, session):
        """-> [(thread id, source, title)] of the Codex threads whose id ends with these 8 characters (or starts:
        an event line from before 2026-11-14), or None when
        there is no thread list to read.  Source: "vscode" (the desktop app), "cli", ...; a sub-agent's is JSON
        ({"subagent": {"thread_spawn": {"parent_thread_id": ...}}}).  Codex's own background jobs (its memory work)
        run as sessions with hooks but are not threads here.  Read only; sqlite3 only loaded for this."""
        import glob, sqlite3
        if self.codex_db is None or not os.path.isfile(self.codex_db):
            dbs = []
            for f in glob.glob(os.path.join(self.codex_home, "state_*.sqlite")):
                v = os.path.basename(f)[6:-7]
                if v.isdigit():
                    dbs.append((int(v), f))
            if not dbs:
                return None
            self.codex_db = max(dbs)[1]
        db = sqlite3.connect("file:%s?mode=ro" % self.codex_db.replace("\\", "/"), uri=True, timeout=0.5)
        try:
            rows = db.execute("select id, source, title from threads where id like ? limit 8", ("%" + session,)).fetchall()
            if not rows:
                rows = db.execute("select id, source, title from threads where id like ? limit 8", (session + "%",)).fetchall()
        finally:
            db.close()
        return [(r[0] if isinstance(r[0], str) else "", r[1] if isinstance(r[1], str) else "",
                 r[2] if isinstance(r[2], str) else "") for r in rows]

    def _codex_thread(self, session):
        """-> (its thread id, its first message) of the one conversation of these 8 characters, or (None, None)"""
        try:
            rows = self.codex_threads(session) or []
        except Exception:
            return (None, None)
        rows = [r for r in rows if not r[1].startswith("{") and r[2].strip()]
        return (rows[0][0], rows[0][2]) if len(rows) == 1 else (None, None)

    def codex_cut(self, session):
        """Codex (2026-11-14: its stop button sends no Stop hook either): True if the last turn mark in this
        conversation's rollout (its thread's rollout_path in Codex's thread list) is "turn_aborted", False if it is
        "task_started" / "task_complete" (you stopped it and sent another message at once: a new turn is on).  Only the
        last 256 KB, only the lines' kinds.  None: no rollout found, or it cannot tell yet."""
        path = self.rolls.get(session)
        if path is None or not os.path.isfile(path):
            import sqlite3
            if self.codex_threads(session) is None:        # finds its thread list (codex_db)
                return None
            db = sqlite3.connect("file:%s?mode=ro" % self.codex_db.replace("\\", "/"), uri=True, timeout=0.5)
            try:
                row = db.execute("select rollout_path from threads where id like ? and rollout_path != '' limit 1",
                                 ("%" + session,)).fetchone()
            finally:
                db.close()
            path = row[0] if row and isinstance(row[0], str) else None
            if not path or not os.path.isfile(path):
                return None
            if len(self.rolls) >= 64:
                self.rolls.clear()
            self.rolls[session] = path
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 262144))
            tail = f.read().decode("utf-8", "ignore")
        lines = tail.splitlines()
        if size > 262144:
            lines = lines[1:]                  # the first is cut
        for i, line in enumerate(reversed(lines)):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except ValueError:
                if i == 0:
                    return None                # the last one being written: cannot tell yet
                continue
            p = d.get("payload") if isinstance(d, dict) else None
            if d.get("type") == "event_msg" and isinstance(p, dict) and p.get("type") in ("task_started", "task_complete", "turn_aborted"):
                return p["type"] == "turn_aborted"
        return None

    def interrupted(self, session, agent=""):
        """Codex's: codex_cut.  Otherwise Claude Code's.
        True if this Claude Code conversation's transcript ends with your interrupt: its last message (lines that
        are not messages, as titles and settings, are passed over) is the "[Request interrupted by user...]" line
        Claude Code writes the moment you press Esc or the stop button.  Only the last 16 KB, only those lines'
        kinds and that marker are looked at.  None: no transcript (another agent's conversation), or it cannot tell."""
        if agent == "codex":
            return self.codex_cut(session)
        path = self.transcript(session)
        if path is None:
            return None
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 16384))
            tail = f.read().decode("utf-8", "ignore")
        lines = tail.splitlines()
        if size > 16384:
            lines = lines[1:]                  # the first is cut
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except ValueError:
                return None                    # cut or being written: cannot tell yet
            if not isinstance(d, dict) or d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
                continue
            if d.get("type") == "assistant":
                return False
            c = (d.get("message") or {}).get("content")
            texts = [c] if isinstance(c, str) else [x.get("text") for x in c if isinstance(x, dict)] if isinstance(c, list) else []
            return any(isinstance(t, str) and t.startswith("[Request interrupted by user") for t in texts)
        return None

    def transcript(self, session):
        """This Claude Code conversation's transcript (~/.claude/projects/<folder>/<its id>.jsonl; the desktop app's
        conversations have one too), or None"""
        path = self.trans.get(session)
        if path is not None and os.path.isfile(path):
            return path
        try:
            for d in os.listdir(self.projects):
                folder = os.path.join(self.projects, d)
                if os.path.isdir(folder):
                    for f in os.listdir(folder):
                        if f.startswith(session) and f.endswith(".jsonl"):
                            if len(self.trans) >= 64:
                                self.trans.clear()
                            self.trans[session] = os.path.join(folder, f)
                            return self.trans[session]
        except OSError:
            pass
        return None

    def claude_kind(self, session):
        """"desk" (in Claude's desktop app: a click opens its link there) or "cli" (in a terminal: its window, its
        Windows Terminal tab) for a Claude Code conversation; None for another agent's, or one that does not say.
        Told, not guessed (2026-11-15): what its hook said (CLAUDE_CODE_ENTRYPOINT, on its "at" line), or else the last
        "entrypoint" its transcript records ("claude-desktop" / "cli" on every message).  A conversation resumed in the
        other one moves with it (a desktop one resumed in a terminal: its last lines say "cli")."""
        e = self.entry.get(session)
        if not e:
            path = self.transcript(session)
            if path is None:
                return None
            mt = self._mtime(path)
            memo = self.ent_memo.get(path)
            if memo is not None and memo[0] == mt:
                e = memo[1]
            else:
                size = os.path.getsize(path)
                with open(path, "rb") as f:
                    f.seek(max(0, size - 65536))
                    found = re.findall(rb'"entrypoint"\s*:\s*"([a-z0-9_-]{1,24})"', f.read())
                e = found[-1].decode("ascii") if found else ""
                if len(self.ent_memo) >= 64:
                    self.ent_memo.clear()
                self.ent_memo[path] = (mt, e)
        if not e:
            return None
        return "desk" if e == "claude-desktop" else "cli"

    def _desk_files(self):
        """<root>[/<app>]/claude-code-sessions/<account>/<org>/local_*.json, newest first"""
        import glob
        out = []
        for root in self.desk_roots:
            for pat in ("claude-code-sessions", os.path.join("*", "claude-code-sessions")):
                out += glob.glob(os.path.join(root, pat, "*", "*", "local_*.json"))
        return sorted(out, key=lambda f: self._mtime(f) or 0, reverse=True)

    def _find(self, session, now, force=False):
        """force: look through the desktop app's sessions now (a click).  A desktop conversation has a transcript
        under ~/.claude/projects too, so "cli" is kept only when the desktop's files were looked through this time
        (2026-11-14: the mouse on one circle, then within 10 s on another desktop one: that one was taken for a
        terminal's for good, and a click on it only brought the window, never its link)."""
        kind = self.claude_kind(session)       # a Claude Code conversation's: told by its hook or its transcript
        hit = self.where.get(session)
        if hit is not None and (kind is None or hit[0] not in ("desk", "cli") or hit[0] == kind):
            return hit
        if kind == "cli":
            path = self.transcript(session)
            if path:
                self.where[session] = ("cli", path)
                return self.where[session]
        key = ('"cliSessionId": "%s' % session).encode("ascii")
        key2 = ('"cliSessionId":"%s' % session).encode("ascii")
        scanned = force or kind == "desk" or now - self.scanned > 10.0
        if scanned:                            # the desktop app's sessions: once in a while, not on every hover
            self.scanned = now
            for path in self._desk_files():
                try:
                    with open(path, "rb") as f:
                        head = f.read(4096)
                except OSError:
                    continue
                if key in head or key2 in head:
                    self.where[session] = ("desk", path)
                    return self.where[session]
        try:
            for d in os.listdir(self.projects):
                folder = os.path.join(self.projects, d)
                if os.path.isdir(folder):
                    for f in os.listdir(folder):
                        if f.startswith(session) and f.endswith(".jsonl"):
                            hit = ("cli", os.path.join(folder, f))
                            if scanned and kind != "desk":     # not one of the desktop app's: a terminal's for good
                                self.where[session] = hit
                            return hit
        except OSError:
            pass
        try:
            for f in os.listdir(self.dsh_views):
                if f.startswith("session-" + session) and f.endswith(".json"):
                    self.where[session] = ("dsh", os.path.join(self.dsh_views, f))
                    return self.where[session]
        except OSError:
            pass
        if os.path.isfile(self.ag_db):
            try:
                if self._ag_title(session)[0]:
                    self.where[session] = ("ag", self.ag_db)
                    return self.where[session]
            except Exception:
                log_exc("Antigravity's conversation list")
        if os.path.isfile(self.codex_index):
            return ("codex", self.codex_index)            # not kept: a thread is named there a while after it starts
        return None

    def _read(self, kind, path, session):
        if kind == "desk":
            with open(path, "rb") as f:
                d = json.loads(f.read().decode("utf-8"))
            t = d.get("title")
            return t if isinstance(t, str) else None
        if kind == "ag":
            return self._ag_title(session)[1]
        if kind == "dsh":
            with open(path, "rb") as f:
                d = json.loads(f.read().decode("utf-8"))
            t = (((d.get("record") or {}).get("rows") or {}).get("title") or {}).get("val")
            return t if isinstance(t, str) else None
        if kind == "cli":
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                f.seek(max(0, size - self.TAIL))
                tail = f.read().decode("utf-8", "ignore")
            for want in ('"custom-title"', '"ai-title"'):
                for line in reversed(tail.splitlines()):
                    if want in line[:40]:
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        t = d.get("customTitle") or d.get("aiTitle") or d.get("title")
                        if isinstance(t, str) and t:
                            return t
            return None
        found = None
        with open(path, "rb") as f:
            for line in f.read().decode("utf-8", "ignore").splitlines():
                if ('"%s' % session) in line[:20] or ('%s"' % session) in line[:60]:   # its id's start or end
                    try:
                        t = json.loads(line).get("thread_name")
                    except ValueError:
                        continue
                    found = t if isinstance(t, str) and t else found
        # not named yet (Codex names a thread a while after it starts): its first message
        return found or self._codex_thread(session)[1]

    def open_now(self, session):
        """True if the Claude desktop app has this conversation open already: of its sessions' files, this one's
        "lastFocusedAt" is the latest (the app writes it when you go to one).  Read from the start of each file only.
        A side question (/btw: "btwLoweredFrom", "forkedFromSessionId") sits beside the conversation it came from, so
        the one in view is that conversation (else a click after a /btw opened the link and the app came up twice)."""
        best = (-1, None, None)
        key = re.compile(rb'"lastFocusedAt"\s*:\s*(\d+)')
        cid = re.compile(rb'"cliSessionId"\s*:\s*"([0-9a-f-]{8})')
        for path in self._desk_files()[:200]:
            try:
                with open(path, "rb") as f:
                    head = f.read(4096)
            except OSError:
                continue
            a, b = key.search(head), cid.search(head)
            if a and b and int(a.group(1)) > best[0]:
                best = (int(a.group(1)), b.group(1).decode("ascii"), path)
        if best[2] is None:
            return False
        try:
            with open(best[2], "rb") as f:
                d = json.loads(f.read().decode("utf-8"))
            parent = d.get("forkedFromSessionId")
            if "btwLoweredFrom" in d and isinstance(parent, str) and all(c.isalnum() or c in "-_" for c in parent):
                with open(os.path.join(os.path.dirname(best[2]), parent + ".json"), "rb") as f:
                    main = json.loads(f.read().decode("utf-8")).get("cliSessionId") or ""
                return main[:8] == session
        except (OSError, ValueError):
            pass
        return best[1] == session

    def link(self, session, agent, now):
        """-> a link that opens this very conversation in its agent's desktop app, or None (a terminal: the window
        is all there is).  Claude desktop app: claude://code/continue?session=<its local_ id> (reported to switch to an
        open session from Desktop 2.37337.1 on, anthropics/claude-code#90035); Codex: codex://threads/<thread id>.
        DeepSeek Harness has no link to one conversation (0.2.1): dsh://open only shows its window, which is what a
        window closed to its tray needs; Antigravity (2.31) likewise, antigravity://open.  Such a conversation is known
        by its agent ("at" line) or else by where its name is kept (AGENT_INFO "open")."""
        one = AGENT_INFO.get(agent, {}).get("open")
        if one:
            return one
        try:
            hit = self._find(session, now, force=True)
            one = AGENT_INFO.get(KIND_AGENT.get(hit[0] if hit else ""), {}).get("open")
            if one:
                return one
            if hit and hit[0] == "desk":
                with open(hit[1], "rb") as f:
                    sid = json.loads(f.read().decode("utf-8")).get("sessionId")
                if isinstance(sid, str) and sid.startswith("local_") and all(c.isalnum() or c in "-_" for c in sid):
                    return "claude://code/continue?session=" + sid
            if agent == "codex" and hit and hit[0] == "codex":
                with open(hit[1], "rb") as f:
                    for line in f.read().decode("utf-8", "ignore").splitlines():
                        if ('"%s' % session) in line[:20] or ('%s"' % session) in line[:60]:
                            tid = json.loads(line).get("id")
                            if isinstance(tid, str) and all(c.isalnum() or c == "-" for c in tid):
                                return "codex://threads/" + tid
                tid = self._codex_thread(session)[0]   # not in the name index yet
                if tid and all(c.isalnum() or c == "-" for c in tid):
                    return "codex://threads/" + tid
        except Exception:
            log_exc("a conversation's link")
        return None

    def title(self, session, now):
        """-> its name or None; read again only when its file changed since."""
        try:
            hit = self._find(session, now)
            if hit is None:
                return None
            kind, path = hit
            mt = self._mtime(path)
            memo = self.memo.get(path)
            if memo is not None and memo[0] == mt and session in memo[1]:
                return memo[1][session]
            t = self._read(kind, path, session)
            if t:
                t = " ".join(t.split())[:40]
            if memo is None or memo[0] != mt:
                memo = (mt, {})
                self.memo[path] = memo
            memo[1][session] = t
            return t
        except Exception:
            log_exc("a conversation's name")
            return None


class ItemOverlay(object):
    """A find at a pet's arm tip: the treasure's icon in a small window in front of the pet, its glow in another
    behind it (the rarity's colour).  Both follow the arm frame by frame (the clip's "item" list in the
    manifest) and play the treasure's own little loop.  Clicks go through them.  Never a reason to stop."""

    def __init__(self, pet):
        self.pet = pet
        self.parts = {}            # "item" / "aura" -> {hwnd, memdc, hbmp, bits, side, stock, shown, key}
        self.broken = False
        self.ticks = 0

    def _part(self, kind, side):
        part = self.parts.get(kind)
        if part is None:
            ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT
            hwnd = CreateWindowExW(ex, CLASS_NAME, ITEM_TITLE, WS_POPUP, 0, 0, 1, 1, None, None, self.pet.family.hinst, None)
            memdc = CreateCompatibleDC(None)
            if not hwnd or not memdc:
                raise ctypes.WinError(ctypes.get_last_error())
            part = self.parts[kind] = {"hwnd": hwnd, "memdc": memdc, "hbmp": None, "bits": None, "side": 0, "stock": None,
                                       "shown": False, "key": None}
        if part["side"] != side:
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = side
            bmi.bmiHeader.biHeight = -side
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB
            bits = LPVOID()
            hbmp = CreateDIBSection(part["memdc"], ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
            if not hbmp or not bits.value:
                raise ctypes.WinError(ctypes.get_last_error())
            GdiFlush()
            old = SelectObject(part["memdc"], hbmp)
            if part["stock"] is None:
                part["stock"] = old
            if part["hbmp"]:
                DeleteObject(part["hbmp"])
            part.update(hbmp=hbmp, bits=bits.value, side=side, key=None)
        return part

    def _put(self, kind, name, frame, cx, cy, alpha):
        got = self.pet.store.item_frames(kind, name)
        if got is None or alpha <= 0:
            self._hide(kind)
            return
        blobs, src = got
        disp = self.pet.disp                   # a frame set drawn bigger or smaller (until its own size is rendered): so is the find
        side = src if disp == 1.0 else max(2, int(round(src * disp)))
        part = self._part(kind, side)
        key = (name, frame % len(blobs), id(self.pet.store), side)
        if key != part["key"]:
            data = zlib.decompress(blobs[key[1]], 15, src * src * 4)
            if len(data) != src * src * 4:
                raise ValueError("treasure frame of %d bytes, expected %d" % (len(data), src * src * 4))
            GdiFlush()
            if side == src:
                ctypes.memmove(part["bits"], data, len(data))
            else:
                cfg = (src, side, part["bits"])
                if part.get("scaler") is None:
                    part["scaler"] = Scaler()
                if part.get("cfg") != cfg:
                    part["scaler"].configure(src, src, part["bits"], side, side, (0.0, 0.0, float(src), float(src)))
                    part["cfg"] = cfg
                part["scaler"].draw(data)
            part["key"] = key
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, int(clamp(alpha, 0, 255)), AC_SRC_ALPHA)
        pos = POINT(int(round(cx - side / 2.0)), int(round(cy - side / 2.0)))
        UpdateLayeredWindow(part["hwnd"], None, ctypes.byref(pos), ctypes.byref(SIZE(side, side)), part["memdc"],
                            ctypes.byref(POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
        fresh = not part["shown"]
        if fresh:
            ShowWindow(part["hwnd"], SW_SHOWNOACTIVATE)
            part["shown"] = True
        if kind == "item":
            if fresh:
                SetWindowPos(part["hwnd"], HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        elif fresh or self.ticks % 8 == 0:     # the glow goes right behind its pet (the pets change places now and then)
            SetWindowPos(part["hwnd"], self.pet.hwnd, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _hide(self, kind):
        part = self.parts.get(kind)
        if part is not None and part["shown"]:
            ShowWindow(part["hwnd"], SW_HIDE)
            part["shown"] = False

    def show(self, now, it, entry):
        """it: the pet's find {"name", "rarity", "t0"}; entry: [x, y, size / 1000] in the frame set's canvas px."""
        if self.broken:
            return
        try:
            pet = self.pet
            st = pet.store
            if st.items is None:
                self.hide()
                return
            self.ticks += 1
            x, y, size = entry
            cx, cy = pet.win_pos[0] + x * pet.disp, pet.win_pos[1] + y * pet.disp
            frame = int((now - it["t0"]) * float(st.items.get("fps") or 12))
            self._put("aura", it["rarity"], frame, cx, cy, 255 * clamp((size - 700) / 300.0, 0.0, 1.0))
            self._put("item", it["name"], frame, cx, cy, 255 * clamp(size / 600.0, 0.0, 1.0))
        except Exception:
            log_exc("treasure overlay; no more of them")
            self.broken = True
            self.destroy()

    def hide(self):
        for kind in list(self.parts):
            self._hide(kind)

    def destroy(self):
        for part in self.parts.values():
            try:
                if part.get("scaler") is not None:
                    part["scaler"].shutdown()
                if part["hwnd"]:
                    DestroyWindow(part["hwnd"])
                if part["memdc"]:
                    if part["stock"]:
                        SelectObject(part["memdc"], part["stock"])
                    DeleteDC(part["memdc"])
                if part["hbmp"]:
                    DeleteObject(part["hbmp"])
            except Exception:
                log_exc("treasure overlay cleanup")
        self.parts = {}


# --------------------------------------------------------------------------- start with Windows
AUTOSTART_WORDS = "open at login" if MAC else "start with Windows"      # (the log's)


def autostart_label():
    """The tray menu's item, in the system's own words."""
    return tr("登录时打开", "Open at Login") if MAC else tr("开机自启", "Start with Windows")


def autostart_command():
    """pythonw and the player in the home folder (a trial copy started with --home registers the real one).  On
    macOS the LaunchAgent's arguments (a list): clawd_mac.system.pet_command, as clawd.py's (RedCrab.app: its own
    launcher)."""
    exe = sys.executable or "pythonw.exe"
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(w):
        exe = w
    script = os.path.join(HOME_DIR, "clawd_pet.pyw")
    if not os.path.exists(script):
        script = os.path.abspath(__file__)
    if MAC:
        return macsys.pet_command(script, os.path.abspath(sys.executable or "/usr/bin/python3"))
    return '"%s" "%s"' % (exe, script)


def set_autostart_mac(on):
    """set_autostart on macOS: our LaunchAgent (clawd_mac.system), from the next login on, as the Run key.  Never
    pointing into App Translocation (where Gatekeeper runs an app not yet moved out of Downloads: gone next time)."""
    cmd = autostart_command()
    if on and macsys.in_translocation(cmd[-1]):
        log("open at login: not set, RedCrab.app runs from App Translocation (move it to Applications first)")
        return
    if not macsys.set_autostart(on, cmd):
        log("open at login -> %s: %s not written" % (on, macsys.launch_agent_path()))


def refresh_hooks():
    """An installed copy whose hooks are another copy's (the program moved, a newer kind of hook) writes them again
    for itself (clawd hooks refresh: only agents with ours, backed up first), in the background; what it did goes
    to the log.  Never from a development checkout (.git beside the program): one of those would take the hooks of
    the copy that is played with."""
    if os.path.exists(os.path.join(HERE, ".git")):
        return
    import subprocess
    import threading
    exe = os.path.join(os.path.dirname(sys.executable), "python.exe")

    def go():
        try:
            r = subprocess.run([exe if os.path.isfile(exe) else sys.executable, "-I", os.path.join(HERE, "clawd.py"),
                                "hooks", "refresh"], stdin=subprocess.DEVNULL, capture_output=True, timeout=60,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"), **child_kw(CREATE_NO_WINDOW))
            log("hooks refresh: %s" % r.stdout.decode("utf-8", "replace").strip().replace("\n", " | "))
        except Exception:
            log_exc("hooks refresh")
    threading.Thread(target=go, daemon=True).start()


def autostart_enabled():
    """Registered in HKCU Run and not switched off in Task Manager (StartupApproved: an odd first byte); on macOS:
    our LaunchAgent is there."""
    if MAC:
        return macsys.autostart_enabled()
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
    except OSError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as k:
            v, _ = winreg.QueryValueEx(k, AUTOSTART_NAME)
        if isinstance(v, bytes) and v and v[0] & 1:
            return False
    except OSError:
        pass
    return True


def set_autostart(on):
    """On: our Run value (and Task Manager's 'disabled' mark gone); off: both removed, nothing left behind."""
    if MAC:
        set_autostart_mac(on)
        return
    import winreg
    try:
        if on:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, AUTOSTART_NAME)
        except FileNotFoundError:
            pass
    except OSError:
        log_exc("%s -> %s" % (AUTOSTART_WORDS, on))


# --------------------------------------------------------------------------- tray
class Tray(object):
    """The family's icon in the notification area, on a hidden window of its own.  A click hides or shows the
    family; its menu has hide/show, back to the corner and quit.  Added again when Explorer restarts
    (TaskbarCreated).  The icon is the idle frame, scaled down once; dimmed while the family is hidden."""

    ID = 1

    def __init__(self, family, store):
        self.family = family
        self.hwnd = None
        self.added = False
        self.icons = {}                        # hidden? -> HICON
        self.last_click = -1e9
        self.taskbar_created = RegisterWindowMessageW("TaskbarCreated") or None
        try:
            self._make_icons(store)
        except Exception:
            log_exc("tray icon picture")
        self.hwnd = CreateWindowExW(WS_EX_TOOLWINDOW, CLASS_NAME, TRAY_TITLE, WS_POPUP, 0, 0, 0, 0,
                                    None, None, family.hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.add()
        if not family.opts["home"] and autostart_enabled():
            self._refresh_autostart()

    @staticmethod
    def _refresh_autostart():
        """The folder or Python moved: point the startup entry at where it runs now."""
        if MAC:
            if macsys.autostart_command() != autostart_command():
                set_autostart(True)            # (not into App Translocation: set_autostart_mac says why)
                if macsys.autostart_command() == autostart_command():
                    log("open at login: entry updated to %s" % " ".join(autostart_command()))
            return
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
                old, _ = winreg.QueryValueEx(k, AUTOSTART_NAME)
            if old != autostart_command():
                set_autostart(True)
                log("start with Windows: entry updated to %s" % autostart_command())
        except OSError:
            pass

    def _make_icons(self, store):
        """Idle frame 0, its body in a square, box-filtered down to the small icon size."""
        s = GetSystemMetrics(SM_CXSMICON) or 16
        raw = zlib.decompress(store.frames(store.idle_name)[0])
        w, h = store.width, store.height
        l, t, r, b = store.bbox
        side = max(r - l + 1, b - t + 1) * 1.04
        x0, y0 = (l + r + 1 - side) / 2.0, (t + b + 1 - side) / 2.0
        k = side / s
        px = bytearray(s * s * 4)
        for j in range(s):
            ya, yb = int(y0 + j * k), int(y0 + (j + 1) * k)
            ys = range(max(ya, 0), min(max(yb, ya + 1), h))
            for i in range(s):
                xa, xb = int(x0 + i * k), int(x0 + (i + 1) * k)
                xs = range(max(xa, 0), min(max(xb, xa + 1), w))
                n = max(1, (max(yb, ya + 1) - ya) * (max(xb, xa + 1) - xa))
                cb = cg = cr = ca = 0
                for y in ys:
                    row = y * w * 4
                    for x in xs:
                        o = row + x * 4
                        cb += raw[o]
                        cg += raw[o + 1]
                        cr += raw[o + 2]
                        ca += raw[o + 3]
                if ca:                         # the frames are premultiplied, an icon is not
                    o = (j * s + i) * 4
                    px[o] = min(255, int(cb * 255.0 / ca + 0.5))
                    px[o + 1] = min(255, int(cg * 255.0 / ca + 0.5))
                    px[o + 2] = min(255, int(cr * 255.0 / ca + 0.5))
                    px[o + 3] = min(255, int(ca / float(n) + 0.5))
        dim = bytearray(px)
        dim[3::4] = bytes(int(a * 0.4) for a in px[3::4])
        self.icons[False] = self._icon(bytes(px), s)
        self.icons[True] = self._icon(bytes(dim), s)

    @staticmethod
    def _icon(px, s):
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = s
        bmi.bmiHeader.biHeight = -s
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bits = LPVOID()
        color = CreateDIBSection(None, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not color or not bits.value:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(bits.value, px, len(px))
        zeros = ctypes.create_string_buffer(((s + 15) // 16) * 2 * s)
        mask = CreateBitmap(s, s, 1, 1, zeros)
        try:
            icon = CreateIconIndirect(ctypes.byref(ICONINFO(True, 0, 0, mask, color)))
        finally:
            DeleteObject(color)
            if mask:
                DeleteObject(mask)
        if not icon:
            raise ctypes.WinError(ctypes.get_last_error())
        return icon

    def _tip(self):
        level = self.family.grow.level
        gift = next_gift(level)
        lv = " Lv.%d" % level + (tr(" · 下一份礼物 Lv.%d %s" % (gift[0], gift[2][0]), " · next gift at Lv.%d: %s" % (gift[0], gift[2][1]))
                                 if gift else tr(" · 满级", " · top level"))
        if MAC:                                # a click on the menu-bar icon opens its menu: nothing to say of clicks
            tip = tr("Clawd%s（已隐藏）" % lv, "Clawd%s (hidden)" % lv) if self.family.hidden else "Clawd%s" % lv
        else:
            tip = (tr("Clawd%s（已隐藏，点一下显示）" % lv, "Clawd%s (hidden, click to show)" % lv) if self.family.hidden
                   else tr("Clawd%s（点一下隐藏）" % lv, "Clawd%s (click to hide)" % lv))
        if self.family.opts["home"]:
            tip += " [test]"
        return tip

    def _nid(self, flags):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = self.ID
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.icons.get(bool(self.family.hidden)) or self.icons.get(False) or LoadIconW(None, IDI_APPLICATION)
        nid.szTip = self._tip()
        return nid

    def add(self):
        nid = self._nid(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        self.added = bool(Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
        if not self.added and Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid)):
            self.added = True                  # it was still there (TaskbarCreated without a restart)
        if not self.added:
            log("tray icon not added; again when the taskbar comes")
        elif self.family.opts["debug"]:
            log("tray icon added")
        return self.added

    def update(self):
        """The icon and its tip follow hidden/shown and the language."""
        if not self.hwnd:
            return
        if not self.added or not Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid(NIF_ICON | NIF_TIP))):
            self.add()

    def handle(self, msg, wparam, lparam):
        if msg == WM_TRAY:
            ev = lparam & 0xFFFF
            if ev == WM_LBUTTONUP:
                now = time.perf_counter()
                if now - self.last_click > GetDoubleClickTime() / 1000.0:   # a double click is one click
                    self.last_click = now
                    self.family.set_hidden(not self.family.hidden, now, "tray click")
            elif ev == WM_RBUTTONUP:
                self._menu()
            return 0
        if self.taskbar_created and msg == self.taskbar_created:
            self.added = False                 # Explorer restarted: the old icon is gone
            self.add()
            return 0
        if msg == WM_CLOSE:
            self.family.quit("WM_CLOSE (tray)")
            return 0
        return None

    def _menu(self):
        family = self.family
        menu = CreatePopupMenu()
        if not menu:
            log("CreatePopupMenu failed, error %d" % ctypes.get_last_error())
            return
        cmd = 0
        try:
            AppendMenuW(menu, MF_STRING, ID_HIDE, tr("显示", "Show") if family.hidden else tr("隐藏", "Hide"))
            AppendMenuW(menu, MF_STRING, ID_RESET, tr("回到右下角", "Back to the corner"))
            AppendMenuW(menu, MF_STRING, ID_ALBUM, self.family.album_label())
            activity = family.activity_menu()
            if activity:
                AppendMenuW(menu, MF_POPUP, activity, tr("活跃度", "Activity"))
            AppendMenuW(menu, MF_STRING, ID_CONNECT, tr("连接 AI…", "Connect AI…"))
            AppendMenuW(menu, MF_STRING | (MF_CHECKED if autostart_enabled() else 0), ID_AUTOSTART,
                        autostart_label())
            AppendMenuW(menu, MF_STRING, ID_RELEASES, tr("去看看新版本", "Check for a new version"))
            AppendMenuW(menu, MF_SEPARATOR, 0, None)
            AppendMenuW(menu, MF_STRING, ID_QUIT, tr("退出", "Quit"))
            pt = POINT()
            GetCursorPos(ctypes.byref(pt))
            SetForegroundWindow(self.hwnd)     # documented quirk: else the menu never closes
            family.menu_open = True
            cmd = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY, pt.x, pt.y, 0, self.hwnd, None)
            PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            family.menu_open = False
            DestroyMenu(menu)
        now = time.perf_counter()
        if cmd == ID_HIDE:
            family.set_hidden(not family.hidden, now, "tray menu")
        elif cmd == ID_RESET:
            family.set_hidden(False, now, "back to the corner")
            family.reset()
        elif cmd == ID_ALBUM:
            family.open_album("tray menu")
        elif cmd == ID_CONNECT:
            family.open_connect("tray menu")
        elif ID_ACTIVITY_BASE <= cmd < ID_ACTIVITY_BASE + len(ACTIVITIES):
            family.set_activity(ACTIVITIES[cmd - ID_ACTIVITY_BASE][0], now, "tray menu")
        elif cmd == ID_AUTOSTART:
            on = not autostart_enabled()
            set_autostart(on)
            log("%s: %s" % (AUTOSTART_WORDS, "on" if autostart_enabled() else "off"))
        elif cmd == ID_RELEASES:
            open_page(RELEASES_URL)
        elif cmd == ID_QUIT:
            family.quit("menu (tray)")

    def destroy(self):
        try:
            if self.added and self.hwnd:
                Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid(0)))
            self.added = False
            if self.hwnd:
                DestroyWindow(self.hwnd)
            for icon in self.icons.values():
                DestroyIcon(icon)
        except Exception:
            log_exc("tray cleanup")
        self.hwnd = None
        self.icons = {}


def open_page(url):
    """The default browser at this page, in the background (it can take a moment to start)."""
    import threading

    def go():
        try:
            open_url(url)
            log("opened %s" % url)
        except OSError as e:
            log("%s did not open (%s)" % (url, e))
    threading.Thread(target=go, daemon=True).start()


# --------------------------------------------------------------------------- frames
def opaque_bbox(raw, w, h):
    """(left, top, right, bottom) inclusive bbox of pixels with alpha > 0, or None."""
    alpha = raw[3::4]
    top = bottom = None
    left, right = w, -1
    for y in range(h):
        row = alpha[y * w:(y + 1) * w]
        rs = row.rstrip(b"\x00")
        if not rs:
            continue
        ls = len(row) - len(row.lstrip(b"\x00"))
        left = min(left, ls)
        right = max(right, len(rs) - 1)
        if top is None:
            top = y
        bottom = y
    if top is None:
        return None
    return left, top, right, bottom


def alpha_centroid(raw, w, h):
    """Alpha-weighted centre of a frame, in pixel-edge coordinates; (w/2, h/2) if empty."""
    alpha = raw[3::4]
    total = sum(alpha)
    if not total:
        return w / 2.0, h / 2.0
    return (sum((x + 0.5) * sum(alpha[x::w]) for x in range(w)) / total,
            sum((y + 0.5) * sum(alpha[y * w:(y + 1) * w]) for y in range(h)) / total)


class FrameStore(object):
    """manifest (v1 or v2) + lazily loaded, zlib-compressed frames, LRU capped."""

    # feet point minus idle-frame-0 centroid, per body px, of the base set (see align_to_base)
    feet_per_px = None

    def __init__(self, frames_dir):
        self.dir = os.path.abspath(frames_dir)
        mpath = os.path.join(self.dir, "manifest.json")
        st = os.stat(mpath)
        with open(mpath, "rb") as f:
            m = json.loads(f.read().decode("utf-8-sig"))
        self.sig = (st.st_mtime_ns, st.st_size)
        self.version = int(m.get("version") or 1)
        self.width = int(m["width"])
        self.height = int(m["height"])
        if not (0 < self.width <= 4096 and 0 < self.height <= 4096):
            raise ValueError("bad canvas size %dx%d" % (self.width, self.height))
        self.fps = clamp(float(m.get("fps") or 20), 1.0, 60.0)
        self.frame_bytes = self.width * self.height * 4
        try:
            self.body_px = int(m.get("base_body_px") or DEFAULT_BODY_PX)
        except (TypeError, ValueError):
            self.body_px = DEFAULT_BODY_PX
        if self.body_px <= 0:
            self.body_px = DEFAULT_BODY_PX
        a = m.get("anchor")
        self.anchor = None
        if isinstance(a, dict) and "feet_x" in a and "feet_y" in a:
            self.anchor = (float(a["feet_x"]), float(a["feet_y"]))
        self.meta = {}
        for name, info in (m.get("actions") or {}).items():
            if isinstance(info, dict) and info.get("file"):
                self.meta[str(name)] = info
        names = list(self.meta)
        self.idle_name = IDLE_NAME if IDLE_NAME in self.meta else (names[0] if names else None)
        self._frames = {}      # name -> [bytes, ...]; dict order = LRU order
        self._sizes = {}
        self._bytes = 0
        self._bad = {}         # name -> monotonic time when a retry is allowed
        self.bbox = None
        it = m.get("items")    # the treasures' icons and glows at this set's size (prerender.py), or none
        self.items = it if (isinstance(it, dict) and isinstance(it.get("names"), dict) and isinstance(it.get("auras"), dict)
                            and isinstance(it.get("box"), int) and it["box"] > 0) else None
        self._item_blobs = {}

    def prepare(self):
        """Load idle, check frame 0, compute the body bbox and the feet anchor."""
        fr = self.frames(self.idle_name) if self.idle_name else None
        if not fr:
            raise RuntimeError("no usable idle frames in %s" % self.dir)
        raw0 = zlib.decompress(fr[0])
        if len(raw0) != self.frame_bytes:
            raise ValueError("idle frame 0 has %d bytes, expected %d" % (len(raw0), self.frame_bytes))
        self.bbox = opaque_bbox(raw0, self.width, self.height) or (0, 0, self.width - 1, self.height - 1)
        if self.anchor is None:
            l, t, r, b = self.bbox
            self.anchor = ((l + r + 1) / 2.0, b + 1.0)
        self.centroid = alpha_centroid(raw0, self.width, self.height)
        if FrameStore.feet_per_px is not None:
            kx, ky = FrameStore.feet_per_px
            self.anchor = (self.centroid[0] + kx * self.body_px, self.centroid[1] + ky * self.body_px)
        return self

    def align_to_base(self):
        """Call on the prepared base set: from now on every set's anchor is derived from its own
        idle centroid and the base set's feet offset, which leaves the base set's anchor as it is.
        Manifest anchors are rounded, and so is the renderer's sprite placement."""
        FrameStore.feet_per_px = ((self.anchor[0] - self.centroid[0]) / self.body_px,
                                  (self.anchor[1] - self.centroid[1]) / self.body_px)

    def names(self):
        return [n for n in self.meta if self.usable(n)]

    def usable(self, name):
        if name not in self.meta:
            return False
        t = self._bad.get(name)
        return t is None or time.monotonic() >= t

    def mark_bad(self, name):
        self._bad[name] = float("inf")
        self._drop(name)

    def _drop(self, name):
        if self._frames.pop(name, None) is not None:
            self._bytes -= self._sizes.pop(name, 0)

    def label(self, name):
        lab = self.meta.get(name, {}).get("label")
        return str(lab) if lab else DEFAULT_LABELS.get(name, name)

    def loops(self, name):
        return bool(self.meta.get(name, {}).get("loop"))

    def fps_of(self, name):
        try:
            return clamp(float(self.meta.get(name, {}).get("fps") or self.fps), 1.0, 60.0)
        except (TypeError, ValueError):
            return self.fps

    def loaded_bytes(self):
        return self._bytes

    def frames(self, name):
        fr = self._frames.get(name)
        if fr is not None:
            if next(reversed(self._frames)) != name:          # LRU touch
                self._frames[name] = self._frames.pop(name)
            return fr
        if not self.usable(name):
            return None
        try:
            fr = self._load(name)
        except OSError as e:      # e.g. the directory is being swapped: retry later
            log("loading frames of %r failed (%s); retry later" % (name, e))
            self._bad[name] = time.monotonic() + 10.0
            return None
        except Exception:
            log_exc("loading frames of %r" % name)
            fr = None
        if not fr:
            self._bad[name] = time.monotonic() + 30.0
            return None
        self._bad.pop(name, None)
        size = len(fr[0].obj)
        self._frames[name] = fr
        self._sizes[name] = size
        self._bytes += size
        self._evict(name)
        return fr

    def item_frames(self, kind, name):
        """-> (the loop's frames as zlib blobs, their side in px) of a treasure (kind "item") or a glow ("aura"), or None."""
        key = (kind, name)
        if key in self._item_blobs:
            return self._item_blobs[key]
        out = None
        try:
            if kind == "item":
                info, side = self.items["names"][name], self.items["box"]
            else:
                info, side = self.items["auras"][name], int(self.items["auras"][name]["size"])
            with open(os.path.join(self.dir, str(info["file"])), "rb") as f:
                data = f.read()
            blobs, off = [], 0
            while off + 4 <= len(data):
                (length,) = struct.unpack_from("<I", data, off)
                off += 4
                if length == 0 or off + length > len(data):
                    break
                blobs.append(data[off:off + length])
                off += length
            if blobs and side > 0:
                out = (blobs, side)
        except Exception:
            log_exc("treasure frames %s %s" % (kind, name))
        self._item_blobs[key] = out
        return out

    def _evict(self, keep):
        while self._bytes > CACHE_BUDGET and len(self._frames) > 2:
            victim = None
            for n in self._frames:                     # least recently used first
                if n != keep and n != self.idle_name:
                    victim = n
                    break
            if victim is None:
                break
            self._drop(victim)

    def _load(self, name):
        info = self.meta[name]
        path = os.path.join(self.dir, str(info["file"]))
        with open(path, "rb") as f:
            data = f.read()
        out = []
        intern = {}            # identical frames of this action share one view object
        view = memoryview(data)    # one block per action, freed whole: no heap fragmentation
        off, n = 0, len(data)
        while off + 4 <= n:
            (length,) = struct.unpack_from("<I", data, off)
            off += 4
            if length == 0 or off + length > n:
                log("frames %s: truncated record at byte %d" % (path, off - 4))
                break
            blob = view[off:off + length]
            off += length
            out.append(intern.setdefault(blob, blob))
        want = info.get("count")
        if isinstance(want, int) and want != len(out):
            log("frames %s: manifest count %s, file has %d" % (path, want, len(out)))
        return out


def try_store(frames_dir):
    try:
        return FrameStore(frames_dir).prepare()
    except Exception as e:
        log("frame set %s unusable: %s" % (frames_dir, e))
        return None


# --------------------------------------------------------------------------- event channel
_JUNK = " \t\r\n\v\f\"'`\ufeff"


def parse_token(line):
    """One event line (bytes, any of UTF-8 / UTF-8 BOM / UTF-16 LE/BE) -> (token, session, more) or None.

    The session is the start of the agent's session id, "" if the line has none or it is malformed.  more: up to
    four words after it (the "at" line: the conversation's window, which agent, Claude Code's entrypoint and the
    Windows Terminal tab; "word session" is all the others are)."""
    if not line:
        return None
    if b"\x00" in line:                       # UTF-16: tokens are ASCII, drop the zero bytes
        line = line.replace(b"\x00", b"")
    line = line.replace(b"\xef\xbb\xbf", b"").replace(b"\xff\xfe", b"").replace(b"\xfe\xff", b"")
    words = line.decode("utf-8", "ignore").strip(_JUNK).split()
    if not words:
        return None
    tok = words[0].strip(_JUNK).lower().replace("-", "_")
    if not tok:
        return None
    sid = words[1].lower() if len(words) > 1 else ""
    return tok, (sid if len(sid) == 8 and all(c in "0123456789abcdef-" for c in sid) else ""), tuple(words[2:6])


class EventChannel(object):
    """Append-only token file read from a remembered offset.

    * size < offset            -> the file was truncated: start again at 0
    * bytes before the offset changed (an old style ">" writer rewrote it) -> start at 0
    * a line without newline is taken after EVENT_PARTIAL_WAIT
    * > EVENT_TRUNC_SIZE, fully read and unchanged for EVENT_TRUNC_IDLE -> truncated by us
    * on startup everything is skipped unless written < EVENT_STALE ago (then the last line)"""

    TAIL = 16

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.tail = b""
        self.sig = None
        self.partial_since = None
        self.changed_at = time.perf_counter()

    def _stat(self):
        try:
            return os.stat(self.path)
        except OSError:
            return None

    def prime(self):
        st = self._stat()
        if st is None:
            return None
        self.sig = (st.st_size, st.st_mtime_ns)
        self.offset = st.st_size
        try:
            with open(self.path, "rb") as f:
                start = max(0, st.st_size - 4096)
                f.seek(start)
                data = f.read(st.st_size - start)
        except OSError:
            self.offset, self.tail = 0, b""
            return None
        self.tail = data[-self.TAIL:]
        if time.time() - st.st_mtime >= EVENT_STALE:
            return None
        for line in reversed(data.split(b"\n")):
            event = parse_token(line)
            if event:
                return event
        return None

    def _read_from(self, start):
        try:
            with open(self.path, "rb") as f:
                f.seek(start)
                return f.read(EVENT_MAX_READ)
        except OSError:
            return None                        # locked by a writer: retry next poll

    def poll(self, now):
        st = self._stat()
        if st is None:
            self.offset, self.tail, self.sig, self.partial_since = 0, b"", None, None
            return ()
        size = st.st_size
        sig = (size, st.st_mtime_ns)
        if sig == self.sig and self.partial_since is None:
            if (size > EVENT_TRUNC_SIZE and size == self.offset
                    and now - self.changed_at >= EVENT_TRUNC_IDLE):
                self._truncate(size)
            return ()
        if sig != self.sig:
            self.sig = sig
            self.changed_at = now
        if size < self.offset:
            self.offset, self.tail = 0, b""
        keep = len(self.tail)
        start = self.offset - keep
        data = self._read_from(start)
        if data is None:
            return ()
        if keep and data[:keep] != self.tail:  # rewritten in place: read it all again
            self.offset, self.tail, keep, start = 0, b"", 0, 0
            data = self._read_from(0)
            if data is None:
                return ()
        new = data[keep:]
        nl = new.rfind(b"\n")
        chunk, rest = (new[:nl + 1], new[nl + 1:]) if nl >= 0 else (b"", new)
        if rest:
            if self.partial_since is None:
                self.partial_since = now
            elif now - self.partial_since >= EVENT_PARTIAL_WAIT:
                chunk += rest
                self.partial_since = None
        else:
            self.partial_since = None
        if not chunk:
            return ()
        self.offset += len(chunk)
        self.tail = data[:keep + len(chunk)][-self.TAIL:]
        if len(chunk) > EVENT_MAX_BACKLOG:      # a flood (e.g. we were stuck): newest only
            cut = chunk.find(b"\n", len(chunk) - EVENT_MAX_BACKLOG)
            chunk = chunk[cut + 1:] if cut >= 0 else chunk[-EVENT_MAX_BACKLOG:]
        return [e for e in (parse_token(l) for l in chunk.split(b"\n")) if e]

    def _truncate(self, size):
        try:
            with open(self.path, "r+b") as f:
                f.seek(0, 2)
                if f.tell() != size:
                    return
                f.truncate(0)
        except OSError:
            return
        self.offset, self.tail = 0, b""
        self.sig = None        # next poll re-reads: a hook may have appended right after the truncate


# --------------------------------------------------------------------------- state.json
def load_state():
    """-> (feet (x, y) or None, scale, migrated_from_v1)."""
    try:
        with open(STATE_PATH, "rb") as f:
            d = json.loads(f.read().decode("utf-8-sig"))
        x, y = int(d["x"]), int(d["y"])
    except Exception:
        return None, 1.0, False
    if "scale" in d:
        try:
            s = float(d["scale"])
            s = clamp(s, SCALE_MIN, SCALE_MAX) if math.isfinite(s) else 1.0
        except (TypeError, ValueError):
            s = 1.0
        if abs(s - 1.0) < SCALE_SNAP:
            s = 1.0
        return (x, y), s, False
    # v1 stored the window's top-left corner of the 156x168 v1 canvas
    return (x + V1_ANCHOR[0], y + V1_ANCHOR[1]), 1.0, True


def load_look():
    """-> how the plain signs look (state.json "sign"), what is not known left as it is by default."""
    look = dict(SIGN_LOOK_DEFAULT)
    try:
        with open(STATE_PATH, "rb") as f:
            d = json.loads(f.read().decode("utf-8-sig")).get("sign")
    except Exception:
        return look
    if isinstance(d, dict):
        for kind in look:
            if look_level(kind, d.get(kind)) is not None:
                look[kind] = d[kind]
    return look


def system_lang():
    """zh when Windows shows Chinese, else en: the language until one is picked (state.json has none yet)."""
    try:
        return "zh" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x04 else "en"
    except Exception:
        return "zh"


def load_lang():
    global LANG
    lang = None
    try:
        with open(STATE_PATH, "rb") as f:
            lang = json.loads(f.read().decode("utf-8-sig")).get("lang")
    except Exception:
        pass
    LANG = lang if lang in dict(LANGS) else system_lang()


def load_activity():
    global ACTIVITY
    try:
        with open(STATE_PATH, "rb") as f:
            act = json.loads(f.read().decode("utf-8-sig")).get("activity")
    except Exception:
        return
    if act in ACTIVITY_PACE:
        ACTIVITY = act


def set_lang(lang):
    """-> True if it changed."""
    global LANG
    if lang not in dict(LANGS) or lang == LANG:
        return False
    LANG = lang
    log("language: %s" % lang)
    return True


def load_family():
    """-> (size asked for or None, slots of the other pets, {slot: (x, y, big one's size then)}),
    whatever the file holds."""
    try:
        with open(STATE_PATH, "rb") as f:
            d = json.loads(f.read().decode("utf-8-sig"))
    except Exception:
        return None, [], {}
    wanted = None
    try:
        v = float(d.get("wanted"))
        if math.isfinite(v):
            wanted = clamp(v, SCALE_MIN, SCALE_MAX)
    except (TypeError, ValueError):
        pass
    raw = d.get("slots")
    slots = [s for s in range(1, len(FAMILY_RATIOS)) if isinstance(raw, list) and s in raw]
    pos = {}
    raw = d.get("pos")
    if isinstance(raw, dict):
        for s in range(1, len(FAMILY_RATIOS)):
            try:
                v = raw[str(s)]
                pos[s] = (int(v[0]), int(v[1]), float(v[2]) if len(v) > 2 else None)
            except (KeyError, IndexError, TypeError, ValueError):
                pass
    return wanted, slots, pos


def load_homes():
    """-> {slot: (x, y)}: the small ones still away after a combo when the program ended."""
    try:
        with open(STATE_PATH, "rb") as f:
            raw = json.loads(f.read().decode("utf-8-sig")).get("homes")
        return {int(k): (int(v[0]), int(v[1])) for k, v in raw.items() if int(k) in range(1, len(FAMILY_RATIOS))}
    except Exception:
        return {}


GROW_NEED_TOP = 1080        # XP a level takes at most (what Lv.9 takes): from Lv.9 on each level is as long, about a day's
                            # work.  Lv.20 (LEVEL_MAX) is 15,242 XP in all: about half a month (养成规划 第三节)


def grow_need(level):
    """XP from Lv.level to the next one: longer and longer up to Lv.9, the same from there on."""
    return min(int(round(40 * level ** 1.5)), GROW_NEED_TOP)


GROW_XP_MAX = 10 ** 9       # a file edited by hand cannot make the level take forever to work out


def grow_level(xp):
    """-> (level, XP into it, XP it takes to the next).  LEVEL_MAX is the top: the XP goes on, the level does not."""
    xp = min(xp, GROW_XP_MAX)
    level = 1
    while xp >= grow_need(level) and level < LEVEL_MAX:
        xp -= grow_need(level)
        level += 1
    return level, xp, grow_need(level)


def grow_safe(fn):
    """养成 never gets in the way of the rest (the work, the signs, the timer): an error in it is logged, that is all."""
    def safe(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            log_exc("grow: " + fn.__name__)
            return None
    safe.__name__ = fn.__name__
    return safe


class Grow(object):
    """The family's growth, in grow.json (apart from state.json): one pool of XP, the combos seen so far, numbers
    of the work.  Counted in memory as things happen, written at most once a minute, at once on a new level and on
    the way out, through a temp file.  The first write of a day keeps the file before it as grow.json.bak.  A
    broken file: the backup (the broken one stays as grow.json.bad); both broken: from zero.  Never a reason to stop."""

    def __init__(self, path):
        self.path = path
        self.bak = path + ".bak"
        self.dirty = False
        self.saved_at = time.perf_counter()
        self.last_play = self.last_hand = -1e9
        self._prog = None
        self.readonly = False                  # counted here, never written (another player has it, or it cannot be read)
        # one writer per file: a second player on the same home (a trial run beside the real one) only counts
        key = zlib.crc32(os.path.normcase(os.path.abspath(path)).encode("utf-8")) & 0xFFFFFFFF
        self._mutex = CreateMutexW(None, False, "Local\\ClawdGrow.%08x" % key)
        if not self._mutex or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            self.readonly = True
            log("grow: another player keeps %s: counted here, not written" % os.path.basename(path))
        self.bak_day = None
        try:
            if os.path.exists(self.bak):
                self.bak_day = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(self.bak)))
        except OSError:
            pass
        self.data = self._load()

    @staticmethod
    def _today():
        return time.strftime("%Y-%m-%d")

    def _fresh(self):
        return {"v": 1, "xp": 0, "level_shown": 1, "seen": {}, "combos": {}, "acts": {}, "items": {}, "chances": DIG_START_CHANCES, "chance_secs": 0.0, "loot": [], "dry_hand": 0, "dry_uncommon": 0, "dry_rare": 0, "dry_special": 0,
                "slips": {}, "slip_dry": 0, "plane_day": "", "album_marks": [], "gifts": [], "turns": 0, "empty_turns": 0, "work_secs": 0.0,
                "agents": 0, "fixes": 0, "plays": 0, "days": 0, "last_day": "", "since": self._today(), "daily": {}, "monument": {}}

    def _read(self, path):
        raw = None
        for i in range(3):                     # a virus scan may hold it a moment
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                break
            except FileNotFoundError:
                raise
            except OSError:
                if i == 2:
                    raise
                time.sleep(0.2)
        d = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(d, dict) or type(d.get("xp")) is not int or d["xp"] < 0:
            raise ValueError("not a grow file")
        out = self._fresh()
        for k, v in d.items():
            want = out.get(k)
            if want is None or type(v) is type(want) or (type(want) is float and type(v) is int):
                out[k] = v                     # a value of the wrong kind keeps the default
        out["xp"] = min(out["xp"], GROW_XP_MAX)
        num = (int, float)
        out["daily"] = {k: v for k, v in out["daily"].items()
                        if isinstance(v, list) and len(v) == 4 and all(type(x) in num for x in v)}
        out["seen"] = {k: v for k, v in out["seen"].items() if isinstance(v, str)}
        out["acts"] = {k: v for k, v in out["acts"].items() if isinstance(v, str)}
        out["slips"] = {k: v for k, v in out["slips"].items() if k in SLIPS and isinstance(v, str)}
        out["combos"] = {k: v for k, v in out["combos"].items() if type(v) is int and v >= 0}
        for k in [k for k in out["combos"] if "." in k]:     # a combo counted apart by who played it (round 7, for a day):
            base = k.partition(".")[0]                       # it is one combo again
            out["combos"][base] = out["combos"].get(base, 0) + out["combos"].pop(k)
        for k in [k for k in out["seen"] if "." in k]:
            base, day = k.partition(".")[0], out["seen"].pop(k)
            out["seen"][base] = min(out["seen"].get(base, day), day)
        out["items"] = {k: v for k, v in out["items"].items() if type(v) is int and v > 0}
        out["chances"] = min(int(out["chances"]), dig_cap(grow_level(int(out["xp"]))[0])) if type(out["chances"]) is int else 0
        out["gifts"] = [x for x in out["gifts"] if isinstance(x, str)]
        out["monument"] = {k: v for k, v in out["monument"].items()
                           if k in MONUMENT_KEYS and type(v) in ((str,) if k in ("since", "day") else (int, float))}
        out["album_marks"] = sorted(set(x for x in out["album_marks"] if type(x) is int))
        out["loot"] = [[x[0], x[1]] for x in out["loot"]
                       if isinstance(x, list) and len(x) == 2 and isinstance(x[0], str) and type(x[1]) is int][:8]
        for k, want in self._fresh().items():
            if type(want) in num and not (type(out[k]) in num and out[k] >= 0):
                out[k] = want
        return out

    def _load(self):
        for p in (self.path, self.bak):
            try:
                d = self._read(p)
            except FileNotFoundError:
                continue
            except OSError as e:               # there, but it cannot be read now: never taken for broken
                log("grow: %s cannot be read (%s): counted, not written this time" % (os.path.basename(p), e))
                self.readonly = True
                continue
            except Exception as e:
                log("grow: %s unreadable (%s)" % (os.path.basename(p), e))
                if p == self.path:
                    try:
                        os.replace(p, p + ".bad")      # kept for a look, never written over
                    except OSError:
                        pass
                continue
            if p == self.bak:
                log("grow: taken from the backup")
                self.dirty = True
            return d
        return self._fresh()

    @property
    def level(self):
        return self.progress()[0]

    def progress(self):
        xp = self.data["xp"]
        if self._prog is None or self._prog[0] != xp:   # asked at every tick: worked out when the XP changes
            self._prog = (xp, grow_level(xp))
        return self._prog[1]

    def monument(self):
        """The numbers of today, kept for good (the gift monument): set once, never changed after."""
        d = self.data
        if d["monument"]:
            return
        items = [v for v in d["items"].values() if type(v) is int and v > 0]
        d["monument"] = {"since": d["since"], "day": self._today(), "days": d["days"], "turns": d["turns"],
                         "work_secs": round(d["work_secs"], 1), "things": sum(items), "kinds": len(items),
                         "played": sum(v for v in d["combos"].values() if type(v) is int), "agents": d["agents"],
                         "fixes": d["fixes"], "plays": d["plays"], "xp": d["xp"]}
        self.dirty = True

    def _day(self):
        """Today's numbers [turns, s at work, empty turns, XP]; a new day of their life together counts once."""
        d = self.data
        today = self._today()
        if d["last_day"] != today:
            d["last_day"] = today
            d["days"] += 1
        day = d["daily"].get(today)
        if not (isinstance(day, list) and len(day) == 4):
            day = d["daily"][today] = [0, 0.0, 0, 0]
            for k in sorted(d["daily"])[:-GROW_DAILY_KEEP]:
                del d["daily"][k]
        self.dirty = True
        return day

    def add(self, n, why):
        """-> True if that reached a new level."""
        if n <= 0:
            return False
        before = self.level
        self.data["xp"] += n
        self._day()[3] += n
        lv, into, need = self.progress()
        log("grow: +%d %s (xp %d, Lv.%d %d/%d)" % (n, why, self.data["xp"], lv, into, need))
        return lv > before

    def turn(self, secs, tools, failed, how=""):
        """A turn is over: counted (an empty one apart).  -> its XP: none if it used no tool or ended in an error."""
        d = self.data
        day = self._day()
        secs = max(0.0, secs)
        log("grow: turn %.0fs, %d tools%s%s" % (secs, tools, ", ended in an error" if failed else "", ", " + how if how else ""))
        if not tools:
            d["empty_turns"] += 1
            day[2] += 1
            return 0
        d["turns"] += 1
        d["work_secs"] = round(d["work_secs"] + secs, 1)
        day[0] += 1
        day[1] = round(day[1] + secs, 1)
        if failed:
            return 0
        return GROW_XP["turn"] + int(secs // 60) * GROW_XP["turn_minute"]      # its work time: no cap (the user, 11-16)

    def count(self, key):
        self.data[key] += 1
        self.dirty = True

    def play(self, now, why):
        """-> the XP for playing with them: none if the last play was too recent."""
        if now - self.last_play < GROW_PLAY_GAP:
            return 0
        self.last_play = now
        self.count("plays")
        return GROW_XP[why]

    def discover(self, name):
        """-> True the first time this combo is seen."""
        if name in self.data["seen"]:
            return False
        self.data["seen"][name] = self._today()
        self.dirty = True
        return True

    def played(self, name):
        """A combo played to its end, whoever began it.  -> (stars it has now, the XP of a star just reached or 0)."""
        n = self.data["combos"][name] = self.data["combos"].get(name, 0) + 1
        self.dirty = True
        return sum(1 for need, _ in GROW_STARS if n >= need), next((xp for need, xp in GROW_STARS if n == need), 0)

    def slip(self, name, went):
        """One of the SLIPS combos played to its end, the other way (went) or not.  -> True at its first 小插曲."""
        self.dirty = True
        if not went:
            self.data["slip_dry"] += 1
            return False
        self.data["slip_dry"] = 0
        if name in self.data["slips"]:
            return False
        self.data["slips"][name] = self._today()
        return True

    def hand(self, now):
        """-> the XP for a combo you set up yourself: none if the last was too recent."""
        if now - self.last_hand < GROW_HAND_GAP:
            return 0
        self.last_hand = now
        return GROW_XP["hand"]

    def act(self, key):
        """-> True the first time this action is seen."""
        if key in self.data["acts"]:
            return False
        self.data["acts"][key] = self._today()
        self.dirty = True
        return True

    def work(self, secs, per):
        """干活时间 (Family.work_tick: any turn at work, counted once): each per s of it one more chance to dig by
        hand, at once, in the middle of a turn too; what is over is kept for the next.  With dig_cap of the level
        kept, the time does not add up (nothing is put by for later).  -> True when a chance comes."""
        d = self.data
        if per <= 0 or d["chances"] >= dig_cap(self.level):
            return False
        d["chance_secs"] = max(0.0, d["chance_secs"]) + secs
        if d["chance_secs"] < per:
            return False                       # written down with the next save (a turn's end, the way out)
        d["chance_secs"] -= per
        d["chances"] += 1
        self.dirty = True
        return True

    def earn_chance(self, secs, per, whole=True):
        """Tests (per 0, the default with --debug): each whole turn (one that ended with stop, not cut short) is one
        more find to dig up by hand, dig_cap of the level kept at most.  (per > 0: Grow.work, as the work goes.)"""
        d = self.data
        if whole and d["chances"] < dig_cap(self.level):
            d["chances"] += 1
            self.dirty = True

    def new_left(self, tier, rarity_of):
        """True if some treasure of at least this rarity is not theirs yet (of rarity_of: what a dig may bring now)."""
        order = [n for n, _ in DIG_RARITY]
        return any(n not in self.data["items"] for n, ra in rarity_of.items()
                   if ra in order and order.index(ra) >= order.index(tier))

    def roll(self, rarity_of, pending=()):
        """pending: finds put away in this turn, not theirs yet (they become theirs when it ends): drawn as if they
        were already, so that 保底 does not give the same sure one twice."""
        if pending:
            d = self.data
            keep = (dict(d["items"]), {r: d["dry_" + r] for r in DIG_DRY}, self.dirty)
            try:
                for item in pending:
                    if item in rarity_of:
                        self.take(item, rarity_of[item], rarity_of)
                return self.roll(rarity_of)
            finally:
                d["items"] = keep[0]
                for r, v in keep[1].items():
                    d["dry_" + r] = v
                self.dirty = keep[2]
        return self._roll(rarity_of)

    def _roll(self, rarity_of):
        """-> a treasure for a find: common mostly; one you do not have yet is likelier.  保底: after DIG_DRY finds
        with nothing new of at least uncommon / rare / special, the next is a new one of at least that (the lowest
        rarity from there that has one); a rarity with nothing new left at or above it has no 保底 any more."""
        d = self.data
        order = [n for n, _ in DIG_RARITY]
        floor = next((r for r in ("special", "rare", "uncommon") if d["dry_" + r] >= DIG_DRY[r] - 1
                      and self.new_left(r, rarity_of)), "common")
        r, acc, rarity = random.random(), 0.0, "common"
        for name, pr in DIG_RARITY:
            acc += pr
            if r < acc:
                rarity = name
                break
        if order.index(rarity) <= order.index(floor) and floor != "common":   # the sure one: something new
            for tier in order[order.index(floor):]:
                new = [n for n, ra in rarity_of.items() if ra == tier and n not in d["items"]]
                if new:
                    return random.choice(new)
        pool = [n for n, ra in rarity_of.items() if ra == rarity]
        while not pool and rarity != "common":             # a frame set without that rarity: the one below
            rarity = order[order.index(rarity) - 1]
            pool = [n for n, ra in rarity_of.items() if ra == rarity]
        if not pool:
            return None
        item = random.choices(pool, [1.0 if n not in d["items"] else DIG_OWNED for n in pool])[0]
        return item

    def take(self, item, rarity, rarity_of=None):
        """The find is theirs.  -> (how many of it now, True if it is the first).  保底 counts the finds since a new one
        of at least each rarity: one they had already does not reset it (no luck is lost to a find they had), unless
        nothing new is left at or above that rarity (rarity_of: what a dig may bring now; None: any find resets)."""
        d = self.data
        new = item not in d["items"]
        order = [r for r, _ in DIG_RARITY]
        if rarity in order:
            for r in DIG_DRY:
                done = order.index(rarity) >= order.index(r) and (new or rarity_of is None or not self.new_left(r, rarity_of))
                d["dry_" + r] = 0 if done else d["dry_" + r] + 1
        n = d["items"][item] = d["items"].get(item, 0) + 1
        self.dirty = True
        return n, n == 1

    def tick(self, now):
        if self.dirty and now - self.saved_at >= (GROW_SAVE_SOON if getattr(self, "watched", False) else GROW_SAVE_EVERY):
            self.save()

    def save(self):
        if not self.dirty or self.readonly:
            return
        self.saved_at = time.perf_counter()
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, sort_keys=True)
            today = self._today()
            if self.bak_day != today and os.path.exists(self.path):
                with open(self.path, "rb") as f:   # the file as it was before today: a fall-back if today's goes wrong
                    old = f.read()
                with open(self.bak + ".tmp", "wb") as f:
                    f.write(old)
                os.replace(self.bak + ".tmp", self.bak)
                self.bak_day = today
            os.replace(tmp, self.path)
            self.dirty = False
        except Exception:
            log_exc("grow save")


def remove_tree(path):
    if os.path.isdir(path):
        import shutil
        shutil.rmtree(path, ignore_errors=True)
        return not os.path.exists(path)
    return False


def has_all_actions(store, base_dir):
    """A custom set rendered before clips were added to the base set lacks them, and one scaled from other frames
    (an update with new art: its "source_stamp" is not its source's set_stamp now): render it again."""
    try:
        with open(os.path.join(base_dir, "manifest.json"), "rb") as f:
            m = json.loads(f.read().decode("utf-8-sig"))
        names = (m.get("actions") or {}).keys()
    except Exception:
        return True                            # no way to tell: keep it
    if not all(n in store.meta for n in names):
        return False
    src = base_dir if store.body_px <= int(m.get("base_body_px") or 100) else hi_dir_of(base_dir)
    now = set_stamp(src)
    if now is None:
        return True
    try:
        with open(os.path.join(store.dir, "manifest.json"), "rb") as f:
            was = json.loads(f.read().decode("utf-8-sig")).get("source_stamp")
    except Exception:
        return False
    if was != now:
        if (store.dir, now) not in _STALE_SAID:      # the others ask every 0.5 s while one scales: say it once
            _STALE_SAID.add((store.dir, now))
            log("frames %s: scaled from other frames than %s now: scaled again" % (store.dir, src))
        return False
    return True


_STALE_SAID = set()
_STAMPS = {}


def set_stamp(d):
    """As clawd_scale.py set_stamp (the manifest's bytes, each .frames file's name and size); None if there is no
    set.  Kept per manifest change time: a few hundred stats once, not per check."""
    import hashlib
    mp = os.path.join(d, "manifest.json")
    try:
        key = (os.path.abspath(d), os.stat(mp).st_mtime_ns)
    except OSError:
        return None
    if key not in _STAMPS:
        try:
            h = hashlib.sha1()
            with open(mp, "rb") as f:
                h.update(f.read())
            for n in sorted(os.listdir(d)):
                if n.endswith(".frames"):
                    h.update(("%s:%d;" % (n, os.path.getsize(os.path.join(d, n)))).encode("utf-8"))
            _STAMPS[key] = h.hexdigest()
        except OSError:
            return None
    return _STAMPS[key]


def custom_dir_of(slot):
    """Where the pet in this slot keeps its re-rendered set: slot 0 is the plain frames_custom."""
    return CUSTOM_DIR if slot == 0 else "%s_%d" % (CUSTOM_DIR, slot)


def remove_stale_render_dirs(custom_dir):
    for p in (custom_dir + ".tmp", custom_dir + ".old"):
        remove_tree(p)


def hi_dir_of(base_dir):
    return os.path.join(os.path.dirname(os.path.abspath(base_dir)), HI_DIR_NAME)


def run_in_job(proc):
    """Resume a process created suspended inside a new kill-on-close job, so that it and everything
    it starts die with the job, or with this process.  -> job handle, or None if that failed."""
    job = None
    try:
        job = CreateJobObjectW(None, None)
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not (job and SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                                ctypes.byref(info), ctypes.sizeof(info))
                and AssignProcessToJobObject(job, int(proc._handle))):
            log("no job object for the re-render, error %d" % ctypes.get_last_error())
            if job:
                CloseHandle(job)
            job = None
    finally:
        NtResumeProcess(int(proc._handle))
    return job


def job_active_processes(job):
    info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
    if not QueryInformationJobObject(job, JobObjectBasicAccountingInformation, ctypes.byref(info),
                                     ctypes.sizeof(info), None):
        return 0
    return info.ActiveProcesses


# macOS: no Job Object.  The re-render runs under nice (what BELOW_NORMAL_PRIORITY_CLASS is), in a session (so a
# process group) of its own, which stop_render_mac ends; and clawd_scale.py stops by itself once the pet is gone.
RENDER_NICE = "10"
RENDER_TERM_WAIT = 2.0      # s after SIGTERM before SIGKILL


def start_render_mac(cmd, logf, env):
    import subprocess
    return subprocess.Popen(["/usr/bin/nice", "-n", RENDER_NICE] + cmd, stdin=subprocess.DEVNULL, stdout=logf,
                            stderr=subprocess.STDOUT, cwd=HERE, env=env, **child_kw())


def stop_render_mac(proc):
    """Its process group: SIGTERM, and SIGKILL if it is still there RENDER_TERM_WAIT s later.  Only while proc has not
    been waited for: its pid (the group's id) cannot have gone to another process yet."""
    import signal
    import subprocess
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(RENDER_TERM_WAIT)
            return
        except subprocess.TimeoutExpired:
            pass


def remove_custom_sets(custom_dir, why):
    removed = [p for p in (custom_dir, custom_dir + ".tmp", custom_dir + ".old") if remove_tree(p)]
    if removed:
        log("deleted %s (%s)" % (", ".join(os.path.basename(p) for p in removed), why))


# --------------------------------------------------------------------------- the pet
class Pet(object):
    """One window: its picture, its animation, its mouse and its place on the screen."""

    def __init__(self, family, slot, store, base_dir, scale, feet, opts):
        self.family = family
        self.slot = slot
        self.tag = "pet%d " % slot if slot else ""
        self.react = None              # (clip, when): a reaction to the big one's event
        self.reacted = None            # the clip the big one chose for the last stop or fail
        self.turn_secs = None          # how long the last turn took (the big one), for the sign
        self.signing = False           # holds up the sign: no extras, walks, reactions or combos of its own
        self.dozing = False            # dozes off by the resting cursor (doze_in, doze); any other clip startles it first
        self.dig = None                # 翻找 under way: {"hand": asked for by you, "until": digs on until then}
        self.dig_rank = R_RUMMAGE      # ... what it is worth (R_HAND when you asked), also while its ending plays
        self.item = None               # a find at the arm's tip now: {"name", "rarity", "clip", "t0"}
        self.overlay = None            # ... and the two small windows that show it
        self.doze_manual = False       # ... asked for by hand: it wakes by itself after DOZE_MANUAL_LOOPS (the cursor does not wake it)
        self.doze_from = 0.0           # ... counted from then
        self.doze_alone = None         # the cursor went elsewhere: it gets up by itself at this time
        self.doze_sleep = False        # the family's bedtime came while it dozed: into sleep at the next nod
        self.in_combo = False
        self.home = None               # (x, y) where it stood before a combo
        self.watch_home = False        # ... it came to watch the big one at work: it stays until the work is done
        self.area = None               # x where the user put it (or it started): its walks stay near
        self.return_at = None          # when it walks back there
        self.returning = False         # on its way back
        self.hop = None                # a jump under way: the window flies along an arc
        self.perch = None              # the pet it stands on (叠罗汉), also while it jumps up or down
        self.ground = None             # (x, y) on the floor while it is up there: where it comes down, what is saved
        self.carry = None              # "left" / "right": holds a note on that side (传纸条)
        self.carry_item = False        # ... or a find (交宝贝): read only while carry is set
        self.hand_clip = None          # the clip you asked for by name (menu, clawd do), while it is queued or plays
        self.custom_dir = custom_dir_of(slot)
        self.render_log = RENDER_LOG if slot == 0 else "%s.%d" % (RENDER_LOG, slot)
        self.store = store
        self.base_dir = os.path.abspath(base_dir)
        self.hi_dir = hi_dir_of(base_dir)
        self.base_body_px = store.body_px
        if store.dir != self.base_dir:                # started on another set
            b = None
            try:
                b = FrameStore(base_dir)
            except Exception:
                pass
            if b is not None:
                self.base_body_px = b.body_px
        self.debug = opts["debug"]
        self.extra_range = paced(opts["extra_range"])
        self.wander_range = paced(opts["wander_range"])
        self.sleep_after = opts["sleep_after"]
        self.dump_dir = opts["dump_dir"]
        self.scale = scale
        self.hwnd = None
        self.quitting = False
        self.errors = 0
        self.n_ticks = 0
        self.n_draws = 0
        self.n_dumps = 0
        self.born = time.perf_counter()
        now = self.born

        # display
        self.memdc = None
        self.hbmp = None
        self.stock_bmp = None
        self.bits = None
        self.dw = self.dh = 0
        self.size = SIZE(0, 0)
        self.disp = 1.0
        self.scaler = None
        self.scaler_broken = False
        self.src_pt = POINT(0, 0)
        self.blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        self.ax = self.ay = 0.0
        self.bbox = store.bbox
        self.fx, self.fy = feet if feet else (0, 0)
        self.win_pos = (0, 0)
        self.ulw_fail_t = 0.0

        # animation
        self.idle_name = store.idle_name
        self.cur = None
        self.cur_kind = KIND_LOOP
        self.cur_frames = None
        self.cur_fps = store.fps
        self.cur_seq = None
        self.cur_until = None
        self.t0 = now
        self.last_idx = -1
        self.loop_no = 0
        self.last_blob = None
        self.bad_idle = set()
        self.pending = None            # (name, until) of a queued clip
        self.next_extra = now + random.uniform(*self.extra_range)
        self.next_wander = now + random.uniform(*self.wander_range)
        self.extra_wanted = None
        self.extra_deadline = 0.0

        # behaviour state
        self.busy = False              # some session is working
        self.busy_clip = "think"       # what the session heard from last is doing
        self.working = {}              # session -> since, until, seen, clip, was_busy (before a compact)
        self.turn_over = set()         # sessions whose last turn reported stop, with no new prompt yet
        self.attention_session = ""
        self.fail_times = []
        self.last_confused = -1e9
        self.attention_until = 0.0
        self.att_i = 0
        self.sleeping = False
        self.wander = None
        self.last_activity = now
        self.last_hover = -1e9
        self.hovering = False

        # mouse
        self.press = None              # screen pos of a left press
        self.press_consumed = False
        self.grab = (0, 0)
        self.dragging = False
        self.glide = None
        self.trail = []                # (ms, x, y) of the cursor while dragged, the ms of the input event: the
                                       # speed at the release (by time, not by count: a 1000 Hz mouse sends many)
        self.fly = None                # thrown and in the air
        self.caught = False            # caught in the air: a click lets it fall on
        self.releasing = False
        self.click_due = None
        self.click_burst = 0
        self.last_click_t = -1e9
        self.click_times = []
        self.dbl_time = clamp(GetDoubleClickTime() / 1000.0, 0.1, 1.0)

        # size / re-render / files
        self.size_due = None
        self.render = None             # {"proc", "job", "px", "t", "logf"}
        self.render_failed = set()
        self.render_unavailable_logged = False
        self.next_poll = 0.0
        self.next_watch = now + WATCH_INTERVAL

        self._create_window(feet)

    # ----------------------------------------------------------- window / GDI
    def _create_window(self, feet):
        self.memdc = CreateCompatibleDC(None)
        if not self.memdc:
            raise ctypes.WinError(ctypes.get_last_error())
        self._reconfigure()
        if feet is None or not self._feet_on_screen(*feet):
            self.fx, self.fy = self._default_feet()
        self.fx, self.fy = self._clamped(self.fx, self.fy)
        self.win_pos = self._win_xy()

        ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        x, y = self.win_pos
        self.hwnd = CreateWindowExW(ex, CLASS_NAME, "Clawd", WS_POPUP, x, y, self.dw, self.dh,
                                    None, None, self.family.hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.family.windows[self.hwnd] = self

        now = time.perf_counter()
        self._start(self.idle_name, now, "startup", draw=False)
        if not self.family.hidden:             # one called while the family is hidden comes along when it shows
            self._redraw(pos=True)
            ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        self._save_state()
        if self.scale != 1.0:
            self.size_due = now + RERENDER_DELAY             # maybe no native set for this size yet
        if not SetTimer(self.hwnd, TIMER_ANIM, 50, None):
            raise ctypes.WinError(ctypes.get_last_error())

    def _make_dib(self, w, h):
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h          # negative = top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bits = LPVOID()
        hbmp = CreateDIBSection(self.memdc, ctypes.byref(bmi), DIB_RGB_COLORS,
                                ctypes.byref(bits), None, 0)
        if not hbmp or not bits.value:
            raise ctypes.WinError(ctypes.get_last_error())
        if self.scaler is not None:
            self.scaler.release()            # its target wraps the old bits
        GdiFlush()
        old = SelectObject(self.memdc, hbmp)
        if self.stock_bmp is None:
            self.stock_bmp = old
        if self.hbmp:
            DeleteObject(self.hbmp)
        self.hbmp, self.bits = hbmp, bits.value
        self.dw, self.dh = w, h
        self.size = SIZE(w, h)
        ctypes.memset(self.bits, 0, w * h * 4)
        self.last_blob = None

    def _reconfigure(self):
        """(Re)compute the display factor / window size for self.store and self.scale."""
        st = self.store
        disp = self._target_px() / float(st.body_px)     # the very size a native set would have
        if abs(disp - 1.0) < DISP_SNAP or self.scaler_broken:
            disp = 1.0
        w, h = st.width, st.height
        ax, ay = st.anchor
        if disp == 1.0:
            dw, dh = w, h
        else:
            # one spare pixel: the source is shifted by < 1 px to put the anchor on a whole pixel
            dw, dh = int(math.ceil(w * disp)) + 1, int(math.ceil(h * disp)) + 1
        if (dw, dh) != (self.dw, self.dh) or not self.bits:
            self._make_dib(dw, dh)
        if disp != 1.0:
            try:
                if self.scaler is None:
                    self.scaler = Scaler()
                src_rect = (ax - round(ax * disp) / disp, ay - round(ay * disp) / disp, dw / disp, dh / disp)
                self.scaler.configure(w, h, self.bits, dw, dh, src_rect)
            except Exception:
                log_exc("GDI+ scaler; showing unscaled frames")
                self.scaler_broken = True
                self.scaler = None
                disp = 1.0
                b = try_store(self.base_dir) if st.dir == self.hi_dir else None
                if b is not None:                  # the 300 % master unscaled would be absurd
                    self.store = st = b
                    w, h = st.width, st.height
                    if self.cur:
                        self.cur_frames = b.frames(self.cur) or self.cur_frames
                if (w, h) != (self.dw, self.dh):
                    self._make_dib(w, h)
        elif self.scaler is not None:
            self.scaler.release()
        self.disp = disp
        self.ax, self.ay = st.anchor
        self.bbox = st.bbox
        self.last_blob = None

    def destroy_gdi(self):
        try:
            if self.scaler is not None:
                self.scaler.shutdown()
                self.scaler = None
            if self.memdc:
                if self.stock_bmp:
                    SelectObject(self.memdc, self.stock_bmp)
                DeleteDC(self.memdc)
                self.memdc = None
            if self.hbmp:
                DeleteObject(self.hbmp)
                self.hbmp = None
        except Exception:
            log_exc("cleanup")

    def _present(self, pos=None):
        ok = UpdateLayeredWindow(self.hwnd, None, ctypes.byref(pos) if pos is not None else None,
                                 ctypes.byref(self.size), self.memdc, ctypes.byref(self.src_pt),
                                 0, ctypes.byref(self.blend), ULW_ALPHA)
        if not ok:
            now = time.monotonic()
            if now - self.ulw_fail_t > 60.0:      # e.g. secure desktop; don't spam
                self.ulw_fail_t = now
                log("UpdateLayeredWindow failed, error %d" % ctypes.get_last_error())

    def _draw(self, idx, force=False, pos=None):
        if self.family.hidden:                 # nothing to see: drawn again when the family shows
            self.last_idx = -1
            self.last_blob = None
            return
        frames = self.cur_frames
        if idx >= len(frames):
            idx = len(frames) - 1
        if idx == self.last_idx and not force:
            return
        self.last_idx = idx
        blob = frames[idx]
        if blob is self.last_blob and not force:     # identical frame (interned)
            return
        try:
            raw = zlib.decompress(blob, 15, self.store.frame_bytes)
            if len(raw) != self.store.frame_bytes:
                raise ValueError("%d bytes, expected %d" % (len(raw), self.store.frame_bytes))
        except (zlib.error, ValueError) as e:
            self._bad_frame(idx, e)
            if pos is not None and self.hwnd:
                self._present(POINT(*self.win_pos))
            return
        GdiFlush()
        if self.disp == 1.0:
            ctypes.memmove(self.bits, raw, self.store.frame_bytes)
        else:
            self.scaler.draw(raw)
        del raw
        self.last_blob = blob
        self.n_draws += 1
        if self.hwnd:
            self._present(POINT(*self.win_pos) if pos is not None else None)

    def _redraw(self, pos=False):
        """Redraw the current frame now (after a resize / frame set swap)."""
        idx = self.last_idx if self.last_idx >= 0 else (self.cur_seq[0] if self.cur_seq else 0)
        self.last_idx = -1
        self.last_blob = None
        self._draw(idx, force=True, pos=True if pos else None)
        if self.dump_dir:
            self._dump("resize")

    def _bad_frame(self, idx, err):
        name = self.cur
        if name == self.idle_name:
            if idx not in self.bad_idle:
                self.bad_idle.add(idx)
                log("idle frame %d is broken (%s); skipped" % (idx, err))
            return
        log("action %r frame %d is broken (%s); action disabled" % (name, idx, err))
        self.store.mark_bad(name)
        if self.pending and self.pending[0] == name:
            self.pending = None
        self._start(self.idle_name, time.perf_counter(), "broken " + name)

    def _dump(self, tag):
        try:
            GdiFlush()
            data = ctypes.string_at(self.bits, self.dw * self.dh * 4)
            self.n_dumps += 1
            path = os.path.join(self.dump_dir, "%02d_%s_%s_%dx%d.bgra"
                                % (self.n_dumps, tag, self.cur, self.dw, self.dh))
            with open(path, "wb") as f:
                f.write(data)
            log("dumped %s (disp %.4f)" % (path, self.disp))
        except Exception:
            log_exc("dump")

    # ----------------------------------------------------------- geometry
    def _win_xy(self):
        return (self.fx - int(round(self.ax * self.disp)),
                self.fy - int(round(self.ay * self.disp)))

    def _move_feet(self, fx, fy):
        self.fx, self.fy = int(fx), int(fy)
        self.family.depth_dirty = True
        pos = self._win_xy()
        if pos != self.win_pos:
            self.win_pos = pos
            SetWindowPos(self.hwnd, None, pos[0], pos[1], 0, 0,
                         SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)

    @staticmethod
    def _feet_on_screen(fx, fy):
        return bool(MonitorFromPoint(POINT(int(fx), int(fy) - 1), MONITOR_DEFAULTTONULL))

    @staticmethod
    def _work_area(fx=None, fy=None):
        if fx is not None:
            hmon = MonitorFromPoint(POINT(int(fx), int(fy) - 1), MONITOR_DEFAULTTONEAREST)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if hmon and GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return mi.rcWork
        wa = RECT()
        if not SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(wa), 0):
            wa = RECT(0, 0, 1280, 720)
        return wa

    def _default_feet(self):
        wa = self._work_area()
        fx = self._feet_limits(wa)[1] - MARGIN   # the body's right side MARGIN px from the edge (not the canvas's,
        return fx, wa.bottom - MARGIN            # which has ~70 px of room for the arms and effects at 100 %)

    def _feet_limits(self, wa):
        """(xlo, xhi, ylo, yhi): where the feet can be with the idle body inside work area wa."""
        l, t, r, b = self.bbox
        d = self.disp
        xlo = wa.left + int(math.ceil((self.ax - l) * d))
        xhi = wa.right - int(math.ceil((r + 1 - self.ax) * d))
        ylo = wa.top + int(math.ceil((self.ay - t) * d))
        yhi = wa.bottom - int(math.ceil((b + 1 - self.ay) * d))
        if xhi < xlo:
            xlo = xhi = (xlo + xhi) // 2
        if yhi < ylo:
            ylo = yhi = (ylo + yhi) // 2
        return xlo, xhi, ylo, yhi

    def _clamped(self, fx, fy):
        xlo, xhi, ylo, yhi = self._feet_limits(self._work_area(fx, fy))
        return clamp(fx, xlo, xhi), clamp(fy, ylo, yhi)

    def _ensure_visible(self):
        self.wander = None
        self.glide = None
        if self.hop is not None or self.perch is not None:
            self.hop = None
            self.come_down(0.0, instant=True)
        if self._feet_on_screen(self.fx, self.fy):
            self._move_feet(*self._clamped(self.fx, self.fy))
        elif self.slot:
            self._move_feet(*self._clamped(*self.family.beside(self._target_px())))
        else:
            self._move_feet(*self._default_feet())
        self._save_state()

    # ----------------------------------------------------------- screen edges
    def _drag_to(self, x, y):
        """Follow the cursor; the body stays inside the work area of the monitor under the cursor."""
        xlo, xhi, ylo, yhi = self._feet_limits(self._work_area(x, y + 1))
        self._move_feet(clamp(x - self.grab[0], xlo, xhi), clamp(y - self.grab[1], ylo, yhi))
        t = GetMessageTime() & 0xFFFFFFFF      # when the input happened, not when we got to it
        self.trail.append((t, x, y))
        if len(self.trail) > 64 and _ms_since(self.trail[0][0], t) > THROW_KEEP_MS:
            self.trail = [q for q in self.trail if _ms_since(q[0], t) <= THROW_KEEP_MS]

    def _snap_after_drop(self, now):
        xlo, xhi, ylo, yhi = self._feet_limits(self._work_area(self.fx, self.fy))
        reach = clamp(int(self._target_px() * SNAP_FRACTION), SNAP_MIN, SNAP_MAX)
        fx, fy = self.fx, self.fy
        if fx - xlo <= reach:
            fx = xlo
        elif xhi - fx <= reach:
            fx = xhi
        if fy - ylo <= reach:
            fy = ylo
        elif yhi - fy <= reach:
            fy = yhi
        if (fx, fy) != (self.fx, self.fy):
            self.glide = (self.fx, self.fy, fx, fy, now)
            if self.debug:
                log("snap: feet (%d, %d) -> (%d, %d)" % (self.fx, self.fy, fx, fy))

    def _glide_step(self, now):
        x0, y0, x1, y1, t0 = self.glide
        u = min((now - t0) / GLIDE_SECS, 1.0)
        e = 1.0 - (1.0 - u) * (1.0 - u)
        self._move_feet(int(round(x0 + (x1 - x0) * e)), int(round(y0 + (y1 - y0) * e)))
        if u >= 1.0:
            self.glide = None
            self._save_state()

    def _finish_glide(self):
        if self.glide is not None:
            self._move_feet(self.glide[2], self.glide[3])
            self.glide = None

    def _flush_edges(self):
        """Which edges the body is on: (left, right, top, bottom)."""
        xlo, xhi, ylo, yhi = self._feet_limits(self._work_area(self.fx, self.fy))
        return (abs(self.fx - xlo) <= FLUSH_PX, abs(self.fx - xhi) <= FLUSH_PX,
                abs(self.fy - ylo) <= FLUSH_PX, abs(self.fy - yhi) <= FLUSH_PX)

    def _refit(self, edges):
        """After a size change: back on the edges it was on, and fully inside the work area."""
        xlo, xhi, ylo, yhi = self._feet_limits(self._work_area(self.fx, self.fy))
        left, right, top, bottom = edges
        fx = xlo if left else xhi if right else clamp(self.fx, xlo, xhi)
        fy = ylo if top else yhi if bottom else clamp(self.fy, ylo, yhi)
        self._move_feet(fx, fy)

    def _thumb_cut_off(self):
        xhi = self._feet_limits(self._work_area(self.fx, self.fy))[1]
        return xhi - self.fx < THUMB_REACH * self._target_px()

    def _walk_clip(self):
        w = self.wander
        side = "right" if w is not None and w["dir"] > 0 else "left"
        carry = ("walk_bring_" if self.carry_item else "walk_carry_") + side
        if self.carry is not None and self.store.usable(carry):
            return carry
        name = "walk_" + side
        return name if self.store.usable(name) else self._loop_name("walk")

    def _save_state(self):
        self.family.save_state()

    # ----------------------------------------------------------- clips
    def _kind(self, name):
        if name == self.idle_name:
            return KIND_LOOP
        if name in HOLD_ACTIONS and not self.store.loops(name):
            return KIND_HOLD
        return KIND_LOOP if self.store.loops(name) else KIND_ONESHOT

    def _loop_name(self, name):
        return name if self.store.usable(name) else self.idle_name

    def _first_clip(self, names):
        return next((n for n in names if self.store.usable(n)), None)

    def _shot_name(self, name):
        if self.store.usable(name):
            return name
        alt = SHOT_FALLBACK.get(name)
        if alt and self.store.usable(alt):
            return alt
        return None

    def _base_name(self):
        """What plays when nothing else is asked for (None = attention sequence)."""
        if self.dragging:
            return self._loop_name("dangle")
        if self.fly is not None:
            return self._first_clip(("tumble_" + self.fly["spin"], "dangle")) or self.idle_name
        if self.sleeping:
            return self._loop_name("sleep")
        if self.wander is not None:
            return self._walk_clip()
        if self.carry is not None and self.store.usable(("bring_hold_" if self.carry_item else "carry_hold_") + self.carry):
            return ("bring_hold_" if self.carry_item else "carry_hold_") + self.carry
        if self.dig is not None and self.store.usable("rummage"):          # by hand: also while busy, until the next work event
            return "rummage_fast" if self.dig.get("helped") and self.store.usable("rummage_fast") else "rummage"
        if self.attention_until:
            return None
        if self.dozing and self.doze_manual and self.store.usable("doze"):
            return "doze"                      # asked for by hand: also while busy, until the next work event
        if self.busy:
            return self.busy_clip if self.store.usable(self.busy_clip) else self.idle_name
        if self.dozing and self.store.usable("doze"):
            return "doze"
        return self.idle_name

    def _holding(self, now):
        """Someone stands on its head, is jumping onto it, or has not yet taken off from it."""
        for p in self.family.pets:
            if p.perch is self and (p.hop is None or p.hop["up"] or p.cur != p.hop["clip"] or now - p.t0 < p.hop["off"]):
                return True
        return False

    def _wanted(self, now):
        """Should the current loop / hold clip keep playing?"""
        if self.cur == "stack_brace" and not self.dragging and self._holding(now):
            return True                        # never pulled out from under one standing on it
        if self.cur_until is not None:
            return now < self.cur_until and not self.dragging
        base = self._base_name()
        if self.cur == base:
            return True
        return self.cur in WORK_HOLDS and base == self.busy_clip and now - self.t0 < WORK_MIN_SECS

    def _calm(self):
        return (self.cur == self.idle_name and self.cur_kind == KIND_LOOP and self.cur_until is None
                and self.pending is None and not self.busy and not self.attention_until
                and not self.sleeping and not self.dragging and self.wander is None
                and self.press is None and not self.in_combo and self.hop is None and self.perch is None
                and self.fly is None
                and not (self.family.combo is not None and self.family.combo.get("receiver") is self))

    def _start(self, name, now, why="", until=None, draw=True):
        if self.dig is not None and name not in DIG_ALL:        # called away while it digs: up first (the hole closes)
            was, self.dig = self.dig, None
            self.family.dig_over(self, now, was, why)
            up = self._shot_name("rummage_up")
            if up and self.cur in DIG_LOOP_CLIPS + ("rummage_in", "rummage_spur") and not self.dragging and self.fly is None and self.press is None:
                if name != (self._base_name() or self.idle_name):
                    self.pending = (name, until)
                name, until, why = up, None, "digging cut short (%s)" % why
        if self.dozing and name not in DOZE_CLIPS:      # anything else wakes it: with a start, unless it is taken
            self.dozing = False
            if self.pending is not None and self.pending[0] in DOZE_CLIPS:
                self.pending = None
            self.family.nap_over(self, now, why)
            shock = self._shot_name("doze_startle")
            if (shock and self.cur in ("doze", "doze_in") and not self.dragging and self.fly is None
                    and self.press is None):
                if name != (self._base_name() or self.idle_name):
                    self.pending = (name, until)        # after the start
                name, until, why = shock, None, "startled (%s)" % why
        frames = self.store.frames(name)
        if not frames:
            if name == self.idle_name:
                raise RuntimeError("idle frames unavailable")
            log("action %r unavailable, falling back to idle" % name)
            name, until = self.idle_name, None
            frames = self.store.frames(name)
            if not frames:
                raise RuntimeError("idle frames unavailable")
        kind = self._kind(name)
        if self.hand_clip is not None and name != self.hand_clip and (self.pending is None or self.pending[0] != self.hand_clip):
            self.hand_clip = None
        self.cur, self.cur_kind, self.cur_frames = name, kind, frames
        self.cur_fps = self.store.fps_of(name)
        if self.wander is not None and name == self._walk_clip():
            self.cur_fps *= self.wander.get("gait", 1.0)   # a quick walk takes quicker steps
        self.cur_seq = range(len(frames)) if kind == KIND_ONESHOT else None
        self.cur_until = until
        self.t0 = now
        self.last_idx = -1
        self.loop_no = 0
        if name == self.idle_name:
            self.next_extra = now + random.uniform(*self.extra_range)
            self.extra_wanted = None
        if self.wander is not None:
            self.wander["last"] = None          # (re)start the walk clock with the clip
        self.family.grow_act(name, now)
        if self.debug:
            log("%splay %s [%s]%s (%s)" % (self.tag, name, kind, " for %.0fs" % (until - now) if until else "", why))
        if draw:
            self._draw(self.cur_seq[0] if self.cur_seq else 0)

    def _next(self, now, why):
        if self.pending is not None:
            name, until = self.pending
            self.pending = None
            self._start(name, now, why, until)
        else:
            self._start_base(now, why)

    def _start_base(self, now, why):
        if self.attention_until and not self.dragging:
            names = [n for n in (self._shot_name("wave"), self._shot_name("look_at_viewer")) if n]
            if names:
                name = names[self.att_i % len(names)]
                self.att_i += 1
                self._start(name, now, why + ", attention")
                return
        self._start(self._base_name() or self.idle_name, now, why)

    def request(self, name, now, why="", until=None):
        """Queue / play a clip.  One-shots are never cut off: the latest request waits."""
        if not name:
            return
        if (self.dragging or self.fly is not None or self.cur_kind == KIND_ONESHOT
                or (self.cur == "stack_brace" and self._holding(now))):    # in the air: after the landing
            if self.debug and (self.pending is None or self.pending[0] != name):
                log("pending %s (%s) while %s plays" % (name, why, self.cur))
            self.pending = (name, until)
            return
        if self.cur_kind == KIND_HOLD:
            self.pending = (name, until)
            self._leave_hold(now, why)
            return
        self._start(name, now, why, until)

    def _doze_end(self, now, n):
        """At the doze loop's first frame: enough by hand, alone long enough, or bedtime.  True = clip changed."""
        if self.doze_sleep:
            self.dozing = self.doze_manual = self.doze_sleep = False
            self.doze_alone = None
            self.family.nap_over(self, now, "fell asleep")
            self.sleeping = True
            log("%sfell asleep while dozing" % self.tag)
            if self.slot == 0:
                self.family.big_fell_asleep(now)
            self._start(self._first_clip(("doze_sleep", "sleep")) or self.idle_name, now, "dozed off for real")
            return True
        enough = self.doze_manual and now - max(self.t0, self.doze_from) >= DOZE_MANUAL_LOOPS * n / self.cur_fps - 0.1
        alone = self.doze_alone is not None and now >= self.doze_alone
        if not (enough or alone):
            return False
        self.dozing = self.doze_manual = False     # up through a stretch
        self.doze_alone = None
        self.family.nap_over(self, now, "dozed enough")
        self._start(self._first_clip(("doze_up", "wake_up")) or self.idle_name, now, "dozed enough")
        return True

    def begin_dig(self, now, hand, loops):
        """Down into the crouch and dig for `loops` loops; then family.dig_result says what comes up.  -> True if it starts."""
        st = self.store
        if (self.dig is not None or st.items is None or not all(st.usable(c) for c in DIG_CLIPS)
                or self.dragging or self.fly is not None or self.hop is not None or self.perch is not None):
            return False
        n_in = st.meta["rummage_in"].get("count", 16) / st.fps_of("rummage_in")
        n_loop = st.meta["rummage"].get("count", 24) / st.fps_of("rummage")
        self.dig = {"hand": hand, "until": now + n_in + loops * n_loop - 0.3, "t": now, "n_in": n_in, "loop": n_loop}
        self.dig_rank = R_HAND if hand else R_RUMMAGE
        self.request("rummage_in", now, "digs" + (" (by hand)" if hand else ""))
        return True

    def _dig_end(self, now):
        """At the dig loop's first frame: long enough?  Then the find comes out, or nothing.  True = clip changed."""
        if now < self.dig["until"]:
            return False
        was, self.dig = self.dig, None
        item = self.family.dig_result(self, now, was)
        if item is not None:
            self.item = {"name": item[0], "rarity": item[1], "clip": "rummage_found", "t0": now}
            self._start("rummage_found", now, "found " + item[0])
        else:
            self._start("rummage_none", now, "found nothing")
        return True

    def dig_spur(self, now):
        """You lend a hand (a click): a start, and it digs harder; what was left of the digging takes half as long,
        two strokes at least.  Before the crouch is done it only goes faster once it is down."""
        d = self.dig
        st = self.store
        wait = max(0.0, d["t"] + d["n_in"] - now) if self.cur == "rummage_in" else 0.0
        left = max(0.0, d["until"] - now - wait)
        spur = self.cur in DIG_LOOP_CLIPS and all(st.usable(c) for c in DIG_MORE)
        if spur:
            wait = st.meta["rummage_spur"].get("count", 10) / st.fps_of("rummage_spur")
        d["until"] = now + wait + max(DIG_HELP_HALF * left, DIG_HELP_MIN)
        d["part"] = 0
        if spur:
            self._start("rummage_spur", now, "a hand with the digging")

    def end_dig(self, now, why):
        """Stop digging (work goes on, the family hides ...): up through rummage_up, nothing found, no chance used."""
        if self.dig is None:
            return
        if self.cur in DIG_LOOP_CLIPS:
            self._start(self._base_after_dig(), now, why)      # _start sees the dig and puts rummage_up first
        else:
            was, self.dig = self.dig, None
            self.family.dig_over(self, now, was, why)
            if self.pending is not None and self.pending[0] in DIG_ALL:
                self.pending = None

    def _base_after_dig(self):
        was, self.dig = self.dig, None
        try:
            return self._base_name() or self.idle_name
        finally:
            self.dig = was

    def _item_tick(self, now):
        """The find follows the arm: where the clip's frame says, or it is gone."""
        it = self.item
        if it is not None:
            if self.cur == it.get("clip") or self.cur in it.get("clips", ()):
                it["on"] = True
            elif it.get("carried") and self.carry is not None and not self.family.hidden:
                pass                           # on its way with it: a step between two of its clips does not lose it
            elif it.get("on") or self.family.hidden or now - it["t0"] > 8.0:      # its clip is over (or never came)
                it = self.item = None
        if it is not None and not it.get("on"):
            return
        entry = 0
        if it is not None:
            track = self.store.meta.get(self.cur, {}).get("item")
            if isinstance(track, list) and 0 <= self.last_idx < len(track):
                entry = track[self.last_idx]
        if it is None or not entry:
            if self.overlay is not None:
                self.overlay.hide()
            return
        if self.overlay is None:
            self.overlay = ItemOverlay(self)
        self.overlay.show(now, it, entry)

    def end_doze(self, now, why):
        """Startled awake (a frame set without doze_startle: straight up)."""
        if not self.dozing:
            return
        self.dozing = False
        if self.pending is not None and self.pending[0] in DOZE_CLIPS:
            self.pending = None
        self.family.nap_over(self, now, why)
        if why in ("clicked", "the cursor moved"):
            self.family.grow_play("startle", now)      # you woke it: that is playing with it
        shock = self._shot_name("doze_startle")
        if shock and self.cur in ("doze", "doze_in") and not self.dragging and self.fly is None:
            self._start(shock, now, "startled (%s)" % why)
        else:
            self._start(self._base_name() or self.idle_name, now, why)

    def _cancel_manual(self):
        if self.cur_until is not None:
            self.cur_until = 0.0
        if self.pending is not None and self.pending[1] is not None:
            self.pending = None

    # ----------------------------------------------------------- hold / outro
    def _hold_bounds(self, n):
        a, b = int(n * HOLD_RANGE[0]), int(n * HOLD_RANGE[1])
        if b - a < 2 or b >= n - 1:
            return None
        return a, b

    def _hold_period(self):
        """Frames after which the current hold repeats exactly, or None if it ping-pongs."""
        return HOLD_LOOP_FRAMES.get(self.cur)

    def _hold_frame(self, idx, n):
        hb = self._hold_bounds(n)
        if hb is None:
            return idx % n
        a, b = hb
        period = self._hold_period()
        if period:
            return idx if idx < a + period else a + (idx - a) % period
        if idx <= b:
            return idx                      # first pass: intro + hold
        span = b - a
        p = (idx - b) % (2 * span)
        return b - p if p <= span else a + (p - span)

    def _leave_hold(self, now, why):
        """End a hold through its own outro (forward from where it is, or rewind the intro)."""
        n = len(self.cur_frames)
        f = self.last_idx
        hb = self._hold_bounds(n)
        seq = None
        if hb is not None and 0 <= f < n:
            period = self._hold_period()
            if period and f >= hb[0]:          # same picture one period later: a shorter way out
                f += (hb[1] - f) // period * period
            seq = range(f - 1, -1, -1) if f < hb[0] else range(f + 1, n)
        if not seq:
            self._next(now, why)
            return
        self.cur_kind = KIND_ONESHOT      # the outro is never cut; requests queue
        self.cur_seq = seq
        self.cur_until = None
        self.t0 = now
        if self.debug:
            log("outro %s, %d frames (%s)" % (self.cur, len(seq), why))
        self._draw(seq[0])

    # ----------------------------------------------------------- per tick
    def _advance(self, now):
        n = len(self.cur_frames)
        idx = int((now - self.t0) * self.cur_fps)
        kind = self.cur_kind
        if kind == KIND_ONESHOT:
            seq = self.cur_seq
            if idx >= len(seq):
                self._next(now, "after " + self.cur)
                return
            self._draw(seq[idx])
            return
        if not self._wanted(now):
            if kind == KIND_HOLD:
                self._leave_hold(now, self.cur + " no longer wanted")
            elif (self.cur == "dangle" and self.cur_until is not None and self.pending is None
                  and not self.dragging and self._shot_name("land")):
                self._start(self._shot_name("land"), now, "manual dangle over")
            else:
                self._next(now, self.cur + " over")
            return
        if kind == KIND_HOLD:
            self._draw(self._hold_frame(idx, n))
            return
        if self.cur == "doze" and self.dozing and idx // n != self.loop_no and self._doze_end(now, n):
            return
        if self.cur in DIG_LOOP_CLIPS and self.dig is not None:
            # long enough?  Asked at the loop's first frame; digging with gusto after each stroke (three a loop, all
            # of them begin in the pose of frame 0, which is where the clips that follow begin)
            part = idx * (3 if self.cur == "rummage_fast" else 1) // n
            if part != self.dig.get("part", 0):
                self.dig["part"] = part
                if self._dig_end(now):
                    return
        if self.cur == self.idle_name and self._calm() and self._idle_life(now, idx, n):
            return
        self.loop_no = idx // n
        self._draw(idx % n)

    def _idle_life(self, now, idx, n):
        """Sleep / wander / idle extras while nothing else is going on. True = clip changed."""
        if now - self.last_activity >= self.sleep_after and self.family.may_sleep():
            self.sleeping = True
            log(self.tag + "fell asleep after %.0fs without interaction" % (now - self.last_activity))
            if self.slot == 0:
                self.family.big_fell_asleep(now)
            self._next(now, "sleepy")
            return True
        if self.family.nap is not None and self.family.nap["pet"] is self:
            return False                       # it has an eye on the cursor: no extras, no walks of its own
        if self.extra_wanted is None:
            quiet = self.slot != 0 and self.family.leader.busy
            if now >= self.next_wander:
                self.next_wander = now + random.uniform(*self.wander_range)
                if random.random() < WANDER_CHANCE and not quiet:
                    self.extra_wanted = WANDER
                    self.extra_deadline = now + EXTRA_SEAM_WAIT
            if self.extra_wanted is None and now >= self.next_extra:
                extras = [a for a in IDLE_EXTRAS if self.store.usable(a)]
                if extras and quiet and random.random() >= QUIET_EXTRA_CHANCE:
                    extras = None
                if (extras and not quiet and random.random() < self.family.opts["play_alone"] * (PLAY_ALONE_LIVELY if ACTIVITY == "lively" else 1.0)
                        and self.family.may_play_alone(self)):
                    self.extra_wanted = PLAY_ALONE
                    self.extra_deadline = now + EXTRA_SEAM_WAIT
                elif extras:
                    self.extra_wanted = random.choice(extras)
                    self.extra_deadline = now + EXTRA_SEAM_WAIT
                else:
                    self.next_extra = now + random.uniform(*self.extra_range)
        if self.extra_wanted is not None:
            # start on a seam: idle loop wrap, a frame identical to idle frame 0, or give up
            # waiting after EXTRA_SEAM_WAIT seconds
            frames = self.cur_frames
            if idx // n != self.loop_no or frames[idx % n] is frames[0] or now >= self.extra_deadline:
                name, self.extra_wanted = self.extra_wanted, None
                if name == WANDER:
                    if self._begin_wander(now, None):
                        self._next(now, "wander")
                        return True
                    return False
                if name == PLAY_ALONE:
                    return bool(self.family.play_item(self, None, now, "by itself", hand=False))
                self._start(name, now, "idle extra")
                return True
        return False

    def _update_modes(self, now):
        if self.working:
            for session, turn in list(self.working.items()):
                if "think_at" in turn and now >= turn["think_at"]:
                    del turn["think_at"]
                    turn["clip"] = "think"
                    self.busy_clip = max(self.working.values(), key=lambda t: t["seen"])["clip"]
                if now >= turn["until"]:
                    running = (turn["clip"] in TOOL_CLIPS.values() and "think_at" not in turn
                               and session not in self.turn_over and now - turn["seen"] < BUSY_TOOL_TIMEOUT
                               and not self.family.talks.get(session, {}).get("wait"))   # a permission asked
                    # for before its tool runs is not a tool at work: you may leave it as long as you like
                    if running:                # its tool is still on: a long command, not a turn gone quiet
                        if not turn.get("long_tool"):
                            turn["long_tool"] = True
                            log("busy: a tool still running after %.0fs quiet, at work on" % (now - turn["seen"]))
                        turn["until"] = now + 60.0
                        continue
                    log("busy timed out after %.0fs" % (now - turn["since"]))
                    self._end_busy(now, session)
        if self.attention_until and now >= self.attention_until:
            self.attention_until = 0.0
            self._activity(now)
            if self.debug:
                log("attention timed out")
        if now >= self.next_wander and (self.busy or self.attention_until or self.sleeping
                                        or self.dragging):
            self.next_wander = now + random.uniform(*self.wander_range)

    # ----------------------------------------------------------- wander
    def _begin_wander(self, now, duration):
        by_hand = duration is not None         # "walk" from the menu or clawd do; None: a walk of its own
        self._finish_glide()
        lo, hi = self._feet_limits(self._work_area(self.fx, self.fy))[:2]
        if duration is None and self.area is not None:   # a walk of its own: near its place (from away: back to it)
            reach = WANDER_AREA * self._target_px()
            alo, ahi = max(lo, self.area - reach), min(hi, self.area + reach)
            if alo <= ahi:
                lo, hi = alo, ahi
        lo, hi = self.family.walk_limits(self, lo, hi)
        if hi - lo < 10:
            return False
        s = self.scale
        speed = WANDER_SPEED * s
        x = clamp(float(self.fx), lo, hi)
        room = {1: hi - x, -1: x - lo}
        if duration is None:
            dist = random.uniform(*WANDER_DIST) * s
            direction = random.choice((-1, 1))
            if room[direction] < WANDER_DIST[0] * s:
                direction = -direction
            duration = dist / speed             # may reach an edge: it turns around there
        else:
            direction = 1 if room[1] >= room[-1] else -1
        self.wander = {"x": x, "dir": direction, "speed": speed, "lo": lo, "hi": hi, "gait": WANDER_SPEED / WALK_CLIP_SPEED,
                       "left": duration, "last": None, "bump": None, "hand": by_hand}
        if self.debug:
            log("wander %s for %.1fs at %.0f px/s (x %d, range %d..%d)"
                % ("right" if direction > 0 else "left", duration, speed, x, lo, hi))
        return True

    def _walk_to(self, x, y, now, secs, pace=COMBO_SPEED):
        """Walk to a place, also at a slant, in at most secs.  -> False if it is already there (or up on another one)."""
        if self.hop is not None or self.perch is not None:
            return False
        self._finish_glide()
        xlo, xhi, ylo, yhi = self._feet_limits(self._work_area(x, y))
        x, y = clamp(x, xlo, xhi), clamp(y, ylo, yhi)
        dx, dy = x - self.fx, y - self.fy
        dist = math.hypot(dx, dy)
        if dist < 3:
            return False
        dur = dist / max(WALK_CLIP_SPEED * pace * self.scale, dist / secs)
        gait = clamp(dist / dur / (WALK_CLIP_SPEED * self.scale), *GAIT_RANGE)
        fps = self.store.fps_of("walk_right" if dx >= 0 else "walk_left") if self.store.usable("walk_right") else self.store.fps
        steps = max(1, int(round(dur * fps * gait / WALK_SEAM)))   # a whole number of steps, so a turn can join the end
        gait = steps * WALK_SEAM / (dur * fps)
        self.wander = {"x": float(self.fx), "dir": 1 if dx >= 0 else -1, "speed": abs(dx) / dur, "lo": -1e9, "hi": 1e9,
                       "left": dur, "last": None, "bump": None, "dur": dur, "x1": x, "y0": self.fy, "y1": y, "gait": gait}
        if self.cur == self._walk_clip() and self.cur_kind == KIND_LOOP:   # walking already: same picture, new pace
            fps = self.store.fps_of(self.cur) * gait
            self.t0 = now - (now - self.t0) * self.cur_fps / fps
            self.cur_fps = fps
        if self.debug:
            log("%swalk to (%d, %d) in %.1fs" % (self.tag, x, y, dur))
        return True

    def _wander_step(self, now):
        w = self.wander
        if self.dragging or self.cur_kind != KIND_LOOP or self.cur != self._walk_clip():
            return
        if w["last"] is None:
            w["last"] = now
            return
        dt = min(now - w["last"], 0.25)
        w["last"] = now
        step = int((now - self.t0) * self.cur_fps) // WALK_SEAM
        if w["bump"] is not None:               # at the edge: tread until the legs can join the turn
            if step != w["bump"]:
                self._turn_around(now)
            return
        x = w["x"] + w["dir"] * w["speed"] * dt
        w["left"] -= dt
        at_edge = x <= w["lo"] if w["dir"] < 0 else x >= w["hi"]
        if at_edge:
            x = w["lo"] if w["dir"] < 0 else w["hi"]
        w["x"] = x
        fy = self.fy
        if "y1" in w:                           # a walk to a place
            fy = int(round(w["y1"] + (w["y0"] - w["y1"]) * max(w["left"], 0.0) / w["dur"]))
        self._move_feet(int(round(x)), fy)
        if w["left"] <= 0.0:
            if "y1" in w:
                self._move_feet(w["x1"], w["y1"])
            self.wander = None
            self._save_state()
            if self.debug:
                log("wander done at x=%d" % self.fx)
        elif at_edge:
            w["bump"] = step
            if self.debug:
                log("wander reached the edge at x=%d" % self.fx)

    def _turn_around(self, now):
        w = self.wander
        w["bump"] = None
        w["dir"] = -w["dir"]
        name = "turn_right" if w["dir"] > 0 else "turn_left"
        if self.store.usable(name):             # afterwards _start_base starts the new walk clip
            self._start(name, now, "edge")

    # ----------------------------------------------------------- hop (叠罗汉)
    def _start_hop(self, x, y, now, perch=None, why="hop", ground=None, arc=None, flip=False, roll=False):
        """Jump to (x, y): onto perch's head, or down when perch is None.  The clip starts now (a combo
        waits for calm first; coming down when a tower breaks up cuts what plays), as the flight goes
        by its clock.  arc: px above the straight line at the top (跳山羊: over another one's head)."""
        self._finish_glide()
        self.wander = None
        name = self._shot_name("stack_hop")
        off, land = HOP_TAKEOFF, HOP_LAND
        up = perch is not None
        if (flip or roll) and not up:          # 小插曲: a whole turn in the air (down from the tower with a flip; over the
            way = "right" if x >= self.fx else "left"     # other one head over heels, dizzy where it lands), a longer flight
            turn = self._shot_name(("slip_roll_" if roll else "stack_flip_") + way)
            if turn:
                name, off, land = (turn, ROLL_OFF, ROLL_LAND) if roll else (turn, FLIP_OFF, FLIP_LAND)
                far = int(round((ROLL_FAR if roll else FLIP_FAR) * self._target_px()))
                x = self._clamped(int(x) + (far if way == "right" else -far), int(y))[0]
        if arc is not None and not up:
            self.ground = (int(x), int(y))     # over another one: if it must come down at once, it lands there
        if not name:
            if up and self.perch is None:
                self.ground = ground if ground is not None else (self.fx, self.fy)
            self.perch = perch if up else self.perch
            self._move_feet(x, y)
            if not up:
                self.perch = self.ground = None
            return
        if up:
            if ground is not None:
                self.ground = ground
            elif self.perch is None:
                self.ground = (self.fx, self.fy)
            self.perch = perch
        self.hop = {"x0": self.fx, "y0": self.fy, "x1": int(x), "y1": int(y), "up": up,
                    "arc": arc if arc is not None else HOP_ARC * self._target_px() + HOP_ARC_UP * max(0, self.fy - y),
                    "down_after": False, "clip": name, "off": off, "land": land}
        self.family.depth_dirty = True
        if self.debug:
            log("%shop %s to (%d, %d)" % (self.tag, "up onto pet%d" % perch.slot if up else "down", x, y))
        self._start(name, now, why)

    def _hop_step(self, now):
        h = self.hop
        if self.dragging:
            self.hop = None
            return
        if self.cur != h["clip"]:              # cut: land at once
            u = 1.0
        else:
            u = clamp((now - self.t0 - h["off"]) / (h["land"] - h["off"]), 0.0, 1.0)
        x = h["x0"] + (h["x1"] - h["x0"]) * u
        y = h["y0"] + (h["y1"] - h["y0"]) * u - h["arc"] * 4.0 * u * (1.0 - u)
        self._move_feet(int(round(x)), int(round(y)))
        if u < 1.0:
            return
        self.hop = None
        if self.debug:
            log("%slanded at (%d, %d)" % (self.tag, self.fx, self.fy))
        if not h["up"]:                        # down on the floor
            self.perch = self.ground = None
            self.family.depth_dirty = True
            self._save_state()
        elif h["down_after"] or self.perch is None:   # the tower broke up while it was in the air
            self.come_down(now, quick=True)

    def come_down(self, now, instant=False, quick=False, flip=False):
        """Off the one below, back to where it jumped up from.  quick: no crouch first (nothing to stand on)."""
        if instant:
            self.hop = None
        if self.hop is not None:
            if self.hop["up"]:
                self.hop["down_after"] = True  # lands first, then comes down
            elif quick and self.cur == "stack_hop" and now - self.t0 < HOP_TAKEOFF:
                self.t0 = now - HOP_TAKEOFF
            return
        if self.perch is None and self.ground is None:
            return
        gx, gy = self.ground if self.ground is not None else (self.fx, self.fy)
        gx, gy = self._clamped(gx, gy)
        if instant or self.dragging:
            if not self.dragging:
                self._move_feet(gx, gy)
            self.perch = self.ground = None
            self.family.depth_dirty = True
            return
        self.hop = None
        self._start_hop(gx, gy, now, why="down", flip=flip and not quick)
        if self.hop is None:                   # no clip for it
            self.perch = self.ground = None
        elif quick:
            self.t0 = now - HOP_TAKEOFF

    # ----------------------------------------------------------- tokens
    def _activity(self, now):
        self.family.touch(self, now)

    def _do_react(self, now):
        name, self.react = self.react[0], None
        self.family.took(self, "a reaction", now, R_REACT)
        self._cancel_manual()
        self.wander = None
        self.request(self._shot_name(name), now, "reaction")

    def _wake(self, now, plays):
        if not self.sleeping:
            return
        self.sleeping = False
        if self.debug:
            log("woke up")
        if not plays:
            self.request(self._shot_name("surprised"), now, "woke up")
        else:                                  # not straight from the crouch into what comes next
            self.request(self._shot_name("wake_up"), now, "woke up")

    def _set_busy(self, now, clip, session):
        if self.dozing and self.doze_manual:   # a doze by hand while at work: the next work event wakes it
            self.end_doze(now, "work")
        if self.dig is not None:               # digging by hand while at work: the same
            self.end_dig(now, "work")
        turn = self.working.get(session)
        if turn is None:
            if not self.working:
                self.fail_times = []
            turn = self.working[session] = {"since": now, "clip": "think", "was_busy": False}
        turn["until"] = now + (BACKGROUND_BUSY_SECS if session in self.turn_over
                               else self.family.opts.get("busy_timeout", BUSY_TIMEOUT))
        turn["seen"] = now
        turn["clip"] = clip
        turn.pop("think_at", None)
        self.busy = True
        self.busy_clip = clip

    def at_work(self, session, turn, now):
        """干活时间: is this turn at work now?  Not once it is over (a helper's tools after its stop), not while it
        waits for you (its circle orange: a question, a permission), and heard from in WORK_QUIET, or a tool of it
        still running (a long command says nothing meanwhile; as the busy timeout sees it)."""
        if session in self.turn_over or self.family.talks.get(session, {}).get("wait"):
            return False
        if now - turn["seen"] <= WORK_QUIET:
            return True
        return turn["clip"] in TOOL_CLIPS.values() and "think_at" not in turn and now - turn["seen"] < BUSY_TOOL_TIMEOUT

    def _end_busy(self, now, session):
        """Only this session.  The pet goes on with what another one is doing, if any."""
        self.working.pop(session, None)
        if self.working:
            self.busy_clip = max(self.working.values(), key=lambda t: t["seen"])["clip"]
        else:
            self.busy = False
            self._activity(now)

    def _on_token(self, tok, now, why="event", session=""):
        if self.debug:
            log("%s %r" % (why, tok))
        if tok == "quit":
            self.family.quit("quit event")
            return
        if tok in ("hide", "show"):
            self.family.set_hidden(tok == "hide", now, "%s %s" % (why, tok))
            return
        if tok.startswith("size:") or tok.startswith("size="):
            try:
                pct = float(tok[5:].rstrip("%"))
            except ValueError:
                return
            if not math.isfinite(pct):
                return
            self._activity(now)
            self.attention_until = 0.0
            self._wake(now, plays=False)
            self.family.set_scale(clamp(pct, 50.0, 300.0) / 100.0, now, why)
            return
        if tok.startswith("family:"):
            try:
                n = int(tok[7:])
            except ValueError:
                return
            self._activity(now)
            self.family.set_count(n, now)
            return
        if tok.startswith("activity:"):
            self.family.set_activity(tok[9:], now, why)
            return
        if tok.startswith("sign:"):            # the 图鉴: a look of the signs, one that the level has brought
            self.family.set_look(tok[5:], now)
            return
        if tok.startswith("lang:"):
            if set_lang(tok[5:]):
                self.family.save_state()
                if self.family.tray is not None:
                    self.family.tray.update()
            return
        if tok.startswith("combo:"):
            if tok[6:] in COMBOS:
                self.family.touch(self, now, wake=False)
                self.family.start_combo(tok[6:], now, manual=True)
            return
        if tok.startswith("dismiss:"):         # test only: the menu's item, which a test cannot click
            if self.debug:
                for pet in list(self.family.pets):
                    if tok[8:] == str(pet.slot):
                        self.family.dismiss(pet, now)
            return
        if tok == "dump":
            if self.dump_dir:
                self._dump("event")
            return
        if tok == "rummage" or (tok.startswith("rummage:") and self.debug):      # clawd do rummage; "rummage:<slot>" for tests
            who = next((q for q in self.family.pets if tok[8:] == str(q.slot)), self)
            self._activity(now)
            self.family.dig_by_hand(who, now, why)
            return
        if tok == "play" or tok.startswith("play:"):     # 把玩: clawd do 把玩 [宝贝], the album; "play:<treasure>:<slot>" for tests
            parts = tok.split(":")
            who = next((q for q in self.family.pets if len(parts) > 2 and parts[2] == str(q.slot)), None) if self.debug else None
            self._activity(now)
            self.family.play_by_hand(who, parts[1] if len(parts) > 1 and parts[1] else None, now, why)
            return
        if tok in SEMANTIC:
            self._activity(now)
            self._semantic(tok, now, session)
        elif (tok in self.store.meta or tok in SHOT_FALLBACK) and not internal(tok):
            self._activity(now)
            self._manual(tok, now, why)
        # anything else: ignored

    def _semantic(self, tok, now, session=""):
        self._cancel_manual()
        self.wander = None
        # a sub-agent says nothing about a question, and neither does another session
        if tok not in ("attention", "agent", "agent_done") and session == self.attention_session:
            self.attention_until = 0.0
        if tok == "listen":
            turn = self.working.get(session)
            if turn is not None and session in self.turn_over:
                turn["since"] = now            # still busy from a sub-agent: a new turn all the same
                turn["grow_since"] = now
                for k in ("tools", "failed", "fixed", "work", "tooled", "dug"):
                    turn.pop(k, None)
            # a message while it works (插话, steering; or one after an Esc not seen yet): the same turn, for 养成 too:
            # its XP and its chance to dig by hand once, at its end (round 9, the user: a whole turn counts once)
            self.turn_over.discard(session)
        if tok == "think" and self.working.get(session, {}).get("clip") in TOOL_CLIPS.values():
            turn = self.working[session]       # the tool is over; its clip stays a moment
            linger = turn.get("think_at")      # already over: this is a tool not shown (an agent, a search
            self._set_busy(now, turn["clip"], session)   # for tools ...), it must not keep the clip longer
            turn["think_at"] = linger if linger is not None else now + TOOL_LINGER_SECS
            self._wake(now, plays=True)
        elif tok in ("listen", "think"):
            self._set_busy(now, tok, session)
            self._wake(now, plays=True)
        elif tok in TOOL_CLIPS:
            self._set_busy(now, TOOL_CLIPS[tok], session)
            self._wake(now, plays=True)
        elif tok in ("agent", "agent_done"):    # Claude Code sends extra agent_done words: see Family.grow_agent
            self._wake(now, plays=True)
            if self.pending is None:           # never in place of a queued turn-end reaction
                self.request(self._shot_name("work_agent" if tok == "agent" else "nod"), now, tok)
        elif tok == "compact":
            turn = self.working.get(session)
            if turn is None or turn["clip"] != "work_compact":
                was_busy = turn is not None
            else:
                was_busy = turn["was_busy"]
            self._set_busy(now, "work_compact", session)
            turn = self.working[session]
            turn["was_busy"] = was_busy
            turn["until"] = now + self.family.opts.get("busy_timeout", BUSY_TIMEOUT)
            self._wake(now, plays=True)
        elif tok == "compact_end":
            turn = self.working.get(session)
            if turn is not None and turn["clip"] == "work_compact":
                if turn["was_busy"]:
                    self._set_busy(now, "think", session)
                else:
                    self._end_busy(now, session)
        elif tok == "fail":
            self._set_busy(now, "think", session)
            self._wake(now, plays=True)
            self.fail_times = [t for t in self.fail_times if now - t <= FAIL_WINDOW] + [now]
            name = "surprised"
            if len(self.fail_times) >= FAIL_MIN and now - self.last_confused >= CONFUSED_COOLDOWN:
                self.last_confused = now
                name = "confused"
            self.reacted = name
            self.request(self._shot_name(name), now, "%d fails" % len(self.fail_times))
        elif tok == "stop":
            name = self.reacted = FINISH_REACTIONS[0][1]
            turn = self.working.get(session)
            self.turn_secs = None              # for the sign: how long it took
            self.family.grow_turn(turn, False, now)
            if turn is not None:
                dur = self.turn_secs = now - turn["since"]
                name = next(n for limit, n in FINISH_REACTIONS if dur < limit)
                self.reacted = name            # the thumb may be cut off here, the length of the turn stays
                if name == "thumbs_up" and self._thumb_cut_off():
                    name = FINISH_REACTIONS[0][1]
                if self.debug:
                    log("turn took %.1fs -> %s" % (dur, name))
            self.turn_over.add(session)
            self._end_busy(now, session)
            self._wake(now, plays=True)
            self.request(self._shot_name(name), now, "stop")
        elif tok == "stopfail":
            turn = self.working.get(session)
            if turn is not None:
                self.family.grow_turn(turn, True, now)
            self.turn_over.add(session)
            self._end_busy(now, session)
            self._wake(now, plays=True)
            self.request(self._shot_name("shrug_sweat"), now, "stopfail")
        elif tok == "attention":
            if not self.attention_until:
                self.att_i = 0
            self.attention_until = now + self.family.opts.get("attention_timeout", ATTENTION_TIMEOUT)
            self.attention_session = session
            self._wake(now, plays=True)
        elif tok == "hello":
            self._wake(now, plays=True)
            self.request(self._shot_name("wave"), now, "hello")
        elif tok == "bye":
            self.turn_over.discard(session)
            self._end_busy(now, session)
            self._wake(now, plays=True)
            self.request(self._shot_name("wave"), now, "bye")
        self._grow_count(tok, now, session)

    def _grow_count(self, tok, now, session):
        """养成: a tool ended (well or not) or a helper went out counts for the turn; a tool that ends well after
        one that failed is a fix (once a turn); a helper back is XP."""
        if tok in ("web", "compact", "agent"):
            self.family.turn_marks.add(tok)      # what a find of this turn may turn into (DIG_SPECIAL)
        if tok == "agent_done":
            self.family.grow_agent(now)
        turn = self.working.get(session)
        if turn is not None and (tok in TOOL_CLIPS or tok in ("think", "fail", "agent")) and not turn.get("tooled"):
            self.family.work_first_tool(turn, now, session not in self.turn_over)   # a tool begun: its 干活时间 counts for the digs by hand
        if tok not in ("think", "fail", "agent") or turn is None:
            return
        turn["tools"] = turn.get("tools", 0) + 1
        if tok == "fail":
            turn["failed"] = True
        elif tok == "think" and turn.get("failed") and not turn.get("fixed"):
            turn["fixed"] = True
            self.family.grow_fix(now)

    def _manual(self, name, now, why):
        """An action asked for by name (event token or menu)."""
        self.family.took(self, "action by hand", now)
        if self.in_combo:
            self.family.cancel_combo("action by hand", now)
        self._cancel_manual()
        self.attention_until = 0.0
        if name != "walk":
            self.wander = None
        self._wake(now, plays=name != self.idle_name)
        if name == self.idle_name:
            return
        if name == "doze" and all(self.store.usable(c) for c in DOZE_CLIPS):
            if self.dragging or self.fly is not None:
                return                         # held or in the air: not now
            self.family.nap_over(self, now, "doze by hand")
            if not self.dozing:
                self.dozing = True
                self.request("doze_in", now, why)
            self.doze_manual = True
            self.doze_from = now
            self.doze_alone = None
            self.doze_sleep = False
            return
        if name == "walk":
            if self.wander is None and not self.dragging and self._begin_wander(now, MANUAL_LOOP_SECS):
                if self.cur_kind == KIND_LOOP:
                    self._next(now, why)
            return
        if not self.store.usable(name):
            self.hand_clip = self._shot_name(name)
            self.request(self.hand_clip, now, why + " (fallback)")
            return
        self.hand_clip = name
        kind = self._kind(name)
        if kind == KIND_LOOP:
            self.request(name, now, why, until=now + MANUAL_LOOP_SECS)
        elif kind == KIND_HOLD:
            self.request(name, now, why, until=now + MANUAL_HOLD_SECS)
        else:
            self.request(name, now, why)

    # ----------------------------------------------------------- size
    def set_scale(self, scale, now, why):
        scale = round(clamp(float(scale), SCALE_MIN, SCALE_MAX), 3)
        if abs(scale - 1.0) < SCALE_SNAP:
            scale = 1.0
        if scale == self.scale:
            return
        self._finish_glide()
        self.wander = None                     # its limits were for the old size
        edges = self._flush_edges()
        old, self.scale = self.scale, scale
        target = self._target_px()
        if self.render is not None and self.render["px"] != target:
            self._kill_render("superseded by %d%%" % round(scale * 100))
        new_store = self._source_store(target)
        if new_store is not None:
            self._use_store(new_store, now, "size %d%%" % round(scale * 100))
        else:
            self._reconfigure()
            self.win_pos = self._win_xy()
            self._redraw(pos=True)
        self._refit(edges)
        self.size_due = now + RERENDER_DELAY
        log("size %d%% -> %d%% (%s), display factor %.3f, window %dx%d"
            % (round(old * 100), round(scale * 100), why, self.disp, self.dw, self.dh))

    def _target_px(self):
        return int(round(self.base_body_px * self.scale))

    def _source_store(self, target):
        """The frame set to change to for a body of target px, None = stay on the current one.
        A native set stays; else the base set up to its size and frames_hi above it, so that the
        display factor stays <= 1.  Without frames_hi: stay, and stretch as a last resort."""
        st = self.store
        if abs(target / float(st.body_px) - 1.0) < DISP_SNAP:
            return None
        if target <= self.base_body_px:
            return try_store(self.base_dir) if st.dir != self.base_dir else None
        if st.dir == self.hi_dir or self.scaler_broken:
            return None
        if os.path.isfile(os.path.join(self.hi_dir, "manifest.json")):
            hi = try_store(self.hi_dir)
            if hi is not None and hi.body_px >= target:
                return hi
        return None

    def _use_store(self, store, now, why):
        old_store, old_idle = self.store, self.idle_name
        self.store = store
        if store.dir == self.base_dir:
            self.base_body_px = store.body_px
        self.idle_name = store.idle_name
        try:
            self._reconfigure()
        except Exception:                      # e.g. no DIB: the old buffer must keep matching the set
            self.store, self.idle_name = old_store, old_idle
            raise
        store = self.store
        self.win_pos = self._win_xy()
        fr = store.frames(self.cur) if self.cur else None
        if fr:
            self.cur_frames = fr               # same clip, same timing; _draw clamps indices
            fps = store.fps_of(self.cur)
            if self.wander is not None and self.cur == self._walk_clip():
                fps *= self.wander.get("gait", 1.0)
            self.t0 = now - (now - self.t0) * self.cur_fps / fps
            self.cur_fps = fps
        else:
            self._start(self.idle_name, now, "frame set swap", draw=False)
        self._redraw(pos=True)
        log("frames: %s %dx%d body %dpx (%s), display factor %.3f, window %dx%d"
            % (store.dir, store.width, store.height, store.body_px, why, self.disp, self.dw, self.dh))

    def _size_settled(self, now):
        self.size_due = None
        self._save_state()
        if self.scale == 1.0 or (self.store.dir == self.hi_dir and self.disp == 1.0):
            why = "size %d%% is native" % round(self.scale * 100)
            self._kill_render(why)
            if self.store.dir != os.path.abspath(self.custom_dir):
                remove_custom_sets(self.custom_dir, why)
            return
        target = self._target_px()
        if self.disp == 1.0 and (self.store.body_px == target or not self.scaler_broken):
            return                                   # already shown 1:1
        if self.render is not None and self.render["px"] == target:
            return
        if self._reuse_custom(target, now):
            return
        if target in self.render_failed:
            return
        src = self._scale_source(target)
        if src is None:
            if not self.render_unavailable_logged:
                self.render_unavailable_logged = True
                log("re-render unavailable (no %s, or no set of %dpx or more); keeping live scaling"
                    % (SCALE_SCRIPT, target))
            return
        if self.family.rendering(self):              # one at a time
            self.size_due = now + 0.5
            return
        self._start_render(target, src, now)

    def _scale_source(self, px):
        """The set a native one of px px is scaled down from: frames at or below their size, frames_hi above; None
        if there is none (or no clawd_scale.py)."""
        if not os.path.isfile(SCALE_SCRIPT):
            return None
        if px <= self.base_body_px:
            return self.base_dir
        try:
            if FrameStore(self.hi_dir).body_px >= px:
                return self.hi_dir
        except Exception:
            pass
        return None

    def _reuse_custom(self, px, now):
        """frames_custom may still hold this very size from before a quick change back and forth."""
        if not os.path.isfile(os.path.join(self.custom_dir, "manifest.json")):
            return False
        try:
            if FrameStore(self.custom_dir).body_px != px:
                return False
            if not has_all_actions(FrameStore(self.custom_dir), self.base_dir):
                return False
        except Exception:
            return False
        store = try_store(self.custom_dir)
        if store is None:
            return False
        self._use_store(store, now, "already rendered")
        return True

    def _start_render(self, px, src, now):
        import subprocess
        self._kill_render("new request")
        exe = os.path.join(os.path.dirname(sys.executable), "python.exe")    # its output goes to render.log
        cmd = [exe if os.path.isfile(exe) else sys.executable, "-I", SCALE_SCRIPT, "--src", src, "--body-px", str(px),
               "--out", self.custom_dir]
        logf = None
        try:
            logf = open(self.render_log, "wb")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            if MAC:
                proc, job = start_render_mac(cmd, logf, env), None
            else:
                proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                                        cwd=HERE, env=env,
                                        creationflags=CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
                                        | CREATE_SUSPENDED)
                job = run_in_job(proc)
        except Exception:
            log_exc("starting re-render")
            if logf:
                logf.close()
            self.render_failed.add(px)
            return
        self.render = {"proc": proc, "job": job, "px": px, "t": now, "logf": logf}
        log("re-render %dpx started (pid %d)" % (px, proc.pid))

    def _kill_render(self, why):
        job, self.render = self.render, None
        if job is None:
            return
        t0 = time.perf_counter()
        try:
            running = job["proc"].poll() is None
            if MAC:
                if running:
                    stop_render_mac(job["proc"])
            elif job["job"]:
                TerminateJobObject(job["job"], 1)
            elif running:                            # prerender's own job takes its workers along
                job["proc"].kill()
            job["proc"].wait(5)
            while (job["job"] and job_active_processes(job["job"])
                   and time.perf_counter() - t0 < 2.0):
                time.sleep(0.005)
            if running:
                log("re-render %dpx stopped in %.0f ms (%s)"
                    % (job["px"], (time.perf_counter() - t0) * 1000.0, why))
        except Exception:
            log_exc("stopping re-render")
        finally:
            self._close_render(job)
        for _ in range(25):                          # a killed process can hold a file a little longer
            remove_stale_render_dirs(self.custom_dir)
            if not (os.path.exists(self.custom_dir + ".tmp") or os.path.exists(self.custom_dir + ".old")):
                break
            time.sleep(0.02)

    @staticmethod
    def _close_render(job):
        try:
            job["logf"].close()
        except Exception:
            pass
        if job["job"]:
            CloseHandle(job["job"])

    def _poll_render(self, now):
        job = self.render
        rc = job["proc"].poll()
        if rc is None:
            if now - job["t"] > RENDER_TIMEOUT:
                self.render_failed.add(job["px"])
                self._kill_render("timeout")
            return
        self.render = None
        self._close_render(job)
        remove_stale_render_dirs(self.custom_dir)
        px = job["px"]
        took = now - job["t"]
        if rc != 0:
            self.render_failed.add(px)
            tail = ""
            try:
                with open(self.render_log, "rb") as f:
                    tail = f.read()[-600:].decode("utf-8", "replace").strip()
            except OSError:
                pass
            log("re-render %dpx failed (exit %s after %.0fs); keeping live scaling\n%s"
                % (px, rc, took, tail))
            return
        store = try_store(self.custom_dir)
        if store is None or store.body_px != px:
            self.render_failed.add(px)
            log("re-render %dpx produced no usable set; keeping live scaling" % px)
            return
        if self._target_px() != px or self.scale == 1.0:
            log("re-render %dpx finished after %.0fs but the size changed meanwhile" % (px, took))
            return
        log("re-render %dpx finished after %.0fs" % (px, took))
        self._use_store(store, now, "re-rendered")

    def _watch_frames(self, now):
        """Hot-swap if the active frame set was regenerated on disk."""
        try:
            st = os.stat(os.path.join(self.store.dir, "manifest.json"))
        except OSError:
            return                                  # mid-swap: look again later
        if (st.st_mtime_ns, st.st_size) == self.store.sig:
            return
        store = try_store(self.store.dir)
        if store is not None:
            self._use_store(store, now, "set changed on disk")

    # ----------------------------------------------------------- mouse
    def _lp_screen(self, lparam):
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        return self.win_pos[0] + x, self.win_pos[1] + y

    @staticmethod
    def _cursor():
        pt = POINT()
        GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    @staticmethod
    def _left_button_down():
        vk = VK_RBUTTON if GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON
        return bool(GetAsyncKeyState(vk) & 0x8000)

    def _on_lbutton_down(self, lparam):
        now = time.perf_counter()
        self.family.took(self, "your hand", now)
        self._activity(now)
        self.glide = None                      # grabbed mid-glide: stays where it is
        self.caught = self.fly is not None     # caught in the air
        self.fly = None
        self.trail = []
        self.press = self._lp_screen(lparam)
        self.grab = (self.press[0] - self.fx, self.press[1] - self.fy)
        self.press_consumed = False
        SetCapture(self.hwnd)
        if self.sleeping:
            self._wake(now, plays=False)
            self.press_consumed = True
        if self.dozing:
            self.end_doze(now, "clicked")
            self.press_consumed = True
        if self.attention_until:
            self.attention_until = 0.0
            self.press_consumed = True
            if self.debug:
                log("attention ended by click")

    def _on_mouse_move(self, lparam):
        now = time.perf_counter()
        self.family.touch(self, now, wake=False)   # the mouse passing by wakes no one, as it does not wake this one
        if self.press is None:
            self._on_hover(now)
            return
        x, y = self._lp_screen(lparam)
        if not self.dragging:
            if abs(x - self.press[0]) <= DRAG_THRESHOLD and abs(y - self.press[1]) <= DRAG_THRESHOLD:
                return
            self._begin_drag(now)
        self._drag_to(x, y)

    def _begin_drag(self, now):
        if self.in_combo or (self.slot == 0 and self.family.combo is not None):
            self.family.cancel_combo("dragged", now)
        self.family.about_taken(self, now, "picked up")
        for p in self.family.pets:             # the ground under them is gone: no crouch first
            if p.perch is self:
                p.come_down(now, quick=True)
        self.home = self.return_at = None
        self.returning = False
        self.hop = None
        self.perch = self.ground = None        # taken off the tower: the user puts it down where it likes
        self.carry = None
        self.family.depth_dirty = True
        self.dragging = True
        self.caught = False
        self.click_due = None
        self.click_burst = 0
        self.wander = None
        self.extra_wanted = None
        self._cancel_manual()
        SetTimer(self.hwnd, TIMER_DRAG, DRAG_POLL_MS, None)
        if self.store.usable("dangle"):
            self._start("dangle", now, "drag")
        else:
            self._start(self._shot_name("surprised") or self.idle_name, now, "drag (no dangle)")

    def _end_drag(self, now, why):
        if not self.dragging:
            return
        self.dragging = False
        self.family.depth_dirty = True
        KillTimer(self.hwnd, TIMER_DRAG)
        self._activity(now)
        throw = self._throw_speed()
        self.trail = []
        if throw is not None:
            self._start_flight(now, throw[0], throw[1], "thrown (%s)" % why)
            self.family.thrown(self, now)
            self.family.grow_play("throw", now)
            return
        self.family.grow_play("drag", now)
        self._snap_after_drop(now)
        self.area = self.glide[2] if self.glide is not None else self.fx   # it lives here now
        self._save_state()
        land = self._shot_name("land")
        if land:
            self._start(land, now, "dropped (%s)" % why)
        else:
            self._next(now, "dropped (%s)" % why)
        self.family.dropped(self, now)

    def _release(self):
        self.releasing = True
        try:
            ReleaseCapture()
        finally:
            self.releasing = False

    def _on_lbutton_up(self, lparam):
        if self.press is None:
            return
        now = time.perf_counter()
        if self.dragging:
            self._drag_to(*self._lp_screen(lparam))
        self.press = None
        self._release()
        if self.dragging:
            self._end_drag(now, "release")
        elif self.caught:                      # caught in the air and let go: it falls on
            self.caught = False
            self._start_flight(now, 0.0, 0.0, "let go in the air")
        elif not self.press_consumed:
            self._register_click(now)

    def _on_drag_timer(self):
        """Fallback only: if we lost the capture, follow the cursor and watch the button."""
        if not self.dragging:
            KillTimer(self.hwnd, TIMER_DRAG)
            return
        if GetCapture() == self.hwnd:
            return
        self._drag_to(*self._cursor())
        if not self._left_button_down():
            self.press = None
            self._end_drag(time.perf_counter(), "button up (poll)")

    def _on_capture_changed(self, new_owner):
        if self.releasing or new_owner == self.hwnd:
            return
        if self.dragging:
            if not self._left_button_down():
                self.press = None
                self._end_drag(time.perf_counter(), "capture lost")
            # else: the drag timer keeps following the cursor
        else:
            self.press = None

    def _register_click(self, now):
        self.click_times = [t for t in self.click_times if now - t <= SHY_WINDOW]
        self.click_times.append(now)
        if len(self.click_times) >= SHY_CLICKS:
            self.click_times = []
            self.click_burst = 0
            self.click_due = None
            self._click_action("shy", now, "%d clicks" % SHY_CLICKS)
            return
        self.click_burst = self.click_burst + 1 if now - self.last_click_t <= self.dbl_time else 1
        self.last_click_t = now
        self.click_due = now + self.dbl_time

    def _resolve_clicks(self, now):
        burst, self.click_burst, self.click_due = self.click_burst, 0, None
        if burst >= 2:
            self._click_action(DOUBLE_CLICK_ACTION, now, "double-click")
        elif burst == 1:
            choices = [a for a in CLICK_ACTIONS if self.store.usable(a)]
            if choices:
                self._click_action(random.choice(choices), now, "click")

    def _click_action(self, name, now, why):
        self.family.grow_play("click", now)
        if self.family.digging(self):          # a click while it digs is a hand with the digging: better luck, and it digs on
            if self.dig is not None and not self.dig.get("helped"):
                self.dig["helped"] = True
                log("dig: %shelped by a click" % (self.tag or "pet0 "))
                self.dig_spur(now)
            return
        combo = self.family.combo
        if self.in_combo and combo is not None and combo["name"] == "stack":
            self.family.cancel_combo("clicked", now)   # a poke and the tower comes down
        self._cancel_manual()
        self.wander = None
        self.request(self._shot_name(name), now, why)

    def _on_hover(self, now):
        if self.hovering:
            return
        self.hovering = True
        tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE, self.hwnd, 0)
        TrackMouseEvent(ctypes.byref(tme))
        if self._calm() and now - self.last_hover >= HOVER_COOLDOWN:
            name = self._shot_name("look_at_viewer")
            if name:
                self.last_hover = now
                self.request(name, now, "hover")

    def _on_wheel(self, wparam):
        delta = ctypes.c_short((wparam >> 16) & 0xFFFF).value
        keys = wparam & 0xFFFF
        if not delta or not ((keys & MK_CONTROL) or (GetAsyncKeyState(VK_CONTROL) & 0x8000)):
            return
        now = time.perf_counter()
        self._activity(now)
        self.family.wheel(WHEEL_STEP ** (delta / float(WHEEL_DELTA)), now)

    # ----------------------------------------------------------- menu
    def _show_menu(self):
        now = time.perf_counter()               # only a look: a combo goes on (what is chosen from it may end it)
        self.family.touch(self, now, wake=False)   # no one wakes yet: 拱醒 needs them asleep
        self.press = None
        self.click_due = None
        self.attention_until = 0.0
        menu = CreatePopupMenu()
        sub = CreatePopupMenu()
        sizes = CreatePopupMenu()
        members = CreatePopupMenu()
        together = CreatePopupMenu()
        langs = CreatePopupMenu()
        toys = CreatePopupMenu()
        if not menu or not sub or not sizes or not members or not together or not langs or not toys:
            log("CreatePopupMenu failed, error %d" % ctypes.get_last_error())
            for m in (menu, sub, sizes, members, together, langs, toys):
                if m:
                    DestroyMenu(m)
            return
        ids = {}
        cmd = 0
        try:
            order = [a for a in ACTION_ORDER if a in self.store.meta]
            order += [a for a in self.store.meta if a not in order and not internal(a)]
            for i, name in enumerate(order):
                if not self.store.usable(name):
                    continue
                AppendMenuW(sub, MF_STRING, ID_ACTION_BASE + i, self.store.label(name) if LANG == "zh" else EN_LABELS.get(name, name))
                ids[ID_ACTION_BASE + i] = name
            for i, pct in enumerate(SIZE_PRESETS):
                flags = MF_STRING | (MF_CHECKED if abs(self.family.big_scale() * 100 - pct) < 0.5 else 0)
                if pct / 100.0 < self.family.floor():
                    flags |= MF_GRAYED
                AppendMenuW(sizes, flags, ID_SIZE_BASE + i, "%d%%" % pct)
            for i, label in enumerate((tr("一只", "One"), tr("两只", "Two"), tr("三只", "Three"))):
                same = self.family.slots == list(range(1, i + 1))
                AppendMenuW(members, MF_STRING | (MF_CHECKED if same else 0), ID_FAMILY_BASE + i, label)
            left = self.family.grow.data["chances"]
            AppendMenuW(menu, MF_STRING | (0 if self.family.can_dig(self) else MF_GRAYED), ID_DIG,
                        tr("翻找（还能翻到 %d 次）" % left, "Rummage (%s left)" % plural(left, "find")))
            have = self.family.treasures()
            if have and self.family.play_clip(self, have[0]):
                AppendMenuW(toys, MF_STRING, ID_PLAY_ANY, tr("随便拿一件", "Any one"))
                AppendMenuW(toys, MF_SEPARATOR, 0, None)
                order = self.store.items["order"]
                for name in have:
                    info = self.store.items["names"][name]
                    AppendMenuW(toys, MF_STRING, ID_PLAY_BASE + order.index(name), str(info.get("zh" if LANG == "zh" else "en") or name))
                AppendMenuW(menu, MF_POPUP, toys, tr("把玩", "Play with a treasure"))
            else:
                DestroyMenu(toys)
                AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, tr("把玩（还没有宝贝）", "Play with a treasure (none yet)"))
            AppendMenuW(menu, MF_STRING, ID_ALBUM, self.family.album_label())
            AppendMenuW(menu, MF_POPUP, sub, tr("做个动作", "Actions"))
            AppendMenuW(menu, MF_POPUP, sizes, tr("大小", "Size"))
            combo_names = list(COMBOS)
            for i, name in enumerate(combo_names):
                AppendMenuW(together, MF_STRING | (0 if self.family.combo_possible(name) else MF_GRAYED),
                            ID_COMBO_BASE + i, COMBOS[name] if LANG == "zh" else EN_COMBOS.get(name, name))
            for i, (code, label) in enumerate(LANGS):
                AppendMenuW(langs, MF_STRING | (MF_CHECKED if code == LANG else 0), ID_LANG_BASE + i, label)
            AppendMenuW(menu, MF_POPUP, members, tr("家人", "Family"))
            AppendMenuW(menu, MF_POPUP, together, tr("一起玩", "Play together"))
            activity = self.family.activity_menu()
            if activity:
                AppendMenuW(menu, MF_POPUP, activity, tr("活跃度", "Activity"))
            AppendMenuW(menu, MF_POPUP, langs, "语言 / Language")
            AppendMenuW(menu, MF_SEPARATOR, 0, None)
            if self.slot:
                AppendMenuW(menu, MF_STRING, ID_DISMISS, tr("让它先回去", "Send this one home"))
            AppendMenuW(menu, MF_STRING, ID_CONNECT, tr("连接 AI…", "Connect AI…"))
            AppendMenuW(menu, MF_STRING, ID_RESET, tr("回到右下角", "Back to the corner"))
            tray = self.family.tray
            AppendMenuW(menu, MF_STRING | (0 if tray is not None and tray.added else MF_GRAYED), ID_HIDE,
                        tr("隐藏（点托盘图标找回）", "Hide (the tray icon brings it back)"))   # no icon: no way back
            AppendMenuW(menu, MF_STRING, ID_QUIT, tr("退出", "Quit"))
            x, y = self._cursor()
            SetForegroundWindow(self.hwnd)      # documented quirk: else the menu never closes
            self.family.menu_open = True
            cmd = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                                 x, y, 0, self.hwnd, None)
            PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            self.family.menu_open = False
            DestroyMenu(menu)                   # also destroys the attached submenus
        if self.debug:
            log("menu -> %d" % cmd)
        now = time.perf_counter()
        if ID_LANG_BASE <= cmd < ID_LANG_BASE + len(LANGS):
            if set_lang(LANGS[cmd - ID_LANG_BASE][0]):
                self.family.save_state()
                if self.family.tray is not None:
                    self.family.tray.update()  # its tip in the new language
            return
        if cmd == ID_HIDE:
            self.family.set_hidden(True, now, "menu")
            return
        if ID_ACTIVITY_BASE <= cmd < ID_ACTIVITY_BASE + len(ACTIVITIES):
            self.family.set_activity(ACTIVITIES[cmd - ID_ACTIVITY_BASE][0], now, "menu")
            return
        if cmd and cmd != ID_QUIT and cmd != ID_COMBO_BASE + list(COMBOS).index("wake"):
            self._activity(now)
            self._wake(now, plays=True)
        if cmd == ID_QUIT:
            self.family.quit("menu")
        elif cmd == ID_DIG:
            self.family.dig_by_hand(self, now, "menu")
        elif cmd == ID_ALBUM:
            self.family.open_album("menu")
        elif cmd == ID_CONNECT:
            self.family.open_connect("menu")
        elif cmd == ID_PLAY_ANY:
            self.family.play_by_hand(self, None, now, "menu")
        elif ID_PLAY_BASE <= cmd < ID_PLAY_BASE + 200 and self.store.items is not None:
            order = self.store.items["order"]
            if cmd - ID_PLAY_BASE < len(order):
                self.family.play_by_hand(self, order[cmd - ID_PLAY_BASE], now, "menu")
        elif cmd == ID_DISMISS:
            self.family.dismiss(self, now)
        elif cmd == ID_RESET:
            self.family.reset()
        elif ID_COMBO_BASE <= cmd < ID_COMBO_BASE + len(COMBOS):
            self.family.start_combo(list(COMBOS)[cmd - ID_COMBO_BASE], now, manual=True)
        elif ID_FAMILY_BASE <= cmd < ID_FAMILY_BASE + len(FAMILY_RATIOS):
            self.family.set_count(cmd - ID_FAMILY_BASE + 1, now)
        elif ID_SIZE_BASE <= cmd < ID_SIZE_BASE + len(SIZE_PRESETS):
            self.family.set_scale(SIZE_PRESETS[cmd - ID_SIZE_BASE] / 100.0, now, "menu")
        elif cmd in ids:
            self._manual(ids[cmd], now, "menu")

    # ----------------------------------------------------------- timer
    def _schedule(self):
        """Re-arm the timer so it fires right when the next frame is due."""
        now = time.perf_counter()
        if self.family.hidden:                 # hidden: no frames, the big one still reads the events
            SetTimer(self.hwnd, TIMER_ANIM, int(POLL_INTERVAL * 1000) if self.slot == 0 else HIDDEN_TICK_MS, None)
            return
        if self.fly is not None:              # in the air: the window moves at ~60 Hz
            SetTimer(self.hwnd, TIMER_ANIM, THROW_TICK_MS, None)
            return
        delay = 0.05
        if self.cur_frames:
            idx = int((now - self.t0) * self.cur_fps)
            delay = self.t0 + (idx + 1) / self.cur_fps - now
        ms = int(math.ceil(delay * 1000.0)) + 1
        ms = max(10, min(ms, int(POLL_INTERVAL * 1000)))
        SetTimer(self.hwnd, TIMER_ANIM, ms, None)

    def _housekeeping(self, now):
        if self.slot == 0:                     # one reader for the family
            self.family.read_events(now)
            if self.quitting:
                return
            fam = self.family
            if now >= fam.album_poll_at:       # is the album open (its own mutex; it may have been opened by `clawd album`)?
                fam.album_poll_at = now + 1.0
                h = OpenMutexW(0x00100000, False, fam.album_mutex)
                if h:
                    CloseHandle(h)
                if h and not getattr(fam.grow, "watched", False):
                    fam.grow.save()            # just opened: what it reads is as of now
                fam.grow.watched = bool(h)
            self.family.grow.tick(now)         # written now and then (also while hidden); soon while the album is open
        if self.render is not None:
            self._poll_render(now)
        if self.size_due is not None and now >= self.size_due:
            self._size_settled(now)
        if now >= self.next_watch:
            self.next_watch = now + WATCH_INTERVAL
            self._watch_frames(now)

    def _on_timer(self):
        if self.quitting:
            return
        now = time.perf_counter()
        self.n_ticks += 1
        try:
            if now >= self.next_poll:
                self.next_poll = now + POLL_INTERVAL
                self._housekeeping(now)
                if self.quitting:
                    return
            self._update_modes(now)
            if self.slot == 0:
                self.family.work_tick(now)     # 干活时间 goes on while they are hidden too
            if self.family.hidden:             # busy and questions time out as usual, nothing else moves
                self.errors = 0
                return
            if self.react is not None and now >= self.react[1]:
                self._do_react(now)
            if self.slot == 0:
                self.family.nap_tick(now)
                self.family.combo_tick(now)
                self.family.dig_tick(now)
                self.family.sign_tick(now)
                self.family.talk_tick(now)
                self.family.grow_tick(now)
                self.family.first_tick(now)
            if self.click_due is not None and now >= self.click_due:
                self._resolve_clicks(now)
            if self.glide is not None:
                self._glide_step(now)
            if self.hop is not None:
                self._hop_step(now)
            if self.fly is not None:
                self._fly_step(now)
            if self.wander is not None:
                self._wander_step(now)
            self._advance(now)
            if self.item is not None or self.overlay is not None:
                self._item_tick(now)
            self.errors = 0
        except Exception:
            self.errors += 1
            log_exc("tick (%d in a row)" % self.errors)
            if self.errors >= MAX_CONSECUTIVE_ERRORS:
                self.family.quit("too many consecutive errors")
                return
            try:      # try to recover into a clean idle
                if self.slot == 0 or self.in_combo:
                    self.family.cancel_combo("error", now, instant=True)
                self.pending = None
                self.dozing = False
                self.dig = self.item = None
                self.wander = None
                self.glide = None
                self.carry = None
                if self.hop is not None or self.perch is not None:
                    self.hop = None
                    self.come_down(now, instant=True)
                self.last_blob = None
                self._start(self.idle_name, now, "error recovery")
            except Exception:
                pass
        finally:
            if not self.quitting:
                self._schedule()

    # ----------------------------------------------------------- thrown
    def _throw_speed(self):
        """(vx, vy) in px/s if the cursor still moved fast at the release, else None (a drop).  Times are those of
        the input events (ms), so a busy moment of ours does not bunch them up."""
        rt = GetMessageTime() & 0xFFFFFFFF    # the release
        trail = list(self.trail)
        while len(trail) >= 2 and trail[-1][1:] == trail[-2][1:]:
            trail.pop()                        # the release where the last move was: the speed is that of the moves
        if len(trail) < 2:
            return None
        last = trail[-1][0]
        pts = [q for q in trail if _ms_since(q[0], last) <= THROW_SAMPLE_SECS * 1000]
        dt = _ms_since(pts[0][0], last) / 1000.0
        stale = _ms_since(last, rt)
        wa = self._work_area(self.fx, self.fy)
        h = max(200, wa.bottom - wa.top)
        sp = math.hypot(pts[-1][1] - pts[0][1], pts[-1][2] - pts[0][2]) / dt if dt >= 0.012 else 0.0
        throw = stale <= THROW_STALE_SECS * 1000 and sp >= THROW_MIN_SPEED * h
        log("%srelease: %d px/s over %d ms, still for %d ms (throw from %d px/s): %s"
            % (self.tag, sp, dt * 1000, stale, THROW_MIN_SPEED * h, "thrown" if throw else "a drop"))
        if not throw:
            return None
        vx, vy = (pts[-1][1] - pts[0][1]) / dt, (pts[-1][2] - pts[0][2]) / dt
        k = min(1.0, THROW_MAX_SPEED * h / sp)
        return vx * k, vy * k

    def _start_flight(self, now, vx, vy, why):
        wa = self._work_area(self.fx, self.fy)
        xlo, xhi, ylo, yhi = self._feet_limits(wa)
        floor = max(ylo, min(yhi, wa.bottom - MARGIN))   # the line the family stands on in the corner
        floor = max(floor, min(self.fy, yhi))            # let go below it: down to there, not up
        self.fly = {"x": float(self.fx), "y": float(self.fy), "vx": vx, "vy": vy, "t": now, "t0": now,
                    "lim": (xlo, xhi, ylo), "floor": floor, "g": THROW_GRAVITY * max(200, wa.bottom - wa.top),
                    "bounce": 0, "spin": "right" if vx >= 0 else "left"}
        self.glide = None
        self.wander = None
        self.extra_wanted = None
        self.react = None
        self.pending = None
        self.sleeping = False
        self._cancel_manual()
        self._start(self._base_name(), now, why)
        log("%s%s: v=(%d, %d) px/s" % (self.tag, why, vx, vy))

    def _fly_step(self, now):
        f = self.fly
        dt = min(now - f["t"], 0.05)
        f["t"] = now
        if dt <= 0.0:
            return
        f["vy"] += f["g"] * dt
        x, y = f["x"] + f["vx"] * dt, f["y"] + f["vy"] * dt
        xlo, xhi, ylo = f["lim"]
        if x < xlo:                            # off a side: back, slower
            x, f["vx"] = xlo + (xlo - x) * THROW_WALL, abs(f["vx"]) * THROW_WALL
        elif x > xhi:
            x, f["vx"] = xhi - (x - xhi) * THROW_WALL, -abs(f["vx"]) * THROW_WALL
        if y < ylo:                            # off the top
            y, f["vy"] = ylo, abs(f["vy"]) * THROW_WALL
        landed = False
        if y >= f["floor"] and f["vy"] > 0.0:
            y = f["floor"]
            if f["bounce"] < len(THROW_BOUNCES):
                frac, keep = THROW_BOUNCES[f["bounce"]]
                f["vy"] = -math.sqrt(2.0 * f["g"] * frac * self._target_px())
                f["vx"] *= keep
                f["bounce"] += 1
                hit = self._first_clip(LAND_CLIPS[:1])
                if hit:
                    self._start(hit, now, "bounce")
                if self.debug:
                    log("%sbounce %d at (%d, %d)" % (self.tag, f["bounce"], x, y))
            else:
                landed = True
        if now - f["t0"] > THROW_MAX_SECS:
            y, landed = f["floor"], True
        f["x"], f["y"] = clamp(x, xlo, xhi), y
        self._move_feet(int(round(f["x"])), int(round(y)))
        if landed:
            self._land_flight(now)

    def _land_flight(self, now):
        self.fly = None
        self.area = self.fx                    # thrown there by the user: it lives there now
        self.family.depth_dirty = True
        self._save_state()
        log("%slanded at (%d, %d) after a throw" % (self.tag, self.fx, self.fy))
        self._start(self._first_clip(LAND_CLIPS) or self.idle_name, now, "landed")
        dizzy = self._first_clip(DIZZY_CLIPS)
        if dizzy and self.cur_kind == KIND_ONESHOT:
            self.pending = (dizzy, None)
        elif dizzy:
            self._start(dizzy, now, "landed")
        self.family.landed(self, now)

    # ----------------------------------------------------------- hidden / shown
    def hide_window(self, now):
        """The family hides: let go of whatever is under way, put it down where it stands, out of sight."""
        if self.press is not None or self.dragging:
            self.press = None
            self._release()
            self._end_drag(now, "hidden")
        if self.fly is not None:
            self._move_feet(int(self.fly["x"]), int(self.fly["floor"]))
            self.fly = None
            self.area = self.fx
        if self.glide is not None:
            self._finish_glide()
        if self.hop is not None or self.perch is not None:
            self.hop = None
            self.come_down(now, instant=True)
        self.wander = None
        self.react = None
        self.carry = None
        self.click_due = None
        self.click_burst = 0
        self.extra_wanted = None
        self.pending = None
        self.dozing = False
        if self.dig is not None:
            was, self.dig = self.dig, None
            self.family.dig_over(self, now, was, "hidden")
        self.item = None
        if self.overlay is not None:
            self.overlay.hide()
        self._cancel_manual()
        if self.hwnd:
            ShowWindow(self.hwnd, SW_HIDE)

    def show_window(self, now):
        """Back in sight with what it is up to now: the work clip if busy, else idle and awake."""
        self.sleeping = False
        self.last_activity = now
        self.pending = None
        self.cur_until = None
        self.next_wander = now + random.uniform(*self.wander_range)
        self._start_base(now, "shown")         # sets the next extra too
        self._redraw(pos=True)
        if self.hwnd:
            ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    # ----------------------------------------------------------- lifecycle
    def close(self):
        """Close this window only.  The family decides when the program ends."""
        if self.quitting:
            return
        self.quitting = True
        try:
            self._kill_render("quit")
        except Exception:
            log_exc("stop re-render on quit")
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
        if self.hwnd:
            KillTimer(self.hwnd, TIMER_ANIM)
            KillTimer(self.hwnd, TIMER_DRAG)
            DestroyWindow(self.hwnd)

    def _handle(self, hwnd, msg, wparam, lparam):
        if msg == WM_TIMER:
            if wparam == TIMER_ANIM:
                self._on_timer()
                return 0
            if wparam == TIMER_DRAG:
                self._on_drag_timer()
                return 0
        elif msg == WM_MOUSEMOVE:
            self._on_mouse_move(lparam)
            return 0
        elif msg in (WM_LBUTTONDOWN, WM_LBUTTONDBLCLK):
            self._on_lbutton_down(lparam)
            return 0
        elif msg == WM_LBUTTONUP:
            self._on_lbutton_up(lparam)
            return 0
        elif msg == WM_MOUSELEAVE:
            self.hovering = False
            return 0
        elif msg == WM_MOUSEWHEEL:
            self._on_wheel(wparam)
            return 0
        elif msg == WM_CAPTURECHANGED:
            self._on_capture_changed(lparam)
            return 0
        elif msg == WM_RBUTTONDOWN:
            return 0
        elif msg == WM_RBUTTONUP:
            if not self.dragging:
                self._show_menu()
            return 0
        elif msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        elif msg == WM_ENTERSIZEMOVE:
            log("unexpected system move loop")       # must never happen in v2
            return 0
        elif msg == WM_DISPLAYCHANGE or (msg == WM_SETTINGCHANGE and wparam == SPI_SETWORKAREA):
            self._ensure_visible()
            return 0
        elif msg == WM_DPICHANGED:
            return 0                    # keep native pixel size; no resize
        elif msg == WM_QUERYENDSESSION:
            self._save_state()
            self.family.grow.save()
            return 1
        elif msg == WM_ENDSESSION:
            if wparam:
                self._kill_render("session end")
                self._save_state()
                self.family.grow.save()
            return 0
        elif msg == WM_CLOSE:
            self.family.quit("WM_CLOSE")
            return 0
        elif msg == WM_DESTROY:
            self.hwnd = None if self.hwnd == hwnd else self.hwnd
            self.family.window_gone(hwnd, self)
            return 0
        return None


# --------------------------------------------------------------------------- the family
class Family(object):
    """What the pets share: the window class, the event file, state.json, the message loop."""

    def __init__(self, base_dir, opts):
        self.base_dir = base_dir
        self.opts = opts
        self.pets = []                         # slot order; pets[0] is the big one
        self.windows = {}                      # hwnd -> pet
        self.quitting = False
        self.born = time.perf_counter()
        self.saved_state = None
        self.wanted = 1.0                      # the big one's size as asked for
        self.slots = []                        # the other pets that should be shown
        self.pos = {}                          # slot -> feet and the big one's size then, also of those not shown
        self.homes = {}                        # slot -> where it stood before a combo, if it is still away
        self.far = set()                       # while a combo of their own is planned: who is too far away
        self.plan_rank = R_HAND                # ... and what it is worth as a chore (for one in the 小剧场)
        self.show_gap = opts["show_gap"]       # s between two shows (games, copying, watching), x the activity pace
        self.show_end = -1e9                   # when the last show ended (or will: one copying)
        self.sign = None                       # the sign up now: kind, text, until, holder (None: over the big one)
        self.sign_board = SignBoard(self)
        self.dots = TalkDots(self)             # the conversations' numbered circles at the family's feet
        self.dot_tip = SignBoard(self)         # ... the name of the one under the mouse, over it
        self.titles = TalkTitles()
        self.tip_read = (None, -1e9, None)     # (session, when, its name) last read
        self.talk_tab = {}                     # session -> (Windows Terminal window, its tab's id) where you typed last
        self.link_last = (None, -1e9)          # (the link last opened, when): not again on a second click
        self.link_q = None                     # links to open, one after another in the order of the clicks
        self.tab_job = None                    # (what, the clawd_tabs.ps1 process, since, its args) under way
        self.tab_next = None                   # a reading waiting for the job under way
        self.tab_click = None                  # a click waiting for the readings
        self.tab_shells = None                 # PowerShell programs to run it with, best first (tab_shells())
        self.tab_refused = False               # macOS: the user did not let the pets choose a tab (said once)
        self.talks = {}                        # session -> {"n": its number, "end": how its last turn ended, "seen"}
        self.talk_where = {}                   # session -> (its window or None, the agent's name), from its "at" line
        self.talk_entry = self.titles.entry    # session -> Claude Code's entrypoint, from its "at" line (TalkTitles)
        self.talk_wt = {}                      # session -> the Windows Terminal tab it runs in (WT_SESSION), "at" line
        self.places_saved = None               # what talks.json holds (_places_now), to write it on a change
        self.codex_kind = {}                   # Codex session -> "talk" (a conversation), "job" (Codex's own background
                                               # work: not shown) or a sub-agent's parent session (counted on it)
        self.ag_subs = set()                   # Antigravity sessions that are sub-agents (codex_kind: their root) ...
        self.ag_checked = set()                # sessions looked up once in Antigravity's files (no "at" line of theirs seen)
        self.ag_open = set()                   # ... and conversations whose turn ended as one went out, at work again by it
        self.codex_first = {}                  # Codex session not yet told apart -> when first seen
        self._places_load()
        self.talk_check = 0.0
        self.talk_keep = opts.get("talk_keep", TALK_KEEP)
        self.talk_done_keep = opts.get("talk_done_keep", TALK_DONE_KEEP)
        self.cut_quiet = opts.get("cut_quiet", CUT_QUIET)
        self.dots_said = None                  # the circles last logged (--debug)
        self.tray = None                      # the notification-area icon (main adds it)
        self.hidden = set()                    # why the family is out of sight: "user" (tray, menu, clawd hide)
        self.sign_last_tool = None             # the tool the last sign of this turn was about
        self.sign_down_at = -1e9
        self.sign_down_tool = False
        self.think_since = None                # since when the big one only thinks (or listens)
        self.think_signed = -1e9               # when "thinking..." last went up
        self.reacted_at = {}                   # event -> when the others last reacted to it
        self.combo = None                      # the combo under way
        self.combo_queue = None                # (name, until): to start as soon as they are idle
        self.menu_open = False
        self.depth_dirty = True
        self.depth_order = None
        self.overlaps = {}                     # (smaller, other) -> since when they overlap
        self.next_overlap_check = 0.0
        self.mimic_range = paced(opts["mimic_range"])
        self.return_range = opts["return_range"]
        self.next_mimic = self.born + self.mimic_range[0]
        self.last_note = -1e9                  # when the last note for a sub-agent went out
        self.combo_range = paced(opts["combo_range"])
        self.peek_after = opts["peek_after"] * ACTIVITY_PACE[ACTIVITY]
        self.wake_range = paced(opts["wake_range"])
        self.wake_chance = opts["wake_chance"]
        self.next_combo = self.born + random.uniform(*self.combo_range)
        self.next_peek = 0.0
        self.play_range = paced(opts["play_range"])
        self.play_after = opts["play_after"]
        self.next_play = self.born + self.play_range[0]   # the two small ones' next game while the big one works
        self.wake_due = None
        self.nap = None                        # 鼠标小剧场 under way: {"pet", "stage", "t"}
        self.nap_times = opts["nap_times"]
        self.nap_next = 0.0                    # next cursor read
        self.nap_at = None                     # where the cursor stopped ...
        self.nap_still = 0.0                   # ... and since when
        self.nap_done = False                  # one 小剧场 per stop of the cursor
        self.nap_rest = 0.0                    # none before this (after a startle)
        self.grow = Grow(GROW_PATH)            # 养成: XP, level, the combos seen
        self.grow_signs = []                   # first-seen combos whose sign is still to go up
        self.gifts_looked = False              # the gifts of levels reached before (补发): looked at once, at the start
        self.look = load_look()                # how the plain signs look (the 图鉴's 礼物 page, token sign:<kind>=<name>)
        self.dig_every = opts["dig_every"]     # 翻找: s of a turn's work time for each dig by itself (tests of other things: never)
        if self.dig_every is None:
            self.dig_every = float("inf") if opts["debug"] else DIG_EVERY
        self.chance_work = opts["chance_work"]  # s of work time for a chance to dig by hand (tests: each turn one, unless given)
        if self.chance_work is None:
            self.chance_work = 0.0 if opts["debug"] else DIG_CHANCE_WORK
        self.work_at = None                    # 干活时间: the last tick (work_tick)
        self.work_last = -1e9                  # ... the last moment the clock for the digs by hand counted
        self.dig_next = 0.0                    # no try before this
        self.loot = []                         # (treasure, the finder's slot or None) found in the turn, shown when it ends
        self.loot_left = [x[0] for x in self.grow.data["loot"]]    # put away in a turn that never ended here (a quit): theirs at the start
        self.treasure = None                   # (finder, treasure, rarity) while 交宝贝 is planned
        self.hand_show = None                  # (finder, treasure, rarity, until): 交宝贝 was cut short, it may hold it up where it stands
        self.first_play = None                 # a treasure found for the first time, to be played with once it has been shown
        self.album_looked = False              # how much of the 图鉴 is found: looked at once at the start (album_check) ...
        self.album_poll_at = 0.0               # the album of this home: looked for once a second (while it is open, grow.json is written soon)
        self.album_mutex = "ClawdAlbum_%08x" % (zlib.crc32(os.path.normcase(os.path.abspath(HOME_DIR)).encode("utf-8")) & 0xFFFFFFFF)
        self.album_recheck = None              # ... and a moment after the album is opened (the first time, it writes album.json)
        self.first_start = None                # the very first start: when the hint and the connect window come (first_tick)
        self.loot_due = None                   # the turn ended then: the finds wait for the "done" sign to come down
        self.turn_marks = set()                # what this turn's work was like (DIG_SPECIAL)
        self.grow_stop_at = -1e9               # the last turn's end: a level-up waits for its reaction
        self.replaying = False                 # the last event again at startup: counted already
        self.events = EventChannel(EVENT_PATH)
        self.n_ticks = self.n_draws = 0        # of the windows closed so far
        self.hinst = GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._wndproc_py)       # keep a reference!
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0                                     # clicks are counted by us
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = self.hinst
        wc.hCursor = LoadCursorW(None, IDC_HAND)
        wc.lpszClassName = CLASS_NAME
        if not RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != ERROR_CLASS_ALREADY_EXISTS:
                raise ctypes.WinError(err)
        self._wc = wc

    @property
    def leader(self):
        return self.pets[0] if self.pets else None

    def add(self, slot, store, scale, feet):
        pet = Pet.__new__(Pet)
        self.pets.append(pet)                  # it may already need the family while it starts
        try:
            pet.__init__(self, slot, store, self.base_dir, scale, feet, self.opts)
        except Exception:
            self.pets.remove(pet)
            raise
        pet.area = pet.fx
        self.depth_dirty = True
        self.depth_order = None
        return pet

    def replay_last_event(self):
        event = self.events.prime()
        if event and event[0] != "quit":
            self.replaying = True
            try:
                if event[0] != "at":
                    self.leader._on_token(event[0], time.perf_counter(), "event at startup", event[1])
            finally:
                self.replaying = False

    def read_events(self, now):
        for tok, session, more in self.events.poll(now):
            if (session and tok != "at" and session not in self.codex_kind and session not in self.talks
                    and not self.talk_where.get(session, (None, ""))[1] and session not in self.ag_checked):
                self._ag_unknown(session, now)
            kind = self.codex_kind.get(session) if session else None
            if kind == "job":
                continue                       # Codex's own background work: nothing of yours
            if kind not in (None, "talk"):     # a Codex or Antigravity sub-agent: its work shows on its conversation's circle
                if session in self.ag_subs:
                    self._ag_sub_event(tok, kind, now)
                if tok in ("at", "hello", "listen", "stop", "stopfail", "bye"):
                    continue
                session = kind
            elif tok == "listen":
                self.ag_open.discard(session)  # a turn of its own again
            if tok == "circles":               # clawd circles: what each circle is, where a click goes
                self.talk_report(now)
                continue
            if tok == "cut":                   # you stopped its turn (the agent says so: Antigravity): over, no "done"
                if session and self.leader is not None:
                    self.turn_cut(session, now, "its agent says so")
                continue
            self.talk_event(tok, session, more, now)
            if tok == "at":                    # where a conversation is: nothing to show, nothing to react to
                continue
            combo = self.combo
            if (combo is not None and self.leader in combo["pets"] and tok in SEMANTIC
                    and (tok not in ("agent", "agent_done", "hello", "bye") or combo["name"] == "stack")):
                self.cancel_combo("event " + tok, now)  # work and questions come first
            if self.hidden and self._asks_to_see(tok):
                self.set_hidden(False, now, "event " + tok)
            self.leader._on_token(tok, now, session=session)
            if self.quitting:
                return
            if self.hidden:                    # the big one keeps track of the work; no signs, no reactions
                continue
            self._sign_event(tok, now, session)    # first: the one that holds the sign does not also react
            self._followers_react(tok, now)

    # ----------------------------------------------------------- the conversations' circles
    def talk_event(self, tok, session, more, now):
        """Every conversation that has worked here has a number.  An "at" line says where it is (its window, and
        which agent's it is): kept also for one not seen at work yet."""
        if not session:
            return
        if tok == "at":
            try:
                hwnd = int(more[0]) if more else 0
            except ValueError:
                hwnd = 0
            agent = more[1].lower()[:16] if len(more) > 1 and more[1] != "-" else ""
            where = (hwnd if hwnd > 0 else self.talk_where.get(session, (None, ""))[0],    # 0: not known, keep what was
                     agent)
            entry = more[2].lower()[:24] if len(more) > 2 and more[2] != "-" else ""
            if entry and self.talk_entry.get(session) != entry:
                if session in self.talk_entry:
                    log("conversation %s: now in %s (was %s)" % (session, entry, self.talk_entry[session]))
                self.talk_entry[session] = entry    # desktop app or terminal: told by its hook (TalkTitles.claude_kind)
                self.titles.where.pop(session, None)
            if len(more) > 3 and more[3] != "-":
                self.talk_wt[session] = more[3].lower()[:36]
            if len(self.talk_where) >= 64 and session not in self.talk_where:
                self.talk_where.clear()
            if where[0] and not MAC and window_class(where[0]) == TERMINAL_CLASS:
                # in Windows Terminal: the window you typed in is the one in front now (its windows are one process,
                # so the hook cannot tell which), and the tab you typed in is its selected one: remember that tab
                # (on macOS the hook says the tab itself, its terminal's device: talk_wt, _tab_of)
                fg = GetForegroundWindow()
                if fg and window_class(fg) == TERMINAL_CLASS:
                    where = (fg, where[1])
                    self.tab_run(("selected", session, fg), ["selected", str(fg)])
                else:
                    log("conversation %s: in Windows Terminal, but no terminal in front (%s): its tab not read"
                        % (session, window_class(fg) or "none"))
            if self.talk_where.get(session) != where:
                self.talk_where[session] = where
                log("conversation %s is at window %s (%s)" % (session, where[0], where[1] or "?"))
            if where[1] in ("codex", "antigravity"):
                self._codex_sort(session, now)
            return
        if tok not in SEMANTIC:
            return
        t = self.talks.get(session)
        if tok == "bye":
            if self.talks.pop(session, None) is not None:
                log("conversation %s said bye: its circle goes" % session)
            self.talk_where.pop(session, None)
            self.talk_tab.pop(session, None)
            self.talk_entry.pop(session, None)
            self.talk_wt.pop(session, None)
            return
        if t is None:
            if tok in ("hello", "attention", "agent_done", "compact_end") or len(self.talks) >= TALK_MAX:
                return                         # not at work yet (or one too many): no number
            if tok != "listen" and session in self.leader.turn_over:
                return                         # its turn is over: a sub-agent still at it in the background
            # the smallest number free: one goes when its circle goes, and they just keep their order (用户 2026-11-13:
            # "一轮对话结束了直接清除掉序号，然后有先后就行"; keeping each one's old number left gaps and odd orders)
            n = min(set(range(1, TALK_MAX + 1)) - set(x["n"] for x in self.talks.values()))
            t = self.talks[session] = {"n": n, "end": None, "seen": now}
            log("conversation %s is number %d (%d now)" % (session, n, len(self.talks)))
            hwnd, agent = self.talk_where.get(session, (None, ""))
            if hwnd and not talk_window_alive(hwnd):    # back, but the window it had is gone (resumed in a new
                self.talk_where[session] = (None, agent)  # terminal): forget that window, not the circle; its "at" line
                self.talk_tab.pop(session, None)          # says where it is now
        t["seen"] = now
        t.pop("back", None)                    # a word of its own since the restart: as any other circle now
        if tok == "attention":
            # mid-turn (a permission, a question): orange till its next word, however long you take (the big one's
            # sign and wave stop after ATTENTION_TIMEOUT; the circle said "working" then, 2026-11-14).  After its
            # turn (Claude Code's "waiting for your input" a minute later): as before, it is done
            if session not in self.leader.turn_over:
                t["wait"] = True
        elif tok not in ("agent", "agent_done"):
            t["wait"] = False
        if tok == "listen":
            t["end"] = t["end_at"] = None
        elif tok == "stop":
            t["end"], t["end_at"] = "done", now
        elif tok == "stopfail":
            t["end"], t["end_at"] = "error", now

    def _places_load(self):
        """Where the conversations are (their window, agent and Windows Terminal tab), as the pets before this one
        knew it: a restart forgot them, and a click on a circle found no window until that conversation's next message.
        A window is taken back only while it is there and still of the same kind (a closed one's handle can come
        back as another window)."""
        path = os.path.join(HOME_DIR, "talks.json")
        circles = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            d = {}
        except (OSError, ValueError) as e:
            log("talks.json not read (%s): no places, no circles from before" % e)
            d = {}

        def part(key):
            v = d.get(key) if isinstance(d, dict) else None
            return v if isinstance(v, dict) else {}
        # each one by itself: one odd entry (a file edited by hand, half written) costs that one only, not all of them
        # (2026-11-15: one let none of the circles come back)
        for session, rec in list(part("where").items())[:64]:
            try:
                hwnd, agent, cls = rec[:3]
                session = str(session)
                if len(rec) > 3 and isinstance(rec[3], str) and rec[3]:
                    self.talk_entry[session] = rec[3][:24]
                if len(rec) > 4 and isinstance(rec[4], str) and rec[4]:
                    self.talk_wt[session] = rec[4][:36]
                if hwnd and not (isinstance(hwnd, int) and talk_window_alive(hwnd) and talk_window_class(hwnd) == cls):
                    hwnd = None                # gone (or its handle is another window's now): the agent stays known
                self.talk_where[session] = (hwnd or None, str(agent or "")[:16])
            except (TypeError, ValueError, OverflowError, ctypes.ArgumentError):
                log("talks.json: an odd place for %s, passed over" % str(session)[:16])
        for session, rec in list(part("tab").items())[:64]:
            try:
                hwnd, tab = rec
                if (isinstance(hwnd, int) and talk_window_alive(hwnd) and talk_window_class(hwnd) == TERMINAL_CLASS
                        and isinstance(tab, str)):
                    self.talk_tab[str(session)] = (hwnd, tab)
            except (TypeError, ValueError, OverflowError, ctypes.ArgumentError):
                log("talks.json: an odd tab for %s, passed over" % str(session)[:16])
        circles = part("circles")
        if self.talk_where or self.talk_tab:
            log("conversations' places from before: %d windows, %d tabs"
                % (len([1 for w in self.talk_where.values() if w[0]]), len(self.talk_tab)))
        try:
            self._circles_back(circles)
        except Exception:
            log_exc("talks.json circles")
        self.places_saved = self._places_now()

    def _circles_back(self, circles):
        """The circles as they were when the pets before these stopped (用户 2026-11-15: closed and opened again, they
        are still there and a click still goes there): same numbers, same colour, each as long as it would have
        stayed.  Only one that can still be gone to: its window still there, or its desktop app still running (a
        click opens it there).  One at work then shows idle till its next word (whether it still is, nobody said)."""
        wall, now = time.time(), time.perf_counter()
        keep = getattr(self, "talk_keep", self.opts.get("talk_keep", TALK_KEEP))
        done_keep = getattr(self, "talk_done_keep", self.opts.get("talk_done_keep", TALK_DONE_KEEP))
        for session, c in sorted(circles.items(), key=lambda kv: kv[1].get("n") if isinstance(kv[1], dict)
                                 and isinstance(kv[1].get("n"), int) else 99):
            if not isinstance(c, dict) or len(self.talks) >= TALK_MAX:
                continue
            session, n = str(session), c.get("n")
            if not isinstance(n, int) or not 1 <= n <= TALK_MAX or n in [t["n"] for t in self.talks.values()]:
                continue
            seen = c.get("seen") if isinstance(c.get("seen"), (int, float)) else 0.0
            end = c.get("end") if c.get("end") in ("done", "error", "cut") else None
            end_at = c.get("end_at") if isinstance(c.get("end_at"), (int, float)) else None
            if wall - seen > keep or (end and end_at is not None and wall - end_at > done_keep):
                continue                       # it would have gone by now
            hwnd, agent = self.talk_where.get(session, (None, ""))
            if not hwnd:
                info = AGENT_INFO.get(agent) or {}
                desk = agent != "claude" or self.titles.claude_kind(session) == "desk"
                if not (info.get("scheme") and desk and app_running(info["scheme"])):
                    continue                   # its window is gone, and no app to open it in: over
            self.talks[session] = {"n": n, "end": end, "end_at": now - (wall - end_at) if end and end_at is not None else None,
                                   "seen": now - (wall - seen), "wait": bool(c.get("wait")), "back": True}
            log("conversation %s is number %d (back from before the restart)" % (session, n))

    def _places_now(self):
        """What talks.json says, to tell when it is to be written again"""
        return (dict(self.talk_where), dict(self.talk_tab), dict(self.talk_entry), dict(self.talk_wt),
                {s: (t["n"], t.get("end"), bool(t.get("wait"))) for s, t in self.talks.items()})

    def _places_save(self):
        self.places_saved = self._places_now()
        wall, now = time.time(), time.perf_counter()
        d = {"where": {s: [w[0] or 0, w[1], talk_window_class(w[0]) if w[0] else "", self.talk_entry.get(s, ""),
                           self.talk_wt.get(s, "")] for s, w in self.talk_where.items()},
             "tab": {s: [t[0], t[1]] for s, t in self.talk_tab.items()},
             "circles": {s: {"n": t["n"], "end": t.get("end"), "wait": bool(t.get("wait")),
                             "end_at": wall - (now - t["end_at"]) if t.get("end_at") is not None else None,
                             "seen": wall - (now - t["seen"])} for s, t in self.talks.items()}}
        path = os.path.join(HOME_DIR, "talks.json")
        try:
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(path + ".tmp", path)
        except OSError as e:
            log("talks.json not written (%s)" % e)

    def talk_state(self, session):
        big = self.leader
        if big.attention_until and big.attention_session == session:
            return "wait"
        if self.talks[session].get("wait"):
            return "wait"
        if session in big.working and session not in big.turn_over:
            return "busy"
        return self.talks[session]["end"] or "idle"

    def _codex_sort(self, session, now):
        """A Codex session: a conversation of yours, a sub-agent of one, or Codex's own background job (2026-11-13/14:
        its memory work and a read-only job came as sessions of their own, with hooks, and took a circle each; a
        click found no conversation).  Told by Codex's thread list: a thread -> yours; a sub-agent's thread -> its
        parent's; none for CODEX_WAIT s -> a job.  Several threads of the same 8 characters (an old key, the start
        of the id, which is by the minute): yours if any is.  No thread list to read: yours, as before."""
        if session in self.codex_kind:
            return
        first = self.codex_first.setdefault(session, now)
        if self.talk_where.get(session, (None, ""))[1] == "antigravity":
            self._ag_sort(session, now, first)
            return
        try:
            rows = self.titles.codex_threads(session)
        except Exception:
            log_exc("Codex's thread list")
            rows = None
        if rows is None:
            kind = "talk"
        elif any(not r[1].startswith("{") for r in rows):
            kind = "talk"
        elif rows:
            kind = "job"
            for r in rows:
                try:
                    parent = json.loads(r[1])["subagent"]["thread_spawn"]["parent_thread_id"]
                    parent = parent[-8:] if r[0].endswith(session) else parent[:8]     # keyed as the hook keys it
                except (ValueError, KeyError, TypeError):
                    continue
                kind = "talk" if parent == session else parent
        elif now - first < CODEX_WAIT:
            return                             # not there yet, maybe: unshown a while
        else:
            kind = "job"
        if len(self.codex_kind) >= 64:
            self.codex_kind.clear()
        self.codex_kind[session] = kind
        self.codex_first.pop(session, None)
        if kind == "talk":
            if now - first > 1.5:
                log("conversation %s: in Codex's thread list after %.1fs" % (session, now - first))
            return
        log("conversation %s: %s, no circle" % (session, "Codex's own background job" if kind == "job"
                                                  else "a Codex sub-agent of %s" % kind))
        self.talks.pop(session, None)
        self.talk_where.pop(session, None)
        self.talk_tab.pop(session, None)
        lead = self.leader
        if lead is not None:
            lead.turn_over.discard(session)
            if session in lead.working:
                lead._end_busy(now, session)
            if lead.attention_session == session:
                lead.attention_until = 0.0

    def _talk_closed(self, session, now):
        """Its window closed with no bye (killed, crashed; an agent with no end event): over as with a bye, without
        the wave.  The big one worked on up to BUSY_TIMEOUT before (2026-11-14: only the circle went)."""
        big = self.leader
        if big is None or (session not in big.working and big.attention_session != session):
            return
        log("conversation %s: its window is gone: not at work any more" % session)
        big.turn_over.discard(session)
        if big.attention_session == session and big.attention_until:
            big.attention_until = 0.0
        if session in big.working:
            big._end_busy(now, session)
        elif not big.working:
            big._activity(now)

    def _cut_check(self, now):
        """Once a second: a Claude Code or Codex turn at work and quiet CUT_QUIET s gets its transcript looked at
        (every CUT_PEEK s while quiet): neither says so when you stop it.  Long thinking, a long command, a sub-agent,
        a permission asked: the transcript does not end with your interrupt, and it works on."""
        big = self.leader
        if big is None:
            return
        for session, turn in list(big.working.items()):
            if (not session or session in big.turn_over or now - turn["seen"] < self.cut_quiet
                    or now < turn.get("cut_peek", 0.0)):
                continue
            agent = self.talk_agent(session, now)
            if agent not in ("", "claude", "codex"):
                continue
            turn["cut_peek"] = now + CUT_PEEK
            try:
                cut = self.titles.interrupted(session, agent)
            except Exception:
                log_exc("a transcript's end")
                cut = None
            if cut:
                self.turn_cut(session, now)
        # one still waiting for you after the big one stopped working on it (BUSY_TIMEOUT: a question you leave a
        # while): stays orange till its next word, so an Esc at that question is looked for here too (else orange on)
        for session, t in list(self.talks.items()):
            if not t.get("wait") or session in big.working or now < t.get("cut_peek", 0.0):
                continue
            agent = self.talk_agent(session, now)
            if agent not in ("", "claude", "codex"):
                continue
            t["cut_peek"] = now + CUT_PEEK
            try:
                cut = self.titles.interrupted(session, agent)
            except Exception:
                log_exc("a transcript's end")
                cut = None
            if cut:
                self.turn_cut(session, now)

    def turn_cut(self, session, now, how="its transcript says so"):
        """You stopped this turn (Esc, the stop button): as a turn that ended, without the "done" reaction.  Its XP
        as an interrupted turn's (what its next message did before); its circle grey ("interrupted"), gone a minute
        later like a done one."""
        big = self.leader
        turn = big.working.get(session)
        log("conversation %s: interrupted (%s, %.0fs quiet): not at work any more"
            % (session, how, now - turn["seen"] if turn else 0.0))
        if turn is not None and turn.get("tools"):
            self.grow_turn(turn, False, now, "interrupted")
        big.turn_over.add(session)
        if big.attention_session == session and big.attention_until:
            big.attention_until = 0.0
        big._end_busy(now, session)
        t = self.talks.get(session)
        if t is not None:
            t["end"], t["end_at"] = "cut", now
            t["wait"] = False

    def _ag_sort(self, session, now, first):
        """An Antigravity session: a conversation of yours, or a sub-agent of one (its work then shows on that one's
        circle).  Its file not there yet: unshown up to CODEX_WAIT s, then taken for yours."""
        try:
            root = self.titles.ag_root(session)
        except Exception:
            log_exc("Antigravity's conversation file")
            root = ""
        if root is None and now - first < CODEX_WAIT:
            return
        self.codex_first.pop(session, None)
        if len(self.codex_kind) >= 64:
            self.codex_kind.clear()
        self.codex_kind[session] = root or "talk"
        if not root:
            return
        if len(self.ag_subs) >= 64:
            self.ag_subs.clear()
        self.ag_subs.add(session)
        log("conversation %s: an Antigravity sub-agent of %s, no circle" % (session, root))
        self.talks.pop(session, None)
        self.talk_where.pop(session, None)
        self.talk_tab.pop(session, None)
        lead = self.leader
        if lead is not None:
            lead.turn_over.discard(session)
            if session in lead.working:
                lead._end_busy(now, session)
            if lead.attention_session == session:
                lead.attention_until = 0.0

    def _ag_unknown(self, session, now):
        """A session with no circle and no "at" line seen (2026-11-15: the pets restarted while an Antigravity
        sub-agent worked: its "at" line came before, and it took a circle of its own): looked up once in Antigravity's
        files; a sub-agent there is sorted as one (its parent's at work again)."""
        if len(self.ag_checked) >= 256:
            self.ag_checked.clear()
        self.ag_checked.add(session)
        try:
            root = self.titles.ag_root(session)
        except Exception:
            log_exc("Antigravity's conversation file")
            return
        if not root:
            return
        if len(self.codex_kind) >= 64:
            self.codex_kind.clear()
        self.codex_kind[session] = root
        if len(self.ag_subs) >= 64:
            self.ag_subs.clear()
        self.ag_subs.add(session)
        log("conversation %s: an Antigravity sub-agent of %s (from its file), no circle" % (session, root))
        self.talk_where.pop(session, None)
        if self.talks.pop(session, None) is not None:
            self.talk_tab.pop(session, None)
            lead = self.leader
            if lead is not None and session in lead.working:
                lead._end_busy(now, session)

    def _ag_sub_event(self, tok, parent, now):
        """Antigravity ends a turn as it sends a sub-agent out (2026-11-15: "a browser agent is on its way, wait a
        moment"; the circle went green and was gone a minute later while the browser worked on).  Its work keeps that
        conversation at work, blue, as a turn of it (not the 20 s of a sub-agent after a turn); its end ends that,
        quietly: green, no reaction, no XP (that turn was counted at its stop)."""
        big = self.leader
        if big is None:
            return
        t = self.talks.get(parent)
        if tok in ("stop", "stopfail"):
            if parent in self.ag_open:
                self.ag_open.discard(parent)
                big.turn_over.add(parent)
                if parent in big.working:
                    big._end_busy(now, parent)
                if t is not None:
                    t["end"], t["end_at"], t["wait"] = "done", now, False
                log("conversation %s: its sub-agent is done" % parent)
        elif tok not in ("at", "hello", "listen", "bye") and parent not in self.ag_open and (
                parent in big.turn_over or parent not in big.working):    # (not at work: the pets restarted meanwhile)
            big.turn_over.discard(parent)      # its work now goes as a turn's (busy as long as one, a circle)
            self.ag_open.add(parent)
            if t is not None:
                t["end"] = t["end_at"] = None
            log("conversation %s: its sub-agent at work after its turn: at work again" % parent)

    def _codex_unsorted(self, session):
        """A Codex or Antigravity session not told apart yet (yours, a sub-agent, a job): no circle meanwhile."""
        return self.talk_where.get(session, (None, ""))[1] in ("codex", "antigravity") and session not in self.codex_kind

    def talk_tick(self, now):
        """Once a second the ones long silent or whose window is gone are dropped; the row follows the big one."""
        big = self.leader
        if self.tab_job is not None:
            self.tab_done()
        if now >= self.talk_check:
            self.talk_check = now + 1.0
            for session in [s for s in self.talks if self._codex_unsorted(s)]:
                self._codex_sort(session, now)
            for session in [s for s in self.talks if not self.talk_where.get(s, (None, ""))[1] and s not in self.ag_checked]:
                self._ag_unknown(session, now)     # whose agent no "at" line said (back from before a restart; a
                                                   # click remembers its app's window, not whose it is): Antigravity's?
            self._cut_check(now)
            if len(self.codex_first) > 64:
                self.codex_first.clear()
            for session, t in list(self.talks.items()):
                hwnd = self.talk_where.get(session, (None, ""))[0]
                why = None
                if hwnd and not talk_window_alive(hwnd):
                    info = AGENT_INFO.get(self.talk_agent(session, now), {})
                    if info.get("open") and app_running(info["scheme"]):
                        # its app closed the window but runs on in its tray (Antigravity with Keep In Menu Bar makes a
                        # new window when opened again): the conversation goes on; a click finds or opens its window
                        self.talk_where[session] = (None, self.talk_where.get(session, (None, ""))[1])
                        log("conversation %s: its window is gone, its app runs on (in the tray)" % session)
                    else:
                        why = "its window is gone"
                elif (t.get("end_at") is not None and now - t["end_at"] > self.talk_done_keep
                      and self.talk_state(session) in ("done", "error", "cut")):
                    why = "its turn is over"           # its green a while to see it was done, then gone
                elif (now - t["seen"] > self.talk_keep and self.talk_state(session) != "busy"
                      and not (t.get("wait") and not t.get("back"))
                      and (t.get("end") is None or t.get("end_at") is None)):
                    why = "long silent"                # (one over goes by the rule above: an Esc at a question
                                                       # left long showed no grey, it went at once)
                if why:
                    del self.talks[session]
                    if why == "its window is gone":    # done or silent only: it is still there, and where it is
                        self.talk_where.pop(session, None)     # stays known for when it comes back (its "at" line
                        self.talk_tab.pop(session, None)       # can come a moment after its first word)
                        self._talk_closed(session, now)
                    log("conversation %s: %s, its circle goes" % (session, why))
            if self._places_now() != self.places_saved:
                self._places_save()
        shown = [(s, t) for s, t in self.talks.items() if not self._codex_unsorted(s)]
        if len(shown) < TALK_SHOW_FROM or big.hwnd is None or big.dragging or big.fly is not None:
            self.dots.show((), 0, None)
            self.dots.hover = False
            self.dot_tip.update(now, None, None, 12, None, False)
            return
        dots = tuple(sorted((t["n"], self.talk_state(s), s) for s, t in shown))
        if self.opts.get("debug") and dots != self.dots_said:   # (tests read the circles' states here)
            self.dots_said = dots
            log("circles: %s" % " ".join("%d=%s(%s)" % (n, st, s) for n, st, s in dots))
        d = int(round(clamp(0.17 * big._target_px(), 14, 40)))
        self.dots.show(dots, d, (big.fx, big.fy + max(2, int(round(0.03 * big._target_px())))))
        self._dot_tip(now, d)

    def _dot_tip(self, now, d):
        """While the mouse is on a circle: its number, the conversation's name (read again every 2 s, so a rename
        shows) and what it is at, on a board over it."""
        session = cx = None
        if self.dots.hover and self.dots.put and self.dots.shown:
            c = self._cursor_pos()             # the real cursor (a test's: its cursor file)
            x0, y0 = self.dots.put[1]
            if c is not None and x0 <= c[0] < x0 + self.dots.w and y0 <= c[1] < y0 + self.dots.h:
                session, cx = self.dots.at_x(x=c[0] - x0)
            else:
                self.dots.hover = False        # off the row: no more looking until it comes back
        if session not in self.talks:
            self.dot_tip.update(now, None, None, 12, None, False)
            return
        last, when, name = self.tip_read
        if last != session or now - when >= 2.0:
            name = self.titles.title(session, now)
            if last != session or name != self.tip_read[2]:
                log("circle %d: %s" % (self.talks[session]["n"], name or "(no name found)"))
            self.tip_read = (session, now, name)
        n = self.talks[session]["n"]
        agent = self.talk_agent(session, now)
        label = AGENT_INFO.get(agent, {}).get("label", agent)
        state = {"busy": tr("在忙", "working"), "wait": tr("等你回复", "your turn"), "done": tr("做完了", "done"),
                 "error": tr("出错停下了", "stopped on an error"), "cut": tr("被打断了", "interrupted"),
                 "idle": tr("在忙", "working")}[self.talk_state(session)]
        if not name:
            name = tr("对话", "Conversation") + (" (%s)" % label if agent else "")
        elif agent and len(set(self.talk_agent(s) for s in self.talks) - {""}) > 1:
            name = "%s · %s" % (label, name)   # circles of several agents: whose this one is (a click goes there)
        text = "%s %s · %s" % ("\u2460\u2461\u2462\u2463\u2464\u2465\u2466\u2467\u2468"[n - 1], name, state)
        x0, y0 = self.dots.put[1]
        gap = max(3, d // 4)                   # under the row, off the pets (用户: it hid them); over it only when
        below = y0 + self.dots.h + gap         # the screen ends there
        wa = self.leader._work_area(x0 + cx, y0)
        if below + max(self.dot_tip.h, d) <= wa.bottom:
            self.dot_tip.update(now, None, text, int(round(clamp(0.62 * d, 12, 22))), (x0 + cx, below), True, 1.0)
        else:
            self.dot_tip.update(now, None, text, int(round(clamp(0.62 * d, 12, 22))), (x0 + cx, y0 - gap), True, 0.0)

    def tab_run(self, what, args, force=False):
        """clawd_tabs.ps1 in the background, one at a time.  what: (mode, session, window), looked at in tab_done
        when it is over.  A reading (which tab you typed in) is never cut short or put after a click: it has to see
        the tab of that moment, and a click killing it left that conversation with no tab (a click soon after a
        message, or many clicks, then only brought the window).  So a click (force) waits for the readings, and
        replaces a click under way or waiting."""
        import subprocess
        if self.tab_job is not None or (force and self.tab_next is not None):
            if not force:
                self.tab_next = (what, args)   # the latest reading waits for the one under way
                return
            if self.tab_job is not None and self.tab_job[0][0] != "selected":
                try:
                    self.tab_job[1].kill()     # the click before this one: this one instead
                except OSError:
                    pass
                self.tab_job = None
            if self.tab_job is not None or self.tab_next is not None:
                self.tab_click = (what, args)  # after the reading(s): a second or so
                if self.tab_job is None:
                    self._tab_after()
                return
        if MAC:
            self._tab_run_mac(what, args)
            return
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clawd_tabs.ps1")
        if self.tab_shells is None:
            self.tab_shells = tab_shells()
            log("tabs: with %s" % (self.tab_shells[0] if self.tab_shells else "no PowerShell found"))
        while self.tab_shells:
            shell = self.tab_shells[0]
            if not os.path.isfile(script):
                log("tabs: no %s" % script)
                return
            try:
                # its errors to stdout too: a run that fails says why in the log (it was silent, 2026-11-15)
                proc = subprocess.Popen([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script] + args,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        creationflags=CREATE_NO_WINDOW)
            except OSError as e:
                self.tab_shells.pop(0)
                log("tabs: %s did not start (%s)%s" % (shell, e, "; now %s" % self.tab_shells[0] if self.tab_shells else ""))
                continue
            self.tab_job = (what, proc, time.perf_counter(), args)
            if self.opts.get("debug"):
                log("tabs: %s %s started" % (what[0], " ".join(args[1:])))
            break

    def _tab_run_mac(self, what, args):
        """macOS: only clicks ("select", the app's pid, the tab's device: _tab_of): the AppleScript of that terminal
        (tab_osascript) in the background, as the PowerShell run; tab_done reads what it said."""
        import subprocess
        pid, tty = int(args[1]), args[2]
        cmd = tab_osascript(macsys.app_bundle_id(pid), tty)
        if cmd is None:
            log("tabs: no tab of %s to choose in app %d" % (tty, pid))
            return
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    **child_kw())
        except OSError as e:
            log("tabs: osascript did not start (%s)" % e)
            return
        self.tab_job = (what, proc, time.perf_counter(), args)
        if self.opts.get("debug"):
            log("tabs: %s %s started" % (what[0], " ".join(args[1:])))

    def _tab_done_mac(self, session, pid, out, rc):
        """macOS: what osascript said.  Refused (the user did not let the pets control that terminal: -1743, said in
        the log once) or no such tab: the app is brought forward, as the click did already, and that is all."""
        n = self.talks.get(session, {}).get("n")
        if rc == 0 and out == "ok":
            log("circle %s: tab selected" % n)
            return
        if "-1743" in out:
            if not self.tab_refused:
                self.tab_refused = True
                log("tabs: macOS did not let the pets control the terminal (Automation refused, -1743): its window "
                    "only (System Settings > Privacy & Security > Automation lets them)")
        elif rc == 0 and out == "gone":
            log("circle %s: tab not found: just its window" % n)
        else:
            log("tabs: osascript failed (exit %s: %s): just its window" % (rc, " ".join(out.split())[:160]))
        if macsys.frontmost_pid() != pid:
            talk_window_front(pid)

    def tab_done(self):
        what, proc, t0, args = self.tab_job
        if proc.poll() is None:
            if time.perf_counter() - t0 > (TAB_WAIT_MAC if MAC else 10.0):
                proc.kill()
                log("tabs: %s took too long" % what[0])
                self.tab_job = None
                self._tab_after()
            return
        out = (proc.stdout.read() or b"").decode("utf-8", "ignore").strip()
        self.tab_job = None
        mode, session, hwnd = what
        if MAC:
            self._tab_done_mac(session, hwnd, out, proc.returncode)
            self._tab_after()
            return
        if proc.returncode and out not in ("ok", "gone") and not all(c.isdigit() or c == "." for c in out or "x"):
            # the PowerShell itself did not run (not "no such tab", not the script's own "error"): the next one
            bad = self.tab_shells.pop(0) if self.tab_shells else "?"
            log("tabs: %s failed (exit %s: %s)%s" % (bad, proc.returncode, " ".join(out.split())[:160],
                                                     "; now %s" % self.tab_shells[0] if self.tab_shells else "; no PowerShell left"))
            if self.tab_shells:
                self.tab_run(what, args, force=(mode == "select"))
                return
        if mode == "selected" and out and all(c.isdigit() or c == "." for c in out):
            if self.talk_tab.get(session) != (hwnd, out):
                self.talk_tab[session] = (hwnd, out)
                log("conversation %s is in tab %s of window %d" % (session, out, hwnd))
        elif mode == "selected":
            log("tabs: no tab read in window %d for %s (%r, exit %s)" % (hwnd, session, out[:60], proc.returncode))
        elif mode == "select":
            # "gone" leaves the tab remembered: it was once said of a tab still open (two circles clicked by turns),
            # and forgetting it made every later click only bring the window; a tab really closed costs a try a click,
            # and the conversation's next message says its tab anew
            log("circle %s: tab %s" % (self.talks.get(session, {}).get("n"), {"ok": "selected", "gone": "not found: just its window"}.get(out, out or "?")))
        self._tab_after()

    def _tab_after(self):
        """The next job: a waiting reading first, then a waiting click."""
        if self.tab_next is not None:
            nxt, self.tab_next = self.tab_next, None
            self.tab_run(*nxt)
        elif self.tab_click is not None:
            nxt, self.tab_click = self.tab_click, None
            self.tab_run(*nxt, force=True)

    def _claude_kind(self, session, now):
        """"desk" / "cli" for a Claude Code conversation (TalkTitles.claude_kind), None for another agent's"""
        if self.talk_agent(session, now) not in ("", "claude"):
            return None
        try:
            return self.titles.claude_kind(session)
        except Exception:
            log_exc("a conversation's kind")
            return None

    def _way(self, session, now):
        """Where a click on this conversation's circle goes, one rule for each kind (2026-11-15; it was pieced
        together from guesses, and each fix of one guess let another one through):
          Claude's desktop app (told by its hook / transcript), Codex's desktop app: its window, and its link opens
            that very conversation ("open": not when it is the one shown already: the app came up twice)
          a terminal (Claude's told so; another agent's by its window): its window, and in Windows Terminal its tab
          DeepSeek, Antigravity (one window, no link to one conversation): their window; from the tray if hidden
        -> {"code", "hwnd", "link", "tab", "agent", "kind"}; code: none / link-app / tab / window / link / open /
        tray-show / tray-link / hidden.  Nothing is done here but finding (talk_jump does, talk_report tells)."""
        where = self.talk_where.get(session, (None, ""))
        agent = self.talk_agent(session, now)
        kind = self._claude_kind(session, now)
        hwnd = where[0] if where[0] and talk_window_alive(where[0]) else None
        term = bool(hwnd) and talk_is_terminal(hwnd)
        if kind == "desk" and term:
            hwnd, term = None, False           # resumed in its desktop app since its terminal said where it was
        elif kind == "cli":
            term = True
        w = {"agent": agent, "kind": kind or ("term" if term else ""), "hwnd": hwnd, "link": None, "tab": None}
        # a conversation in a terminal stays there: its app's link would open it somewhere else (Codex's CLI and app
        # share their threads)
        link = None if term else self.titles.link(session, agent, now)
        w["link"] = link
        if not hwnd and link:
            # not known yet (the pets started after its last message, its app opened anew): its app's window is the
            # one (up at once; the link alone waited for the app to come up by itself)
            hwnd = app_window(link.split(":", 1)[0])
            if hwnd:
                self.talk_where[session] = (hwnd, where[1])
                log("conversation %s: its window not known yet, its app's is %d" % (session, hwnd))
            w["hwnd"] = hwnd
        if not hwnd:
            w["code"] = "link-app" if link else "none"
            return w
        hidden = not talk_window_visible(hwnd)
        tab = self._tab_of(session)
        if hidden and AGENT_INFO.get(agent, {}).get("hides"):
            code = "tray-show"                 # DeepSeek only hides its one window: shown again at once
        elif hidden:
            code = "tray-link" if link else "hidden"
        elif term and tab and tab[0] == hwnd:
            code, w["tab"] = "tab", tab[1]     # a tab of Windows Terminal: that very tab (by its id: a rename keeps it)
        elif link and link in [a.get("open") for a in AGENT_INFO.values()]:
            code = "window"                    # one app, one window (DeepSeek, Antigravity): the window is all there is
        elif link and link.startswith("claude:") and not self._link_moving(link, now) and self.titles.open_now(session):
            code = "open"
        elif link:
            code = "link"
        else:
            code = "window"
        w["code"] = code
        return w

    def _tab_of(self, session):
        """-> (window, tab) where this conversation was typed in last, or None: Windows Terminal's tab, read when its
        message came (tab_run "selected"); on macOS the device its "at" line said (talk_wt: "ttys013"), in Terminal or
        iTerm2 (the app of that line)."""
        if not MAC:
            return self.talk_tab.get(session)
        pid, tty = self.talk_where.get(session, (None, ""))[0], self.talk_wt.get(session, "")
        if pid and MAC_TTY.match(tty) and talk_window_class(pid) == TERMINAL_CLASS:
            return (pid, tty)
        return None

    def _way_text(self, w, zh=True):
        """What a click does, in a few words (talk_report; the log has the English)"""
        c, kind = w["code"], w["kind"]
        if c == "window" and kind in ("cli", "term"):
            if talk_window_class(w["hwnd"]) == TERMINAL_CLASS:
                return tr("拉它的终端窗口（标签还没记下：在那个标签里发一条消息就记下）",
                          "its terminal's window (its tab not known yet: a message sent in that tab tells)") if zh \
                    else "its terminal's window, its tab not known"
            return tr("拉它的终端窗口", "its terminal's window") if zh else "its terminal's window"
        term = talk_terminal_name(w["hwnd"]) if c == "tab" else ""
        texts = {"none": ("它的窗口还不知道（它下一次发消息时记下）", "its window not known yet (its next message tells)"),
                 "link-app": ("打开它的链接（程序的窗口没找到）", "its link (its app's window not found)"),
                 "tab": ("切到它在 %s 里的标签" % term, "its tab in %s" % term),
                 "window": ("拉它的窗口", "its window"),
                 "link": ("拉窗口，打开它的链接", "its window, and its link"),
                 "open": ("拉窗口（它就是桌面版里正开着的那个）", "its window (the conversation shown there already)"),
                 "tray-show": ("从托盘显示它的窗口", "its window, shown from the tray"),
                 "tray-link": ("窗口在托盘里：打开它的链接", "its window in the tray: its link"),
                 "hidden": ("窗口藏着，打不开", "its window hidden, nothing to open it with")}
        zh_, en = texts.get(c, (c, c))
        return tr(zh_, en) if zh else en

    def _kind_text(self, w, zh=True):
        say = (lambda a, b: tr(a, b)) if zh else (lambda a, b: b)
        agent, kind = w["agent"], w["kind"]
        label = AGENT_INFO.get(agent, {}).get("label", agent or say("对话", "conversation"))
        if agent in ("", "claude", "codex") and kind:
            if kind == "desk" or (agent == "codex" and kind != "term"):
                where = say("桌面版", "desktop app")
            else:
                tabs = w["hwnd"] and talk_window_class(w["hwnd"]) == TERMINAL_CLASS
                where = say("终端", "terminal") + (" (%s)" % talk_terminal_name(w["hwnd"]) if tabs else "")
            return "%s %s" % (label if agent else "Claude", where)
        return label

    def talk_jump(self, session, now):
        """A click on a circle: there (_way), and one line in the log says which way and why."""
        n = self.talks.get(session, {}).get("n")
        w = self._way(session, now)
        code, hwnd, link = w["code"], w["hwnd"], w["link"]
        log("circle %s (%s) way: %s, %s" % (n, session, self._kind_text(w, zh=False), self._way_text(w, zh=False)))
        if code == "none":
            log("circle %s (%s) clicked: its window is not known" % (n, session))
            return
        if code == "link-app":
            self.open_link(link, n, now)
            return
        shown = False
        if code == "tray-show":
            # DeepSeek: showing that window is all dsh://open would do, without starting a second copy of the app to
            # pass it on (about 2 s; 用户: slow)
            talk_window_show(hwnd)
            shown = talk_window_visible(hwnd)
        hidden = not talk_window_visible(hwnd)     # closed to the tray (its app still runs): only it can show it again
        talk_window_restore(hwnd)
        ok = False if hidden else talk_window_front(hwnd)
        log("circle %s (%s) clicked: window %d %s" % (n, session, hwnd, "hidden (in the tray)" if hidden
                                                    else ("shown from the tray, " if shown else "") + "to the front"
                                                    + ("" if ok else " (refused)")))
        if code == "tab":
            self.tab_run(("select", session, hwnd), ["select", str(hwnd), w["tab"]], force=True)
        elif code in ("link", "tray-link"):
            if self.link_last[0] == link and now - self.link_last[1] < 2.0:
                log("circle %s: the same link a moment ago, not again" % n)    # two quick clicks: the app once
            else:
                self.open_link(link, n, now)   # (hidden: the link brings the app's window back, at that conversation)
        elif code == "open":
            log("circle %s: already the conversation open in its app, no link" % n)

    def talk_report(self, now):
        """clawd circles: each circle, what it is and where a click on it goes (_way, as a click would find it),
        in circles.txt beside the event file."""
        lines = []
        for session, t in sorted(self.talks.items(), key=lambda kv: kv[1]["n"]):
            try:
                w = self._way(session, now)
                name = self.titles.title(session, now) or tr("（没找到名字）", "(no name found)")
                state = {"busy": tr("在忙", "working"), "wait": tr("等你回复", "your turn"), "done": tr("做完了", "done"),
                         "error": tr("出错停下了", "stopped on an error"), "cut": tr("被打断了", "interrupted"),
                         "idle": tr("在忙", "working")}[self.talk_state(session)] if self.leader is not None else ""
                lines.append("%s %s · %s · %s  (%s)" % ("①②③④⑤⑥⑦⑧⑨"[t["n"] - 1], name, self._kind_text(w), state, session))
                lines.append("   %s%s" % (tr("点了：", "a click: "), self._way_text(w)))
            except Exception:
                log_exc("clawd circles")
                lines.append("%d (%s): ?" % (t["n"], session))
        if not lines:
            lines = [tr("现在没有圆圈。", "No circles now.")]
        try:
            with open(os.path.join(HOME_DIR, "circles.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            log("circles.txt not written (%s)" % e)

    def _link_moving(self, link, now):
        """True while another link of this app was opened a moment ago: the app is about to go there, and which
        conversation it shows now says nothing of where it will be (so the click opens its own link, which goes after
        that one and wins)."""
        last, when = self.link_last
        return (last is not None and last != link and now - when < LINK_SETTLE
                and last.split(":", 1)[0] == link.split(":", 1)[0])

    def talk_agent(self, session, now=None):
        """Which agent a conversation is: its "at" line says, or else where its name was found (before its next
        message after the pets started)."""
        agent = self.talk_where.get(session, (None, ""))[1]
        if not agent:
            kind = (self.titles.where.get(session) or ("",))[0]
            agent = KIND_AGENT.get(kind, "")
        return agent

    def open_link(self, link, n, now):
        """In the background: the app takes a second or so to take it, and the pets go on meanwhile.  The app brings
        its window up again when it has taken it, so a link is opened only when the conversation is not the one shown
        (else you minimise it and up it comes)."""
        import queue, threading
        self.link_last = (link, now)
        if self.link_q is None:
            # one thread, the links in the order of the clicks: two threads raced, and the app could get the later
            # click's link first and end at the earlier one
            self.link_q = queue.Queue()

            def go():
                while True:
                    link_, n_ = self.link_q.get()
                    try:
                        open_url(link_)
                        log("circle %s: opened %s" % (n_, link_))
                    except OSError as e:
                        log("circle %s: %s did not open (%s)" % (n_, link_, e))
            threading.Thread(target=go, daemon=True).start()
        self.link_q.put((link, n))

    def _asks_to_see(self, tok):
        """clawd do <action or combo>: the user wants to see it, so the family shows first."""
        if tok.startswith("combo:"):
            return tok[6:] in COMBOS
        if tok == "play" or tok.startswith("play:"):
            return True
        big = self.leader
        return (tok not in SEMANTIC and (tok in big.store.meta or tok in SHOT_FALLBACK)
                and not internal(tok))

    # ----------------------------------------------------------- activity
    def set_activity(self, name, now, why):
        """How often they find something to do by themselves; the next waits start over at the new pace."""
        global ACTIVITY
        if name not in ACTIVITY_PACE or name == ACTIVITY:
            return
        ACTIVITY = name
        log("activity: %s (%s)" % (name, why))
        o = self.opts
        self.combo_range = paced(o["combo_range"])
        self.play_range = paced(o["play_range"])
        self.mimic_range = paced(o["mimic_range"])
        self.wake_range = paced(o["wake_range"])
        self.peek_after = o["peek_after"] * ACTIVITY_PACE[name]
        self.next_combo = now + random.uniform(*self.combo_range)
        self.next_play = now + random.uniform(*self.play_range)
        self.next_mimic = now + random.uniform(*self.mimic_range)
        if self.wake_due is not None:
            self.wake_due = now + random.uniform(*self.wake_range)
        if name == "quiet":
            self.combo_queue = None
        for pet in self.pets:
            pet.extra_range = paced(o["extra_range"])
            pet.wander_range = paced(o["wander_range"])
            pet.next_extra = now + random.uniform(*pet.extra_range)
            pet.next_wander = now + random.uniform(*pet.wander_range)
        self.save_state()

    def activity_menu(self):
        """A submenu of the three, the current one ticked (the caller attaches it; ids ID_ACTIVITY_BASE + i)."""
        m = CreatePopupMenu()
        if m:
            for i, (code, zh, en) in enumerate(ACTIVITIES):
                AppendMenuW(m, MF_STRING | (MF_CHECKED if code == ACTIVITY else 0), ID_ACTIVITY_BASE + i, tr(zh, en))
        return m

    # ----------------------------------------------------------- hidden / shown
    def set_hidden(self, on, now, why, reason="user"):
        was = bool(self.hidden)
        if on:
            self.hidden.add(reason)
        else:
            self.hidden.discard(reason)
        if bool(self.hidden) != was:
            if self.hidden:
                self._hide(now, why)
            else:
                self._show(now, why)
            self.save_state()
        if self.tray is not None:
            self.tray.update()

    def _hide(self, now, why):
        log("hidden (%s)" % why)
        self.cancel_combo("hidden", now, instant=True)
        self.end_sign(now, "hidden")
        self.sign_board.hide_now()
        self.dots.hide_now()
        self.dot_tip.hide_now()
        self.nap = None
        self.nap_done = True                   # shown again: not straight back into it
        for pet in self.pets:
            pet.hide_window(now)
        self.cancel_combo("hidden", now, instant=True)   # one a drop let go of might have started
        self.combo_queue = None
        self.wake_due = None
        self.think_since = None
        for pet in self.pets:
            pet.wander = None
            pet.glide = None

    def _show(self, now, why):
        log("shown (%s)" % why)
        for pet in self.pets:
            pet.show_window(now)
        self.touch(None, now, wake=False)
        self.depth_dirty = True
        self.next_combo = now + random.uniform(*self.combo_range)
        self.next_play = max(self.next_play, now + self.play_range[0])
        self.next_mimic = max(self.next_mimic, now + self.mimic_range[0])
        big = self.leader
        if big is not None and big.attention_until:
            self.show_sign("attention", now, None, session=big.attention_session)    # still waiting for you: say so again
        elif big is not None and big.busy and big.busy_clip == "work_compact":
            self.show_sign("compact", now, None)

    # ----------------------------------------------------------- sign
    def _sign_text(self, kind, args=None):
        if kind == "levelup":
            return tr("升级啦！Lv.%d" % args["level"], "Level up! Lv.%d" % args["level"])
        if kind == "gift":
            zh, en = next(g[2] for g in LEVEL_GIFTS if g[1] == args["gift"])
            return tr(("补发：%s" if args["back"] else "礼物：%s") % zh, ("Late gift: %s" if args["back"] else "Gift: %s") % en)
        if kind == "discover":
            if "item" in args:
                zh, en = args["zh"], args["en"]
                rz, re_ = RARITY_NAMES.get(args["rarity"], ("", ""))
                return tr("捡到了：%s%s" % (zh, "（%s）" % rz if rz else ""), "Found: %s%s" % (en, " (%s)" % re_ if re_ else ""))
            if "act" in args:
                zh, en = GROW_ACTS[args["act"]]
                return tr("新发现：%s！" % zh, "New: %s!" % en)
            if "album" in args:
                return tr("图鉴收集 %d%%！" % args["album"], "Album %d%% found!" % args["album"])
            if "slip" in args:
                zh, en = SLIPS[args["slip"]][1]
                return tr("新发现：%s！" % zh, "New: %s!" % en)
            zh, en = GROW_NAMES.get(args["name"], (args["name"], args["name"]))
            if args.get("stars"):
                stars = "★" * args["stars"]
                return tr("%s %s 熟练了！" % (zh, stars), "%s %s Well practised!" % (en, stars))
            return tr("新发现：%s！" % zh, "New: %s!" % en)
        zh, en = SIGN_TEXTS[kind]
        secs = self.leader.turn_secs if kind == "stop" else None
        if secs is None:
            return tr(zh, en)
        if secs < 60:
            n = max(1, int(round(secs)))
            return tr("%s用了 %d 秒" % (zh, n), "%s %d s" % (en, n))
        m = int(round(secs / 60.0))
        if m < 60:
            return tr("%s用了 %d 分钟" % (zh, m), "%s %d min" % (en, m))
        return tr("%s用了 %d 小时 %d 分" % (zh, m // 60, m % 60), "%s %d h %d min" % (en, m // 60, m % 60))

    def _sign_holder(self):
        """The smallest one with nothing of its own to do (a walk or an idle extra is nothing, a reaction gives way);
        None: the board goes over the big one's head.  A sign is news, not one pet's job: it never cuts short the
        小剧场, a game, copying the big one or what you asked for."""
        for pet in sorted(self.pets[1:], key=lambda p: -p.slot):
            if (pet.dragging or pet.press is not None or pet.in_combo or pet.hop is not None or pet.perch is not None
                    or any(p.perch is pet for p in self.pets) or pet.render is not None or pet.dozing):
                continue                       # one dozing is left to doze: the board goes elsewhere
            r, what = self.chore(pet)
            if r < R_BASE and what not in ("a reaction", "watching"):    # one that came to watch stands by idle
                continue
            if all(pet.store.usable(c) for c in SIGN_CLIPS):
                return pet
        return None

    def _sign_event(self, tok, now, said=""):
        """What the big one is up to, in words: a tool when it changes, the end of a turn, an error, a question.
        said: the conversation the token is from (with several, the sign says its number)."""
        big = self.leader
        if tok in ("listen", "stop", "stopfail"):
            self.sign_last_tool = None         # a new turn: its first tool gets a sign again
        if (tok == "listen" and self.sign is not None and self.sign["kind"] in ("stop", "stopfail")
                and self.sign.get("session") in (None, "", said)):
            self.end_sign(now, "a new message")    # it is old news once you write again (in that conversation)
        if tok == "bye":
            self.end_sign(now, "bye")
            return
        if tok == "listen":
            return
        if tok not in SIGN_TEXTS or tok == "think":    # a think comes after every tool: see _think_tick
            return
        self._sign_expire(now)
        if tok in SIGN_TOOLS:
            if (tok, said) == self.sign_last_tool:
                return                         # the same kind of tool again (of that conversation): it was said already
            self.sign_last_tool = (tok, said)
        elif tok == "attention" and not big.attention_until:
            return
        over_head = tok == "stopfail" or (tok == "stop" and big.reacted == "celebrate")   # the others come to it
        secs = SIGN_TOOL_SECS if tok in SIGN_TOOLS else SIGN_DONE_SECS if tok in ("stop", "stopfail") else None
        self.show_sign(tok, now, secs, over_head, None, session=said)

    def talk_mark(self, session):
        """The conversation's number as its sign says it (the circle's), "" while there are no circles."""
        t = self.talks.get(session) if session else None
        if t is None or len(self.talks) < TALK_MARK_FROM:
            return ""
        return "\u2460\u2461\u2462\u2463\u2464\u2465\u2466\u2467\u2468"[t["n"] - 1] + " "

    def show_sign(self, kind, now, secs, over_head=False, args=None, session=""):
        s = self.sign
        session = session or (args or {}).get("session", "")
        text = self.talk_mark(session) + self._sign_text(kind, args)
        if s is not None:
            if SIGN_RANK[kind] < SIGN_RANK[s["kind"]]:
                return False                   # a tool does not cover a question or the end of a turn
            s.update(kind=kind, text=text, lang=LANG, secs=secs, until=None if secs is None else now + secs, args=args, session=session)
            if self.opts["debug"]:
                log("sign now: %s" % text)
            return True
        if SIGN_RANK[kind] == 1 and self.sign_down_tool and now - self.sign_down_at < SIGN_GAP:
            return False                       # a tool's sign just down: not up again for every quick tool
        holder = None if over_head else self._sign_holder()
        clip = None
        if holder is not None:
            big = self.leader
            side = -1 if holder.fx <= big.fx else 1    # on its outer side, away from the big one ...
            wa = holder._work_area(holder.fx, holder.fy)
            room = 1.2 * big._target_px()              # ... unless the screen ends there: the board would not fit
            if side < 0 and holder.fx - wa.left < room:
                side = 1
            elif side > 0 and wa.right - holder.fx < room:
                side = -1
            clip = "sign_left" if side < 0 else "sign_right"
            self.took(holder, "the sign", now, R_WORK)
            holder.wander = None
            holder.react = None
            holder.extra_wanted = None
            holder.signing = True
            holder._wake(now, plays=False)
            holder.request(clip, now, "sign", until=now + 3600.0)       # down when the sign ends
        self.sign = {"kind": kind, "text": text, "lang": LANG, "secs": secs, "until": None if secs is None else now + secs,
                     "up_at": None, "holder": holder, "clip": clip, "args": args, "session": session}
        if self.opts["debug"]:
            log("sign up: %s (%s)" % (text, "pet%d" % holder.slot if holder else "over the big one"))
        return True

    def end_sign(self, now, why):
        s = self.sign
        if s is None:
            return
        self.sign = None
        self.sign_down_at = now
        self.sign_down_tool = s["kind"] in SIGN_TOOLS
        h = s["holder"]
        if h is not None:
            h.signing = False
            if h.pending is not None and h.pending[0] == s["clip"]:
                h.pending = None
            if h.cur == s["clip"] and h.cur_until is not None:
                h.cur_until = now              # leaves its hold at the next tick: the stick comes down
        if self.opts["debug"]:
            log("sign down (%s)" % why)

    def _sign_expire(self, now):
        """End a sign whose time is over, whose question was answered or whose compact is done."""
        s = self.sign
        if s is None:
            return
        big = self.leader
        h = s["holder"]
        if s["kind"] == "attention" and not big.attention_until:
            self.end_sign(now, "answered")
        elif s["kind"] == "compact" and not (big.busy and big.busy_clip == "work_compact"):
            self.end_sign(now, "compact over")
        elif s["until"] is not None and now >= s["until"]:
            self.end_sign(now, "time")
        elif h is not None and (h not in self.pets or h.dragging or h.in_combo or h.hop is not None or h.perch is not None):
            self.end_sign(now, "holder taken")
        elif h is not None and h.cur != s["clip"] and not (h.pending is not None and h.pending[0] == s["clip"]):
            self.end_sign(now, "holder does something else")
        elif h is None and big.dragging:
            self.end_sign(now, "big one taken")

    def _think_tick(self, now):
        """Long thought with no tool in between: "thinking..." now and then.  A think event comes after every
        tool, so the time counts from when the big one shows only thinking (or listening, before the first tool)."""
        big = self.leader
        if not (big.busy and big.busy_clip in ("think", "listen")):
            self.think_since = None
            return
        if self.think_since is None:
            self.think_since = now
        if (now - self.think_since >= SIGN_THINK_AFTER and now - self.think_signed >= SIGN_THINK_EVERY
                and self.sign is None):
            self.think_signed = now
            self.show_sign("think", now, SIGN_DONE_SECS)

    def sign_tick(self, now):
        self._think_tick(now)
        s = self.sign
        if s is None and not self.sign_board.shown:
            return
        self._sign_expire(now)
        s = self.sign
        big = self.leader
        at, visible, text = None, False, None
        if s is not None:
            if s["lang"] != LANG:              # the language was switched while it is up: the words follow
                s["text"], s["lang"] = self.talk_mark(s.get("session")) + self._sign_text(s["kind"], s["args"]), LANG
                if self.opts["debug"]:
                    log("sign now: %s" % s["text"])
            text = s["text"]
            h = s["holder"]
            if h is not None:
                hb = h._hold_bounds(len(h.cur_frames)) if h.cur == s["clip"] else None
                visible = (hb is not None and h.cur_kind == KIND_HOLD and h.last_idx >= hb[0])
                top = h.store.meta.get(s["clip"], {}).get("top")
                if top:
                    at = (h.fx + (top[0] - h.ax) * h.disp, h.fy + (top[1] - h.ay) * h.disp)
            else:
                visible = not big.dragging and big.hwnd is not None
                l, t, r, b = big.bbox
                at = (big.fx, big.fy + (t - big.ay) * big.disp - 0.08 * big._target_px())
            if visible and s["up_at"] is None:
                s["up_at"] = now               # the time counts from when it can be read
                if s["secs"] is not None:
                    s["until"] = now + s["secs"]
        # the words in proportion to the one that holds the board (the big one when it floats over its head),
        # never too small to read
        who = s["holder"] if s is not None and s["holder"] is not None else big
        px = int(round(clamp(0.2 * who._target_px(), 12, 26)))
        deco = self._grow_deco(s, now) if s is not None and s["kind"] in SignBoard.GROW_STYLE else None
        self.sign_board.update(now, s["kind"] if s else None, text, px, at, visible,
                               0.28 if s is not None and s["holder"] is not None else 0.0, deco)

    # ----------------------------------------------------------- 养成
    def grow_gain(self, n, why, now):
        if n <= 0 or self.replaying:
            return
        if self.grow.add(n, why):
            self.grow.save()                   # a new level is written down at once
            if self.tray is not None:
                self.tray.update()             # its tip says the level

    # ----------------------------------------------------------- 干活时间
    def work_tick(self, now):
        """Each tick, hidden or not: every turn at work (Pet.at_work) adds the tick to its own work time (its XP, its
        digs by themselves); and once, however many are at work, to the clock of the digs by hand, if one of them
        has begun a tool (a turn that only talks earns nothing)."""
        last, self.work_at = self.work_at, now
        dt = 0.0 if last is None else now - last
        if dt <= 0.0 or dt > WORK_TICK_MAX or self.replaying:
            return
        big = self.leader
        tooled = False
        for session, turn in big.working.items():
            if big.at_work(session, turn, now):
                turn["work"] = turn.get("work", 0.0) + dt
                tooled = tooled or bool(turn.get("tooled"))
        if tooled:
            self.work_last = now
            self.grow_work(dt)

    def work_first_tool(self, turn, now, counts=True):
        """A turn begins its first tool: from now on its work time counts for the digs by hand, and what it worked
        before (its message read, thought over) too: the part no other turn counted already."""
        turn["tooled"] = True
        if not counts or self.replaying:
            return
        back = min(turn.get("work", 0.0), now - max(turn.get("grow_since", turn["since"]), self.work_last))
        if back > 0.0:
            self.work_last = now
            self.grow_work(back)

    @grow_safe
    def grow_work(self, secs):
        if self.grow.work(secs, self.chance_work):
            log("dig: work earned a chance to dig by hand (%d now)" % self.grow.data["chances"])

    def dig_most(self):
        """Digs by themselves a turn at most: as many as the chances that can be kept at the level (3, 4, 5)."""
        return self.opts["dig_most"] or dig_cap(self.grow.level)

    def dig_owed(self, turn):
        """Digs by themselves this turn has earned (one each dig_every s of its work time, once it has begun a tool)
        and not had yet."""
        if turn is None or not turn.get("tooled"):
            return 0
        return max(0, min(self.dig_most(), int(turn.get("work", 0.0) // self.dig_every)) - turn.get("dug", 0))

    def pending_finds(self):
        """What is put away in turns not over yet: drawn as theirs already (Grow.roll, _special)."""
        return [item for item, _ in self.loot]

    @grow_safe
    def grow_turn(self, turn, failed, now, how=""):
        """A turn is over (stop, stopfail, cut by you): its XP for its work time (Grow.turn); in a test home without
        a clock for the digs by hand (chance_work 0), a chance; and its digs by themselves no small one got to (none
        free, or no small one at all): the big one pulls those out itself, each as likely."""
        if self.replaying:
            return
        self.grow_stop_at = now
        secs = 0.0 if turn is None else turn.get("work", 0.0)
        xp = self.grow.turn(secs, 0 if turn is None else turn.get("tools", 0), failed, how)
        self.grow_gain(xp, "turn", now)
        if xp > 0 and self.chance_work <= 0:
            self.grow.earn_chance(secs, self.chance_work, how != "interrupted")
        owed = self.dig_owed(turn) if xp > 0 else 0
        if owed and self.can_dig(self.leader):
            turn["dug"] = turn.get("dug", 0) + owed
            force = self.opts["dig_find"]
            names = self._items()
            for _ in range(owed):
                if force == "no" or (force is None and random.random() >= DIG_SELF_LUCK):
                    continue
                item = force if force in names else (self._special(now, secs) or self.grow.roll(self._pool(), self.pending_finds()))
                if item in names:
                    self.loot.append((item, None))
                    log("dig: pet0 has a find of its own (%s), %d digs no one got to in %.0fs of work" % (item, owed, secs))
            self._loot_keep()
        if self.loot and self.loot_due is None:
            self.loot_due = now                # shown once the "done" sign is down (_loot_tick)
        if not self.leader.working:
            self.turn_marks = set()

    @grow_safe
    def grow_agent(self, now):
        """A helper back (agent_done): counts in the album ("派出的帮手") and gives XP.

        Known quirk, left as is (2026-11-17): the count runs high with Claude Code.  After each reply Claude Code runs
        small background tasks of its own (most likely memory extraction or the next-prompt suggestion; they keep no
        transcript).  They end through the same code as a turn's Stop and carry an agent id, so they fire
        SubagentStop, but they never fire SubagentStart.  So most replies bring one agent_done that no agent word
        came before: it counts here, and the family nods or brings a note (Family follower rules) as for a real one.
        Codex and DeepSeek send their start and end in pairs; Antigravity has no start at all (clawd_hook.ag_words).
        A fix, if you want one: for agents that do send starts, keep per session how many helpers are out and take
        an agent_done only while one is (here, in Pet._semantic and in the follower reaction)."""
        if not self.replaying:
            self.grow.count("agents")
            self.grow_gain(GROW_XP["agent_done"], "helper back", now)

    @grow_safe
    def grow_fix(self, now):
        self.turn_marks.add("fix")
        if not self.replaying:
            self.grow.count("fixes")
            self.grow_gain(GROW_XP["fix"], "fixed after an error", now)

    @grow_safe
    def grow_play(self, why, now):
        if not self.replaying:
            self.grow_gain(self.grow.play(now, why), "play: " + why, now)

    def _grow_find(self, xp, why, now, after, **args):
        """XP with a mint sign of its own (a first find, a star): the sign waits its turn in grow_signs."""
        lv0, into0, need0 = self.grow.progress()
        self.grow_gain(xp, why, now)
        if xp <= 0:
            log("grow: %s" % why)
        lv1, into1, need1 = self.grow.progress()
        self.grow.save()
        args.update({"at": now + after, "gain": xp, "from": float(into0) / need0,
                     "to": float(into1) / need1 if lv1 == lv0 else 1.0})
        self.grow_signs.append(args)

    @grow_safe
    def _grow_combo(self, combo, now):
        """A combo played to its end: a find the first time (XP, a sign once it is over), counted every time (a
        star at 10, 30 and 100: XP and a sign), and a little XP if you set it up with your own hand."""
        name = combo["name"]
        if self.replaying or name == "treasure":       # 交宝贝 is how a find is shown, not a combo of the 图鉴
            return
        if self.grow.discover(name):
            self._grow_find(GROW_XP["discover"], "new: " + name, now, GROW_DISCOVER_AFTER, name=name)
        stars, xp = self.grow.played(name)
        if xp:
            self._grow_find(xp, "star %d: %s" % (stars, name), now, GROW_DISCOVER_AFTER, name=name, stars=stars)
        if name in SLIPS and self.grow.level >= slips_level() and self.grow.slip(name, bool(combo.get("slip"))):
            self._grow_find(GROW_XP["act"], "new 小插曲: " + name, now, GROW_DISCOVER_AFTER, slip=name)
        if combo.get("handmade"):
            self.grow_gain(self.grow.hand(now), "by hand: " + name, now)
        self.album_check(now)

    def album_cells(self):
        """-> [(id, found)]: the 图鉴's cells, as clawd_album.pyw lists them (ids as in its album.json)."""
        d, st = self.grow.data, self.leader.store
        out = [("item:" + n, n in d["items"]) for n in self._items()]
        out += [("combo:" + k, k in d["seen"] or d["combos"].get(k, 0) > 0) for k in ALBUM_COMBOS]
        acts = list(GROW_ACTS) + [a for a in ACTION_ORDER if a in st.meta and a not in GROW_ACTS] + list(ALBUM_ACTS_EXTRA)
        out += [("act:" + a, a in d["acts"]) for a in acts]
        return out

    def album_new(self):
        """How many found cells the 图鉴 has not shown you yet (its album.json); 0 before it was ever opened.  The
        gifts the level has brought too, once the album keeps them (its v 2: before, all you had counts as shown)."""
        try:
            with open(os.path.join(HOME_DIR, "album.json"), "r", encoding="utf-8") as f:
                d = json.load(f)
            seen = d.get("seen")
        except Exception:
            return 0
        if not isinstance(seen, dict):
            return 0
        n = sum(1 for i, found in self.album_cells() if found and i not in seen)
        if type(d.get("v")) is int and d["v"] >= 2:
            n += len(gift_news(seen, self.grow.level))
        return n

    @grow_safe
    def album_check(self, now):
        """How much of the 图鉴 is found: a mark reached for the first time (ALBUM_MARKS) is a find of its own, the
        family cheers when its sign goes up.  Several at once (an old family, the first time): one sign, all the XP.
        Only once the album has been opened (its album.json): the marks are of the book you look at."""
        if self.replaying or self.leader is None or not os.path.exists(os.path.join(HOME_DIR, "album.json")):
            return                             # the album was never opened: nothing to count yet
        cells = self.album_cells()
        if not cells:
            return
        pct = 100 * sum(1 for _, f in cells if f) // len(cells)
        marks = self.grow.data["album_marks"]
        new = [m for m, _ in ALBUM_MARKS if pct >= m and m not in marks]
        if not new:
            return
        marks.extend(new)
        marks.sort()
        self.grow.dirty = True
        xp = sum(x for m, x in ALBUM_MARKS if m in new)
        self._grow_find(xp, "album %d%% found" % max(new), now, GROW_DISCOVER_AFTER, album=max(new))

    @grow_safe
    def grow_act(self, clip, now):
        """A clip begins: written down the first time (for the 图鉴); one of the nine special ones is a find."""
        key = GROW_ACT_KEYS.get(clip, clip)
        if key in self.grow.data["acts"] or self.replaying or clip in COMBO_CLIPS or clip in BRING_CLIPS or clip in SIGN_CLIPS or clip in NAP_LOOKS:
            return
        if self.grow.act(key) and key in GROW_ACTS:
            self._grow_find(GROW_XP["act"], "new action: " + key, now, GROW_ACT_AFTER, act=key)
        self.album_check(now)

    @grow_safe
    def grow_tick(self, now):
        """The growth signs, one at a time and only when no other sign is up: a first find as soon as its combo is
        over (at work too: it covers no tool's sign for long), a level-up only when the big one is calm (never in
        the middle of a turn, and after the turn's own reaction).  A 小剧场 does not hold it up: like the other
        reactions, the cheer wakes one that dozes.  Hidden: they wait."""
        gap = SIGN_GAP if self.sign_down_tool else GROW_SIGN_GAP     # as long as a tool's sign would wait
        if (self.sign is not None or self.sign_board.shown or now - self.sign_down_at < gap or self.menu_open
                or self.opts["grow_quiet"]):
            return
        big = self.leader
        if big is None or big.dragging or big.hwnd is None:
            return
        if not self.album_looked or (self.album_recheck is not None and now >= self.album_recheck):
            self.album_looked, self.album_recheck = True, None
            self.album_check(now)
        if not self.gifts_looked:
            self.gifts_looked = True
            self.gifts_due(0, min(self.grow.data["level_shown"], self.grow.level), now, back=True)
        if self.grow_signs:
            a = self.grow_signs[0]
            cheer = "album" in a or a.get("cheer")
            if cheer and now >= a["at"] and (self.combo is not None or not big._calm()):
                return                         # the whole family cheers with it: a calm moment first
            if now >= a["at"] and self.show_sign("gift" if "gift" in a else "discover", now, GROW_DISCOVER_SECS, over_head=True, args=a):
                self.grow_signs.pop(0)
                if cheer and len(self.pets) >= 2 and self.start_combo("celebrate_all", now, manual=True, by_hand=False):
                    self.combo["grow"] = True  # not a first find of its own
            return
        if self.grow.level <= self.grow.data["level_shown"]:
            return
        if (self.combo is not None or self.combo_queue is not None or not big._calm()
                or now - self.grow_stop_at < GROW_AFTER_STOP or any(p.fly is not None or p.dragging for p in self.pets)):
            return                             # a high five a turn's end asked for goes first
        self._level_up(now)

    def _level_up(self, now):
        """The whole family cheers (those near enough: none is sent across the screen), the big one holds up the
        level; alone, it cheers by itself.  More than one level at once: the last."""
        lv, into, need = self.grow.progress()
        was = self.grow.data["level_shown"]
        self.grow.data["level_shown"] = lv
        self.grow.dirty = True
        self.grow.save()
        big = self.leader
        if len(self.pets) >= 2 and self.start_combo("celebrate_all", now, manual=True, by_hand=False):
            self.combo["grow"] = True          # not a first find of its own
        else:
            big.request(big._shot_name("celebrate"), now, "level up")
        log("grow: level up shown, Lv.%d" % lv)
        self.show_sign("levelup", now, GROW_LEVELUP_SECS, over_head=True,
                       args={"level": lv, "from": 0.0, "to": float(into) / need, "left": need - into})
        self.gifts_due(was, lv, now + GROW_LEVELUP_SECS, back=False)

    @grow_safe
    def gifts_due(self, lo, hi, now, back):
        """The gifts of the levels above lo up to hi that are made and not given yet: each holds up its sign in
        turn (back: 补发, a level reached before the gift was there).  Given is written down at once."""
        given = self.grow.data["gifts"]
        due = [g for g in LEVEL_GIFTS if lo < g[0] <= hi and g[1] not in given and g[1] not in GIFTS_LATER]
        for i, (lv, gid, name, line) in enumerate(due):
            given.append(gid)
            a = {"gift": gid, "back": back, "level": lv, "at": now + GIFT_AFTER + 0.5 * i, "gain": 0, "from": 0.0, "to": 1.0}
            if gid == "monument":              # the numbers of this day, for good; the whole family cheers once more
                self.grow.monument()
                a["cheer"] = True
            self.grow_signs.append(a)
            log("grow: gift %s (Lv.%d)%s" % (gid, lv, ", 补发" if back else ""))
        if due:
            self.grow.dirty = True
            self.grow.save()

    def set_look(self, arg, now):
        """A look of the plain signs (sign:<kind>=<name>), if the level has brought it: kept, and held up once."""
        kind, _, name = arg.partition("=")
        lv = look_level(kind, name)
        if lv is None or lv > self.grow.level:
            log("look: %s=%s not there (Lv.%d)" % (kind, name, self.grow.level))
            return
        self.look[kind] = name
        self.save_state()
        log("look: %s=%s" % (kind, name))
        if not self.hidden:
            self.show_sign("look", now, SIGN_LOOK_SECS)

    @grow_safe
    def _grow_deco(self, s, now):
        """What moves on a growth sign: the bar filling (eased), the chalk's shimmer, the words after the bar."""
        a = s["args"]
        t = 0.0 if s["up_at"] is None else now - s["up_at"]
        k = min(1.0, t / GROW_BAR_SECS)
        k = 1.0 - (1.0 - k) ** 3
        fill = round(a["from"] + (a["to"] - a["from"]) * k, 2)
        if s["kind"] == "levelup" and a["level"] >= LEVEL_MAX:
            label = tr("满级！", "Top level!")
            fill = 1.0
        elif s["kind"] == "levelup":
            label = tr("Lv.%d 还差 %d" % (a["level"] + 1, a["left"]), "%d to Lv.%d" % (a["left"], a["level"] + 1))
        elif s["kind"] == "gift":
            nxt = next_gift(a["level"])
            label = (tr("下一份 Lv.%d" % nxt[0], "next at Lv.%d" % nxt[0]) if nxt is not None else tr("全部到手！", "All of them!"))
        elif "item" in a:
            label = tr("新！经验 +%d" % a["gain"], "New! XP +%d" % a["gain"]) if a["new"] else "×%d" % a["count"]
        else:
            label = tr("经验 +%d" % a["gain"], "XP +%d" % a["gain"])
        return fill, int(t / GROW_PHASE_SECS) % GROW_PHASES, label

    def _followers_react(self, tok, now):
        # a small reaction is for those free for it: not one holding the sign, in a combo or in the 小剧场 (others jump)
        followers = [p for p in self.pets[1:] if not p.in_combo and not p.signing and not self.napping(p) and not self.digging(p)]
        reacted = self.leader.reacted
        rule = FOLLOWER_RULES.get((tok, reacted) if tok in ("stop", "fail") else tok)
        comfort = len(self.pets) >= 2 and (tok == "stopfail" or (tok == "fail" and reacted == "confused"))
        key = "comfort" if comfort else tok    # failures come quickly: the first must not hold back the comfort
        if rule is None or not (followers or comfort) or now - self.reacted_at.get(key, -1e9) < FOLLOWER_COOLDOWN:
            return
        self.reacted_at[key] = now
        if comfort and not self.menu_open and self.start_combo("comfort", now, manual=True, by_hand=False):
            return                             # the big one goes on working, the others come to it
        if (tok == "agent_done" and not self.menu_open and self.combo is None and now - self.last_note >= NOTE_COOLDOWN
                and self.start_combo("note", now, manual=True, by_hand=False, agent=True)):
            self.last_note = now               # a small one brings the big one what the sub-agent found
            big = self.leader                  # it takes the note: no nod before as well
            if big.pending is not None and big.pending[0] == big._shot_name("nod"):
                big.pending = None
            return
        if tok == "stop" and reacted == "celebrate":    # the big one celebrates, the others run to it (the whole
            if self.start_combo("celebrate_all", now, rush=True):    # family: one in the 小剧场 too, with a start)
                return
        if not followers:
            return
        if tok == "stop" and reacted == "thumbs_up" and ACTIVITY != "quiet":
            luck = random.random()
            if luck < COMBO_FIVE_CHANCE:
                self.combo_queue = ("high_five", now + COMBO_QUEUE_SECS)
            elif luck < COMBO_FIVE_CHANCE + COMBO_STACK_CHANCE:
                self.combo_queue = ("stack", now + COMBO_QUEUE_SECS)
        name, who = rule
        if who == "one":
            followers = [random.choice(followers)]
        for i, pet in enumerate(followers):
            pet.react = (name, now + FOLLOWER_STAGGER * (i + 1))

    # ----------------------------------------------------------- 差事
    def chore(self, pet):
        """(rank, what) that pet is up to now (R_*; a lower rank wins).  Read off its state, never stored."""
        if pet.dragging or pet.press is not None or pet.fly is not None:
            return R_HAND, "your hand"
        if pet.dozing and pet.doze_manual:
            return R_HAND, "a doze by hand"
        if pet.hand_clip is not None and (pet.cur == pet.hand_clip or (pet.pending is not None and pet.pending[0] == pet.hand_clip)):
            return R_HAND, "an action by hand"
        if pet.wander is not None and pet.wander.get("hand"):
            return R_HAND, "a walk by hand"
        if self.digging(pet):
            return pet.dig_rank, "rummaging"
        combo = self.combo
        if combo is not None and (pet in combo["pets"] or combo.get("receiver") is pet):
            return combo["rank"], "combo " + combo["name"]
        if pet.perch is not None or pet.hop is not None or any(p.perch is pet for p in self.pets):
            return R_PLAY, "a tower coming apart"
        if pet is self.leader and (pet.busy or pet.attention_until):
            return R_WORK, "work"
        if pet.signing:
            return R_WORK, "the sign"
        if pet.dozing or (self.nap is not None and self.nap["pet"] is pet):
            return R_NAP, "小剧场"
        if pet.react is not None:
            return R_REACT, "a reaction"
        if pet.slot and pet.cur in MIMIC_CLIPS and pet.cur_until is not None:
            return R_WATCH, "copying"
        if pet.home is not None and pet.watch_home and not pet.returning:
            return R_WATCH, "watching"
        if pet.sleeping:
            return R_BASE, "sleep"
        if pet.returning:
            return R_BASE, "the walk back"
        if pet.wander is not None:
            return R_BASE, "a walk"
        if pet.cur != pet.idle_name or pet.extra_wanted is not None:
            return R_BASE, "idle life"
        return R_FREE, ""

    def took(self, pet, why, now, rank=None):
        """pet is taken for something (rank: what it is worth, None = your hand).  Written down when that cuts
        short a chore of its own (pet.log, also without --debug), so one can see later who was cut short by what."""
        if pet is None or pet not in self.pets:
            return
        r, what = self.chore(pet)
        if r < R_BASE and not (r == R_HAND and rank is None) and (rank is None or rank <= r):
            log("chore: %scut short %s for %s" % (pet.tag or "pet0 ", what, why))

    def touch(self, source, now, wake=True):
        """Any activity counts for all of them, so they fall asleep and wake up together."""
        for pet in self.pets:
            pet.last_activity = now
            if wake and pet is not source and pet.sleeping:
                pet._wake(now, plays=True)

    def may_sleep(self):
        big = self.leader
        return not (big.busy or big.attention_until or self.combo is not None)

    # ----------------------------------------------------------- combos
    def combo_possible(self, name):
        """For the menu: could it start now, if asked?"""
        return len(self.pets) >= 2 and self._plan(name, manual=True) is not None

    def napping(self, pet):
        """In the cursor's 小剧场 (picked, looking over, coming closer or dozing), not a doze asked for by hand."""
        return (self.nap is not None and self.nap["pet"] is pet) or (pet.dozing and not pet.doze_manual)

    def digging(self, pet):
        """翻找 from the crouch to the end of its last clip (the find held up, or the letdown)."""
        return pet.dig is not None or pet.cur in DIG_ALL

    def _free(self, pet, manual):
        """Can it take part?  By hand the idle ones and those asleep can; by itself it waits for calm.  One in the
        小剧场 only for your hand or the whole family's cheer (self.plan_rank: what the combo planned is worth)."""
        if (pet.dragging or pet.press is not None or pet.hop is not None or pet.perch is not None or pet.fly is not None
                or any(p.perch is pet for p in self.pets)):
            return False
        if pet is self.leader and (pet.busy or pet.attention_until):
            return False
        if pet in self.far:                    # a combo of their own leaves out one put far away
            return False
        if pet.signing:                        # holds up the sign (a combo by hand takes it down first)
            return False
        if self.napping(pet):
            return self.plan_rank <= R_ALL     # with a start first (start_combo)
        if self.digging(pet):                  # up out of the hole first: for your hand, and one digging by itself for an event too
            return self.plan_rank <= (R_HAND if pet.dig_rank == R_HAND else R_EVENT)
        return manual or pet._calm()

    def _beside(self, mover, other, dist, side=None):
        """(x, y, side): where mover can stand dist from other, on its own side unless told; side -1 is
        left of it.  If that side does not fit on the screen, the other one."""
        if side is None:
            side = -1 if mover.fx < other.fx else 1
        xlo, xhi, ylo, yhi = mover._feet_limits(mover._work_area(other.fx, other.fy))
        y = clamp(other.fy, ylo, yhi)
        fits = [s for s in (side, -side) if xlo <= other.fx + s * dist <= xhi]
        for s in fits:
            if not self._collides(mover, other.fx + s * dist, y, other):
                return other.fx + s * dist, y, s
        side = fits[0] if fits else side
        return clamp(other.fx + side * dist, xlo, xhi), y, side

    def _collides(self, pet, x, y, also=None):
        """Would pet at (x, y) stand on top of another one on its row, not counting also?"""
        px = pet._target_px()
        for p in self.pets:
            if p is pet or p is also:
                continue
            opx = p._target_px()
            if abs(y - p.fy) <= ROW_TOLERANCE * max(px, opx) and abs(x - p.fx) < OVERLAP * (px + opx):
                return True
        return False

    def _plan(self, name, manual=False, pair=None, rush=False, agent=False):
        """-> (pets, phases) or None if it cannot be done now.  It only looks; nothing changes yet."""
        big = self.leader
        small = [p for p in self.pets[1:] if self._free(p, manual)]
        secs = COMBO_RUSH_SECS if rush else COMBO_WALK_SECS
        if name == "high_five":
            if pair is None:
                everyone = ([big] if self._free(big, manual) else []) + small
                if len(everyone) < 2:
                    return None
                pair = random.sample(everyone, 2)
                pair.sort(key=lambda p: p.slot)
                pair = (pair[1], pair[0])      # the smaller one comes to the bigger one
            mover, other = pair
            bigger, smaller = (mover, other) if mover._target_px() >= other._target_px() else (other, mover)
            dist = int(round(HIGH_FIVE_BIG * bigger._target_px() + HIGH_FIVE_SMALL * smaller._target_px()))
            x, y, side = self._beside(mover, other, dist)
            there, here = ("left", "right") if side < 0 else ("right", "left")   # mover looks here, other there
            # the smaller one jumps to reach the bigger one's arm; the stars are in the bigger one's clip
            clip = {mover: here, other: there}
            return list(pair), [("walk", {mover: (x, y)}, secs),
                                ("play", [(bigger, "high_five_" + clip[bigger], 0.0),
                                          (smaller, "high_five_up_" + clip[smaller], 0.0)])]
        if name == "peek":
            if not small:
                return None
            mover = random.choice(small)
            dist = (mover._target_px() + big._target_px()) // 2
            x, y, side = self._beside(mover, big, dist)
            return [mover], [("walk", {mover: (x, y)}, secs), ("play", [(mover, "peek_right" if side < 0 else "peek_left", 0.0)])]
        if name == "wake":
            asleep = [p for p in self.pets if p.sleeping or p.cur == "sleep"]
            target = big if big in asleep or not asleep else asleep[0]
            if target is big and (big.busy or big.attention_until):
                return None
            if target.dragging:
                return None
            movers = [p for p in ([big] + small) if p is not target and self._free(p, manual)]
            awake = [p for p in movers if p not in asleep]
            if not movers:
                return None
            mover = random.choice(awake or [p for p in movers if p is not big] or movers)
            dist = int(NUDGE_REACH * mover._target_px() + target._target_px() * 0.4)
            x, y, side = self._beside(mover, target, dist)
            # just awake or not: it does not hurry
            return [mover, target], [("walk", {mover: (x, y)}, COMBO_WAKE_WALK_SECS, COMBO_WAKE_PACE),
                                     ("play", [(mover, "nudge_right" if side < 0 else "nudge_left", 0.0)]),
                                     ("call", lambda now: self._woken(target, now))]
        if name == "parade":
            return self._plan_parade(small, manual)
        if name == "stack":
            return self._plan_stack(small, manual, pair)
        if name == "note":
            return self._plan_note(small, manual, agent)
        if name == "treasure":
            return self._plan_treasure(small, pair)
        if name == "leapfrog":
            return self._plan_leapfrog(small, manual)
        if name == "comfort":
            walks, pats, taken = {}, [], []
            for mover in sorted(small, key=lambda p: abs(p.fx - big.fx)):
                dist = int(NUDGE_REACH * mover._target_px() + big._target_px() * 0.4)
                side = -1 if mover.fx < big.fx else 1
                x, y, got = self._beside(mover, big, dist, -side if side in taken else side)
                if got in taken:               # one on each side; no room for a second one: one will do
                    continue
                taken.append(got)
                walks[mover] = (x, y)
                pats.append((mover, "comfort_right" if got < 0 else "comfort_left", COMFORT_STAGGER * len(pats)))
            if not pats:
                return None
            return list(walks), [("walk", walks, COMFORT_WALK_SECS), ("play", pats), ("call", self._comforted)]
        if name == "console":                  # one landed after a throw (pair): the others come and pat it
            target = pair
            if target is None or target not in self.pets:
                return None
            movers = [p for p in self.pets if p is not target and self._free(p, manual)]
            walks, pats, taken = {}, [], []
            for mover in sorted(movers, key=lambda p: abs(p.fx - target.fx)):
                dist = int(NUDGE_REACH * mover._target_px() + target._target_px() * 0.4)
                side = -1 if mover.fx < target.fx else 1
                x, y, got = self._beside(mover, target, dist, -side if side in taken else side)
                if got in taken:
                    continue
                taken.append(got)
                walks[mover] = (x, y)
                pats.append((mover, "comfort_right" if got < 0 else "comfort_left", COMFORT_STAGGER * len(pats)))
            if not pats:
                return None
            phases = [("walk", walks, COMFORT_WALK_SECS), ("play", pats), ("call", lambda now: self._consoled(target, now))]
            if big in walks:                   # the big one has no home to go back to: it walks back itself
                phases.append(("walk", {big: (big.fx, big.fy)}, RETURN_WALK_SECS, RETURN_PACE))
            return list(walks), phases
        if name == "celebrate_all":
            with_big = self._free(big, manual) and not rush
            if len(small) + (1 if with_big else 0) < 2 and not (rush and small):
                return None
            walks = {}
            taken = {-1: big._target_px() // 2, 1: big._target_px() // 2}    # how far each side is occupied
            for mover in sorted(small, key=lambda p: abs(p.fx - big.fx)):
                px = mover._target_px()
                gap = int(px * SIBLING_GAP)
                side = -1 if mover.fx < big.fx else 1
                if taken[side] > taken[-side]:   # the nearest took this side: the other one, if there is room
                    side = -side
                x, y, got = self._beside(mover, big, taken[side] + gap + px // 2, side)
                if got != side:                  # no room there: next to whoever stands on that side
                    x, y, got = self._beside(mover, big, taken[got] + gap + px // 2, got)
                walks[mover] = (x, y)
                taken[got] += gap + px
            pets = ([big] if with_big else []) + small
            return pets, [("walk", walks, secs), ("play", [(p, "celebrate", 0.15 * i) for i, p in enumerate(pets)])]
        return None

    def _plan_parade(self, small, manual):
        """In a row behind the big one, a walk there, all turn, and back: the big one ends where it stood,
        the smallest leads on the way back.  All walk at one speed, or the row would come apart."""
        big = self.leader
        if not small or not self._free(big, manual):
            return None
        behind, off, prev = {}, 0, big
        for pet in sorted(small, key=lambda p: p.slot):
            px, ppx = pet._target_px(), prev._target_px()
            off += (px + ppx) // 2 + int(max(px, ppx) * SIBLING_GAP)
            behind[pet] = off
            prev = pet
        xlo, xhi, ylo, yhi = big._feet_limits(big._work_area(big.fx, big.fy))
        y = clamp(big.fy, ylo, yhi)
        way = int(PARADE_DIST * big._target_px())
        ways = []
        for d in (1, -1):                      # d: the way they walk; the row stands behind the big one
            lo, hi = (xlo + off, xhi - way) if d > 0 else (xlo + way, xhi - off)
            if lo <= hi:
                head = clamp(big.fx, lo, hi)
                ways.append((abs(head - big.fx), random.random(), d, head))
        if not ways:
            return None                        # no room on this screen
        _, _, d, head = min(ways)
        row = {big: (head, y)}
        for pet, back in behind.items():
            row[pet] = (head - d * back, y)
        there = {pet: (x + d * way, y) for pet, (x, y) in row.items()}
        turn = "turn_left" if d > 0 else "turn_right"
        return list(row), [("walk", row, COMBO_WALK_SECS),
                           ("walk", there, PARADE_SECS, 0.5),   # 0.5: slow enough that secs decides for all of them
                           ("play", [(pet, turn, 0.0) for pet in row]),
                           ("walk", row, PARADE_SECS, 0.5)]

    @staticmethod
    def _head(pet):
        """Feet of one standing on pet's head."""
        return pet.fy - int(round(STACK_HEAD * pet._target_px())) + STACK_SINK

    def _plan_stack(self, small, manual, pair=None):
        """叠罗汉: the bigger ones at the bottom brace, the others jump up one by one, the top one cheers,
        and they jump down again from the top.  pair (top, bottom): dropped on its head by the user."""
        big = self.leader
        if pair is not None:
            top, bottom = pair
            tower, walks = [bottom, top], None
        else:
            if not small or not self._free(big, manual):
                return None
            tower = [big] + sorted(small, key=lambda p: p.slot)
            walks = {}                         # they wait beside it, the nearer one next to it
            taken = {-1: big._target_px() // 2, 1: big._target_px() // 2}
            for mover in sorted(tower[1:], key=lambda p: abs(p.fx - big.fx)):
                px = mover._target_px()
                gap = int(max(px, big._target_px()) * STACK_GAP)
                side = -1 if mover.fx < big.fx else 1
                if taken[side] > taken[-side]:
                    side = -side
                x, y, got = self._beside(mover, big, taken[side] + gap + px // 2, side)
                if got != side:
                    x, y, got = self._beside(mover, big, taken[got] + gap + px // 2, got)
                walks[mover] = (x, y)
                taken[got] += gap + px
        if not (all(p.store.usable("stack_brace") for p in tower[:-1]) and all(p.store.usable("stack_hop") for p in tower[1:])
                and tower[-1].store.usable("stack_top")):
            return None
        y = tower[0].fy                        # the top one must fit under the top of the screen
        for below in tower[:-1]:
            y -= int(round(STACK_HEAD * below._target_px())) - STACK_SINK
        if y < tower[-1]._feet_limits(tower[-1]._work_area(tower[0].fx, tower[0].fy))[2]:
            return None
        phases = [("walk", walks, COMBO_WALK_SECS)] if walks else []
        ground = None
        if pair is not None:                   # it comes down beside the other one, not in the air where it was dropped
            ground = self._beside(tower[1], tower[0], (tower[0]._target_px() + tower[1]._target_px()) // 2
                                  + int(tower[0]._target_px() * STACK_GAP))[:2]
            phases.append(("call", lambda now: self._perch(tower[1], tower[0], ground)))
        phases.append(("call", lambda now: self._brace(tower[0], now)))
        for i in range(1, len(tower)):
            phases.append(("hop", tower[i], tower[i - 1], ground))
            if i < len(tower) - 1:
                phases.append(("call", lambda now, p=tower[i]: self._brace(p, now)))
        phases.append(("play", [(tower[-1], "stack_top", 0.0)]))
        for i in range(len(tower) - 1, 0, -1):
            phases.append(("hop", tower[i], None, None))
            phases.append(("call", lambda now, p=tower[i - 1]: self._unbrace(p)))
        return tower, phases

    def _perch(self, pet, below, ground):
        pet.perch, pet.ground = below, ground
        self.depth_dirty = True

    @staticmethod
    def _brace(pet, now):
        pet.request("stack_brace", now, "combo", until=now + COMBO_MAX_SECS)

    @staticmethod
    def _unbrace(pet):
        if pet.cur == "stack_brace":
            pet.cur_until = 0.0
        if pet.pending is not None and pet.pending[0] == "stack_brace":
            pet.pending = None

    def _plan_note(self, small, manual, agent=False):
        """传纸条: a small one takes out a note, walks over with it and hands it over; the other one reads it.
        For a sub-agent that is done, the big one gets it and need not stop working: it only reads."""
        big = self.leader
        if not small:
            return None
        if agent or (manual and not self._free(big, manual)):
            receivers = [big] if not (big.dragging or big.press is not None or big.sleeping or big.attention_until) else []
        else:
            receivers = [p for p in [big] + small if self._free(p, manual)]
        if agent:
            receivers = receivers[:1]
        pairs = [(g, r) for r in receivers for g in small if g is not r]
        if not pairs:
            return None
        to_big = [pr for pr in pairs if pr[1] is big]
        if to_big and (agent or random.random() < NOTE_TO_BIG or len(to_big) == len(pairs)):
            pairs = to_big
        else:
            pairs = [pr for pr in pairs if pr[1] is not big] or pairs
        giver, receiver = random.choice(pairs)
        dist = int(round(NOTE_K[receiver.slot] * receiver._target_px() + NOTE_K[giver.slot] * giver._target_px()))
        x, y, side = self._beside(giver, receiver, dist)
        to_r, back = ("right", "left") if side < 0 else ("left", "right")
        give, receive = "give_" + NOTE_KIND[giver.slot] + to_r, "receive_" + NOTE_KIND[receiver.slot] + back
        if not (all(giver.store.usable(c + to_r) for c in ("carry_start_", "walk_carry_", "carry_hold_"))
                and giver.store.usable(give) and receiver.store.usable(receive)):
            return None
        at_work = receiver is big and (big.busy or big.attention_until)
        pets = [giver] if at_work else [giver, receiver]   # one at work goes on working: work events do not cancel it
        return pets, [("call", lambda now: self._take_note(giver, to_r, now)),
                      ("walk", {giver: (x, y)}, NOTE_WALK_SECS),
                      ("handoff", giver, receiver, give, receive)]

    def _plan_treasure(self, small, giver):
        """交宝贝 (the turn is over and its find is better than common): the one that dug it up takes it out again,
        carries it to the big one and hands it over; the big one holds it high.  The other small one, if it has
        nothing to do, comes to look from the other side; for a rare or special find all of them cheer."""
        big = self.leader
        if self.treasure is None or giver not in small or not self._free(big, True) or big.sleeping:
            return None
        _, item, rarity = self.treasure
        dist = int(round(NOTE_K[0] * big._target_px() + NOTE_K[giver.slot] * giver._target_px()))
        x, y, side = self._beside(giver, big, dist)
        to_r, back = ("right", "left") if side < 0 else ("left", "right")
        give, receive = "hand_" + NOTE_KIND[giver.slot] + to_r, "take_" + back
        if not (all(giver.store.usable(c + to_r) for c in ("bring_start_", "walk_bring_", "bring_hold_"))
                and giver.store.usable(give) and big.store.usable(receive)
                and giver.store.items is not None and big.store.items is not None):
            return None
        pets, walks, looks = [giver, big], {giver: (x, y)}, []
        for other in small:
            if other is giver or not other._calm() or self.napping(other):
                continue
            wx, wy, got = self._beside(other, big, (other._target_px() + big._target_px()) // 2, -side)
            clip = "peek_right" if got < 0 else "peek_left"
            if got == side or not other.store.usable(clip):
                continue                       # no room on the other side
            pets.append(other)
            walks[other] = (wx, wy)
            looks.append((other, clip))
            break
        phases = [("call", lambda now: self._take_item(giver, to_r, item, rarity, give, now)),
                  ("walk", walks, NOTE_WALK_SECS),
                  ("handoff", giver, big, give, receive, looks, (item, rarity))]
        if rarity in HAND_CHEER and all(p.store.usable("celebrate") for p in pets):
            phases.append(("play", [(p, "celebrate", 0.15 * i) for i, p in enumerate(pets)]))
        return pets, phases

    def _plan_leapfrog(self, small, manual):
        """跳山羊: the bigger one ducks, the smaller one jumps over its head; then the other way round, so
        that both moved on two steps the same way.  The two small ones if they can (the big one may be at
        work), else the big one with a small one."""
        big = self.leader
        pair = random.sample(small, 2) if len(small) >= 2 else (small + [big] if small and self._free(big, manual) else [])
        if len(pair) < 2:
            return None
        a, b = sorted(pair, key=lambda p: p.slot)    # a ducks first, b jumps first
        if not all(p.store.usable("leap_crouch") and p.store.usable("stack_hop") for p in (a, b)):
            return None
        d = int(round(LEAP_GAP * (a._target_px() + b._target_px())))
        xlo, xhi, ylo, yhi = b._feet_limits(b._work_area(a.fx, a.fy))
        alo, ahi = a._feet_limits(a._work_area(a.fx, a.fy))[:2]
        y = a.fy if ylo <= a.fy <= yhi else None
        if y is None:
            return None
        home = lambda p: p.area if p.area is not None else p.fx
        ways = []
        for s in (-1, 1) if b.fx < a.fx else (1, -1):   # s: b starts on this side of a; they go the other way
            start, b_land, a_land = a.fx + s * d, a.fx - s * d, a.fx - 2 * s * d
            if not (xlo <= start <= xhi and xlo <= b_land <= xhi and alo <= a_land <= ahi):
                continue
            # not into the third one: the one that is not playing stays where it is; and the way that keeps
            # them nearest to where the user put them
            crowded = self._collides(b, b_land, y, a) or self._collides(a, a_land, y, b)
            away = abs(a_land - home(a)) + abs(b_land - home(b))
            ways.append((crowded, away, len(ways), start, b_land, a_land))
        if not ways:
            return None                        # no room for it here
        _, _, _, start, b_land, a_land = min(ways)
        phases = [("walk", {b: (start, y)}, COMBO_WALK_SECS), ("leap", a, b, b_land, y), ("leap", b, a, a_land, y)]
        if a is big:                           # the big one has no walk home of its own: it goes back at once
            phases.append(("walk", {a: (a.fx, a.fy)}, RETURN_WALK_SECS, RETURN_PACE))
        return [a, b], phases

    def _leap_phase(self, combo, phase, now):
        """One jump: `base` ducks and `jumper` flies over it, on base's clock (as in a hand-over)."""
        _, base, jumper, x, y = phase[:5]
        if not combo["started"]:
            ready = all(p.cur_kind != KIND_ONESHOT and p.pending is None and not p.dragging and p.hop is None
                        for p in (base, jumper))
            if ready:
                combo["started"] = True
                combo["jumped"] = False
                combo["phase_t"] = now
                base.request(base._shot_name("leap_crouch"), now, "combo")
            elif now - combo["phase_t"] > COMBO_SYNC_WAIT:
                self.cancel_combo("not ready to leap", now)
            return
        if not combo["jumped"]:
            if base.cur != "leap_crouch":      # still on its way out of a hold, or it was stopped
                if (base.dragging or now - combo["phase_t"] > COMBO_SYNC_WAIT
                        or base.pending is None or base.pending[0] != "leap_crouch"):
                    self.cancel_combo("no one to jump over", now)
                return
            if now - base.t0 >= LEAP_HOP_AT:
                combo["jumped"] = True
                arc = LEAP_ARC[0] * base._target_px() + LEAP_ARC[1] * jumper._target_px()
                jumper._start_hop(x, y, now, why="leap", arc=arc, roll=len(phase) > 5)
                if jumper.cur == "stack_hop":
                    jumper.t0 = base.t0 + LEAP_HOP_AT
            return
        if jumper.hop is None and jumper.cur_kind != KIND_ONESHOT and base.cur_kind != KIND_ONESHOT:
            self._next_phase(now)

    @staticmethod
    def _take_note(pet, side, now):
        pet.carry = side
        pet.carry_item = False
        pet.request("carry_start_" + side, now, "combo")

    @staticmethod
    def _take_item(pet, side, item, rarity, give, now):
        """交宝贝: the find it had put away comes out again on the arm towards the big one."""
        pet.carry = side
        pet.carry_item = True
        pet.item = {"name": item, "rarity": rarity, "carried": True, "t0": now,
                    "clips": ("bring_start_" + side, "walk_bring_" + side, "bring_hold_" + side, give)}
        pet.request("bring_start_" + side, now, "combo")

    def _hand_over(self, pet, item, rarity, now):
        """交宝贝 begins, if it can now.  -> True: they set off, and the find is theirs from this moment (cut short
        or not: only the showing can be lost, and its sign goes up all the same)."""
        self.treasure = (pet, item, rarity)
        try:
            ok = self.start_combo("treasure", now, manual=True, by_hand=False, pair=pet)
        finally:
            self.treasure = None
        if ok:
            n = len(self.grow_signs)
            self._loot_credit(item, now, HAND_SIGN_WAIT, self.leader)
            if self.combo is not None and len(self.grow_signs) > n:
                self.combo["sign"] = self.grow_signs[-1]
            log("dig: %sbrings %s (%s) to the big one" % (pet.tag, item, rarity))
        return ok

    def _hand_cut(self, combo, now):
        """交宝贝 was cut short.  The find is theirs already; its sign comes now.  Not handed over yet: the one that
        brought it puts it away, and holds it up where it stands if it has a calm moment (your hand on it, a
        clip you asked for: then not)."""
        sign = combo.get("sign")
        if sign is not None and any(s is sign for s in self.grow_signs):
            sign["at"] = min(sign["at"], now + 0.6)
        if combo.get("handed"):
            return
        giver = combo["pets"][0]
        it, giver.item = giver.item, None
        if it is not None and giver in self.pets and not self.hidden:
            self.hand_show = (giver, it["name"], it["rarity"], now + HAND_SHOW_SECS)

    def _comforted(self, now):
        big = self.leader
        big._wake(now, plays=True)
        if big.pending is None:                # never in place of a queued turn-end reaction
            big.request(big._shot_name("nod"), now, "comforted")

    def _consoled(self, target, now):
        if target in self.pets and target.fly is None and not target.dragging and target.pending is None:
            target.request(target._shot_name("nod"), now, "consoled")

    def _woken(self, target, now):
        if target.sleeping:
            target._wake(now, plays=True)      # gets up ...
            target.request(target._shot_name("nod"), now, "nudged")   # ... all right, all right
        else:                                  # it was awake after all
            target.request(target._shot_name("surprised"), now, "nudged")
        target._activity(now)                  # the others wake as well

    @staticmethod
    def combo_rank(name, manual=False, by_hand=None, rush=False):
        """What a combo is worth as a chore: by your hand; the whole family's cheer (a long turn, a level-up); one
        an event sends (comfort, a note, a pat); or one of their own (a game; coming over to watch)."""
        if manual if by_hand is None else by_hand:
            return R_HAND
        if name == "celebrate_all" and (rush or manual):
            return R_ALL
        if manual and name != "wake":
            return R_EVENT
        return R_WATCH if name == "peek" else R_PLAY

    def start_combo(self, name, now, manual=False, pair=None, rush=False, by_hand=None, stay=False, agent=False):
        if self.quitting:
            return False
        own = not (manual if by_hand is None else by_hand)
        if not own and self.sign is not None and self.sign["holder"] is not None:
            self.end_sign(now, "combo by hand")    # the user's wish: the sign comes down, the holder joins in
        # one they start themselves does not send one across the screen: those put far away are left
        # out, and no walk may be longer (by hand they come from anywhere)
        reach = COMBO_NEAR * self.leader._target_px()
        if own and len(self.pets) >= 2:
            big = self.leader
            if name == "console" and pair is not None:     # a pat for one thrown: who is near that one
                self.far = {p for p in self.pets if p is not pair and math.hypot(p.fx - pair.fx, p.fy - pair.fy) > reach}
            else:
                self.far = {p for p in self.pets[1:] if math.hypot(p.fx - big.fx, p.fy - big.fy) > reach}
        rank = self.combo_rank(name, manual, by_hand, rush)
        self.plan_rank = rank
        try:
            plan = self._plan(name, manual, pair, rush, agent) if len(self.pets) >= 2 else None
        finally:
            self.far = set()
            self.plan_rank = R_HAND
        if plan is None:
            if manual:
                log("combo %s: not now" % name)
            return False
        pets, phases = plan
        slip = self._slip(name, phases)
        if slip is not None:
            phases = slip
        if own:
            walk = next((ph[1] for ph in phases if ph[0] == "walk"), {})
            far = [p for p, (x, y) in walk.items() if math.hypot(x - p.fx, y - p.fy) > reach]
            if far:
                if self.opts["debug"]:
                    log("combo %s left out: too far for %s" % (name, ", ".join("pet%d" % p.slot for p in far)))
                self.combo_queue = None        # a queued one would only ask again at every tick
                return False
        for pet in pets:
            self.took(pet, "combo " + name, now, rank)
        if self.combo is not None:
            self.cancel_combo("another combo", now)
        target = pets[1] if name == "wake" else None    # stays asleep until it is nudged
        for pet in pets:
            if stay:                           # dropped on another one: the user chose this place for both
                pet.home = None
            elif pet.slot and pet.home is None:
                pet.home = (pet.fx, pet.fy)
                pet.watch_home = name == "peek"   # the others go back home at once, work or not
            pet.return_at = None
            pet.returning = False
            pet.in_combo = True
            pet.react = None
            pet.extra_wanted = None
            if pet.cur == "sleep":             # also a sleep asked for by hand, which would end by itself
                pet.sleeping = True
            pet._cancel_manual()
            pet.wander = None
            if pet is target:
                if pet.cur == "sleep":
                    pet.cur_until = None
            elif pet.sleeping:
                pet._wake(now, plays=True)
            elif pet.dozing:
                pet.end_doze(now, "combo")
        self.combo = {"name": name, "pets": pets, "phases": phases, "i": -1, "t": now, "phase_t": now, "started": False, "due": None,
                      "about": pair if name == "console" else None,
                      "handmade": stay or name == "console", "by_hand": manual if by_hand is None else by_hand, "rank": rank, "show": rank in (R_PLAY, R_WATCH),
                      "receiver": next((ph[2] for ph in phases if ph[0] == "handoff"), None), "slip": slip is not None}
        self.combo_queue = None
        log("combo %s: %s%s" % (name, ", ".join("pet%d" % p.slot for p in pets), " (小插曲)" if slip is not None else ""))
        self._next_phase(now)
        return True

    def _slip(self, name, phases):
        """小插曲: -> the phases of this combo going the other way, or None (not this time, not yet, no clips).
        击掌: both jump and miss, down on their bottoms.  跳山羊: the first jump as ever; at the second the one
        ducking ducks as ever and the jumper goes over it head over heels, a whole turn, and sits down dizzy
        where it lands.  叠罗汉: the top one comes down with a flip."""
        if name not in SLIPS or self.replaying or self.grow.level < slips_level():
            return None
        want = self.opts.get("slip")
        if want == "no" or not (want == "yes" or self.grow.data["slip_dry"] >= SLIP_DRY or random.random() < SLIP_CHANCE):
            return None
        clip = SLIPS[name][0]
        out = list(phases)
        if name == "high_five":
            i = next((i for i, ph in enumerate(out) if ph[0] == "play"), None)
            if i is None:
                return None
            plays = [(pet, "%s_%s" % (clip, c.rsplit("_", 1)[1]), delay) for pet, c, delay in out[i][1]]
            if not all(pet.store.usable(c) for pet, c, _ in plays):
                return None
            out[i] = ("play", plays)
        elif name == "leapfrog":
            leaps = [i for i, ph in enumerate(out) if ph[0] == "leap"]
            if len(leaps) < 2:
                return None
            jumper = out[leaps[1]][2]
            if not (jumper.store.usable(clip + "_left") and jumper.store.usable(clip + "_right")):
                return None
            out[leaps[1]] = out[leaps[1]] + (True,)
        elif name == "stack":
            i = next((i for i, ph in enumerate(out) if ph[0] == "hop" and ph[2] is None), None)
            if i is None or not (out[i][1].store.usable(clip + "_left") and out[i][1].store.usable(clip + "_right")):
                return None
            out[i] = out[i] + (True,)
        return out

    def _break_up(self, pets, now, instant=False):
        """No tower and no note left: the ones up there come down (the top first), the bases stand easy."""
        def level(p):
            n, q = 0, p
            while q.perch is not None and n < len(self.pets):
                n, q = n + 1, q.perch
            return n
        for pet in sorted(pets, key=level, reverse=True):
            pet.carry = None
            if pet.hop is not None or pet.perch is not None:
                pet.come_down(now, instant)
            self._unbrace(pet)

    def cancel_combo(self, why, now, instant=False):
        combo, self.combo = self.combo, None
        if instant:
            self._break_up(self.pets, now, True)
        if combo is None:
            return
        self._break_up(combo["pets"], now, instant)
        clips = set(c for phase in combo["phases"] if phase[0] == "play" for _, c, _ in phase[1])
        clips.update(c for phase in combo["phases"] if phase[0] == "handoff" for c in phase[3:5])
        if any(phase[0] == "leap" for phase in combo["phases"]):
            clips.add("leap_crouch")
        for phase in combo["phases"]:          # one at work, not in the combo, must not reach for a note that never comes
            if phase[0] == "handoff" and phase[2].pending is not None and phase[2].pending[0] == phase[4]:
                phase[2].pending = None
        for pet in combo["pets"]:
            pet.in_combo = False
            if pet.wander is not None and "y1" in pet.wander:
                pet.wander = None
            if pet.pending is not None and pet.pending[0] in clips:
                pet.pending = None
            if pet.home is not None:
                pet.return_at = now + random.uniform(*self.return_range)
        self.next_combo = now + random.uniform(*self.combo_range)
        if combo["show"]:
            self.show_end = now
        if combo["name"] == "treasure":
            self._hand_cut(combo, now)
        log("combo %s cancelled (%s)" % (combo["name"], why))

    def _end_combo(self, now):
        combo, self.combo = self.combo, None
        self._break_up(combo["pets"], now)     # nothing to do when all went well
        for pet in combo["pets"]:
            pet.in_combo = False
            if pet.home is not None:
                pet.return_at = now + random.uniform(*self.return_range)
        self.next_combo = now + random.uniform(*self.combo_range)
        if combo["show"]:
            self.show_end = now
        self.save_state()
        log("combo %s over after %.1fs" % (combo["name"], now - combo["t"]))
        if not combo.get("grow"):
            self._grow_combo(combo, now)

    def _next_phase(self, now):
        combo = self.combo
        combo["i"] += 1
        combo["phase_t"] = now
        combo["started"] = False
        if combo["i"] >= len(combo["phases"]):
            self._end_combo(now)
            return
        phase = combo["phases"][combo["i"]]
        if phase[0] == "walk":
            for pet, (x, y) in phase[1].items():
                pet._walk_to(x, y, now, *phase[2:])
        elif phase[0] == "call":
            phase[1](now)
            if self.combo is combo:
                self._next_phase(now)
        elif phase[0] == "handoff":
            combo["asked"] = False

    def _combo_step(self, now):
        combo = self.combo
        if now - combo["t"] > COMBO_MAX_SECS:
            self.cancel_combo("took too long", now)
            return
        if combo["name"] == "wake" and not combo["by_hand"] and not combo["pets"][1].sleeping and combo["i"] < 2:
            self.cancel_combo("the big one is awake", now)
            return
        phase = combo["phases"][combo["i"]]
        if phase[0] == "leap":
            self._leap_phase(combo, phase, now)
            return
        if phase[0] == "hop":
            self._hop_phase(combo, phase, now)
            return
        if phase[0] == "handoff":
            self._handoff_phase(combo, phase, now)
            return
        if phase[0] == "walk":
            if all(pet.wander is None for pet in phase[1]):
                for pet, (x, y) in phase[1].items():
                    if abs(pet.fx - x) > 4 or abs(pet.fy - y) > 4:
                        self.cancel_combo("the walk was stopped", now)   # by a click, a display change ...
                        return
                self._next_phase(now)
            return
        pets = [p for p, _, _ in phase[1]]
        settled = all(p.cur_kind != KIND_ONESHOT and p.pending is None for p in pets)
        if not combo["started"]:
            # all from the same moment: wait for a clip under way, which is never cut
            if settled or now - combo["phase_t"] > COMBO_SYNC_WAIT:
                combo["started"] = True
                combo["due"] = [(now + delay, pet, clip) for pet, clip, delay in phase[1]]
            else:
                return
        if combo["due"]:
            for item in [d for d in combo["due"] if now >= d[0]]:
                combo["due"].remove(item)
                item[1].request(item[1]._shot_name(item[2]), now, "combo")
            return
        if settled:
            self._next_phase(now)

    def _hop_phase(self, combo, phase, now):
        _, pet, below, ground = phase[:4]
        if not combo["started"]:
            ready = pet.cur_kind != KIND_ONESHOT and pet.pending is None and not pet.dragging
            if below is not None:
                ready = ready and below.cur == "stack_brace" and below.hop is None
            if ready:
                combo["started"] = True
                if below is None:
                    pet.come_down(now, flip=len(phase) > 4)
                else:
                    pet._start_hop(below.fx, self._head(below), now, perch=below, ground=ground)
            elif now - combo["phase_t"] > COMBO_SYNC_WAIT:
                self.cancel_combo("not ready to jump", now)
            return
        if pet.hop is None and pet.cur_kind != KIND_ONESHOT:
            if below is not None and pet.perch is not below:
                self.cancel_combo("fell off", now)
                return
            self._next_phase(now)

    def _handoff_phase(self, combo, phase, now):
        """The note changes hands at the same moment of both clips: the giver starts when the other one
        does (which may first finish what it plays), on the same clock."""
        _, giver, receiver, give, receive = phase[:5]
        if not combo["asked"]:
            if giver.cur_kind != KIND_ONESHOT and giver.pending is None and receiver.pending is None:
                combo["asked"] = True
                combo["phase_t"] = now
                receiver._cancel_manual()
                receiver.request(receive, now, "note")
            elif now - combo["phase_t"] > NOTE_SYNC_WAIT:
                self.cancel_combo("no one took the note", now)
            return
        if not combo["started"]:
            if receiver.cur == receive:
                combo["started"] = True
                giver.carry = None
                giver._start(give, now, "note")
                giver.t0 = receiver.t0
                if len(phase) > 5:             # 交宝贝: the find goes over with it, the third one looks on, the sign goes up
                    looks, (item, rarity) = phase[5], phase[6]
                    receiver.item = {"name": item, "rarity": rarity, "clips": (receive,),
                                     "t0": giver.item["t0"] if giver.item is not None else now}
                    combo["handed"] = True
                    for other, clip in looks:
                        if other.cur_kind != KIND_ONESHOT and not other.dragging:
                            other.request(clip, now, "combo")
                    if combo.get("sign") is not None:
                        combo["sign"]["at"] = min(combo["sign"]["at"], now + HAND_SIGN_HIGH)
            elif (receiver.dragging or now - combo["phase_t"] > NOTE_SYNC_WAIT
                  or receiver.pending is None or receiver.pending[0] != receive):
                self.cancel_combo("no one took the note", now)
            return
        if giver.cur_kind != KIND_ONESHOT and receiver.cur != receive:
            self._next_phase(now)

    def _depth_tick(self):
        """Lower feet are nearer: in front.  The one in the hand is in front of all.  Windows only when the order changes."""
        if not self.depth_dirty:
            return
        self.depth_dirty = False
        if len(self.pets) < 2:
            return
        def key(p):
            n, q = 0, p
            while q.perch is not None and n < len(self.pets):
                n, q = n + 1, q.perch
            leaping = p.hop is not None and p.perch is None and not p.hop["up"]
            fy = max(p.hop["y0"], p.hop["y1"]) if leaping else q.fy    # in the air its row is where it jumped from
            return (p.dragging, fy, n, leaping, p.slot)   # one up there, or jumping over: in front of the one below
        order = sorted(self.pets, key=key)
        slots = [p.slot for p in order]
        if slots == self.depth_order:
            return
        self.depth_order = slots
        for pet in order:                      # from the back: each goes on top of those before it
            if pet.hwnd:
                SetWindowPos(pet.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        self.dots.raise_top()
        self.dot_tip.raise_top()
        self.sign_board.raise_top()            # the board stays in front of them all

    def _return_tick(self, now):
        for pet in self.pets[1:]:
            if pet.home is None:
                continue
            if pet.returning:
                if pet.wander is None:         # there, or stopped on the way by a click or a reaction
                    pet.returning = False
                    if abs(pet.fx - pet.home[0]) <= 4 and abs(pet.fy - pet.home[1]) <= 4:
                        pet.home = None
                        self.save_state()
                    else:
                        pet.return_at = now + random.uniform(*self.return_range)
            elif (pet.return_at is not None and now >= pet.return_at and (not pet.watch_home or not self.leader.busy)
                  and pet._calm() and pet.react is None):
                pet.return_at = None
                if pet._walk_to(pet.home[0], pet.home[1], now, RETURN_WALK_SECS, RETURN_PACE):
                    pet.returning = True
                    if self.opts["debug"]:
                        log("%swalks back" % pet.tag)
                else:
                    pet.home = None

    def _overlap_tick(self, now):
        """Two on one row on top of each other: the smaller one walks aside."""
        if now < self.next_overlap_check:
            return
        self.next_overlap_check = now + 0.5
        seen = {}
        for i, a in enumerate(self.pets):
            for b in self.pets[i + 1:]:        # b is the smaller one, slots are in order of size
                pa, pb = a._target_px(), b._target_px()
                if (not self._same_row(a, b) or abs(a.fx - b.fx) >= OVERLAP * (pa + pb)
                        or a.wander is not None or b.wander is not None or a.dragging or b.dragging
                        or a.hop is not None or b.hop is not None or a.perch is not None or b.perch is not None):
                    continue                   # one just passing by is no collision
                key = (b.slot, a.slot)
                seen[key] = since = self.overlaps.get(key, now)
                if now - since < OVERLAP_PATIENCE or b.home is not None or not b._calm() or self.napping(b):
                    continue                   # one that is away goes back by itself
                need = (pa + pb) // 2 + int(pa * SIBLING_GAP)
                x, y, side = self._beside(b, a, need)
                if self._collides(b, x, b.fy, a):
                    continue                   # no room: they stay, it does not shuffle to and fro
                if b._walk_to(x, b.fy, now, RETURN_WALK_SECS, RETURN_PACE):
                    log("%swalks aside" % b.tag)
                seen.pop(key, None)
                self.overlaps = seen
                return
        self.overlaps = seen

    def _company_tick(self, now):
        """The big one is at work: now and then a small one comes to watch, or copies its tool."""
        big = self.leader
        since = now - min(t["since"] for t in big.working.values())
        if self._busy_copying() or not self.show_ok(now):
            return
        if now >= self.next_play and since >= self.play_after and not any(p.home is not None for p in self.pets[1:]):
            self.next_play = now + COMBO_RETRY
            if sum(1 for p in self.pets[1:] if self._free(p, False)) >= 2:
                name = random.choices([c[0] for c in PLAY_AT_WORK], [c[1] for c in PLAY_AT_WORK])[0]
                if self.start_combo(name, now):
                    self.next_play = now + random.uniform(*self.play_range)
                    self.next_peek = max(self.next_peek, now + COMBO_PEEK_EVERY[0])   # not one game after another
                    self.next_mimic = max(self.next_mimic, now + MIMIC_SECS * 2)
                    return
        if (now >= self.next_peek and not any(p.home is not None for p in self.pets[1:]) and since >= self.peek_after * (1 if big.busy_clip in WATCHED_CLIPS else COMBO_PEEK_ANY)):
            started = self.start_combo("peek", now)
            self.next_peek = now + (random.uniform(*COMBO_PEEK_EVERY) if started else COMBO_RETRY)
            if started:
                self.next_mimic = max(self.next_mimic, now + MIMIC_SECS * 2)
            return
        if now >= self.next_mimic and since >= MIMIC_AFTER and big.busy_clip in MIMIC_CLIPS:
            ready = [p for p in self.pets[1:] if p._calm() and not self.napping(p)]
            if ready:
                pet = random.choice(ready)
                self.next_mimic = now + random.uniform(*self.mimic_range)
                self.show_end = now + MIMIC_SECS
                pet.request(pet._shot_name(big.busy_clip), now, "copies", until=now + MIMIC_SECS)
            else:
                self.next_mimic = now + COMBO_RETRY

    def _busy_copying(self):
        return any(p.cur in MIMIC_CLIPS for p in self.pets[1:])

    def show_ok(self, now):
        """The shows (a game of their own, copying the big one, coming to watch; 翻找 later) keep a gap between them,
        longer when quiet: never two at once or one right after another.  Reactions and your hand do not wait."""
        return now >= self.show_end + self.show_gap * ACTIVITY_PACE[ACTIVITY]

    def combo_tick(self, now):
        self._depth_tick()
        if self.combo is not None:
            self._combo_step(now)
            return
        big = self.leader
        if self.wake_due is not None and not big.sleeping:
            self.wake_due = None
        if len(self.pets) < 2 or self.menu_open:
            return
        self._return_tick(now)
        self._overlap_tick(now)
        if self.combo_queue is not None:
            name, until = self.combo_queue
            if now >= until:
                self.combo_queue = None
            elif big._calm() and self.start_combo(name, now):
                return
        if ACTIVITY == "quiet":                # none of their own: no nudge awake, no company at work, no idle games
            return
        if self.wake_due is not None and now >= self.wake_due:
            self.wake_due = None
            if all(p.sleeping for p in self.pets):
                self.start_combo("wake", now, manual=True, by_hand=False)
            return
        if big.busy:
            self._company_tick(now)
            return
        if now >= self.next_combo and self.show_ok(now):
            self.next_combo = now + COMBO_RETRY
            if big._calm():
                self.start_combo(random.choices([c[0] for c in COMBO_IDLE], [c[1] for c in COMBO_IDLE])[0], now)

    # ----------------------------------------------------------- 翻找
    def _items(self):
        st = self.leader.store
        return st.items["names"] if st.items is not None else {}

    def _pool(self):
        """-> {treasure: rarity} of what a dig may bring up now (not the second batch before its gift)."""
        locked = items_locked(self.grow.level)
        return dict((n, i.get("rarity")) for n, i in self._items().items() if n not in locked)

    def can_dig(self, pet):
        return pet.store.items is not None and all(pet.store.usable(c) for c in DIG_CLIPS) and pet.dig is None

    def _loot_tick(self, now):
        """The turn is over and its "done" sign is down: the find is shown.  The one that dug it up holds it up
        where it stands (present); the big one's own comes out from behind its back (pull_out); the sign says
        what it is.  No moment for it in DIG_SHOW_WAIT: counted all the same, with its sign only."""
        if self.loot_left and not self.replaying:      # the family quit in the middle of a turn: what it had found is theirs
            left, self.loot_left = self.loot_left, []
            self._loot_keep()
            for i, item in enumerate(left):
                log("dig: %s was put away when they quit: theirs now" % item)
                self._loot_credit(item, now, 3.0 + i)
        if self.hand_show is not None:                 # 交宝贝 was cut short: it holds the find up where it stands, or not
            pet, item, rarity, until = self.hand_show
            if now > until or pet not in self.pets or self.hidden or not pet.store.usable("present"):
                self.hand_show = None
            elif pet._calm() and not self.menu_open:
                self.hand_show = None
                pet.item = {"name": item, "rarity": rarity, "clip": "present", "t0": now}
                pet.request("present", now, "shows the find (not handed over)")
        if self.loot_due is None:
            return
        if not self.loot:
            self.loot_due = None
            return
        late = now - self.loot_due > DIG_SHOW_WAIT
        if not late and (self.sign is not None or self.sign_board.shown or now - self.sign_down_at < DIG_SHOW_AFTER
                         or now - self.loot_due < GROW_AFTER_STOP or self.combo is not None or self.menu_open):
            return
        item, slot = self.loot[0]
        info = self._items().get(item)
        pet = next((q for q in self.pets if q.slot == slot), None) if slot is not None else self.leader
        clip = "pull_out" if slot is None else "present"
        if pet is None or not pet.store.usable(clip) or pet.store.items is None:
            pet = None                         # it has gone home meanwhile: the sign alone
        if pet is not None and not late and not (pet._calm() or (pet is self.leader and pet.cur_kind != KIND_ONESHOT
                                                              and not pet.dragging and pet.fly is None)):
            return                             # it has its hands full: in a moment
        self.loot.pop(0)
        self._loot_keep()
        if not self.loot:
            self.loot_due = None
        rarity = str(info.get("rarity")) if info is not None else ""
        if (pet is not None and info is not None and not late and slot is not None and rarity in HAND_RARITIES
                and self._hand_over(pet, item, rarity, now)):
            self.show_end = now + 3.0
            return
        if pet is not None and info is not None and not late:
            pet.item = {"name": item, "rarity": str(info.get("rarity")), "clip": clip, "t0": now}
            pet.hand_clip = None
            pet.request(clip, now, "shows the find")
            self.show_end = now + 3.0
            sign_after = DIG_SHOW_SIGN + (1.6 if clip == "pull_out" else 0.0)
            big = self.leader
            if pet is not big and big._calm() and big._shot_name("thumbs_up"):
                big.react = ("thumbs_up", now + 1.0)       # well done
        else:
            sign_after = 0.0
        self._loot_credit(item, now, sign_after, pet)

    def _loot_keep(self):
        """What is put away is written down at once: a quit before the turn ends does not lose it."""
        self.grow.data["loot"] = [[item, -1 if slot is None else slot] for item, slot in self.loot]
        self.grow.dirty = True
        self.grow.save()

    def _first_play_tick(self, now):
        """A treasure found for the first time: once it has been shown (its sign down, the hand-over done), the one
        that holds it takes it out again and plays with it, there and then.  No calm moment in FIRST_PLAY_WAIT: not."""
        fp = self.first_play
        if fp is None:
            return
        pet = fp["pet"]
        if now > fp["until"] or pet not in self.pets or self.hidden:
            self.first_play = None
            return
        if (now < fp["at"] or self.sign is not None or self.sign_board.shown or self.grow_signs or now - self.sign_down_at < GROW_SIGN_GAP
                or self.combo is not None or self.menu_open or not pet._calm() or self.napping(pet) or self.digging(pet)
                or any(self.playing(q) for q in self.pets) or (pet is self.leader and (pet.busy or pet.attention_until))):
            return
        self.first_play = None
        self.play_item(pet, fp["item"], now, "first of its kind", hand=False, first=True)

    def dig_tick(self, now):
        """By themselves: a turn at work owes a dig each dig_every s of its work time (dig_owed, dig_most a turn): a
        small one that has nothing better to do digs it (one at a time, the oldest turn's first; called away, it is
        owed again).  What is owed when the turn ends the big one pulls out itself (grow_turn)."""
        self._loot_tick(now)
        self._first_play_tick(now)
        big = self.leader
        if (not big.busy or len(self.pets) < 2 or self.menu_open or self.combo is not None or big.attention_until
                or now < self.dig_next or self.replaying):
            return
        owed = [(s, t) for s, t in big.working.items() if self.dig_owed(t) > 0 and big.at_work(s, t, now)]
        if not owed or not self.show_ok(now) or any(self.digging(p) for p in self.pets):
            return
        self.dig_next = now + COMBO_RETRY
        ready = [p for p in self.pets[1:] if p._calm() and not self.napping(p) and self.can_dig(p)]
        if not ready:
            return
        session, turn = min(owed, key=lambda st: st[1]["since"])
        pet = random.choice(ready)
        if pet.begin_dig(now, False, random.randint(*DIG_LOOPS)):
            pet.dig["session"] = session
            turn["dug"] = turn.get("dug", 0) + 1
            log("dig: %sdigs, %.0fs into the turn (%d of %d)" % (pet.tag, turn.get("work", 0.0), turn["dug"], self.dig_most()))

    def album_label(self):
        """The menu's 图鉴, with how many finds wait in it (sealed: not looked at yet)."""
        try:
            n = self.album_new()
        except Exception:
            n = 0
        return tr("图鉴（%d 个新）" % n, "Album (%d new)" % n) if n else tr("图鉴", "Album")

    @grow_safe
    def open_album(self, why):
        """图鉴: the album is a process of its own (tkinter), so it costs the pets nothing; it only reads grow.json,
        which is written down first.  One window a home: asked for again, the one that is open comes to the front."""
        import subprocess
        self.grow.save()
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clawd_album.pyw")
        exe = sys.executable or "pythonw.exe"
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        subprocess.Popen([w if os.path.exists(w) else exe, script, "--home", HOME_DIR, "--frames-dir", self.opts["frames_dir"] or BASE_FRAMES_DIR],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         **child_kw())
        log("album: opened (%s)" % why)
        self.album_recheck = time.perf_counter() + 5.0

    def open_connect(self, why):
        """连接 AI…: the window that connects the agents (clawd_connect.pyw), a process of its own; one at a time."""
        import subprocess
        try:
            exe = sys.executable or "pythonw.exe"
            w = os.path.join(os.path.dirname(exe), "pythonw.exe")
            subprocess.Popen([w if os.path.exists(w) else exe, os.path.join(HERE, "clawd_connect.pyw"), "--home", HOME_DIR],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                             **child_kw())
            log("connect: opened (%s)" % why)
        except Exception:
            log_exc("opening the connect window")

    def first_tick(self, now):
        """The very first start (no state.json then): the big family says where the menu is, and the window that
        connects the agents opens.  Once: the state is written at the start."""
        if self.first_start is None or now < self.first_start or self.menu_open or self.hidden:
            return
        self.first_start = None
        self.show_sign("hint", now, SIGN_HINT_SECS)
        self.open_connect("first start")

    # ----------------------------------------------------------- 把玩
    def treasures(self):
        """The treasures they have, in the album's order."""
        st = self.leader.store
        if st.items is None:
            return []
        own = self.grow.data["items"]
        return [n for n in st.items["order"] if type(own.get(n)) is int and own[n] > 0]

    def play_clip(self, pet, item):
        """The clip pet plays with this treasure: its own (play_<treasure>, the treasure drawn in), or in a frame set
        from before those, its way (PLAY_WAY) with the treasure laid on by the player."""
        st = pet.store
        own = "play_" + item
        if own in st.meta and st.usable(own):
            return own
        clip = PLAY_WAY.get(item, "play_look")
        if st.items is not None and clip in st.meta and st.usable(clip) and isinstance(st.meta[clip].get("item"), list):
            return clip
        return None

    @staticmethod
    def playing(pet):
        """Has a treasure out (or is about to)."""
        return (pet.item is not None or pet.cur.startswith("play_")
                or (pet.pending is not None and pet.pending[0].startswith("play_")))

    def may_play_alone(self, pet):
        """Idle, nothing else going on: one of them at a time takes a treasure out by itself."""
        big = self.leader
        return (bool(self.treasures()) and not big.busy and not big.attention_until and self.combo is None
                and not self.menu_open and self.sign is None and not any(self.playing(q) for q in self.pets))

    def play_by_hand(self, pet, item, now, why):
        """You ask for it (the menu: that one; the album, clawd do: one with nothing to do, else the big one)."""
        if pet is None:
            calm = [q for q in self.pets if q._calm() and not self.napping(q) and not self.playing(q)]
            pet = random.choice(calm) if calm else self.leader
        return self.play_item(pet, item, now, why)

    def play_item(self, pet, item, now, why, hand=True, first=False):
        """把玩: pet takes a treasure of theirs (None: any one) out from behind its back, plays with it and puts it
        away.  By hand it is your hand (R_HAND: its sign comes down, a combo lets it go); by itself it is idle life."""
        have = self.treasures()
        if item is None and have:
            item = random.choice(have)
        if item not in have:
            log("play: %snot theirs: %s (%s)" % (pet.tag or "pet0 ", item, why))
            return False
        if not hand and not first and not self.may_play_alone(pet):
            return False                       # picked a moment ago, but another one has taken one out since
        clip = self.play_clip(pet, item)
        if (clip is None or pet.dragging or pet.fly is not None or pet.hop is not None or pet.perch is not None
                or (pet.item is not None and pet.item.get("on")) or pet.cur.startswith("play_")):
            log("play: %snot now (%s, %s)" % (pet.tag or "pet0 ", item, why))
            return False
        if hand:
            self.took(pet, "a treasure to play with", now)
            if pet.in_combo or (pet is self.leader and self.combo is not None):
                self.cancel_combo("play by hand", now)
            if pet.signing:
                self.end_sign(now, "play by hand")
            if self.nap is not None and self.nap["pet"] is pet:
                self.nap_over(pet, now, "play by hand")
            pet._cancel_manual()
            pet.attention_until = 0.0
            pet.wander = None
            pet._wake(now, plays=True)
            pet.hand_clip = clip
            self.grow_play("treasure", now)
        if clip != "play_" + item:            # an old frame set: the treasure is laid on
            pet.item = {"name": item, "rarity": str(self._items()[item].get("rarity")), "clip": clip, "t0": now}
        pet.request(clip, now, "plays with " + item)
        log("play: %splays with %s (%s, %s)" % (pet.tag or "pet0 ", item, clip, why))
        return True

    def dig_by_hand(self, pet, now, why):
        """You ask one to dig: at once, whatever it was doing (its sign comes down, a combo lets it go)."""
        if not self.can_dig(pet) or pet.dragging or pet.fly is not None:
            return False
        self.took(pet, "a rummage by hand", now)
        if pet.in_combo or (pet is self.leader and self.combo is not None):
            self.cancel_combo("rummage by hand", now)
        if pet.signing:
            self.end_sign(now, "rummage by hand")
        if self.nap is not None and self.nap["pet"] is pet:
            self.nap_over(pet, now, "rummage by hand")
        pet._cancel_manual()
        pet.attention_until = 0.0
        pet.wander = None
        pet._wake(now, plays=True)
        ok = pet.begin_dig(now, True, DIG_HAND_LOOPS)
        if ok:
            log("dig: %sdigs by hand (%s), %d finds left" % (pet.tag or "pet0 ", why, self.grow.data["chances"]))
        return ok

    def dig_over(self, pet, now, was, why):
        """Called away before anything came up: nothing found, nothing used; one digging by itself may try again."""
        log("dig: %scut short (%s)" % (pet.tag or "pet0 ", why))
        if not was["hand"]:
            turn = self.leader.working.get(was.get("session"))
            if turn is not None and turn.get("dug"):
                turn["dug"] -= 1                   # that dig is owed again
            self.dig_next = now + COMBO_RETRY
        self.show_end = now

    def _special(self, now, secs=None):
        """The treasure this turn's work turns a find into, or None.  secs: the turn's work time, if it is over."""
        big = self.leader
        marks = set(self.turn_marks)
        if secs is None:
            secs = max(t.get("work", 0.0) for t in big.working.values()) if big.working else 0.0
        if secs >= DIG_LONG:
            marks.add("long")
        hour = time.localtime().tm_hour
        if hour >= DIG_NIGHT[0] or hour < DIG_NIGHT[1]:
            marks.add("night")
        names = self._pool()
        pending = self.pending_finds()
        own = set(self.grow.data["items"]) | set(pending)     # what is put away in this turn is as good as theirs
        got = [item for mark, item in DIG_SPECIAL if mark in marks and item in names
               and not (item == "plane_model" and (self.grow.data["plane_day"] == self.grow._today() or "plane_model" in pending))]
        new = [i for i in got if i not in own]
        if new and random.random() < DIG_SPECIAL_NEW:
            return new[0]
        if got and random.random() < DIG_SPECIAL_AGAIN:
            return random.choice(got)
        return None

    @grow_safe
    def dig_result(self, pet, now, was):
        """The digging is done: -> (treasure, rarity) that comes up, or None.  By hand it is theirs at once and
        takes one of the chances work has earned (so does coming up empty; the next is then sure); by itself it is put away until the turn ends."""
        names = self._items()
        big = self.leader
        force = self.opts["dig_find"]          # tests: "yes", "no" or a treasure's name
        if was["hand"]:
            ok = self.grow.data["chances"] > 0 and not self.replaying      # what one has put away in this turn does not count here
            sure = self.grow.data["dry_hand"] > 0      # the last one by hand came up empty: this one does not
            found = ok and (sure or random.random() < DIG_HAND_LUCK + (DIG_HELP if was.get("helped") else 0.0) or force not in (None, "no"))
            if force == "no" and not sure:
                found = False
            if ok:                             # the one place a chance is used: the digging got to its end, find or no find
                self.grow.data["chances"] -= 1
                self.grow.data["dry_hand"] = 0 if found else 1
                self.grow.dirty = True
        else:
            found = random.random() < DIG_SELF_LUCK + (DIG_HELP if was.get("helped") else 0.0)
            found = (found or force not in (None, "no")) and not self.replaying
        if force == "no" and not was["hand"]:
            found = False
        self.show_end = now + 3.0              # its ending is part of the show
        item = None
        if found:
            rarity_of = self._pool()
            pending = self.pending_finds()
            item = force if force in names else ((None if was["hand"] else self._special(now)) or self.grow.roll(rarity_of, pending))
            if was.get("helped") and force not in names and rarity_of.get(item) != "special":       # your hand in it: the better of two
                other = self.grow.roll(rarity_of, pending)
                order = [n for n, _ in DIG_RARITY]
                if other is not None and item is not None and order.index(rarity_of[other]) > order.index(rarity_of[item]):
                    item = other
        if item is None or item not in names:
            log("dig: %sfound nothing%s" % (pet.tag or "pet0 ", "" if not was["hand"] else
                                            (" (a chance used, the next by hand is sure)" if ok else " (no finds left)")))
            return None
        rarity = str(names[item].get("rarity"))
        if was["hand"]:
            self._loot_credit(item, now, DIG_SIGN_AFTER, pet)
        else:
            self.loot.append((item, pet.slot))
            self._loot_keep()
            s = was.get("session")
            if self.loot_due is None and (s not in big.working or s in big.turn_over):
                self.loot_due = now            # its turn ended while it dug: shown now, not at the end of the next one
        log("dig: %sfound %s (%s)%s" % (pet.tag or "pet0 ", item, rarity, "" if was["hand"] else ", kept till the turn ends"))
        return item, rarity

    @grow_safe
    def _loot_credit(self, item, now, after, who=None):
        """A find is theirs: counted, XP the first time, and its sign when the moment comes.  The first of its kind:
        who (the one that holds it) takes it out again to play with once the showing is over (_first_play_tick)."""
        info = self._items().get(item)
        if info is None or self.replaying:
            return
        rarity = str(info.get("rarity"))
        if item == "plane_model":
            self.grow.data["plane_day"] = self.grow._today()
        count, first = self.grow.take(item, rarity, self._pool())
        if first:
            self.album_check(now)
        if first and who is not None:
            self.first_play = {"pet": who, "item": item, "at": now + after + GROW_DISCOVER_SECS, "until": now + after + FIRST_PLAY_WAIT}
        self._grow_find(GROW_XP["item"] if first else 0, "treasure: %s x%d" % (item, count), now, after, item=item, new=first, count=count,
                        rarity=rarity, zh=str(info.get("zh") or item), en=str(info.get("en") or item))

    # ----------------------------------------------------------- 鼠标小剧场
    def _cursor_pos(self):
        path = self.opts.get("cursor_file")
        if path:
            try:
                with open(path, "r") as f:
                    x, y = f.read().split()[:2]
                return int(float(x)), int(float(y))
            except (OSError, ValueError):
                return None
        pt = POINT()
        if not GetCursorPos(ctypes.byref(pt)):
            return None                        # the lock screen, a UAC prompt
        return pt.x, pt.y

    def _nap_ok(self, pet):
        """Can it (go on to) take part?  Nothing else for it under way, nothing asked of it."""
        return (pet in self.pets and not (pet.dragging or pet.press is not None or pet.in_combo or pet.signing
                                          or pet.sleeping or pet.busy or pet.attention_until or pet.hop is not None
                                          or pet.perch is not None or pet.fly is not None or pet.home is not None
                                          or pet.returning or pet.react is not None or pet.render is not None
                                          or any(p.perch is pet for p in self.pets))
                and not (self.combo is not None and self.combo.get("receiver") is pet))

    def _nap_pick(self, pos):
        """The calm one nearest to the cursor, if it is near enough."""
        best = None
        for pet in self.pets:
            if not pet._calm() or not self._nap_ok(pet):
                continue
            if not all(pet.store.usable(c) for c in DOZE_CLIPS + NAP_LOOKS):
                continue
            px = pet._target_px()
            d = math.hypot(pos[0] - pet.fx, pos[1] - (pet.fy - px * 0.5))
            if d <= NAP_NEAR * px and (best is None or d < best[0]):
                best = (d, pet)
        return best[1] if best else None

    def nap_over(self, pet, now, why):
        """It is taken for something else, or startled awake: this 小剧场 is over."""
        if self.nap is not None and self.nap["pet"] is pet:
            dozed = self.nap["stage"] == "doze"
            self.nap = None
            self.nap_done = True
            if dozed:
                self.nap_rest = now + self.opts["nap_rest"]
            if self.opts["debug"]:
                log("%snap over (%s)" % (pet.tag, why))

    def nap_tick(self, now):
        """The cursor rests near one of them: it looks over, comes closer, sits down and dozes; a move startles it."""
        if now < self.nap_next or self.quitting:
            return
        self.nap_next = now + NAP_TICK
        pos = self._cursor_pos()
        if pos is None:
            return
        if self.nap_at is None or math.hypot(pos[0] - self.nap_at[0], pos[1] - self.nap_at[1]) > NAP_STILL_PX:
            self.nap_at, self.nap_still, self.nap_done = pos, now, False
            if self.nap is not None:
                pet = self.nap["pet"]
                if pet.dozing and pet in self.pets:
                    px = pet._target_px()
                    if math.hypot(pos[0] - pet.fx, pos[1] - (pet.fy - px * 0.5)) <= NAP_NEAR * px:
                        pet.end_doze(now, "the cursor moved")
                    elif pet.doze_alone is None:   # moving about elsewhere: it dozes on a while, then gets up
                        pet.doze_alone = now + self.opts["nap_alone"]
                        if self.opts["debug"]:
                            log("%sdozes on: the cursor went elsewhere" % pet.tag)
                else:
                    self.nap_over(pet, now, "the cursor moved")   # a walk under way just ends where it ends
            return
        still = now - self.nap_still
        t_look, t_come, t_doze = self.nap_times
        nap = self.nap
        if nap is None:
            if self.nap_done or still < t_look or now < self.nap_rest or self.menu_open or self.dots.hover:
                return                         # (on the circles: reading a name, not resting by them)
            pet = self._nap_pick(pos)
            if pet is None:
                return
            self.nap = {"pet": pet, "stage": "look", "t": now}
            pet.extra_wanted = None
            log("%snap: looks at the cursor" % pet.tag)
            dx = pos[0] - pet.fx
            look = NAP_LOOKS[dx > 0] if abs(dx) >= 0.3 * pet._target_px() else "look_at_viewer"
            pet.request(pet._shot_name(look), now, "the cursor rests near")
            return
        pet = nap["pet"]
        if nap["stage"] == "doze":
            if not pet.dozing or pet not in self.pets:     # taken without a call to nap_over (should not happen)
                self.nap = None
                self.nap_done = True
            elif (pet.cur == "doze" and now - pet.last_activity >= pet.sleep_after and self.may_sleep()):
                pet.doze_sleep = True          # dozes off for real at the next nod: the family falls asleep
            return
        if not self._nap_ok(pet) or pet.pending is not None or self.menu_open:
            self.nap_over(pet, now, "busy with something else")
            return
        if pet.cur not in (pet.idle_name, pet._shot_name("look_at_viewer")) + NAP_LOOKS and pet.wander is None:
            self.nap_over(pet, now, "plays " + str(pet.cur))
            return
        wait = t_come - t_look if nap["stage"] == "look" else t_doze - t_come
        if now - nap["t"] < wait or not pet._calm():
            return
        if nap["stage"] == "look":
            nap["stage"], nap["t"] = "come", now
            px = pet._target_px()
            dx = pos[0] - pet.fx
            step = min(abs(dx) - 0.6 * px, NAP_STEP * px)   # not under the cursor: beside it
            if step >= 0.12 * px:
                x = pet.fx + (step if dx > 0 else -step)
                if pet.area is not None:
                    reach = WANDER_AREA * px
                    x = clamp(x, pet.area - reach, pet.area + reach)
                if ((x - pet.fx) * dx > 0 and 0.12 * px <= abs(x - pet.fx) <= NAP_STEP * px + 1
                        and not self._collides(pet, x, pet.fy)):
                    if pet._walk_to(x, pet.fy, now, 3.0, NAP_PACE):
                        log("%snap: comes closer" % pet.tag)
                        pet._next(now, "comes closer")
            return
        nap["stage"], nap["t"] = "doze", now
        log("%snap: dozes off" % pet.tag)
        pet.dozing = True
        pet.doze_manual = pet.doze_sleep = False
        pet.doze_alone = None
        pet.request("doze_in", now, "dozes off")

    def big_fell_asleep(self, now):
        self.wake_due = None
        if random.random() < self.wake_chance:
            self.wake_due = now + random.uniform(*self.wake_range)

    def about_taken(self, pet, now, why):
        """The one a pat is for is picked up or thrown again: the pat is off."""
        if self.combo is not None and self.combo.get("about") is pet:
            self.cancel_combo(why, now)

    def landed(self, pet, now):
        """Down after a throw: those near come and pat it while it is dizzy (not across the screen)."""
        if len(self.pets) >= 2 and not self.hidden:
            self.start_combo("console", now, manual=True, pair=pet, by_hand=False)

    def thrown(self, pet, now):
        """One is thrown: the others are startled (those that are calm)."""
        self.about_taken(pet, now, "thrown again")
        if self.combo is not None and pet in self.combo["pets"]:
            self.cancel_combo("thrown", now)
        i = 0
        for other in self.pets:
            if other is not pet and other._calm() and not self.napping(other):
                i += 1
                other.react = ("surprised", now + FOLLOWER_STAGGER * i)

    def dropped(self, pet, now):
        """Dropped on another one: a high five.  Not with a big one at work or at a question."""
        if pet is self.leader and (pet.busy or pet.attention_until):
            return
        for other in self.pets:
            if other is pet or not self._free(other, True):
                continue
            px, opx = pet._target_px(), other._target_px()
            if (px < opx and abs(pet.fx - other.fx) < opx * 0.35 and abs(pet.fy - self._head(other)) < opx * 0.3
                    and not (other is self.leader and (other.busy or other.attention_until))):
                self.start_combo("stack", now, manual=True, pair=(pet, other), stay=True)   # put on its head
                return
            if abs(pet.fx - other.fx) < (px + opx) * 0.35 and self._same_row(pet, other):    # else: behind it
                self.start_combo("high_five", now, manual=True, pair=(pet, other), stay=True)
                return

    def rendering(self, pet):
        return any(p is not pet and p.render is not None for p in self.pets)

    @staticmethod
    def _same_row(a, b):
        return abs(a.fy - b.fy) <= ROW_TOLERANCE * max(a._target_px(), b._target_px())

    def walk_limits(self, pet, lo, hi):
        """Narrow a walk so that it stops short of the others on its row, wherever their walks go.
        Already too close to one: it can only walk away from that one."""
        px = pet._target_px()
        for other in self.pets:
            if other is pet:
                continue
            opx = other._target_px()
            if not self._same_row(pet, other):
                continue                       # it passes in front or behind
            need = (px + opx) // 2 + int(max(px, opx) * SIBLING_GAP)
            near, far = other.fx, other.fx
            w = other.wander
            if w is not None:
                reach = w["speed"] * max(w["left"], 0.0)
                near, far = max(w["lo"], w["x"] - reach), min(w["hi"], w["x"] + reach)
            if other.fx > pet.fx:
                hi = min(hi, near - need)
            else:
                lo = max(lo, far + need)
        return min(lo, pet.fx), max(hi, pet.fx)

    # ----------------------------------------------------------- size
    def floor(self):
        """The big one's smallest size: the smallest pet stops at SCALE_MIN, the others with it."""
        ratio = min([FAMILY_RATIOS[0]] + [FAMILY_RATIOS[s] for s in self.slots])
        return math.ceil(SCALE_MIN / ratio * 1000.0) / 1000.0

    def big_scale(self):
        return clamp(self.wanted, self.floor(), SCALE_MAX)

    def set_scale(self, scale, now, why):
        self.cancel_combo("size", now, instant=True)
        self.wanted = clamp(float(scale), SCALE_MIN, SCALE_MAX)
        self.apply_scale(now, why)

    def wheel(self, factor, now):
        # from the size shown; at a limit the wheel does nothing, it does not build up
        self.set_scale(clamp(self.big_scale() * factor, self.floor(), SCALE_MAX), now, "ctrl+wheel")

    def apply_scale(self, now, why):
        big = self.leader
        old_scale, old_x, old_y = big.scale, big.fx, big.fy
        size = self.big_scale()
        big.set_scale(size, now, why)
        grow = big.scale / old_scale
        if grow != 1.0:
            self.homes = {}
            for pet in self.pets:
                pet.home = pet.return_at = None
                pet.returning = False
        for pet in self.pets[1:]:
            if grow != 1.0 and abs(pet.fy - old_y) <= pet._target_px():    # on one row: keep the layout
                pet._finish_glide()
                pet.wander = None
                pet._move_feet(big.fx + int(round((pet.fx - old_x) * grow)), pet.fy)
            pet.set_scale(size * FAMILY_RATIOS[pet.slot], now, why)
        if grow != 1.0:                        # the layout grew or shrank with them: their places too
            for pet in self.pets:
                pet.area = pet.fx
        self.save_state()

    # ----------------------------------------------------------- members
    def beside(self, px, placed=None):
        """Feet for a new body of px px: left of the others, or right of them if the left is full."""
        placed = self.pets if placed is None else placed
        big = self.leader
        wa = big._work_area(big.fx, big.fy)
        gap = int(px * SIBLING_GAP)
        left = min(placed, key=lambda p: p.fx)
        x = left.fx - left._target_px() // 2 - gap - px // 2
        if x - px // 2 < wa.left:
            right = max(placed, key=lambda p: p.fx)
            x = right.fx + right._target_px() // 2 + gap + px // 2
        return int(x), big.fy

    def add_follower(self, slot, now, greet, base=None):
        big = self.leader
        scale = round(self.big_scale() * FAMILY_RATIOS[slot], 3)
        if base is None:
            base = FrameStore(self.base_dir).prepare()
        store = choose_store(base, scale, custom_dir_of(slot))
        px = int(round(big.base_body_px * scale))
        feet = None
        if slot in self.pos and self.opts.get("keep_place"):   # else a new one comes beside the others
            x, y, then = self.pos[slot]
            if then and abs(y - big.fy) <= px:   # the family's size changed while it was away
                x = big.fx + int(round((x - big.fx) * big.scale / then))
            feet = (x, y)
        if feet is None or not Pet._feet_on_screen(*feet):
            feet = self.beside(px)
        home = self.homes.get(slot)            # read first: a new window saves the state, without a home yet
        pet = self.add(slot, store, scale, feet)
        if home is not None:
            pet.home = home
            pet.return_at = now + random.uniform(*self.return_range)
        if greet:
            pet.request(pet._shot_name("hop"), now, "hello")
        return pet

    def set_count(self, n, now):
        if not 1 <= n <= len(FAMILY_RATIOS):
            return
        slots = list(range(1, n))
        if slots == self.slots:
            return
        self.cancel_combo("number of pets", now, instant=True)
        self.save_state()                      # remembers where the leaving ones stand
        self.slots = slots
        for pet in self.pets[1:]:
            if pet.slot not in slots:
                pet.close()
        self.apply_scale(now, "family of %d" % n)
        for slot in slots:
            if not any(p.slot == slot for p in self.pets):
                try:
                    self.add_follower(slot, now, greet=True)
                except Exception:
                    log_exc("adding pet %d" % slot)
                    self.slots.remove(slot)
        log("family of %d" % (len(self.slots) + 1))
        self.save_state()

    def dismiss(self, pet, now):
        if pet.slot == 0 or pet.slot not in self.slots:
            return
        self.cancel_combo("a pet left", now, instant=True)
        self.save_state()
        self.slots.remove(pet.slot)
        pet.close()
        self.apply_scale(now, "pet %d left" % pet.slot)
        log("pet %d left, %d shown" % (pet.slot, len(self.pets)))

    def reset(self):
        big = self.leader
        self.cancel_combo("back to the corner", time.perf_counter(), instant=True)
        self.homes = {}
        for pet in self.pets:
            pet.home = pet.return_at = None
            pet.returning = False
        placed = []
        for pet in self.pets:
            pet.wander = None
            pet.glide = None
            pet._move_feet(*(pet._default_feet() if pet is big else pet._clamped(*self.beside(pet._target_px(), placed))))
            pet.area = pet.fx
            placed.append(pet)
        self.save_state()

    def save_state(self):
        big = self.leader
        if big is None:
            return
        for pet in self.pets[1:]:
            fx, fy = pet.ground if pet.ground is not None else (pet.fx, pet.fy)   # not up on another one
            self.pos[pet.slot] = (int(fx), int(fy), round(big.scale, 3))
            if pet.home is not None:
                self.homes[pet.slot] = (int(pet.home[0]), int(pet.home[1]))
            else:
                self.homes.pop(pet.slot, None)
        d = {"x": int(big.fx), "y": int(big.fy), "scale": round(big.scale, 3),
             "wanted": round(self.wanted, 3), "slots": list(self.slots),
             "pos": {str(k): list(v) for k, v in sorted(self.pos.items())}}
        if self.homes:
            d["homes"] = {str(k): list(v) for k, v in sorted(self.homes.items())}
        if LANG != "zh":
            d["lang"] = LANG
        if ACTIVITY != "normal":
            d["activity"] = ACTIVITY
        look = dict((k, v) for k, v in self.look.items() if v != SIGN_LOOK_DEFAULT[k])
        if look:
            d["sign"] = look
        if self.hidden:
            d["hidden"] = True                 # for clawd status / clawd; a new start shows them all the same
        if d == self.saved_state:
            return
        try:
            os.makedirs(HOME_DIR, exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, STATE_PATH)
            self.saved_state = d
        except Exception:
            log_exc("save_state")

    def quit(self, why):
        if self.quitting:
            return
        self.quitting = True
        up = time.perf_counter() - self.born
        pets = list(self.pets)
        ticks = self.n_ticks + sum(p.n_ticks for p in pets)
        draws = self.n_draws + sum(p.n_draws for p in pets)
        log("exit: %s (up %.0fs, %d ticks, %d frames drawn, %.1f fps avg, %.1f MB frames cached)"
            % (why, up, ticks, draws, draws / max(up, 1e-3),
               sum(p.store.loaded_bytes() for p in pets) / 1048576.0))
        self.hidden = set()                    # not saved as hidden: the next start shows them
        try:
            self.save_state()
        except Exception:
            log_exc("save on quit")
        try:
            self._places_save()                # the circles as they are now, for the next start
        except Exception:
            log_exc("talks.json on quit")
        self.grow.save()
        if self.tray is not None:
            self.tray.destroy()
        self.sign = None
        self.sign_board.destroy()
        self.dots.destroy()
        self.dot_tip.destroy()
        for pet in reversed(pets):
            pet.close()

    def window_gone(self, hwnd, pet):
        if self.nap is not None and self.nap["pet"] is pet:
            self.nap = None
            self.nap_done = True
        self.windows.pop(hwnd, None)
        self.depth_dirty = True
        self.depth_order = None
        pet.destroy_gdi()
        if pet in self.pets:
            self.pets.remove(pet)
            self.n_ticks += pet.n_ticks
            self.n_draws += pet.n_draws
        if not self.windows:
            PostQuitMessage(0)

    def destroy(self):
        if self.tray is not None:              # also after a crash: no dead icon left in the tray
            self.tray.destroy()
        for pet in list(self.pets):
            pet.destroy_gdi()
        try:
            UnregisterClassW(CLASS_NAME, self.hinst)
        except Exception:
            log_exc("cleanup")

    def _wndproc_py(self, hwnd, msg, wparam, lparam):
        pet = self.windows.get(hwnd)           # none yet while CreateWindowEx is still running
        if pet is not None:
            try:
                r = pet._handle(hwnd, msg, wparam, lparam)
                if r is not None:
                    return r
            except Exception:
                log_exc("wndproc msg 0x%04X" % msg)
        elif hwnd == self.dots.hwnd and hwnd:
            try:
                r = self.dots.handle(msg, wparam, lparam)
                if r is not None:
                    return r
            except Exception:
                log_exc("circles msg 0x%04X" % msg)
        elif self.tray is not None and hwnd == self.tray.hwnd:
            try:
                r = self.tray.handle(msg, wparam, lparam)
                if r is not None:
                    return r
            except Exception:
                log_exc("tray msg 0x%04X" % msg)
        return DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        msg = MSG()
        while True:
            r = GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0:
                break
            if r == -1:
                log("GetMessageW failed, error %d" % ctypes.get_last_error())
                break
            TranslateMessage(ctypes.byref(msg))
            DispatchMessageW(ctypes.byref(msg))


# --------------------------------------------------------------------------- main
def _range_opt(val, default):
    lo, _, hi = val.partition("-")
    try:
        lo = float(lo)
        hi = float(hi or lo)
        return (max(0.5, min(lo, hi)), max(0.5, lo, hi))
    except ValueError:
        return default


def parse_args(argv):
    opts = {"frames_dir": None, "debug": False, "extra_range": EXTRA_RANGE, "home": None, "grow_quiet": False,
            "wander_range": WANDER_RANGE, "sleep_after": SLEEP_AFTER, "dump_dir": None,
            "combo_range": COMBO_EVERY, "peek_after": COMBO_PEEK_AFTER, "wake_range": COMBO_WAKE_AFTER,
            "wake_chance": COMBO_WAKE_CHANCE, "mimic_range": MIMIC_EVERY, "return_range": RETURN_AFTER,
            "play_range": PLAY_EVERY, "play_after": PLAY_AFTER, "nap_times": NAP_TIMES, "nap_rest": NAP_REST, "nap_alone": NAP_ALONE, "cursor_file": None, "show_gap": SHOW_GAP, "dig_every": None, "dig_find": None, "dig_most": None, "chance_work": None, "play_alone": PLAY_ALONE_CHANCE}
    valued = ("--frames-dir", "--extra-interval", "--wander-interval", "--sleep-after",
              "--home", "--dump-dir", "--combo-interval", "--peek-after", "--wake-after",
              "--mimic-interval", "--return-after", "--play-interval", "--play-after", "--nap-times", "--nap-rest", "--nap-alone", "--cursor-file", "--show-gap", "--dig-every", "--dig-find", "--dig-most", "--chance-work", "--play-alone", "--slip", "--talk-keep", "--talk-done-keep", "--cut-quiet", "--attention-timeout", "--busy-timeout")
    it = iter(argv)
    for a in it:
        key, eq, val = a.partition("=")
        if key in valued and not eq:
            val = next(it, "")
        if key == "--frames-dir" and val:
            opts["frames_dir"] = os.path.abspath(val)
        elif key == "--home" and val:
            opts["home"] = os.path.abspath(val)
        elif key == "--nap-times" and val:     # tests: look,come,doze seconds of a still cursor
            try:
                t = tuple(max(0.0, float(v)) for v in val.split(","))
                if len(t) == 3 and t[0] <= t[1] <= t[2]:
                    opts["nap_times"] = t
            except ValueError:
                pass
        elif key == "--nap-alone" and val:
            try:
                opts["nap_alone"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--nap-rest" and val:
            try:
                opts["nap_rest"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--cursor-file" and val:   # tests: "x y" read from this file instead of the real cursor
            opts["cursor_file"] = os.path.abspath(val)
        elif key == "--dump-dir" and val:
            opts["dump_dir"] = os.path.abspath(val)
        elif key == "--extra-interval" and val:
            opts["extra_range"] = _range_opt(val, EXTRA_RANGE)
        elif key == "--wander-interval" and val:
            opts["wander_range"] = _range_opt(val, WANDER_RANGE)
        elif key == "--mimic-interval" and val:
            opts["mimic_range"] = _range_opt(val, MIMIC_EVERY)
        elif key == "--play-interval" and val:
            opts["play_range"] = _range_opt(val, PLAY_EVERY)
        elif key == "--return-after" and val:
            opts["return_range"] = _range_opt(val, RETURN_AFTER)
        elif key == "--combo-interval" and val:
            opts["combo_range"] = _range_opt(val, COMBO_EVERY)
        elif key == "--wake-after" and val:
            opts["wake_range"] = _range_opt(val, COMBO_WAKE_AFTER)
            opts["wake_chance"] = 1.0          # a test does not wait for its luck
        elif key == "--talk-done-keep" and val:    # s a circle stays green after its turn
            try:
                opts["talk_done_keep"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--attention-timeout" and val:     # s the big one's "your turn" sign and wave last
            try:
                opts["attention_timeout"] = max(1.0, float(val))
            except ValueError:
                pass
        elif key == "--cut-quiet" and val:     # s a quiet turn waits before its transcript is looked at
            try:
                opts["cut_quiet"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--busy-timeout" and val:  # tests: s a turn that says nothing keeps the big one at work
            try:
                opts["busy_timeout"] = max(1.0, float(val))
            except ValueError:
                pass
        elif key == "--talk-keep" and val:     # s a silent conversation keeps its circle
            try:
                opts["talk_keep"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--dig-every" and val:         # tests: s of a turn's work time for each dig by itself
            try:
                opts["dig_every"] = max(0.5, float(val))
            except ValueError:
                pass
        elif key == "--dig-most" and val:          # tests: digs by itself a turn at most
            try:
                opts["dig_most"] = max(1, int(val))
            except ValueError:
                pass
        elif key == "--chance-work" and val:       # tests: s of work for a chance to dig by hand (0: each turn one)
            try:
                opts["chance_work"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--play-alone" and val:        # tests: the chance an idle extra is a treasure to play with
            try:
                opts["play_alone"] = clamp(float(val), 0.0, 1.0)
            except ValueError:
                pass
        elif key == "--dig-find" and val:          # tests: every dig finds something ("yes"), nothing ("no"), or this treasure
            opts["dig_find"] = val
        elif key == "--slip" and val:              # tests: the combos of SLIPS always go the other way ("yes") or never ("no")
            opts["slip"] = val
        elif key == "--show-gap" and val:
            try:
                opts["show_gap"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--play-after" and val:
            try:
                opts["play_after"] = max(0.0, float(val))
            except ValueError:
                pass
        elif key == "--peek-after" and val:
            try:
                opts["peek_after"] = max(1.0, float(val))
            except ValueError:
                pass
        elif key == "--sleep-after" and val:
            try:
                opts["sleep_after"] = max(1.0, float(val))
            except ValueError:
                pass
        elif key == "--debug":
            opts["debug"] = True
        elif key == "--keep-place":            # tests: start where state.json says, not in the corner
            opts["keep_place"] = True
        elif key == "--grow-quiet":            # tests of other things: XP is counted, no growth sign or level-up cheer
            opts["grow_quiet"] = True
        elif key == "--tray":                  # a --home instance with a tray icon too (else none: no dead icons from tests)
            opts["tray"] = True
        elif key == "--first-start":           # tests: the very first start's hint and connect window, also with --home
            opts["first_start"] = True
    return opts


def choose_store(base, scale, custom_dir):
    """Start on the custom set if it matches the saved size, else on frames_hi above 100 %,
    else on the base set."""
    if scale == 1.0:
        remove_custom_sets(custom_dir, "size is 100%")
        return base
    remove_stale_render_dirs(custom_dir)
    target = int(round(base.body_px * scale))
    if os.path.isfile(os.path.join(custom_dir, "manifest.json")):
        c = try_store(custom_dir)
        if c is not None and c.body_px == target and has_all_actions(c, base.dir):
            return c
    hi_dir = hi_dir_of(base.dir)
    if target > base.body_px and os.path.isfile(os.path.join(hi_dir, "manifest.json")):
        hi = try_store(hi_dir)
        if hi is not None and hi.body_px >= target:
            return hi
    return base


def main(argv):
    opts = parse_args(argv)
    mutex_name = MUTEX_NAME
    if opts["home"]:
        set_home(opts["home"])
        mutex_name = MUTEX_NAME + ".test"
    base_dir = opts["frames_dir"] or BASE_FRAMES_DIR
    mutex = CreateMutexW(None, False, mutex_name)
    err = ctypes.get_last_error()
    if not mutex or err == ERROR_ALREADY_EXISTS:
        if mutex:
            CloseHandle(mutex)
        return 0                         # already running: leave quietly
    family = None
    try:
        disable_ime()
        set_dpi_awareness()
        os.makedirs(HOME_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        if opts["dump_dir"]:
            os.makedirs(opts["dump_dir"], exist_ok=True)
        base = FrameStore(base_dir).prepare()
        base.align_to_base()
        first = not os.path.exists(STATE_PATH)  # the very first start: no state yet (written below, at once)
        feet, scale, migrated = load_state()
        load_lang()
        load_activity()
        if migrated:
            log("state.json v1 (window corner) migrated to feet point %s" % (feet,))
        family = Family(base_dir, opts)
        wanted, family.slots, family.pos = load_family()
        family.homes = load_homes()
        if not opts.get("keep_place"):         # every start in the corner; only the size and the members stay
            feet, family.pos, family.homes = None, {}, {}
        family.wanted = scale if wanted is None else wanted
        scale = family.big_scale()
        store = choose_store(base, scale, custom_dir_of(0))
        pet = family.add(0, store, scale, feet)
        log("start v2: frames=%s %dx%d body %dpx (manifest v%d), %d actions, scale %d%%, "
            "display factor %.3f, feet=(%d, %d)"
            % (store.dir, store.width, store.height, store.body_px, store.version,
               len(store.meta), round(scale * 100), pet.disp, pet.fx, pet.fy))
        now = time.perf_counter()
        for slot in list(family.slots):
            try:
                family.add_follower(slot, now, greet=False, base=base)
            except Exception:
                log_exc("adding pet %d" % slot)
                family.slots.remove(slot)
        if family.slots:
            log("family of %d" % (len(family.slots) + 1))
        family.save_state()
        if (first and not opts["home"]) or opts.get("first_start"):
            family.first_start = now + FIRST_START_AFTER
            log("first start: the hint and the connect window in %.0f s" % FIRST_START_AFTER)
        if not opts["home"]:
            refresh_hooks()
        if not opts["home"] or opts.get("tray"):
            try:
                family.tray = Tray(family, base)
            except Exception:
                log_exc("tray icon")           # the pets work without it; only hiding needs it
        family.replay_last_event()
        store = base = pet = None        # the pets own them now; a later swap must be able to free them
        family.run()
        return 0
    except Exception:
        log_exc("main")
        if family is not None and not family.quitting:
            try:
                family.quit("fatal error")
            except Exception:
                pass
        return 1
    finally:
        if family is not None:
            family.destroy()
        CloseHandle(mutex)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
