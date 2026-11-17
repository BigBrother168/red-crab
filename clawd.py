# -*- coding: utf-8 -*-
"""Clawd 桌面小宠物命令行工具（仅标准库）。
用法: python -I -S clawd.py [on|off|hide|show|do <动作>|size [百分比]|list|status|lang [zh|en]|activity [quiet|normal|lively]|autostart [on|off]|hooks on|off|status [claude|codex|deepseek|antigravity]]
"""
import sys
import os
import re
import json
import shutil
import subprocess
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))       # the program
HERE_FWD = HERE.replace("\\", "/")           # for commands run by bash


def data_home():
    """What the pets keep (event, state, saves): found as clawd_pet.pyw finds it (default_home): CLAWD_HOME; this
    folder if a save is already here (a copy run from source); else %APPDATA%\\Clawd (an install)."""
    h = os.environ.get("CLAWD_HOME")
    if h:
        return os.path.abspath(h)
    if any(os.path.exists(os.path.join(HERE, n)) for n in ("state.json", "grow.json")):
        return HERE
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Clawd")


HOME = data_home()
EVENT_FILE = os.path.join(HOME, "event")
MANIFEST = os.path.join(HERE, "frames", "manifest.json")
PET = os.path.join(HERE, "clawd_pet.pyw")
# the Python that runs this (what the hooks and the pet run with too): no fixed install place.  The hooks run
# python.exe, also when this is loaded by a window run with pythonw.exe (the connect window, the pets)
PYTHON = os.path.abspath(sys.executable or r"C:\Python312\python.exe")
if os.path.basename(PYTHON).lower() == "pythonw.exe" and os.path.isfile(os.path.join(os.path.dirname(PYTHON), "python.exe")):
    PYTHON = os.path.join(os.path.dirname(PYTHON), "python.exe")
_w = os.path.join(os.path.dirname(PYTHON), "pythonw.exe")
PYTHONW = _w if os.path.isfile(_w) else PYTHON
MUTEX_NAME = "Local\\ClawdDesktopPet"
# where each agent keeps its settings: their own variables first (CLAUDE_CONFIG_DIR, CODEX_HOME), then the home folder
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
CODEX_DIR = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
DSH_DIR = (os.environ.get("DSH_HOME") or "").strip() or os.path.join(os.path.expanduser("~"), ".dsh")
DEFAULT_SETTINGS = os.path.join(CLAUDE_DIR, "settings.json")


def _q(path):
    """A path in a command: quoted only when it has a space (so an install without one stays as it was)."""
    return '"%s"' % path if " " in path else path


PY_FWD = _q(PYTHON.replace("\\", "/"))
PY_EXEC = PYTHON.replace("\\", "/")         # exec form (args): no shell, so no quoting
MARK = "#clawd-event"

ACTIONS = [
    ("idle", "待机"), ("listen", "认真听"), ("think", "想一想"), ("nod", "点头"),
    ("thumbs_up", "点赞"), ("confused", "困惑"), ("shrug_sweat", "摊手流汗"),
    ("aha", "恍然大悟"), ("celebrate", "庆祝"), ("wave", "挥手"), ("hop", "开心小跳"),
    ("surprised", "吓一跳"), ("head_tilt", "歪头"), ("wink", "眨眼"),
    ("look_at_viewer", "看向你"), ("proud", "叉腰"), ("shake_head", "摇头"),
    ("tiptoe_peek", "踮脚看"), ("work_read", "放大镜"), ("work_edit", "打字"),
    ("work_run", "跑命令"), ("work_web", "望远镜"), ("work_compact", "整理记忆"),
    ("work_agent", "纸飞机"),
]

# (事件, matcher 或 None, 写入的事件词)；其他工具的 PreToolUse 不写，保持当前动作
HOOK_MAP = [
    ("UserPromptSubmit", None, "listen"),
    ("PreToolUse", "Read|Grep|Glob", "read"),
    ("PreToolUse", "Edit|Write|NotebookEdit", "edit"),
    ("PreToolUse", "Bash|PowerShell", "run"),
    ("PreToolUse", "WebSearch|WebFetch", "web"),
    ("PostToolUse", None, "think"),
    ("PostToolUseFailure", None, "fail"),
    ("SubagentStart", None, "agent"),
    ("SubagentStop", None, "agent_done"),
    ("PreCompact", None, "compact"),
    ("PostCompact", None, "compact_end"),
    ("Stop", None, "stop"),
    ("StopFailure", None, "stopfail"),
    ("PermissionRequest", None, "attention"),
    ("Notification", None, "attention"),
    ("SessionStart", None, "hello"),
    ("SessionEnd", None, "bye"),
]
# 对话在哪个窗口（"at" 行，给对话圆圈用）：这些事件各多挂一个 clawd_hook.py，每个对话开始、每条消息各记一次
WHERE_EVENTS = ("SessionStart", "UserPromptSubmit")
# Codex（~/.codex/hooks.json，格式和 Claude Code 一样）。它的 hook 在 Windows 上不一定跑在 bash 里，所以每个词
# 都由 clawd_hook.py 写；没有 PostToolUseFailure（命令失败也发 PostToolUse），读文件、查网页走 shell 或不发 hook
CODEX_MAP = [
    ("UserPromptSubmit", None, "listen"),
    ("PreToolUse", "Bash", "run"),
    ("PreToolUse", "apply_patch", "edit"),
    ("PostToolUse", None, "think"),
    ("SubagentStart", None, "agent"),
    ("SubagentStop", None, "agent_done"),
    ("PreCompact", None, "compact"),
    ("PostCompact", None, "compact_end"),
    ("Stop", None, "stop"),
    ("PermissionRequest", None, "attention"),
    ("SessionStart", None, "hello"),
    ("SessionEnd", None, "bye"),
]
# 每个 agent 一张翻译表：它的哪个事件（和工具）-> 桌宠认的哪个词。桌宠本身不分 agent
# DeepSeek Harness 不用 hook（它在 Windows 上把 hook 命令放进沙箱，写不到工作区外面），而是装一个只听不拦的插件
# clawd_dsh.mjs：翻译表在插件里，这里只往桌面版的配置（profiles/desktop/cordis.patch.yml）末尾加一段、删一段
AGENTS = {
    "claude": {"name": "Claude Code", "settings": DEFAULT_SETTINGS, "map": HOOK_MAP, "exec": True},
    "codex": {"name": "Codex", "settings": os.path.join(CODEX_DIR, "hooks.json"), "map": CODEX_MAP},
    "deepseek": {"name": "DeepSeek Harness", "settings": os.path.join(DSH_DIR, "profiles", "desktop", "cordis.patch.yml"),
                 "plugin": True},
    "antigravity": {"name": "Antigravity", "settings": os.path.join(os.path.expanduser("~"), ".gemini", "config", "hooks.json"),
                    "named": True},
}
# Antigravity（~/.gemini/config/hooks.json）：格式是“hook 名 -> 事件”，我们只占 "clawd" 这一项。它等每个 hook 跑完
# 才往下走，所以每个事件只挂一个、matcher 用 "*"，按工具名翻译放在 clawd_hook.py（AG_TOOLS）。命令由 cmd /c 运行
# 不挂 PreToolUse：它把没有 decision 的答复（我们的 {}）当成拒绝，每个工具都被拦（2026-11-13 用户实测：
# “tool call denied by pre-tool hook”），而回 allow 会绕过用户自己的权限设置。所以工具做完（PostToolUse）才显示它的动作
AG_KEY = "clawd"
AG_EVENTS = [("SessionStart", "ag_start"), ("PreInvocation", "ag_turn"), ("PostToolUse", "ag_done"), ("Stop", "ag_stop")]
AG_TOOL_EVENTS = ("PostToolUse",)
DSH_BEGIN = "# >>> clawd-pet: the desktop pets follow this agent (clawd hooks on deepseek; clawd hooks off deepseek removes it)"
DSH_END = "# <<< clawd-pet"
STATE_FILE = os.path.join(HOME, "state.json")
AUTOSTART_EVENT = "SessionStart"
AUTOSTART_HOOK = {"type": "command", "command": PY_EXEC,
                  "args": ["-I", "-S", HERE_FWD + "/clawd.py", "on", "--quiet", MARK], "async": True}


