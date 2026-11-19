# -*- coding: utf-8 -*-
"""Prerender Clawd desktop-pet frames (manifest v2).

Run with the venv that has numpy + PIL:
    .venv\\Scripts\\python.exe prerender.py [--body-px 100] [--out DIR]

--out DIR is the frames directory itself (default frames\\ next to this script). Output is written to DIR.tmp and
renamed into place (per-file with the manifest last if the directory is held open); the player tolerates both.

After a fresh clone (the frames are not in git): create .venv next to this script from requirements.txt, then
    .venv\\Scripts\\python.exe prerender.py --out frames
    .venv\\Scripts\\python.exe prerender.py --body-px 300 --out frames_hi
Contents: manifest.json (version 2), <action>.frames, preview.png (unless --no-preview).
Record format of *.frames: uint32 LE length L, then zlib.compress(raw) (L bytes);
raw = W*H*4 bytes, BGRA, premultiplied alpha, rows top-down.

Parallel, two passes over a process pool (--workers, default min(8, cores), below-normal priority):
  1. render chunks of frames, each worker spilling level-1 compressed bbox crops to DIR.tmp\\crops
     (raw frames are never collected in RAM: at body 300 px they would be ~700 MB);
  2. with the union bbox known, encode the chunks into the final records, joined per action.
The output does not depend on --workers.  The workers live in a Job Object owned by the main process, so
they die with it however it ends; the venv launcher alone does not guarantee that, because its job lets
grandchildren break away silently.
"""
import bisect, sys, os, json, math, time, struct, zlib, argparse, shutil, ctypes
from concurrent.futures import ProcessPoolExecutor

for _v in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):      # before numpy: no per-core pools
    os.environ.setdefault(_v, '1')

THIS_SCRIPT = os.path.abspath(__file__)
HERE = os.path.dirname(THIS_SCRIPT)
VW = os.path.join(HERE, 'renderer')          # the character code: clawd.py + common.py
VENV_PY = os.path.join(HERE, '.venv', 'Scripts', 'python.exe')
DEFAULT_OUT = os.path.join(HERE, 'frames')
sys.path.insert(0, VW)
import numpy as np
from PIL import Image, ImageDraw
import clawd as C
import items as ITEMS
from common import (Scale, paste_rgba, hrand, rrect_poly, clamp, smooth, lerp, bump, env_in_out,
                    ease_in, ease_out, ease_out_back, rot_pts, FLOOR_Y, CH, font, star_poly)

FPS = 20
SLOW_FPS = 15                     # idle / sleep: slow breathing, fewer frames on disk
PX = 960.0                        # logical x where Clawd stands in the render canvas
SS = 3
PAD = 4
ALPHA_THR = 3                     # alpha <= this is treated as empty when computing bboxes
ZLEVEL = 9
MAX_WORKERS = 8
CHUNK_FRAMES = 16                 # frames per pool task; idle alone is 22 % of all frames
CROP_ZLEVEL = 1                   # temporary crops only
STAT_ACTIONS = ('idle', 'sleep', 'walk', 'dangle', 'think')
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

IDLE_PERIOD = 3.3                 # breathing period of apply_idle
IDLE_LEN = 4 * IDLE_PERIOD        # 13.2 s loop
IDLE_XFADE = IDLE_PERIOD          # crossfade length at the end of the loop
SLEEP_LEN = 5.0                   # one deep breath per loop
WALK_CYCLE = 0.6                  # one step cycle (both leg pairs)
WALK_LEN = 2 * WALK_CYCLE         # 1.2 s loop
WALK_LOOK = 0.85                  # walk_left / walk_right: eyes towards the walking direction
WALK_LEAN = 3.5                   # ... and a slight lean into it (degrees)
TURN_LEN = WALK_CYCLE             # turn_left / turn_right: one shuffle step on the spot
WORK_LEN = 2.4                    # work_*: start and end in the plain pose, so any two of them join
WORK_LOOP = WORK_LEN * 24 / 47    # read / edit / run / compact repeat after 24 frames: 48 frames, 47 steps (player: HOLD_LOOP_FRAMES)
THROW_LEN = 1.6                   # work_agent: one paper plane
HIGH_FIVE_LEN = 1.6               # high_five_*, nudge_*, peek_*: clips for two pets standing side by side (combos)
HIGH_FIVE_HIT = HIGH_FIVE_LEN * 14 / 31   # contact: frame 14 of 32 (endpoint sampling), played at 14 / 20 = 0.70 s
NUDGE_LEN = 1.2
PEEK_LEN = 2.4
COMFORT_LEN = 2.4                 # comfort_*: three slow pats on the neighbour
STACK_BRACE_LEN = 3.0             # stack_brace: the one below, a loop; its head does not move by a single pixel
HOP_LEN = 1.0                     # stack_hop: one jump on the spot, up onto a head and down from it
STACK_TOP_LEN = 2.4               # stack_top: cheering on top
LEAP_LEN = 1.5                    # leap_crouch: down by LEAP_DOWN, still until LEAP_RISE, up, a small bounce
LEAP_DOWN, LEAP_RISE = 0.28, 0.86
CARRY_LEN = 0.6                   # carry_start_*: the note comes out
CARRY_HOLD_LEN = 2.4              # carry_hold_*: waiting with it, a loop
GIVE_LEN = 2.0                    # give_*, receive_*: the hand-over
RECEIVE_LEN = 2.6
SPARK_LEN = 0.3                   # the little stars after a high five
CALM_TILT = 0.25                  # think / listen / idle keep this much of the character's head tilt
IDLE_TILT = 0.5
SOFT_TILT = 0.6                   # head_tilt / wink
DANGLE_LEN = 2.4
LAND_LEN = 0.5
TUMBLE_LEN = 0.8                  # tumble_*: one whole turn in the air, a loop
SQUASH_LEN = 0.35                 # squash: the hit on the floor at a bounce (the shadow goes quickly: the window is going up)
DIZZY_LEN = 1.8                   # dizzy: sits down, spiral eyes, three stars go round above the head, stands up
SHY_LEN = 1.5
DOZE_IN_LEN = 1.6                 # doze_in: a small stretch, heavy eyes, sits down into the first frame of doze
DOZE_LEN = 4.0                    # doze: sitting, eyes shut; one slow nod per loop (sinks, a jerk up), a bubble swells and pops
DOZE_JERK = 0.8                   # ... of the loop: the head has sunk all the way, jerks up by DOZE_JERK + DOZE_UP
DOZE_UP = 0.08
DOZE_WAKE_LEN = 1.1               # doze_startle: up at once, wide eyes, a small hop and a "!", ends in the plain pose
DOZE_SLEEP_LEN = 0.9              # doze_sleep: from the first frame of doze into the first frame of sleep (z z z fade in)
NAP_LOOK_LEN = 1.6                # nap_look_*: eyes towards the cursor's side, a lean, a blink; plain pose at both ends
THINK_FADE = 0.3                  # bubble fades out over the last 0.3 s of think
RUMMAGE_IN_LEN = 0.8              # rummage_in: looks down, crouches, the first sand flies; ends in frame 0 of rummage
RUMMAGE_LEN = 1.2                 # rummage: two strokes of each arm, a loop
RUMMAGE_FOUND_LEN = 3.2           # rummage_found: stops short, up, shakes the earth off, out with the find, a hop, puts it away
RUMMAGE_NONE_LEN = 4.4            # rummage_none: peers into the hole, up, a shake, looks at its empty arms, lets everything hang
RUMMAGE_UP_LEN = 0.6              # rummage_up: called away in the middle: up at once, the earth drops off it, the hole closes
PULL_OUT_LEN = 3.4                # pull_out: an arm behind its back, feels about, out with a find held high, puts it away
PRESENT_LEN = 2.6                 # present: a find held up from the plain pose, rays behind it, put away
PLAY_LOOK_LEN, PLAY_TOSS_LEN, PLAY_LISTEN_LEN, PLAY_SHOW_LEN = 4.6, 4.4, 4.7, 4.0   # 把玩: the four ways to play with a treasure
PLAY_ROBOT_LEN = 5.5
PLAY_CUBE_LEN = 5.5
PLAY_TOP_LEN = 5.5
PLAY_MOON_LEN = 5.5
PLAY_BALLOON_LEN = 5.5             # the second batch's ways of their own (round 9)
PLAY_DUCK_LEN, PLAY_GOLD_LEN, PLAY_BISCUIT_LEN, PLAY_BOTTLE_LEN, PLAY_HOURGLASS_LEN, PLAY_BUG_LEN, PLAY_PLANE_LEN = 5.5, 4.5, 5.5, 5.5, 5.5, 4.9, 5.0   # ... and the ways of their own (rare and special treasures)
PLAY_WAY = {'semicolon': 'toss', 'screw': 'toss', 'paper_ball': 'toss', 'pebble': 'toss', 'gear': 'toss',
            'paperclip': 'look', 'sticky_note': 'look', 'pencil': 'look', 'leaf': 'look', 'braces': 'look',
            'floppy': 'look', 'bug': 'bug', 'biscuit': 'biscuit',
            'keycap': 'listen', 'shell': 'listen', 'bottle': 'bottle', 'hourglass': 'hourglass',
            'rubber_duck': 'duck', 'gold_semicolon': 'gold', 'plane_model': 'plane',
            'coffee': 'look', 'usb': 'toss', 'headphones': 'listen',          # the second batch (round 9); the rare and
            'balloon': 'balloon', 'robot': 'robot', 'cube': 'cube', 'spin_top': 'top', 'moon_lamp': 'moon'}   # special get ways of their own next
RUMMAGE_SPUR_LEN = 0.45           # rummage_spur: you lend a hand (a click): a start, both arms up, and down to dig twice as hard
TAKE_LEN = 3.0                    # take_*: the big one is handed a find, holds it high, puts it away
SIGN_LEN = 2.4                    # sign_*: a hold like work_*: up by 0.42 s, still from there to 2.0 s, down by the end
SIGN_UP, SIGN_DOWN = 0.42, 0.4
SIGN_ARM = (48.0, 1.16)           # the arm up and out on the outer side, holding the stick
SIGN_STICK = 300.0                # logical px from the arm's tip to the stick's top; the player puts the board there
SIGN_LEAN = 4.0                   # degrees: the stick's top leans outwards
SIGN_LOOK = (0.5, -0.9)           # eyes up towards the board (x towards its side)
SIGN_HOLD_AT = 1.2                # a moment of the still part: where the stick's top is written to the manifest

# (action, label, ctx, loop, fps or None for default, endpoint)
# endpoint=True: the last frame is sampled exactly at u=D (so the action ends at its rest pose / bubble-free)
ACTIONS = [
    ('idle', '待机', {}, True, SLOW_FPS, False),
    ('listen', '认真听', {}, False, None, True),
    ('think', '想一想', {}, False, None, True),
    ('nod', '点头', {}, False, None, False),
    ('thumbs_up', '点赞', {}, False, None, True),
    ('confused', '困惑', {}, False, None, True),
    ('shrug_sweat', '摊手流汗', {}, False, None, False),
    ('aha', '恍然大悟', {}, False, None, False),
    ('celebrate', '庆祝', {}, False, None, True),
    ('wave', '挥手', {}, False, None, True),
    ('hop', '开心小跳', {'text': '+1'}, False, None, False),
    ('surprised', '吓一跳', {}, False, None, False),
    ('head_tilt', '歪头', {}, False, None, False),
    ('wink', '眨眼', {}, False, None, False),
    ('look_at_viewer', '看向你', {}, False, None, True),
    ('proud', '叉腰', {}, False, None, True),
    ('shake_head', '摇头', {}, False, None, True),
    ('tiptoe_peek', '踮脚看', {}, False, None, False),
    ('sleep', '睡觉', {}, True, SLOW_FPS, False),
    ('walk', '走路', {}, True, None, False),
    ('walk_left', '向左走', {}, True, None, False),
    ('walk_right', '向右走', {}, True, None, False),
    ('turn_left', '转向左', {}, False, None, True),
    ('turn_right', '转向右', {}, False, None, True),
    ('work_read', '放大镜', {}, False, None, True),
    ('work_edit', '打字', {}, False, None, True),
    ('work_run', '跑命令', {}, False, None, True),
    ('work_web', '望远镜', {}, False, None, True),
    ('work_compact', '整理记忆', {}, False, None, True),
    ('work_agent', '纸飞机', {}, False, None, True),
    ('dangle', '被拎起来', {}, True, None, False),
    ('land', '落地', {}, False, None, True),
    ('wake_up', '醒来', {}, False, None, True),
    ('shy', '害羞', {}, False, None, True),
    ('high_five_right', '击掌（右）', {}, False, None, True),
    ('high_five_left', '击掌（左）', {}, False, None, True),
    ('high_five_up_right', '击掌（高，右）', {}, False, None, True),
    ('high_five_up_left', '击掌（高，左）', {}, False, None, True),
    ('nudge_right', '拱一拱（右）', {}, False, None, True),
    ('nudge_left', '拱一拱（左）', {}, False, None, True),
    ('peek_right', '看过去（右）', {}, False, None, True),
    ('peek_left', '看过去（左）', {}, False, None, True),
    ('comfort_right', '安慰（右）', {}, False, None, True),
    ('comfort_left', '安慰（左）', {}, False, None, True),
    ('stack_brace', '叠罗汉（底）', {}, True, SLOW_FPS, False),
    ('stack_hop', '叠罗汉（跳）', {}, False, None, False),
    ('stack_top', '叠罗汉（顶上欢呼）', {}, False, None, True),
    ('leap_crouch', '跳山羊（蹲）', {}, False, None, True),
    ('carry_start_right', '拿出纸条（右）', {}, False, None, True),
    ('carry_start_left', '拿出纸条（左）', {}, False, None, True),
    ('carry_hold_right', '举着纸条（右）', {}, True, SLOW_FPS, False),
    ('carry_hold_left', '举着纸条（左）', {}, True, SLOW_FPS, False),
    ('walk_carry_right', '拿纸条向右走', {}, True, None, False),
    ('walk_carry_left', '拿纸条向左走', {}, True, None, False),
    ('sign_right', '举牌（右）', {}, False, None, True),
    ('sign_left', '举牌（左）', {}, False, None, True),
    ('tumble_right', '翻滚（向右）', {}, True, None, False),
    ('tumble_left', '翻滚（向左）', {}, True, None, False),
    ('squash', '弹地', {}, False, None, True),
    ('dizzy', '晕乎乎', {}, False, None, True),
    ('slip_sit_right', '击掌扑空（右）', {}, False, None, True),
    ('slip_sit_left', '击掌扑空（左）', {}, False, None, True),
    ('slip_roll_right', '滚了过去（向右）', {}, False, None, True),
    ('slip_roll_left', '滚了过去（向左）', {}, False, None, True),
    ('stack_flip_right', '翻跟头下来（向右）', {}, False, None, True),
    ('stack_flip_left', '翻跟头下来（向左）', {}, False, None, True),
    ('doze_in', '犯困坐下', {}, False, None, True),
    ('doze', '打瞌睡', {}, True, SLOW_FPS, False),
    ('doze_startle', '惊醒', {}, False, None, True),
    ('doze_up', '打完盹站起来', {}, False, None, True),
    ('doze_sleep', '打盹变睡着', {}, False, None, True),
    ('nap_look_right', '朝右看', {}, False, None, True),
    ('nap_look_left', '朝左看', {}, False, None, True),
    ('rummage_in', '蹲下翻找', {}, False, None, True),
    ('rummage', '翻找', {}, True, None, False),
    ('rummage_found', '翻到了', {}, False, None, True),
    ('rummage_none', '没翻到', {}, False, None, True),
    ('rummage_up', '不翻了', {}, False, None, True),
    ('pull_out', '从身后掏出来', {}, False, None, True),
    ('present', '举起来看', {}, False, None, True),
    ('rummage_spur', '来劲了', {}, False, None, True),
    ('rummage_fast', '起劲地翻找', {}, True, None, False),
    ('bring_start_right', '拿出宝贝（右）', {}, False, None, True),
    ('bring_start_left', '拿出宝贝（左）', {}, False, None, True),
    ('bring_hold_right', '捧着宝贝（右）', {}, True, SLOW_FPS, False),
    ('bring_hold_left', '捧着宝贝（左）', {}, True, SLOW_FPS, False),
    ('walk_bring_right', '捧着宝贝向右走', {}, True, None, False),
    ('walk_bring_left', '捧着宝贝向左走', {}, True, None, False),
    ('take_right', '接过宝贝（右）', {}, False, None, False),
    ('take_left', '接过宝贝（左）', {}, False, None, False),
] + [('%s_%s%s' % (verb, role, d), '%s（%s，%s）' % (lab, {'': '大', 'mid_': '中', 'small_': '小'}[role], dl), {}, False, None, False)
     for verb, lab in (('give', '递纸条'), ('receive', '接纸条')) for role in ('', 'mid_', 'small_')
     for d, dl in (('right', '右'), ('left', '左'))] + [
    ('hand_%s%s' % (role, d), '递宝贝（%s，%s）' % ({'mid_': '中', 'small_': '小'}[role], dl), {}, False, None, False)
    for role in ('mid_', 'small_') for d, dl in (('right', '右'), ('left', '左'))]
ACTIONS += [('play_' + _i, '把玩' + ITEMS.ITEMS[_i][0], {}, False, None, True) for _i in ITEMS.ORDER if _i in PLAY_WAY]
LOOP_LEN = {'idle': IDLE_LEN, 'sleep': SLEEP_LEN, 'walk': WALK_LEN, 'walk_left': WALK_LEN, 'walk_right': WALK_LEN,
            'dangle': DANGLE_LEN, 'stack_brace': STACK_BRACE_LEN, 'carry_hold_right': CARRY_HOLD_LEN, 'carry_hold_left': CARRY_HOLD_LEN,
            'walk_carry_right': WALK_LEN, 'walk_carry_left': WALK_LEN, 'tumble_right': TUMBLE_LEN, 'tumble_left': TUMBLE_LEN, 'doze': DOZE_LEN, 'rummage': RUMMAGE_LEN,
            'rummage_fast': RUMMAGE_LEN, 'bring_hold_right': CARRY_HOLD_LEN, 'bring_hold_left': CARRY_HOLD_LEN,
            'walk_bring_right': WALK_LEN, 'walk_bring_left': WALK_LEN}
WAKE_LEN = 1.1
SLIP_SIT_LEN = 2.6                # slip_sit_*: 小插曲, the high five missed: up, no hand there, down on its bottom, a laugh
SLIP_ROLL_LEN = 2.6               # slip_roll_*: 小插曲, the leapfrog's jumper goes over head over heels: one turn in the air, dizzy, up
STACK_FLIP_LEN = 2.0              # stack_flip_*: 小插曲, down from the top of the stack with a whole turn in the air, proud
ONESHOT_LEN = {'wake_up': WAKE_LEN, 'land': LAND_LEN, 'shy': SHY_LEN, 'turn_left': TURN_LEN, 'turn_right': TURN_LEN,
               'work_read': WORK_LEN, 'work_edit': WORK_LEN, 'work_run': WORK_LEN, 'work_web': WORK_LEN,
               'work_compact': WORK_LEN, 'work_agent': THROW_LEN,
               'high_five_right': HIGH_FIVE_LEN, 'high_five_left': HIGH_FIVE_LEN,
               'high_five_up_right': HIGH_FIVE_LEN, 'high_five_up_left': HIGH_FIVE_LEN,
               'nudge_right': NUDGE_LEN, 'nudge_left': NUDGE_LEN, 'peek_right': PEEK_LEN, 'peek_left': PEEK_LEN,
               'comfort_right': COMFORT_LEN, 'comfort_left': COMFORT_LEN,
               'stack_hop': HOP_LEN, 'stack_top': STACK_TOP_LEN, 'leap_crouch': LEAP_LEN,'carry_start_right': CARRY_LEN, 'carry_start_left': CARRY_LEN,
               'sign_right': SIGN_LEN, 'sign_left': SIGN_LEN, 'squash': SQUASH_LEN, 'dizzy': DIZZY_LEN,
               'slip_sit_right': SLIP_SIT_LEN, 'slip_sit_left': SLIP_SIT_LEN, 'slip_roll_right': SLIP_ROLL_LEN,
               'slip_roll_left': SLIP_ROLL_LEN, 'stack_flip_right': STACK_FLIP_LEN, 'stack_flip_left': STACK_FLIP_LEN,
               'doze_in': DOZE_IN_LEN, 'doze_startle': DOZE_WAKE_LEN, 'doze_up': WAKE_LEN, 'doze_sleep': DOZE_SLEEP_LEN,
               'nap_look_right': NAP_LOOK_LEN, 'nap_look_left': NAP_LOOK_LEN,
               'rummage_in': RUMMAGE_IN_LEN, 'rummage_found': RUMMAGE_FOUND_LEN, 'rummage_none': RUMMAGE_NONE_LEN,
               'pull_out': PULL_OUT_LEN, 'present': PRESENT_LEN, 'rummage_up': RUMMAGE_UP_LEN,
               'rummage_spur': RUMMAGE_SPUR_LEN, 'bring_start_right': CARRY_LEN, 'bring_start_left': CARRY_LEN,
               'take_right': TAKE_LEN, 'take_left': TAKE_LEN}
for _r in ('', 'mid_', 'small_'):
    for _d in ('right', 'left'):
        ONESHOT_LEN['give_%s%s' % (_r, _d)] = GIVE_LEN; ONESHOT_LEN['receive_%s%s' % (_r, _d)] = RECEIVE_LEN
        if _r: ONESHOT_LEN['hand_%s%s' % (_r, _d)] = GIVE_LEN
PREVIEW_FRACS = {'think': (0.2, 0.7, 1.0), 'land': (0.05, 0.25, 0.6), 'shy': (0.2, 0.5, 0.85)}


# ---------------------------------------------------------------- pose helpers
def make_pose():
    return C.new_pose(x=PX, propL=None)      # propL=None: no teaching pointer


def idle_pose(t):
    P = make_pose(); C.apply_idle(P, t); P['tilt'] *= IDLE_TILT; return P


def blend_pose(A, B, w):
    """numeric blend of two poses (w=0 -> A, w=1 -> B); eye_open takes the min so blinks stay crisp."""
    out = {}
    for k, a in A.items():
        b = B[k]
        if k == 'eye_open':
            out[k] = min(a, b)
        elif isinstance(a, bool) or isinstance(a, str) or a is None:
            out[k] = a if w < 0.5 else b
        elif isinstance(a, (int, float)):
            out[k] = lerp(a, b, w)
        elif isinstance(a, tuple):
            out[k] = tuple(lerp(x, y, w) for x, y in zip(a, b))
        else:
            out[k] = a
    return out


def idle_loop_pose(tau, T=IDLE_LEN, X=IDLE_XFADE):
    """seamless: Q(tau) = P(tau) before the fade, then P(tau)->P(tau-T) smoothstep so that Q(T) == Q(0)."""
    if tau <= T - X:
        return idle_pose(tau)
    w = smooth((tau - (T - X)) / X)
    return blend_pose(idle_pose(tau), idle_pose(tau - T), w)


TWO_PI = 2 * math.pi


def sleep_pose(u, T=SLEEP_LEN):
    """eyes closed, slow deep breath (one period per loop), drooping head. Everything is periodic in T."""
    P = make_pose(); c = TWO_PI * u / T
    br = math.sin(c)
    P['eyes'] = 'closed'
    P['sy'] *= 0.955 * (1 + 0.032 * br); P['sx'] *= 1.012 * (1 - 0.016 * br)
    P['tilt'] += 2.0 + 0.8 * math.sin(c + 0.9)                 # droops a little to one side
    P['legx'] = -22.0                                           # crouches
    P['look'] = (0.0, 0.0)
    P['nubL'] = (-8 + 3 * math.sin(c + 0.5), 0.92); P['nubR'] = (-28 + 3 * math.sin(c + 1.2), 0.9)   # arms hang
    return P, [('zzz', u, T)]


def walk_pose_loop(u, T=WALK_LEN, facing=0.0):
    """legs step in place, small body bob; x fixed (the window moves). Periodic in T = 2 step cycles.
    facing: -1 left .. +1 right; 0 looks straight ahead."""
    P = make_pose(); ph = u / WALK_CYCLE                        # walk phase in cycles
    P['walk'] = ph; P['walkamp'] = 1.3
    P['lift'] += 4.5 * abs(math.sin(math.pi * ph))
    foot = 1 - abs(math.sin(math.pi * ph))                      # 1 at footfall
    P['sy'] *= 1 - 0.014 * foot; P['sx'] *= 1 + 0.007 * foot
    P['tilt'] += 1.6 * math.sin(TWO_PI * ph) + 0.8 * math.sin(TWO_PI * u / T)
    a, e = P['nubL']; P['nubL'] = (a + 13 * math.sin(TWO_PI * ph), e)
    a, e = P['nubR']; P['nubR'] = (a - 13 * math.sin(TWO_PI * ph), e)
    if facing:
        P['tilt'] -= WALK_LEAN * facing
        P['look'] = (WALK_LOOK * facing, 0.0)
    return P, []


def turn_pose(u, D, to):
    """Turn to face `to` (-1 left, +1 right) with one step on the spot.  The first and the last frame
    are frame 0 of the walk away from and towards `to`, so both joins are seamless."""
    e = clamp(u / D, 0.0, 1.0); e = e * e * (3 - 2 * e)
    return walk_pose_loop(WALK_CYCLE * e, facing=to * (2 * e - 1))


def loop_pose(name, u):
    if name == 'walk_left': return walk_pose_loop(u, facing=-1.0)
    if name == 'walk_right': return walk_pose_loop(u, facing=1.0)
    if name.startswith('walk_carry_'): return walk_carry_pose(u, 1 if name.endswith('right') else -1)
    if name.startswith('carry_hold_'): return carry_hold_pose(u, 1 if name.endswith('right') else -1)
    if name.startswith('walk_bring_'): return walk_carry_pose(u, 1 if name.endswith('right') else -1, 'item')
    if name.startswith('bring_hold_'): return carry_hold_pose(u, 1 if name.endswith('right') else -1, thing='item')
    if name == 'rummage_fast': return rummage_pose(u, gusto=True)
    if name == 'stack_brace': return stack_brace_pose(u)
    if name.startswith('tumble_'): return tumble_pose(u, 1 if name.endswith('right') else -1)
    if name == 'rummage': return rummage_pose(u)
    return {'sleep': sleep_pose, 'walk': walk_pose_loop, 'dangle': dangle_pose, 'doze': doze_pose}[name](u)


def dangle_pose(u, T=DANGLE_LEN):
    """picked up by the scruff: feet off the floor, legs swing slowly, surprised eyes, slow sway. Periodic in T."""
    P = make_pose(); c = TWO_PI * u / T
    P['eyes'] = 'wide'; P['look'] = (0.0, 0.35)
    P['lift'] += 62 + 3 * math.sin(2 * c + 0.5)
    P['walk'] = u / (T / 2); P['walkamp'] = 1.0                 # 2 slow swings per loop
    P['sy'] *= 1.03 + 0.008 * math.sin(2 * c); P['sx'] *= 0.985
    P['tilt'] += 5.5 * math.sin(c)
    P['nubL'] = (58 + 9 * math.sin(2 * c + 0.4), 1.1); P['nubR'] = (58 - 9 * math.sin(2 * c + 0.4), 1.1)
    return P, []


def land_pose(u, D=LAND_LEN):
    """short drop, hard squash, stretch, settle back to rest."""
    P = make_pose(); t_hit = 0.09
    if u < t_hit:
        P['lift'] += 28 * (1 - ease_in(u / t_hit))
        s = 0.06 * smooth(u / 0.05)
        P['sy'] *= 1 + s; P['sx'] *= 1 - 0.035 * s / 0.06
        P['eyes'] = 'wide'; P['nubL'] = (50, 1.1); P['nubR'] = (50, 1.1)
    else:
        w = u - t_hit
        sq = math.exp(-7 * w) * math.cos(TWO_PI * w / 0.36) * (1 - smooth((u - 0.34) / (D - 0.34)))
        P['sy'] *= 1 - 0.19 * sq; P['sx'] *= 1 + 0.12 * sq
        k = bump(u, t_hit, 0.42)
        P['nubL'] = (lerp(P['nubL'][0], 55, k), 1.0 + 0.1 * k); P['nubR'] = (lerp(P['nubR'][0], 55, k), 1.0 + 0.1 * k)
        if w < 0.14: P['eyes'] = 'squeeze'
    return P, [('dust', u, t_hit)]


def shy_pose(u, D=SHY_LEN):
    """happy eyes, blush ramps up then down, little wiggle and foot shuffle, glances away."""
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.4)
    P['blush'] = env_in_out(u, D, 0.55, 0.55)
    if 0.15 < u < D - 0.25: P['eyes'] = 'happy'
    P['tilt'] += (1.5 + 1.8 * math.sin(TWO_PI * 2.4 * u)) * e
    P['look'] = (-0.35 * e, 0.45 * e)
    P['sy'] *= 1 - 0.035 * e; P['sx'] *= 1 + 0.015 * e
    P['nubL'] = (lerp(P['nubL'][0], -38, e), lerp(1.0, 0.8, e)); P['nubR'] = (lerp(P['nubR'][0], -38, e), lerp(1.0, 0.8, e))
    P['walk'] = u * 1.5; P['walkamp'] = 0.55 * e
    return P, []


# ---------------------------------------------------------------- fx
def pet_confetti(img, sc, P, u):
    """smaller version of the board confetti: narrow spread, stays above the floor (a desktop pet window must stay compact)."""
    g = C.geom(P); hx, hy = g['head']; d = ImageDraw.Draw(img); S = sc.f
    cols = [CH['y'], CH['p'], CH['b'], CH['g'], CH['o'], CH['w']]
    for i in range(46):
        r1, r2, r3 = hrand('cf', i, 1), hrand('cf', i, 2), hrand('cf', i, 3)
        vx = (r1 - 0.5) * 420; vy = -(420 + 360 * r2)
        tt = u - 0.12
        if tt < 0: continue
        px_ = hx + vx * tt; py_ = hy - 40 + vy * tt + 900 * tt * tt
        if py_ > FLOOR_Y - 14: continue                   # landed behind the feet: let it vanish
        a = int(255 * clamp((C.D_CONF - tt) / 0.6, 0, 1))
        if a < 8: continue
        ang = tt * (6 + 10 * r3)
        pts = rrect_poly(px_, py_, 16, 8, 2, math.degrees(ang))
        d.polygon([(S(x), S(y)) for x, y in pts], fill=cols[i % len(cols)] + (a,))


def draw_zzz(img, sc, P, u, T, fade=1.0):
    """three letters z / Z / z drifting up from the head's right side, growing and fading; periodic in T."""
    g = C.geom(P); hx, hy = g['head']; d = ImageDraw.Draw(img); S = sc.f
    for i, ch in enumerate(('z', 'Z', 'z')):
        ph = (u / T + i / 3.0) % 1.0
        a = int(235 * bump(ph, 0.0, 1.0) ** 0.7 * fade)
        if a < 6: continue
        size = 38 + 28 * ph
        x = hx + 88 + 46 * ph + 7 * math.sin(TWO_PI * ph * 1.5 + i)
        y = hy + 6 - 108 * ph
        f = font('yaheib', S(size))
        d.text((S(x), S(y)), ch, font=f, fill=(176, 218, 255, a), stroke_width=max(1, int(round(S(2.2)))), stroke_fill=(62, 96, 168, a))


def draw_dust(img, sc, P, u, t_hit):
    """two small puffs kicked out to the sides at the moment of landing."""
    if u < t_hit: return
    w = u - t_hit; d = ImageDraw.Draw(img); S = sc.f
    if w > 0.32: return
    a = int(200 * clamp(1 - w / 0.32, 0, 1))
    for side in (-1, 1):
        for j in range(2):
            x = P['x'] + side * (72 + 62 * ease_out(w / 0.32) + 18 * j); y = FLOOR_Y - 9 - 8 * j - 22 * ease_out(w / 0.32)
            r = 7 + 9 * w / 0.32 - 2 * j
            d.ellipse((S(x - r), S(y - r), S(x + r), S(y + r)), fill=(214, 206, 194, a))


# ---------------------------------------------------------------- work clips
# Told apart by arms and props, not by tilting.  e is 0 at both ends: the plain pose, no prop.
# Clawd's arms are short stubs at its sides and stay that way: they never cross the body (front stays False),
# hardly change in length (ext at most about 1.3), and there is no separate hand.  So the arm does not reach for a
# prop: the prop is hung on the arm's tip, g['tipR'].  All of it is in logical units, so it scales with the body.
_G0 = None


def _rest():
    """Geometry of the plain pose."""
    global _G0
    if _G0 is None: _G0 = C.geom(make_pose())
    return _G0


def _arm(P, key, ang, ext, e):
    a0, x0 = P['nub' + key]
    P['nub' + key] = (lerp(a0, ang, e), lerp(x0, ext, e))


def read_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.3); w = math.sin(TWO_PI * u / WORK_LOOP)
    _arm(P, 'R', 6 + 9 * w, 1.1, e)                            # the glass goes up and down beside the face
    P['look'] = (0.85 * e, (-0.35 - 0.3 * w) * e)
    return P, [('work', 'read', u, e)]


def edit_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.3); w = math.sin(TWO_PI * 3 * u / WORK_LOOP)
    _arm(P, 'L', -68, 1.26 + 0.09 * w, e); _arm(P, 'R', -68, 1.26 - 0.09 * w, e)   # the two ends of the keyboard, in turn
    P['look'] = (0.0, 0.8 * e)
    P['sy'] *= 1 - 0.008 * abs(w) * e
    return P, [('work', 'edit', u, e)]


def run_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.3); w = math.sin(TWO_PI * u / WORK_LOOP)
    _arm(P, 'R', 8 + 3 * w, 1.1, e)
    P['look'] = (0.8 * e, 0.05 * e)
    return P, [('work', 'run', u, e)]


def web_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.3)
    _arm(P, 'R', 72, 1.3, e)                                   # under the tube; the eyepiece comes to the eye
    P['look'] = (0.75 * e, -0.2 * e)
    return P, [('work', 'web', u, e)]


def compact_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.3); w = 0.5 - 0.5 * math.cos(TWO_PI * u / WORK_LOOP)
    _arm(P, 'L', 48 + 10 * w, 1.1, e); _arm(P, 'R', 48 + 10 * w, 1.1, e)
    P['sy'] *= 1 - 0.03 * w * e; P['sx'] *= 1 + 0.015 * w * e
    if e > 0.5: P['eyes'] = 'happy'
    return P, [('work', 'compact', u, e)]


# ---------------------------------------------------------------- reactions
# Same rules as the work clips: start and end in the plain pose, say it with the arms, keep the body nearly upright.
def thumbs_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.2, 0.3)
    _arm(P, 'R', 34 + 6 * bump(u, 0.2, 0.55), 1.1, e)
    if e > 0.4: P['eyes'] = 'happy'
    P['blush'] = e
    P['sy'] *= 1 + 0.02 * e
    return P, [('work', 'thumb', u, e), ('check', u)]


def celebrate_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.15, 0.4)
    j1, j2 = bump(u, 0.12, 0.9), bump(u, 1.05, 1.6)
    squash = bump(u, 0.0, 0.14) + bump(u, 0.9, 1.06) + bump(u, 1.6, 1.8)
    P['lift'] += 85 * j1 + 42 * j2
    P['sy'] *= 1 + 0.05 * (j1 + j2) - 0.09 * squash
    P['sx'] *= 1 - 0.025 * (j1 + j2) + 0.05 * squash
    sw = 14 * math.sin(TWO_PI * 2.6 * u)
    _arm(P, 'L', 55 + sw, 1.25, e); _arm(P, 'R', 55 - sw, 1.25, e)
    if e > 0.3: P['eyes'] = 'star'
    P['blush'] = e
    return P, [('confetti', u)]


def wave_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.2, 0.3); s = math.sin(TWO_PI * 2.2 * u)
    _arm(P, 'R', 44 + 24 * s, 1.25, e)
    if e > 0.4: P['eyes'] = 'happy'
    P['blush'] = 0.8 * e
    P['tilt'] += 1.0 * s * e
    return P, []


def proud_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.4)                  # arms down and out, chest out
    _arm(P, 'L', -40, 0.95, e); _arm(P, 'R', -40, 0.95, e)
    P['sy'] *= 1 + 0.04 * e; P['sx'] *= 1 + 0.015 * e
    if e > 0.5: P['eyes'] = 'closed'
    return P, []


def look_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.15, 0.2)                 # eyes wide, a little closer to you
    if e > 0.5: P['eyes'] = 'wide'
    P['sy'] *= 1 + 0.04 * e; P['sx'] *= 1 + 0.02 * e
    _arm(P, 'L', 26, P['nubL'][1], e); _arm(P, 'R', 26, P['nubR'][1], e)
    return P, []


def confused_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.3)                  # scratches its side
    P['tilt'] += 2.5 * math.sin(TWO_PI * u / 1.6) * e
    if e > 0.3: P['eyes'] = 'spiral'
    _arm(P, 'R', 60 + 9 * math.sin(TWO_PI * 3 * u), 1.2, e)
    _arm(P, 'L', 25, 1.0, e)
    return P, [('qmarks', u, e), ('sweat', u, e)]


def shake_pose(u, D):
    P = make_pose(); e = env_in_out(u, D, 0.15, 0.2); s = math.sin(TWO_PI * 2 * u / D)   # "no": eyes and body from side to side
    P['look'] = (0.85 * s * e, 0.0)
    P['x'] += 7 * s * e
    P['tilt'] -= 1.5 * s * e
    a = 8 * s * e
    P['nubL'] = (P['nubL'][0] + a, P['nubL'][1]); P['nubR'] = (P['nubR'][0] - a, P['nubR'][1])
    return P, []


def wake_up_pose(u, D, A=None):
    """From the sleeping crouch to the plain pose: the eyes open first, then it stands up with a small stretch.
    The first frame is the sleep pose half way through its breath (or A); the last frame is the plain pose."""
    if A is None: A = sleep_pose(0.0)[0]
    P = make_pose(); B = make_pose()
    e = smooth((u - 0.28) / 0.62)
    for k in ('sx', 'sy', 'tilt', 'legx'):
        P[k] = lerp(A[k], B[k], e)
    for key in ('nubL', 'nubR'):
        P[key] = (lerp(A[key][0], B[key][0], e), lerp(A[key][1], B[key][1], e))
    stretch = bump(u, 0.45, 1.0)
    P['sy'] *= 1 + 0.025 * stretch; P['sx'] *= 1 - 0.012 * stretch
    a, x = P['nubL']; P['nubL'] = (a + 16 * stretch, x)
    a, x = P['nubR']; P['nubR'] = (a + 16 * stretch, x)
    P['eyes'] = 'closed' if u < 0.3 else B['eyes']
    return P, []


# (u, angle, length) of the throwing arm: an underarm toss.  The plane leaves the hand at THROW_RELEASE, on the way up.
THROW_KEYS = ((0.0, -10.0, 1.0), (0.35, -58.0, 1.05), (0.5, -62.0, 1.05), (0.72, 30.0, 1.2), (0.95, 42.0, 1.15), (THROW_LEN, -10.0, 1.0))
THROW_RELEASE = 0.58
THROW_HEAD = 38.0                 # degrees above the horizon: the nose, held and at the start of the flight


