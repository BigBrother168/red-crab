"""图鉴 checks: the album opens on a made-up family (its own home, nothing of the real one), every page and every
cell is clicked, a find you have not looked at yet is sealed and opens on a click (album.json), the picked action
plays, "play it" writes its word, the window is made bigger and smaller.  The album does it itself (--selftest)
and writes what it saw; this script checks that.  Also: Chinese and English hints for every cell, and the
English page.  A window shows for a few seconds each run."""
import json, os, subprocess, sys, time
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the album's folder
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 't')
ALBUM = os.path.join(T, 'clawd_album.pyw')
FRAMES = os.path.join(T, 'frames')
HI = os.path.join(T, 'frames_hi')
HOME = S + "/albumhome"
os.makedirs(HOME, exist_ok=True)
res = []


def check(name, ok, info=""):
    res.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(info)[:600]))


GROW = {"v": 1, "xp": 2557, "level_shown": 8, "since": "2026-11-10", "days": 3, "turns": 161, "work_secs": 14793.4, "agents": 28,
        "fixes": 15, "plays": 224, "chances": 2,
        "items": {"semicolon": 2, "paperclip": 1, "braces": 1, "rubber_duck": 1, "bug": 1},
        "seen": {"high_five": "2026-11-10", "leapfrog": "2026-11-12", "stack": "2026-11-10", "console": "2026-11-10"},
        "combos": {"high_five": 44, "leapfrog": 3, "stack": 11, "console": 8},
        "acts": {"idle": "2026-11-10", "wave": "2026-11-10", "shy": "2026-11-10", "work_run": "2026-11-11", "rummage": "2026-11-11"},
        "daily": {time.strftime("%Y-%m-%d"): [5, 1800.0, 2, 40]}}
# looked at before: all of them but the paperclip, leapfrog and the wave (those three are new)
SEEN = ["item:semicolon", "item:braces", "item:rubber_duck", "item:bug", "combo:high_five", "combo:stack", "combo:console",
        "act:idle", "act:shy", "act:work_run", "act:rummage"]


def run(lang="zh", seen=True, grow=None, album=None):
    for f in ("event", "album.json", "album.log", "out.json"):
        try:
            os.remove(os.path.join(HOME, f))
        except OSError:
            pass
    json.dump(grow or GROW, open(HOME + "/grow.json", "w", encoding="utf-8"))
    json.dump({"lang": lang}, open(HOME + "/state.json", "w"))
    if album is not None:
        json.dump(album, open(HOME + "/album.json", "w"))
    elif seen:
        json.dump({"v": 1, "seen": dict((k, "2026-11-11") for k in SEEN)}, open(HOME + "/album.json", "w"))
    t0 = time.time()
    p = subprocess.run(["C:/Python312/python.exe", ALBUM, "--home", HOME, "--frames-dir", FRAMES, "--hi-dir", HI,
                        "--selftest", HOME + "/out.json"], capture_output=True, text=True, timeout=180)
    out = json.load(open(HOME + "/out.json", encoding="utf-8")) if os.path.exists(HOME + "/out.json") else {}
    out["wall_s"] = round(time.time() - t0, 1)
    out["stderr"] = p.stderr[-800:]
    return out


# ---- the hints: every cell has its words in both languages
sys.path.insert(0, T)
import clawd_album_hints as H
check("hints: the same cells in Chinese and English", set(H.HINTS) == set(H.HINTS_EN), set(H.HINTS) ^ set(H.HINTS_EN))
check("hints: each is (riddle, nudge, plain)", all(len(v) == 3 and v[0] and v[2] for d in (H.HINTS, H.HINTS_EN) for v in d.values()))

import importlib.machinery, importlib.util
_l = importlib.machinery.SourceFileLoader("album", ALBUM)
A = importlib.util.module_from_spec(importlib.util.spec_from_loader("album", _l))
_l.exec_module(A)
cells = list(A.COMBO_ORDER)
check("the album's combo cells are the player's (ALBUM_COMBOS), each with a group photo",
      sorted(cells) == sorted(A.P.ALBUM_COMBOS) and all(k in A.COMBO_PHOTO for k in cells), (sorted(cells), sorted(A.P.ALBUM_COMBOS)))

looks = [(kind, row[0], row[1]) for kind, rows in A.P.SIGN_LOOKS.items() for row in rows if row[1] > 1]
gifts = dict((g[1], g[0]) for g in A.P.LEVEL_GIFTS)
check("each look of the signs comes with a gift of its level", all(gifts.get("%s_%s" % (k, n)) == lv for k, n, lv in looks), looks)
check("each gift has its words in both languages", all(len(g[2]) == 2 and len(g[3]) == 2 and all(g[2]) and all(g[3]) for g in A.P.LEVEL_GIFTS))

o = run()
print(json.dumps({k: v for k, v in o.items() if k not in ("seen_file",)}, ensure_ascii=False)[:1500])
check("1 no errors", not o.get("errors") and not o.get("stderr"), (o.get("errors"), o.get("stderr")))
check("1 all five pages", o.get("steps") == ["page items", "page combos", "page acts", "page family", "page gifts"], o.get("steps"))
gf = o.get("gifts") or {}
check("1 gifts: a badge for each level with a gift, you on the road", gf.get("badges") == len(set(g[0] for g in A.P.LEVEL_GIFTS)) and gf.get("marker"), gf)
check("1 gifts: at Lv.8 the pink chalk and the dotted frame can be picked; picking one writes its word",
      gf.get("looks_open") == 2 and gf.get("look_token") == ["sign:chalk=pink"], gf)