INTERNAL_CLIPS = ("walk_left", "walk_right", "turn_left", "turn_right", "wake_up", "sign_left", "sign_right", "high_five_left", "high_five_right",
                  "high_five_up_left", "high_five_up_right", "nudge_left", "nudge_right", "peek_left", "peek_right", "comfort_left", "comfort_right",
                  "stack_brace", "stack_hop", "stack_top", "carry_start_left", "carry_start_right", "walk_carry_left", "walk_carry_right",
                  "carry_hold_left", "carry_hold_right", "leap_crouch", "tumble_left", "tumble_right", "squash", "doze_in", "doze_startle", "doze_up", "doze_sleep",
                  "nap_look_left", "nap_look_right", "rummage_in", "rummage_found", "rummage_none", "rummage_up", "rummage_spur", "rummage_fast", "pull_out", "present", "play_look", "play_toss", "play_listen", "play_show") + tuple(n + d for d in ("left", "right") for n in ("bring_start_", "bring_hold_", "walk_bring_", "hand_mid_", "hand_small_", "take_")) + tuple("%s_%s%s" % (a, k, d) for a in ("give", "receive")
                  for k in ("", "mid_", "small_") for d in ("left", "right"))
# the cells of the album's combo page
ALBUM_COMBOS = 9 + 1                 # the 图鉴's combo cells: the menu's nine and the pat after a throw
COMBOS = [("high_five", "击掌"), ("celebrate_all", "全家庆祝"), ("peek", "凑过来看"), ("wake", "拱醒"), ("parade", "排排走"), ("comfort", "一起安慰"), ("stack", "叠罗汉"), ("note", "传纸条"), ("leapfrog", "跳山羊")]


ACTION_EN = {
    "rummage": "Rummage",
    "idle": "Idle", "listen": "Listening", "think": "Thinking", "nod": "Nod",
    "thumbs_up": "Thumbs up", "confused": "Confused", "shrug_sweat": "Shrug", "aha": "Aha",
    "celebrate": "Celebrate", "wave": "Wave", "hop": "Happy hop", "surprised": "Startled",
    "head_tilt": "Head tilt", "wink": "Wink", "look_at_viewer": "Look at you",
    "proud": "Hands on hips", "shake_head": "Shake head", "tiptoe_peek": "Tiptoe peek",
    "sleep": "Sleep", "walk": "Walk", "work_read": "Magnifier", "work_edit": "Typing",
    "work_run": "Terminal", "work_web": "Telescope", "work_compact": "Tidy up memory",
    "work_agent": "Paper plane", "dangle": "Dangle", "land": "Land", "shy": "Shy",
    "wake_up": "Wake up", "dizzy": "Dizzy", "doze": "Doze",
}
COMBO_EN = {
    "high_five": "High five", "celebrate_all": "Family cheer", "peek": "Come and look",
    "wake": "Nudge awake", "parade": "Parade", "comfort": "Comfort", "stack": "Tower",
    "note": "Pass a note", "leapfrog": "Leapfrog",
}
LANG_ALIASES = {
    "zh": "zh", "cn": "zh", "chinese": "zh", "中文": "zh", "汉语": "zh", "简体中文": "zh", "zh-cn": "zh",
    "en": "en", "english": "en", "英文": "en", "英语": "en", "en-us": "en",
}
_LANG = None


def get_lang():
    """当前界面语言（state.json 的 "lang"），没有就跟系统（中文 Windows 是 zh，其他 en，和桌宠一样）。每个进程只读一次。"""
    global _LANG
    if _LANG is None:
        v = read_state().get("lang")
        if v not in ("zh", "en"):
            try:
                import ctypes
                v = "zh" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x04 else "en"
            except Exception:
                v = "zh"
        _LANG = v
    return _LANG


def T(zh, en):
    return en if get_lang() == "en" else zh


def norm_name(a):
    """名字比较用：去引号、小写、空格/下划线/连字符都当成同一个分隔符。"""
    return re.sub(r"[\s_\-]+", "_", a.strip().strip("\"'").strip().lower())


def say(msg, quiet=False):
    if not quiet:
        print(msg)


def is_running():
    if os.name != "nt":
        return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.OpenMutexW.restype = ctypes.c_void_p
        k.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
        h = k.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
        if h:
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            k.CloseHandle(h)
            return True
        return False
    except Exception:
        return False


def load_actions():
    """返回 [(name, label)]，优先使用 manifest。"""
    try:
        with open(MANIFEST, "r", encoding="utf-8-sig") as f:
            m = json.load(f)
        acts = m.get("actions") or {}
        if acts:
            return [(k, (v or {}).get("label", k)) for k, v in acts.items()
                    if k not in INTERNAL_CLIPS and not k.startswith("play_")]
    except Exception:
        pass
    return list(ACTIONS)


def write_event(token):
    os.makedirs(HOME, exist_ok=True)
    with open(EVENT_FILE, "a", encoding="utf-8", newline="\n") as f:
        f.write(token + "\n")


def cmd_on(quiet=False):
    if is_running():
        if read_state().get("hidden") and not quiet:   # quiet: the autostart hook, which must not undo a hide
            write_event("show")
            say(T("Clawd 已经在运行，刚才是隐藏的，已显示出来。", "Clawd is already running; it was hidden, now it shows."), quiet)
            return 0
        say(T("Clawd 已经在运行了。", "Clawd is already running."), quiet)
        return 0
    if not os.path.exists(PET):
        say(T("找不到 clawd_pet.pyw，无法启动。", "Cannot find clawd_pet.pyw, so it cannot start."), quiet)
        return 1
    base = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True, cwd=HERE)
    try:
        subprocess.Popen([PYTHONW, PET], creationflags=base | 0x01000000, **kw)
    except OSError:
        try:
            subprocess.Popen([PYTHONW, PET], creationflags=base, **kw)
        except OSError as e:
            say(T("启动失败：%s", "Failed to start: %s") % e, quiet)
            return 1
    say(T("Clawd 已启动。", "Clawd started."), quiet)
    return 0


def cmd_off(quiet=False):
    write_event("quit")
    say(T("已通知 Clawd 退出。", "Asked Clawd to quit.") if is_running()
        else T("Clawd 当前未在运行（已写入退出指令）。", "Clawd isn't running (quit command written)."), quiet)
    return 0