def agent_pose(u, D):
    P = make_pose()
    for (u0, a0, x0), (u1, a1, x1) in zip(THROW_KEYS, THROW_KEYS[1:]):
        if u <= u1:
            s = smooth((u - u0) / (u1 - u0)); P['nubR'] = (lerp(a0, a1, s), lerp(x0, x1, s)); break
    P['tilt'] += 1.5 * bump(u, 0.15, 0.55) - 2.0 * bump(u, 0.52, 1.2)    # leans back, then into the throw
    e = env_in_out(u, D, 0.2, 0.3)
    P['look'] = (0.75 * e, (0.4 if u < THROW_RELEASE else -0.45) * e)    # at the plane in the hand, then after it
    if THROW_RELEASE < u < D - 0.25: P['eyes'] = 'happy'
    return P, [('work', 'agent', u, e)]


# ---------------------------------------------------------------- combo clips (two pets standing next to each other)
# `side` is where the neighbour stands: +1 on the viewer's right (the pet's R arm, eyes towards +x, leaning right is a
# negative tilt), -1 on the left.  Left is the same motion mirrored.  Both start and end in the plain pose, whose
# arms are not symmetric (L 18 degrees, R -10), so only the first and last moments of the two sides differ.
# Same arm rules as above: the arm is a short stub at the side, hardly longer than 1.3, never crosses the body.
HF_ARM = (28.0, 1.3)              # high five (the bigger pet): the arm at the contact (angle up from the side, length)
HF_LEAN = 2.5                     # ... and the lean towards the neighbour then (degrees, the near foot stays down)
HF_HOP = 9.0                      # ... and the small hop that has its top at the contact (logical px)
HF_UP_ARM = (60.0, 1.3)           # high_five_up (the smaller pet jumps up to the bigger one's hand): arm, steeper
HF_UP_LEAN = 3.0                  # ... lean (degrees)
HF_UP_HOP = 65.0                  # ... height of the jump (logical px; celebrate lifts 85)
HF_UP_AIR = 0.30                  # ... seconds from take-off to the contact, and from the contact to landing
SPARK_AT = (-14.0, -8.0)          # the burst's centre, from the bigger pet's arm tip: (towards its own body, up) in logical px
SPARK_ANGLES = (0.0, 28.0, -28.0, 52.0, -52.0)     # degrees from straight up (only the bigger pet has stars: one burst at the contact)
SPARK_REACH = (46.0, 38.0, 38.0, 30.0, 30.0)       # how far each flies (logical px); the size comes with it
SPARK_SIZE = (13.5, 12.0, 12.0, 10.5, 10.5)


def _mirror_arm(P, side, ang, ext, e, e_ext=None):
    """the arm on `side` towards (ang, ext) with weight e; e_ext: a different weight for the length."""
    key = 'R' if side > 0 else 'L'
    a0, x0 = P['nub' + key]
    P['nub' + key] = (lerp(a0, ang, e), lerp(x0, ext, e if e_ext is None else e_ext))


def high_five_body(u, side):
    """The pose of a high five; the arm's tip (and the lean and the hop) are at their top exactly at HIGH_FIVE_HIT."""
    P = make_pose(); hit = HIGH_FIVE_HIT
    w = smooth((u - 0.10) / (hit - 0.10)) * (1.0 - smooth((u - hit) / 0.72))
    _mirror_arm(P, side, HF_ARM[0], HF_ARM[1], w, w ** 3)                 # the length comes late: a push into the contact
    P['tilt'] -= side * HF_LEAN * w
    P['lift'] += HF_HOP * bump(u, hit - 0.30, hit + 0.30)
    k = bump(u, 0.0, 0.34) - bump(u, hit + 0.16, hit + 0.48)       # a little crouch to jump, a little squash on landing
    P['sy'] *= 1 - 0.03 * k; P['sx'] *= 1 + 0.015 * k
    e = env_in_out(u, HIGH_FIVE_LEN, 0.3, 0.4)
    P['look'] = (0.5 * side * e, -0.15 * e)
    if 0.28 < u < HIGH_FIVE_LEN - 0.3: P['eyes'] = 'happy'
    P['blush'] = 0.7 * e
    return P


def high_five_up_body(u, side):
    """The smaller pet of a high five: crouches, jumps with the top of the jump at HIGH_FIVE_HIT, the arm up steeply to
    the bigger one's hand (its arm stays at 1.3 at most), lands where it took off.  No stars: the bigger pet has them."""
    P = make_pose(); hit = HIGH_FIVE_HIT; air = HF_UP_AIR
    w = smooth((u - 0.10) / (hit - 0.10)) * (1.0 - smooth((u - hit) / 0.72))
    _mirror_arm(P, side, HF_UP_ARM[0], HF_UP_ARM[1], w, w ** 2)
    P['tilt'] -= side * HF_UP_LEAN * w
    x = (u - hit) / air
    if abs(x) < 1.0: P['lift'] += HF_UP_HOP * (1.0 - x * x)               # one parabola, apex at the contact
    crouch = bump(u, 0.04, hit - air); stretch = bump(u, hit - air, hit + air); land = bump(u, hit + air - 0.02, hit + air + 0.28)
    P['legx'] = -16.0 * crouch + 8.0 * stretch - 12.0 * land               # bends before take-off, stretches in the air, bends on landing
    P['sy'] *= 1 - 0.03 * crouch + 0.03 * stretch - 0.04 * land; P['sx'] *= 1 + 0.015 * crouch - 0.015 * stretch + 0.02 * land
    e = env_in_out(u, HIGH_FIVE_LEN, 0.3, 0.4)
    P['look'] = (0.5 * side * e, -0.4 * e)                                  # up at the hand
    if 0.28 < u < HIGH_FIVE_LEN - 0.3: P['eyes'] = 'happy'
    P['blush'] = 0.7 * e
    return P


def high_five_up_pose(u, D, side):
    return high_five_up_body(u, side), []


def high_five_pose(u, D, side):
    P = high_five_body(u, side)
    g = C.geom(high_five_body(HIGH_FIVE_HIT, side)); key = 'tipR' if side > 0 else 'tipL'
    return P, [('spark', u - HIGH_FIVE_HIT, (g[key][0] + side * SPARK_AT[0], g[key][1] + SPARK_AT[1]))]


def nudge_pose(u, D, side):
    """Two small pokes at the neighbour with the arm on its side, feet planted, leaning in a little."""
    P = make_pose()
    ready = smooth((u - 0.04) / 0.26) * (1.0 - smooth((u - 0.92) / 0.24))
    p = bump(u, 0.277, 0.557) + bump(u, 0.590, 0.870)              # the pokes: 0 -> 1 -> 0 each, tops on frames 8 and 14 of 24
    _mirror_arm(P, side, 32.0 - 22.0 * p, 1.0 + 0.3 * p, ready)
    P['tilt'] -= side * (1.6 * ready + 0.5 * p)
    P['look'] = (0.85 * side * ready, -0.15 * ready)
    P['blush'] = 0.5 * ready
    return P, []


def peek_pose(u, D, side):
    """On tiptoe like tiptoe_peek, eyes wide and towards the neighbour and a little up, leaning over a bit."""
    P = make_pose(); e = env_in_out(u, D, 0.4, 0.4); ph = TWO_PI * u / 0.55
    P['legx'] = 28 * e + 2.5 * e * math.sin(ph)
    P['sy'] *= 1 + 0.04 * e; P['sx'] *= 1 - 0.022 * e
    P['tilt'] -= side * (1.6 + 0.4 * math.sin(TWO_PI * u / 1.6)) * e
    P['look'] = (0.95 * side * e, (-0.45 + 0.1 * math.sin(TWO_PI * u / 1.1)) * e)
    for key in 'LR': _arm(P, key, 8 + 4 * math.sin(ph + 1.0), 1.0, e)       # arms out a little for balance
    if e > 0.3: P['eyes'] = 'wide'
    P['eye_open'] = lerp(1.0, C.blink_amount(u + 0.5), env_in_out(u, D, 0.3, 0.3))
    return P, []


COMFORT_PATS = (0.62, 1.12, 1.62)  # s: the arm is down on the neighbour at these moments, up between them
COMFORT_ARM = (34.0, 1.2)         # ... the arm then (angle up from the side, length); it stays a short stub
COMFORT_LIFT = 20.0               # ... how much higher it is between the pats (degrees)
COMFORT_LEAN = 3.0                # the lean towards the neighbour (degrees, the near foot stays down)
HEART_LEN = 0.7
HEART_SIZE = 30.0                 # logical px


def comfort_body(u, side):
    """Pats the neighbour three times, slowly, leaning in with a warm look: slower and softer than the pokes of nudge."""
    P = make_pose()
    ready = smooth((u - 0.06) / 0.38) * (1.0 - smooth((u - 1.94) / 0.38))
    up = 1.0 - sum(bump(u, t - 0.25, t + 0.25) for t in COMFORT_PATS)   # 1: the arm up, 0: down on the neighbour
    _mirror_arm(P, side, COMFORT_ARM[0] + COMFORT_LIFT * up, COMFORT_ARM[1], ready)
    P['tilt'] -= side * (COMFORT_LEAN + 0.5 * (1.0 - up)) * ready
    P['sy'] *= 1 - 0.012 * (1.0 - up) * ready
    e = env_in_out(u, COMFORT_LEN, 0.3, 0.4)
    P['look'] = (0.6 * side * e, -0.2 * e)
    if 0.3 < u < COMFORT_LEN - 0.34: P['eyes'] = 'happy'
    P['blush'] = 0.6 * e
    return P


def comfort_pose(u, D, side):
    key = 'tipR' if side > 0 else 'tipL'
    fxs = []
    for t in COMFORT_PATS:
        tip = C.geom(comfort_body(t, side))[key]
        fxs.append(('heart', u - t, (tip[0] + side * 6.0, tip[1] - 40.0)))
    return comfort_body(u, side), fxs


# ---- stacking: one pet stands on another one's head (every pet is its own window; the player moves them)
STACK_LEGX = -6.0                 # ... knees a little bent
STACK_SY, STACK_SX = 0.985, 1.01  # ... a little squashed by the load (constant: the top edge stays put)
STACK_BLINK = 1.9                 # ... one blink per loop, at this moment
HOP_OFF, HOP_ON = 0.35, 0.75      # ... take-off and touch-down (s; frames 7 and 15 at 20 fps); in between the
                                  #     feet stay on the anchor and the player carries the window along its arc
STACK_TOP_HOPS = ((0.30, 0.72), (0.98, 1.40), (1.62, 2.00))   # small bounces, back down to the head each time; a burst of
                                                               # stars over its right, left, then middle at each top


def stack_brace_pose(u, T=STACK_BRACE_LEN):
    """Stands firm with the knees a little bent and both arms out to the sides; the body's size, tilt and place are
    the same in every frame, only the arms sway a little and the eyes blink.  Periodic in T."""
    P = make_pose(); c = TWO_PI * u / T
    P['legx'] = STACK_LEGX; P['sy'] *= STACK_SY; P['sx'] *= STACK_SX
    P['nubL'] = (6.0 + 4.0 * math.sin(c + 0.4), 1.15); P['nubR'] = (6.0 + 4.0 * math.sin(c + 2.0), 1.15)
    P['look'] = (0.12 * math.sin(c), -0.55)                    # up at the one on its head
    b = (u - STACK_BLINK) / 0.16
    if 0.0 <= b <= 1.0: P['eye_open'] = abs(1 - 2 * b) ** 0.8
    P['blush'] = 0.3
    return P, []


def stack_hop_pose(u, D):
    """Crouch, jump, land.  The feet never leave the anchor: during the air time the player moves the window."""
    P = make_pose(); arm = 0.0; ext = 1.0
    if u < HOP_OFF:                                            # crouch, arms swing down and back
        c = smooth(u / 0.3)
        P['legx'] = -16.0 * c; P['sy'] *= 1 - 0.05 * c; P['sx'] *= 1 + 0.025 * c
        arm = -34.0 * c
    elif u < HOP_ON:                                           # in the air: stretched at first, legs drawn up, then reaching
        a = (u - HOP_OFF) / (HOP_ON - HOP_OFF)
        P['legx'] = lerp(lerp(6.0, -10.0, smooth(a / 0.55)), 4.0, smooth((a - 0.6) / 0.4))
        st = 1.0 - smooth(a / 0.6)
        P['sy'] *= 1 + 0.05 * st; P['sx'] *= 1 - 0.025 * st
        arm = lerp(-34.0, 46.0, smooth(a / 0.45)); arm = lerp(arm, 24.0, smooth((a - 0.6) / 0.4)); ext = 1.15
        P['eyes'] = 'happy'
        P['shadow'] = max(1.0 - smooth(a / 0.15), smooth((a - 0.85) / 0.15))    # no shadow under a window in the air
    else:                                                      # touch-down: a squash, then the plain pose by the last frame
        k = bump(u, HOP_ON, 0.95)
        P['legx'] = -12.0 * k; P['sy'] *= 1 - 0.07 * k; P['sx'] *= 1 + 0.04 * k
        arm = 24.0 * smooth((0.92 - u) / 0.17); ext = lerp(1.0, 1.15, smooth((0.92 - u) / 0.17))
        if u < 0.84: P['eyes'] = 'squeeze'
    for key in 'LR':
        a0, x0 = P['nub' + key]
        if arm or ext != 1.0: P['nub' + key] = (a0 + arm, lerp(x0, ext, 1.0))
    return P, []


def stack_top_body(u, D):
    """On top: both stubs up and waving, three small bounces that come back down to the head."""
    P = make_pose(); e = env_in_out(u, D, 0.3, 0.4)
    sw = 16.0 * math.sin(TWO_PI * u / 0.7)
    _arm(P, 'L', 62.0 + sw, 1.25, e); _arm(P, 'R', 62.0 - sw, 1.25, e)
    for t0, t1 in STACK_TOP_HOPS:
        P['lift'] += 20.0 * bump(u, t0, t1)
        k = bump(u, t1 - 0.02, t1 + 0.16)
        P['sy'] *= 1 - 0.05 * k; P['sx'] *= 1 + 0.03 * k
    if e > 0.3: P['eyes'] = 'star'
    P['blush'] = e
    return P


def stack_top_pose(u, D):
    fxs = []
    for i, (t0, t1) in enumerate(STACK_TOP_HOPS):             # a burst at the top of each bounce, over a raised arm
        tm = 0.5 * (t0 + t1); g = C.geom(stack_top_body(tm, D)); sd = (1, -1, 0)[i]
        fxs.append(('spark', u - tm + 0.08, (g['x'] + sd * 105.0, g['top'] - 22.0), 1.7))
    return stack_top_body(u, D), fxs


def leap_crouch_pose(u, D):
    """跳山羊: ducks down low with the arms tucked in and the eyes squeezed shut while the other one jumps over its
    head (the player starts that one's stack_hop LEAP_HOP_AT after this clip: in the air from 0.40 to 0.80 s),
    ducks a little more as it passes, then stands up with a happy little bounce.  Starts and ends in the plain pose."""
    P = make_pose()
    c = smooth(u / LEAP_DOWN) * (1.0 - smooth((u - LEAP_RISE) / 0.32))
    duck = bump(u, 0.42, 0.82)
    k = bump(u, LEAP_RISE + 0.3, D)                            # the bounce after standing up
    P['legx'] = -22.0 * c - 6.0 * duck * c - 8.0 * k
    P['sy'] *= 1 - 0.06 * c - 0.03 * duck * c - 0.03 * k; P['sx'] *= 1 + 0.03 * c + 0.015 * duck * c + 0.02 * k
    for key in 'LR':
        a0, x0 = P['nub' + key]; P['nub' + key] = (a0 - 32.0 * c, lerp(x0, 0.9, c))
    P['look'] = (0.0, 0.45 * c)
    if 0.24 < u < LEAP_RISE + 0.05: P['eyes'] = 'squeeze'
    elif LEAP_RISE + 0.18 < u < D - 0.06: P['eyes'] = 'happy'
    P['blush'] = 0.5 * bump(u, LEAP_RISE, D)
    return P, []


# ---- thrown: tumbling in the air, squashed at each bounce, dizzy after the landing (the player moves the window)
TUMBLE_LIFT = 46.0                # logical px: the body turns about its centre, this much higher than at rest, so that
                                  # no part of it reaches below the feet and the canvas does not grow
DIZZY_STAND = 0.45                # ... the last this long it stands up into the plain pose


def tumble_pose(u, sgn, T=TUMBLE_LEN):
    """Turning head over heels about the body's centre (sgn +1: clockwise, thrown to the right), legs kicking,
    arms out, eyes wide.  No squash: the body keeps its shape.  Periodic in T."""
    P = make_pose(); c = u / T
    P['shadow'] = 0.0
    P['eyes'] = 'wide'; P['look'] = (0.0, 0.0)
    P['walk'] = 2.0 * c; P['walkamp'] = 1.3
    w = math.sin(TWO_PI * 2 * c)
    P['nubL'] = (62 + 18 * w, 1.12); P['nubR'] = (62 - 18 * w, 1.12)
    th = -sgn * 360.0 * c
    P['tilt'] = th
    if abs(th) > 1e-3:                                          # turn about the centre, not about a foot
        g0 = C.geom(dict(P, tilt=0.0)); cx, cy = g0['x'], g0['cy']
        piv = C.tilt_pivot(P, g0['bw'], g0['feet'])
        rx, ry = rot_pts([(cx, cy)], piv[0], piv[1], th)[0]
        P['x'] += cx - rx; P['lift'] -= cy - ry
    P['lift'] += TUMBLE_LIFT
    return P, []


def squash_pose(u, D=SQUASH_LEN):
    """The hit: flat and wide at once, eyes squeezed, arms flung up, then a stretch upwards.  Ends a little stretched
    with wide eyes, as it leaves the floor again (or sits down dizzy)."""
    P = make_pose()
    hit = math.exp(-14.0 * u)
    st = bump(u, 0.10, D) * 0.5
    P['sy'] *= 1 - 0.26 * hit + 0.07 * st; P['sx'] *= 1 + 0.2 * hit - 0.04 * st
    P['legx'] = -14.0 * hit
    P['shadow'] = 1.0 - smooth(u / 0.12)
    P['eyes'] = 'squeeze' if u < 0.16 else 'wide'
    P['nubL'] = (lerp(70, 55, smooth(u / D)), 1.12); P['nubR'] = (lerp(70, 55, smooth(u / D)), 1.12)
    return P, [('dust', u + 0.09, 0.09)]


def dizzy_pose(u, D=DIZZY_LEN):
    """Sits down hard, spiral eyes, the head going round in a small circle, arms hanging, three little stars
    circling above the head; at the end it stands up into the plain pose (the stars fade out on their own)."""
    P = make_pose()
    sit = smooth(u / 0.18) * (1.0 - smooth((u - (D - DIZZY_STAND)) / DIZZY_STAND))
    P['legx'] = -22.0 * sit
    P['sy'] *= 1 - 0.05 * sit; P['sx'] *= 1 + 0.03 * sit
    ph = TWO_PI * u / 0.9
    P['tilt'] += 6.0 * math.sin(ph) * sit
    P['look'] = (0.35 * math.cos(ph) * sit, 0.25 * math.sin(ph) * sit)
    for key, off in (('L', 0.0), ('R', 1.3)):
        a0, x0 = P['nub' + key]
        P['nub' + key] = (lerp(a0, -14 + 6 * math.sin(ph + off), sit), lerp(x0, 0.95, sit))
    if 0.1 < u < D - 0.3: P['eyes'] = 'spiral'
    g = C.geom(P)
    return P, [('dizzy', u, (g['x'], g['top'] - 58.0), sit)]


def draw_dizzy(fr, sc, u, head, a):
    """Three small yellow stars going round on a flat ring above the head; those behind are smaller and paler."""
    if a <= 0.01: return
    hx, hy = head; RX, RY = 124.0, 28.0
    def paint(d, X, Y, k):
        stars = []
        for i in range(3):
            q = TWO_PI * (u / 0.75 + i / 3.0)
            depth = math.sin(q)                                  # +1 in front, -1 behind
            stars.append((depth, hx + RX * math.cos(q), hy + RY * depth, 27.0 * (0.78 + 0.22 * depth)))
        for depth, x, y, R in sorted(stars):
            light = 0.75 + 0.25 * depth
            d.polygon([(X(x_), Y(y_)) for x_, y_ in star_poly(x, y, R, R * 0.45, rot=-90 + 40 * u)],
                      fill=(255, int(150 + 58 * light), int(40 + 30 * light), 255))
            d.polygon([(X(x_), Y(y_)) for x_, y_ in star_poly(x, y, R * 0.5, R * 0.22, rot=-90 + 40 * u)],
                      fill=(255, 238, 170, 255))
    draw_prop_layer(fr, sc, hx - RX - 30, hy - RY - 30, hx + RX + 30, hy + RY + 30, a, paint)


# ---- dozing off: the cursor has rested near it a while (the player's 鼠标小剧场); a move of the cursor startles it
def doze_pose(u, T=DOZE_LEN):
    """Sitting in the crouch of sleep, eyes shut, arms hanging; the head sinks slowly to one side and jerks up once
    per loop (eyes half open for a moment), a bubble swells by its face and pops at the jerk.  Periodic in T."""
    P = make_pose(); c = (u / T) % 1.0
    br = math.sin(TWO_PI * c)
    sink = smooth(c / DOZE_JERK) if c < DOZE_JERK else 1.0 - smooth((c - DOZE_JERK) / DOZE_UP)
    jerk = bump(c, DOZE_JERK, DOZE_JERK + 2 * DOZE_UP)
    P['legx'] = -22.0
    P['sy'] *= 0.955 * (1 + 0.018 * br) * (1 - 0.035 * sink + 0.025 * jerk); P['sx'] *= 1.012 * (1 + 0.016 * sink)
    P['tilt'] += 1.5 + 6.5 * sink
    P['lift'] += 4.0 * jerk
    P['look'] = (0.0, 0.0)
    P['eyes'] = 'half' if DOZE_JERK + 0.01 < c < DOZE_JERK + 0.13 else 'closed'
    P['nubL'] = (-10 + 2 * br - 6 * sink, 0.92); P['nubR'] = (-26 + 2 * br - 6 * sink, 0.9)
    return P, [('snot', c)]


def snot_anchor(P):
    """Where the bubble sits: below the eyes, a little to the right, turned with the body."""
    g0 = C.geom(dict(P, tilt=0.0))
    pt = (P['x'] + 0.1 * g0['bw'], g0['cy'] + 0.06 * g0['bh'])
    if abs(P['tilt']) > 1e-3:
        piv = C.tilt_pivot(P, g0['bw'], g0['feet'])
        pt = rot_pts([pt], piv[0], piv[1], P['tilt'])[0]
    return pt


def draw_snot(fr, sc, P, c):
    """A pale blue bubble that swells while the head sinks, pops at the jerk (a few short lines fly out)."""
    ax, ay = snot_anchor(P)
    if c < DOZE_JERK:
        grow = smooth(c / (DOZE_JERK - 0.04))
        R = 12.0 + 24.0 * grow * (1 + 0.04 * math.sin(TWO_PI * c * 3))
        bx, by = ax + 0.75 * R, ay + 0.25 * R
        def paint(d, X, Y, k):
            d.ellipse((X(bx - R), Y(by - R), X(bx + R), Y(by + R)), fill=(196, 228, 255, 165),
                      outline=(104, 166, 228, 240), width=max(1, int(round(3.4 * k))))
            r = R * 0.28
            d.ellipse((X(bx - R * 0.42 - r), Y(by - R * 0.42 - r), X(bx - R * 0.42 + r), Y(by - R * 0.42 + r)), fill=(255, 255, 255, 230))
        draw_prop_layer(fr, sc, bx - R - 8, by - R - 8, bx + R + 8, by + R + 8, smooth(c / 0.16), paint)
    elif c < DOZE_JERK + 0.07:
        w = (c - DOZE_JERK) / 0.07
        bx, by = ax + 0.75 * 34.0, ay + 0.25 * 34.0
        def paint(d, X, Y, k):
            for i in range(6):
                a = TWO_PI * i / 6 + 0.4
                r0, r1 = 18 + 26 * w, 28 + 30 * w
                d.line((X(bx + r0 * math.cos(a)), Y(by + r0 * math.sin(a)), X(bx + r1 * math.cos(a)), Y(by + r1 * math.sin(a))),
                       fill=(150, 196, 240, 255), width=max(1, int(round(3.0 * k))))
        draw_prop_layer(fr, sc, bx - 70, by - 70, bx + 70, by + 70, 1.0 - w, paint)


def doze_sleep_pose(u, D=DOZE_SLEEP_LEN):
    """Dozed off for real: from the first frame of doze into the first frame of sleep, the z z z fading in."""
    w_ = smooth(u / D)
    P = blend_pose(doze_pose(0.0)[0], sleep_pose(0.0)[0], w_)
    P['eyes'] = 'closed'
    return P, [('zzz', 0.0, SLEEP_LEN, w_)]


def nap_look_pose(u, D, side):
    """The cursor has come to rest on this side: the eyes go over to it (a little up), it leans that way, blinks
    once, and comes back to the plain pose."""
    P = make_pose(); e = env_in_out(u, D, 0.25, 0.3)
    P['look'] = (0.85 * side * e, -0.25 * e)
    P['tilt'] -= 2.5 * side * e
    P['sy'] *= 1 + 0.025 * e; P['sx'] *= 1 + 0.012 * e
    P['eye_open'] = 1.0 - bump(u, 0.78, 0.94)
    _arm(P, 'R' if side > 0 else 'L', 30, 1.05, e)
    return P, []


def doze_in_pose(u, D=DOZE_IN_LEN):
    """A small stretch with heavy eyes, then it sits down; the last frame is the first frame of doze."""
    A = make_pose(); B = doze_pose(0.0)[0]
    s = smooth((u - 0.55) / 0.8)
    P = blend_pose(A, B, s)
    st = bump(u, 0.0, 0.62)
    for key in ('nubL', 'nubR'):
        a, x = P[key]; P[key] = (a + 46 * st, x + 0.08 * st)
    P['sy'] *= 1 + 0.03 * st; P['sx'] *= 1 - 0.015 * st
    P['eyes'] = 'open' if u < 0.12 else ('half' if u < 0.9 else 'closed')
    return P, []


def doze_startle_pose(u, D=DOZE_WAKE_LEN):
    """From the first frame of doze straight up: wide eyes, arms flung up, a small hop and a "!" by the head,
    then a soft landing into the plain pose."""
    A = doze_pose(0.0)[0]; P = make_pose(); plain = make_pose()
    up = smooth(u / 0.12)
    for k in ('sx', 'sy', 'tilt', 'legx'):
        P[k] = lerp(A[k], plain[k], up)
    j = bump(u, 0.06, 0.48)
    P['lift'] += 28.0 * j; P['sy'] *= 1 + 0.05 * j; P['sx'] *= 1 - 0.025 * j
    k2 = bump(u, 0.46, 0.64)
    P['sy'] *= 1 - 0.05 * k2; P['sx'] *= 1 + 0.03 * k2
    e = env_in_out(u, D, 0.08, 0.35)
    for key in ('nubL', 'nubR'):
        a0 = (lerp(A[key][0], plain[key][0], up), lerp(A[key][1], plain[key][1], up))
        P[key] = (lerp(a0[0], 62, e), lerp(a0[1], 1.1, e))
    P['eyes'] = 'closed' if u < 0.03 else ('wide' if u < D - 0.2 else 'open')
    return P, [('exclaim', u, D)]


# ---- rummaging (翻找, 养成): in a long turn a small one crouches where it stands and digs a hole in front of it
# with both short arms, earth flying up; some of it lands on its face (it squeezes its eyes shut) and stays there.
# Then it stands up and shakes itself like a wet dog, and either pulls a find out of the hole, star-eyed
# (rummage_found), or has nothing and droops with a sigh (rummage_none).  The find itself is not in the frames: the
# player lays the treasure's icon over the arm's tip (fx 'item': side, size; written to the manifest per frame).
# PREVIEW_ITEM paints one in, for looking at the art.
DIG_LEGX = -30.0                  # the crouch: legs this much shorter
DIG_ARM = (-62.0, 26.0, 1.28)     # the arms point down beside the body: (angle, swing either way, length)
DIG_STROKE = RUMMAGE_LEN / 2      # one stroke of each arm (they take turns)
DIG_STROKE_FAST = RUMMAGE_LEN / 3 # rummage_fast (someone lends a hand): three strokes a loop, wider, more earth
PIT = (200.0, 62.0, 70.0)         # the earth in front of the feet: (half width, height of the rim, half width of the hole)
SPLAT_AT = 0.56                   # ... of the loop: a clod lands on its face
SPLAT_LEN = 0.26                  # the eyes are squeezed shut this long
# the earth that stays on it: (x, y) in body widths / heights from the body's centre, size in logical px
DIRT_SPOTS = ((-0.35, 0.18, 23.0), (0.38, -0.3, 18.0), (0.06, 0.27, 26.0))
SPLAT_SPOT = 2                    # the one the clod of SPLAT_AT lands on
SHAKE_LEN = 0.56                  # the shake that throws the earth off
EARTH = ((172, 124, 82), (200, 154, 108), (146, 102, 66), (104, 70, 48), (78, 52, 36))   # base, light, dark, the hole, its depth
ITEM_ARM = (62.0, 1.2)            # a find held up
ITEM_BOX = 128.0                  # logical px: the icon's box (the body is 290 wide)
ITEM_UP, ITEM_OUT = 46.0, 14.0    # its centre from the arm's tip: up, and away from the body
BRING_OUT = (58.0, 14.0)          # a find that is carried: this far out and up from where a note would be (it would hide an eye)
PREVIEW_ITEM = None               # a treasure's name, only to look at the clips (tools); None: nothing painted


def _item_centre(P, side, scale=1.0):
    tip = C.geom(P)['tipR' if side > 0 else 'tipL']
    return tip[0] + side * ITEM_OUT * scale, tip[1] - ITEM_UP * scale


def _fx_item_centre(P, fx):
    """Where the find of fx ('item', side, size[, carried]) is: held up over the arm's tip, or (carried: a scale)
    carried and handed over where a note would be, so that it changes hands at one height on the screen."""
    if len(fx) <= 3: return _item_centre(P, fx[1], fx[2])
    if isinstance(fx[3], tuple): return fx[3]  # 把玩: in the air, where the pose says
    x, y = _note_centre(P, fx[1], fx[3])
    out = fx[4] if len(fx) > 4 else 0.0        # 0..1: away from the face (it is bigger than a note), not at the hand-over
    return x + fx[1] * BRING_OUT[0] * out, y - BRING_OUT[1] * out


def dig_body(u, gusto=False):
    """Crouched over the hole, the two arms scrabbling in turn; once a loop a clod hits its face: eyes squeezed
    shut, a small jerk back.  Periodic in RUMMAGE_LEN.  gusto: faster and wider (frame 0 is the same pose)."""
    P = make_pose(); w = math.sin(TWO_PI * u / (DIG_STROKE_FAST if gusto else DIG_STROKE))
    k = 1.35 if gusto else 1.0
    P['legx'] = DIG_LEGX
    P['sy'] *= 0.93 * (1 + 0.035 * k * abs(w)); P['sx'] *= 1.025 * (1 - 0.012 * k * abs(w))
    P['tilt'] += 3.4 * k * w
    ang, swing, ext = DIG_ARM
    P['nubR'] = (ang + swing * k * w, ext); P['nubL'] = (ang - swing * k * w, ext)
    P['look'] = (0.3 * w, 0.92)
    c = u % RUMMAGE_LEN
    if SPLAT_AT <= c < SPLAT_AT + SPLAT_LEN:
        P['eyes'] = 'squeeze'
        j = bump(c, SPLAT_AT, SPLAT_AT + SPLAT_LEN)
        P['sy'] *= 1 + 0.04 * j; P['sx'] *= 1 - 0.02 * j; P['lift'] += 5.0 * j
    return P


def rummage_pose(u, T=RUMMAGE_LEN, gusto=False):
    if gusto:
        P = dig_body(u, True)
        if P['eyes'] != 'squeeze': P['eyes'] = 'happy'         # it likes the help
        return P, [('pit', u, 1.0, 1.0, DIG_STROKE_FAST), ('dirt', u, 1.0, 0.0)]
    return dig_body(u), [('pit', u, 1.0, 1.0), ('dirt', u, 1.0, 0.0)]


def rummage_spur_pose(u, D=RUMMAGE_SPUR_LEN):
    """A click while it digs: it starts, looks up, throws both arms up, and goes down to dig twice as hard.  First
    and last frame: frame 0 of rummage (and of rummage_fast)."""
    P = dig_body(0.0)
    up = bump(u, 0.0, D)
    P['lift'] += 20.0 * bump(u, 0.04, 0.34)
    P['sy'] *= 1 + 0.05 * up; P['sx'] *= 1 - 0.025 * up
    for key in ('nubL', 'nubR'):
        a, x = P[key]; P[key] = (lerp(a, 40.0, up), lerp(x, 1.15, up))
    P['look'] = (0.0, lerp(0.92, -0.3, up))
    if 0.02 < u < D - 0.04: P['eyes'] = 'wide' if u < 0.16 else 'happy'
    return P, [('pit', 0.0, 1.0, 0.0), ('dirt', 0.0, 1.0, 0.0), ('twinkle', u - 0.1, (P['x'], C.geom(P)['top'] - 30.0), 1.2)]


def rummage_in_pose(u, D=RUMMAGE_IN_LEN):
    """Looks down at the ground, a small start, down into the crouch, the first earth flies and the first of it
    lands on its face; the last frame is frame 0 of rummage."""
    A = make_pose(); B = dig_body(u - D)
    A['look'] = (0.0, 0.92 * smooth(u / 0.22))
    A['sy'] *= 1 + 0.03 * bump(u, 0.1, 0.4); A['sx'] *= 1 - 0.015 * bump(u, 0.1, 0.4)
    e = smooth((u - 0.26) / 0.34)
    P = blend_pose(A, B, e)
    return P, [('pit', u - D, smooth((u - 0.4) / 0.3), smooth((u - 0.5) / 0.2)), ('dirt', u - D, clamp((u - 0.5) / 0.28, 0.0, 1.0), 0.0)]


def _stand_up(u, t0, t1):
    """from the crouch (frame 0 of rummage) up to the plain pose between t0 and t1, with a small stretch at the top."""
    e = smooth((u - t0) / (t1 - t0))
    P = blend_pose(dig_body(0.0), make_pose(), e)
    st = bump(u, t0 + 0.6 * (t1 - t0), t1 + 0.25)
    P['sy'] *= 1 + 0.03 * st; P['sx'] *= 1 - 0.015 * st
    P['eye_open'] = 1.0; P['eyes'] = 'open'
    return P, e


def _shake(P, u, t0):
    """Shakes itself like a wet dog from t0 for SHAKE_LEN: quick rocking, eyes squeezed shut.  -> how far the
    shake has got (0..1): the earth on it is thrown off with it."""
    v = (u - t0) / SHAKE_LEN
    if 0.0 < v < 1.0:
        env = math.sin(math.pi * v) ** 0.6
        q = math.sin(TWO_PI * (u - t0) / 0.112)
        P['tilt'] += 7.5 * q * env
        P['sx'] *= 1 + 0.035 * abs(q) * env; P['sy'] *= 1 - 0.03 * abs(q) * env
        for key, sgn in (('nubL', 1), ('nubR', -1)):
            a, x = P[key]; P[key] = (a + (18 + 14 * q * sgn) * env, x)
        P['eyes'] = 'squeeze'
    return clamp(v, 0.0, 1.0)


def _hold_up(P, u, t_up, t_show, t_away, t_end, hop=22.0, pop_from=None, star=0.0):
    """The right arm up with a find from t_up to t_show, a hop and happy eyes (stars in them for `star` seconds
    first), put away from t_away to t_end.  -> the find's size at u (0: not there)."""
    rest = make_pose()['nubR']
    a0, x0 = P['nubR']
    up = smooth((u - t_up) / (t_show - t_up)); away = smooth((u - t_away) / (t_end - t_away))
    w = up * (1.0 - away)
    P['nubR'] = (lerp(lerp(a0, ITEM_ARM[0], up), rest[0], away), lerp(lerp(x0, ITEM_ARM[1], up), rest[1], away))
    P['lift'] += hop * bump(u, t_show - 0.02, t_show + 0.34)
    k = bump(u, t_show - 0.14, t_show) + bump(u, t_show + 0.32, t_show + 0.5)
    P['sy'] *= 1 - 0.045 * k; P['sx'] *= 1 + 0.022 * k
    P['look'] = (lerp(P['look'][0], 0.8, w), lerp(P['look'][1], -0.5, w))
    if t_show - 0.02 < u < t_away + 0.12: P['eyes'] = 'star' if u < t_show + star else 'happy'
    P['blush'] = 0.7 * bump(u, t_show - 0.1, t_end)
    t_pop = t_up if pop_from is None else pop_from
    pop = clamp((u - t_pop) / 0.22, 0.0, 1.0)
    size = (ease_out_back(pop, 2.0) if pop < 1.0 else 1.0) * (1.0 - smooth((u - t_away - 0.04) / (t_end - t_away - 0.1)))
    return size if u > t_pop else 0.0


def _held_point(t):
    """Where a find is while held up in the plain pose (the twinkle and the rays are there)."""
    P = make_pose(); P['nubR'] = ITEM_ARM
    return _item_centre(P, 1)


def rummage_found_pose(u, D=RUMMAGE_FOUND_LEN):
    """Something is there: stops short with wide eyes, stands up, shakes the earth off, reaches down into the hole
    and comes up with the find, stars in its eyes and a happy hop; a look at it, and it is put away.  The hole
    closes.  First frame: frame 0 of rummage, last: the plain pose."""
    P, e = _stand_up(u, 0.24, 0.62)
    if u < 0.3: P['eyes'] = 'wide'
    sh = _shake(P, u, 0.62)
    dip = smooth((u - 1.18) / 0.26) * (1.0 - smooth((u - 1.52) / 0.3))          # the right arm down into the hole
    a, x = P['nubR']; P['nubR'] = (lerp(a, -84.0, dip), lerp(x, 1.3, dip))
    P['tilt'] -= 4.5 * dip; P['sy'] *= 1 - 0.035 * dip
    P['look'] = (lerp(P['look'][0], 0.55, dip), lerp(P['look'][1], 0.85, dip))
    size = _hold_up(P, u, 1.5, 1.92, 2.56, 3.0, pop_from=1.56, star=0.42)
    fxs = [('pit', 0.0, 1.0 - smooth((u - 1.9) / 0.6), 0.0), ('dirt', 0.0, 1.0, sh)]
    if u < 0.4: fxs.append(('exclaim', u, 0.4))
    if size > 0.01: fxs.append(('item', 1, size))
    fxs.append(('twinkle', u - 1.92, _held_point(u), 1.3))
    return P, fxs


def rummage_up_pose(u, D=RUMMAGE_UP_LEN):
    """Called away while it digs (the player: something of a higher rank wants it): up out of the crouch at once,
    the earth drops off it, the hole closes.  First frame: frame 0 of rummage, last: the plain pose."""
    P, e = _stand_up(u, 0.0, 0.36)
    return P, [('pit', 0.0, 1.0 - smooth(u / 0.4), 0.0), ('dirt', 0.0, 1.0, clamp(u / 0.4, 0.0, 1.0))]