mp = o.get("missing_pictures", {})
check("1 every cell has its picture", all(mp.get(k) == [] for k in ("items", "combos", "acts")), mp)
check("1 the family picture", mp.get("family", 0) >= 1, mp)
check("1 the title bar in leather, Clawd as the icon", o.get("dressed") and o.get("icon"), (o.get("dressed"), o.get("icon")))
check("2 the new ones opened on a click: none left", o.get("news_after") == {"items": 0, "combos": 0, "acts": 0}, o.get("news_after"))
sf = o.get("seen_file", {})
check("2 album.json: the three opened now are written down", all(k in sf for k in ("item:paperclip", "combo:leapfrog", "act:wave")),
      sorted(sf))
check("2 album.json: nothing not found is in it", "item:gear" not in sf and "combo:note" not in sf, sorted(sf))
check("3 the picked action plays", o.get("anim_frames", 0) >= 8, o.get("anim_frames"))
check("3 play it: its word in the event file", o.get("event_tail") == ["shy"], o.get("event_tail"))
sz = o.get("sizes") or []
check("4 bigger and smaller: it follows the window", len(sz) == 2 and sz[0][2] > sz[1][2] and all(s[3] > 10 for s in sz), sz)
check("5 quick: the first page, all pages", o.get("first_page_s", 99) < 4 and o.get("all_pages_s", 99) < 25, (o.get("first_page_s"), o.get("all_pages_s")))
check("5 memory: working set under 60 MB", 0 < o.get("work_set_mb", 999) < 60, (o.get("work_set_mb"), o.get("private_mb")))

o = run(seen=False)
sf = o.get("seen_file", {})
check("6 the first time (no album.json): what is found counts as looked at, nothing sealed",
      not o.get("errors") and "item:paperclip" in sf and "act:wave" in sf and "item:gear" not in sf, (o.get("errors"), sorted(sf)))

o = run("en")
check("7 English: no errors, every picture", not o.get("errors") and all((o.get("missing_pictures") or {}).get(k) == [] for k in ("items", "combos", "acts")),
      (o.get("errors"), o.get("missing_pictures")))

# ---- 8, 9: the gifts are looked at too (album.json v 2).  An album.json of before (run 1, Lv.8): the three gifts
# you have were not news.  Of v 2 without the Lv.7 gift: its card shows first (the pets' menu counts it till then).
check("8 gift_news: what the level has brought, not what is looked at",
      A.P.gift_news({"gift:chalk_pink": "x"}, 8) == ["dig_4", "frame_dots"] and A.P.gift_news({}, 1) == [])
o = run()
sf = o.get("seen_file", {})
check("8 an album.json of before: the gifts you have count as looked at", o.get("gift_news_first") == []
      and all("gift:" + g in sf for g in ("chalk_pink", "dig_4", "frame_dots")) and "gift:items_2" not in sf and not o.get("errors"),
      (o.get("gift_news_first"), sorted(k for k in sf if k.startswith("gift:")), o.get("errors")))
o = run(album={"v": 2, "seen": dict([(k, "2026-11-11") for k in SEEN] + [("gift:chalk_pink", "x"), ("gift:dig_4", "x")])})
gf = o.get("gifts") or {}
check("9 a gift not looked at: news as it opens, its card shows first, then none is left", o.get("gift_news_first") == ["frame_dots"]
      and gf.get("first_pick") == "frame_dots" and gf.get("news_left") == 0 and "gift:frame_dots" in o.get("seen_file", {}),
      (o.get("gift_news_first"), gf))

# ---- 10: a family at a few levels (the first batch all found before Lv.10; the top): no errors, every badge
xp_at = lambda lv: sum(A.P.grow_need(i) for i in range(1, lv))
names = A.P.ITEMS_2
first = [k for k in json.load(open(os.path.join(FRAMES, "manifest.json"), encoding="utf-8"))["items"]["names"] if k not in names]
for lv, lang in ((1, "zh"), (9, "zh"), (16, "zh"), (20, "zh"), (20, "en")):
    items = dict((k, 1) for k in (first if lv >= 9 else [])) if lv < 20 else dict((k, 2) for k in first + list(names))
    g = dict(GROW, xp=xp_at(lv) + 5, level_shown=lv, items=items, gifts=[x[1] for x in A.P.LEVEL_GIFTS if x[0] <= lv])
    if lv == 20:
        g["monument"] = {"since": "2026-11-10", "day": "2026-11-24", "days": 15, "turns": 1234, "work_secs": 3600.0, "things": 56, "kinds": 28, "played": 300}
    o = run(lang, grow=g)
    gf = o.get("gifts") or {}
    check("10 Lv.%d %s: no errors, every badge clicked%s" % (lv, lang, ", the monument's card first" if lv == 20 else ""),
          not o.get("errors") and gf.get("all_picked") == gf.get("badges") == len(set(x[0] for x in A.P.LEVEL_GIFTS))
          and (lv < 20 or gf.get("first_pick") == "monument"), (o.get("errors"), gf))

print("%d/%d passed" % (sum(1 for _, ok in res if ok), len(res)))
sys.exit(0 if all(ok for _, ok in res) else 1)
