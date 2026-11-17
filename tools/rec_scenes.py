"""rec_scenes.py NAME [LANG]: play one scene on a test family and record it (tools/t/rec/NAME_LANG).
Then rec_gif.py cuts the picture out of it (the marks tell where)."""
import ctypes, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))    # window places in real pixels
import rec_scene as S

T = S.T
DEV = os.path.join(T, "grow.json")        # a family that has everything: no gifts or first finds at the start
S1, S2, S3 = "a1b2c3d4", "e5f6a7b8", "c9d0e1f2"


def save(**over):
    g = json.load(open(DEV, encoding="utf-8"))
    g.update(over)
    return g


def hero(out, lang):
    """A turn of work and its end: listen, read, edit, run ... (2 minutes) ... done, the family celebrates."""
    S.start(out, lang, grow=save(), scale=1.5, pos={0: 1000, 1: 780, 2: 590},
            extra=["--dig-every", "9999", "--peek-after", "9999", "--mimic-interval", "9999-9999", "--debug"])
    time.sleep(2.0)
    S.mark("listen"); S.event("listen " + S1); time.sleep(2.8)
    S.mark("read"); S.event("read " + S1); time.sleep(3.0); S.event("think " + S1); time.sleep(0.6)
    S.mark("edit"); S.event("edit " + S1); time.sleep(3.0); S.event("think " + S1); time.sleep(0.6)
    S.mark("run"); S.event("run " + S1)
    end = time.time() + 122
    while time.time() < end:
        time.sleep(4)
        S.event("think " + S1)
        time.sleep(0.3)
        S.event("run " + S1)
    S.mark("stop"); S.event("stop " + S1); time.sleep(14)
    S.stop()


TITLES = {"zh": ("整理 README 动图", "修复登录页的 bug", "给接口写单元测试"),
          "en": ("README pictures", "Fix the login bug", "Unit tests for the API")}