def rummage_none_pose(u, D=RUMMAGE_NONE_LEN):
    """Nothing this time.  It peers into the hole, one side and the other; stands up and shakes the earth off;
    holds up its two empty arms and looks from one to the other; and then it sinks: the arms drop, the eyes go
    sad, the whole body sags and leans, dark lines hang over its head, a long sigh.  It scuffs once at the ground,
    takes a breath and is itself again.  The hole closes.  Ends in the plain pose."""
    P, e = _stand_up(u, 0.52, 0.9)
    peer = smooth(u / 0.12) * (1.0 - smooth((u - 0.46) / 0.14))
    P['look'] = (lerp(P['look'][0], -0.8 if u < 0.27 else 0.8, peer), P['look'][1])
    P['tilt'] += (2.5 if u < 0.27 else -2.5) * peer
    sh = _shake(P, u, 0.9)
    show = smooth((u - 1.5) / 0.16) * (1.0 - smooth((u - 2.05) / 0.2))          # both arms up, empty: a look at each
    for key in ('nubL', 'nubR'):
        a, x = P[key]; P[key] = (lerp(a, 44.0, show), lerp(x, 1.1, show))
    if show > 0.02:
        P['look'] = (lerp(P['look'][0], -0.85 if u < 1.82 else 0.85, show), lerp(P['look'][1], -0.2, show))
    sad = smooth((u - 2.1) / 0.45) * (1.0 - smooth((u - 3.75) / 0.4))
    sigh = bump(u, 2.75, 3.5)
    sway = math.sin(TWO_PI * (u - 2.1) / 1.5) * sad
    P['legx'] = lerp(P['legx'], -14.0, sad)
    P['sy'] *= 1 - 0.075 * sad + 0.03 * bump(u, 2.55, 2.85) - 0.03 * sigh; P['sx'] *= 1 + 0.035 * sad
    P['tilt'] += (3.0 + 1.6 * sway) * sad
    for key in ('nubL', 'nubR'):
        a, x = P[key]; P[key] = (lerp(a, -52.0 + 3 * sway, sad), lerp(x, 0.9, sad))
    P['look'] = (lerp(P['look'][0], -0.2, sad), lerp(P['look'][1], 0.95, sad))
    if 2.2 < u < 3.85:
        P['eyes'] = 'sad'
        b = (u - 3.05) / 0.2
        if 0.0 <= b <= 1.0: P['eyes'] = 'flat'                  # a slow blink in the middle of it
    scuff = bump(u, 3.5, 3.8)                                   # one small scuff at the ground, then up
    P['tilt'] -= 2.0 * scuff
    up = bump(u, 3.85, 4.3)
    P['sy'] *= 1 + 0.035 * up; P['sx'] *= 1 - 0.018 * up
    g = C.geom(P)
    fxs = [('pit', 0.0, 1.0 - smooth((u - 3.3) / 0.6), 0.0), ('dirt', 0.0, 1.0, sh),
           ('gloom', (g['x'] + 0.2 * g['bw'], g['top']), sad * (1.0 - smooth((u - 3.5) / 0.3)), u),
           ('puff', u - 2.9, (g['x'] + 0.5 * g['bw'] + 52.0, g['cy'] + 0.22 * g['bh'])),
           ('puff', u - 3.6, (g['x'] - 0.3 * g['bw'], FLOOR_Y - 16.0))]
    return P, fxs


def draw_gloom(fr, sc, origin, a, u):
    """The dark lines that hang over a head when the heart sinks: five of them, uneven, swaying a little."""
    if a <= 0.01: return
    ox, oy = origin
    def paint(d, X, Y, k):
        for i in range(5):
            x = ox + 26 * i + 3 * math.sin(1.7 * u + i)
            L = (36, 58, 44, 64, 40)[i] * (0.5 + 0.5 * a)
            y0 = oy - 44 + 6 * (i % 2)
            d.line((X(x), Y(y0), X(x + 2), Y(y0 + L)), fill=(92, 104, 140, 255), width=max(1, int(round(5.0 * k))))
    draw_prop_layer(fr, sc, ox - 20, oy - 60, ox + 140, oy + 40, 0.85 * a, paint)


BEHIND_ARM = (-152.0, 1.0)        # pull_out: the right arm behind the back (drawn behind the body: it cannot be seen)


def pull_out_pose(u, D=PULL_OUT_LEN):
    """The big one finds something by itself: the right arm goes behind its back, it feels about with its eyes up
    and to the side, a start, and out comes a find held high with rays behind it; a hop, and it is put away."""
    P = make_pose(); rest = P['nubR']
    back = smooth(u / 0.4) * (1.0 - smooth((u - 1.34) / 0.3))
    P['nubR'] = (lerp(rest[0], BEHIND_ARM[0], back), lerp(rest[1], BEHIND_ARM[1], back))
    feel = smooth((u - 0.3) / 0.2) * (1.0 - smooth((u - 1.25) / 0.12))
    w = math.sin(TWO_PI * (u - 0.4) / 0.36)
    P['tilt'] += (2.0 + 1.8 * w) * feel
    P['sy'] *= 1 - 0.02 * feel * (0.5 + 0.5 * w); P['sx'] *= 1 + 0.01 * feel
    P['look'] = (-0.55 * feel, -0.7 * feel)
    a, x = P['nubL']; P['nubL'] = (a + 10 * feel, x)
    if 1.24 < u < 1.5: P['eyes'] = 'wide'
    size = _hold_up(P, u, 1.34, 1.78, 2.62, 3.1, pop_from=1.5)
    fxs = []
    if 1.2 < u < 1.6: fxs.append(('exclaim', u - 1.2, 0.4))
    if size > 0.01: fxs.append(('item', 1, size))
    fxs.append(('twinkle', u - 1.78, _held_point(u), 1.3))
    return P, fxs


def present_pose(u, D=PRESENT_LEN):
    """Holds a find up from the plain pose to show it: rays behind it, a hop, happy eyes; then it is put away."""
    P = make_pose()
    size = _hold_up(P, u, 0.0, 0.42, 1.86, 2.34, pop_from=0.12)
    fxs = [('item', 1, size)] if size > 0.01 else []
    fxs.append(('twinkle', u - 0.42, _held_point(u), 1.3))
    return P, fxs


# ---- 把玩 (养成第 7 轮): a treasure from the collection is taken out from behind the back, played with, and put
# back.  The treasure is drawn into the frames (one clip play_<treasure> each): the arm's tip holds it (drawn again
# over it), it is behind the body while the arm is behind the back, it turns with the hand and spins in the air, and
# its size is the pet's.  Four ways for now (PLAY_WAY); a treasure may get a way of its own later under the same
# name.  First and last frame: the plain pose.
PLAY_OUT = 0.75                   # out from behind the back with it (in the hand from PLAY_GRAB, behind the body until clear)
PLAY_GRAB = 0.3
PLAY_AWAY = 0.62                  # back behind the back with it (gone at the end of that), and the arm down at the side
HELD_UP, HELD_OUT = 34.0, 8.0     # a treasure in the hand: its centre from the arm's tip (the tip holds its lower edge)
HELD_BOX = 0.92                   # of ITEM_BOX: in the hand it is a little smaller than held up high to show
HELD_RIM = True                   # the icon's dark rim (as everywhere else they are seen)
PLAY_GLOW = 0.55                  # the rarity's glow behind it while it is played with (dimmer than at a find)
LOOK_ARM, TOSS_ARM, LISTEN_ARM, SHOW_ARM = (36.0, 1.12), (22.0, 1.08), (76.0, 0.94), (66.0, 1.22)
TOSS_THROWS = ((0.42, 0.62, 110.0, 1), (1.36, 0.92, 240.0, 2))   # (release, time in the air, height, turns) after PLAY_OUT


def _play_arm(P, u, D, hold):
    """The right arm: behind the back (empty), the treasure taken there, out to `hold` (pose offsets already in
    P['nubR'] are kept), and at the end behind the back again, where it is let go, and down at the side.
    -> (in the hand, behind the body)."""
    rest = make_pose()['nubR']
    a_back = smooth(u / PLAY_GRAB)
    a_out = smooth((u - PLAY_GRAB) / (PLAY_OUT - PLAY_GRAB))
    b_back = smooth((u - (D - PLAY_AWAY)) / 0.3)
    b_down = smooth((u - (D - PLAY_AWAY + 0.3)) / (PLAY_AWAY - 0.3))
    if u < D - PLAY_AWAY:
        a0, x0 = P['nubR']
        ang = lerp(lerp(rest[0], BEHIND_ARM[0], a_back), hold[0] + (a0 - rest[0]), a_out)
        ext = lerp(lerp(rest[1], BEHIND_ARM[1], a_back), hold[1] + (x0 - rest[1]), a_out)
    else:
        ang = lerp(lerp(hold[0], BEHIND_ARM[0], b_back), rest[0], b_down)
        ext = lerp(lerp(hold[1], BEHIND_ARM[1], b_back), rest[1], b_down)
    P['nubR'] = (ang, ext)
    if 0.1 < u < PLAY_GRAB + 0.12:                             # feeling about behind its back
        f = bump(u, 0.1, PLAY_GRAB + 0.12)
        P['look'] = (lerp(P['look'][0], -0.5, f), lerp(P['look'][1], -0.6, f)); P['tilt'] += 2.0 * f
    swing = u < PLAY_OUT or u >= D - PLAY_AWAY                 # coming out from behind the back, or going back there:
    return PLAY_GRAB <= u < D - 0.3, ang < -95.0 or (swing and ang < -30.0)   # behind the body till it is clear of it


def _play_glow(u, D):
    return PLAY_GLOW * smooth((u - PLAY_OUT + 0.15) / 0.3) * (1.0 - smooth((u - (D - PLAY_AWAY)) / 0.2))


def _held(item, P, u, D, state, rot=0.0, at=None, k=1.0, squash=(1.0, 1.0), grip=None, off=(0.0, 0.0), glow=1.0,
          t_item=None, u_loop=None):
    """The fx of a treasure in the hand (at=None) or in the air (at: its centre), turned by rot (degrees, against
    the clock) besides the hand's own turn, k: its size."""
    inhand, behind = state
    if not inhand: return []
    hand = P['tilt'] + 0.45 * (P['nubR'][0] - 40.0) if at is None else 0.0
    c = at if at is not None else (lambda t: (t[0] + HELD_OUT + off[0], t[1] - HELD_UP + off[1]))(C.geom(P)['tipR'])
    return [('held', item, c, rot + hand, k, behind and at is None, at is None if grip is None else grip, glow * _play_glow(u, D),
             u if u_loop is None else u_loop, squash, t_item)]


def _nod(P, v, t0, n=2, period=0.36, depth=0.035):
    """n small nods from t0 (a squash of the body each)."""
    if t0 < v < t0 + n * period:
        w = max(0.0, math.sin(TWO_PI * (v - t0) / period))
        P['sy'] *= 1 - depth * w; P['sx'] *= 1 + 0.5 * depth * w


def play_look_pose(u, D, item=None):
    """细看: holds it out to the side and looks at it closely, leaning in, turning it this way and that; brings it
    nearer and squints; a start (it has seen something!), then happy: two nods, a blush, a heart; a little wiggle."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    lean = smooth(v / 0.4) * (1.0 - smooth((v - 1.9) / 0.3))
    turn = math.sin(TWO_PI * (v - 0.3) / 0.8) * bump(v, 0.3, 1.5)
    close = bump(v, 1.4, 2.0)                                  # nearer, squinting
    a, x = P['nubR']; P['nubR'] = (a + 6.0 * turn + 14.0 * close - 4.0 * lean, x - 0.06 * lean - 0.1 * close)
    P['tilt'] -= 5.5 * lean + 2.5 * close
    P['look'] = (lerp(0.0, 0.95, smooth(v / 0.3)), lerp(0.0, -0.4, smooth(v / 0.3)) + 0.12 * turn)
    if 0.0 < v < 1.45: P['eyes'] = 'wide' if v < 0.3 else 'open'
    if 1.45 <= v < 1.95: P['eyes'] = 'half'
    aha = bump(v, 1.95, 2.25)
    P['lift'] += 14.0 * aha
    P['sy'] *= 1 + 0.04 * aha; P['sx'] *= 1 - 0.02 * aha
    if 1.95 <= v < 2.2: P['eyes'] = 'wide'
    _nod(P, v, 2.3)
    if 2.2 <= v < mid: P['eyes'] = 'happy'; P['look'] = (0.5, -0.2)
    P['blush'] = 0.7 * bump(v, 2.1, mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    st = _play_arm(P, u, D, LOOK_ARM)
    rot = 26.0 * turn + 8.0 * math.sin(TWO_PI * (v - 2.3) / 0.36) * bump(v, 2.3, 3.0)
    fxs = _held(item, P, u, D, st, rot)
    c = C.geom(P)['tipR']
    if 0.0 <= v - 1.95 < 0.5: fxs.append(('exclaim', v - 1.95, 0.5))
    fxs.append(('heart', v - 2.35, (c[0] - 30.0, c[1] - 80.0)))
    return P, fxs


def _toss_at(v):
    """-> (throw i, f in the air 0..1) or None while it is in the hand."""
    for i, (t0, air, h, turns) in enumerate(TOSS_THROWS):
        if t0 <= v < t0 + air: return i, (v - t0) / air
    return None


def _toss_body(u, D):
    """play_toss without the treasure: the arm throws and catches, the eyes follow it up and down."""
    P = make_pose(); v = u - PLAY_OUT
    look_up = 0.0
    for i, (t0, air, h, turns) in enumerate(TOSS_THROWS):
        wind = bump(v, t0 - 0.26, t0 + 0.02)                  # down a little first
        a, x = P['nubR']; P['nubR'] = (a - 26.0 * wind, x)
        P['sy'] *= 1 - 0.045 * wind; P['sx'] *= 1 + 0.022 * wind
        throw = bump(v, t0 - 0.02, t0 + 0.3)                   # up it goes
        a, x = P['nubR']; P['nubR'] = (a + (40.0 + 14.0 * i) * throw, x + 0.1 * throw)
        P['lift'] += (5.0 + 9.0 * i) * throw
        f = (v - t0) / air
        if 0.0 < f < 1.0: look_up = max(look_up, math.sin(math.pi * f) * (0.7 + 0.3 * i))
        catch = bump(v, t0 + air - 0.03, t0 + air + 0.28)      # it lands in the hand: down with it
        a, x = P['nubR']; P['nubR'] = (a - 20.0 * catch, x)
        P['sy'] *= 1 - 0.05 * catch; P['sx'] *= 1 + 0.025 * catch
        if 0.0 < f < 1.0: P['eyes'] = 'wide' if i == 1 and f > 0.55 else 'open'
    P['look'] = (0.55 - 0.3 * look_up, 0.3 - 1.1 * look_up)
    t_end = TOSS_THROWS[-1][0] + TOSS_THROWS[-1][1]
    if t_end + 0.05 < v: P['eyes'] = 'happy'; P['lift'] += 18.0 * bump(v, t_end + 0.1, t_end + 0.44)
    P['blush'] = 0.6 * bump(v, t_end, D - PLAY_OUT)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    return P, _play_arm(P, u, D, TOSS_ARM)


def _hand_point(P):
    t = C.geom(P)['tipR']; return t[0] + HELD_OUT, t[1] - HELD_UP


def play_toss_pose(u, D, item=None):
    """抛接: throws it up and catches it, twice: a small one, then high, turning over and over (wide eyes: will it
    come down?); caught with a dip; a happy hop."""
    P, st = _toss_body(u, D)
    v = u - PLAY_OUT
    air = _toss_at(v)
    if air is None:
        land = max([bump(v, t0 + a - 0.03, t0 + a + 0.2) for t0, a, h, n in TOSS_THROWS])
        fxs = _held(item, P, u, D, st, -10.0 * land)
    else:
        i, f = air
        t0, a, h, turns = TOSS_THROWS[i]
        x0, y0 = _hand_point(_toss_body(t0 + PLAY_OUT, D)[0])
        x1, y1 = _hand_point(P)
        at = (lerp(x0, x1, f) + 14.0 * math.sin(math.pi * f), lerp(y0, y1, f) - 4.0 * h * f * (1.0 - f))
        fxs = _held(item, P, u, D, st, -360.0 * turns * smooth(f), at)
    c = _hand_point(P)
    for t0, a, h, n in TOSS_THROWS:
        fxs.append(('twinkle', v - t0 - a, c, 0.7))
    return P, fxs


def draw_hum(fr, sc, t, origin, alpha):
    """Something to hear: small arcs going out from a point (the treasure at its ear), one after another."""
    if alpha <= 0.01: return
    ox, oy = origin
    def paint(d, X, Y, k):
        for i in range(3):
            ph = (t * 0.8 + i / 3.0) % 1.0; r = 30 + 40 * ph; a = int(230 * (1 - ph) * min(1.0, ph * 5))
            d.arc((X(ox - r), Y(oy - r), X(ox + r), Y(oy + r)), -50, 40, fill=(92, 150, 214, a), width=int(max(1, 6 * k)))
    draw_prop_layer(fr, sc, ox - 10, oy - 80, ox + 90, oy + 80, alpha, paint)


def play_listen_pose(u, D, item=None):
    """听一听: holds it up beside its head and gives it a good shake, then holds still, eyes shut, rocking slowly
    with what it hears; a little start (there it is!), opens its eyes happy and nods along."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    sh = bump(v, 0.1, 0.8)
    shake = sh * math.sin(TWO_PI * v / 0.11)
    a, x = P['nubR']; P['nubR'] = (a + 7.0 * shake, x)
    P['tilt'] += 1.5 * shake
    if 0.05 < v < 0.85: P['eyes'] = 'squeeze' if sh > 0.6 else 'wide'; P['look'] = (0.9, -0.3)
    hear = smooth((v - 0.9) / 0.3) * (1.0 - smooth((v - 2.5) / 0.25))
    P['tilt'] -= 4.0 * hear * (0.6 + 0.4 * math.sin(TWO_PI * (v - 0.9) / 1.2))
    if 0.95 < v < 2.2: P['eyes'] = 'closed'
    perk = bump(v, 2.2, 2.5)                                   # there it is!
    P['lift'] += 10.0 * perk
    if 2.2 <= v < 2.5: P['eyes'] = 'wide'
    if 2.5 <= v < mid: P['eyes'] = 'happy'
    _nod(P, v, 2.55, 2, 0.34)
    P['blush'] = 0.6 * bump(v, 1.0, mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    st = _play_arm(P, u, D, LISTEN_ARM)
    fxs = _held(item, P, u, D, st, 18.0 * shake - 6.0 * hear)
    c = _hand_point(P)
    fxs.append(('hum', v - 0.9, (c[0] + 34.0, c[1]), min(1.0, hear + 0.6 * bump(v, 2.2, 2.9))))
    return P, fxs


def play_show_pose(u, D, item=None):
    """举高: holds it up high like a cup, the other arm at its side as in proud; sways left and right with it, stars
    in its eyes, then happy; sparkles at the treasure."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    hip = smooth(v / 0.3) * (1.0 - smooth((v - mid + 0.3) / 0.3))
    a, x = P['nubL']; P['nubL'] = (lerp(a, -32.0, hip), lerp(x, 0.72, hip))
    P['sy'] *= 1 + 0.035 * hip; P['sx'] *= 1 - 0.018 * hip
    P['lift'] += 20.0 * bump(v, 0.0, 0.34)
    sway = math.sin(TWO_PI * (v - 0.35) / 1.0) * bump(v, 0.35, 2.4)
    P['tilt'] += 5.0 * sway
    a, x = P['nubR']; P['nubR'] = (a - 4.0 * sway, x)
    if 0.0 < v < mid: P['eyes'] = 'star' if v < 0.8 else 'happy'
    P['look'] = (0.6 * hip, -0.5 * hip)
    P['blush'] = 0.7 * bump(v, 0.0, mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    st = _play_arm(P, u, D, SHOW_ARM)
    fxs = _held(item, P, u, D, st, -6.0 * sway)
    c = _hand_point(P)
    for t in (0.05, 0.85, 1.65):
        fxs.append(('twinkle', v - t, c, 1.3))
    return P, fxs


def draw_squeak(fr, sc, t, origin, size=1.0):
    """A squeak: three short strokes bursting out of a point, and a little note going up; t: time since it."""
    if t < 0 or t >= 0.55: return
    f = t / 0.55; ox, oy = origin; a = clamp((1.0 - f) / 0.5, 0.0, 1.0)
    def paint(d, X, Y, k):
        w = int(max(1, 5.5 * k * size))
        for ang in (-40.0, 0.0, 40.0):
            q = math.radians(ang); r0 = (14 + 26 * ease_out(f)) * size; r1 = r0 + 22 * size * (1.0 - 0.5 * f)
            d.line((X(ox + r0 * math.sin(q)), Y(oy - r0 * math.cos(q)), X(ox + r1 * math.sin(q)), Y(oy - r1 * math.cos(q))),
                   fill=(255, 196, 60, 255), width=w)
        nx, ny = ox + 34 * size, oy - (30 + 46 * ease_out(f)) * size           # a quaver
        r = 9.0 * size
        d.ellipse((X(nx - r), Y(ny - 0.75 * r), X(nx + r), Y(ny + 0.75 * r)), fill=(108, 112, 150, 255))
        d.line((X(nx + 0.8 * r), Y(ny), X(nx + 0.8 * r), Y(ny - 3.2 * r)), fill=(108, 112, 150, 255), width=w)
        d.line((X(nx + 0.8 * r), Y(ny - 3.2 * r), X(nx + 2.0 * r), Y(ny - 2.3 * r)), fill=(108, 112, 150, 255), width=w)
    draw_prop_layer(fr, sc, ox - 60 * size, oy - 120 * size, ox + 80 * size, oy + 10 * size, a, paint)


# On the floor: the arms are short (the tip does not get near the floor standing), so a treasure is let go low and
# drops to its feet, and to press it from above it crouches a little; the tip is put exactly on its top (_reach).
FLOOR_EXT = 1.28                  # the arm as long as it gets for that
ITEM_TOP, ITEM_BOT = 0.36, 0.43   # of the treasure's box: its top and its bottom from its centre (the duck; measured)


def _tip_at(P, a, ext):
    return C.geom(dict(P, nubR=(a, ext)))['tipR']


def _reach(P, y, ext=FLOOR_EXT):
    """-> the right arm's angle that puts its tip at height y (logical; the tip goes down as the angle does)."""
    lo, hi = -85.0, 40.0
    for _ in range(22):
        m = (lo + hi) / 2.0
        if _tip_at(P, m, ext)[1] < y: hi = m
        else: lo = m
    return (lo + hi) / 2.0


def _floor_spot():
    """Where a treasure put down at its feet stands: its centre, so that a little crouch reaches its top."""
    B = ITEM_BOX * HELD_BOX
    cy = FLOOR_Y - ITEM_BOT * B
    P = make_pose(); P['legx'] = -12.0
    a = _reach(P, cy - ITEM_TOP * B)
    return _tip_at(P, a, FLOOR_EXT)[0], cy


def _floor_top(cy, sqy):
    """The top of a treasure on the floor, squashed to sqy from its box's bottom."""
    B = ITEM_BOX * HELD_BOX
    return cy + B / 2.0 - sqy * (B / 2.0 + ITEM_TOP * B)


# 橡皮鸭: (contact, how hard, down in, up in); the last one picks it up
DUCK_PRESSES = ((0.95, 1.0, 0.12, 0.1), (2.35, 0.45, 0.35, 0.25), (2.95, 0.8, 0.1, 0.1), (3.19, 0.8, 0.1, 0.1), (3.43, 0.9, 0.1, 0.14))
DUCK_DROP = (0.5, 0.7)            # let go, on the floor
DUCK_PICK = (3.8, 4.05)           # the tip down to it, up with it in the hand
DUCK_CARRY = (-22.0, 1.15)        # the arm with the duck in it, low at the side


def _duck_press(v):
    """-> (how far down the arm is 0..1, how flat the duck is 0..1, crouch 0..1)."""
    w = q = 0.0
    for tc, hard, dn, up in DUCK_PRESSES:
        if tc - dn <= v < tc: w = max(w, smooth((v - (tc - dn)) / dn))
        elif tc <= v < tc + 0.16: w = 1.0; q = max(q, hard * bump(v, tc, tc + 0.16))
        elif tc + 0.16 <= v < tc + 0.16 + up: w = max(w, 1.0 - smooth((v - tc - 0.16) / up))
    t0, t1 = DUCK_PICK
    if t0 - 0.22 <= v < t0: w = max(w, smooth((v - t0 + 0.22) / 0.22))
    return w, q


def _duck_ready(v):
    """The arm while it does not press: (angle, length)."""
    a0, a1 = DUCK_DROP
    if v < a0 - 0.32: return DUCK_CARRY
    if v < a0:
        f = smooth((v - a0 + 0.32) / 0.32); return lerp(DUCK_CARRY[0], -50.0, f), lerp(DUCK_CARRY[1], FLOOR_EXT, f)
    if v < 0.8:
        f = smooth((v - a0) / 0.3); return lerp(-50.0, -4.0, f), lerp(FLOOR_EXT, 1.2, f)
    if v < 1.07: return -4.0, 1.2
    if v < 1.95:                                               # flung up with the start, then slowly down
        f = smooth((v - 1.07) / 0.12) * (1.0 - smooth((v - 1.55) / 0.35)); return lerp(-4.0, 48.0, f), 1.2
    if v < 2.9: return -4.0, 1.2
    if v < DUCK_PICK[0]: return -16.0, 1.2
    f = smooth((v - DUCK_PICK[0]) / (DUCK_PICK[1] - DUCK_PICK[0]))
    up = bump(v, DUCK_PICK[1], DUCK_PICK[1] + 0.3)              # holds it up a little, pleased
    return lerp(-50.0, DUCK_CARRY[0], f) + 22.0 * up, lerp(FLOOR_EXT, DUCK_CARRY[1], f)


def _blink(P, v, t, length=0.12):
    if t <= v < t + length: P['eye_open'] = min(P['eye_open'], 1.0 - 0.9 * bump(v, t, t + length))


def play_duck_pose(u, D=PLAY_DUCK_LEN, item=None):
    """橡皮鸭: puts it down at its feet, crouches a little and presses it from above: SQUEAK, and it jerks back with
    its arms up, staring; creeps back, a blink, and a careful second press: a small squeak, a blink, and it is
    delighted: three quick ones, bobbing along; picks it up (the tip down to it, up it comes), holds it up a moment,
    pleased, and puts it away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    fx_, fy = _floor_spot()
    w, q = _duck_press(v)
    P['legx'] = -(12.0 + 14.0 * q) * w
    P['tilt'] -= 3.0 * w + 4.0 * bump(v, DUCK_DROP[0] - 0.35, DUCK_DROP[0] + 0.25)
    back = smooth((v - 1.07) / 0.14) * (1.0 - smooth((v - 1.6) / 0.5))                  # the start: jerks back
    P['x'] -= 26.0 * back
    P['lift'] += 9.0 * bump(v, 1.07, 1.35)
    P['sy'] *= 1 + 0.05 * bump(v, 1.07, 1.3) - 0.04 * bump(v, 1.3, 1.5)
    P['sx'] *= 1 - 0.025 * bump(v, 1.07, 1.3) + 0.02 * bump(v, 1.3, 1.5)
    a, x = P['nubL']; P['nubL'] = (a + 34.0 * smooth((v - 1.07) / 0.12) * (1.0 - smooth((v - 1.55) / 0.35)), x)
    for tc, hard, dn, up in DUCK_PRESSES[2:]:                 # bobbing along with the quick ones
        P['lift'] += 7.0 * bump(v, tc + 0.1, tc + 0.3)
    P['look'] = (0.75, 0.75) if v > 0.2 else (0.8 * smooth(v / 0.2), 0.75 * smooth(v / 0.2))
    if 1.0 <= v < 1.8: P['eyes'] = 'wide'
    _blink(P, v, 1.75)
    _blink(P, v, 2.5)
    if 2.6 <= v < mid: P['eyes'] = 'happy'
    P['blush'] = 0.8 * bump(v, 2.55, mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    ra, re = _duck_ready(max(0.0, min(v, mid)))
    sqy = 1.0 - 0.3 * q
    if w > 0.0:
        ra = lerp(ra, _reach(P, _floor_top(fy, sqy)), w); re = lerp(re, FLOOR_EXT, w)
    rest = make_pose()['nubR']
    P['nubR'] = rest                                          # _play_arm puts the arm at `hold` from the outro on
    st = _play_arm(P, u, D, (ra, re))
    squash = (1.0 + 0.2 * q, sqy)
    if v < DUCK_DROP[0] or v >= DUCK_PICK[1]:
        return P, _held(item, P, u, D, st, 0.0) + [('twinkle', v - DUCK_PICK[1], _hand_point(P), 1.0)]
    if v < DUCK_PICK[0]:                                      # let go: it drops, bounces a little, and stands
        f = clamp((v - DUCK_DROP[0]) / (DUCK_DROP[1] - DUCK_DROP[0]), 0.0, 1.0)
        rel = _hand_point(_duck_body_at(DUCK_DROP[0], D))
        at = (lerp(rel[0], fx_, f), lerp(rel[1], fy, f * f) - 9.0 * bump(v, DUCK_DROP[1], DUCK_DROP[1] + 0.16))
        rot = 10.0 * (1.0 - f) - 6.0 * bump(v, DUCK_DROP[1], DUCK_DROP[1] + 0.2)
        fxs = _held(item, P, u, D, (True, False), rot, at, squash=squash, grip=w > 0.6, glow=1.0 - smooth(f / 0.4))    # no glow on the floor
    else:                                                     # up into the hand with the arm
        f = smooth((v - DUCK_PICK[0]) / (DUCK_PICK[1] - DUCK_PICK[0]))
        hp = _hand_point(P)
        fxs = _held(item, P, u, D, (True, False), 0.0, (lerp(fx_, hp[0], f), lerp(fy, hp[1], f)), grip=True, glow=smooth((f - 0.6) / 0.4))
    for tc, hard, dn, up in DUCK_PRESSES:
        fxs.append(('squeak', v - tc, (fx_ + 20.0, _floor_top(fy, 1.0) - 6.0), 0.6 + 0.5 * hard))
    if 0.0 <= v - 1.05 < 0.75: fxs.append(('exclaim', v - 1.05, 0.75))       # the start: "!"
    return P, fxs


GOLD_SIDE, GOLD_HIGH = (36.0, 1.12), (68.0, 1.26)    # 金色分号: at its side, turned in the light; up high like a cup


def play_gold_pose(u, D=PLAY_GOLD_LEN, item=None):
    """金色分号: like a prize.  Holds it at its side and turns it this way and that in the light: a glint, stars in its
    eyes; then up high like a cup, a hop, the other arm at its side as in proud; rays behind it, it puffs up with
    its eyes shut, pleased, rocking a little; sparkles on it; down to its side again, a nod, and away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    up = smooth((v - 1.1) / 0.35) * (1.0 - smooth((v - 2.55) / 0.35))
    ang = lerp(GOLD_SIDE[0], GOLD_HIGH[0], up); ext = lerp(GOLD_SIDE[1], GOLD_HIGH[1], up)
    turn = math.sin(TWO_PI * (v - 0.3) / 0.8) * bump(v, 0.3, 1.1)
    ang += 5.0 * turn
    P['look'] = (lerp(0.0, 0.9, smooth(v / 0.3)) * (1.0 - 0.4 * up), lerp(0.0, -0.4, smooth(v / 0.3)) - 0.3 * up)
    if 0.0 < v < 0.62: P['eyes'] = 'open'
    if 0.62 <= v < 1.1: P['eyes'] = 'star'                     # the glint
    P['lift'] += 22.0 * bump(v, 1.2, 1.55)
    hip = smooth((v - 1.2) / 0.3) * (1.0 - smooth((v - 2.55) / 0.3))
    a, x = P['nubL']; P['nubL'] = (lerp(a, -32.0, hip), lerp(x, 0.72, hip))
    puff = smooth((v - 1.45) / 0.3) * (1.0 - smooth((v - 2.5) / 0.3))
    bob = math.sin(TWO_PI * (v - 1.6) / 0.9) * puff
    P['sy'] *= 1 + 0.04 * puff + 0.01 * bob; P['sx'] *= 1 - 0.02 * puff
    P['tilt'] += 2.5 * bob
    if 1.1 <= v < 1.5: P['eyes'] = 'happy'
    _blink(P, v, 1.48)
    if 1.55 <= v < 2.55: P['eyes'] = 'closed'
    if 2.55 <= v < mid: P['eyes'] = 'happy'
    _nod(P, v, 2.75, 1, 0.34)
    P['blush'] = 0.7 * bump(v, 1.3, mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ang, ext))
    fxs = _held(item, P, u, D, st, 20.0 * turn - 3.0 * bob, off=(24.0 * up, 4.0 * up))     # up high: out past the head's corner
    c = _hand_point(P); c = (c[0] + 24.0 * up, c[1] + 4.0 * up)
    fxs.append(('rays', v - 1.35, c, 1.1))
    fxs.append(('twinkle', v - 0.62, c, 1.1))
    for t in (1.7, 2.2):
        fxs.append(('spark', v - t, (c[0], c[1] - 30.0), 1.0))
    return P, fxs


def draw_drop(fr, sc, t, origin, alpha):
    """A drop of sweat at the top of the head (on the side away from what it holds), sliding down a little."""
    if alpha <= 0.01 or t < 0: return
    ox, oy = origin[0], origin[1] + 16.0 * min(1.0, t / 0.9)
    def paint(d, X, Y, k):
        d.polygon([(X(ox), Y(oy - 26)), (X(ox - 13), Y(oy + 4)), (X(ox + 13), Y(oy + 4))], fill=(150, 210, 255, 230))
        d.ellipse((X(ox - 13), Y(oy - 9), X(ox + 13), Y(oy + 17)), fill=(150, 210, 255, 230))
        d.ellipse((X(ox - 6), Y(oy - 2), X(ox), Y(oy + 5)), fill=(240, 250, 255, 240))
    draw_prop_layer(fr, sc, ox - 20, oy - 30, ox + 20, oy + 22, alpha, paint)


def draw_crunch(fr, sc, t, origin, crumbs=True):
    """CRUNCH: a quick burst of short strokes where it meets something hard, and (crumbs) a few crumbs falling."""
    if t < 0 or t >= 0.9: return
    ox, oy = origin
    def paint(d, X, Y, k):
        if t < 0.22:
            f = t / 0.22; a = int(255 * (1.0 - f))
            for i in range(6):
                q = math.radians(-150 + 60 * i); r0 = 14 + 22 * ease_out(f); r1 = r0 + 18 * (1.0 - f)
                d.line((X(ox + r0 * math.cos(q)), Y(oy + r0 * math.sin(q)), X(ox + r1 * math.cos(q)), Y(oy + r1 * math.sin(q))),
                       fill=(255, 206, 96, a), width=int(max(1, 6 * k)))
        for i in range(6 if crumbs else 0):                    # crumbs: little bits of biscuit, falling
            vx = (hrand('cr', i) - 0.35) * 150.0; vy = -(90.0 + 120.0 * hrand('cy', i))
            x = ox + vx * t; y = min(oy + vy * t + 0.5 * 1400.0 * t * t, FLOOR_Y - 6.0)    # they stay on the floor
            r = 4.0 + 3.0 * hrand('cs', i); a = int(255 * clamp((0.9 - t) / 0.3, 0.0, 1.0))
            d.rectangle((X(x - r), Y(y - r), X(x + r), Y(y + r)), fill=((214, 170, 104, a) if i % 2 else (186, 140, 80, a)))
    draw_prop_layer(fr, sc, ox - 120, oy - 80, ox + 160, FLOOR_Y + 10, 1.0, paint)


BISCUIT_SIDE, BISCUIT_HIGH = (34.0, 1.12), (80.0, 1.2)    # 压缩饼干: at its side; up high
BISCUIT_THROW, BISCUIT_BITE, BISCUIT_BACK = 0.5, 0.92, 1.25   # after PLAY_OUT: tossed at its face; CRUNCH; back in the hand
                                  # (the arms cannot reach its face: it is tossed there, like a treat, and bounces back)
BISCUIT_KNOCKS = (2.2, 2.55)    # ... and the two knocks on its own head