def resolve_action(arg):
    """中文名、英文名、内部名都认，与当前语言无关。"""
    a = arg.strip().strip("\"'").strip()
    norm = norm_name(a)
    for name, label in load_actions():
        if norm == name or a == label or norm == norm_name(ACTION_EN.get(name, name)):
            return name
    return None


def resolve_combo(arg):
    a = arg.strip().strip("\"'").strip()
    norm = norm_name(a)
    for name, label in COMBOS:
        if norm == name or a == label or norm == norm_name(COMBO_EN.get(name, name)):
            return name
    return None


def action_label(name, zh_label):
    return ACTION_EN.get(name, name) if get_lang() == "en" else zh_label


def combo_label(name, zh_label):
    return COMBO_EN.get(name, name) if get_lang() == "en" else zh_label


PLAY_WORDS = ("把玩", "play", "玩")


def load_treasures():
    """-> {内部名: (中文名, 英文名)}，来自帧清单。"""
    try:
        with open(MANIFEST, "r", encoding="utf-8-sig") as f:
            names = (json.load(f).get("items") or {}).get("names") or {}
        return dict((k, (str(v.get("zh") or k), str(v.get("en") or k))) for k, v in names.items())
    except Exception:
        return {}


def cmd_play(args, quiet=False):
    """do 把玩 [宝贝]：拿一件收集到的宝贝出来玩，不写宝贝就随便拿一件。"""
    names = load_treasures()
    grow, _ = read_grow()
    own = (grow or {}).get("items") or {}
    have = [k for k in names if type(own.get(k)) is int and own[k] > 0]
    if not have:
        say(T("还没有宝贝，先让它们翻找吧。", "No treasures yet: let them rummage first."), quiet)
        return 2
    name = None
    if args:
        a = " ".join(args).strip().strip("\"'").strip()
        norm = norm_name(a)
        name = next((k for k, (zh, en) in names.items() if norm == k or a == zh or norm == norm_name(en)), None)
        if name is None:
            say(T("没有这件宝贝：%s", "No such treasure: %s") % a, quiet)
            return 2
        if name not in have:
            say(T("%s 还没找到。", "%s is not found yet.") % names[name][get_lang() == "en"], quiet)
            return 2
    write_event("play:" + name if name else "play")
    shown = names[name][get_lang() == "en"] if name else T("随便一件", "any one")
    if is_running():
        say(T("好的：把玩 %s", "OK: playing with %s") % shown, quiet)
    else:
        say(T("Clawd 没在运行（已写入；3 秒内启动会补播，否则忽略）。",
              "Clawd isn't running (written; it replays if you start it within 3 seconds, otherwise it is ignored)."), quiet)
    return 0


def cmd_do(args, quiet=False):
    if not args:
        say(T("用法：do <动作>。可用 list 查看动作。", "Usage: do <action>. Run list to see the actions."), quiet)
        return 2
    if args[0].strip().lower() in PLAY_WORDS:
        return cmd_play(args[1:], quiet)
    combo = resolve_combo(" ".join(args))
    if combo is not None:
        slots = read_state().get("slots")
        if not slots:
            say(T("组合动作至少要两只，先运行 clawd 2。", "Combos need at least two pets. Run clawd 2 first."), quiet)
            return 2
        write_event("combo:" + combo)
        shown = combo_label(combo, dict(COMBOS)[combo])
        if is_running():
            say(T("好的：%s", "OK: %s") % shown, quiet)
        else:
            say(T("Clawd 没在运行（已写入 %s；3 秒内启动会补播，否则忽略）。",
                  "Clawd isn't running (wrote %s; it replays if you start it within 3 seconds, otherwise it is ignored).") % shown, quiet)
        return 0
    name = resolve_action(" ".join(args))
    if name is None:
        say(T("未知动作：%s。可用 list 查看动作。", "Unknown action: %s. Run list to see the actions.") % " ".join(args), quiet)
        return 2
    write_event(name)
    shown = action_label(name, dict(load_actions()).get(name, name))
    if is_running():
        say(T("好的：%s", "OK: %s") % shown, quiet)
    else:
        say(T("Clawd 没在运行（已写入 %s；3 秒内启动会补播，否则忽略）。",
              "Clawd isn't running (wrote %s; it replays if you start it within 3 seconds, otherwise it is ignored).") % shown, quiet)
    return 0


def read_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_state(d):
    os.makedirs(HOME, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, STATE_FILE)


def family_floor(slots):
    """全家一起缩放时大的最小百分比：最小那只到 50% 时全家一起停。"""
    return 84 if 2 in slots else 63 if 1 in slots else 50


def cmd_family(n, quiet=False):
    if is_running():
        write_event("family:%d" % n)
        say(T("好的：现在是 %d 只。", "OK: now %d pet%s.") % ((n,) if get_lang() == "zh" else (n, "" if n == 1 else "s")), quiet)
        return 0
    d = read_state()
    d["slots"] = list(range(1, n))
    write_state(d)
    return cmd_on(quiet)


def cmd_size(args, quiet=False):
    if not args:
        try:
            with open(STATE_FILE, "r", encoding="utf-8-sig") as f:
                sc = float(json.load(f).get("scale", 1.0))
            print(T("当前缩放：%d%%", "Current scale: %d%%") % round(sc * 100))
        except Exception:
            print(T("当前缩放：100%（尚无 state.json）", "Current scale: 100% (no state.json yet)"))
        return 0
    a = args[0].strip().strip("\"'").rstrip("%").strip()
    try:
        pct = float(a)
    except ValueError:
        print(T("用法：size [50..300]，例如 size 150 或 size 150%", "Usage: size [50..300], e.g. size 150 or size 150%"))
        return 2
    if not (50 <= pct <= 300):
        print(T("百分比须在 50 到 300 之间。", "The percentage must be between 50 and 300."))
        return 2
    write_event("size:%g" % pct)
    slots = read_state().get("slots")
    floor = family_floor(slots if isinstance(slots, list) else [])
    if pct < floor:
        say(T("现在这几只最小是 %d%%，会停在这里；只数变少时再恢复到 %g%%。",
              "With this many pets the smallest size is %d%%, so it stops there; it goes back to %g%% when there are fewer pets.") % (floor, pct), quiet)
    else:
        say(T("好的：缩放 %g%%", "OK: scale %g%%") % pct, quiet)
    return 0


def cmd_list():
    for name, label in load_actions():
        print("%-16s %s" % (name, action_label(name, label)))
    for name, label in COMBOS:
        print(T("%-16s %s（组合）", "%-16s %s (combo)") % (name, combo_label(name, label)))
    return 0


def grow_need(level):
    """和 clawd_pet.pyw 一样：从 Lv.level 升到下一级要的经验。"""
    return min(int(round(40 * level ** 1.5)), 1080)


def read_grow():
    """-> (grow.json 的内容, 是否来自 grow.json.bak)；都没有或都坏了：(None, False)。"""
    for name in ("grow.json", "grow.json.bak"):
        try:
            with open(os.path.join(HOME, name), "r", encoding="utf-8-sig") as f:
                d = json.load(f)
            if isinstance(d, dict) and type(d.get("xp")) is int and d["xp"] >= 0:
                d["xp"] = min(d["xp"], 10 ** 9)      # 和桌宠一样封顶，手改的大数不会算很久
                return d, name != "grow.json"
        except Exception:
            pass
    return None, False


