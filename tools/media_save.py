"""media_save.py OUT_DIR LANG: a family part way along, for the README's album pictures (the user, 11-16: keep a mystery).
Lv.11 (the second batch is open), four gifts, 18 of the 28 treasures: of the rare and special only the four the README's
play picture shows (readme_media.py: the duck, the cube, the moon lamp, the bottle), and every common and uncommon one it
shows; 6 of the 10 combos (the README's four among them); no monument.
Then: python tools/shot.py OUT.png 4 --size 900x718 -- C:/Python312/python.exe clawd_album.pyw --home OUT_DIR --page N"""
import json, os, sys

out, lang = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
D = ["2026-11-%02d" % d for d in range(8, 17)]          # nine days together; the album's chart shows the last seven
items = {"semicolon": 14, "paperclip": 17, "screw": 19, "sticky_note": 11, "pencil": 9, "paper_ball": 15, "leaf": 12,
         "braces": 6, "gear": 7, "keycap": 4, "floppy": 5, "coffee": 2, "headphones": 1,
         "rubber_duck": 3, "cube": 1, "bottle": 2, "moon_lamp": 1}
combos = {"high_five": 23, "stack": 12, "leapfrog": 9, "parade": 5, "note": 44, "celebrate_all": 14}
acts = ["aha", "celebrate", "confused", "dangle", "dizzy", "doze", "doze_startle", "doze_up", "head_tilt", "hop", "idle",
        "land", "listen", "look_at_viewer", "nod", "proud", "rummage", "shake_head", "shrug_sweat", "shy", "sleep",
        "surprised", "think", "thumbs_up", "tiptoe_peek", "tumble", "wake_up", "walk", "wave", "wink", "work_edit",
        "work_read", "work_run", "work_web", "work_agent", "present", "pull_out",
        "play_toss", "play_look", "play_listen", "play_show"] + ["play_" + k for k in items]
need = [min(round(40 * lv ** 1.5), 1080) for lv in range(1, 11)]    # grow_need of Lv.1-10
mins = [190, 215, 240, 205, 260, 230, 150]                          # the last seven days, minutes at work
g = {"v": 1, "xp": sum(need) + 380, "level_shown": 11, "since": D[0], "days": len(D), "last_day": D[-1],
     "turns": 342, "empty_turns": 77, "work_secs": 118200.0, "agents": 121, "fixes": 27, "plays": 233,
     "items": items, "combos": combos, "seen": dict((k, D[1]) for k in combos),
     "acts": dict((k, D[0]) for k in acts), "gifts": ["chalk_pink", "dig_4", "frame_dots", "items_2"],
     "chances": 2, "chance_secs": 240, "dry_hand": 0, "dry_uncommon": 3, "dry_rare": 7, "dry_special": 18,
     "album_marks": [10, 25, 50], "loot": [],
     "daily": dict((d, [38 + 3 * i, m * 60.0, 30 + 2 * i, 500 + 20 * i]) for i, (d, m) in enumerate(zip(D[-7:], mins)))}
json.dump(g, open(os.path.join(out, "grow.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"lang": lang, "slots": [1, 2]}, open(os.path.join(out, "state.json"), "w", encoding="utf-8"))
seen = dict(("item:" + k, D[1]) for k in items)                     # opened already: no red dots in the picture
seen.update(("combo:" + k, D[1]) for k in combos)
seen.update(("act:" + k, D[1]) for k in acts)
seen.update(("gift:" + k, D[1]) for k in g["gifts"])
json.dump({"v": 2, "seen": seen}, open(os.path.join(out, "album.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("level xp", g["xp"], "->", out)