def play_biscuit_pose(u, D=PLAY_BISCUIT_LEN, item=None):
    """压缩饼干: happy (something to eat!), it tosses the biscuit up at its face, to catch it with the mouth it does not
    have, below its eyes: CRUNCH: it jars, eyes squeezed shut, crumbs fall, the biscuit is as it was and bounces back
    into its hand.  It stares at it;
    not having that, it holds it up and knocks it on the top of its own head, twice: KNOCK, KNOCK, and it is the one
    that goes dizzy (eyes going round, stars).  It shakes it off, flat eyes, a drop of sweat, a sigh, and away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    b = BISCUIT_BITE; k1, k2 = BISCUIT_KNOCKS
    t0, tb, t1 = BISCUIT_THROW, BISCUIT_BITE, BISCUIT_BACK
    wind = bump(v, t0 - 0.24, t0 + 0.02); throw = bump(v, t0 - 0.02, t0 + 0.3)
    catch = bump(v, t1 - 0.03, t1 + 0.26)
    up = smooth((v - 1.7) / 0.35) * (1.0 - smooth((v - 2.75) / 0.35))
    knock = max(bump(v, k1 - 0.1, k1 + 0.12), bump(v, k2 - 0.1, k2 + 0.12))
    ang = lerp(BISCUIT_SIDE[0] - 24.0 * wind + 40.0 * throw - 18.0 * catch, BISCUIT_HIGH[0] + 7.0 * knock, up)
    ext = lerp(BISCUIT_SIDE[1], BISCUIT_HIGH[1], up)
    P['sy'] *= 1 - 0.04 * wind - 0.04 * catch; P['sx'] *= 1 + 0.02 * wind + 0.02 * catch
    jar = bump(v, b, b + 0.45)                                 # CRUNCH: it jars, shaking
    shake = 3.0 * jar * math.sin(TWO_PI * (v - b) / 0.09)
    P['tilt'] += shake
    P['sy'] *= 1 - 0.06 * bump(v, b, b + 0.2) - 0.07 * knock; P['sx'] *= 1 + 0.03 * bump(v, b, b + 0.2) + 0.035 * knock
    dizzy = smooth((v - k2 - 0.05) / 0.15) * (1.0 - smooth((v - 3.35) / 0.2))
    P['tilt'] += 4.0 * dizzy * math.sin(TWO_PI * (v - k2) / 0.55)
    off_it = bump(v, 3.35, 3.6)                                # shakes it off
    P['tilt'] += 3.0 * off_it * math.sin(TWO_PI * (v - 3.35) / 0.08)
    P['look'] = (lerp(0.0, 0.9, smooth(v / 0.3)), lerp(0.0, -0.3, smooth(v / 0.3)))
    if 0.15 <= v < t0: P['eyes'] = 'happy'                     # something to eat!
    if t0 <= v < b:                                            # its eyes on it as it comes, then shut: here goes
        f = (v - t0) / (b - t0); P['look'] = (0.9 - 0.9 * f, -0.8 * math.sin(math.pi * min(1.0, f * 1.4)))
        if f > 0.7: P['eyes'] = 'closed'
    if t1 - 0.05 <= v < t1 + 0.1: P['look'] = (0.9, -0.2)
    if b <= v < b + 0.45: P['eyes'] = 'squeeze'
    if b + 0.45 <= v < 1.6: P['eyes'] = 'wide'; P['look'] = (0.95, -0.35)               # stares at it
    if 1.6 <= v < k2: P['look'] = (0.7, -0.9 * up)              # up at it
    if k1 - 0.02 <= v < k1 + 0.25 or k2 - 0.02 <= v < k2 + 0.1: P['eyes'] = 'squeeze'
    if k2 + 0.1 <= v < 3.4: P['eyes'] = 'spiral'; P['look'] = (0.0, 0.0)
    _blink(P, v, 3.55)
    if 3.65 <= v < mid: P['eyes'] = 'flat'
    sigh = bump(v, 3.75, mid + 0.1)                             # a quiet sigh: down it sinks
    P['sy'] *= 1 - 0.045 * sigh; P['sx'] *= 1 + 0.02 * sigh
    a, x = P['nubL']; P['nubL'] = (a - 10.0 * sigh, x)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ang - 6.0 * sigh, ext))
    g = C.geom(P)
    mouth = (g['x'], g['cy'] + 36.0)
    if t0 <= v < t1:                                            # in the air: at its face, and back
        if v < b:
            f = (v - t0) / (b - t0); a0 = _hand_point(play_biscuit_pose(t0 + PLAY_OUT - 1e-6, D)[0]); a1 = mouth; h = 110.0
            rot = -200.0 * smooth(f)
        else:
            f = (v - b) / (t1 - b); a0 = mouth; a1 = _hand_point(P); h = 50.0
            rot = -200.0 + 200.0 * smooth(f)
        at = (lerp(a0[0], a1[0], f), lerp(a0[1], a1[1], f) - 4.0 * h * f * (1.0 - f))
        fxs = _held(item, P, u, D, st, rot + 2.0 * shake, at, k=0.9)
    else:
        fxs = _held(item, P, u, D, st, -10.0 * up + 25.0 * knock, off=(8.0 * up, -6.0 * up))     # on the corner, not over the eye
    fxs.append(('crunch', v - b, (mouth[0], mouth[1] - 30.0)))
    head = (g['x'] + g['bw'] / 2.0 - 34.0, g['top'] + 4.0)
    fxs.append(('crunch', v - k1, head, False))
    fxs.append(('crunch', v - k2, head, False))
    fxs.append(('dizzy', v - k2, (g['x'], g['top'] - 58.0), dizzy))
    fxs.append(('drop', v - 3.7, (g['x'] - g['bw'] / 2.0 + 34.0, g['top'] + 20.0), bump(v, 3.65, mid + 0.25)))
    return P, fxs


PAPER_ROLL, PAPER_OPEN = (60.0, 22.0), (106.0, 80.0)   # the message: rolled up, and open in the hand (logical px)


def draw_paper(fr, sc, P, fx):
    """The message ('paper', centre, rot, open 0..1, held, behind): a roll of paper with a red band, or open, with
    lines of writing, or anything between (it unrolls and rolls up); held: the left arm's tip over its lower edge."""
    _, (cx, cy), rot, opn, held, behind = fx
    w = lerp(PAPER_ROLL[0], PAPER_OPEN[0], opn); h = lerp(PAPER_ROLL[1], PAPER_OPEN[1], opn)
    ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    pt = lambda x, y: (cx + x * ca + y * sa, cy - x * sa + y * ca)
    def paint(d, X, Y, k):
        _poly(d, X, Y, rrect_poly(cx, cy, w, h, lerp(9.0, 6.0, opn), rot), (214, 206, 186, 255))
        _poly(d, X, Y, rrect_poly(cx, cy, w - 5, h - 5, lerp(7.0, 4.0, opn), rot), (252, 249, 238, 255))
        if opn < 0.98:                                         # the band round the roll
            _poly(d, X, Y, rrect_poly(cx, cy, 7.0, h + 2.0, 2.0, rot), (214, 84, 84, int(255 * (1.0 - opn))))
        if opn > 0.3:                                          # the writing comes into view as it opens
            a = int(255 * clamp((opn - 0.3) / 0.5, 0.0, 1.0))
            for j, ln in enumerate((0.7, 0.7, 0.45)):
                y = (-0.22 + 0.22 * j) * h; x0 = -w / 2 + 12
                _poly(d, X, Y, rrect_poly(*pt(x0 + ln * (w - 24) / 2, y), ln * (w - 24), 6.0, 3.0, rot), (166, 174, 196, a))
    def tip_paint(d, X, Y, k):                                 # the left arm's tip over it, not over the body
        L = C.NUB_L * P['nubL'][1]
        _poly(d, X, Y, _arm_piece(P, 'L', L - 30, L, C.NUB_T, 12), C.NUB_COL + (255,))
        _poly(d, X, Y, _body_poly(P), (0, 0, 0, 0))
    box = (cx - w, cy - w, cx + w, cy + w)
    draw_prop_layer(fr, sc, *box, 1.0, paint)
    if held and not behind:
        tip = C.geom(P)['tipL']
        draw_prop_layer(fr, sc, *_box_around((tip,), 60), 1.0, tip_paint)


def draw_cork(fr, sc, t, origin):
    """The cork, popped: up and turning, and gone."""
    if t < 0 or t >= 0.5: return
    ox, oy = origin[0] + 40.0 * t, origin[1] - 260.0 * t + 500.0 * t * t
    a = clamp((0.5 - t) / 0.2, 0.0, 1.0)
    def paint(d, X, Y, k):
        _poly(d, X, Y, rrect_poly(ox, oy, 20.0, 13.0, 4.0, 720.0 * t), (198, 148, 98, 255))
    draw_prop_layer(fr, sc, ox - 20, oy - 20, ox + 20, oy + 20, a, paint)


BOTTLE_SIDE, BOTTLE_UP = (36.0, 1.12), (52.0, 1.18)   # 漂流瓶: at its side; up, upside down, to be shaken
BOTTLE_POP = 0.6                                      # after PLAY_OUT: the cork pops
BOTTLE_SHAKES = (1.1, 1.32, 1.54)                     # the shakes; the message slides out at the last
BOTTLE_SLIDE, BOTTLE_OUT, BOTTLE_CATCH = 1.5, 1.64, 2.0    # out of the neck bit by bit, then free; in the other hand
NOTE_ARM = (30.0, 1.2)                                # the other arm, with the message to read
BOTTLE_OPEN, BOTTLE_READ = 2.0, (2.25, 2.75)          # it unrolls in the hand; read, line by line
BOTTLE_ROLL, BOTTLE_TOSS, BOTTLE_IN = 3.1, 3.42, 3.74 # rolled up again; tossed from that hand; in at the neck
BOTTLE_MOUTH = (23.0 / 118.0, -33.0 / 118.0)          # of the box: its open neck from its centre (upright, leaning)


def _bottle_left(v, mid):
    """The left arm: up for the message, a wind-up and a toss at the end, and down at its side."""
    rest = make_pose()['nubL']
    up = smooth((v - BOTTLE_SLIDE) / 0.3)
    down = smooth((v - BOTTLE_TOSS - 0.1) / max(0.05, mid - BOTTLE_TOSS - 0.1))
    a = lerp(lerp(rest[0], NOTE_ARM[0], up), rest[0], down) - 18.0 * bump(v, BOTTLE_TOSS - 0.14, BOTTLE_TOSS + 0.02) \
        + 30.0 * bump(v, BOTTLE_TOSS - 0.02, BOTTLE_TOSS + 0.25)
    x = lerp(lerp(rest[1], NOTE_ARM[1], up), rest[1], down)
    return a, x


def _bottle_mouth(c, rot):
    """Where the open neck is, the bottle at c turned by rot (degrees against the clock)."""
    B = ITEM_BOX * HELD_BOX
    mx, my = BOTTLE_MOUTH[0] * B, BOTTLE_MOUTH[1] * B
    q = math.radians(rot)
    return c[0] + mx * math.cos(q) + my * math.sin(q), c[1] - mx * math.sin(q) + my * math.cos(q)


def play_bottle_pose(u, D=PLAY_BOTTLE_LEN, item=None):
    """漂流瓶: looks into it: something inside!  Pops the cork, turns it upside down and shakes it, once, twice, three
    times: the message slides out of the neck and drops, over to its other hand, its eyes after it; it unrolls in the
    hand.  Reads it, line by line; at the end stars in its eyes, a heart, a blush (something nice).  Rolls it up again
    and tosses it into the bottle (the arms cannot meet: the bottle is held up for it), a glint at the neck, a nod, and
    the bottle is put away with its message in it."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    peek = bump(v, 0.3, 0.85)
    flip = smooth((v - 0.8) / 0.3) * (1.0 - smooth((v - 1.75) / 0.35))       # up and upside down (the neck straight down), and back
    shake = 0.0
    for t in BOTTLE_SHAKES:
        shake += bump(v, t - 0.09, t + 0.11) * (1.0 if t < BOTTLE_SHAKES[-1] else 1.4)
    down = smooth((v - 1.95) / 0.35) * (1.0 - smooth((v - BOTTLE_ROLL) / 0.3))      # down at its side while it reads
    catch = bump(v, BOTTLE_IN - 0.02, BOTTLE_IN + 0.2)
    ang = lerp(lerp(BOTTLE_SIDE[0] + 8.0 * peek + 10.0 * bump(v, BOTTLE_POP - 0.05, BOTTLE_POP + 0.15), BOTTLE_UP[0], flip)
               - 16.0 * shake, BOTTLE_SIDE[0] - 6.0, down) - 8.0 * catch
    ext = lerp(lerp(BOTTLE_SIDE[1], BOTTLE_UP[1], flip), BOTTLE_SIDE[1], down)
    P['sy'] *= 1 - 0.03 * shake; P['sx'] *= 1 + 0.015 * shake
    P['lift'] += 6.0 * shake
    P['nubL'] = _bottle_left(v, mid)
    P['look'] = (lerp(0.0, 0.9, smooth(v / 0.3)), lerp(0.0, -0.3, smooth(v / 0.3)))
    if 0.3 <= v < 0.85: P['eyes'] = 'wide'                               # something inside!
    if BOTTLE_SLIDE <= v < BOTTLE_OUT: P['eyes'] = 'wide'; P['look'] = (0.85, 0.2)      # it is coming out!
    if BOTTLE_OUT <= v < BOTTLE_CATCH:                                    # its eyes after the message
        f = (v - BOTTLE_OUT) / (BOTTLE_CATCH - BOTTLE_OUT); P['look'] = (lerp(0.85, -0.85, smooth(f)), -0.5 * math.sin(math.pi * f))
        P['eyes'] = 'wide'
    r0, r1 = BOTTLE_READ
    if BOTTLE_CATCH <= v < r1:                                            # reading: along a line, and the next, lower
        line = (v - r0) / ((r1 - r0) / 2.0)
        f = line % 1.0 if v >= r0 else 0.0
        P['look'] = (-0.95 + 0.5 * f, -0.25 + 0.2 * min(1.0, max(0.0, math.floor(line))))
    _blink(P, v, r1 + 0.02)
    if r1 + 0.1 <= v < r1 + 0.4: P['eyes'] = 'star'
    if r1 + 0.4 <= v < mid: P['eyes'] = 'happy'
    if BOTTLE_TOSS <= v < BOTTLE_IN + 0.05:                               # its eyes after the roll, into the bottle
        f = (v - BOTTLE_TOSS) / (BOTTLE_IN - BOTTLE_TOSS); P['look'] = (lerp(-0.8, 0.8, smooth(f)), -0.4 * math.sin(math.pi * f))
    P['lift'] += 12.0 * bump(v, r1 + 0.1, r1 + 0.42)
    P['blush'] = 0.8 * bump(v, r1, mid + 0.2)
    _nod(P, v, BOTTLE_IN + 0.08, 1, 0.3)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ang, ext))
    jig = 0.0
    for t in BOTTLE_SHAKES:
        jig += 14.0 * bump(v, t - 0.09, t + 0.11) * math.sin(TWO_PI * (v - t) / 0.2)
    name = item or PREVIEW_ITEM or 'bottle'
    shape = name if v < BOTTLE_POP else (name + '_empty' if BOTTLE_SLIDE + 0.08 <= v < BOTTLE_IN else name + '_open')
    c = _hand_point(P)
    rot = 205.0 * flip + jig - 8.0 * peek                                  # the icon leans 38 degrees: 205 + the hand's turn puts the neck down
    hand_rot = rot + P['tilt'] + 0.45 * (P['nubR'][0] - 40.0)
    B = ITEM_BOX * HELD_BOX
    neck = (c[0] + 6.0, c[1] + 0.46 * B)                                  # upside down: its neck, down
    fxs = []
    held_rot = -NOTE_ROT + P['tilt']
    if BOTTLE_SLIDE <= v < BOTTLE_OUT:                                    # sliding out of the neck (the bottle over its top)
        f = smooth((v - BOTTLE_SLIDE) / (BOTTLE_OUT - BOTTLE_SLIDE))
        fxs.append(('paper', (neck[0], neck[1] - 18.0 + 30.0 * f), 90.0, 0.0, False, False))
    mouth = _bottle_mouth(c, hand_rot)
    roll_rot = 90.0 - 38.0 + hand_rot                                     # along the bottle, to go in at the neck
    if BOTTLE_IN - 0.08 <= v < BOTTLE_IN + 0.06:                          # going in: under the glass
        f = smooth((v - BOTTLE_IN + 0.08) / 0.14)
        fxs.append(('paper', (lerp(mouth[0], c[0], 0.4 * f), lerp(mouth[1], c[1], 0.4 * f)), roll_rot, 0.0, False, False))
    fxs += _held(shape, P, u, D, st, rot)
    fxs.append(('twinkle', v - 0.45, (c[0], c[1] + 6.0), 0.7))           # something glints inside
    fxs.append(('cork', v - BOTTLE_POP, _bottle_mouth(c, hand_rot)))
    if BOTTLE_OUT <= v < BOTTLE_CATCH:                                    # free: over to the other hand, turning
        f = (v - BOTTLE_OUT) / (BOTTLE_CATCH - BOTTLE_OUT)
        start = (neck[0], neck[1] + 12.0); end = _note_centre(P, -1, 0.85)
        pos = (lerp(start[0], end[0], f), lerp(start[1], end[1], f) - 4.0 * 120.0 * f * (1.0 - f))
        fxs.append(('paper', pos, lerp(90.0, 360.0 + held_rot, smooth(f)), 0.0, False, False))
    elif BOTTLE_CATCH <= v < BOTTLE_TOSS:                                 # in the hand: it opens, is read, rolls up
        opn = smooth((v - BOTTLE_OPEN) / 0.25) * (1.0 - smooth((v - BOTTLE_ROLL) / 0.22))
        fxs.append(('paper', _note_centre(P, -1, 0.85), held_rot, opn, True, False))
    elif BOTTLE_TOSS <= v < BOTTLE_IN - 0.08:                              # tossed into the bottle
        f = (v - BOTTLE_TOSS) / (BOTTLE_IN - 0.08 - BOTTLE_TOSS)
        start = _note_centre(play_bottle_pose(BOTTLE_TOSS - 1e-6 + PLAY_OUT, D)[0], -1, 0.85)
        pos = (lerp(start[0], mouth[0], f), lerp(start[1], mouth[1] - 6.0, f) - 4.0 * 150.0 * f * (1.0 - f))
        fxs.append(('paper', pos, lerp(held_rot, roll_rot + 360.0, smooth(f)), 0.0, False, False))
    fxs.append(('twinkle', v - BOTTLE_IN - 0.04, mouth, 0.9))
    fxs.append(('heart', v - r1 - 0.3, (C.geom(P)['x'], C.geom(P)['top'] - 30.0)))
    return P, fxs


def draw_pause(fr, sc, t, origin, alpha):
    """Time stands still: a pause sign over its head (two bars), popping in."""
    if alpha <= 0.01 or t < 0: return
    ox, oy = origin; k = 1.35 * (0.7 + 0.3 * ease_out_back(min(1.0, t / 0.2)))
    def paint(d, X, Y, kk):
        for s_ in (-1, 1):
            _poly(d, X, Y, rrect_poly(ox + s_ * 11.0 * k, oy, 13.0 * k, 38.0 * k, 4.0 * k), (92, 112, 150, 255))
            _poly(d, X, Y, rrect_poly(ox + s_ * 11.0 * k, oy, 7.0 * k, 32.0 * k, 3.0 * k), (150, 176, 220, 255))
    draw_prop_layer(fr, sc, ox - 40, oy - 40, ox + 40, oy + 40, alpha, paint)


def _keys(v, keys):
    """A value eased from key to key: keys ((time, (x, y)), ...) in order."""
    if v <= keys[0][0]: return keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if v < t1:
            f = smooth((v - t0) / (t1 - t0)); return lerp(a[0], b[0], f), lerp(a[1], b[1], f)
    return keys[-1][1]


HOURGLASS_ARM = (34.0, 1.12)        # 沙漏: held at its side
HG_FLIP = (0.3, 0.62)               # after PLAY_OUT: turned over to start the sand
HG_TIP, HG_HOP, HG_HANG = (1.3, 1.55), 1.8, 2.05    # turned on its side (the sand stops); a hop ... stopped on the way up
HG_BACK, HG_LAND = (2.77, 3.02), 3.22                  # upright again (the sand runs): down it drops
HG_LIFT = 60.0                      # how high it hangs
HG_RUN = (HG_FLIP[1], HG_TIP[0] + 0.12, HG_BACK[1] - 0.05)   # the sand runs from, stops at, runs again from
HG_EMPTY = 0.72                     # the icon's phase with all the sand down
HG_EYE = (0.85, -0.2)               # its eyes on the hourglass


def _hg_sand(v, mid):
    """-> the icon's phase: all down before it is turned over; running while upright; still on its side; all down
    just before the end."""
    if v < HG_FLIP[1]: return HG_EMPTY
    a, b, c = HG_RUN
    run = min(v, b) - a + max(0.0, v - c)
    total = (b - a) + (mid - 0.1 - c)
    return HG_EMPTY * clamp(run / total, 0.0, 1.0)


def _hg_hop(v):
    """-> (lift, stretch): a hop stopped on its way up (still going: stretched, rising), held there while time stands
    still, then dropped."""
    if v < HG_HOP - 0.02: return 0.0, 0.0
    if v < HG_BACK[1] + 0.02:
        f = (min(v, HG_HANG) - HG_HOP) / (HG_HANG - HG_HOP)
        return HG_LIFT * max(0.0, f) * (2.0 - 0.6 * max(0.0, f)) / 1.4, 0.06 * smooth((v - HG_HOP + 0.02) / 0.07) * (1.0 - 0.5 * max(0.0, f))
    if v < HG_LAND:
        f = (v - HG_BACK[1] - 0.02) / (HG_LAND - HG_BACK[1] - 0.02)
        return HG_LIFT * (1.0 - f * f), 0.03 * (1.0 - f)
    return 0.0, 0.0


def play_hourglass_pose(u, D=PLAY_HOURGLASS_LEN, item=None):
    """沙漏: the sand is all down: it turns it over, and the sand runs; its eyes follow it down.  It turns it on its
    side: the sand stops (time stands still?); it tries it: a hop, and it stops on the way up, stretched, in the
    air, quite still but for its eyes (down: up here!, and round); a pause sign.  It turns the hourglass up again: the sand runs,
    and down it drops, plop.  Pleased, it watches the last of the sand run down, a nod, and away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    f0, f1 = HG_FLIP
    flip = smooth((v - f0) / (f1 - f0))
    tip = smooth((v - HG_TIP[0]) / (HG_TIP[1] - HG_TIP[0])) * (1.0 - smooth((v - HG_BACK[0]) / (HG_BACK[1] - HG_BACK[0])))
    still = HG_HANG <= v < HG_BACK[1]                          # everything holds still but the eyes (and the hand at the end)
    vv = min(v, HG_HANG) if still else v
    ang = HOURGLASS_ARM[0] + 18.0 * bump(v, f0 - 0.1, f1 + 0.1) + 10.0 * tip
    wind = bump(v, HG_HOP - 0.24, HG_HOP + 0.02)               # down a little, and up
    P['sy'] *= 1 - 0.07 * wind; P['sx'] *= 1 + 0.035 * wind
    lift, stretch = _hg_hop(v)
    P['lift'] += lift
    P['sy'] *= 1 + stretch; P['sx'] *= 1 - 0.5 * stretch
    land = bump(v, HG_LAND, HG_LAND + 0.24)
    P['sy'] *= 1 - 0.09 * land; P['sx'] *= 1 + 0.045 * land
    a, x = P['nubL']; P['nubL'] = (a + 26.0 * smooth((vv - HG_HOP + 0.05) / 0.2) * (1.0 - smooth((v - HG_LAND + 0.05) / 0.3)), x)
    # its eyes: on the hourglass; following the sand down, and up again for more; round and round in the air
    eye = _keys(v, ((0.0, (0.0, 0.0)), (0.3, HG_EYE), (HG_LAND + 0.25, HG_EYE), (HG_LAND + 0.45, (0.8, -0.1))))
    follow = smooth((v - f1) / 0.15) * (1.0 - smooth((v - HG_TIP[0]) / 0.15))
    ph = ((v - f1) / 0.56) % 1.0
    g_ = smooth(ph / 0.7) if ph < 0.7 else 1.0 - smooth((ph - 0.7) / 0.3)
    eye = (eye[0], eye[1] + follow * (-0.15 + 0.45 * g_))
    if HG_HANG <= v < HG_BACK[1]:                              # in the air: down (up here!), round, back at the hourglass
        h0 = HG_HANG
        eye = _keys(v, ((h0, HG_EYE), (h0 + 0.16, (0.1, 0.85)), (h0 + 0.34, (0.1, 0.85)), (h0 + 0.52, (-0.85, -0.1)),
                        (HG_BACK[1], HG_EYE)))
    P['look'] = eye
    if HG_TIP[0] + 0.15 <= v < HG_HOP - 0.1: P['eyes'] = 'wide'                   # it has stopped!
    if HG_BACK[1] <= v < HG_LAND: P['eyes'] = 'wide'                              # time goes on: down it goes!
    if HG_HANG - 0.05 <= v < HG_BACK[1]: P['eyes'] = 'wide'
    if HG_LAND <= v < HG_LAND + 0.22: P['eyes'] = 'squeeze'
    _blink(P, v, HG_LAND + 0.22)
    if HG_LAND + 0.32 <= v < mid: P['eyes'] = 'happy'
    P['blush'] = 0.7 * bump(v, HG_LAND + 0.2, mid + 0.2)
    _nod(P, v, HG_LAND + 0.4, 2, 0.32)
    lean = smooth((v - HG_FLIP[1]) / 0.3) * (1.0 - smooth((v - HG_TIP[0]) / 0.25))   # leans in to watch the sand
    P['tilt'] -= 3.5 * lean
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ang, HOURGLASS_ARM[1]))
    rot = (180.0 * flip if v < f1 else 0.0) - 90.0 * tip       # turned over; on its side (the top away from it)
    held_still = HG_BACK[1] - HG_HANG                          # its glow held still too, and going on from there
    u_loop = HG_HANG + PLAY_OUT if still else (u - held_still if v >= HG_BACK[1] else None)
    name = (item or PREVIEW_ITEM or 'hourglass') + '_play'          # with grains in the stream
    wide = max(tip, math.sin(math.pi * flip))                 # on its side it is wider: out past the head's corner
    fxs = _held(name, P, u, D, st, rot, t_item=_hg_sand(v, mid), u_loop=u_loop, off=(20.0 * wide, -4.0 * wide))
    g = C.geom(P)
    fxs.append(('pause', v - HG_HANG, (g['x'], g['top'] - 40.0), 1.0 - smooth((v - HG_BACK[0]) / 0.15)))
    c = _hand_point(P)
    fxs.append(('twinkle', v - (mid - 0.12), (c[0], c[1] + 20.0), 0.8))    # the last grain is down
    return P, fxs


BUG_SIDE, BUG_UP = (36.0, 1.12), (58.0, 1.2)       # 小虫: on the tip at its side; up, to let it go
BUG_LIFT, BUG_OPEN, BUG_FLY, BUG_LAND = 0.45, 0.68, 0.82, 2.55   # after PLAY_OUT: up it goes; the shell opens; off; back
BUG_TURN = 114.0                                   # where the icon's head points (degrees against the clock from x)


BUG_OFF = 14.0                                     # out from the tip a little more than other treasures: clear of the head


def _bug_up(v):
    return smooth((v - BUG_LIFT) / (BUG_FLY - BUG_LIFT)) * (1.0 - smooth((v - BUG_FLY - 0.05) / 0.3))


def _bug_hand(P, v):
    """Where the bug sits on the hand: further out the higher the arm (past the corner of the head)."""
    c = _hand_point(P); return c[0] + BUG_OFF + 14.0 * _bug_up(v), c[1]


def _bug_arm(v):
    """The right arm: (angle, length): up a little to let it go, down at rest while the bug is away, held out for it
    to land on, and at its side with it."""
    rest = make_pose()['nubR']
    up = _bug_up(v)
    toss = bump(v, BUG_FLY - 0.08, BUG_FLY + 0.16)                         # a little lift as it goes
    empty = smooth((v - BUG_FLY - 0.05) / 0.35) * (1.0 - smooth((v - BUG_LAND + 0.6) / 0.35))
    ang = lerp(lerp(BUG_SIDE[0], BUG_UP[0], up) + 10.0 * toss, rest[0], empty)
    ang = lerp(ang, BUG_SIDE[0] + 4.0, smooth((v - BUG_LAND + 0.6) / 0.35) * (1.0 - smooth((v - BUG_LAND - 0.3) / 0.3)))
    return ang, lerp(lerp(BUG_SIDE[1], BUG_UP[1], up), rest[1], empty)


def play_bug_body(v, D):
    """The arm alone at v (after PLAY_OUT): where the hand is, for the bug to go off and come back to."""
    P = make_pose()
    P['nubR'] = make_pose()['nubR']
    _play_arm(P, v + PLAY_OUT, D, _bug_arm(v))
    return P


def _bug_flight(v, g, hand0, hand1, turn0=0.0):
    """-> (centre, heading in degrees against the clock): off the hand, up and over its head to the left, round,
    back over it and down to the hand; at an even speed along the way (eased at both ends)."""
    x, t = g['x'], g['top']
    pts = [hand0, (hand0[0] + 5.0, hand0[1] - 115.0), (x - 95.0, t - 80.0), (x - 120.0, t - 130.0), (x - 80.0, t - 170.0),
           (x + 20.0, t - 178.0), (x + 115.0, t - 125.0), (hand1[0] + 70.0, hand1[1] - 95.0), hand1]
    def at(q):
        q = clamp(q, 0.0, 1.0) * (len(pts) - 1); i = min(int(q), len(pts) - 2); w = q - i
        p0, p1, p2, p3 = pts[max(0, i - 1)], pts[i], pts[i + 1], pts[min(len(pts) - 1, i + 2)]
        return tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * w + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * w * w
                            + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * w ** 3) for k in (0, 1))
    n = 240; way = [at(k / float(n)) for k in range(n + 1)]; acc = [0.0]
    for a, b in zip(way, way[1:]): acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    def along(d):                                              # the point at distance d along the way
        d = clamp(d, 0.0, acc[-1]); k = min(n - 1, bisect.bisect_right(acc, d) - 1)
        w = (d - acc[k]) / max(1e-6, acc[k + 1] - acc[k])
        return lerp(way[k][0], way[k + 1][0], w), lerp(way[k][1], way[k + 1][1], w)
    f = clamp((v - BUG_FLY) / (BUG_LAND - BUG_FLY), 0.0, 1.0)
    d = (smooth(f) * 0.5 + 0.5 * f) * acc[-1]
    c = along(d); a = along(d - 45.0); b = along(d + 45.0)     # (a wide look: it turns smoothly)
    head = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))
    head = lerp(BUG_TURN + turn0, head + 360.0 * (head < 0), smooth(f / 0.15))      # off the hand, then where it flies
    return c, head


def play_bug_pose(u, D=PLAY_BUG_LEN, item=None):
    """被抓住的小虫 (a ladybug): it looks at it on the tip of its arm, holds it up and lets it go: the shell opens and
    off it flies, a loop over its head, the eyes after it, leaning after it; it holds the arm out, and the bug comes
    back down on the tip, turns round.  Delighted: a hop, a heart; away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    ang, ext = _bug_arm(v)
    ang -= 10.0 * bump(v, BUG_LAND - 0.02, BUG_LAND + 0.22)      # it lands: a little dip
    P['blush'] = 0.7 * bump(v, BUG_LAND, mid + 0.2)
    P['lift'] += 12.0 * bump(v, BUG_LAND + 0.15, BUG_LAND + 0.45)
    a, x = P['nubL']; P['nubL'] = (a + 20.0 * bump(v, BUG_FLY - 0.05, BUG_FLY + 0.5), x)   # there it goes!
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ang, ext))
    g = C.geom(P)
    Pf = play_bug_body(BUG_FLY, D); turn0 = Pf["tilt"] + 0.45 * (Pf["nubR"][0] - 40.0)     # the hand's own turn as it goes
    hand0 = _bug_hand(Pf, BUG_FLY); hand1 = _bug_hand(play_bug_body(BUG_LAND, D), BUG_LAND)
    land_head = _bug_flight(BUG_LAND - 1e-3, g, hand0, hand1)[1]
    name = item or PREVIEW_ITEM or 'bug'
    if BUG_FLY <= v < BUG_LAND:
        c, head = _bug_flight(v, g, hand0, hand1, turn0)
        fxs = _held(name + '_fly', P, u, D, (True, False), head - BUG_TURN, at=c)
        eye = (clamp((c[0] - g['x']) / 120.0, -1.0, 1.0), clamp((c[1] - g['cy'] + 40.0) / 140.0, -1.0, 1.0))
        P['tilt'] -= 3.0 * eye[0] * smooth((v - BUG_FLY) / 0.25) * (1.0 - smooth((v - BUG_LAND + 0.35) / 0.3))   # leans after it
    else:
        turn = (land_head - BUG_TURN) * (1.0 - smooth((v - BUG_LAND) / 0.4)) if v >= BUG_LAND else 0.0   # landed: turns round
        fxs = _held(name + '_fly' if BUG_OPEN <= v < BUG_FLY or BUG_LAND <= v < BUG_LAND + 0.12 else name, P, u, D, st, turn,
                    off=(BUG_OFF + 14.0 * _bug_up(v), 0.0))
        c = _bug_hand(P, v); eye = (0.85, -0.3 - 0.4 * smooth((v - BUG_LIFT) / 0.3))
    P['look'] = eye if v > 0.0 else (lerp(0.0, 0.85, smooth(u / PLAY_OUT)), lerp(0.0, -0.3, smooth(u / PLAY_OUT)))
    if 0.1 <= v < BUG_LIFT: P['eyes'] = 'happy'
    if BUG_OPEN <= v < BUG_FLY + 0.3: P['eyes'] = 'wide'                 # off it goes!
    _blink(P, v, BUG_LAND + 0.08)
    if BUG_LAND + 0.2 <= v < mid: P['eyes'] = 'happy'
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    fxs.append(('heart', v - BUG_LAND - 0.25, (g['x'], g['top'] - 30.0)))
    return P, fxs


def draw_blow(fr, sc, t, origin, to):
    """A breath blown out: a little cloud of it from origin drifting towards `to`, swelling and thinning, and four
    wavy strokes after it, one after another."""
    if t < 0 or t >= 0.7: return
    ox, oy = origin; dx, dy = to[0] - ox, to[1] - oy; L = math.hypot(dx, dy) or 1.0; ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    def paint(d, X, Y, k):
        f = clamp(t / 0.5, 0.0, 1.0)                           # the cloud
        if f < 1.0:
            a = int(200 * min(1.0, f * 5.0) * (1.0 - f)); cx, cy = ox + ux * L * 0.7 * ease_out(f), oy + uy * L * 0.7 * ease_out(f)
            for bx, by, br in ((0.0, 0.0, 1.0), (-0.7, -0.45, 0.7), (-0.7, 0.5, 0.65), (0.55, -0.5, 0.6)):
                r = (12.0 + 12.0 * f) * br; x, y = cx + (bx * ux + by * nx) * 14.0, cy + (bx * uy + by * ny) * 14.0
                d.ellipse((X(x - r - 3), Y(y - r - 3), X(x + r + 3), Y(y + r + 3)), fill=(96, 150, 220, a))
            for bx, by, br in ((0.0, 0.0, 1.0), (-0.7, -0.45, 0.7), (-0.7, 0.5, 0.65), (0.55, -0.5, 0.6)):
                r = (12.0 + 12.0 * f) * br; x, y = cx + (bx * ux + by * nx) * 14.0, cy + (bx * uy + by * ny) * 14.0
                d.ellipse((X(x - r), Y(y - r), X(x + r), Y(y + r)), fill=(238, 246, 255, a))
        for j in range(4):
            f = clamp((t - 0.05 - 0.07 * j) / 0.42, 0.0, 1.0)
            if f <= 0.0 or f >= 1.0: continue
            a = int(240 * math.sin(math.pi * f)); off = (j - 1.5) * 12.0
            pts = []
            for q in range(7):
                w = q / 6.0; r = (4.0 + 0.85 * L * f) + 40.0 * w
                wob = off + 5.0 * math.sin(math.pi * 2 * w + 8 * t)
                pts.append((X(ox + ux * r + nx * wob), Y(oy + uy * r + ny * wob)))
            d.line(pts, fill=(74, 130, 214, a), width=int(max(1, 7 * k)), joint='curve')
    draw_prop_layer(fr, sc, min(ox, to[0]) - 70, min(oy, to[1]) - 70, max(ox, to[0]) + 70, max(oy, to[1]) + 70, 1.0, paint)


PLANE_SIDE, PLANE_UP = (36.0, 1.12), (42.0, 1.32)   # 纸飞机模型: at its side; up by its face, to be blown on
PLANE_HELD = (-3.0, -22.0)          # the stand's foot on the arm's tip, over it (not under it: the foot is thin)
PLANE_RAISE, PLANE_IN, PLANE_BLOW = (0.0, 0.35), (0.35, 0.75), 0.78   # after PLAY_OUT: up by its face; a breath in; blows
PLANE_GO, PLANE_HOME = 1.0, 2.6     # it shakes on its stand, and off; back on it after a loop
PLANE_LOOP = 88.0                   # the loop's radius


def _plane_arm(v, mid):
    """-> (angle, length, how far up): up by its face and out from it (room for the breath), down at the end."""
    up = smooth((v - PLANE_RAISE[0]) / (PLANE_RAISE[1] - PLANE_RAISE[0])) * (1.0 - smooth((v - PLANE_HOME - 0.25) / 0.4))
    ang = lerp(PLANE_SIDE[0], PLANE_UP[0], up) - 8.0 * bump(v, PLANE_HOME - 0.02, PLANE_HOME + 0.22)
    return ang, lerp(PLANE_SIDE[1], PLANE_UP[1], up), up


def play_plane_pose(u, D=PLAY_PLANE_LEN, item=None):
    """纸飞机模型: holds it up by its face and looks at it; a breath in (it swells, its eyes shut), and it blows on
    it: the plane lifts off its stand and loops the loop over it (upside down at the top), the pet's eyes going
    round after it, its body leaning back to see the top; it comes down level and lands on its stand again.
    Delighted: a hop, a blush, a glint; away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    ang, ext, up = _plane_arm(v, mid)
    held = PLANE_HELD
    i0, i1 = PLANE_IN
    breath = smooth((v - i0) / (i1 - i0)) * (1.0 - smooth((v - PLANE_BLOW + 0.04) / 0.2))        # a big breath in: it swells
    blow = smooth((v - PLANE_BLOW + 0.04) / 0.16) * (1.0 - smooth((v - PLANE_BLOW - 0.3) / 0.25))   # all of it out
    P['sy'] *= 1 + 0.065 * breath - 0.07 * blow; P['sx'] *= 1 + 0.05 * breath + 0.04 * blow
    P['lift'] += 6.0 * breath
    P['tilt'] -= 7.0 * blow
    P['blush'] = 0.7 * breath
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ang, ext))
    name = item or PREVIEW_ITEM or 'plane_model'
    t_icon = (u / 2.0) % 1.0                                   # the icon's own loop, as in the album
    hand = _hand_point(P); hand = (hand[0] + held[0], hand[1] + held[1])
    hand_rot = P['tilt'] + 0.45 * (P['nubR'][0] - 40.0)
    g = C.geom(P)
    if v < PLANE_GO or v >= PLANE_HOME:                         # the model as a whole
        shake = 6.0 * math.sin(TWO_PI * (v - PLANE_BLOW) / 0.07) * bump(v, PLANE_BLOW + 0.04, PLANE_GO)   # in the wind
        fxs = _held(name + '_play', P, u, D, st, shake, off=held, grip=False)
        c = hand
    else:                                                       # the stand in the hand, the plane looping over it
        fxs = _held(name + '_stand', P, u, D, st, 0.0, off=held, glow=0.0, t_item=t_icon, grip=False)
        f = (v - PLANE_GO) / (PLANE_HOME - PLANE_GO)
        q = TWO_PI * (f * f * (3.0 - 2.0 * f))
        R = PLANE_LOOP
        ctr = (hand[0], hand[1] - R)
        c = (ctr[0] + R * math.sin(q), ctr[1] + R * math.cos(q))
        fxs += _held(name + '_plane', P, u, D, (True, False), hand_rot + math.degrees(q), at=c, t_item=t_icon)
    face = (g['x'] + g['bw'] / 2.0 + 2.0, g['cy'] - 50.0)      # the breath from the side of its face, outside it
    look = (clamp((c[0] - g['x']) / 140.0, -1.0, 1.0), clamp((c[1] - g['cy'] + 40.0) / 120.0, -1.0, 1.0))
    P['look'] = look if v > 0.0 else (lerp(0.0, 0.85, smooth(u / PLAY_OUT)), lerp(0.0, -0.3, smooth(u / PLAY_OUT)))
    if PLANE_GO < v < PLANE_HOME:                               # leans back a little to see it at the top
        P['tilt'] += 2.5 * max(0.0, -math.cos(TWO_PI * (v - PLANE_GO) / (PLANE_HOME - PLANE_GO)))
    if i0 + 0.05 <= v < PLANE_BLOW: P['eyes'] = 'closed'         # a breath in
    if PLANE_BLOW <= v < PLANE_BLOW + 0.4: P['eyes'] = 'squeeze'
    if PLANE_BLOW + 0.4 <= v < PLANE_BLOW + 0.65: P['eyes'] = 'wide'          # it goes!
    _blink(P, v, PLANE_HOME + 0.05)
    if PLANE_HOME + 0.18 <= v < mid: P['eyes'] = 'happy'
    P['lift'] += 12.0 * bump(v, PLANE_HOME + 0.15, PLANE_HOME + 0.45)
    P['blush'] = max(P['blush'], 0.7 * bump(v, PLANE_HOME, mid + 0.2))
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    fxs.append(('blow', v - PLANE_BLOW, face, hand))           # over the model: the wind goes by it
    fxs.append(('twinkle', v - PLANE_HOME - 0.02, hand, 0.9))
    return P, fxs


def _duck_body_at(v, D):
    """The pose at v (after PLAY_OUT), for where the duck was let go."""
    return play_duck_pose(v - 1e-6 + PLAY_OUT, D)[0]