def fake_titles(lang):
    """Conversation names for the circles: a Claude Code config folder of our own (CLAUDE_CONFIG_DIR) with three
    transcripts that hold only a title line."""
    d = os.path.join(S.HOME, "claude_cfg")
    p = os.path.join(d, "projects", "demo")
    os.makedirs(p, exist_ok=True)
    for s, t in zip((S1, S2, S3), TITLES[lang]):
        with open(os.path.join(p, s + "-0000-4000-8000-000000000000.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "ai-title", "aiTitle": t, "sessionId": s}, ensure_ascii=False) + "\n")
    return d


def hover(k, of):
    """The cursor (the file the pet reads) over circle k (0 = left) of the row of 'of' circles."""
    import ctypes, ctypes.wintypes as w
    u = ctypes.windll.user32
    found = []

    def f(h, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(32)
        u.GetWindowTextW(h, buf, 32)
        if pid.value == S.proc.pid and u.IsWindowVisible(h) and buf.value == "ClawdTalks":
            found.append(h)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)(f), 0)
    if not found:
        print("no circles to hover")
        return
    r = w.RECT()
    u.GetWindowRect(found[0], ctypes.byref(r))
    x, y = int(r.left + (k + 0.5) * (r.right - r.left) / of), (r.top + r.bottom) // 2
    S.cursor(x, y)                             # where the pet looks (its cursor file) ...
    time.sleep(0.1)
    u.PostMessageW(found[0], 0x0200, 0, ((y - r.top) << 16) | (x - r.left))    # ... once the row has the mouse


def circles(out, lang):
    """Three conversations at once: busy (blue), waiting for you (orange), done (green); the names on hover."""
    os.environ["CLAUDE_CONFIG_DIR"] = fake_titles(lang)
    S.start(out, lang, grow=save(), scale=1.5, pos={0: 1000, 1: 780, 2: 590},
            extra=["--dig-every", "9999", "--peek-after", "9999", "--mimic-interval", "9999-9999"])
    time.sleep(1.5)
    S.mark("one"); S.evs("listen " + S1, "read " + S1); time.sleep(2.5)
    S.mark("two"); S.evs("listen " + S2, "edit " + S2); time.sleep(3.2)
    S.mark("three"); S.evs("listen " + S3, "run " + S3); time.sleep(3.2)
    S.mark("done"); S.evs("think " + S1, "stop " + S1); time.sleep(4.8)
    S.mark("ask"); S.event("attention " + S3); time.sleep(3.0)
    S.mark("hover"); hover(2, 3); time.sleep(3.5)
    S.cursor(50, 50); time.sleep(0.6)
    S.mark("reply"); S.evs("listen " + S3, "run " + S3); time.sleep(3.5)
    S.mark("end")
    S.stop()


def dig(out, lang):
    """A small one digs while they work, finds a rubber duck; at the turn's end it walks over and hands it over."""
    S.start(out, lang, grow=save(), scale=1.5, pos={0: 1000, 1: 780, 2: 590},
            extra=["--dig-every", "4", "--dig-most", "1", "--dig-find", "rubber_duck",
                   "--peek-after", "9999", "--mimic-interval", "9999-9999"])
    time.sleep(1.5)
    S.mark("listen"); S.evs("listen " + S1, "run " + S1)
    for _ in range(4):
        time.sleep(3.7)
        S.evs("think " + S1, "run " + S1, gap=0.3)
    S.mark("stop"); S.event("stop " + S1); time.sleep(16.0)
    S.mark("end")
    S.stop()


def combos(out, lang):
    """The combos you can start from the menu, one after another (the same in both languages: no words)."""
    S.start(out, lang, grow=save(), extra=["--slip", "no", "--return-after", "1-2"], scale=1.5,
            pos={0: 1000, 1: 800, 2: 630})
    time.sleep(1.5)
    for c in ("high_five", "stack", "leapfrog", "parade", "note"):
        S.mark(c); S.event("combo:" + c); time.sleep(17.0)
    S.mark("end")
    S.stop()


def levelup(out, lang):
    """A short turn ends just before Lv.10: the family cheers, the gold sign, then the gift (the second batch)."""
    g = save()
    second = ("coffee", "usb", "headphones", "balloon", "robot", "cube", "spin_top", "moon_lamp")
    g.update({"xp": 4440, "level_shown": 9, "gifts": ["chalk_pink", "dig_4", "frame_dots"],
              "items": dict((k, v) for k, v in g["items"].items() if k not in second)})
    for k in ("monument", "slips"):
        g.pop(k, None)
    S.start(out, lang, grow=g, scale=1.5, pos={0: 1000, 1: 780, 2: 590},
            extra=["--dig-every", "9999", "--peek-after", "9999", "--mimic-interval", "9999-9999", "--debug"])
    time.sleep(1.5)
    S.mark("listen"); S.evs("listen " + S1, "edit " + S1); time.sleep(5.0)
    S.evs("think " + S1, "run " + S1); time.sleep(5.0)
    S.mark("stop"); S.evs("think " + S1, "stop " + S1, gap=0.3); time.sleep(22.0)
    S.mark("end")
    S.stop()


def menu(out, lang):
    """The right-click menu beside the family: the menu's own picture (PrintWindow) and where it was (menu.json),
    and the family recorded as always (rec_gif.py --at puts them together)."""
    import ctypes, ctypes.wintypes as w
    from PIL import Image
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    S.start(out, lang, grow=save(), extra=["--dig-every", "9999", "--tray"], scale=1.5, pos={0: 1000, 1: 780, 2: 590})
    time.sleep(1.5)

    def mine(cls):
        found = []

        def f(h, _):
            pid = w.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            buf = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(h, buf, 64)
            if pid.value == S.proc.pid and u.IsWindowVisible(h) and (cls is None or buf.value == cls):
                r = w.RECT()
                u.GetWindowRect(h, ctypes.byref(r))
                found.append((h, buf.value, (r.left, r.top, r.right, r.bottom)))
            return True
        u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)(f), 0)
        return found
    wins = mine(None)
    print("windows", [(x[1], x[2]) for x in wins])
    big = max((x for x in wins if x[1] != "#32768"), key=lambda x: (x[2][2] - x[2][0]) * (x[2][3] - x[2][1]))
    l, t, r, b = big[2]
    S.cursor(r - 40, t + 70)
    time.sleep(0.6)
    S.mark("menu")
    u.PostMessageW(big[0], 0x0205, 0, ((t + 70 - t) << 16) | (r - 40 - l))
    last, still, menus = None, 0, []
    for _ in range(40):                        # until the menu has stopped growing (it slides open)
        time.sleep(0.1)
        menus = mine("#32768")
        rect = menus[0][2] if menus else None
        still = still + 1 if rect is not None and rect == last else 0
        last = rect
        if still >= 6:
            break
    time.sleep(0.3)
    print("menu rect", last, "stable", still)
    if menus:
        h, _, (ml, mt, mr, mb) = menus[0]
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(ml, mt, mr, mb), all_screens=True).save(os.path.join(out, "menu_screen.png"))
        W, H = mr - ml, mb - mt
        hdc = u.GetWindowDC(h)
        mdc = g.CreateCompatibleDC(hdc)
        bmp = g.CreateCompatibleBitmap(hdc, W, H)
        g.SelectObject(mdc, bmp)
        u.PrintWindow(h, mdc, 2)
        buf = ctypes.create_string_buffer(W * H * 4)
        bi = (ctypes.c_uint32 * 10)(40, W, (-H) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
        g.GetDIBits(mdc, bmp, 0, H, buf, bi, 0)
        Image.frombuffer("RGBA", (W, H), buf.raw, "raw", "BGRA", 0, 1).convert("RGB").save(os.path.join(out, "menu.png"))
        json.dump({"rect": [ml, mt, mr, mb]}, open(os.path.join(out, "menu.json"), "w"))
        u.PostMessageW(h, 0x0100, 0x1B, 0)      # Esc
        time.sleep(0.3)
        u.PostMessageW(h, 0x0101, 0x1B, 0)
        print("menu", (ml, mt, mr, mb))
    else:
        print("no menu")
    time.sleep(1.0)
    S.stop()


if __name__ == "__main__":
    name = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else "zh"
    out = os.path.join(T, "tools", "t", "rec", "%s_%s" % (name, lang))
    globals()[name](out, lang)