def span_text(secs):
    m = int(secs // 60)
    if m < 60:
        return T("%d 分钟", "%d min") % m
    return T("%d 小时 %d 分", "%d h %d min") % (m // 60, m % 60)


def load_pet():
    """clawd_pet.pyw as a module, for its tables (the level gifts); a stand-in without them if it cannot be read."""
    try:
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("clawd_pet", os.path.join(HERE, "clawd_pet.pyw"))
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("clawd_pet", loader))
        loader.exec_module(mod)
        return mod
    except Exception:
        class Nothing(object):
            pass
        return Nothing()


def grow_lines(running):
    d, from_bak = read_grow()
    if d is None:
        return [T("养成：还没有记录（让智能体干完一个回合就有了）。",
                  "Growth: nothing yet (it starts with the agent's first finished turn).")]
    pet = load_pet()
    top = getattr(pet, "LEVEL_MAX", 10 ** 6)
    level, into = 1, d["xp"]
    while into >= grow_need(level) and level < top:
        into -= grow_need(level)
        level += 1
    need = grow_need(level)
    n = 12
    filled = n if level >= top else min(n, int(n * into / need))
    bar = "█" * filled + "░" * (n - filled)

    def num(key):
        v = d.get(key, 0)
        return v if isinstance(v, (int, float)) else 0
    seen = d.get("seen") if isinstance(d.get("seen"), dict) else {}
    combos = d.get("combos") if isinstance(d.get("combos"), dict) else {}
    acts = d.get("acts") if isinstance(d.get("acts"), dict) else {}
    stars = sum(sum(1 for need in (10, 30, 100) if type(v) is int and v >= need) for v in combos.values())
    special = sum(1 for a in ("shy", "dangle", "tumble", "dizzy", "doze", "doze_startle", "doze_up", "shrug_sweat", "surprised")
                  if a in acts)
    items = d.get("items") if isinstance(d.get("items"), dict) else {}
    if level >= top:
        head = T("全家 Lv.%d  %s  满级！", "Family Lv.%d  %s  top level!") % (level, bar)
    else:
        head = (T("全家 Lv.%d  %s  %d/%d（升到 Lv.%d 还差 %d 经验）", "Family Lv.%d  %s  %d/%d (%d more XP to Lv.%d)")
                % ((level, bar, into, need, level + 1, need - into) if get_lang() == "zh" else (level, bar, into, need, need - into, level + 1)))
    gift = pet.next_gift(level) if hasattr(pet, "next_gift") else None
    lines = [head]
    if gift:
        lines.append(T("下一份礼物：Lv.%d %s", "Next gift: Lv.%d %s") % (gift[0], gift[2][0] if get_lang() == "zh" else gift[2][1]))
    lines += [
             T("回合 %d · 一起工作 %s · 帮手回来 %d 次 · 修好错误 %d 次 · 一起 %d 天",
               "Turns %d · worked together %s · helpers back %d · errors fixed %d · days together %d")
             % (num("turns"), span_text(num("work_secs")), num("agents"), num("fixes"), num("days")),
             T("见过的组合 %d/%d · 星星 %d/%d · 特殊动作 %d/9", "Combos seen %d/%d · stars %d/%d · special actions %d/9")
             % (min(len(seen), ALBUM_COMBOS), ALBUM_COMBOS, stars, 3 * ALBUM_COMBOS, special),
             T("宝贝 %d 种，共 %d 件 · 还能亲手翻到 %d 次", "Treasures: %d kinds, %d in all · %d find" + ("" if num("chances") == 1 else "s") + " left to dig up by hand")
             % (len(items), sum(v for v in items.values() if type(v) is int), num("chances"))]
    if from_bak:
        lines.append(T("（grow.json 读不了，这是备份 grow.json.bak 里的）", "(grow.json cannot be read: these are from grow.json.bak)"))
    if running:
        lines.append(T("（运行时每分钟存一次，最近一分钟的可能还没算进来）", "(saved once a minute while it runs: the last minute may be missing)"))
    return lines


def cmd_circles():
    """clawd circles: each conversation circle, what it is (Claude desktop / terminal, Codex, ...) and where a click
    on it goes, as the running pets find it now (they write circles.txt on the "circles" event)."""
    import time
    if not is_running():
        print(T("Clawd 未运行。", "Clawd is not running."))
        return 1
    path = os.path.join(HOME, "circles.txt")
    try:
        before = os.path.getmtime(path)
    except OSError:
        before = None
    write_event("circles")
    end = time.time() + 6.0
    while time.time() < end:
        time.sleep(0.2)
        try:
            if os.path.getmtime(path) != before:
                time.sleep(0.1)
                with open(path, encoding="utf-8") as f:
                    sys.stdout.write(f.read())
                return 0
        except OSError:
            pass
    print(T("桌宠没有回应（隐藏着也会回应；可能是旧版本，从菜单重启一下）。",
            "The pets did not answer (they do even when hidden; maybe an older version: restart them from the menu)."))
    return 1


def cmd_status():
    running = is_running()
    if not running:
        print(T("Clawd 未运行。", "Clawd is not running."))
    elif read_state().get("hidden"):
        print(T("Clawd 正在运行（已隐藏，点托盘图标或运行 clawd show 显示）。",
                "Clawd is running (hidden; click the tray icon or run clawd show)."))
    else:
        print(T("Clawd 正在运行。", "Clawd is running."))
    for line in grow_lines(running):
        print(line)
    return 0


def cmd_hide(show, quiet=False):
    if not is_running():
        say(T("Clawd 当前未在运行。", "Clawd isn't running."), quiet)
        return 1
    write_event("show" if show else "hide")
    say(T("好的：显示出来了。", "OK: shown.") if show
        else T("好的：已隐藏，点托盘图标或运行 clawd show 显示。", "OK: hidden. Click the tray icon or run clawd show."), quiet)
    return 0


AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
AUTOSTART_NAME = "Clawd"


def autostart_state():
    """'on', 'off', or 'disabled' (registered, but switched off in Task Manager)."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
    except OSError:
        return "off"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as k:
            v, _ = winreg.QueryValueEx(k, AUTOSTART_NAME)
        if isinstance(v, bytes) and v and v[0] & 1:
            return "disabled"
    except OSError:
        pass
    return "on"


def cmd_autostart(args):
    """开机自启：只写当前用户的启动项（HKCU Run），关掉时连任务管理器的禁用标记一起删。"""
    import winreg
    a = args[0].lower() if args else ""
    if a not in ("on", "off", ""):
        print(T("用法：autostart [on|off]", "Usage: autostart [on|off]"))
        return 2
    if a:
        if a == "on":
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, '"%s" "%s"' % (PYTHONW, PET))
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
    s = autostart_state()
    print({"on": T("开机自启：开。", "Start with Windows: on."),
           "off": T("开机自启：关。", "Start with Windows: off."),
           "disabled": T("开机自启：已登记，但在任务管理器里被禁用了（运行 autostart on 重新打开）。",
                         "Start with Windows: registered, but disabled in Task Manager (run autostart on to turn it on again).")}[s])
    return 0


ACTIVITY_ALIASES = {
    "quiet": "quiet", "calm": "quiet", "安静": "quiet", "少动": "quiet",
    "normal": "normal", "default": "normal", "正常": "normal", "默认": "normal",
    "lively": "lively", "active": "lively", "活泼": "lively", "多动": "lively",
}
ACTIVITY_LABELS = {"quiet": ("安静", "quiet"), "normal": ("正常", "normal"), "lively": ("活泼", "lively")}


def cmd_activity(args, quiet=False):
    """活跃度：它们自己找事做的频率（小动作、散步、自己开始的组合、工作时小的找乐子）。"""
    cur = read_state().get("activity")
    cur = cur if cur in ACTIVITY_LABELS else "normal"
    if not args:
        print(T("当前活跃度：%s。可选 quiet（安静）、normal（正常）、lively（活泼）。",
                "Activity: %s. Choose quiet, normal or lively.") % T(*ACTIVITY_LABELS[cur]))
        return 0
    new = ACTIVITY_ALIASES.get(" ".join(args).strip().strip("\"'").strip().lower())
    if new is None:
        print(T("用法：activity [quiet|normal|lively]（也可写 安静 / 正常 / 活泼）",
                "Usage: activity [quiet|normal|lively]"))
        return 2
    write_event("activity:" + new)
    if not is_running():           # 运行中时播放器自己保存
        d = read_state()
        if new == "normal":
            d.pop("activity", None)
        else:
            d["activity"] = new
        write_state(d)
    say(T("好的：活跃度改为%s。", "OK: activity set to %s.") % T(*ACTIVITY_LABELS[new]), quiet)
    return 0


def cmd_lang(args, quiet=False):
    global _LANG
    if not args:
        print(T("当前语言：中文（zh）。切换：lang en", "Language: English (en). Switch with: lang zh"))
        return 0
    new = LANG_ALIASES.get(" ".join(args).strip().strip("\"'").strip().lower())
    if new is None:
        print(T("用法：lang [zh|en]（也可写 中文 / English）", "Usage: lang [zh|en] (中文 / English also work)"))
        return 2
    write_event("lang:" + new)
    if not is_running():           # 运行中时播放器自己保存，这里写会互相覆盖
        d = read_state()
        d["lang"] = new
        write_state(d)
    _LANG = new
    say(T("好的：界面语言改为中文。", "OK: language set to English."), quiet)
    return 0


# ---------------- hooks ----------------

def exec_hook(word, agent, at=False):
    """Claude Code 的 hook：exec 形式（有 args 就不经过 shell，直接运行 Python）。2026-11-14 真机查到：命令行版在这台电脑上
    找不到 Git Bash（where git 第一个是 ucrt64\\bin\\git.exe，推不出 bash），hook 改由 PowerShell 跑，原来的 bash 一行命令
    一个词都没写进去，只有 Python 的 at 行到了（还要 5.5 秒）。exec 形式不管有没有 Git Bash、路径带不带空格都一样，约 0.1 秒。
    标记放在 args 最后（clawd_hook.py 不理 # 开头的参数）"""
    return {"type": "command", "command": PY_EXEC,
            "args": ["-I", "-S", HERE_FWD + "/clawd_hook.py", word, agent] + (["--at"] if at else []) + [MARK],
            "async": True}


def py_hook(word, agent, at=False, windows=False):
    """clawd_hook.py 写这个词（at=True 时顺带记窗口）。windows=True：给 cmd / PowerShell 用的反斜杠写法，不带标记"""
    args = " %s %s%s" % (word, agent, " --at" if at else "")
    if windows:
        return "%s -I -S %s%s" % (_q(PYTHON), _q(os.path.join(HERE, "clawd_hook.py")), args)
    return "%s -I -S %s%s %s" % (PY_FWD, _q(HERE_FWD + "/clawd_hook.py"), args, MARK)


def hook_entries(agent):
    """-> [(事件, matcher, hook 条目)]：这个 agent 要装的全部 hook"""
    a = AGENTS[agent]
    out = []
    for ev, matcher, tok in a["map"]:
        at = ev in WHERE_EVENTS                # these also say where the conversation is (its "at" line)
        if a.get("exec"):
            h = exec_hook(tok, agent, at)
        else:
            h = {"type": "command", "command": py_hook(tok, agent, at),
                 "commandWindows": py_hook(tok, agent, at, True), "async": True}
            if agent == "codex" and ev == "SessionEnd":
                del h["async"]                 # Codex runs it in the foreground anyway and warns if it says async
                h["timeout"] = 3               # (its most there: 1 s by default)
        out.append((ev, matcher, h))
    return out


def is_ours(h):
    """带标记的：shell 形式标记在命令末尾（bash、PowerShell 里都是注释），exec 形式在 args 最后"""
    if not isinstance(h, dict) or not isinstance(h.get("command"), str):
        return False
    args = h.get("args")
    if isinstance(args, list) and args and args[-1] == MARK:
        return True
    return h["command"].rstrip().endswith(MARK)


def shown(h):
    """一条 hook 写成一行（status 里显示，也用来比较）"""
    args = h.get("args")
    return " ".join([h["command"]] + [str(a) for a in args]) if isinstance(args, list) else h["command"]


def read_settings(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8-sig") as f:
        txt = f.read()
    if not txt.strip():
        return {}
    return json.loads(txt)


def strip_ours(settings):
    """删除所有带标记的 hook；清理因此变空的分组/事件/hooks。返回删除数量。"""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for ev in list(hooks.keys()):
        groups = hooks[ev]
        if not isinstance(groups, list):
            continue
        new_groups = []
        ev_removed = 0
        for g in groups:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                kept = [h for h in g["hooks"] if not is_ours(h)]
                n = len(g["hooks"]) - len(kept)
                ev_removed += n
                if n and not kept:
                    continue  # 整组都是我们的，整组删除
                if n:
                    g = dict(g)
                    g["hooks"] = kept
            new_groups.append(g)
        removed += ev_removed
        if not ev_removed:
            continue          # 未改动的事件（包括用户原有的空列表）原样保留
        if new_groups:
            hooks[ev] = new_groups
        else:
            del hooks[ev]
    if removed and not hooks:
        del settings["hooks"]  # 只有因删除我们的 hook 而变空时才移除
    return removed


def count_ours(settings):
    res = {}
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return res
    for ev, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for g in groups:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                for h in g["hooks"]:
                    if is_ours(h):
                        res.setdefault(ev, []).append(shown(h))
    return res


def ours_shell(settings):
    """还有几条我们的 hook 是 shell 形式（没有 args）：Claude Code 的旧装法"""
    n = 0
    for groups in (settings.get("hooks") or {}).values():
        for g in groups if isinstance(groups, list) else []:
            for h in (g.get("hooks") or []) if isinstance(g, dict) else []:
                if is_ours(h) and not isinstance(h.get("args"), list):
                    n += 1
    return n


BACKUP_SUFFIX = ".clawd-bak"   # 每家的设置文件旁边只有这一个备份：最近一次改动之前的样子（用户 11-16：只留一个）


def back_up(path):
    """改之前复制成 <文件>.clawd-bak（覆盖上一个，所以每家永远只有一个）；以前那种带时间的 <文件>.bak-年月日-时分秒[-n]
    顺手删掉（只删这种名字的，别的文件不碰）"""
    import re
    bak = path + BACKUP_SUFFIX
    shutil.copy2(path, bak)
    print(T("已备份：%s", "Backed up: %s") % bak)
    folder, base = os.path.dirname(path) or ".", os.path.basename(path)
    pat = re.compile(re.escape(base) + r"\.bak-\d{8}-\d{6}(?:-\d+)?$")
    for n in os.listdir(folder):
        if pat.match(n):
            try:
                os.remove(os.path.join(folder, n))
            except OSError:
                pass


def save_settings(path, settings):
    if os.path.exists(path):
        back_up(path)
    else:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".clawd-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def dsh_block():
    """The rows clawd hooks on deepseek adds to DeepSeek Harness's profile patch: our plugin, by its file URL."""
    import pathlib
    url = pathlib.Path(HERE, "clawd_dsh.mjs").resolve().as_uri()
    return "\n".join([DSH_BEGIN, "- insert:", "    - id: clawd-pet", "      name: '%s'" % url.replace("'", "''"), DSH_END])


def dsh_strip(text):
    """-> (text without our block(s), how many there were).  Only lines between our two markers go."""
    out, n, inside = [], 0, False
    for line in text.splitlines(True):
        s = line.strip()
        if not inside and s.startswith(DSH_BEGIN[:16]):
            inside, n = True, n + 1
            if out and not out[-1].strip():
                out.pop()                      # the blank line on goes with it
            continue
        if inside:
            if s == DSH_END:
                inside = False
            continue
        out.append(line)
    return "".join(out), n


def cmd_dsh(sub, path):
    """hooks on|off|status deepseek: our plugin's row in DeepSeek Harness's desktop profile (its cordis.patch.yml).
    The file is DeepSeek's own YAML; we touch only the lines between our markers, and back it up first."""
    who = AGENTS["deepseek"]["name"]
    if not os.path.isfile(path):
        if sub == "on":
            print(T("没找到 %s 的配置：%s\n先打开一次 DeepSeek Harness 桌面版再试。",
                    "No %s profile found at %s\nOpen the DeepSeek Harness desktop app once, then try again.") % (who, path))
            return 1
        print(T("Clawd（%s）：未安装（没找到它的配置）。", "Clawd (%s): not installed (no profile found).") % who)
        return 0
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        print(T("读取配置失败（未做任何修改）：%s", "Could not read the profile (nothing was changed): %s") % e)
        return 1
    rest, n = dsh_strip(text)
    block = dsh_block()
    if sub == "status":
        if not n:
            print(T("Clawd（%s）：未安装。", "Clawd (%s): not installed.") % who)
        else:
            print(T("Clawd（%s）：已安装（插件 %s）%s", "Clawd (%s): installed (plugin %s)%s")
                  % (who, os.path.join(HERE, "clawd_dsh.mjs"), "" if block in text else T("，路径不是这一份，重新 on 一下",
                                                                                    "; not this copy's path: run on again")))
        return 0
    if sub == "off" and not n:
        print(T("没有需要移除的 Clawd 插件。", "No Clawd plugin to remove."))
        return 0
    if sub == "on":
        new = rest.rstrip("\n") + ("\n\n" if rest.strip() else "") + block + "\n"
        if new == text:
            print(T("Clawd 插件已是最新，无需修改。", "The Clawd plugin is already up to date; nothing to change."))
            return 0
    elif sub == "off":
        new = rest.rstrip("\n") + "\n"
    else:
        print(T("用法：hooks on|off|status deepseek", "Usage: hooks on|off|status deepseek"))
        return 2
    back_up(path)
    tmp = path + ".clawd-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    os.replace(tmp, path)
    if sub == "on":
        print(T("已给 %s 装上 Clawd 插件。重启 DeepSeek Harness 后生效（托盘图标右键退出，再打开）。",
                "Installed the Clawd plugin for %s. Restart DeepSeek Harness for it to take effect (quit from its tray icon, open it again).") % who)
    else:
        print(T("已移除 Clawd 插件。重启 DeepSeek Harness 后生效。", "Removed the Clawd plugin. Restart DeepSeek Harness for it to take effect."))
    return 0


def ag_spec():
    """Our entry in Antigravity's hooks.json (no PreToolUse: see AG_EVENTS).  It waits for each hook's JSON answer, so
    should Python or this folder be gone (moved, uninstalled, no hooks off first), cmd answers {} itself: Antigravity
    goes on as if we were not there."""
    spec = {}
    for ev, word in AG_EVENTS:
        h = {"type": "command", "command": py_hook(word, "antigravity", windows=True) + " || echo {}", "timeout": 5}
        spec[ev] = [{"matcher": "*", "hooks": [h]}] if ev in AG_TOOL_EVENTS else [h]
    return spec


def cmd_ag(sub, path, flags):
    """hooks on|off|status antigravity: the "clawd" entry of Antigravity's hooks.json; nothing else in it is touched,
    and it is backed up first."""
    who = AGENTS["antigravity"]["name"]
    try:
        settings = read_settings(path)
    except Exception as e:
        print(T("读取设置失败（未做任何修改）：%s", "Could not read the settings file (nothing was changed): %s") % e)
        return 1
    if not isinstance(settings, dict):
        print(T("设置文件不是 JSON 对象，未做修改。", "The settings file is not a JSON object; nothing was changed."))
        return 1
    ours = settings.get(AG_KEY)
    if sub == "status":
        if not isinstance(ours, dict):
            print(T("Clawd hooks（%s）：未安装。", "Clawd hooks (%s): not installed.") % who)
        else:
            if ours == ag_spec():
                note = ""
            elif "PreToolUse" in ours:
                note = T("，是旧版：挂了 PreToolUse，会拦下 Antigravity 的所有工具，马上重新 on 一下",
                         "; an old one: it hooks PreToolUse, which blocks all of Antigravity's tools. Run on again now")
            else:
                note = T("，是旧版或别的路径，重新 on 一下", "; an old one or another copy's: run on again")
            print(T("Clawd hooks（%s）：已安装（%d 个：%s）%s", "Clawd hooks (%s): installed (%d: %s)%s")
                  % (who, len(ours), ", ".join(ours), note))
        return 0
    if sub == "off":
        if AG_KEY not in settings:
            print(T("没有需要移除的 Clawd hooks。", "No Clawd hooks to remove."))
            return 0
        del settings[AG_KEY]
        save_settings(path, settings)
        print(T("已移除 Antigravity 的 Clawd hooks。", "Removed the Clawd hooks from Antigravity."))
        return 0
    if sub == "on":
        spec = ag_spec()
        if ours == spec:
            print(T("Clawd hooks 已是最新，无需修改。", "Clawd hooks are already up to date; nothing to change."))
            return 0
        settings[AG_KEY] = spec
        save_settings(path, settings)
        print(T("已给 %s 安装 Clawd hooks（%d 个）。新开的对话生效；没反应就重启一下 Antigravity。",
                "Installed Clawd hooks for %s (%d). New conversations pick them up; if nothing happens, restart Antigravity.")
              % (who, len(spec)))
        return 0
    print(T("用法：hooks on|off|status antigravity", "Usage: hooks on|off|status antigravity"))
    return 2


def cmd_hooks(args):
    path = None
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--settings" and i + 1 < len(args):
            path = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    sub = rest[0] if rest else "status"
    flags = rest[1:]
    named = next((f.lower() for f in flags if not f.startswith("--")), None)
    if sub == "status" and named is None and path is None:
        for a in AGENTS:                       # every agent at once: what is wired in where, a line each
            cmd_hooks(["status", a, "--brief"])
        return 0
    agent = named or "claude"
    if agent not in AGENTS:
        print(T("不认识的 agent：%s（可用：%s）", "Unknown agent: %s (known: %s)") % (agent, ", ".join(sorted(AGENTS))))
        return 2
    who = AGENTS[agent]["name"]
    if path is None:
        path = AGENTS[agent]["settings"]
    if AGENTS[agent].get("plugin"):
        return cmd_dsh(sub, path)
    if AGENTS[agent].get("named"):
        return cmd_ag(sub, path, flags)
    try:
        settings = read_settings(path)
    except Exception as e:
        print(T("读取设置失败（未做任何修改）：%s", "Could not read the settings file (nothing was changed): %s") % e)
        return 1
    if not isinstance(settings, dict):
        print(T("设置文件不是 JSON 对象，未做修改。", "The settings file is not a JSON object; nothing was changed."))
        return 1
    if "hooks" in settings and not isinstance(settings["hooks"], dict):
        print(T("设置文件中 hooks 格式异常，未做修改。", "The \"hooks\" entry in the settings file has an unexpected format; nothing was changed."))
        return 1

    if sub == "status":
        ours = count_ours(settings)
        if not ours:
            print(T("Clawd hooks（%s）：未安装。", "Clawd hooks (%s): not installed.") % who)
        else:
            auto = any(c.endswith(" on --quiet " + MARK) for c in ours.get(AUTOSTART_EVENT, []))
            n = sum(len(c) for c in ours.values())
            print(T("Clawd hooks（%s）：已安装（%d 个，%s）", "Clawd hooks (%s): installed (%d, %s)")
                  % (who, n, T("含自动启动", "with autostart") if auto else T("无自动启动", "no autostart")))
            if AGENTS[agent].get("exec") and ours_shell(settings):
                print(T("  旧装法（bash 一行命令）：找不到 Git Bash 时（比如命令行版）一个词也写不进去，运行 hooks on 更新。",
                        "  An old install (bash one-liners): with no Git Bash found (the CLI, for one) they write nothing; run hooks on to update."))
            if "--brief" not in flags:         # every agent at once: one line each
                for ev, cmds in ours.items():
                    for c in cmds:
                        print("  %s -> %s" % (ev, c))
        return 0

    if sub == "off":
        before = json.dumps(settings, sort_keys=True)
        n = strip_ours(settings)
        if n == 0:
            print(T("没有需要移除的 Clawd hooks。", "No Clawd hooks to remove."))
            return 0
        save_settings(path, settings)
        print(T("已移除 %d 个 Clawd hook。", "Removed %d Clawd hook(s).") % n)
        return 0

    if sub == "on":
        autostart = "--autostart" in flags and agent == "claude"
        original = json.dumps(settings, sort_keys=True)
        strip_ours(settings)
        hooks = settings.setdefault("hooks", {})
        entries = hook_entries(agent)
        if autostart:
            entries.append((AUTOSTART_EVENT, None, dict(AUTOSTART_HOOK)))
        for ev, matcher, h in entries:
            lst = hooks.setdefault(ev, [])
            # 省略 matcher 即匹配所有；async 让 hook 不阻塞 agent
            group = {"hooks": [h]}
            if matcher:
                group = {"matcher": matcher, **group}
            lst.append(group)
        if json.dumps(settings, sort_keys=True) == original:
            print(T("Clawd hooks 已是最新，无需修改。", "Clawd hooks are already up to date; nothing to change."))
            return 0
        save_settings(path, settings)
        print(T("已给 %s 安装 Clawd hooks（%d 个%s）。", "Installed Clawd hooks for %s (%d%s).") % (who, len(entries), T("，含自动启动", ", with autostart") if autostart else ""))
        if agent == "codex":
            print(T("Codex 要你先看过并信任这些 hook 才会运行：命令行里输入 /hooks，桌面版在 设置 > Hooks。",
                    "Codex runs them only once you have reviewed and trusted them: /hooks in the CLI, Settings > Hooks in the desktop app."))
        return 0

    names = "|".join(AGENTS)
    print(T("用法：hooks on [%s] [--autostart] | hooks off [agent] | hooks status [agent] [--settings PATH]（不写 agent：on/off 是 Claude Code，status 是全部）" % names,
            "Usage: hooks on [%s] [--autostart] | hooks off [agent] | hooks status [agent] [--settings PATH] (no agent: Claude Code for on/off, all of them for status)" % names))
    return 2


# ------------------------------------------------- connecting the agents: the connect window (clawd_connect.pyw),
# clawd connect / uninstall / hooks refresh.  Each change goes through cmd_hooks: only our own entries, backed up first.
AGENT_ORDER = ("claude", "codex", "deepseek", "antigravity")
NEXT_STEP = {      # what is left to do after connecting (the connect window shows it at once)
    "claude": ("新开的对话就会跟着动。", "New conversations make them move."),
    "codex": ("还差一步：在 Codex 里信任这些 hook（命令行输入 /hooks，桌面版在 设置 > Hooks）。",
              "One more step: trust these hooks in Codex (/hooks in the CLI, Settings > Hooks in the desktop app)."),
    "deepseek": ("还差一步：重启 DeepSeek（托盘图标右键退出，再打开）。",
                 "One more step: restart DeepSeek Harness (quit from its tray icon, open it again)."),
    "antigravity": ("新开的对话就会跟着动；没反应就重启 Antigravity。",
                    "New conversations make them move; if nothing happens, restart Antigravity."),
}


def agent_found(agent):
    """Has this agent run on this computer (the folder it makes the first time)?  Nothing to connect if not."""
    home = os.path.expanduser("~")
    return os.path.isdir({"claude": CLAUDE_DIR, "codex": CODEX_DIR, "deepseek": DSH_DIR,
                          "antigravity": os.path.join(home, ".gemini", "antigravity")}[agent])


def _with_autostart(settings):
    """Claude Code's settings hold our autostart hook (clawd hooks on --autostart): connecting again keeps it."""
    for g in ((settings.get("hooks") or {}).get(AUTOSTART_EVENT) or []):
        for h in (g.get("hooks") or []) if isinstance(g, dict) else []:
            if is_ours(h) and isinstance(h.get("args"), list) and h["args"][-3:-1] == ["on", "--quiet"]:
                return True
    return False


def hook_state(agent):
    """-> "on" (ours, as this copy writes them), "old" (ours, but another copy's paths or an older kind: connect
    again), "off" (none of ours), "bad" (its settings cannot be read: left alone)."""
    a, path = AGENTS[agent], AGENTS[agent]["settings"]
    try:
        if a.get("plugin"):
            if not os.path.isfile(path):
                return "off"
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
            if not dsh_strip(text)[1]:
                return "off"
            return "on" if dsh_block() in text else "old"
        settings = read_settings(path)
        if not isinstance(settings, dict):
            return "bad"
        if a.get("named"):
            ours = settings.get(AG_KEY)
            return "off" if not isinstance(ours, dict) else ("on" if ours == ag_spec() else "old")
        have = []
        for ev, groups in (settings.get("hooks") or {}).items():
            for g in groups if isinstance(groups, list) else []:
                for h in (g.get("hooks") or []) if isinstance(g, dict) else []:
                    if is_ours(h):
                        have.append(json.dumps([ev, g.get("matcher") or None, h], sort_keys=True))
        if not have:
            return "off"
        entries = hook_entries(agent)
        if agent == "claude" and _with_autostart(settings):
            entries.append((AUTOSTART_EVENT, None, dict(AUTOSTART_HOOK)))
        want = [json.dumps([ev, m or None, h], sort_keys=True) for ev, m, h in entries]
        return "on" if sorted(have) == sorted(want) else "old"
    except Exception:
        return "bad"


def set_hooks(agent, on):
    """Connect (on) or disconnect an agent, as clawd hooks on|off <agent> does.  -> (ok, what it printed)."""
    import contextlib
    import io
    args = ["on" if on else "off", agent]
    if on and agent == "claude":
        try:
            if _with_autostart(read_settings(AGENTS["claude"]["settings"])):
                args.append("--autostart")
        except Exception:
            pass
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = cmd_hooks(args)
    except Exception as e:
        return False, "%s%s" % (out.getvalue(), e)
    return rc == 0, out.getvalue().strip()


def cmd_refresh(quiet=False):
    """hooks refresh: ours that are another copy's (the program moved, an older kind) are written again for this
    copy; the others are left as they are.  The pets run it at each start."""
    n = 0
    for agent in AGENT_ORDER:
        if hook_state(agent) == "old":
            ok, text = set_hooks(agent, True)
            n += 1
            say(T("%s：%s", "%s: %s") % (AGENTS[agent]["name"], text.splitlines()[-1] if text else ("ok" if ok else "?")), quiet)
    if not n:
        say(T("各家的 Clawd hooks 都是这一份的，不用改。", "Every agent's Clawd hooks are this copy's; nothing to change."), quiet)
    return 0


def close_windows(wait=10.0):
    """An install (its own Python in python\\ beside the program): once the pets have quit (they save first), what
    else runs with that Python is closed: the album and the Connect AI window (they hold its files, so an update or
    an uninstall could not replace or remove them; 2026-11-16), a re-render.  Never for a copy run with a Python
    that is not its own (C:\\Python312: other programs may run with it).  -> how many were closed."""
    if os.name != "nt":
        return 0
    pydir = os.path.normcase(os.path.dirname(os.path.abspath(PYTHON)))
    if os.path.normcase(os.path.join(HERE, "python")) != pydir:
        return 0
    t0 = time.time()
    while is_running() and time.time() - t0 < wait:
        time.sleep(0.2)
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.TerminateProcess.argtypes = [wintypes.HANDLE, ctypes.c_uint]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.K32EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    pids = (wintypes.DWORD * 4096)()
    got = wintypes.DWORD()
    if not k.K32EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got)):
        return 0
    n = 0
    for pid in pids[:got.value // ctypes.sizeof(wintypes.DWORD)]:
        if not pid or pid == os.getpid():
            continue
        h = k.OpenProcess(0x1000 | 0x0001, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE
        if not h:
            continue
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if (k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                    and os.path.normcase(os.path.dirname(buf.value)) == pydir and k.TerminateProcess(h, 0)):
                n += 1
        finally:
            k.CloseHandle(h)
    return n


def cmd_uninstall(quiet=False):
    """clawd uninstall (the uninstaller runs it): the pets quit, an install's windows close, every agent's hooks out
    and the one backup we kept beside each agent's settings removed, not started with Windows.  The save stays
    (where it is is printed)."""
    cmd_off(True)
    close_windows()
    for agent in AGENT_ORDER:
        if hook_state(agent) in ("on", "old"):
            ok, text = set_hooks(agent, False)
            say("%s: %s" % (AGENTS[agent]["name"], text.splitlines()[-1] if text else ""), quiet)
        bak = AGENTS[agent]["settings"] + BACKUP_SUFFIX
        if os.path.isfile(bak):
            try:
                os.remove(bak)
                say(T("已删除备份：%s", "Backup removed: %s") % bak, quiet)
            except OSError:
                pass
    if PET.lower() in autostart_command().lower():     # only this copy's: another copy's start stays
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_autostart(["off"])
    say(T("已退出，四家的 hook 和开机自启都去掉了。存档还在：%s", "Quit; the hooks of every agent and starting with "
          "Windows are gone. The save is still in %s") % HOME, quiet)
    return 0


def autostart_command():
    """-> the command registered to start with Windows, or ""."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
            return str(winreg.QueryValueEx(k, AUTOSTART_NAME)[0])
    except OSError:
        return ""


def open_connect(quiet=False):
    import subprocess
    subprocess.Popen([PYTHONW, os.path.join(HERE, "clawd_connect.pyw")],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    say(T("连接 AI 的窗口打开了。", "The Connect AI window is open."), quiet)
    return 0


def main(argv):
    quiet = "--quiet" in argv
    args = [a for a in argv if a != "--quiet" and not a.startswith("#")]   # the hooks' marker (exec form passes it)
    if not args or args[0] == "on":
        return cmd_on(quiet)
    c = args[0]
    if c in ("1", "2", "3") and len(args) == 1:
        return cmd_family(int(c), quiet)
    if c == "off":
        rc = cmd_off(quiet)
        if "--all" in args:                # the installer, before an update: an install's windows too
            close_windows()
        return rc
    if c in ("hide", "show"):
        return cmd_hide(c == "show", quiet)
    if c == "do":
        return cmd_do(args[1:], quiet)
    if c == "size":
        return cmd_size(args[1:], quiet)
    if c == "list":
        return cmd_list()
    if c == "status":
        return cmd_status()
    if c in ("circles", "圆圈"):
        return cmd_circles()
    if c in ("album", "图鉴"):
        import subprocess
        subprocess.Popen([PYTHONW, os.path.join(os.path.dirname(os.path.abspath(PET)), "clawd_album.pyw"), "--home", HOME],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        say(T("图鉴打开了。", "The album is open."), quiet)
        return 0
    if c == "lang":
        return cmd_lang(args[1:], quiet)
    if c == "activity":
        return cmd_activity(args[1:], quiet)
    if c == "autostart":
        return cmd_autostart(args[1:])
    if c == "hooks" and args[1:2] == ["refresh"]:
        return cmd_refresh(quiet)
    if c == "hooks":
        return cmd_hooks(args[1:])
    if c in ("connect", "连接"):
        return open_connect(quiet)
    if c == "uninstall":
        return cmd_uninstall(quiet)
    if resolve_action(" ".join(args)) or resolve_combo(" ".join(args)):
        return cmd_do(args, quiet)
    print(T("未知命令：%s", "Unknown command: %s") % c)
    print(T("可用：1 2 3 on off hide show do size list status circles lang activity autostart hooks connect uninstall",
            "Available: 1 2 3 on off hide show do size list status circles lang activity autostart hooks connect uninstall"))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