BALLOON_ARM = (52.0, 1.26)        # 气球: the arm up and out, holding the string
BALLOON_K = 1.4                   # the balloon a little bigger than other treasures in the hand
BALLOON_HIGH = 132.0              # how far above the hand it floats on its string (logical px)
BALLOON_RISE = 58.0               # how far it lifts the pet off the floor
BALLOON_UP, BALLOON_TOP, BALLOON_DOWN, BALLOON_LAND = 0.75, 2.05, 2.75, 3.6   # after PLAY_OUT: off, at the top, coming down, on the floor
BALLOON_KNOT = 22.0               # the knot below the balloon's centre (its icon's units)
STRING_COL = (110, 96, 104)


def _balloon_rise(v):
    up = smooth((v - BALLOON_UP) / (BALLOON_TOP - BALLOON_UP))
    down = smooth((v - BALLOON_DOWN) / (BALLOON_LAND - BALLOON_DOWN))
    return up * (1.0 - down)


def draw_string(fr, sc, a, b, bend, alpha=1.0):
    """A string from a (the hand) to b (the balloon's knot), bowed sideways by bend (logical px)."""
    if alpha <= 0.01: return
    (ax, ay), (bx, by) = a, b
    mx, my = (ax + bx) / 2.0 + bend, (ay + by) / 2.0
    pts = [(lerp(lerp(ax, mx, t), lerp(mx, bx, t), t), lerp(lerp(ay, my, t), lerp(my, by, t), t)) for t in (i / 16.0 for i in range(17))]
    def paint(d, X, Y, k):
        d.line([(X(x), Y(y)) for x, y in pts], fill=STRING_COL + (255,), width=int(max(1, 3.2 * k)), joint='curve')
    draw_prop_layer(fr, sc, min(ax, bx, mx) - 8, min(ay, by) - 8, max(ax, bx, mx) + 8, max(ay, by) + 8, alpha, paint)


def play_balloon_pose(u, D=PLAY_BALLOON_LEN, item=None):
    """气球: out from behind its back it comes and floats up on its long string over the pet's head; it tugs (up
    on its toes, eyes wide), and slowly the pet is lifted off the floor, legs hanging, swaying, the other arm
    paddling; at the top a look down (so high!) and delight; the balloon lets it down gently, a soft landing, a
    happy hop; the balloon is pulled down into the hand and put away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    rise = _balloon_rise(v)
    bob = 3.0 * math.sin(TWO_PI * (v - BALLOON_TOP) / 0.9) * bump(v, BALLOON_TOP - 0.3, BALLOON_DOWN + 0.3)
    P['lift'] += BALLOON_RISE * rise + bob * rise
    tug = bump(v, 0.35, BALLOON_UP + 0.15)                     # the first tug: up on its toes, stretched
    P['sy'] *= 1 + 0.06 * tug + 0.03 * rise; P['sx'] *= 1 - 0.03 * tug - 0.015 * rise
    P['legx'] = 7.0 * rise                                     # its legs hang
    sway = math.sin(TWO_PI * (v - BALLOON_UP) / 1.4) * rise
    P['tilt'] += 5.0 * sway
    paddle = math.sin(TWO_PI * v / 0.5) * smooth((v - BALLOON_UP) / 0.3) * (1.0 - smooth((v - BALLOON_TOP + 0.2) / 0.3))
    a, x = P['nubL']; P['nubL'] = (a + 22.0 * paddle + 30.0 * bump(v, BALLOON_TOP + 0.5, BALLOON_DOWN + 0.4), x)
    land = bump(v, BALLOON_LAND - 0.02, BALLOON_LAND + 0.24)
    P['sy'] *= 1 - 0.08 * land; P['sx'] *= 1 + 0.04 * land
    hop = bump(v, BALLOON_LAND + 0.3, BALLOON_LAND + 0.56)
    P['lift'] += 12.0 * hop
    peek = bump(v, BALLOON_TOP - 0.15, BALLOON_TOP + 0.5)      # a look down: so high!
    up_look = smooth(v / 0.3) * (1.0 - smooth((v - BALLOON_TOP + 0.3) / 0.2))
    P['look'] = (0.35 * up_look, -0.9 * up_look + 0.75 * peek)
    if v > BALLOON_TOP + 0.5: P['look'] = (0.3, -0.2)
    if 0.0 < v < BALLOON_TOP + 0.5: P['eyes'] = 'wide'
    if BALLOON_TOP + 0.5 <= v < BALLOON_LAND: P['eyes'] = 'happy'
    if BALLOON_LAND <= v < BALLOON_LAND + 0.2: P['eyes'] = 'squeeze'
    if BALLOON_LAND + 0.2 <= v < mid: P['eyes'] = 'happy'
    P['blush'] = 0.7 * bump(v, BALLOON_TOP, mid + 0.2)
    P['shadow'] = 1.0 - 0.5 * rise
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    st = _play_arm(P, u, D, BALLOON_ARM)
    a, x = P['nubR']; P['nubR'] = (a - 3.0 * sway + 8.0 * tug, x)
    # the balloon: up on its string once the arm is out, pulled down into the hand at the end
    out = smooth(v / 0.45) * (1.0 - smooth((v - mid + 0.4) / 0.4))
    high = BALLOON_HIGH * out + 10.0 * tug + 6.0 * rise
    drift = (16.0 + 10.0 * math.sin(TWO_PI * v / 2.2)) * out - 18.0 * sway
    rot = -8.0 * sway + 4.0 * math.sin(TWO_PI * v / 1.7) * out
    fxs = _held('balloon_free', P, u, D, st, rot, k=BALLOON_K, off=(drift, -high), grip=out < 0.15)
    if fxs and out > 0.05:
        g = C.geom(P)
        hand = g['tipR']
        cx, cy = fxs[0][2]
        total = math.radians(fxs[0][3])
        kn = BALLOON_KNOT * ITEM_BOX * HELD_BOX * BALLOON_K / 100.0
        knot = (cx + kn * math.sin(total), cy + kn * math.cos(total))
        fxs.insert(0, ('string', hand, knot, (6.0 - 10.0 * rise) * out + 5.0 * sway, min(1.0, out * 3.0)))
        fxs.append(('twinkle', v - (BALLOON_TOP + 0.45), (cx, cy - 20.0), 1.0))
    return P, fxs


ROBOT_K = 1.45                     # 发条小机器人: bigger than other treasures in the hand: it is watched
ROBOT_BOT = 0.48                   # of the box: its feet below its centre
ROBOT_HEAD = (-0.04, 0.36)         # ... the top of its head (where it is tapped), from its centre
ROBOT_DROP = (0.25, 0.42)          # after PLAY_OUT: let go, on the floor
ROBOT_GO = 0.45                    # it starts to march by itself
ROBOT_JOIN = 0.8                   # the pet marches along with it
ROBOT_SLOW = (2.0, 2.85)           # its spring runs down: slower and slower, and still (and the pet with it)
ROBOT_LOOK = 2.95                  # the pet looks at it: stopped?
ROBOT_TAPS = (3.38, 3.6)           # two taps on its head
ROBOT_PICK = (3.85, 4.05)          # the tip down to it, up it comes
ROBOT_PACE = 1.5                   # steps: this many pairs a second at full speed
ROBOT_SPOT_OUT = 34.0              # further out than a duck: room to march


def _robot_speed(v):
    return ROBOT_PACE * smooth((v - ROBOT_GO) / 0.15) * (1.0 - smooth((v - ROBOT_SLOW[0]) / (ROBOT_SLOW[1] - ROBOT_SLOW[0])))


def _robot_phase(v):
    """How far the march has gone (pairs of steps) at v: the speed added up."""
    if v <= ROBOT_GO: return 0.0
    n = max(4, int((v - ROBOT_GO) / 0.01))
    h = (v - ROBOT_GO) / n
    return sum(_robot_speed(ROBOT_GO + (i + 0.5) * h) for i in range(n)) * h


def _robot_spot():
    B = ITEM_BOX * HELD_BOX * ROBOT_K
    cy = FLOOR_Y - ROBOT_BOT * B
    P = make_pose(); P['legx'] = -12.0
    return _tip_at(P, _reach(P, cy - 0.3 * B), FLOOR_EXT)[0] + ROBOT_SPOT_OUT, cy


def _robot_body_at(v, D):
    return play_robot_pose(v - 1e-6 + PLAY_OUT, D)[0]


def _robot_tap(v):
    """-> (how far over to its head 0..1, how high the tip is lifted between taps 0..1, the knock 0..1)."""
    t0, t1 = ROBOT_TAPS
    over = smooth((v - t0 + 0.32) / 0.25) * (1.0 - smooth((v - t1 - 0.12) / 0.2))
    lift = 0.0
    for a, b in ((t0 - 0.2, t0), (t0 + 0.04, t1)):             # up a little, and down on its head
        lift = max(lift, bump(v, a, b))
    knock = max(bump(v, t0, t0 + 0.1), bump(v, t1, t1 + 0.1))
    return over, lift, knock


def play_robot_pose(u, D=PLAY_ROBOT_LEN, item=None):
    """发条小机器人, 学走步: puts it down beside it and it marches on the spot, stiffly; the pet watches, gets it,
    and marches along in step, just as stiff (eyes ahead, both arms swinging like levers).  The robot's spring runs
    down: slower and slower, and the pet slows down with it, step for step, till both stand still.  The pet looks
    at it (stopped?), blinks, leans over and taps it on the head, twice: nothing.  It picks it up and puts it away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    B = ITEM_BOX * HELD_BOX * ROBOT_K
    rx, ry = _robot_spot()
    ph = _robot_phase(v)
    sp = _robot_speed(v) / ROBOT_PACE                          # 1 at full speed, 0 when it has run down
    join = smooth((v - ROBOT_JOIN) / 0.2)
    march = join * sp
    P['walk'] = ph
    P['walkamp'] = 0.85 * march
    P['lift'] += 7.0 * abs(math.sin(math.pi * ph)) * march
    m = clamp(1.8 * math.sin(TWO_PI * ph), -1.0, 1.0) * march  # the arms like levers: snap from one end to the other
    stiff = join * (1.0 - smooth((v - ROBOT_SLOW[1]) / 0.2))
    P['sy'] *= 1 + 0.03 * stiff; P['sx'] *= 1 - 0.015 * stiff
    a, x = P['nubL']; P['nubL'] = (a + 38.0 * m, x)
    over, lift, knock = _robot_tap(v)
    P['tilt'] -= 5.0 * over + 2.0 * bump(v, ROBOT_LOOK, ROBOT_TAPS[0])
    P['legx'] = -6.0 * over
    # eyes: on it, wide when it starts; ahead while marching; on it again when it stops; a blink; a little squint at
    # the taps (anyone in there?); then a shrug of a smile as it is picked up
    look_on = (0.75, 0.6)
    P['look'] = look_on if v > 0.2 else (0.75 * smooth(v / 0.2), 0.6 * smooth(v / 0.2))
    ahead = smooth((v - ROBOT_JOIN) / 0.2) * (1.0 - smooth((v - ROBOT_SLOW[1] - 0.05) / 0.15))
    P['look'] = (lerp(P['look'][0], 0.05, ahead), lerp(P['look'][1], 0.0, ahead))
    if ROBOT_GO <= v < ROBOT_JOIN: P['eyes'] = 'wide'
    _nod(P, v, ROBOT_GO + 0.12, 1, 0.22)
    _blink(P, v, ROBOT_LOOK + 0.12)
    _blink(P, v, ROBOT_LOOK + 0.32)
    if ROBOT_TAPS[0] - 0.3 <= v < ROBOT_PICK[0]: P['look'] = (0.85, 0.75)   # down at its head while it taps it
    if ROBOT_PICK[0] <= v < mid: P['eyes'] = 'happy'
    P['blush'] = 0.5 * bump(v, ROBOT_PICK[0] - 0.1, mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    # the right arm: low with it, let go; a lever in the march; over to its head and two taps; down to pick it up
    a0, a1 = ROBOT_DROP
    if v < a0:
        f = smooth((v - a0 + 0.25) / 0.25); ra, re = lerp(DUCK_CARRY[0], -50.0, f), lerp(DUCK_CARRY[1], FLOOR_EXT, f)
    else:
        f = smooth((v - a0) / 0.3)
        ra, re = lerp(-50.0, -10.0, f) - 38.0 * m, lerp(FLOOR_EXT, 1.05, f)
        head = (rx + ROBOT_HEAD[0] * B, ry - ROBOT_HEAD[1] * B - 2.0)
        if over > 0.0:                                         # the tip on its head (the pet leans over to it)
            ta = _reach(P, head[1] - 22.0 * lift + 6.0 * knock)
            tip = _tip_at(P, ta, FLOOR_EXT)
            P['x'] += (head[0] - tip[0]) * over
            ra, re = lerp(ra, ta, over), lerp(re, FLOOR_EXT, over)
        pk = smooth((v - ROBOT_PICK[0] + 0.25) / 0.25)
        if pk > 0.0:                                           # down to its middle, and up it comes
            g = smooth((v - ROBOT_PICK[0]) / (ROBOT_PICK[1] - ROBOT_PICK[0]))
            ta = _reach(P, ry - 0.05 * B)
            tip = _tip_at(P, ta, FLOOR_EXT)
            P['x'] += (rx - 0.2 * B - tip[0]) * pk * (1.0 - g)
            P['legx'] -= 10.0 * pk * (1.0 - g)
            ra = lerp(lerp(ra, ta, pk), DUCK_CARRY[0], g)
            re = lerp(lerp(re, FLOOR_EXT, pk), DUCK_CARRY[1], g)
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ra, re))
    name = item or PREVIEW_ITEM or 'robot'
    if v < a0 or v >= ROBOT_PICK[1]:
        return P, _held(name, P, u, D, st, 0.0, k=ROBOT_K)
    t_item = ph % 1.0 if v >= ROBOT_GO else 0.0
    sq = (1.0 + 0.05 * knock, 1.0 - 0.07 * knock)              # it gives a little under each tap
    if v < ROBOT_PICK[0]:
        f = clamp((v - a0) / (a1 - a0), 0.0, 1.0)
        rel = _hand_point(_robot_body_at(a0, D))
        at = (rx, ry) if f >= 1.0 else (lerp(rel[0], rx, f), lerp(rel[1], ry, f * f))
        jig = 1.5 * math.sin(TWO_PI * ph * 2.0) * sp            # a tin rattle as it marches
        fxs = _held(name, P, u, D, (True, False), jig, at, k=ROBOT_K, squash=sq, grip=over > 0.3, glow=1.0 - smooth(f / 0.4),
                    t_item=t_item)
    else:
        f = smooth((v - ROBOT_PICK[0]) / (ROBOT_PICK[1] - ROBOT_PICK[0]))
        hp = _hand_point(P)
        fxs = _held(name, P, u, D, (True, False), 0.0, (lerp(rx, hp[0], f), lerp(ry, hp[1], f)),
                    k=ROBOT_K, grip=True, glow=smooth((f - 0.6) / 0.4), t_item=t_item)
    return P, fxs


CUBE_ARM = (30.0, 1.2)             # 魔方: held out at its side on the tip, clear of the body
CUBE_K = 1.1                       # a little bigger than other treasures in the hand: its colours are watched
CUBE_GATHER = (0.3, 0.75)          # after PLAY_OUT: eyes shut, it gathers itself ...
CUBE_CAST = 0.75                   # ... and casts: the cube floats up off the hand
CUBE_OUT = 18.0                    # out from the hand point: clear of the head's corner
CUBE_HIGH = 62.0                   # how far above the hand it spins
CUBE_SPIN = (0.8, 3.0)             # it turns round its upright axis (drawn in 3D), faster, then slower ...
CUBE_TURNS = 3.0                   # ... and stops after this many whole turns (at most ~37 degrees a frame: no wagon wheel)
CUBE_DOWN = (3.08, 3.4)            # back down into the hand
CUBE_HOP = (3.5, 3.8)            # a hop of joy


def _cube_turns(v):
    """How far it has twirled (turns) at v: speeding up, then slowing down to a stop at a whole turn."""
    a, b = CUBE_SPIN
    f = clamp((v - a) / (b - a), 0.0, 1.0)
    return CUBE_TURNS * (f * f * (3.0 - 2.0 * f))              # smooth: slow, fast, slow


def _cube_rise(v):
    return smooth((v - CUBE_CAST) / 0.4) * (1.0 - smooth((v - CUBE_DOWN[0]) / (CUBE_DOWN[1] - CUBE_DOWN[0])))


def draw_orbit(fr, sc, t, origin, alpha, r):
    """Magic: small stars going round a point on a flat ring (the ones behind smaller and dimmer); t: time."""
    if alpha <= 0.01: return
    ox, oy = origin
    def paint(d, X, Y, k):
        d.ellipse((X(ox - r), Y(oy - 0.32 * r), X(ox + r), Y(oy + 0.32 * r)), outline=(255, 226, 130, 110),
                  width=int(max(1, 3.0 * k)))                  # the ring it goes round on, faint
        for i in range(7):
            q = TWO_PI * (t * 0.9 + i / 7.0)
            x, y = ox + r * math.cos(q), oy + 0.32 * r * math.sin(q)
            near = 0.5 + 0.5 * math.sin(q)                     # in front: bigger, brighter
            s_ = (13.0 + 10.0 * near) * (1.0 if i % 2 else 0.8)
            col = ((255, 226, 92) if i % 2 else (255, 250, 220)) + (int(255 * (0.55 + 0.45 * near)),)
            pts = []
            for j in range(8):
                rr = s_ if j % 2 == 0 else s_ * 0.42
                a_ = math.pi / 4.0 * j
                pts.append((X(x + rr * math.sin(a_)), Y(y - rr * math.cos(a_))))
            d.polygon(pts, fill=col)
    draw_prop_layer(fr, sc, ox - r - 26, oy - 0.32 * r - 26, ox + r + 26, oy + 0.32 * r + 26, alpha, paint)


def play_cube_pose(u, D=PLAY_CUBE_LEN, item=None):
    """魔方, 施魔法: held out at its side, mixed up.  It shuts its eyes and gathers itself (up a little, the other arm
    rising), and casts: a flick, wide eyes, and the cube floats up off its hand, a ring of little stars going round
    it, and twirls (round its upright axis, its colours changing as it turns), faster, then slower, and stops: every
    face one colour, a flash.  It comes down into the hand; the pet is delighted: a hop, and it puts it away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    g0, g1 = CUBE_GATHER
    gather = smooth((v - g0) / (g1 - g0)) * (1.0 - smooth((v - CUBE_CAST) / 0.12))
    P['sy'] *= 1 + 0.05 * gather; P['sx'] *= 1 - 0.025 * gather
    flick = bump(v, CUBE_CAST - 0.04, CUBE_CAST + 0.3)
    P['sy'] *= 1 - 0.04 * flick
    rise = _cube_rise(v)
    turns = _cube_turns(v)
    spin_f = clamp((v - CUBE_SPIN[0]) / (CUBE_SPIN[1] - CUBE_SPIN[0]), 0.0, 1.0)
    casting = smooth((v - CUBE_CAST) / 0.2) * (1.0 - smooth((v - CUBE_SPIN[1]) / 0.2))   # keeping it going
    a, x = P['nubL']
    wig = math.sin(TWO_PI * v / 0.42)
    P['nubL'] = (a + 44.0 * gather + 64.0 * flick + (30.0 + 10.0 * wig) * casting, x + 0.12 * casting)
    P['tilt'] += 2.0 * wig * casting - 2.5 * flick
    P['lift'] += 3.0 * math.sin(TWO_PI * v / 0.84) * casting
    hop = bump(v, CUBE_HOP[0], CUBE_HOP[1])
    P['lift'] += 20.0 * hop
    P['sy'] *= 1 - 0.05 * bump(v, CUBE_HOP[0] - 0.14, CUBE_HOP[0] + 0.02) - 0.05 * bump(v, CUBE_HOP[1] - 0.02, CUBE_HOP[1] + 0.16)
    land = bump(v, CUBE_DOWN[1] - 0.04, CUBE_DOWN[1] + 0.16)
    up_look = 0.6 * rise
    P['look'] = (0.75, 0.0 - up_look) if v > 0.15 else (0.75 * smooth(v / 0.15), 0.0)
    if g0 <= v < CUBE_CAST: P['eyes'] = 'closed'
    if CUBE_CAST <= v < CUBE_CAST + 0.35: P['eyes'] = 'wide'
    if CUBE_CAST + 0.35 <= v < CUBE_SPIN[1]: P['eyes'] = 'star' if spin_f > 0.25 else 'wide'
    if CUBE_SPIN[1] <= v < CUBE_DOWN[1]: P['eyes'] = 'wide'
    if CUBE_DOWN[1] <= v < mid: P['eyes'] = 'happy'
    P['blush'] = 0.7 * bump(v, CUBE_DOWN[1] - 0.1, mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    st = _play_arm(P, u, D, (CUBE_ARM[0] - 6.0 * land + 6.0 * flick, CUBE_ARM[1]))
    if v < CUBE_SPIN[0]:
        name, t_item = (item or 'cube'), 0.0
    elif v < CUBE_SPIN[1]:
        name, t_item = 'cube_turning', turns                     # turned in 3D; a row more in place each quarter turn
    else:
        name, t_item = 'cube_solved', None
    pop = bump(v, CUBE_SPIN[1], CUBE_SPIN[1] + 0.2)
    hover = 3.0 * math.sin(TWO_PI * v / 0.9) * rise
    off = (CUBE_OUT, -CUBE_HIGH * rise + hover)
    fxs = _held(name, P, u, D, st, 2.0 * math.sin(TWO_PI * v / 1.3) * rise, k=CUBE_K * (1.0 + 0.12 * pop), off=off,
                grip=rise < 0.15, t_item=t_item, glow=1.0 - 0.6 * rise)
    if fxs:
        cx, cy = fxs[0][2]
        mid_c = (cx, cy)
        fxs.insert(0, ('orbit', v, (mid_c[0], mid_c[1] + 12.0), casting * smooth((rise - 0.6) / 0.4), 64.0))   # round the cube, clear of the arm below
        fxs.append(('spark', v - CUBE_SPIN[1], (cx, cy - 26.0), 2.0))
        fxs.append(('twinkle', v - CUBE_SPIN[1] - 0.05, (cx + 34.0, cy - 30.0), 1.3))
        fxs.append(('twinkle', v - CUBE_SPIN[1] - 0.25, (cx - 34.0, cy - 16.0), 1.0))
    g = C.geom(P)
    fxs.append(('twinkle', v - CUBE_CAST, g['tipL'], 1.1))       # the cast: a spark off the other arm
    return P, fxs


MOON_ARM = (28.0, 1.15)            # 小月亮夜灯: held out at its side
MOON_LIGHT = 0.35                  # after PLAY_OUT: it lights up by itself
MOON_UP = (0.65, 1.35)             # the moon floats up off its stand, above the pet's head ...
MOON_SKY = (1.0, 1.7)              # ... and a piece of night sky opens round it
MOON_SHOOT = 2.35                  # a shooting star
MOON_CLOSE = (3.05, 3.5)           # the sky folds back into the moon ...
MOON_DOWN = (3.1, 3.6)             # ... and the moon comes down onto its stand
MOON_OFF = 3.85                    # the lamp goes out
MOON_K = 1.45                      # the moon up there, this big
MOON_AT = (70.0, -120.0)           # ... its centre from the body's middle-x and top
MOON_C = (2.0, -8.0)               # the moon's centre in its icon (box units)
SKY_AT = (100.0, -40.0)            # the sky's centre from the body's middle-x and top; its half width and height:
SKY_R = (330.0, 262.0)             # inside the frames' canvas as it is (union x 704..1414, y 331..973): no bigger window
def _sky_stars():
    """The stars of the night sky, as (x, y in -1..1 of its half width and height, size, twinkle phase, twinkles a
    second, brightness): scattered at random (no pattern), a few clusters, many fine ones along a faint band; most
    tiny and dim, a few bright, a handful big."""
    import random
    rnd = random.Random(20261112)
    out = []
    def add(x, y, big=False):
        if x * x + y * y > 0.8: return
        r = rnd.random()
        size = rnd.uniform(4.2, 7.0) if big else (rnd.uniform(0.8, 1.6) if r < 0.72 else rnd.uniform(1.8, 3.0))
        out.append((x, y, size, rnd.random(), rnd.uniform(0.5, 2.4), rnd.uniform(0.35, 1.0) if not big else 1.0))
    for _ in range(70):                                        # anywhere
        add(rnd.uniform(-1, 1), rnd.uniform(-1, 1))
    for cx, cy in ((-0.45, -0.35), (0.38, -0.12), (0.05, 0.42)):   # a few clusters
        for _ in range(9):
            add(cx + rnd.gauss(0, 0.1), cy + rnd.gauss(0, 0.08))
    for _ in range(45):                                        # fine ones along the band
        f = rnd.uniform(-1, 1)
        x, y = f * 0.95, -0.3 * f + rnd.gauss(0, 0.09) - 0.05
        if x * x + y * y <= 0.8:
            out.append((x, y, rnd.uniform(0.6, 1.2), rnd.random(), rnd.uniform(0.6, 2.0), rnd.uniform(0.25, 0.7)))
    for _ in range(7):                                         # a handful of big ones
        add(rnd.uniform(-0.8, 0.8), rnd.uniform(-0.75, 0.6), big=True)
    return out


SKY_STARS = _sky_stars()
SKY_BAND = (-0.3, -0.05, 0.16)    # the faint band: y = a x + b (of the half sizes), its half width
SKY_METEORS = ((1.9, (-0.55, -0.55), 24.0, 0.55, 0.38, 0.7),  # (after PLAY_OUT, start, degrees down, length, s, size):
               (None, (-0.75, -0.62), 21.0, 1.3, 0.55, 1.0),  # None: the big one, at MOON_SHOOT (the pet hops)
               (2.95, (0.05, -0.72), 38.0, 0.6, 0.34, 0.65))  # now and then one goes by
MOON_REST_TOP = C.geom(make_pose())['top']   # the sky and the moon are placed from the top of the pet at rest
MOON_SIT = 54.0                    # the lamp sits on the arm's tip (held from below by its foot): its centre this far above


def draw_sky(fr, sc, t, centre, rx, ry, alpha, shoot_t):
    """A piece of night sky behind the pet: a deep blue oval fading smoothly out at its edge (worked out pixel by
    pixel: no rings) with a faint lighter band across it, stars scattered in it twinkling each in its own time (only
    those inside it as it opens; far away: small points of light, no glow), and now and then a shooting star (SKY_METEORS; the big one at shoot_t)."""
    if alpha <= 0.01 or rx < 4: return
    ox, oy = centre
    x0, y0 = int(math.floor((ox - rx) * sc.s)), int(math.floor((oy - ry) * sc.s))
    x1, y1 = int(math.ceil((ox + rx) * sc.s)) + 1, int(math.ceil((oy + ry) * sc.s)) + 1
    xs = (np.arange(x0, x1, dtype=np.float32) + 0.5) / sc.s
    ys = (np.arange(y0, y1, dtype=np.float32) + 0.5) / sc.s
    nx, ny = (xs[None, :] - ox) / rx, (ys[:, None] - oy) / ry
    e = np.sqrt(nx ** 2 + ny ** 2)                             # 0 at the middle, 1 at the edge
    edge = np.clip((1.0 - e) / 0.32, 0.0, 1.0)
    a = edge * edge * (3.0 - 2.0 * edge) * 238.0 * alpha        # smooth out over the outer third
    m = np.clip(e, 0.0, 1.0)
    ba, bb, bw = SKY_BAND
    band = np.exp(-((ny - (ba * nx + bb)) / bw) ** 2 / (1.0 + ba * ba)) * (1.0 - m)   # the faint band, fading out too
    lay = np.zeros((y1 - y0, x1 - x0, 4), np.float32)
    lay[..., 0] = 18 + (66 - 18) * m + 34 * band               # deep blue in the middle, a little lighter out there
    lay[..., 1] = 24 + (64 - 24) * m + 36 * band
    lay[..., 2] = 70 + (146 - 70) * m + 44 * band
    lay[..., 3] = a
    fr.alpha_composite(Image.fromarray(np.clip(lay, 0, 255).astype(np.uint8), 'RGBA'), (x0, y0))
    def paint(d, X, Y, k):
        for ux, uy, size, ph, rate, bright in SKY_STARS:
            x, y = ox + ux * SKY_R[0], oy + uy * SKY_R[1]
            if ((x - ox) / rx) ** 2 + ((y - oy) / ry) ** 2 > 0.8: continue       # not yet open there, or too near the edge
            tw = 0.5 + 0.5 * math.sin(TWO_PI * (t * rate + ph))
            r = (size * (0.5 + 0.45 * tw)) if size < 3.5 else (1.9 + 0.5 * tw)    # far away: points of light, no glow
            d.ellipse((X(x - r), Y(y - r), X(x + r), Y(y + r)),
                      fill=(255, 250, 232, int(255 * (bright if size < 3.5 else 1.0) * (0.35 + 0.65 * tw))))
        for t0, (sx, sy), deg, length, dur, size in SKY_METEORS:
            st = t - (shoot_t if t0 is None else t0)
            if not 0.0 <= st < dur: continue
            f = st / dur
            q = math.radians(deg)
            dx, dy = math.cos(q) * length * SKY_R[0], math.sin(q) * length * SKY_R[0]
            hx, hy = ox + sx * SKY_R[0] + dx * f, oy + sy * SKY_R[1] + dy * f
            fade = 1.0 - smooth((f - 0.7) / 0.3)
            for j in range(12):                                # its tail, thinning and fading behind it
                qq = j / 12.0
                tx, ty = hx - 0.22 * dx * qq / max(0.3, length), hy - 0.22 * dy * qq / max(0.3, length)
                r = (5.0 * (1.0 - qq) + 0.8) * size
                d.ellipse((X(tx - r), Y(ty - r), X(tx + r), Y(ty + r)), fill=(255, 246, 214, int(255 * (1.0 - qq) * fade)))
    draw_prop_layer(fr, sc, ox - rx - 4, oy - ry - 4, ox + rx + 4, oy + ry + 4, alpha, paint)


def play_moon_pose(u, D=PLAY_MOON_LEN, item=None):
    """小月亮夜灯, 一片星空: held out at its side, and it lights up by itself.  The little moon floats up off its
    stand, above the pet's head, bigger, glowing, and a piece of night sky opens out round it behind the pet: deep
    blue, stars coming out, twinkling.  The pet looks up, wide-eyed, stars in its eyes, then rapt (happy, a blush),
    swaying a little, its other arm slowly reaching up; a shooting star (it follows it).  The sky folds back into the
    moon, the moon comes down onto its stand, the lamp goes out; a pleased little nod, and it puts it away."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    up = smooth((v - MOON_UP[0]) / (MOON_UP[1] - MOON_UP[0])) * (1.0 - smooth((v - MOON_DOWN[0]) / (MOON_DOWN[1] - MOON_DOWN[0])))
    sky = smooth((v - MOON_SKY[0]) / (MOON_SKY[1] - MOON_SKY[0])) * (1.0 - smooth((v - MOON_CLOSE[0]) / (MOON_CLOSE[1] - MOON_CLOSE[0])))
    rapt = smooth((v - MOON_SKY[1] + 0.1) / 0.4) * (1.0 - smooth((v - MOON_CLOSE[0]) / 0.3))
    sway = math.sin(TWO_PI * (v - MOON_SKY[1]) / 1.6) * rapt
    P['tilt'] += 2.5 * sway
    P['sy'] *= 1 + 0.035 * up                                  # up on its toes to look
    a, x = P['nubL']; P['nubL'] = (a + 52.0 * smooth((v - MOON_SKY[1]) / 0.9) * (1.0 - smooth((v - MOON_CLOSE[0]) / 0.35)), x)
    shoot = bump(v, MOON_SHOOT - 0.05, MOON_SHOOT + 0.6)
    P['lift'] += 5.0 * bump(v, MOON_SHOOT, MOON_SHOOT + 0.3)
    look_up = (0.25 + 0.35 * shoot * (v - MOON_SHOOT) / 0.6, -1.0)
    look_lamp = (0.75, 0.2)
    P['look'] = look_lamp if v > 0.15 else (0.75 * smooth(v / 0.15), 0.2 * smooth(v / 0.15))
    w = max(up, sky)
    P['look'] = (lerp(P['look'][0], look_up[0], w), lerp(P['look'][1], look_up[1], w))
    if MOON_LIGHT <= v < MOON_LIGHT + 0.3: P['eyes'] = 'wide'
    if MOON_UP[0] <= v < MOON_SKY[0] + 0.3: P['eyes'] = 'wide'
    if MOON_SKY[0] + 0.3 <= v < MOON_SKY[1] + 0.2: P['eyes'] = 'star'
    if MOON_SKY[1] + 0.2 <= v < MOON_CLOSE[1]: P['eyes'] = 'happy'
    if MOON_SHOOT <= v < MOON_SHOOT + 0.45: P['eyes'] = 'wide'
    if MOON_CLOSE[1] <= v < mid: P['eyes'] = 'happy'
    _nod(P, v, MOON_OFF + 0.02, 1, 0.24)
    P['blush'] = 0.75 * bump(v, MOON_SKY[1], mid + 0.2)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    st = _play_arm(P, u, D, (MOON_ARM[0] - 4.0 * sway, MOON_ARM[1]))
    lit = MOON_LIGHT <= v < MOON_OFF
    name = (item or 'moon_lamp') if lit else 'moon_lamp_off'
    sit = (-HELD_OUT, HELD_UP - MOON_SIT)                       # on the tip, held from below by its foot
    if v < MOON_UP[0] - 0.02 or v >= MOON_DOWN[1]:            # the whole lamp in the hand
        fxs = _held(name, P, u, D, st, 0.0, off=sit, grip=False)
    else:                                                     # the stand in the hand, the moon up there
        fxs = _held('moon_lamp_stand', P, u, D, st, 0.0, off=sit, grip=False, glow=0.0)
        if fxs:
            hx, hy = fxs[0][2]
            B = ITEM_BOX * HELD_BOX / 100.0
            g = C.geom(P)
            k = lerp(1.0, MOON_K, up)
            src = (hx + MOON_C[0] * B, hy + MOON_C[1] * B)     # where the moon sits on the stand
            dst = (PX + MOON_AT[0], MOON_REST_TOP + MOON_AT[1] + 4.0 * math.sin(TWO_PI * v / 1.8))   # still in the sky, not with the pet
            c = (lerp(src[0], dst[0], up), lerp(src[1], dst[1], up) - 30.0 * math.sin(math.pi * up))
            at = (c[0] - MOON_C[0] * B * k, c[1] - MOON_C[1] * B * k)
            fxs += _held('moon_lamp_moon', P, u, D, (True, False), 0.0, at, k=k, grip=False, glow=0.9 * (1.0 - min(1.0, 3.0 * sky)))   # its rays look grey on the blue: gone as the sky opens
    g = C.geom(P)
    centre = (PX + SKY_AT[0], MOON_REST_TOP + SKY_AT[1])        # the sky stays where it is while the pet moves
    f = ease_out(sky) if sky > 0 else 0.0
    fxs.insert(0, ('sky', v, centre, SKY_R[0] * f, SKY_R[1] * f, min(1.0, sky * 1.4), MOON_SHOOT))
    if fxs and fxs[-1][0] == 'held':
        c = fxs[-1][2]
        fxs.append(('twinkle', v - MOON_LIGHT, (c[0] + 20.0, c[1] - 30.0), 1.2))
    return P, fxs


TOP_K = 1.3                       # 陀螺: a little bigger than other treasures in the hand: it is watched
TOP_U = ITEM_BOX * HELD_BOX * TOP_K * 0.84 / 100.0   # logical px a unit of its icon
TOP_H = (ITEMS.TOP_TIP + 8.2) * TOP_U                # its point below its centre
TOP_AT = 298.0                     # its point on the floor, this far right of the body's middle
TOP_OFF = (0.0, -10.0)             # in the hand: held by its cone
TOP_LET, TOP_LAND = 0.5, 0.68      # after PLAY_OUT: flung, let go ... down on its point, spinning
TOP_DETACH = 0.64                  # the whip jerked back just before: the cord comes off it
TOP_LASH = (1.45, 2.05, 2.65)      # the whip's cord round its waist: three lashes in a steady beat, time between them
                                   # for it to slow and wobble (the last a big one: it glows)
TOP_WAIST = 5.0                    # where the cord hits it: this low on its cone (icon units), below the crown
TOP_DRIFT = (2.92, 3.34, 81.0)     # slower and wobbling, it wanders off towards the pet's feet ...
TOP_CATCH = (3.28, 3.48)           # ... and is about to fall over: the pet leans over and stops it with its tip ...
TOP_PICK = (3.48, 3.68)            # ... up into the hand
TOP_SPEED = ((0.45, 0.0), (0.5, 5.0), (0.68, 7.0), (0.95, 4.6), (1.2, 1.9), (1.44, 0.9), (1.48, 3.8), (1.8, 2.4),
             (2.04, 1.3), (2.08, 5.0), (2.4, 3.0), (2.64, 1.7), (2.69, 8.0), (3.12, 5.0), (3.42, 1.0), (3.52, 0.6),
             (3.68, 0.0))   # turns a second: down to a wobble before each lash, up again with it
TOP_STICK = 40.0                   # the whip: its stick, from the arm's tip ...
TOP_CORD = 126.0                   # ... and its cord: a string of beads worked out by itself (Verlet), once a clip
TOP_NODES, TOP_HZ, TOP_G, TOP_DAMP, TOP_ITERS, TOP_WRAP = 16, 240, 6000.0, 0.986, 8, 7
TOP_HOLD = (18.0, 1.12)
_TOP_ARM = [(0.1, TOP_HOLD), (0.4, (58.0, 1.18)), (0.56, (-42.0, 1.24)), (0.62, (-42.0, 1.24)), (0.74, (2.0, 1.16)),
            (1.05, (16.0, 1.12))]
_TOP_WRIST = [(0.4, (-60.0, 0.0)), (0.6, (-60.0, 0.0)), (0.74, (16.0, 0.0)), (1.05, (64.0, 0.0))]
for _i, _tc in enumerate(TOP_LASH):  # each lash: up and back, down onto it, back to the rest
    _big = _i == len(TOP_LASH) - 1
    _TOP_ARM += [(_tc - 0.24, (16.0, 1.12)), (_tc - 0.08, (50.0 if _big else 42.0, 1.18)), (_tc, (-60.0 if _big else -55.0, 1.26)),
                 (_tc + 0.06, (-62.0 if _big else -58.0, 1.26)), (_tc + 0.2, (16.0, 1.12))]   # low a moment, then up
    _TOP_WRIST += [(_tc - 0.24, (64.0, 0.0)), (_tc - 0.08, (78.0, 0.0)), (_tc - 0.035, (6.0, 0.0)), (_tc, (-2.0, 0.0)),
                   (_tc + 0.06, (-22.0, 0.0)), (_tc + 0.2, (64.0, 0.0))]
_TOP_ARM += [(TOP_DRIFT[0], (16.0, 1.12)), (TOP_DRIFT[0] + 0.25, (24.0, 1.1))]                 # the whip up, out of its way
_TOP_WRIST += [(TOP_DRIFT[0], (64.0, 0.0)), (TOP_DRIFT[0] + 0.25, (100.0, 0.0)), (TOP_CATCH[1], (130.0, 0.0)),
               (TOP_PICK[1], (-60.0, 0.0))]
_TOP_TAB = {}
_TOP_SIM = {}


def _top_speed(v):
    return _keys(v, [(t, (sp, 0.0)) for t, sp in TOP_SPEED])[0]


def _top_table():
    """-> (step, [(turned, wobbled)] from v = 0.4): the spin and the wobble's slow circling, added up."""
    if 'tab' not in _TOP_TAB:
        h, a, b, out = 0.002, 0.0, 0.0, []
        for i in range(int(4.6 / h)):
            v = 0.4 + i * h
            out.append((a, b))
            sp = _top_speed(v + 0.5 * h)
            a += sp * h
            b += (1.3 + 1.3 * clamp((2.4 - sp) / 1.8, 0.0, 1.0)) * h
        _TOP_TAB['tab'] = out
    return _TOP_TAB['tab']


def _top_turns(v):
    tab = _top_table()
    x = clamp((v - 0.4) / 0.002, 0.0, len(tab) - 2.0)
    i = int(x); f = x - i
    return lerp(tab[i][0], tab[i + 1][0], f), lerp(tab[i][1], tab[i + 1][1], f)


def _top_rot(x, y, r):
    """A point of the top's icon (units, from its centre) on the screen, the icon turned by r (degrees, against the clock)."""
    q = math.radians(r)
    return (x * math.cos(q) + y * math.sin(q)) * TOP_U, (-x * math.sin(q) + y * math.cos(q)) * TOP_U


def _top_floor(v):
    """The top spinning on the floor at v: (its centre, its turn (degrees), lean towards you, blur, turned)."""
    sp = _top_speed(v)
    turned, circ = _top_turns(v)
    A = 12.0 * clamp((2.4 - sp) / 1.6, 0.0, 1.0) ** 1.2         # it wobbles as it slows, circling faster
    th = A * math.cos(TWO_PI * circ)
    lean = math.sin(math.radians(A)) * math.sin(TWO_PI * circ)
    if v >= TOP_LAND:                                          # it lands with a little shudder
        th += 7.0 * math.exp(-(v - TOP_LAND) / 0.15) * math.sin(TWO_PI * 7.0 * (v - TOP_LAND))
    for tc in TOP_LASH:                                        # pushed a little by each lash
        th -= 4.0 * bump(v, tc, tc + 0.14)
    stop = smooth((v - TOP_CATCH[0] - 0.06) / (TOP_CATCH[1] - TOP_CATCH[0] - 0.06))
    th = lerp(th, 6.0, stop); lean *= 1.0 - stop               # stopped by the pet's tip, leaning a little
    tx, ty = PX + TOP_AT - TOP_DRIFT[2] * smooth((v - TOP_DRIFT[0]) / (TOP_DRIFT[1] - TOP_DRIFT[0])), FLOOR_Y
    c = (tx - TOP_H * math.sin(math.radians(th)), ty - TOP_H * math.cos(math.radians(th)))
    return c, th, lean, smooth((sp - 1.2) / 1.4), turned, tx


def _top_body(u, D):
    """The pet at u: -> (pose, (in the hand, behind), the whip's angle (degrees, against the clock), the top's centre
    and turn in the hand)."""
    P = make_pose(); v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    ra, re = _keys(v, _TOP_ARM)
    wrist = _keys(v, _TOP_WRIST)[0]
    L3 = TOP_LASH[-1]
    wind = smooth((v - 0.1) / 0.3) * (1.0 - smooth((v - 0.42) / 0.1))      # back to fling it ...
    throw = bump(v, 0.42, 0.78)                                             # ... and down it goes
    P['tilt'] += 4.0 * wind - 6.0 * throw
    P['sy'] *= 1 + 0.02 * wind - 0.03 * throw
    P['legx'] = -6.0 * throw
    P['lift'] += 12.0 * bump(v, 0.8, 1.06)                    # a hop: it spins!
    a, x = P['nubL']; P['nubL'] = (a + 25.0 * throw + 55.0 * bump(v, L3 + 0.07, L3 + 0.57), x)
    for tc in TOP_LASH:
        up, hit = bump(v, tc - 0.24, tc - 0.02), bump(v, tc - 0.06, tc + 0.14)
        P['tilt'] += 3.0 * up - 5.0 * hit
        P['legx'] -= 8.0 * hit                                 # down low with the sweep
        P['lift'] += 8.0 * bump(v, tc + 0.02, tc + 0.24)
        P['sy'] *= 1 - 0.04 * bump(v, tc - 0.03, tc + 0.08)
        a, x = P['nubL']; P['nubL'] = (a + 15.0 * hit, x)
    P['tilt'] += 3.5 * math.sin(TWO_PI * (v - L3 - 0.07) / 0.6) * bump(v, L3 + 0.12, L3 + 0.62)   # delighted: it glows
    # eyes: on it in the hand, shut tight to fling it, wide as it lands, stars, happy; wide when it wobbles; on it
    # at the lashes, tight at each; stars when it glows, wide when it tips over, happy when it is caught
    hand_look = (0.9, -0.1)
    floor_look = (0.8, 0.7)
    f = smooth((v - 0.3) / 0.25)
    P['look'] = (lerp(hand_look[0], floor_look[0], f), lerp(hand_look[1], floor_look[1], f))
    if v >= TOP_PICK[0]:
        g = smooth((v - TOP_PICK[0]) / 0.2); P['look'] = (lerp(floor_look[0], 0.9, g), lerp(floor_look[1], -0.1, g))
    eyes = ((0.38, 0.56, 'squeeze'), (0.56, 0.78, 'wide'), (0.78, 1.15, 'star'),
            (L3 + 0.05, L3 + 0.37, 'star'), (L3 + 0.37, L3 + 0.59, 'happy'), (L3 + 0.59, TOP_PICK[0], 'wide'), (TOP_PICK[0] + 0.05, mid, 'happy'))
    for a_, b_, e_ in eyes:
        if a_ <= v < b_: P['eyes'] = e_
    for i, tc in enumerate(TOP_LASH):                          # it wobbles: wide; the lash: tight; it spins up: happy
        if tc - 0.26 <= v < tc - 0.02: P['eyes'] = 'wide'
        elif tc - 0.02 <= v < tc + 0.07: P['eyes'] = 'squeeze'
        elif tc + 0.07 <= v < tc + 0.3 and i < len(TOP_LASH) - 1: P['eyes'] = 'happy'
    P['blush'] = 0.6 * bump(v, 0.78, 1.6) + 0.7 * bump(v, L3 + 0.02, mid + 0.2)
    _nod(P, v, TOP_PICK[1] + 0.02, 1, 0.3)
    if u > D - PLAY_AWAY + 0.1: P['eyes'] = 'open'
    # it leans over to the tipping top and catches it under its cone, and up it comes
    pk = smooth((v - TOP_CATCH[0]) / (TOP_CATCH[1] - TOP_CATCH[0]))
    g = smooth((v - TOP_PICK[0]) / (TOP_PICK[1] - TOP_PICK[0]))
    if pk > 0.0:
        c, th = _top_floor(TOP_CATCH[1])[:2]
        dx, dy = _top_rot(-4.0, ITEMS.TOP_FACE - ITEMS.TOP_RX * ITEMS.TOP_E, th)   # its tip on the back of its face
        tgt = (c[0] + dx, c[1] + dy)
        P['tilt'] -= 4.0 * pk * (1.0 - g)
        P['legx'] -= 13.0 * pk * (1.0 - g)
        ta = _reach(P, tgt[1])
        tip = _tip_at(P, ta, FLOOR_EXT)
        P['x'] += (tgt[0] - tip[0]) * pk * (1.0 - g)
        ra = lerp(lerp(ra, ta, pk), TOP_HOLD[0], g)
        re = lerp(lerp(re, FLOOR_EXT, pk), TOP_HOLD[1], g)
    P['nubR'] = make_pose()['nubR']
    st = _play_arm(P, u, D, (ra, re))
    gm = C.geom(P)
    (tx, ty), (px, py) = gm['tipR'], gm['pivR']
    ang = math.degrees(math.atan2(-(ty - py), tx - px)) + wrist
    hand_c = (tx + HELD_OUT + TOP_OFF[0], ty - HELD_UP + TOP_OFF[1])
    hand_r = P['tilt'] + 0.45 * (P['nubR'][0] - 40.0)
    return P, st, ang, hand_c, hand_r


def _top_flight(v, D):
    """The top in the air, flung: -> (centre, turn, how much of the cord is still round it)."""
    _, _, _, c0, r0 = _top_body(TOP_LET + PLAY_OUT, D)
    e = (PX + TOP_AT, FLOOR_Y - TOP_H)
    f = clamp((v - TOP_LET) / (TOP_LAND - TOP_LET), 0.0, 1.0)
    k = (e[0] + 6.0, c0[1] + 0.35 * (e[1] - c0[1]))
    c = ((1 - f) ** 2 * c0[0] + 2 * f * (1 - f) * k[0] + f * f * e[0], (1 - f) ** 2 * c0[1] + 2 * f * (1 - f) * k[1] + f * f * e[1])
    return c, lerp(r0, 0.0, smooth(f)), 1.0 - f


def _top_waist(c, r, wound):
    """Where the cord comes off the coils round the top (the lowest one's right end)."""
    n = max(1, int(math.ceil(6 * wound - 1e-6)))
    y = ITEMS.TOP_BAND + 5.0 + 3.6 * (n - 1)
    dx, dy = _top_rot(ITEMS._top_hw(y) + 1.4, y + 2.2, r)
    return c[0] + dx, c[1] + dy


def _top_ends(v, D):
    """The cord's ends at v: the stick's end, the top's waist while it is wound round it (else None), the cord's length."""
    P, st, ang, hc, hr = _top_body(v + PLAY_OUT, D)
    tip = C.geom(P)['tipR']
    q = math.radians(ang)
    S = (tip[0] + TOP_STICK * math.cos(q), tip[1] - TOP_STICK * math.sin(q))
    if v >= TOP_DETACH: return S, None, TOP_CORD
    if v < TOP_LET: W = _top_waist(hc, hr, 1.0)
    else:
        c, r, wound = _top_flight(v, D)
        W = _top_waist(c, r, wound)
    return S, W, clamp(math.hypot(W[0] - S[0], W[1] - S[1]) * 1.06 + 4.0, 20.0, TOP_CORD)


def _top_guide(v):
    """At a lash the cord's end wraps round the front of the top's crown: -> (how much, the beads' places) or None."""
    for tc in TOP_LASH:
        w = smooth((v - tc + 0.035) / 0.035) * (1.0 - smooth((v - tc - 0.05) / 0.05))
        if w > 0.0:
            c, th, lean = _top_floor(v)[:3]
            e = clamp(ITEMS.TOP_E + lean, 0.06, 0.55)
            hw = ITEMS._top_hw(TOP_WAIST)
            pts = []
            for j in range(TOP_WRAP):
                q = math.radians(-90.0 + 105.0 * j / (TOP_WRAP - 1))
                dx, dy = _top_rot(hw * math.sin(q), TOP_WAIST + hw * e * math.cos(q), th)
                pts.append((c[0] + dx, c[1] + dy))
            return w, pts
    return None


def _top_sim(D):
    """The whip's cord over the whole clip, worked out once: a string of beads hung from the stick's end, pulled by
    its weight, held to its length; tied to the top until the jerk, wrapped round its crown at each lash."""
    key = round(D, 4)
    if key in _TOP_SIM: return _TOP_SIM[key]
    v0, v1 = PLAY_GRAB - PLAY_OUT, D - PLAY_OUT
    grid = [_top_ends(v0 + i / 120.0, D) for i in range(int((v1 - v0) * 120) + 3)]
    def ends(v):
        x = (v - v0) * 120.0; i = min(len(grid) - 2, max(0, int(x))); f = x - i
        (S0, W0, L0), (S1, W1, L1) = grid[i], grid[i + 1]
        S = (lerp(S0[0], S1[0], f), lerp(S0[1], S1[1], f))
        W = None if W0 is None or W1 is None else (lerp(W0[0], W1[0], f), lerp(W0[1], W1[1], f))
        return S, W, lerp(L0, L1, f)
    n, dt = TOP_NODES, 1.0 / TOP_HZ
    S, W, La = ends(v0)
    pos = [(lerp(S[0], W[0], j / (n - 1.0)), lerp(S[1], W[1], j / (n - 1.0))) for j in range(n)]
    prev = list(pos)
    out = []
    for step in range(int((v1 - v0) * TOP_HZ) + 2):
        v = v0 + step * dt
        S, W, La = ends(v)
        seg = La / (n - 1.0)
        damp = TOP_DAMP - 0.015 * bump(v, TOP_DETACH, TOP_DETACH + 0.5)
        for tc in TOP_LASH:                                    # pulled off the top: it trails, it does not loop over
            damp -= 0.05 * smooth((v - tc - 0.03) / 0.04) * (1.0 - smooth((v - tc - 0.3) / 0.1))
        for j in range(1, n):
            (x, y), (px_, py_) = pos[j], prev[j]
            prev[j] = (x, y)
            pos[j] = (x + (x - px_) * damp, y + (y - py_) * damp + TOP_G * dt * dt)
        pos[0] = S
        if W is not None: pos[-1] = W
        fixed_end = W is not None
        for it in range(TOP_ITERS):
            for j in range(n - 1):
                (ax, ay), (bx, by) = pos[j], pos[j + 1]
                dx, dy = bx - ax, by - ay
                d = math.hypot(dx, dy) or 1e-6
                wa = 0.0 if j == 0 else 0.5
                wb = 0.0 if (j + 1 == n - 1 and fixed_end) else 0.5
                if wa + wb == 0.0: continue
                k = (d - seg) / d / (wa + wb)
                pos[j] = (ax + dx * k * wa, ay + dy * k * wa)
                pos[j + 1] = (bx - dx * k * wb, by - dy * k * wb)
            for j in range(1, n - 2):                          # stiff a little: no bend sharper than this
                (ax, ay), (bx, by) = pos[j], pos[j + 2]
                dx, dy = bx - ax, by - ay
                d = math.hypot(dx, dy) or 1e-6
                if d < 1.8 * seg:
                    k = 0.4 * (d - 1.8 * seg) / d
                    pos[j] = (ax + dx * k, ay + dy * k)
                    if not (j + 2 == n - 1 and fixed_end): pos[j + 2] = (bx - dx * k, by - dy * k)
        gd = _top_guide(v)
        if gd:
            w, pts = gd
            for j, (gx, gy) in enumerate(pts):
                i = n - TOP_WRAP + j
                x, y = pos[i]
                pos[i] = (lerp(x, gx, 0.3 * w), lerp(y, gy, 0.3 * w))
                prev[i] = (lerp(prev[i][0], pos[i][0], w), lerp(prev[i][1], pos[i][1], w))   # held there: no speed kept
        settle = max([smooth((v - tc - 0.07) / 0.06) * (1.0 - smooth((v - tc - 0.3) / 0.12)) for tc in TOP_LASH]
                     + [smooth((v - TOP_DETACH - 0.12) / 0.08) * (1.0 - smooth((v - TOP_DETACH - 0.4) / 0.15))])
        if settle > 0.0:                                       # pulled off: it falls to hang, no loop over the stick
            for j in range(1, n):
                hx, hy = S[0], S[1] + j * seg * 0.97
                x, y = pos[j]
                pos[j] = (lerp(x, hx, 0.05 * settle), lerp(y, hy, 0.05 * settle))
        for j in range(1, n):                                  # the floor
            x, y = pos[j]
            if y > FLOOR_Y - 2.0:
                pos[j] = (x, FLOOR_Y - 2.0)
                prev[j] = (lerp(prev[j][0], x, 0.3), prev[j][1])
        out.append(list(pos))
    _TOP_SIM[key] = (v0, out)
    return _TOP_SIM[key]


def _top_cord(v, D):
    v0, out = _top_sim(D)
    return out[min(len(out) - 1, max(0, int(round((v - v0) * TOP_HZ))))]


def draw_top_shadow(fr, sc, centre, rx, alpha):
    """A small soft shadow on the floor under the spinning top."""
    if alpha <= 0.01: return
    ox, oy = centre
    def paint(d, X, Y, k):
        for i, f_ in enumerate((1.0, 0.7)):
            d.ellipse((X(ox - rx * f_), Y(oy - 5.0 * f_), X(ox + rx * f_), Y(oy + 5.0 * f_)), fill=(10, 8, 20, int(34 + 20 * i)))
    draw_prop_layer(fr, sc, ox - rx - 4, oy - 10, ox + rx + 4, oy + 10, alpha, paint)


def draw_whirl(fr, sc, centre, rot, alpha, t):
    """Lines of the spin round the top's crown and cone, either side (it is going round fast)."""
    if alpha <= 0.02: return
    cx, cy = centre
    def paint(d, X, Y, k):
        w = int(max(1, 3.0 * k))
        for yb, rx, ry, span, j in ((-19.0, ITEMS.TOP_RX + 9.0, 13.0, 34.0, 0), (6.0, 25.0, 9.0, 26.0, 1)):
            for side in (-1, 1):
                a0 = (180.0 if side < 0 else 0.0) - span / 2 + 6.0 * math.sin(TWO_PI * (t * 3.0 + 0.3 * j + 0.5 * side))
                pts = []
                for i in range(9):
                    q = math.radians(a0 + span * i / 8.0)
                    dx, dy = _top_rot(rx * math.cos(q), yb + ry * math.sin(q), rot)
                    pts.append((X(cx + dx), Y(cy + dy)))
                d.line(pts, fill=(118, 126, 158, 255), width=w, joint='curve')
    m = (ITEMS.TOP_RX + 14.0) * TOP_U
    draw_prop_layer(fr, sc, cx - m, cy - m, cx + m, cy + m + 20, alpha, paint)


def _smooth_line(pts):
    """Corner cutting (twice): a string of beads drawn as a soft curve."""
    for _ in range(2):
        out = [pts[0]]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            out += [(0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by), (0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by)]
        out.append(pts[-1])
        pts = out
    return pts


def draw_whip(fr, sc, P, fx, part):
    """The whip ('whip', the stick's angle, the cord's beads, behind): a short wooden stick out of the arm's tip and
    its cord; in front, the arm's tip again over the stick's end (it holds it); behind the body while the arm is."""
    _, ang, cord, behind = fx
    if (part == 'back') != behind: return
    tip = C.geom(P)['tipR']
    q = math.radians(ang)
    ax = (math.cos(q), -math.sin(q))
    end = (tip[0] + TOP_STICK * ax[0], tip[1] + TOP_STICK * ax[1])
    line = _smooth_line([end] + list(cord[1:]))
    def paint(d, X, Y, k):
        _bar(d, X, Y, tip, ax, -6.0, TOP_STICK, 4.4, 3.6, (112, 72, 42, 255))
        _bar(d, X, Y, tip, ax, 2.0, TOP_STICK - 3.0, 1.2, 1.0, (170, 124, 82, 255))
        d.line([(X(x), Y(y)) for x, y in line], fill=ITEMS.CORD + (255,), width=int(max(5.6, 3.6 * k)), joint='curve')   # 1.4 px at least: seen at 50%
        ex, ey = line[-1]
        d.ellipse((X(ex - 2.6), Y(ey - 2.6), X(ex + 2.6), Y(ey + 2.6)), fill=ITEMS.CORD + (255,))
        d.ellipse((X(end[0] - 4.8), Y(end[1] - 4.8), X(end[0] + 4.8), Y(end[1] + 4.8)), fill=(96, 60, 34, 255))
        if part == 'front':
            L = C.NUB_L * P['nubR'][1]
            _poly(d, X, Y, _arm_piece(P, 'R', L - 30, L, C.NUB_T, 12), C.NUB_COL + (255,))
            hl1 = 0.85 * L - 2.7
            if hl1 > L - 28:
                _poly(d, X, Y, _arm_piece(P, 'R', L - 28, hl1, C.NUB_T * 0.16, 4, -C.NUB_T * 0.28), C.NUB_HI + (255,))
            _poly(d, X, Y, _body_poly(P), (0, 0, 0, 0))
    draw_prop_layer(fr, sc, *(_box_around(line + [tip, end], 30) + (1.0, paint)))


def play_top_pose(u, D=PLAY_TOP_LEN, item=None):
    """陀螺, 抽陀螺: out it comes with the whip's cord wound round it; it draws back and flings it down at its feet,
    jerking the whip back so the cord comes off: down it lands, spinning (a hop: stars).  It slows, starts to wobble
    (wide eyes): up goes the whip, and down onto it, the cord wrapping round its crown and pulled off: it spins up
    again; three lashes in a beat, the pet hopping with each, the last a big one: it glows.  Slower and slower, it
    tips over; the pet leans over and catches it, and puts it away, pleased.  The whip's cord swings by itself."""
    P, st, ang, hand_c, hand_r = _top_body(u, D)
    v = u - PLAY_OUT; mid = D - PLAY_OUT - PLAY_AWAY
    name = 'spin_top_run'
    fxs = []
    if v < TOP_LET:                                            # in the hand, the cord round it
        fxs += _held(name, P, u, D, st, 0.0, off=TOP_OFF, k=TOP_K, glow=1.0 - smooth((v - 0.3) / 0.2),
                     t_item=(0.0, 0.0, 0.0, 1.0))
    elif v < TOP_LAND:                                         # in the air, the cord coming off it
        c, r, wound = _top_flight(v, D)
        tu = _top_turns(v)[0]
        fxs += _held(name, P, u, D, (True, False), r, c, k=TOP_K, grip=False, glow=0.0, t_item=(tu, 1.0, 0.0, wound))
    elif v < TOP_PICK[1]:                                      # spinning on the floor; caught and taken up
        c, th, lean, blur, tu, tx = _top_floor(v)
        lit = smooth((v - TOP_LASH[-1]) / 0.15) * (1.0 - smooth((v - TOP_LASH[-1] - 0.42) / 0.3))
        fxs.append(('tshadow', (tx, FLOOR_Y), 27.0 + 9.0 * abs(math.sin(math.radians(th))), 1.0 - smooth((v - TOP_PICK[0]) / 0.1)))
        if v >= TOP_PICK[0]:
            g = smooth((v - TOP_PICK[0]) / (TOP_PICK[1] - TOP_PICK[0]))
            c = (lerp(c[0], hand_c[0], g), lerp(c[1], hand_c[1], g)); th = lerp(th, hand_r, g)
        fxs += _held(name, P, u, D, (True, False), th, c, k=TOP_K, grip=v >= TOP_PICK[0] + 0.1,
                     glow=lit + smooth((v - TOP_PICK[0]) / 0.2), t_item=(tu, blur, lean, 0.0))
        yb = 0.5 * (ITEMS.TOP_FACE + ITEMS.TOP_BAND)
        dx, dy = _top_rot(0.0, yb, th)
        fxs.append(('whirl', (c[0], c[1]), th, blur * (1.0 - smooth((v - TOP_CATCH[0]) / 0.1)), v))
        for i, tc in enumerate(TOP_LASH):                      # sparks where the cord hits it
            ex, ey = _top_rot(-ITEMS._top_hw(TOP_WAIST), TOP_WAIST, _top_floor(tc)[1])
            cc = _top_floor(tc)[0]
            fxs.append(('spark', v - tc, (cc[0] + ex, cc[1] + ey), 0.8 if i < 2 else 1.1))
        fxs.append(('twinkle', v - TOP_LASH[-1] - 0.05, (c[0] + dx, c[1] + dy - 30.0), 1.2))
    else:
        fxs += _held(name, P, u, D, st, 0.0, off=TOP_OFF, k=TOP_K, t_item=(_top_turns(TOP_PICK[1])[0], 0.0, 0.0, 0.0))
    for side in (-1, 1):
        fxs.append(('puff', v - TOP_LAND, (PX + TOP_AT + 34.0 * side, FLOOR_Y - 4.0)))
    if st[0]:
        whip = ('whip', ang, _top_cord(v, D), st[1])
        if TOP_DRIFT[0] - 0.05 <= v:                           # behind the arm and the top from now on (it comes near)
            fxs.append(whip[:3] + (True,))
        else: fxs.append(whip)
    return P, fxs


PLAY_POSES = {'look': (play_look_pose, PLAY_LOOK_LEN), 'toss': (play_toss_pose, PLAY_TOSS_LEN),
              'listen': (play_listen_pose, PLAY_LISTEN_LEN), 'show': (play_show_pose, PLAY_SHOW_LEN),
              'duck': (play_duck_pose, PLAY_DUCK_LEN), 'gold': (play_gold_pose, PLAY_GOLD_LEN),
              'biscuit': (play_biscuit_pose, PLAY_BISCUIT_LEN), 'bottle': (play_bottle_pose, PLAY_BOTTLE_LEN),
              'hourglass': (play_hourglass_pose, PLAY_HOURGLASS_LEN), 'bug': (play_bug_pose, PLAY_BUG_LEN),
              'plane': (play_plane_pose, PLAY_PLANE_LEN), 'balloon': (play_balloon_pose, PLAY_BALLOON_LEN),
              'robot': (play_robot_pose, PLAY_ROBOT_LEN), 'cube': (play_cube_pose, PLAY_CUBE_LEN),
              'moon': (play_moon_pose, PLAY_MOON_LEN), 'top': (play_top_pose, PLAY_TOP_LEN)}


def draw_held(fr, sc, P, fx, part):
    """A treasure drawn into the frame ('held', name, centre, rot, size, behind, gripped, glow, u): its glow and,
    while the arm is behind the back, the treasure itself behind the body (part 'back'); else the treasure in
    front, and the arm's tip over its lower edge if it is in the hand (part 'front')."""
    _, name, (cx, cy), rot, k, behind, grip, glow, u = fx[:9]
    sqx, sqy = fx[9] if len(fx) > 9 else (1.0, 1.0)
    t_item = fx[10] if len(fx) > 10 else None                 # set by the play (the hourglass's sand): no glint then
    name = name or PREVIEW_ITEM
    if name is None or k <= 0.02: return
    t = (u / 2.0) % 1.0                                        # its own little loop: 2 s, as the player plays it
    n = max(4, int(round(ITEM_BOX * HELD_BOX * k * sc.s)))
    if part == 'back' and not behind:
        if glow > 0.02:
            au = ITEMS.draw_aura(ITEMS.ITEMS[name][2], n, t)
            au.putalpha(au.getchannel('A').point(lambda a_: int(a_ * glow + 0.5)))
            fr.alpha_composite(au, (int(round(cx * sc.s - au.size[0] / 2.0)), int(round(cy * sc.s - au.size[1] / 2.0))))
        return
    if (part == 'back') != behind: return
    im = ITEMS.draw_item(name, n, rim=HELD_RIM, t=t if t_item is None else t_item, shine=t_item is None)
    if abs(sqx - 1.0) > 0.01 or abs(sqy - 1.0) > 0.01:      # squeezed: flatter and wider, its bottom where it was
        w2, h2 = max(2, int(round(n * sqx))), max(2, int(round(n * sqy)))
        sq = Image.new('RGBA', (max(n, w2), n), (0, 0, 0, 0))
        sq.alpha_composite(im.resize((w2, h2), Image.LANCZOS), ((sq.size[0] - w2) // 2, n - h2))
        im = sq
    if abs(rot) > 0.5: im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    fr.alpha_composite(im, (int(round(cx * sc.s - im.size[0] / 2.0)), int(round(cy * sc.s - im.size[1] / 2.0))))
    if part == 'front' and grip:
        L = C.NUB_L * P['nubR'][1]
        def tip_paint(d, X, Y, k_):                            # the arm's tip again, over it but not over the body
            _poly(d, X, Y, _arm_piece(P, 'R', L - 30, L, C.NUB_T, 12), C.NUB_COL + (255,))
            hl1 = 0.85 * L - 2.7
            if hl1 > L - 28:
                _poly(d, X, Y, _arm_piece(P, 'R', L - 28, hl1, C.NUB_T * 0.16, 4, -C.NUB_T * 0.28), C.NUB_HI + (255,))
            _poly(d, X, Y, _body_poly(P), (0, 0, 0, 0))
        tip = C.geom(P)['tipR']
        draw_prop_layer(fr, sc, *_box_around((tip,), 60), 1.0, tip_paint)


def draw_pit(fr, sc, P, u, heap, fly, part, stroke=DIG_STROKE):
    """The hole it digs, in front of its feet: a low ring of earth with the dark hole in the middle (heap: 0..1 of
    its size), and the clods each stroke throws up in front of it (fly: their opacity), a tiny star among them
    once a loop.  The clods are periodic in DIG_STROKE, the star and the clod for the face in RUMMAGE_LEN."""
    if heap <= 0.01: return
    if part == 'back':                                         # the lumps fly behind it: they never cross its face
        if fly > 0.01: _draw_clods(fr, sc, P['x'], u, fly, stroke)
        return
    x0, y0 = P['x'], FLOOR_Y + 5.0
    W_, H_, HOLE = PIT
    w = W_ * (0.55 + 0.45 * heap); h = H_ * heap; hole = HOLE * heap
    base, light, dark, pit, deep = EARTH
    def prof(x, hh, ww):
        q = x / ww
        return hh * max(0.0, 1.0 - q * q) ** 1.1 if abs(q) < 1 else 0.0
    def paint(d, X, Y, k):
        n = 48
        xs = [w * (2.0 * i / n - 1) for i in range(n + 1)]
        _poly(d, X, Y, [(x0 + x, y0 - prof(x, h, w) + 0.3 * h * math.exp(-(x / (1.15 * hole)) ** 2)) for x in xs], base + (255,))
        _poly(d, X, Y, [(x0 - 6 + 0.8 * x, y0 - 0.2 * h - prof(0.8 * x, 0.74 * h, 0.8 * w) + 0.34 * h * math.exp(-(0.8 * x / (1.2 * hole)) ** 2))
                        for x in xs] + [(x0 - 6 + 0.8 * w, y0 - 0.2 * h)], light + (255,))
        _poly(d, X, Y, [(x0 + x, y0 - prof(x, 0.2 * h, w)) for x in xs], dark + (255,))
        cy = y0 - 0.56 * h
        d.ellipse((X(x0 - hole), Y(cy - 0.2 * hole), X(x0 + hole), Y(cy + 0.2 * hole)), fill=pit + (255,))
        d.ellipse((X(x0 - 0.76 * hole), Y(cy - 0.06 * hole), X(x0 + 0.76 * hole), Y(cy + 0.2 * hole)), fill=deep + (255,))
        for j in range(9):
            gx = x0 + w * (hrand('pp', j) * 1.6 - 0.8)
            if abs(gx - x0) < 1.15 * hole: continue
            gy = y0 - prof(gx - x0, h, w) * (0.3 + 0.4 * hrand('pq', j)); r = (2.8 + 2.6 * hrand('pr', j)) * (0.5 + 0.5 * heap)
            d.ellipse((X(gx - r), Y(gy - r), X(gx + r), Y(gy + r)), fill=((214, 204, 190) if j % 3 == 0 else dark) + (255,))
    draw_prop_layer(fr, sc, x0 - W_ - 10, y0 - H_ - 14, x0 + W_ + 10, y0 + 4, 1.0, paint)
    if fly <= 0.01: return
    G = 1500.0
    def dust(d, X, Y, k):                                      # a low puff of dust at the hole with each stroke
        for side in (-1, 1):
            t = (u - (0.0 if side > 0 else stroke / 2)) % stroke
            f = t / stroke
            for j_ in range(3):
                r = (12 + 20 * f) * (1.0 - 0.18 * j_)
                x = x0 + side * (152 + 40 * f + 20 * j_); y = FLOOR_Y - 22 - 30 * f - 8 * j_ * (1 - f)
                d.ellipse((X(x - r), Y(y - 0.8 * r), X(x + r), Y(y + 0.8 * r)), fill=(206, 184, 156, int(170 * (1 - f) ** 1.3)))
    draw_prop_layer(fr, sc, x0 - 240, FLOOR_Y - 140, x0 + 240, FLOOR_Y + 4, fly, dust)


def _draw_clods(fr, sc, x0, u, fly, stroke=DIG_STROKE):
    G = 1500.0; base, dark = EARTH[0], EARTH[2]
    def clods(d, X, Y, k):                                     # lumps of earth thrown up and out, turning as they fly
        for side in (-1, 1):
            for b in range(int(round(RUMMAGE_LEN / stroke))):  # a lump may be in the air for longer than one stroke
                t_emit = (0.0 if side > 0 else stroke / 2) + b * stroke
                for j_ in range(5):
                    t = (u - t_emit - 0.03 * j_) % RUMMAGE_LEN
                    vy = -(520 + 200 * hrand('gy', side, b, j_)); vx = side * (150 + 110 * hrand('gx', side, b, j_))
                    life = min(0.95, -2 * vy / G + 0.05, (236.0 - 40.0) / abs(vx))
                    if t > life: continue
                    gx = x0 + side * 40 + vx * t; gy = FLOOR_Y - 44 + vy * t + 0.5 * G * t * t
                    a = int(255 * clamp((life - t) / 0.08, 0.0, 1.0))
                    if j_ == 2 and b == 0 and side > 0:        # once a loop a tiny star comes up with the earth
                        R = 20.0
                        d.polygon([(X(a_), Y(b_)) for a_, b_ in star_poly(gx, gy, R, R * 0.34, n=4, rot=-90 + 220 * t)], fill=(255, 214, 90, a))
                        d.polygon([(X(a_), Y(b_)) for a_, b_ in star_poly(gx, gy, R * 0.5, R * 0.2, n=4, rot=-90 + 220 * t)], fill=(255, 244, 196, a))
                        continue
                    r = 8.0 + 8.0 * hrand('gr', side, b, j_); rot = 360 * hrand('g0', side, b, j_) + side * 420 * t
                    col = dark if j_ % 2 == 0 else base
                    pts = []
                    for m in range(6):                         # an uneven lump, not a ball
                        q_ = math.radians(rot + 60 * m); rr_ = r * (0.72 + 0.5 * hrand('gs', side, b, j_, m))
                        pts.append((X(gx + rr_ * math.cos(q_)), Y(gy + rr_ * math.sin(q_))))
                    d.polygon(pts, fill=col + (a,))
    draw_prop_layer(fr, sc, x0 - 250, FLOOR_Y - 330, x0 + 250, FLOOR_Y + 4, fly, clods)


def _on_body(P, fx_, fy_):
    """A point of the body (in body widths / heights from its centre), where it is on screen: squashed and tilted with it."""
    g0 = C.geom(dict(P, tilt=0.0))
    pt = (P['x'] + fx_ * g0['bw'], g0['cy'] + fy_ * g0['bh'])
    if abs(P['tilt']) > 1e-3:
        piv = C.tilt_pivot(P, g0['bw'], g0['feet'])
        pt = rot_pts([pt], piv[0], piv[1], P['tilt'])[0]
    return pt


def draw_dirt(fr, sc, P, u, amount, shaken):
    """The earth that has landed on it: blobs on its face and body (amount: 0..1, they come one by one), the one
    of SPLAT_SPOT hit again once a loop (a clod flies up to it, a splash); shaken: 0..1, they fly off sideways."""
    if amount <= 0.01 or shaken >= 0.999: return
    base, light, dark = (150, 106, 72), (176, 132, 94), EARTH[2]
    c = u % RUMMAGE_LEN if shaken <= 0.0 else -1.0
    n = len(DIRT_SPOTS)
    def paint(d, X, Y, k):
        for i, (fx_, fy_, r0) in enumerate(DIRT_SPOTS):
            vis = clamp(amount * n - i, 0.0, 1.0)
            if vis <= 0.0: continue
            x, y = _on_body(P, fx_, fy_); r = r0 * ease_out_back(vis, 2.4) if vis < 1.0 else r0
            if shaken > 0.0:                                   # thrown off: out to its side and down, smaller
                go = clamp(shaken * 1.5 - 0.08 * i, 0.0, 1.0)
                side = 1 if fx_ >= 0 else -1
                x += side * 150.0 * ease_out(go) * (0.6 + 0.4 * hrand('fl', i)); y += -40.0 * math.sin(math.pi * go) + 150.0 * go * go
                r *= 1.0 - 0.75 * go
                if go >= 1.0: continue
            elif i == SPLAT_SPOT and SPLAT_AT <= c < SPLAT_AT + 0.2:
                r *= 1.0 + 0.7 * (1.0 - (c - SPLAT_AT) / 0.2)       # fresh: bigger for a moment
            ph = 1.3 * i                                       # a flat splash of mud: a lobed blot and a few drops by it
            blot = [(x + r * (0.87 + 0.13 * math.cos(5 * q_ + ph)) * math.cos(q_) * 1.15, y + r * (0.87 + 0.13 * math.cos(5 * q_ + ph)) * math.sin(q_) * 0.9)
                    for q_ in (TWO_PI * m / 48 for m in range(48))]
            _poly(d, X, Y, blot, base + (255,))
            _poly(d, X, Y, [(x + (bx - x) * 0.55 - 0.06 * r, y + (by - y) * 0.55 - 0.08 * r) for bx, by in blot], light + (255,))
            for m in range(3):
                q_ = ph + 2.1 * m + 0.5; rr_ = r * (0.16 + 0.05 * m); dd = r * (1.35 + 0.12 * m)
                d.ellipse((X(x + dd * math.cos(q_) - rr_), Y(y + dd * 0.8 * math.sin(q_) - rr_), X(x + dd * math.cos(q_) + rr_), Y(y + dd * 0.8 * math.sin(q_) + rr_)),
                          fill=base + (255,))
        if shaken <= 0.0 and amount >= 1.0 and SPLAT_AT - 0.2 <= c < SPLAT_AT:      # the clod on its way up to the face
            f = (c - (SPLAT_AT - 0.2)) / 0.2
            tx, ty = _on_body(P, *DIRT_SPOTS[SPLAT_SPOT][:2])
            x = lerp(P['x'] + 10, tx, f); y = lerp(FLOOR_Y - 40, ty, f) - 46 * math.sin(math.pi * f)
            d.ellipse((X(x - 12), Y(y - 12), X(x + 12), Y(y + 12)), fill=base + (255,))
            d.ellipse((X(x - 7), Y(y - 8), X(x + 1), Y(y)), fill=light + (255,))
        if shaken <= 0.0 and SPLAT_AT <= c < SPLAT_AT + 0.16:   # the splash
            f = (c - SPLAT_AT) / 0.16
            tx, ty = _on_body(P, *DIRT_SPOTS[SPLAT_SPOT][:2])
            for q in range(6):
                a_ = TWO_PI * q / 6 + 0.3; r_ = 22 + 34 * ease_out(f); rr_ = 5.0 * (1.0 - f)
                d.ellipse((X(tx + r_ * math.cos(a_) - rr_), Y(ty + r_ * math.sin(a_) - rr_), X(tx + r_ * math.cos(a_) + rr_), Y(ty + r_ * math.sin(a_) + rr_)),
                          fill=dark + (255,))
    g = C.geom(dict(P, tilt=0.0))
    draw_prop_layer(fr, sc, P['x'] - 245, g['top'] - 60, P['x'] + 245, FLOOR_Y + 4, 1.0, paint)


def draw_puff(fr, sc, t, origin):
    """A small puff of dust: three pale blobs that swell, drift up and fade; t is the time since it."""
    if t < 0 or t >= 0.36: return
    f = t / 0.36; ox, oy = origin
    def paint(d, X, Y, k):
        for j, (dx, dy) in enumerate(((-12, 0), (10, -6), (0, 8))):
            r = (7 + 9 * f) * (1.0 - 0.15 * j); x = ox + dx * (1 + 1.2 * f); y = oy + dy - 22 * ease_out(f)
            d.ellipse((X(x - r), Y(y - r), X(x + r), Y(y + r)), fill=(232, 230, 234, 255))
    draw_prop_layer(fr, sc, ox - 60, oy - 60, ox + 60, oy + 40, 0.85 * clamp((1.0 - f) / 0.6, 0.0, 1.0), paint)


def draw_rays(fr, sc, t, origin, hold):
    """Soft rays behind a find held up: they open, turn slowly for `hold` seconds, and close; t: time since they open."""
    if t < 0 or t >= hold + 0.5: return
    a = smooth(t / 0.22) * (1.0 - smooth((t - hold) / 0.5)); ox, oy = origin
    def paint(d, X, Y, k):
        for i in range(8):
            q = TWO_PI * i / 8 + 0.5 * t
            r0, r1 = 46.0, (104.0 if i % 2 == 0 else 84.0) * (0.6 + 0.4 * a); hw = 0.17
            d.polygon([(X(ox + r0 * math.cos(q - hw * 0.5)), Y(oy + r0 * math.sin(q - hw * 0.5))),
                       (X(ox + r1 * math.cos(q - hw)), Y(oy + r1 * math.sin(q - hw))),
                       (X(ox + r1 * math.cos(q + hw)), Y(oy + r1 * math.sin(q + hw))),
                       (X(ox + r0 * math.cos(q + hw * 0.5)), Y(oy + r0 * math.sin(q + hw * 0.5)))], fill=(255, 222, 110, 255))
    draw_prop_layer(fr, sc, ox - 112, oy - 112, ox + 112, oy + 112, 0.8 * a, paint)


def draw_item_held(fr, sc, P, side, size, u, part, centre=None):
    """Only for looking at the clips: the treasure PREVIEW_ITEM (a name of renderer/items.py) at the arm's tip, as
    the player will lay it: its glow behind the pet once it is held up, the icon in front, in its own little loop."""
    if PREVIEW_ITEM is None or size <= 0.02: return
    import items
    cx, cy = centre if centre is not None else _item_centre(P, side, size)
    t = (u / 2.0) % 1.0
    n = max(2, int(round(ITEM_BOX * size * sc.s)))
    glow = clamp((size - 0.7) / 0.3, 0.0, 1.0)
    if part == 'glow':
        if glow <= 0.02: return
        au = items.draw_aura(items.ITEMS[PREVIEW_ITEM][2], n, t)
        if glow < 0.995: au.putalpha(au.getchannel('A').point(lambda v: int(v * glow + 0.5)))
        fr.alpha_composite(au, (int(round(cx * sc.s - au.size[0] / 2.0)), int(round(cy * sc.s - au.size[1] / 2.0))))
        return
    fr.alpha_composite(items.draw_item(PREVIEW_ITEM, n, t=t), (int(round(cx * sc.s - n / 2.0)), int(round(cy * sc.s - n / 2.0))))


# ---- passing a note: one pet carries a small folded note to another and hands it over
# Directions as in comfort: `side` is where the neighbour is, the note is on the arm on that side.  The note hangs on
# the arm's tip (NOTE_UP above it, NOTE_IN towards the pet's own body) and is drawn in front of the body, with the
# arm's tip drawn again over its bottom edge so that the arm holds it.  The canvas must not grow (old frames stay
# byte-identical), and on the left the canvas ends 0.61 body px from the feet: so the note stays close to the arm.
NOTE_W, NOTE_H = 88.0, 66.0       # logical px (the body is 290 wide, the body + arms 390)
NOTE_UP, NOTE_IN = 24.0, 8.0
NOTE_SIZE = 1.4                   # all of the note (and NOTE_UP / NOTE_IN) this much bigger: at 1.0 it was hard to see
NOTE_ROT = 6.0                    # degrees, the top leaning towards the pet's own head
CARRY_ARM = (60.0, 1.1)           # carry_*, walk_carry_*, carry_hold_*, the first frame of give_*: the note held up
CARRY_LOOK = 0.85                 # ... eyes towards that side (as in walk_left / walk_right)
PASS_FRAME = 16                   # the hand-over: give_* shows the note up to frame 15, receive_* from frame 16 (0.80 s)
PASS_AT = PASS_FRAME / FPS
NOTE_ROLES = {'': 1.0, 'mid_': 0.8, 'small_': 0.6}    # give_* / receive_* for the big pet, the 80 % one, the 60 % one
NOTE_SHOWN = 0.72                 # at the hand-over every pet draws the note this big (of the big pet's own note) ...
# ... and holds it at the same height on screen, so the two notes are one: the arm for each pet at the hand-over.
# (angle, ext, lean): the small one reaches up, the big one down; the angles of the other two are solved below.
PASS_SMALL = (62.0, 1.3, 2.0)
PASS_EXT = {'': (1.15, 1.0), 'mid_': (1.1, 0.5)}     # role -> (ext, lean)


def _note_scale(role):
    return NOTE_SHOWN / NOTE_ROLES[role]


def _note_centre(P, side, scale):
    tip = C.geom(P)['tipR' if side > 0 else 'tipL']; scale *= NOTE_SIZE
    return tip[0] - side * NOTE_IN * scale, tip[1] - NOTE_UP * scale


def _pass_body(side, arm):
    P = make_pose(); ang, ext, lean = arm
    _mirror_arm(P, side, ang, ext, 1.0); P['tilt'] -= side * lean
    return P


def _solve_pass():
    """The hand-over arm of each role, so that the note's centre is at the same height on screen for all three."""
    arms = {'small_': PASS_SMALL}
    P = _pass_body(1, PASS_SMALL); h = FLOOR_Y - _note_centre(P, 1, _note_scale('small_'))[1]
    target = h * NOTE_ROLES['small_']                          # in the big pet's logical px
    for role, (ext, lean) in PASS_EXT.items():
        want = target / NOTE_ROLES[role]; lo, hi = -60.0, 80.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            P = _pass_body(1, (mid, ext, lean))
            if FLOOR_Y - _note_centre(P, 1, _note_scale(role))[1] < want: lo = mid
            else: hi = mid
        arms[role] = (0.5 * (lo + hi), ext, lean)
    return arms


PASS_ARMS = _solve_pass()


def carry_pose(side):
    P = make_pose(); _mirror_arm(P, side, CARRY_ARM[0], CARRY_ARM[1], 1.0)
    P['look'] = (CARRY_LOOK * side, 0.0)
    return P


def _carried(thing, side, size, scale=1.0, out=1.0):
    """What is on the arm: a note (drawn in the frame) or a find (thing 'item': laid over by the player)."""
    return ('item', side, size, scale, out) if thing == 'item' else ('note', side, size * scale, 1.0)


def carry_start_pose(u, D, side, thing='note'):
    """The arm on the neighbour's side comes up, and the note (or the find it has kept) pops out at its tip."""
    P = make_pose(); e = smooth(u / 0.45)
    _mirror_arm(P, side, CARRY_ARM[0], CARRY_ARM[1], e)
    P['look'] = (CARRY_LOOK * side * smooth(u / 0.35), 0.0)
    P['blush'] = 0.5 * bump(u, 0.1, D)
    pop = clamp((u - 0.22) / 0.2, 0.0, 1.0)
    fxs = ([_carried(thing, side, pop, 1.0)] if thing == 'item' else
           [('note', side, ease_out_back(pop, 2.2) if pop < 1.0 else 1.0, 1.0)]) if pop > 0 else []
    fxs.append(('twinkle', u - 0.24, _fx_item_centre(carry_pose(side), ('item', side, 1.0, 1.0, 1.0)) if thing == 'item' else _note_centre(carry_pose(side), side, 1.0), 1.0))
    return P, fxs


def carry_hold_pose(u, side, T=CARRY_HOLD_LEN, thing='note'):
    """Waiting with the note held up: frame 0 is the last frame of carry_start and the first of give."""
    P = carry_pose(side); c = TWO_PI * u / T
    br = math.sin(c)
    P['sy'] *= 1 + 0.01 * br; P['sx'] *= 1 - 0.005 * br
    key = 'R' if side > 0 else 'L'; a, x = P['nub' + key]; P['nub' + key] = (a + 2.0 * math.sin(c + 0.8) - 2.0 * math.sin(0.8), x)
    b = (u - 1.3) / 0.16
    if 0.0 <= b <= 1.0: P['eye_open'] = abs(1 - 2 * b) ** 0.8
    return P, [_carried(thing, side, 1.0)]


def walk_carry_pose(u, side, thing='note'):
    """walk_left / walk_right with the arm on the walking side held up, the note on it; periodic in WALK_CYCLE."""
    P, _ = walk_pose_loop(u, facing=side)
    key = 'R' if side > 0 else 'L'
    P['nub' + key] = (CARRY_ARM[0] + 3.0 * math.sin(TWO_PI * u / WALK_CYCLE), CARRY_ARM[1])
    return P, [_carried(thing, side, 1.0)]


def _arm_path(P, side, keys, u):
    """the arm on `side` along (u, angle, ext) keys, smoothstep between them."""
    key = 'R' if side > 0 else 'L'
    for (u0, a0, x0), (u1, a1, x1) in zip(keys, keys[1:]):
        if u <= u1:
            s = smooth((u - u0) / (u1 - u0)); P['nub' + key] = (lerp(a0, a1, s), lerp(x0, x1, s)); return
    P['nub' + key] = (keys[-1][1], keys[-1][2])


def give_pose(u, D, side, role, thing='note'):
    """Reaches out with the note to the neighbour, lets go at the hand-over, arm back down, one happy little hop."""
    rest = make_pose()['nubR' if side > 0 else 'nubL']; ang, ext, lean = PASS_ARMS[role]
    P = carry_pose(side)
    reach = smooth(u / 0.6); back = smooth((u - 0.85) / 0.45)
    if u > 0.0:
        _arm_path(P, side, ((0.0, CARRY_ARM[0], CARRY_ARM[1]), (0.6, ang, ext), (0.85, ang, ext), (1.3, rest[0], rest[1])), u)
    w = reach * (1.0 - back)
    P['tilt'] -= side * lean * w
    P['look'] = (lerp(CARRY_LOOK, 0.7, reach) * side * (1.0 - smooth((u - 1.0) / 0.5)), -0.1 * w)
    P['lift'] += 16.0 * bump(u, 1.3, 1.62)
    k = bump(u, 1.2, 1.34) + bump(u, 1.6, 1.76)
    P['sy'] *= 1 - 0.04 * k; P['sx'] *= 1 + 0.02 * k
    if 1.0 < u < 1.85: P['eyes'] = 'happy'
    P['blush'] = 0.6 * bump(u, 0.9, 1.95)
    fxs = []
    if u < PASS_AT - 1e-6:
        fxs.append(_carried(thing, side, 1.0, lerp(1.0, _note_scale(role), reach), 1.0 - reach))
    return P, fxs


RECEIVE_LOOK_ARM = (44.0, 1.15)   # receive_*: the note held up beside the face to look at it


def receive_body(u, side, role):
    """Reaches out, takes the note at the hand-over, holds it up beside the face to read, a small nod, puts it away."""
    rest = make_pose()['nubR' if side > 0 else 'nubL']; ang, ext, lean = PASS_ARMS[role]
    P = make_pose()
    _arm_path(P, side, ((0.0, rest[0], rest[1]), (0.6, ang, ext), (0.88, ang, ext), (1.3, RECEIVE_LOOK_ARM[0], RECEIVE_LOOK_ARM[1]),
                        (2.0, RECEIVE_LOOK_ARM[0] + 4.0, RECEIVE_LOOK_ARM[1]), (2.5, rest[0], rest[1])), u)
    reach = smooth(u / 0.6) * (1.0 - smooth((u - 0.88) / 0.42))
    P['tilt'] -= side * lean * reach
    read = smooth((u - 0.95) / 0.35) * (1.0 - smooth((u - 2.0) / 0.4))
    away = 1.0 - smooth((u - 2.1) / 0.35)
    P['look'] = (max(0.7 * reach, 0.75 * read) * side * away, -0.1 * reach - 0.35 * read)
    if 0.25 < u < 0.8: P['eyes'] = 'wide'
    d = bump(u, 1.45, 1.75)                                    # a small nod while reading
    P['sy'] *= 1 - 0.045 * d; P['sx'] *= 1 + 0.02 * d
    if 1.5 < u < 2.3: P['eyes'] = 'happy'
    P['blush'] = 0.6 * bump(u, 1.2, 2.5)
    return P


TAKE_ARM = (64.0, 1.2)            # take_*: the find held high


def take_pose(u, D, side):
    """The big one is handed a find: reaches down for it, takes it at the hand-over (as receive_*), holds it up
    high with stars in its eyes and a hop, a long look, and puts it away."""
    rest = make_pose()['nubR' if side > 0 else 'nubL']; ang, ext, lean = PASS_ARMS['']
    P = make_pose()
    _arm_path(P, side, ((0.0, rest[0], rest[1]), (0.6, ang, ext), (0.88, ang, ext), (1.3, TAKE_ARM[0], TAKE_ARM[1]),
                        (2.3, TAKE_ARM[0] + 3.0, TAKE_ARM[1]), (2.8, rest[0], rest[1])), u)
    reach = smooth(u / 0.6) * (1.0 - smooth((u - 0.88) / 0.42))
    P['tilt'] -= side * lean * reach
    high = smooth((u - 0.95) / 0.35) * (1.0 - smooth((u - 2.3) / 0.4))
    P['look'] = (max(0.7 * reach, 0.8 * high) * side, -0.1 * reach - 0.5 * high)
    if 0.25 < u < 0.8: P['eyes'] = 'wide'
    P['lift'] += 22.0 * bump(u, 1.28, 1.64)
    k = bump(u, 1.16, 1.3) + bump(u, 1.62, 1.8)
    P['sy'] *= 1 - 0.045 * k; P['sx'] *= 1 + 0.022 * k
    if 1.28 < u < 2.42: P['eyes'] = 'star' if u < 1.72 else 'happy'
    P['blush'] = 0.7 * bump(u, 1.2, 2.8)
    fxs = []
    if u >= PASS_AT - 1e-6:
        size = 1.0 - smooth((u - 2.34) / 0.36)
        if size > 0.02: fxs.append(('item', side, size, lerp(_note_scale(''), 1.0, smooth((u - 0.88) / 0.42)), 0.6 * smooth((u - 0.88) / 0.42)))
        Q = make_pose(); _mirror_arm(Q, side, TAKE_ARM[0], TAKE_ARM[1], 1.0)
        fxs.append(('twinkle', u - 1.3, _fx_item_centre(Q, ('item', side, 1.0, 1.0, 0.6)), 1.3))
    return P, fxs


def receive_pose(u, D, side, role):
    fxs = []
    if u >= PASS_AT - 1e-6:
        s = lerp(_note_scale(role), 1.0, smooth((u - 0.88) / 0.42)) * (1.0 - smooth((u - 2.0) / 0.32))
        if s > 0.02: fxs.append(('note', side, s, 1.0))
        fxs.append(('twinkle', u - 2.12, _note_centre(receive_body(2.12, side, role), side, 0.6), 1.0))
    return receive_body(u, side, role), fxs


def sign_weight(u, D=SIGN_LEN):
    """0 at rest, 1 held up: exactly 1 from SIGN_UP to D - SIGN_DOWN, the part the player holds."""
    return smooth(u / SIGN_UP) * (1.0 - smooth((u - (D - SIGN_DOWN)) / SIGN_DOWN))


def sign_pose(u, D, side):
    """sign_*: the arm on the outer side comes up with a stick; at the top it stays quite still (the board the
    player shows on the stick's top must not swim), the eyes look up at it.  Starts and ends in the plain pose."""
    P = make_pose(); e = sign_weight(u, D)
    _mirror_arm(P, side, SIGN_ARM[0], SIGN_ARM[1], e)
    P['look'] = (SIGN_LOOK[0] * side * e, SIGN_LOOK[1] * e)
    b = (u - 1.25) / 0.16
    if 0.0 <= b <= 1.0: P['eye_open'] = abs(1 - 2 * b) ** 0.8
    return P, [('stick', side, e)]


def sign_top(P, side, length=SIGN_STICK):
    """-> (the arm's tip, the stick's top) in logical px."""
    tx, ty = C.geom(P)['tip' + ('R' if side > 0 else 'L')]
    a = math.radians(SIGN_LEAN)
    return (tx, ty), (tx + side * math.sin(a) * length, ty - math.cos(a) * length)


def draw_stick(fr, sc, P, side, e, part):
    """part 'pole': the stick, behind the body; part 'tip': the arm's tip again, over the stick, so that it holds it."""
    fade = clamp(e * 5.0, 0.0, 1.0)            # quickly: half see-through it looks grey
    if fade <= 0.01: return
    key = 'R' if side > 0 else 'L'
    (tx, ty), (sx, sy) = sign_top(P, side)
    if part == 'pole':
        ax = ((sx - tx) / SIGN_STICK, (sy - ty) / SIGN_STICK)
        def paint(d, X, Y, k):
            _bar(d, X, Y, (tx, ty + 16), ax, 0, SIGN_STICK + 16, 7.5, 6.5, (126, 88, 56, 255))
            _bar(d, X, Y, (tx, ty + 16), ax, 2, SIGN_STICK + 12, 2.2, 1.8, (166, 124, 86, 255))
        draw_prop_layer(fr, sc, min(tx, sx) - 24, sy - 24, max(tx, sx) + 24, ty + 48, fade, paint)
    else:
        L = C.NUB_L * P['nub' + key][1]
        def tip_paint(d, X, Y, k):
            _poly(d, X, Y, _arm_piece(P, key, L - 30, L, C.NUB_T, 12), C.NUB_COL + (255,))
            hl1 = 0.85 * L - 2.7
            if hl1 > L - 28:
                _poly(d, X, Y, _arm_piece(P, key, L - 28, hl1, C.NUB_T * 0.16, 4, -C.NUB_T * 0.28), C.NUB_HI + (255,))
            _poly(d, X, Y, _body_poly(P), (0, 0, 0, 0))
        draw_prop_layer(fr, sc, tx - 60, ty - 60, tx + 60, ty + 60, 1.0, tip_paint)


# ---- 小插曲 (the gift of Lv.16): now and then a combo goes another way.  Plain first versions.
def _turn_about_centre(P, th):
    """The whole body turned by th degrees about its centre (as tumble does), not about a foot."""
    P['tilt'] = th
    if abs(th) > 1e-3:
        g0 = C.geom(dict(P, tilt=0.0)); cx, cy = g0['x'], g0['cy']
        piv = C.tilt_pivot(P, g0['bw'], g0['feet'])
        rx, ry = rot_pts([(cx, cy)], piv[0], piv[1], th)[0]
        P['x'] += cx - rx; P['lift'] -= cy - ry


SLIP_SIT_HIT = HIGH_FIVE_HIT + HF_UP_AIR + 0.06    # the bottom meets the floor
SLIP_SIT_UP = 0.5                                  # the last this long it gets back on its feet


def slip_sit_pose(u, D, side):
    """The high five that misses: jumps with the arm up like high_five_up, no hand there (eyes wide), tips over
    backwards (away from the other) and comes down on its bottom: a hard squash, a bounce, stars going round, sits
    a moment with the arms propped out, laughs, stands up."""
    P = make_pose(); hit = HIGH_FIVE_HIT; air = HF_UP_AIR; t1 = SLIP_SIT_HIT
    w = smooth((u - 0.10) / (hit - 0.10)) * (1.0 - smooth((u - hit - 0.05) / 0.2))
    _mirror_arm(P, side, HF_UP_ARM[0], HF_UP_ARM[1], w, w ** 2)
    x = (u - hit) / air
    if u < t1 and abs(x) < 1.25: P['lift'] += max(0.0, HF_UP_HOP * (1.0 - x * x))
    crouch = bump(u, 0.04, hit - air)
    sit = smooth((u - hit - 0.1) / (t1 - hit - 0.1)) * (1.0 - smooth((u - (D - SLIP_SIT_UP)) / (SLIP_SIT_UP - 0.1)))
    back = smooth((u - hit) / 0.22) * (1.0 - smooth((u - (D - SLIP_SIT_UP)) / 0.3))
    P['legx'] = -16.0 * crouch - 26.0 * sit
    P['tilt'] += side * (15.0 * back * (1.0 - 0.55 * smooth((u - t1) / 0.3)) - HF_UP_LEAN * w)
    P['sy'] *= 1 - 0.03 * crouch; P['sx'] *= 1 + 0.015 * crouch
    if u >= t1:
        v = u - t1
        sq = math.exp(-6.0 * v) * math.cos(TWO_PI * v / 0.34)
        P['sy'] *= 1 - 0.2 * sq; P['sx'] *= 1 + 0.13 * sq
        P['lift'] += 14.0 * bump(v, 0.09, 0.33)                 # one small bounce on its bottom
        for key in 'LR': _arm(P, key, lerp(58.0, 4.0, smooth(v / 0.3)), 1.15, sit)
    elif u > hit + 0.05:
        fl = smooth((u - hit - 0.05) / 0.15)
        for key in 'LR': _arm(P, key, 58.0, 1.15, fl)           # both arms fly up as it tips over
    if hit - 0.06 < u < t1: P['eyes'] = 'wide'
    elif t1 <= u < t1 + 0.34: P['eyes'] = 'squeeze'
    elif t1 <= u < t1 + 0.95: P['eyes'] = 'spiral'
    elif t1 <= u < D - 0.12: P['eyes'] = 'happy'
    laugh = bump(u, t1 + 0.95, D - 0.2)
    P['lift'] += 5.0 * laugh * abs(math.sin(TWO_PI * (u - t1) / 0.3))
    P['look'] = (0.5 * side * w, -0.4 * w)
    P['blush'] = 0.9 * smooth((u - t1 - 0.6) / 0.4) * (1.0 - smooth((u - D + 0.3) / 0.3))
    g = C.geom(dict(P, tilt=0.0))
    a = smooth((u - t1) / 0.12) * (1.0 - smooth((u - t1 - 0.95) / 0.3))
    return P, [('dust', u - t1 + 0.09, 0.09), ('dizzy', u - t1, (g['x'], g['top'] - 58.0), a)]


SLIP_ROLL_TURN = (0.12, 0.92)     # the turn along the floor
SLIP_ROLL_UP = 0.5


def slip_roll_pose(u, D, side):
    """Knocked over in the leapfrog: one whole turn along the floor (the player moves the window with it), comes
    to rest sitting, spiral eyes and stars, shakes it off with a laugh, stands up."""
    P = make_pose(); t0, t1 = SLIP_ROLL_TURN
    a = clamp((u - t0) / (t1 - t0), 0.0, 1.0)
    turn = a * a * (3 - 2 * a) * 0.35 + a * 0.65                 # nearly even, eased a little at both ends
    if 0.0 < a < 1.0:
        P['walk'] = 2.0 * a; P['walkamp'] = 1.2
        wv = math.sin(TWO_PI * 2 * a)
        P['nubL'] = (58 + 16 * wv, 1.12); P['nubR'] = (58 - 16 * wv, 1.12)
        P['eyes'] = 'wide'
        _turn_about_centre(P, -side * 360.0 * turn)
        P['lift'] += TUMBLE_LIFT * (smooth(a / 0.14) * (1.0 - smooth((a - 0.86) / 0.14)))
        P['shadow'] = 1.0 - smooth(a / 0.1) * (1.0 - smooth((a - 0.9) / 0.1))
        return P, []
    if u <= t0:
        P['eyes'] = 'wide'; k = smooth(u / t0)
        P['tilt'] -= side * 6.0 * k; P['sy'] *= 1 - 0.03 * k
        return P, []
    v = u - t1
    sit = 1.0 - smooth((u - (D - SLIP_ROLL_UP)) / (SLIP_ROLL_UP - 0.08))
    sq = math.exp(-7.0 * v) * math.cos(TWO_PI * v / 0.34)
    P['legx'] = -22.0 * sit
    P['sy'] *= 1 - 0.05 * sit - 0.16 * sq; P['sx'] *= 1 + 0.03 * sit + 0.1 * sq
    ph = TWO_PI * v / 0.9
    wob = sit * (1.0 - smooth((v - 0.85) / 0.25))
    P['tilt'] += 6.0 * math.sin(ph) * wob
    P['look'] = (0.35 * math.cos(ph) * wob, 0.25 * math.sin(ph) * wob)
    for key, off in (('L', 0.0), ('R', 1.3)):
        a0, x0 = P['nub' + key]
        P['nub' + key] = (lerp(a0, -14 + 6 * math.sin(ph + off), sit), lerp(x0, 0.95, sit))
    if v < 0.14: P['eyes'] = 'squeeze'
    elif v < 0.95: P['eyes'] = 'spiral'
    elif u < D - 0.12: P['eyes'] = 'happy'
    laugh = bump(v, 0.95, D - t1 - 0.2)
    P['lift'] += 5.0 * laugh * abs(math.sin(TWO_PI * v / 0.3))
    P['blush'] = 0.9 * smooth((v - 0.7) / 0.4) * (1.0 - smooth((u - D + 0.3) / 0.3))
    g = C.geom(dict(P, tilt=0.0))
    return P, [('dust', v + 0.09, 0.09), ('dizzy', v, (g['x'], g['top'] - 58.0), smooth(v / 0.12) * (1.0 - smooth((v - 0.95) / 0.3)))]


FLIP_OFF, FLIP_ON = 0.35, 1.05    # stack_flip: take-off and touch-down; the player carries the window along its arc


def stack_flip_pose(u, D, side):
    """Down from the top of the stack with a flourish: crouch, off, one whole turn in the air (tucked: legs drawn
    up, arms in), lands with a squash, then both arms up, star eyes, a proud little bounce."""
    P = make_pose()
    if u < FLIP_OFF:
        c = smooth(u / 0.3)
        P['legx'] = -16.0 * c; P['sy'] *= 1 - 0.05 * c; P['sx'] *= 1 + 0.025 * c
        for key in 'LR':
            a0, x0 = P['nub' + key]; P['nub' + key] = (a0 - 34.0 * c, x0)
        return P, []
    if u < FLIP_ON:
        a = (u - FLIP_OFF) / (FLIP_ON - FLIP_OFF)
        tuck = bump(a, 0.05, 0.95)
        P['legx'] = lerp(6.0, -12.0, tuck)
        for key in 'LR': _arm(P, key, lerp(46.0, -20.0, tuck), 1.0, 1.0)
        P['eyes'] = 'happy' if 0.1 < a < 0.9 else 'wide'
        P['shadow'] = max(1.0 - smooth(a / 0.15), smooth((a - 0.85) / 0.15))
        turn = smooth((a - 0.08) / 0.84)
        _turn_about_centre(P, -side * 360.0 * turn)
        P['lift'] += TUMBLE_LIFT * (smooth(a / 0.16) * (1.0 - smooth((a - 0.84) / 0.16)))
        return P, []
    v = u - FLIP_ON
    k = math.exp(-7.0 * v) * math.cos(TWO_PI * v / 0.34)
    P['legx'] = -12.0 * max(0.0, k); P['sy'] *= 1 - 0.14 * k; P['sx'] *= 1 + 0.09 * k
    e = smooth((v - 0.12) / 0.2) * (1.0 - smooth((u - (D - 0.3)) / 0.26))
    for key in 'LR': _arm(P, key, 64.0, 1.25, e)
    P['lift'] += 16.0 * bump(v, 0.2, 0.52)
    if v < 0.1: P['eyes'] = 'squeeze'
    elif e > 0.3: P['eyes'] = 'star'
    P['blush'] = e
    g = C.geom(dict(P, tilt=0.0))
    return P, [('dust', v + 0.09, 0.09), ('spark', v - 0.3, (g['x'], g['top'] - 34.0), 1.7)]


REACTION_POSES = {'thumbs_up': thumbs_pose, 'celebrate': celebrate_pose, 'wave': wave_pose, 'proud': proud_pose,
                  'look_at_viewer': look_pose, 'confused': confused_pose, 'shake_head': shake_pose}
for _n, _fn in (('high_five', high_five_pose), ('high_five_up', high_five_up_pose), ('nudge', nudge_pose), ('peek', peek_pose), ('comfort', comfort_pose),
                 ('slip_sit', slip_sit_pose), ('slip_roll', slip_roll_pose), ('stack_flip', stack_flip_pose)):
    REACTION_POSES[_n + '_right'] = lambda u, D, _fn=_fn: _fn(u, D, 1)
    REACTION_POSES[_n + '_left'] = lambda u, D, _fn=_fn: _fn(u, D, -1)
REACTION_POSES['wake_up'] = wake_up_pose
REACTION_POSES['stack_hop'] = stack_hop_pose
REACTION_POSES['stack_top'] = stack_top_pose
REACTION_POSES['leap_crouch'] = leap_crouch_pose
REACTION_POSES['squash'] = squash_pose
REACTION_POSES['dizzy'] = dizzy_pose
REACTION_POSES['doze_in'] = doze_in_pose
REACTION_POSES['doze_startle'] = doze_startle_pose
REACTION_POSES['doze_up'] = lambda u, D: wake_up_pose(u, D, doze_pose(0.0)[0])   # 打瞌睡 by hand: up by itself
REACTION_POSES['nap_look_right'] = lambda u, D: nap_look_pose(u, D, 1)
REACTION_POSES['doze_sleep'] = doze_sleep_pose
REACTION_POSES['nap_look_left'] = lambda u, D: nap_look_pose(u, D, -1)
REACTION_POSES['rummage_in'] = rummage_in_pose
REACTION_POSES['rummage_found'] = rummage_found_pose
REACTION_POSES['rummage_none'] = rummage_none_pose
REACTION_POSES['rummage_up'] = rummage_up_pose
REACTION_POSES['pull_out'] = pull_out_pose
REACTION_POSES['present'] = present_pose
for _i, _w in PLAY_WAY.items():                 # 把玩: one clip a treasure, the treasure drawn in
    REACTION_POSES['play_' + _i] = lambda u, D, _i=_i, _w=_w: PLAY_POSES[_w][0](u, D, _i)
    ONESHOT_LEN['play_' + _i] = PLAY_POSES[_w][1]
REACTION_POSES['rummage_spur'] = rummage_spur_pose
for _s, _d in ((1, 'right'), (-1, 'left')):
    REACTION_POSES['carry_start_' + _d] = lambda u, D, _s=_s: carry_start_pose(u, D, _s)
    for _r in NOTE_ROLES:
        REACTION_POSES['give_%s%s' % (_r, _d)] = lambda u, D, _s=_s, _r=_r: give_pose(u, D, _s, _r)
        REACTION_POSES['receive_%s%s' % (_r, _d)] = lambda u, D, _s=_s, _r=_r: receive_pose(u, D, _s, _r)
    REACTION_POSES['sign_' + _d] = lambda u, D, _s=_s: sign_pose(u, D, _s)
    REACTION_POSES['bring_start_' + _d] = lambda u, D, _s=_s: carry_start_pose(u, D, _s, 'item')
    REACTION_POSES['take_' + _d] = lambda u, D, _s=_s: take_pose(u, D, _s)
    for _r in ('mid_', 'small_'):
        REACTION_POSES['hand_%s%s' % (_r, _d)] = lambda u, D, _s=_s, _r=_r: give_pose(u, D, _s, _r, 'item')
WORK_POSES = {'work_read': read_pose, 'work_edit': edit_pose, 'work_run': run_pose, 'work_web': web_pose,
              'work_compact': compact_pose, 'work_agent': agent_pose}


def draw_prop_layer(fr, sc, x0, y0, x1, y1, alpha, paint):
    """Paint a prop at 4x in the logical box and composite it: thin lines stay clean at small sizes."""
    if alpha <= 0.01: return
    px0, py0 = int(math.floor(x0 * sc.s)), int(math.floor(y0 * sc.s))
    w, h = int(math.ceil((x1 - x0) * sc.s)) + 1, int(math.ceil((y1 - y0) * sc.s)) + 1
    k = 4 * sc.s
    lay = Image.new('RGBA', (w * 4, h * 4), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    X = lambda v: (v * sc.s - px0) * 4
    Y = lambda v: (v * sc.s - py0) * 4
    paint(d, X, Y, k)
    lay = lay.resize((w, h), Image.LANCZOS)
    if alpha < 0.995: lay.putalpha(lay.getchannel('A').point(lambda v: int(v * alpha + 0.5)))
    fr.alpha_composite(lay, (px0, py0))


def _poly(d, X, Y, pts, fill):
    d.polygon([(X(a), Y(b)) for a, b in pts], fill=fill)


def _rrect(d, X, Y, k, a, b, c, e_, r, fill):
    d.rounded_rectangle((X(a), Y(b), X(c), Y(e_)), radius=max(1, r * k), fill=fill)


def _bar(d, X, Y, p, ax, c0, c1, w0, w1, fill):
    """A piece of a straight prop: from c0 to c1 along axis ax from point p, half widths w0 and w1."""
    vx, vy = -ax[1], ax[0]
    _poly(d, X, Y, [(p[0] + ax[0] * c0 + vx * w0, p[1] + ax[1] * c0 + vy * w0), (p[0] + ax[0] * c1 + vx * w1, p[1] + ax[1] * c1 + vy * w1),
                    (p[0] + ax[0] * c1 - vx * w1, p[1] + ax[1] * c1 - vy * w1), (p[0] + ax[0] * c0 - vx * w0, p[1] + ax[1] * c0 - vy * w0)], fill)


def _box_around(pts, pad):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


KEY_ORDER = (3, 19, 8, 26, 13, 1, 30, 11, 22, 6, 28, 16)         # one key lights up per tick, in a fixed loop


def draw_work(fr, sc, P, kind, u, e):
    g = C.geom(P); x, top = P['x'], g['top']
    fade = clamp(e * 2.5, 0.0, 1.0)                            # a prop shows up at the hand, then comes along with it
    if kind == 'read':                                         # magnifying glass beside the face; behind the arm's tip
        tx, ty = g['tipR']; r = 44.0
        cx, cy = tx + 12, ty - 84
        ax = (-12 / 84.0, 1.0)
        def paint(d, X, Y, k):
            _bar(d, X, Y, (cx, cy), ax, r - 6, 96, 8, 9, (120, 82, 52, 255))
            d.ellipse((X(cx - r), Y(cy - r), X(cx + r), Y(cy + r)), fill=(70, 74, 92, 255))
            q = r - 9
            d.ellipse((X(cx - q), Y(cy - q), X(cx + q), Y(cy + q)), fill=(222, 240, 250, 255))
            d.arc((X(cx - q + 8), Y(cy - q + 8), X(cx + q - 8), Y(cy + q - 8)), 195, 265, fill=(255, 255, 255, 255), width=int(max(1, 6 * k)))
        draw_prop_layer(fr, sc, cx - r - 4, cy - r - 4, max(cx + r, tx + 30) + 4, ty + 34, fade, paint)
    elif kind == 'edit':                                       # a wide keyboard held at both ends; the arms press its ends
        cy0 = g['cy'] + 86 + 18 * (1 - e); hw, h = 186.0, 40.0
        tick = int(u / WORK_LOOP * 12 + 1e-6) % 12
        lit = KEY_ORDER[tick]
        def paint(d, X, Y, k):
            # seen from above and in front: dark keys, or a bright row on the belly looks like teeth
            _poly(d, X, Y, [(x - hw + 22, cy0), (x + hw - 22, cy0), (x + hw, cy0 + h), (x - hw, cy0 + h)], (58, 62, 78, 255))
            for row in range(3):
                f = 0.88 + 0.06 * row
                for col in range(11):
                    kx = x + (col - 5) * 27.0 * f; ky = cy0 + 7 + row * 10.5
                    c = (120, 205, 250, 255) if row * 11 + col == lit else (96, 102, 124, 255)
                    _rrect(d, X, Y, k, kx - 10 * f, ky, kx + 10 * f, ky + 7, 2, c)
            for key in ('L', 'R'):                             # the arm's tip, over the keyboard
                tx, ty = g['tip' + key]; dx, dy = g['dir' + key]
                ang = math.degrees(math.atan2(-dy, dx))
                _poly(d, X, Y, rrect_poly(tx - dx * 10, ty - dy * 10, 34, C.NUB_T, 12, ang), C.NUB_COL + (255,))
        draw_prop_layer(fr, sc, x - hw - 40, cy0 - 50, x + hw + 40, cy0 + h + 8, fade, paint)
    elif kind == 'run':                                        # small terminal, held by the arm in front of its corner
        tx, ty = g['tipR']
        x0, x1, y1 = tx - 16, tx + 148, ty + 40; y0 = y1 - 134
        tick = int(u / WORK_LOOP * 6 + 1e-6)
        n = tick % 6
        def paint(d, X, Y, k):
            _rrect(d, X, Y, k, x0, y0, x1, y1, 12, (32, 35, 46, 255))
            _rrect(d, X, Y, k, x0, y0, x1, y0 + 22, 11, (62, 66, 84, 255))
            for i, c in enumerate(((236, 106, 94), (244, 191, 79), (98, 196, 98))):
                bx = x0 + 17 + i * 18
                d.ellipse((X(bx - 5), Y(y0 + 6), X(bx + 5), Y(y0 + 16)), fill=c + (255,))
            for i in range(min(n, 3)):                         # output lines appear one by one
                _rrect(d, X, Y, k, x0 + 22, y0 + 36 + i * 17, x0 + 22 + (112, 74, 98)[i], y0 + 45 + i * 17, 3, (136, 214, 150, 255))
            cy_ = y0 + 36 + min(n, 3) * 17
            d.line([(X(x0 + 22), Y(cy_ - 1)), (X(x0 + 32), Y(cy_ + 5)), (X(x0 + 22), Y(cy_ + 11))], fill=(236, 238, 245, 255), width=int(max(1, 4 * k)))
            if tick % 2 == 0:
                _rrect(d, X, Y, k, x0 + 38, cy_ - 1, x0 + 49, cy_ + 11, 1, (236, 238, 245, 255))
        draw_prop_layer(fr, sc, x0 - 2, y0 - 2, x1 + 2, y1 + 2, fade, paint)
    elif kind == 'web':                                        # telescope resting on the raised arm, the eyepiece at the eye, panning slowly
        tx, ty = g['tipR']; L, grip = 196.0, 84.0
        a = math.radians(lerp(-6.0, 20 + 6 * math.sin(TWO_PI * u / WORK_LEN), e)); ax = (math.cos(a), -math.sin(a))
        p = (tx - ax[0] * grip, ty - ax[1] * grip)
        def paint(d, X, Y, k):
            _bar(d, X, Y, p, ax, 0, 120, 18, 20, (172, 122, 62, 255))
            _bar(d, X, Y, p, ax, 112, L, 25, 28, (120, 80, 44, 255))
            _bar(d, X, Y, p, ax, 0, 9, 21, 21, (232, 196, 120, 255))
            _bar(d, X, Y, p, ax, L - 10, L, 30, 30, (232, 196, 120, 255))
            _bar(d, X, Y, p, ax, 112, 120, 27, 27, (232, 196, 120, 255))
        far = (p[0] + ax[0] * L, p[1] + ax[1] * L)
        draw_prop_layer(fr, sc, *_box_around((p, far), 50), fade, paint)
    elif kind == 'compact':                                    # three sheets above the head folded into one
        ph = (u % WORK_LOOP) / WORK_LOOP; w = 0.5 - 0.5 * math.cos(TWO_PI * ph)
        cy = top - 62
        def paint(d, X, Y, k):
            for i, off in enumerate((-96, 96, 0)):
                bx = x + off * (1 - w); by = cy + 8 * i * (1 - w)
                _rrect(d, X, Y, k, bx - 40, by - 30, bx + 40, by + 30, 5, (248, 246, 236, 255))
                for j in range(3):
                    _rrect(d, X, Y, k, bx - 28, by - 17 + j * 13, bx + (28 - 12 * (j == 2)), by - 11 + j * 13, 2, (176, 184, 204, 255))
        draw_prop_layer(fr, sc, x - 146, cy - 40, x + 146, cy + 50, fade, paint)
    elif kind == 'agent':                                      # a paper plane: held behind the arm's tip, tossed, let go along its own nose
        if u < THROW_RELEASE:
            tip = g['tipR']; head = THROW_HEAD; alpha = clamp(u / 0.2, 0.0, 1.0)
            a = math.radians(head); cx, cy = tip[0] + math.cos(a) * 30, tip[1] - math.sin(a) * 30
        else:
            tip = C.geom(agent_pose(THROW_RELEASE, THROW_LEN)[0])['tipR']
            t = clamp((u - THROW_RELEASE) / (THROW_LEN - THROW_RELEASE), 0.0, 1.0); f = ease_out(t)
            a = math.radians(THROW_HEAD)
            cx = tip[0] + math.cos(a) * 30 + 190 * f
            cy = tip[1] - math.sin(a) * 30 - 190 * math.tan(a) * (f - 0.35 * f * f)    # falls off to nearly level
            head = math.degrees(math.atan(math.tan(a) * (1 - 0.7 * f)))
            alpha = clamp((1 - t) / 0.3, 0.0, 1.0)
        a = math.radians(head); ux, uy = math.cos(a), -math.sin(a); vx, vy = -uy, ux
        pt = lambda along, side: (cx + ux * along + vx * side, cy + uy * along + vy * side)
        def paint(d, X, Y, k):
            _poly(d, X, Y, [pt(50, 0), pt(-40, -20), pt(-14, 2)], (250, 250, 252, 255))     # wing
            _poly(d, X, Y, [pt(50, 0), pt(-14, 2), pt(-30, 24)], (206, 214, 232, 255))      # keel
        draw_prop_layer(fr, sc, cx - 70, cy - 70, cx + 70, cy + 70, alpha, paint)
    elif kind == 'thumb':                                      # the arm's tip with a small thumb straight up, nothing more
        hx, hy = g['tipR']; pop = lerp(0.5, 1.0, clamp(e * 1.6, 0.0, 1.0))
        def paint(d, X, Y, k):
            _rrect(d, X, Y, k, hx - 30, hy - 26, hx + 26, hy + 26, 16, C.NUB_COL + (255,))
            _rrect(d, X, Y, k, hx - 19 * pop, hy - 62 * pop, hx + 13 * pop, hy - 8, 14 * pop, C.NUB_COL + (255,))
            _rrect(d, X, Y, k, hx - 11 * pop, hy - 54 * pop, hx - 5 * pop, hy - 26 * pop, 3, C.NUB_HI + (255,))
        draw_prop_layer(fr, sc, hx - 40, hy - 80, hx + 40, hy + 36, clamp(e * 2.5, 0.0, 1.0), paint)
    elif kind == 'ear':                                        # listen: sound waves at the cupped hand
        tx, ty = g['tipR']
        def paint(d, X, Y, k):
            for i in range(2):
                ph = (u * 0.9 + i / 2.0) % 1.0; r = 26 + 34 * ph; a = int(220 * (1 - ph))
                d.arc((X(tx + 26 - r), Y(ty - r), X(tx + 26 + r), Y(ty + r)), -42, 42, fill=(92, 150, 214, a), width=int(max(1, 6 * k)))
        draw_prop_layer(fr, sc, tx, ty - 75, tx + 100, ty + 75, e, paint)


def draw_sparks(fr, sc, t, origin, size=1.0):
    """3-5 tiny yellow stars bursting upwards out of the contact point of a high five; t is the time since the contact."""
    if t < 0 or t >= SPARK_LEN: return
    f = t / SPARK_LEN; ox, oy = origin; a = clamp((1.0 - f) / 0.45, 0.0, 1.0)
    def paint(d, X, Y, k):
        for i, ang in enumerate(SPARK_ANGLES):
            r = (4 + (SPARK_REACH[i] - 4) * ease_out(f)) * size; q = math.radians(ang)
            cx, cy = ox + r * math.sin(q), oy - r * math.cos(q)
            R = SPARK_SIZE[i] * size * (0.55 + 0.45 * ease_out(t / 0.08)) * (1.0 - 0.4 * f); rot = -90 + (14 if i % 2 else -14) * f
            d.polygon([(X(x_), Y(y_)) for x_, y_ in star_poly(cx, cy, R, R * 0.45, rot=rot)], fill=(255, 208, 70, 255))
            d.polygon([(X(x_), Y(y_)) for x_, y_ in star_poly(cx, cy, R * 0.55, R * 0.25, rot=rot)], fill=(255, 232, 140, 255))
    draw_prop_layer(fr, sc, ox - 60 * size, oy - 70 * size, ox + 60 * size, oy + 30 * size, a, paint)


def draw_heart(fr, sc, t, origin):
    """A small heart rising from where the arm pats; t is the time since the pat."""
    if t < 0 or t >= HEART_LEN: return
    f = t / HEART_LEN; ox, oy = origin[0], origin[1] - 70.0 * ease_out(f)
    R = HEART_SIZE * (0.5 + 0.5 * ease_out(min(1.0, t / 0.14)))
    def paint(d, X, Y, k):
        pts = []
        for i in range(32):
            q = TWO_PI * i / 32
            pts.append((ox + R * 0.0625 * 16 * math.sin(q) ** 3,
                        oy - R * 0.0625 * (13 * math.cos(q) - 5 * math.cos(2 * q) - 2 * math.cos(3 * q) - math.cos(4 * q))))
        d.polygon([(X(x_), Y(y_)) for x_, y_ in pts], fill=(240, 112, 128, 255))
    draw_prop_layer(fr, sc, ox - 50, oy - 50, ox + 50, oy + 50, clamp((1.0 - f) / 0.4, 0.0, 1.0), paint)


TWINKLE_LEN = 0.35


def draw_twinkle(fr, sc, t, origin, size=1.0):
    """A small pop of light: four little four-pointed stars flying out of a point; t is the time since it."""
    if t < 0 or t >= TWINKLE_LEN: return
    f = t / TWINKLE_LEN; ox, oy = origin; a = clamp((1.0 - f) / 0.5, 0.0, 1.0)
    def paint(d, X, Y, k):
        for i, ang in enumerate((40.0, 130.0, 220.0, 310.0)):
            r = size * (10 + 34 * ease_out(f)); q = math.radians(ang)
            cx, cy = ox + r * math.cos(q), oy - r * math.sin(q)
            R = size * (11.0 if i % 2 == 0 else 8.5) * (0.6 + 0.4 * ease_out(t / 0.08)) * (1.0 - 0.5 * f)
            d.polygon([(X(x_), Y(y_)) for x_, y_ in star_poly(cx, cy, R, R * 0.32, n=4, rot=-90)], fill=(255, 214, 90, 255))
            d.polygon([(X(x_), Y(y_)) for x_, y_ in star_poly(cx, cy, R * 0.5, R * 0.18, n=4, rot=-90)], fill=(255, 244, 196, 255))
    m = size * 60
    draw_prop_layer(fr, sc, ox - m, oy - m, ox + m, oy + m, a, paint)


def _arm_piece(P, key, c0, c1, w, r, off=0.0):
    """Polygon of a piece of the arm from c0 to c1 along it (as the renderer draws the arm), off: sideways."""
    g0 = C.geom(dict(P, tilt=0.0)); d = g0['dir' + key]; px, py = g0['piv' + key]
    a = math.degrees(math.atan2(-d[1], d[0])); s = 1 if key == 'R' else -1
    cx, cy = px + d[0] * (c0 + c1) / 2 + (-d[1]) * off * s, py + d[1] * (c0 + c1) / 2 + d[0] * off * s
    pts = rrect_poly(cx, cy, c1 - c0, w, r, a)
    piv = C.tilt_pivot(P, g0['bw'], g0['feet'])
    return rot_pts(pts, piv[0], piv[1], P['tilt']) if abs(P['tilt']) > 1e-3 else pts


def draw_note(fr, sc, P, side, scale, alpha=1.0):
    """The folded note on the arm's tip (see NOTE_*), and the arm's tip over its bottom edge so that it holds it."""
    if scale <= 0.01: return
    key = 'R' if side > 0 else 'L'
    cx, cy = _note_centre(P, side, scale); scale *= NOTE_SIZE; w, h = NOTE_W * scale, NOTE_H * scale
    rot = side * NOTE_ROT + P['tilt']
    ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    pt = lambda x, y: (cx + x * ca + y * sa, cy - x * sa + y * ca)        # note coordinates (x right, y down) -> logical
    L = C.NUB_L * P['nub' + key][1]
    def paint(d, X, Y, k):
        _poly(d, X, Y, rrect_poly(cx, cy, w, h, 5 * scale, rot), (214, 206, 186, 255))              # edge
        _poly(d, X, Y, rrect_poly(cx, cy, w - 5 * scale, h - 5 * scale, 4 * scale, rot), (252, 249, 238, 255))
        f = 20 * scale; x1, y0 = w / 2 - 2.5 * scale, -h / 2 + 2.5 * scale                    # folded corner, top right
        _poly(d, X, Y, [pt(x1 - f, y0), pt(x1, y0 + f), pt(x1 - f, y0 + f)], (226, 218, 196, 255))
        for j, ln in enumerate((0.62, 0.62, 0.42)):
            y = (-14 + 14 * j) * scale; x0 = -w / 2 + 13 * scale
            _poly(d, X, Y, rrect_poly(*pt(x0 + ln * w / 2, y), ln * w, 6 * scale, 3 * scale, rot), (166, 174, 196, 255))
    def tip_paint(d, X, Y, k):                                 # the arm's tip again, over the note but not over the body
        _poly(d, X, Y, _arm_piece(P, key, L - 30, L, C.NUB_T, 12), C.NUB_COL + (255,))
        hl1 = 0.85 * L - 2.7
        if hl1 > L - 28:
            _poly(d, X, Y, _arm_piece(P, key, L - 28, hl1, C.NUB_T * 0.16, 4, -C.NUB_T * 0.28), C.NUB_HI + (255,))
        _poly(d, X, Y, _body_poly(P), (0, 0, 0, 0))
    tip = C.geom(P)['tip' + key]
    box = _box_around(((cx - w, cy - w), (cx + w, cy + w), tip), 40)
    draw_prop_layer(fr, sc, *box, alpha, paint)
    draw_prop_layer(fr, sc, *box, alpha, tip_paint)


def _body_poly(P):
    """The body's outline as the renderer draws it (rounded, tilted)."""
    g0 = C.geom(dict(P, tilt=0.0)); bw, bh = g0['bw'], g0['bh']
    pts = rrect_poly(P['x'], g0['cy'], bw, bh, 0.13 * min(bw, bh), 0.0, n=8)
    piv = C.tilt_pivot(P, bw, g0['feet'])
    return rot_pts(pts, piv[0], piv[1], P['tilt']) if abs(P['tilt']) > 1e-3 else pts


WORK_BEHIND = ('read', 'run', 'agent')     # the arm's tip is drawn over these props: it holds them


def render_frame(sc, P, fxs, u, fx_alpha=1.0):
    fr = Image.new('RGBA', (sc.W, sc.H), (0, 0, 0, 0))
    for fx in fxs:
        if fx[0] == 'work' and fx[1] in WORK_BEHIND: draw_work(fr, sc, P, fx[1], fx[2], fx[3])
        elif fx[0] == 'rays': draw_rays(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'item': draw_item_held(fr, sc, P, fx[1], fx[2], u, 'glow', _fx_item_centre(P, fx))
        elif fx[0] == 'held': draw_held(fr, sc, P, fx, 'back')
        elif fx[0] == 'sky': draw_sky(fr, sc, *fx[1:])
        elif fx[0] == 'tshadow': draw_top_shadow(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'whip': draw_whip(fr, sc, P, fx, 'back')
        elif fx[0] == 'paper' and fx[5]: draw_paper(fr, sc, P, fx)
        elif fx[0] == 'pit': draw_pit(fr, sc, P, fx[1], fx[2], fx[3], 'back', *fx[4:])
        elif fx[0] == 'stick': draw_stick(fr, sc, P, fx[1], fx[2], 'pole')
    spr, (x, y) = C.render(P, sc, SS=SS); paste_rgba(fr, spr, x, y)
    for fx in fxs:
        if fx[0] == 'stick': draw_stick(fr, sc, P, fx[1], fx[2], 'tip')
    rest = []
    for fx in fxs:
        if fx[0] == 'confetti': pet_confetti(fr, sc, P, fx[1])
        elif fx[0] == 'zzz': draw_zzz(fr, sc, P, fx[1], fx[2], *fx[3:])
        elif fx[0] == 'dust': draw_dust(fr, sc, P, fx[1], fx[2])
        elif fx[0] == 'spark': draw_sparks(fr, sc, fx[1], fx[2], *fx[3:])
        elif fx[0] == 'heart': draw_heart(fr, sc, fx[1], fx[2])
        elif fx[0] == 'hum': draw_hum(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'squeak': draw_squeak(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'drop': draw_drop(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'crunch': draw_crunch(fr, sc, fx[1], fx[2], *fx[3:])
        elif fx[0] == 'paper' and not fx[5]: draw_paper(fr, sc, P, fx)
        elif fx[0] == 'cork': draw_cork(fr, sc, fx[1], fx[2])
        elif fx[0] == 'blow': draw_blow(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'pause': draw_pause(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'string': draw_string(fr, sc, fx[1], fx[2], fx[3], fx[4])
        elif fx[0] == 'orbit': draw_orbit(fr, sc, fx[1], fx[2], fx[3], fx[4])
        elif fx[0] == 'held': draw_held(fr, sc, P, fx, 'front')
        elif fx[0] == 'whip': draw_whip(fr, sc, P, fx, 'front')
        elif fx[0] == 'whirl': draw_whirl(fr, sc, fx[1], fx[2], fx[3], fx[4])
        elif fx[0] == 'note': draw_note(fr, sc, P, fx[1], fx[2], fx[3])
        elif fx[0] == 'twinkle': draw_twinkle(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'dizzy': draw_dizzy(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'snot': draw_snot(fr, sc, P, fx[1])
        elif fx[0] == 'pit': draw_pit(fr, sc, P, fx[1], fx[2], fx[3], 'front', *fx[4:])
        elif fx[0] == 'dirt': draw_dirt(fr, sc, P, fx[1], fx[2], fx[3])
        elif fx[0] == 'puff': draw_puff(fr, sc, fx[1], fx[2])
        elif fx[0] == 'gloom': draw_gloom(fr, sc, fx[1], fx[2], fx[3])
        elif fx[0] == 'item': draw_item_held(fr, sc, P, fx[1], fx[2], u, 'icon', _fx_item_centre(P, fx))
        elif fx[0] == 'work':
            if fx[1] not in WORK_BEHIND: draw_work(fr, sc, P, fx[1], fx[2], fx[3])
        elif fx[0] in ('stick', 'rays'): pass                  # drawn above, around the body
        else: rest.append(fx)
    if rest and fx_alpha > 0.002:
        if fx_alpha >= 0.998:
            C.draw_fx(fr, sc, P, rest, u)
        else:                                                   # draw on its own layer, scale alpha, composite
            lay = Image.new('RGBA', (sc.W, sc.H), (0, 0, 0, 0))
            C.draw_fx(lay, sc, P, rest, u)
            a = lay.getchannel('A').point(lambda v: int(v * fx_alpha + 0.5)); lay.putalpha(a)
            fr.alpha_composite(lay)
    return fr


def alpha_bbox(arr):
    m = arr[..., 3] > ALPHA_THR
    ys = np.flatnonzero(m.any(1)); xs = np.flatnonzero(m.any(0))
    if len(ys) == 0: return None
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def premul_bgra(rgba):
    a = rgba[..., 3:4].astype(np.uint16)
    rgb = (rgba[..., :3].astype(np.uint16) * a + 127) // 255
    out = np.empty(rgba.shape, np.uint8)
    out[..., 0] = rgb[..., 2]; out[..., 1] = rgb[..., 1]; out[..., 2] = rgb[..., 0]; out[..., 3] = rgba[..., 3]
    return out


def frame_inputs(name, ctx, loop, endpoint, k, N, fps):
    """-> (pose, fxs, u, fx_alpha) for frame k of N."""
    if loop:
        u = k / fps
        if name == 'idle': return idle_loop_pose(u), [], u, 1.0
        P, fxs = loop_pose(name, u)
        return P, fxs, u, 1.0
    D = ONESHOT_LEN.get(name) or C.action_dur(name, ctx)
    u = (k / (N - 1) * D) if (endpoint and N > 1) else k / fps
    fa = 1.0
    if name in WORK_POSES or name in REACTION_POSES:
        P, fxs = (WORK_POSES.get(name) or REACTION_POSES[name])(u, D)
        return P, fxs, u, clamp((D - u) / 0.3, 0.0, 1.0)     # effects are gone by the last frame
    if name in ONESHOT_LEN:
        if name in ('turn_left', 'turn_right'):
            P, fxs = turn_pose(u, D, -1 if name == 'turn_left' else 1)
            return P, fxs, u, 1.0                # no idle overlay: it must join the walk loops exactly
        else:
            P, fxs = {'land': land_pose, 'shy': shy_pose}[name](u, D)
    else:
        P = make_pose(); fxs = C.run_action(name, P, u, ctx, D)
        if name == 'think':
            fxs = [('bubble', fx[1], fx[2], 1.0) if fx[0] == 'bubble' else fx for fx in fxs]   # keep it alive; we fade it ourselves
            fa = clamp(min(D - u, u) / THINK_FADE, 0.0, 1.0)     # no bubble at either end
    if name in ('think', 'listen'):              # no sway and no glances: starts and ends in the plain pose
        P['tilt'] *= CALM_TILT
        arm = make_pose()['nubR']                # the arm stays at the side, it does not cross the body
        en = env_in_out(u, D, 0.35, 0.3) if name == 'think' else env_in_out(u, D, 0.3, 0.35)
        P['nubR'] = (lerp(arm[0], 42 if name == 'think' else 64, en), lerp(arm[1], 1.05, en)); P['frontR'] = False
        P['eye_open'] = min(P['eye_open'], lerp(1.0, C.blink_amount(u + 0.5), env_in_out(u, D, 0.3, 0.3)))
        if name == 'listen': fxs = list(fxs) + [('work', 'ear', u, env_in_out(u, D, 0.3, 0.35))]
        return P, fxs, u, fa
    if name in ('head_tilt', 'wink'): P['tilt'] *= SOFT_TILT
    C.apply_idle(P, u + 0.5)
    return P, fxs, u, fa


def action_len(name, ctx, loop):
    if loop: return LOOP_LEN[name]
    return ONESHOT_LEN.get(name) or C.action_dur(name, ctx)


# ---------------------------------------------------------------- atomic output
def swap_into_place(tmp, dst):
    old = dst + '.old'
    if os.path.isdir(old): shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(dst):
        ok = False
        for _ in range(15):
            try:
                os.replace(dst, old); ok = True; break
            except OSError:
                time.sleep(0.2)
        if not ok:        # something holds the directory open: replace file by file, manifest last
            names = sorted(os.listdir(tmp), key=lambda n: n == 'manifest.json')
            for n in names: os.replace(os.path.join(tmp, n), os.path.join(dst, n))
            keep = set(names)
            for n in os.listdir(dst):
                if n not in keep and (n.endswith('.frames')): os.remove(os.path.join(dst, n))
            shutil.rmtree(tmp, ignore_errors=True); return
    for attempt in range(15):             # a scanner or indexer can hold a just-written file for a moment
        try:
            os.replace(tmp, dst); break
        except OSError:
            if attempt == 14:
                if os.path.isdir(old) and not os.path.exists(dst): os.replace(old, dst)   # keep the previous set
                raise
            time.sleep(0.2)
    shutil.rmtree(old, ignore_errors=True)


def fsync_files(folder):
    """Flush a finished set to disk before it is swapped in, so a power cut cannot commit zero-filled files."""
    for n in os.listdir(folder):
        p = os.path.join(folder, n)
        if os.path.isfile(p):
            with open(p, 'r+b') as f:
                os.fsync(f.fileno())


# ---------------------------------------------------------------- process control
class _JobBasicLimits(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', ctypes.c_uint32), ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32),
                ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32), ('SchedulingClass', ctypes.c_uint32)]


class _JobExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _JobBasicLimits), ('IoInfo', ctypes.c_ulonglong * 6),
                ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


_job_handle = None      # held (never inherited) until this process ends: its closing kills the workers


def _kernel32():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.CreateJobObjectW.restype = ctypes.c_void_p
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    k.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    return k


def bind_children_to_this_process():
    """Put this process in a kill-on-close job before any worker exists, so workers cannot outlive it.
    Windows only: elsewhere a pool's workers end with it (multiprocessing stops them when the parent goes)."""
    global _job_handle
    if sys.platform != 'win32':
        return
    k = _kernel32()
    job = k.CreateJobObjectW(None, None)
    info = _JobExtendedLimits()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (not job or not k.SetInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info))
            or not k.AssignProcessToJobObject(job, k.GetCurrentProcess())):
        print('WARNING: no job object (error %d); workers may outlive a killed run' % ctypes.get_last_error())
        return
    _job_handle = job


def set_low_priority():
    if sys.platform != 'win32':
        os.nice(10)                  # about what BELOW_NORMAL_PRIORITY_CLASS is on Windows
        return
    k = _kernel32()
    k.SetPriorityClass(k.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)


# ---------------------------------------------------------------- pool tasks (module level: they get pickled)
def _read_crops(path):
    """Yield the straight-RGBA payloads of a chunk's crop file, in order."""
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    while off < len(data):
        (n,) = struct.unpack_from('<I', data, off)
        off += 4
        yield zlib.decompress(data[off:off + n])
        off += n


def _chunk_frames(path, bbs, union):
    """Yield the full straight-RGBA canvas of each frame of a chunk."""
    ux0, uy0, W, H = union
    crops = _read_crops(path)
    for bb in bbs:
        out = np.zeros((H, W, 4), np.uint8)
        if bb is not None:
            x0, y0, x1, y1 = bb
            out[y0 - uy0:y1 - uy0, x0 - ux0:x1 - ux0] = np.frombuffer(next(crops), np.uint8).reshape(y1 - y0, x1 - x0, 4)
        yield out


def _diff(a, b):
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def render_chunk(a_idx, k0, k1, N, fps, out_w, crop_path):
    """Pass 1: render frames k0..k1-1, spill their bbox crops, return the bboxes."""
    name, _label, ctx, loop, _afps, endpoint = ACTIONS[a_idx]
    sc = Scale(out_w)
    bbs = []
    with open(crop_path, 'wb') as f:
        for k in range(k0, k1):
            P, fxs, u, fa = frame_inputs(name, ctx, loop, endpoint, k, N, fps)
            fr = np.asarray(render_frame(sc, P, fxs, u, fa))
            bb = alpha_bbox(fr)
            bbs.append(bb)
            if bb is not None:
                x0, y0, x1, y1 = bb
                z = zlib.compress(fr[y0:y1, x0:x1].tobytes(), CROP_ZLEVEL)
                f.write(struct.pack('<I', len(z))); f.write(z)
    return bbs


def encode_chunk(crop_path, bbs, union, part_path, next_src):
    """Pass 2: full canvases -> final records.  next_src is None, or (crop_path, bbs) of the chunk holding the
    frame after this chunk's last one (for the last chunk of an action: its frame 0, the loop seam); it asks
    for the diff stats of the chunk, returned as (consecutive steps, diff to that following frame)."""
    steps = []
    prev = None
    with open(part_path, 'wb') as f:
        for fr in _chunk_frames(crop_path, bbs, union):
            z = zlib.compress(premul_bgra(fr).tobytes(), ZLEVEL)
            f.write(struct.pack('<I', len(z))); f.write(z)
            if next_src is not None:
                if prev is not None:
                    steps.append(_diff(prev, fr))
                prev = fr
    if next_src is None:
        return steps, None
    return steps, _diff(prev, next(_chunk_frames(next_src[0], next_src[1][:1], union)))


def think_last_frame_check(out_w, n, fps):
    """think: last frame bubble-free? compare with the same pose rendered without fx."""
    sc = Scale(out_w)
    P, fxs, u, fa = frame_inputs('think', {}, False, True, n - 1, n, fps)
    a = np.asarray(render_frame(sc, P, [], u, 1.0)); b = np.asarray(render_frame(sc, P, fxs, u, fa))
    return fa, int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max())


# a find is held in these: its place per frame goes to the manifest
ITEM_CLIPS = ('rummage_found', 'pull_out', 'present') + tuple(n + d for d in ('right', 'left') for n in (
    'bring_start_', 'bring_hold_', 'walk_bring_', 'hand_mid_', 'hand_small_', 'take_'))
ITEM_FPS = 12                     # the treasures' own little loops (items.LOOP_FRAMES frames each)


def item_track(name, ctx, loop, endpoint, N, fps, sc, ux0, uy0):
    """-> per frame [x, y, size in 1/1000] of the find's centre in canvas px, or 0 while there is none."""
    out = []
    for k in range(N):
        P, fxs, u, fa = frame_inputs(name, ctx, loop, endpoint, k, N, fps)
        it = next((fx for fx in fxs if fx[0] == 'item'), None)
        if it is None or it[2] <= 0.02:
            out.append(0)
        else:
            cx, cy = _fx_item_centre(P, it)
            out.append([int(round(cx * sc.s)) - ux0, int(round(cy * sc.s)) - uy0, int(round(it[2] * 1000))])
    return out


def _records(images):
    out = []
    for im in images:
        z = zlib.compress(premul_bgra(np.asarray(im.convert('RGBA'))).tobytes(), ZLEVEL)
        out.append(struct.pack('<I', len(z)) + z)
    return b''.join(out)


def render_item_file(kind, name, px, path):
    """One treasure's loop (kind 'item') or one rarity's glow (kind 'aura') at this size -> records like *.frames."""
    n = ITEMS.LOOP_FRAMES
    if kind == 'item':
        ims = [ITEMS.draw_item(name, px, t=i / float(n)) for i in range(n)]
    else:
        ims = [ITEMS.draw_aura(name, px, i / float(n)) for i in range(n)]
    with open(path, 'wb') as f:
        f.write(_records(ims))
    return ims[0].size[0]


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--body-px', type=float, default=100.0, help='width in physical px of Clawd (body + arms, idle pose)')
    ap.add_argument('--out', default=DEFAULT_OUT, help='frames directory (written via OUT.tmp then swapped in)')
    ap.add_argument('--fps', type=int, default=FPS)
    ap.add_argument('--workers', type=int, default=min(MAX_WORKERS, os.cpu_count() or 1))
    ap.add_argument('--no-preview', action='store_true', help='skip preview.png (the player never reads it)')
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out).rstrip('\\/')
    tmp_dir = out_dir + '.tmp'
    t_start = time.time()
    bind_children_to_this_process()
    set_low_priority()

    # calibrate scale: idle sprite (body + arms) width == body_px
    ref = Scale(1920 // 5)
    spr, _ = C.render(make_pose(), ref, SS=SS)
    s = args.body_px / (spr.size[0] / ref.s)
    out_w = int(round(1920 * s))
    sc = Scale(out_w)
    print('scale s=%.4f canvas %dx%d' % (sc.s, sc.W, sc.H))

    if os.path.isdir(tmp_dir): shutil.rmtree(tmp_dir)
    crop_dir = os.path.join(tmp_dir, 'crops')
    os.makedirs(crop_dir)
    try:
        with ProcessPoolExecutor(max_workers=max(1, args.workers), initializer=set_low_priority) as pool:
            try:
                manifest, nframes, total = run_passes(args, pool, sc, out_w, tmp_dir, crop_dir, t_start)
            except BaseException:
                pool.shutdown(wait=False, cancel_futures=True)      # don't finish the queue for a failed run
                raise
        shutil.rmtree(crop_dir, ignore_errors=True)
        with open(os.path.join(tmp_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        fsync_files(tmp_dir)
        swap_into_place(tmp_dir, out_dir)
        shutil.rmtree(os.path.join(out_dir, 'crops'), ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    W, H = manifest['width'], manifest['height']
    size_disk = sum(os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir) if f.endswith('.frames'))
    print('W x H = %d x %d ; total frames %d ; frames bytes %d (%.2f MB) ; avg %.0f B/frame (raw %d B/frame)'
          % (W, H, nframes, size_disk, size_disk / 1e6, total / nframes, W * H * 4))
    print('total %.1fs' % (time.time() - t_start))
    for name, label, ctx, loop, afps, endpoint in ACTIONS:
        info = manifest['actions'][name]
        print('  %-15s %4d frames @%2d fps %s  %d B' % (name, info['count'], info['fps'], 'loop' if loop else '    ',
                                                    os.path.getsize(os.path.join(out_dir, name + '.frames'))))


def run_passes(args, pool, sc, out_w, tmp_dir, crop_dir, t_start):
    # pass 1: render everything, one chunk of frames per pool task
    chunks = {}          # name -> [(k0, k1, crop_path), ...]
    meta = {}
    futs = {}
    for a_idx, (name, label, ctx, loop, afps, endpoint) in enumerate(ACTIONS):
        fps = afps or args.fps
        N = int(round(action_len(name, ctx, loop) * fps))
        meta[name] = dict(count=N, loop=loop, label=label, fps=fps)
        chunks[name] = []
        for k0 in range(0, N, CHUNK_FRAMES):
            k1 = min(N, k0 + CHUNK_FRAMES)
            path = os.path.join(crop_dir, '%s.%04d.crops' % (name, k0))
            chunks[name].append((k0, k1, path))
            futs[name, k0] = pool.submit(render_chunk, a_idx, k0, k1, N, fps, out_w, path)
    think_fut = pool.submit(think_last_frame_check, out_w, meta['think']['count'], meta['think']['fps'])
    bboxes = {}          # name -> [bbox or None per frame]
    for name in meta:
        bboxes[name] = [bb for k0, _k1, _p in chunks[name] for bb in futs[name, k0].result()]
    print('rendered %d frames with %d workers (%.1fs elapsed)'
          % (sum(len(b) for b in bboxes.values()), args.workers, time.time() - t_start))

    # union bbox + padding (feet anchored: every frame uses the same canvas, only cropped)
    ux0 = uy0 = 10 ** 9; ux1 = uy1 = -1
    who = {}             # which action sets each union edge
    for name in meta:
        for bb in bboxes[name]:
            if bb is None: continue
            x0, y0, x1, y1 = bb
            if x0 < ux0: ux0 = x0; who['l'] = name
            if y0 < uy0: uy0 = y0; who['t'] = name
            if x1 > ux1: ux1 = x1; who['r'] = name
            if y1 > uy1: uy1 = y1; who['b'] = name
    ux0 = max(0, ux0 - PAD); uy0 = max(0, uy0 - PAD); ux1 = min(sc.W, ux1 + PAD); uy1 = min(sc.H, uy1 + PAD)
    W, H = ux1 - ux0, uy1 - uy0
    union = (ux0, uy0, W, H)
    print('union bbox', (ux0, uy0, ux1, uy1), '-> W x H =', W, H, ' edges set by', who)

    # pass 2: encode the final records into OUT.tmp, one part per chunk, joined per action
    manifest = {'version': 2, 'fps': args.fps, 'width': W, 'height': H, 'base_body_px': int(round(args.body_px)),
                'renderer': {'python': VENV_PY, 'script': THIS_SCRIPT},
                'anchor': {'feet_x': int(round(PX * sc.s)) - ux0, 'feet_y': int(round(FLOOR_Y * sc.s)) - uy0},
                'actions': {}}
    futs = {}
    for name in meta:
        cs = chunks[name]
        for i, (k0, k1, path) in enumerate(cs):
            next_src = None
            if name in STAT_ACTIONS:
                nk0, nk1, npath = cs[(i + 1) % len(cs)]
                next_src = (npath, bboxes[name][nk0:nk1])
            futs[name, i] = pool.submit(encode_chunk, path, bboxes[name][k0:k1], union, path + '.part', next_src)
    total = 0; nframes = 0
    stats = {}           # name -> (consecutive steps, last->first)
    for name, label, ctx, loop, afps, endpoint in ACTIONS:
        fn = name + '.frames'
        steps = []; seam = None
        with open(os.path.join(tmp_dir, fn), 'wb') as f:
            for i, (k0, k1, path) in enumerate(chunks[name]):
                part_steps, after = futs[name, i].result()
                steps += part_steps
                if i + 1 < len(chunks[name]):
                    if after is not None: steps.append(after)
                else:
                    seam = after
                with open(path + '.part', 'rb') as p:
                    data = p.read()
                f.write(data); total += len(data)
                os.remove(path + '.part')
        nframes += meta[name]['count']
        stats[name] = (steps, seam)
        manifest['actions'][name] = {'file': fn, 'count': meta[name]['count'], 'loop': loop, 'label': label, 'fps': meta[name]['fps']}
        if name.startswith('sign_'):           # where the player puts the board: the stick's top while held, canvas px
            P, _ = sign_pose(SIGN_HOLD_AT, SIGN_LEN, 1 if name == 'sign_right' else -1)
            _, (sx, sy) = sign_top(P, 1 if name == 'sign_right' else -1)
            manifest['actions'][name]['top'] = [int(round(sx * sc.s)) - ux0, int(round(sy * sc.s)) - uy0]

    # loop seam numbers: mean abs diff (straight RGBA) last->first vs typical consecutive step
    for name in ('idle', 'sleep', 'walk', 'dangle'):
        n = meta[name]['count']; fps = meta[name]['fps']
        steps, seam = stats[name]
        Pn, _ = (lambda tau: (idle_loop_pose(tau), None))(n / fps) if name == 'idle' else frame_pose_only(name, n / fps)
        P0, _ = (idle_loop_pose(0.0), None) if name == 'idle' else frame_pose_only(name, 0.0)
        num = max(abs(Pn[k] - P0[k]) for k in ('sx', 'sy', 'tilt', 'lift', 'walkamp', 'blush'))
        num += max(abs(Pn['look'][i] - P0['look'][i]) for i in (0, 1))
        num += max(abs(Pn['nub' + k][i] - P0['nub' + k][i]) for k in 'LR' for i in (0, 1))
        num += abs(math.sin(math.pi * Pn['walk']) - math.sin(math.pi * P0['walk'])) + abs(math.cos(math.pi * Pn['walk']) - math.cos(math.pi * P0['walk'])) if name in ('walk', 'dangle') else 0
        print('%-7s seam: last->first mean|diff| = %.4f ; consecutive steps mean %.4f max %.4f ; pose(T) vs pose(0) param diff %.2e'
              % (name, seam, float(np.mean(steps)), float(np.max(steps)), num))
    fa, maxdiff = think_fut.result()
    print('think last frame: fade alpha %.3f ; max |diff| vs bubble-free render = %d' % (fa, maxdiff))
    steps = stats['think'][0]
    print('think consecutive step mean %.3f max %.3f (last steps %s)' % (np.mean(steps), np.max(steps), ['%.2f' % x for x in steps[-5:]]))

    # the treasures: every icon's loop and every rarity's glow at this set's size, and where a find is held
    for name in ITEM_CLIPS:
        a = next(a for a in ACTIONS if a[0] == name)
        manifest['actions'][name]['item'] = item_track(name, a[2], a[3], a[5], meta[name]['count'], meta[name]['fps'], sc, ux0, uy0)
    box = max(8, int(round(ITEM_BOX * sc.s)))
    futs = {('item', n): pool.submit(render_item_file, 'item', n, box, os.path.join(tmp_dir, 'item_%s.frames' % n)) for n in ITEMS.ORDER}
    futs.update({('aura', r): pool.submit(render_item_file, 'aura', r, box, os.path.join(tmp_dir, 'aura_%s.frames' % r)) for r in ITEMS.AURA})
    manifest['items'] = {'box': box, 'frames': ITEMS.LOOP_FRAMES, 'fps': ITEM_FPS, 'order': list(ITEMS.ORDER),
                         'names': {n: {'file': 'item_%s.frames' % n, 'zh': ITEMS.ITEMS[n][0], 'en': ITEMS.ITEMS[n][1], 'rarity': ITEMS.ITEMS[n][2]}
                                   for n in ITEMS.ORDER},
                         'auras': {r: {'file': 'aura_%s.frames' % r, 'size': futs['aura', r].result()} for r in ITEMS.AURA}}
    for n in ITEMS.ORDER: futs['item', n].result()

    if not args.no_preview:
        make_preview(os.path.join(tmp_dir, 'preview.png'), chunks, bboxes, union, meta, W, H)
    print('encoded (%.1fs elapsed)' % (time.time() - t_start))
    return manifest, nframes, total


def frame_pose_only(name, u):
    return loop_pose(name, u)


def make_preview(path, chunks, bboxes, union, meta, W, H, per=3):
    from PIL import ImageFont

    def frame_at(name, i):
        for k0, k1, crop_path in chunks[name]:
            if k0 <= i < k1:
                for j, fr in enumerate(_chunk_frames(crop_path, bboxes[name][k0:k1], union)):
                    if j == i - k0:
                        return fr

    names = [a[0] for a in ACTIONS]; cols = 3
    cw = (W + 14) * per + 14; lab_h = 30; ch = H + lab_h + 10
    rows = math.ceil(len(names) / cols)
    sheet = Image.new('RGBA', (cols * cw, rows * ch), (0x1A, 0x1B, 0x26, 255)); d = ImageDraw.Draw(sheet)
    try: ft = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 18)
    except Exception: ft = ImageFont.load_default()
    for idx, name in enumerate(names):
        r, c = divmod(idx, cols); X0, Y0 = c * cw, r * ch
        n = meta[name]['count']
        d.text((X0 + 14, Y0 + 4), '%s %s (%d @%d)' % (name, meta[name]['label'], n, meta[name]['fps']), font=ft, fill=(200, 205, 230, 255))
        fr = PREVIEW_FRACS.get(name, (0.15, 0.45, 0.8))
        if meta[name]['loop']: fr = (0.0, 1 / 3.0, 2 / 3.0)
        idxs = [min(n - 1, int(round((n - 1) * f)) if name in PREVIEW_FRACS else int(n * f)) for f in fr]
        for j, i in enumerate(idxs):
            img = Image.fromarray(frame_at(name, min(i, n - 1)), 'RGBA')
            sheet.alpha_composite(img, (X0 + 14 + j * (W + 14), Y0 + lab_h))
            d.rectangle((X0 + 14 + j * (W + 14), Y0 + lab_h, X0 + 14 + j * (W + 14) + W - 1, Y0 + lab_h + H - 1), outline=(60, 62, 85, 255))
    sheet.convert('RGB').save(path)


if __name__ == '__main__':
    main()
