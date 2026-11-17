# Combos: by hand, by themselves, and everything that must interrupt them.
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import family_test as t
from family_test import check, send, since, mark, wait_for, windows, stop, plays

QUIET = ('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999', '--combo-interval', '9999', '--return-after', '9999')
HOME_STATE = {'x': 1800, 'y': 1000, 'scale': 1.0, 'wanted': 1.0, 'slots': [1, 2],
              'pos': {'1': [1500, 1000], '2': [1450, 880]}}


def begin(slots=(1, 2), keep=False, args=QUIET):
    if not keep:
        d = dict(HOME_STATE, slots=list(slots))
        with open(t.STATE, 'w') as f:
            json.dump(d, f)
    t.start(*args)


def over(m, name, secs=14):
    return wait_for(lambda: 'combo %s over' % name in since(m) or 'combo %s cancelled' % name in since(m), secs)


def by_hand():
    print('--- by hand')
    t.fresh()
    begin()
    check('three to start with', len(windows()) == 3, len(windows()))

    m = mark()
    send('combo:high_five')
    ok = over(m, 'high_five')
    text = since(m)
    check('high five: over', ok and 'combo high_five over' in text, plays(text))
    fives = re.findall(r'\[\d+\] (pet\d )?play high_five_(up_)?(left|right)', text)
    check('two pets, facing each other', len(fives) == 2 and {f[2] for f in fives} == {'left', 'right'}, fives)
    check('the smaller one jumps', sum(1 for f in fives if f[1]) == 1, fives)
    when = re.findall(r'(\d\d:\d\d:\d\d) \[\d+\] (?:pet\d )?play high_five', text)
    check('in sync', len(set(when)) <= 2, when)
    time.sleep(0.5)
    f = t.feet()
    who_ = re.search(r'combo high_five: pet(\d), pet(\d)', text)
    a, b = int(who_.group(1)), int(who_.group(2))
    size = {0: 100, 1: 80, 2: 60}
    want = 0.64 * max(size[a], size[b]) + 0.34 * min(size[a], size[b])
    check('they stand so that the arms meet', abs(abs(f[a][0] - f[b][0]) - want) <= 2 and f[a][1] == f[b][1], (f, want))

    m = mark()
    send('combo:peek')
    ok = over(m, 'peek')
    text = since(m)
    check('peek: a small one comes and looks', ok and re.search(r'pet\d play peek_', text) and 'combo peek over' in text, plays(text))
    side = re.search(r'pet(\d) play peek_(left|right)', text)
    f = t.feet()
    if side:
        s, d = int(side.group(1)), side.group(2)
        check('it looks toward the big one', (f[s][0] < f[0][0]) == (d == 'right'), (f, d))

    m = mark()
    send('combo:celebrate_all')
    ok = over(m, 'celebrate_all')
    text = since(m)
    n = len(re.findall(r'play celebrate', text))
    check('celebrate: all three', ok and n == 3, plays(text))
    f = t.feet()
    xs = sorted(v[0] for v in f.values())
    check('they stand apart', xs[1] - xs[0] >= 60 and xs[2] - xs[1] >= 60, f)
    check('on one row', len({v[1] for v in f.values()}) <= 2, f)

    stop()


def asleep():
    print('--- waking')
    begin(args=('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '4', '--combo-interval', '9999', '--wake-after', '2-2'))
    m = mark()
    ok = wait_for(lambda: 'combo wake:' in since(m), 14)
    check('asleep a while: a small one goes to wake the big one', ok, plays(since(m))[-6:])
    ok = wait_for(lambda: 'combo wake over' in since(m), 14)
    time.sleep(2.5)                      # it gets up and nods after the combo
    text = since(m)
    check('it nudges', re.search(r'pet\d play nudge_', text) is not None, plays(text))
    order = plays(text)
    mover = next((p.split()[0] for p in order if ' play nudge_' in p), 'pet?')
    seq = [p.split(' play ')[1] for p in order if p.startswith(mover)]
    check('it gets up before it walks', 'wake_up' in seq and any(c.startswith('walk_') for c in seq) and seq.index('wake_up') < min(i for i, c in enumerate(seq) if c.startswith('walk_')), seq)
    check('the big one gets up and nods', ok and re.search(r'\] play wake_up', text) and re.search(r'\] play nod', text), order)
    check('all are awake', text.count('woke up') >= 3, text.count('woke up'))
    time.sleep(1)
    m = mark()
    wait_for(lambda: 'combo wake:' in since(m) or since(m).count('fell asleep') >= 3, 12)
    wait_for(lambda: 'combo wake:' in since(m), 6)
    m = mark()
    if 'combo wake:' not in since(m):
        send('listen aaaaaaaa')
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()


def wake_by_hand():
    print('--- waking by hand')
    begin(args=('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '4', '--combo-interval', '9999'))
    m = mark()
    wait_for(lambda: since(m).count('fell asleep') >= 3, 10)
    time.sleep(0.5)
    m = mark()
    send('combo:wake')
    ok = wait_for(lambda: 'combo wake over' in since(m), 16); time.sleep(2.5)
    text = since(m)
    check('all asleep, by hand: over', ok, plays(text))
    nudge = re.search(r'pet\d play nudge_', text)
    before = text[:nudge.start()] if nudge else text
    check('the big one sleeps on until it is nudged', nudge and not re.search(r'\] play ', before) and len(re.findall(r'\] woke up', before)) == 1, before.splitlines()[:8])
    check('then it gets up and nods', re.search(r'\] play wake_up', text) and re.search(r'\] play nod', text), plays(text))
    stop()

    # asleep because you told it to, the others awake
    begin()
    m = mark()
    send('sleep')
    wait_for(lambda: 'play sleep' in since(m), 3)
    time.sleep(1)
    m = mark()
    send('combo:wake')
    ok = wait_for(lambda: 'combo wake over' in since(m), 16); time.sleep(2.5)
    text = since(m)
    nudge = re.search(r'pet\d play nudge_', text)
    before = text[:nudge.start()] if nudge else text
    check('one asleep by hand: another walks to it', ok and nudge and re.search(r'pet\d play walk_', before), plays(text))
    check('it sleeps until then', not re.search(r'\] play ', before), plays(before))
    check('and gets up', re.search(r'\] play wake_up', text), plays(text))
    stop()


def interruptions():
    print('--- interrupted')
    begin()
    hs = lambda: sorted(windows(), key=lambda h: t.rect(h)[2] - t.rect(h)[0])

    def walking(name='high_five'):
        d = t.state()
        d['pos'] = HOME_STATE['pos']
        m = mark()
        send('combo:' + name)
        wait_for(lambda: 'combo %s:' % name in since(m), 3)
        return m

    # dragged while it walks
    send('family:3')
    time.sleep(0.5)
    t.drag(hs()[0], -300, -250)        # far away, so that the next combo has a walk
    t.drag(hs()[1], -300, 200)
    time.sleep(1)
    m = walking()
    time.sleep(0.25)
    t.drag(hs()[0] if 'pet2' in since(m) else hs()[1], -60, -60)
    time.sleep(0.5)
    text = since(m)
    check('dragged: the combo is cancelled', 'cancelled (dragged)' in text or 'combo high_five over' in text, text.splitlines()[:3])
    check('and it hangs in the hand', 'play dangle' in text, plays(text))
    time.sleep(2)

    # an event while the big one takes part
    t.drag(hs()[1], -250, 150)
    time.sleep(1)
    m = mark()
    send('combo:celebrate_all')
    time.sleep(0.2)
    send('listen aaaaaaaa')
    ok = wait_for(lambda: 'cancelled (event listen)' in since(m), 3)
    check('work comes first: an event cancels it', ok, since(m).splitlines()[:3])
    check('and the big one listens', wait_for(lambda: re.search(r'\] play listen', since(m)) is not None, 4), plays(since(m)))

    # while the big one works it is not asked to join
    m = mark()
    send('combo:celebrate_all')
    ok = over(m, 'celebrate_all')
    text = since(m)
    check('while it works: the two small ones only', ok and len(re.findall(r'pet\d play celebrate', text)) == 2 and not re.search(r'\] play celebrate', text), plays(text))

    # a peek goes on through the work: the big one is not part of it
    m = mark()
    send('combo:peek')
    wait_for(lambda: 'combo peek:' in since(m), 3)
    send('read aaaaaaaa')
    ok = over(m, 'peek')
    text = since(m)
    check('tool events do not stop a peek', ok and 'combo peek over' in text and 'play work_read' in text, plays(text))
    send('stop aaaaaaaa')
    time.sleep(3)

    # a click stops the walk: no high five at a distance
    t.drag(hs()[1], 220, -220)
    time.sleep(1)
    t.drag(hs()[0], -200, -180)
    time.sleep(1)
    m = mark()
    send('combo:high_five')
    wait_for(lambda: 'combo high_five:' in since(m), 3)
    text = since(m)
    who_ = re.search(r'combo high_five: pet(\d)', text)
    h = hs()[2 - int(who_.group(1))]
    time.sleep(0.2)
    r = t.rect(h)
    p = t.lp((r[2] - r[0]) // 2, (r[3] - r[1]) * 2 // 3)
    t.u.PostMessageW(h, t.WM_LDOWN, 1, p)
    time.sleep(0.03)
    t.u.PostMessageW(h, t.WM_LUP, 0, p)
    ok = wait_for(lambda: 'the walk was stopped' in since(m), 3)
    time.sleep(1.8)
    check('a click stops the walk: cancelled', ok, plays(since(m)))
    check('no high five at a distance', 'play high_five' not in since(m), plays(since(m)))

    # dragging the big one while a small one walks to it
    t.drag(hs()[1], -220, 220)
    time.sleep(1)
    m = mark()
    send('combo:peek')
    wait_for(lambda: 'combo peek:' in since(m), 3)
    time.sleep(0.1)
    t.drag(hs()[2], -40, -160)
    ok = wait_for(lambda: 'combo peek cancelled (dragged)' in since(m) or 'combo peek over' in since(m), 3)
    check('the big one dragged away: no peek at empty space', ok and 'combo peek cancelled (dragged)' in since(m), since(m).splitlines()[:3])
    time.sleep(2)

    # by hand, the big one awake: it is only startled
    m = mark()
    send('combo:wake')
    ok = over(m, 'wake')
    text = since(m)
    check('wake by hand, the big one awake: it is startled', ok and 'combo wake over' in text and re.search(r'pet\d play nudge_', text)
          and re.search(r'\] play surprised', text), plays(text))
    time.sleep(1.5)

    # the big one at work, dropped on a small one
    send('listen aaaaaaaa')
    time.sleep(0.5)
    b, s_ = t.rect(hs()[2]), t.rect(hs()[0])
    m = mark()
    t.drag(hs()[2], (s_[0] + s_[2]) // 2 - (b[0] + b[2]) // 2, s_[3] - b[3])
    time.sleep(1.5)
    check('the big one at work, dropped on a small one: no combo', 'combo high_five' not in since(m), since(m).splitlines()[:3])
    send('stop aaaaaaaa')
    time.sleep(3)

    # size and number of pets
    t.drag(hs()[1], 200, -200)
    time.sleep(1)
    m = mark()
    send('combo:high_five')
    time.sleep(0.1)
    send('size:110')
    ok = wait_for(lambda: 'cancelled (size)' in since(m) or 'combo high_five over' in since(m), 3)
    check('size: cancelled', ok, since(m).splitlines()[:3])
    send('size:100')
    time.sleep(1)
    t.drag(hs()[1], -200, 200)
    time.sleep(1)
    m = mark()
    send('combo:high_five')
    time.sleep(0.1)
    send('family:1')
    check('number of pets: cancelled, one left', t.count_is(1), len(windows()))
    time.sleep(1)
    check('and no combo left behind', 'cancelled (number of pets)' in since(m) or 'combo high_five over' in since(m), since(m).splitlines()[:3])
    m = mark()
    send('combo:high_five')
    time.sleep(0.8)
    check('one pet: not now', 'combo high_five: not now' in since(m), since(m).splitlines()[:2])
    send('family:2')
    t.count_is(2)
    time.sleep(0.5)
    send('listen aaaaaaaa')
    time.sleep(0.5)
    m = mark()
    send('combo:high_five')
    time.sleep(0.8)
    check('two pets, the big one works: not now', 'not now' in since(m), since(m).splitlines()[:2])
    send('stop aaaaaaaa')
    time.sleep(3)
    send('family:3')
    t.count_is(3)
    time.sleep(1)

    # dropped on another one
    t.drag(hs()[2], 150, 0)            # room around it
    time.sleep(1)
    d = t.feet()
    m = mark()
    t.drag(hs()[0], d[0][0] - d[2][0], d[0][1] - d[2][1])
    ok = wait_for(lambda: 'combo high_five over' in since(m), 10)
    text = since(m)
    check('dropped on the big one: a high five', ok and 'combo high_five: pet2, pet0' in text and 'combo high_five over' in text, text.splitlines()[-4:])
    stop()


def company():
    print('--- company while it works')
    begin(args=QUIET[:-2] + ('--return-after', '1-1', '--mimic-interval', '2-2', '--peek-after', '9999'))
    m = mark()
    send('listen aaaaaaaa')
    time.sleep(7)
    check('nothing to copy while it listens', not re.search(r'pet\d play work_', since(m)), plays(since(m)))
    m = mark()
    send('read aaaaaaaa')
    ok = wait_for(lambda: re.search(r'pet\d play work_read', since(m)) is not None, 8)
    check('a small one copies the tool', ok, plays(since(m)))
    time.sleep(1)
    now_copying = len(re.findall(r'pet\d play work_read', since(m)))
    check('only one at a time', now_copying == 1, plays(since(m)))
    t0 = time.time()
    who_ = re.search(r'(pet\d) play work_read', since(m)).group(1) if ok else 'pet?'
    done = wait_for(lambda: (who_ + ' play idle') in since(m), 8)
    check('and stops after a few seconds', done and time.time() - t0 < 6, '%.1f s' % (time.time() - t0))
    check('the big one goes on', not re.search(r'\] play idle', since(m)), plays(since(m)))
    send('stop aaaaaaaa')
    time.sleep(1.5)
    stop()

    print('--- coming to watch, walking back')
    begin(args=QUIET[:-2] + ('--return-after', '1-1', '--mimic-interval', '9999', '--peek-after', '3'))
    before = t.feet()
    m = mark()
    send('listen aaaaaaaa')
    send('run aaaaaaaa')
    ok = wait_for(lambda: 'combo peek over' in since(m), 14)
    check('at a command: a small one comes to watch', ok, plays(since(m)))
    time.sleep(21)                       # a turn of 20 s: the reaction at the end hits the way back
    text = since(m)
    check('and only one of them', len(set(re.findall(r'combo peek: (pet\d)', text))) == 1, text.count('combo peek:'))
    text = since(m)
    s_ = int(re.search(r'combo peek: pet(\d)', text).group(1)) if ok else 1
    time.sleep(0.5)
    away = t.feet()
    check('it stays while the work goes on', abs(away[s_][0] - before[s_][0]) > 30, (before, away))
    m = mark()
    send('stop aaaaaaaa')
    ok = wait_for(lambda: 'wander done' in since(m) or 'walks back' in since(m), 6)
    wait_for(lambda: t.feet()[s_] == before[s_], 20)
    check('after the work it walks back', t.feet()[s_] == before[s_], (before, t.feet()))
    stop()

    print('--- high five, then back; dropped stays')
    begin(args=QUIET[:-2] + ('--return-after', '1-1', '--mimic-interval', '9999', '--peek-after', '9999'))
    before = t.feet()
    m = mark()
    send('combo:celebrate_all')
    over(m, 'celebrate_all')
    wait_for(lambda: t.feet() == before, 14)
    check('after a combo they walk back', t.feet() == before, (before, t.feet()))
    hs = lambda: sorted(windows(), key=lambda h: t.rect(h)[2] - t.rect(h)[0])
    d = t.feet()
    m = mark()
    t.drag(hs()[0], d[0][0] - d[2][0], d[0][1] - d[2][1])
    ok = wait_for(lambda: 'combo high_five over' in since(m), 10)
    time.sleep(0.4)
    after = t.feet()
    time.sleep(5)
    check('dropped on another: high five, and it stays', ok and t.feet() == after and 'combo high_five:' in since(m), (after, t.feet()))
    stop()


def three_in_a_row():
    print('--- no shuffling to and fro')
    d = dict(HOME_STATE, x=1800, y=1000, pos={'1': [1698, 1000], '2': [1619, 1000]})
    with open(t.STATE, 'w') as f:
        json.dump(d, f)
    t.start(*(QUIET[:-2] + ('--return-after', '9999', '--mimic-interval', '9999', '--peek-after', '1')))
    m = mark()
    send('listen aaaaaaaa')
    send('run aaaaaaaa')
    wait_for(lambda: 'combo peek over' in since(m), 12)
    m2 = mark()
    time.sleep(14)
    check('a watcher in the default layout stays put', 'walks aside' not in since(m2) and 'walk to' not in since(m2), since(m2).splitlines()[:4])
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()

    print('--- away when it closes')
    d = dict(HOME_STATE, x=1800, y=1000, pos={'1': [1500, 1000], '2': [1300, 880]})
    with open(t.STATE, 'w') as f:
        json.dump(d, f)
    t.start(*(QUIET[:-2] + ('--return-after', '9999')))
    before = t.feet()
    m = mark()
    send('combo:celebrate_all')
    over(m, 'celebrate_all')
    time.sleep(0.5)
    away = t.feet()
    stop()
    check('saved: the place to go back to', t.state().get('homes', {}).get('1') == list(before[1]), t.state())
    t.start(*(QUIET[:-2] + ('--return-after', '1-1')))
    wait_for(lambda: t.feet() == before, 14)
    check('after a restart it still walks back', t.feet() == before, (before, away, t.feet()))
    check('and nothing is left to go back to', wait_for(lambda: 'homes' not in t.state(), 2), t.state())
    stop()


def depth():
    print('--- in front and behind')
    d = dict(HOME_STATE, x=1500, y=1000, pos={'1': [1500, 1090], '2': [1300, 1000]})
    with open(t.STATE, 'w') as f:
        json.dump(d, f)
    t.start(*QUIET)
    time.sleep(0.5)
    width = lambda h: t.rect(h)[2] - t.rect(h)[0]
    top = windows()
    sizes = [width(h) for h in top]
    check('lower feet are in front', sizes[0] == sorted(sizes)[1], sizes)   # the 80 % one is lowest
    hs = sorted(windows(), key=width)
    t.drag(hs[1], 0, -220)             # the 80 % one, up: now far behind the big one
    time.sleep(0.8)
    top = windows()
    sizes2 = [width(h) for h in top]
    check('dragged up it goes behind', sizes2[-1] == sorted(sizes2)[1], sizes2)

    m = mark()
    time.sleep(5)
    check('one behind another stays there', 'walks aside' not in since(m), since(m).splitlines()[:3])
    stop()

    print('--- on one row')
    d = dict(HOME_STATE, x=1500, y=1000, pos={'1': [1470, 1000], '2': [1100, 1000]})
    with open(t.STATE, 'w') as f:
        json.dump(d, f)
    t.start(*QUIET)
    m = mark()
    ok = wait_for(lambda: 'pet1 walks aside' in since(m), 6)
    check('on one row, on top of each other: the smaller walks aside', ok, since(m).splitlines()[:3])
    wait_for(lambda: abs(t.feet()[1][0] - 1500) >= 100, 10)
    f = t.feet()
    check('until they stand apart', abs(f[1][0] - f[0][0]) >= 100, f)
    stop()

    # dropped behind another: no high five
    d = dict(HOME_STATE, x=1500, y=1000, pos={'1': [1100, 1000], '2': [1300, 1000]})
    with open(t.STATE, 'w') as f:
        json.dump(d, f)
    t.start(*QUIET)
    hs = sorted(windows(), key=width)
    m = mark()
    t.drag(hs[0], 200, -80)
    time.sleep(3)
    check('dropped behind another: no combo, no moving', 'combo high_five' not in since(m) and 'walks aside' not in since(m), since(m).splitlines()[-4:])
    stop()


def parade():
    print('--- parade')
    t.fresh()
    begin()
    m = mark()
    send('combo:parade')
    ok = over(m, 'parade', 25)
    text = since(m)
    check('parade: over', ok and 'combo parade over' in text, text.splitlines()[-4:])
    check('all three take part', 'combo parade: pet0, pet1, pet2' in text, text.splitlines()[:2])
    turns = re.findall(r'play turn_(left|right)', text)
    check('all turn, the same way', len(turns) == 3 and len(set(turns)) == 1, turns)
    walks = re.findall(r'walk to \((-?\d+), (-?\d+)\) in ([\d.]+)s', text)
    outs = [w for w in walks if w[2] == '4.2']
    check('six walks at one pace, three each way', len(outs) == 6, walks)
    if len(outs) == 6:
        check('the row keeps its gaps', len(set(int(a[0]) - int(b[0]) for a, b in zip(outs[:3], outs[3:]))) == 1, outs)
        check('and is in one line', len(set(w[1] for w in outs)) == 1, outs)
    m = mark()
    send('combo:parade')
    wait_for(lambda: 'combo parade:' in since(m), 3)
    time.sleep(1.0)
    send('read')
    ok = wait_for(lambda: 'combo parade cancelled (event read)' in since(m), 3)
    check('work stops a parade', ok, since(m).splitlines()[-3:])
    send('stop')
    stop()


def comfort():
    print('--- comfort')
    t.fresh()
    begin()
    m = mark()
    send('combo:comfort')
    ok = over(m, 'comfort', 12)
    text = since(m)
    check('comfort by hand: over', ok and 'combo comfort over' in text, text.splitlines()[-4:])
    pats = re.findall(r'play comfort_(left|right)', text)
    check('two pat, from both sides', sorted(pats) == ['left', 'right'], pats)
    check('the big one nods', 'play nod' in text, plays(text))
    m = mark()
    send('think')
    time.sleep(0.5)
    send('fail')
    time.sleep(0.5)
    send('fail')
    ok = wait_for(lambda: 'combo comfort:' in since(m), 3)
    check('two failures: they come', ok, since(m).splitlines()[:6])
    ok = over(m, 'comfort', 12)
    text = since(m)
    check('work goes on, comfort is not cancelled', ok and 'combo comfort over' in text and 'comfort cancelled' not in text, text.splitlines()[-4:])
    check('the big one is confused first', 'play confused' in text, plays(text))
    m = mark()
    send('stopfail')
    wait_for(lambda: 'combo comfort:' in since(m), 3)
    check('a turn that failed: comfort', 'combo comfort:' in since(m), since(m).splitlines()[:6])
    over(m, 'comfort', 12)
    stop()
    t.fresh()
    begin(slots=())
    m = mark()
    send('combo:comfort')
    wait_for(lambda: 'combo comfort' in since(m), 3)
    check('one pet: not now', 'combo comfort: not now' in since(m), since(m).splitlines()[:2])
    m = mark()
    send('fail')
    time.sleep(0.3)
    send('fail')
    time.sleep(1.0)
    check('one pet: failing starts nothing', 'combo comfort:' not in since(m), since(m).splitlines()[:4])
    stop()


def player_const(name):
    with open(os.path.join(t.T, 'clawd_pet.pyw'), encoding='utf-8') as f:
        src = f.read()
    m = re.search(r'^%s(?:, \w+)* = ([^#\n]+)' % name, src, re.M)
    if m:
        return float(m.group(1).split(',')[0])
    m = re.search(r'^(\w+(?:, \w+)+) = ([^#\n]+)', src[src.find(name) - 40:], re.M)
    names = [n.strip() for n in m.group(1).split(',')]
    return float(m.group(2).split(',')[names.index(name)])


def biggest():
    hs = windows()
    return max(hs, key=lambda h: (t.rect(h)[2] - t.rect(h)[0]) * (t.rect(h)[3] - t.rect(h)[1]))


def landed(text):
    return [(p or 'pet0', int(x), int(y)) for p, x, y in re.findall(r'\] (pet\d )?landed at \((-?\d+), (-?\d+)\)', text)]


def stack():
    print('--- tower')
    head, sink = player_const('STACK_HEAD'), player_const('STACK_SINK')
    t.fresh()
    begin()
    m = mark()
    send('combo:stack')
    ok = over(m, 'stack', 30)
    text = since(m)
    check('tower of three: over', ok and 'combo stack over' in text, text.splitlines()[-4:])
    check('all three, the big one at the bottom', 'combo stack: pet0, pet1, pet2' in text, text.splitlines()[:2])
    check('the bottom two brace', re.search(r'\] play stack_brace', text) and re.search(r'pet1 play stack_brace', text), plays(text))
    check('the top one cheers', 'pet2 play stack_top' in text and 'pet1 play stack_top' not in text, plays(text))
    hops = re.findall(r'(pet\d) hop (up onto pet\d|down)', text)
    check('up one by one, down from the top', hops == [('pet1', 'up onto pet0'), ('pet2', 'up onto pet1'), ('pet2', 'down'), ('pet1', 'down')], hops)
    f = t.feet()
    lands = landed(text)
    if len(lands) == 4:
        y1 = f[0][1] - round(head * 100) + sink
        y2 = y1 - round(head * 80) + sink
        check('each stands on the head below', lands[0][2] == y1 and lands[1][2] == y2 and lands[0][1] == lands[1][1] == f[0][0], (lands, f[0], y1, y2))
    else:
        check('four landings', False, lands)
    check('all back on the floor', f[1][1] == f[0][1] and f[2][1] == f[0][1], f)
    check('no one floats in the saved state', all(v[1] == f[0][1] for v in f.values()), f)

    m = mark()                                  # work comes first: the tower comes down
    send('combo:stack')
    wait_for(lambda: 'pet2 landed' in since(m) or 'pet1 landed' in since(m), 12)
    send('read aaaaaaaa')
    ok = wait_for(lambda: 'combo stack cancelled (event read)' in since(m), 3)
    check('work breaks up a tower', ok, since(m).splitlines()[-3:])
    time.sleep(2.5)
    f = t.feet()
    text = since(m)
    check('those up there come down', f[1][1] == f[0][1] and f[2][1] == f[0][1] and 'hop down' in text, (f, re.findall(r'pet\d hop \w+', text)))
    send('stop aaaaaaaa')
    time.sleep(2.5)

    m = mark()                                  # the big one dragged away from under them
    send('combo:stack')
    ok = wait_for(lambda: 'pet1 landed' in since(m), 12)
    ground_y = t.feet()[0][1]
    t.drag(biggest(), -260, 0)
    ok = wait_for(lambda: 'combo stack cancelled (dragged)' in since(m), 3) and ok
    check('dragging the bottom one breaks it up', ok, since(m).splitlines()[-3:])
    time.sleep(2.5)
    f = t.feet()
    check('and they come down to the floor', f[1][1] == ground_y and f[2][1] == ground_y, (f, ground_y))

    m = mark()                                  # a size change: down at once
    send('combo:stack')
    wait_for(lambda: 'pet1 landed' in since(m), 12)
    send('size:120')
    time.sleep(0.6)
    f = t.feet()
    check('a size change puts them down at once', abs(f[1][1] - f[0][1]) <= 2 and abs(f[2][1] - f[0][1]) <= 2, f)
    send('size:100')
    time.sleep(1.5)
    stop()

    print('--- tower of two, and put on its head by hand')
    t.fresh()
    begin(slots=(1,))
    m = mark()
    send('combo:stack')
    ok = over(m, 'stack', 25)
    text = since(m)
    check('tower of two: over', ok and 'combo stack over' in text and 'pet1 play stack_top' in text, plays(text))
    time.sleep(0.5)
    f = t.feet()
    hs = sorted(windows(), key=lambda h: (t.rect(h)[2] - t.rect(h)[0]))
    small = hs[0]
    dx = f[0][0] - f[1][0]
    dy = int((f[0][1] - round(head * 100) + sink) - f[1][1])
    m = mark()
    t.drag(small, dx, dy)
    ok = over(m, 'stack', 15)
    text = since(m)
    check('dropped on its head: a tower', 'combo stack: pet0, pet1' in text, text.splitlines()[:8])
    check('it cheers up there and comes down', ok and 'pet1 play stack_top' in text and 'pet1 hop down' in text, plays(text))
    time.sleep(0.5)
    f = t.feet()
    check('beside the big one, on the floor', f[1][1] == f[0][1] and abs(f[1][0] - f[0][0]) >= 80, f)

    m = mark()                                  # quit while up there: saved on the floor
    send('combo:stack')
    wait_for(lambda: 'pet1 landed' in since(m), 12)
    ground = t.feet()[0][1]
    stop()
    f = t.feet()
    check('quit while up there: saved on the floor', f[1][1] == ground, (f, ground))


def note():
    print('--- note')
    with open(os.path.join(t.T, 'clawd_pet.pyw'), encoding='utf-8') as f:
        k = [float(v) for v in re.search(r'^NOTE_K = \(([^)]*)\)', f.read(), re.M).group(1).split(',')]
    t.fresh()
    begin()
    m = mark()
    send('combo:note')
    ok = over(m, 'note', 20)
    text = since(m)
    check('note by hand: over', ok and 'combo note over' in text, text.splitlines()[-4:])
    g = re.search(r'(pet\d) play carry_start_(left|right)', text)
    check('one takes out a note', g is not None, plays(text))
    check('and walks with it', re.search(r'pet\d play walk_carry_(left|right)', text) is not None, plays(text))
    gv = re.search(r'(\d\d:\d\d:\d\d)\S* \[\d+\] (pet\d )?play give_(?:mid_|small_)?(left|right)', text)
    rc = re.search(r'(\d\d:\d\d:\d\d)\S* \[\d+\] (pet\d )?play receive_(?:mid_|small_)?(left|right)', text)
    check('one gives, the other takes, facing', gv and rc and gv.group(3) != rc.group(3), plays(text))
    give_line = re.search(r'\[\d+\] (pet\d )?play give_', text)
    recv_line = re.search(r'\[\d+\] (pet\d )?play receive_', text)
    if give_line and recv_line:
        a = int((give_line.group(1) or 'pet0').strip()[3:])
        b = int((recv_line.group(1) or 'pet0').strip()[3:])
        size = {0: 100, 1: 80, 2: 60}
        f = t.feet()
        want = k[b] * size[b] + k[a] * size[a]
        kinds = {0: '', 1: 'mid_', 2: 'small_'}
        check('each plays the clip for its size', ('play give_' + kinds[a]) in text and ('play receive_' + kinds[b]) in text, plays(text))
        check('they stand so that the hands meet', abs(abs(f[a][0] - f[b][0]) - want) <= 2 and f[a][1] == f[b][1], (a, b, f, want))
    stop()

    print('--- note for a sub-agent')
    t.fresh()
    begin()
    m = mark()
    send('think aaaaaaaa')
    time.sleep(0.8)
    send('agent_done aaaaaaaa')
    ok = wait_for(lambda: 'combo note:' in since(m), 3)
    text = since(m)
    who_ = re.search(r'combo note: (.*)', text)
    check('a sub-agent done: a small one brings a note', ok, text.splitlines()[:6])
    check('the big one is not taken off its work', who_ and 'pet0' not in who_.group(1), who_ and who_.group(1))
    time.sleep(1.5)
    send('read aaaaaaaa')                       # work goes on meanwhile
    ok = over(m, 'note', 20)
    text = since(m)
    check('work does not stop the note', ok and 'combo note over' in text, text.splitlines()[-4:])
    check('the big one reads it', re.search(r'\] play receive_', text) is not None, plays(text))
    check('without a nod before it', re.search(r'\] play nod', text.split('play receive_')[0]) is None, plays(text))
    check('and goes back to work', re.search(r'\] play work_read', text.split('play receive_')[-1]) is not None, plays(text)[-6:])
    m = mark()
    send('agent_done aaaaaaaa')
    time.sleep(1.5)
    text = since(m)
    check('another one soon after: only a nod', 'combo note:' not in text and re.search(r'pet\d play nod', text), plays(text))
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()
    t.fresh()
    begin(slots=())
    m = mark()
    send('agent_done')
    time.sleep(1.0)
    check('one pet: no note', 'combo note' not in since(m), since(m).splitlines()[:4])
    stop()


def hops(text):
    return [(p or 'pet0 ').strip() for p in re.findall(r'\] (pet\d )?hop down to', text)]


def leapfrog():
    print('--- leapfrog')
    gap = player_const('LEAP_GAP')
    size = {0: 100, 1: 80, 2: 60}
    t.fresh()
    begin()
    before = t.feet()
    m = mark()
    send('combo:leapfrog')
    ok = over(m, 'leapfrog', 16)
    text = since(m)
    check('leapfrog by hand: over', ok and 'combo leapfrog over' in text, text.splitlines()[-4:])
    check('the two small ones', 'combo leapfrog: pet1, pet2' in text, text.splitlines()[:2])
    check('the bigger one ducks first, then the other', re.findall(r'(pet\d) play leap_crouch', text) == ['pet1', 'pet2'], plays(text))
    check('the smaller one jumps first, then the other', hops(text) == ['pet2', 'pet1'], hops(text))
    duck = re.findall(r'(\d\d:\d\d:\d\d)\S* \[\d+\] pet1 play leap_crouch', text)
    jump = re.findall(r'(\d\d:\d\d:\d\d)\S* \[\d+\] pet2 hop down', text)
    check('it jumps while the other one is down', duck and jump and duck[0] == jump[0] or (duck and jump and abs(int(jump[0][-2:]) - int(duck[0][-2:])) <= 1), (duck, jump))
    f = t.feet()
    d = gap * (size[1] + size[2])
    check('they end side by side, one row', abs(abs(f[1][0] - f[2][0]) - d) <= 2 and f[1][1] == f[2][1], (f, d))
    moved = f[1][0] - before[1][0]
    # the one that ducked first jumps last: it ends in front, the other one a gap behind it
    check('both went the same way, two jumps far', abs(abs(moved) - 2 * d) <= 3 and (f[1][0] - f[2][0]) * moved > 0, (before, f))
    check('the big one stays where it was', f[0] == before[0], (before, f))
    lands = landed(text)
    check('each lands where it was meant to', len(lands) == 2, lands)
    stop()

    print('--- leapfrog: two pets, one at work')
    t.fresh()
    begin(slots=(1,))
    before = t.feet()
    m = mark()
    send('combo:leapfrog')
    ok = over(m, 'leapfrog', 20)
    text = since(m)
    check('two pets: the big one plays too', ok and 'combo leapfrog: pet0, pet1' in text and 'combo leapfrog over' in text, text.splitlines()[:2])
    check('the big one ducks, the small one jumps', re.search(r'\] play leap_crouch', text) and hops(text) == ['pet1', 'pet0'], plays(text))
    time.sleep(0.5)
    check('then the big one walks back to where it stood', t.feet()[0] == before[0], (before, t.feet()))
    m = mark()
    send('read aaaaaaaa')
    time.sleep(0.5)
    send('combo:leapfrog')
    time.sleep(1.0)
    check('the big one at work and only one small: not now', 'combo leapfrog: not now' in since(m), since(m).splitlines()[:4])
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()

    t.fresh()
    begin(args=QUIET[:-2] + ('--return-after', '1-1'))
    before = t.feet()
    m = mark()
    send('read aaaaaaaa')
    time.sleep(0.5)
    send('combo:leapfrog')
    time.sleep(1.0)
    send('edit aaaaaaaa')                    # work goes on: it is not part of it
    ok = over(m, 'leapfrog', 16)
    text = since(m)
    check('at work, by hand: the two small ones play', ok and 'combo leapfrog: pet1, pet2' in text and 'combo leapfrog over' in text, text.splitlines()[-4:])
    check('the big one keeps working', re.search(r'\] play work_edit', text) is not None and re.search(r'\] play leap_crouch', text) is None, plays(text))
    back = wait_for(lambda: t.feet()[1] == before[1] and t.feet()[2] == before[2], 12)
    check('and they walk back at once, though the work goes on', back and 'stop' not in since(m), (before, t.feet()))
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()

    print('--- leapfrog: cut short')
    t.fresh()
    begin()
    m = mark()
    send('combo:leapfrog')
    wait_for(lambda: 'pet2 hop down' in since(m), 8)
    time.sleep(0.45)
    send('size:120')                         # in the air: it lands at once, not up there
    ok = wait_for(lambda: 'combo leapfrog cancelled' in since(m), 4)
    time.sleep(3)
    f = t.feet()
    check('resized in the air: cancelled', ok, since(m).splitlines()[-4:])
    check('and it is on the floor', f[2][1] == f[1][1], f)
    stop()


def play_at_work():
    print('--- the small ones play while the big one works')
    t.fresh()
    begin(args=QUIET[:-2] + ('--return-after', '1-1', '--play-interval', '20-20', '--play-after', '2'))
    before = t.feet()
    m = mark()
    send('listen aaaaaaaa')
    send('read aaaaaaaa')
    ok = wait_for(lambda: re.search(r'combo \w+: pet[12], pet[12]', since(m)) is not None, 30)
    text = since(m)
    name = re.search(r'combo (\w+): pet[12], pet[12]', text)
    check('working a while: the two small ones play', ok, text.splitlines()[:6])
    check('a game meant for it', name and name.group(1) in ('leapfrog', 'high_five', 'note'), name and name.group(1))
    check('without the big one', not re.search(r'combo \w+: pet0', text), text.splitlines()[:6])
    name = name.group(1) if name else 'x'
    ok = over(m, name, 20)
    send('run aaaaaaaa')
    check('work does not stop it', ok and ('combo %s over' % name) in since(m), since(m).splitlines()[-4:])
    ok = wait_for(lambda: t.feet()[1] == before[1] and t.feet()[2] == before[2], 16)
    check('they walk back while the work goes on', ok and 'combo %s:' % name in since(m) and 'stop' not in since(m), (before, t.feet()))
    check('the big one is still at work', re.search(r'\] play work_run', since(m)) is not None, plays(since(m))[-6:])
    m = mark()
    time.sleep(4)
    check('not one game after the other', not re.search(r'combo \w+: pet', since(m)), since(m).splitlines()[:4])
    send('stop aaaaaaaa')
    time.sleep(1.5)
    stop()

    t.fresh()
    begin(slots=(1,), args=QUIET[:-2] + ('--return-after', '1-1', '--play-interval', '3-3', '--play-after', '1'))
    m = mark()
    send('read aaaaaaaa')
    time.sleep(8)
    check('one small one: no game', not re.search(r'combo \w+: pet', since(m)), since(m).splitlines()[:4])
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()


def by_themselves():
    print('--- by themselves')
    begin(args=('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999', '--combo-interval', '3-3', '--peek-after', '3',
                '--show-gap', '2'))             # two in 30 s: the gap between shows kept short
    m = mark()
    ok = wait_for(lambda: since(m).count(' over after') >= 2, 30)
    text = since(m)
    names = re.findall(r'combo (\w+): pet', text)
    check('while idle they do it now and then', ok, names)
    check('only the ones meant for idle time', set(names) <= {'high_five', 'celebrate_all', 'parade', 'comfort', 'stack', 'note', 'leapfrog'}, names)
    stop()                               # no one away from a combo: then no one comes to watch
    begin(args=('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999', '--combo-interval', '9999', '--peek-after', '3'))
    m = mark()
    send('listen aaaaaaaa')
    ok = wait_for(lambda: 'combo peek:' in since(m), 14)
    check('working a while: a small one comes to watch', ok, plays(since(m))[:6])
    check('the big one keeps working', 'combo peek cancelled' not in since(m), since(m).splitlines()[:3])
    time.sleep(5)
    text = since(m)
    check('and not again and again', text.count('combo peek:') <= 2, text.count('combo peek:'))
    send('stop aaaaaaaa')
    time.sleep(2)
    stop()
    with open(t.LOG, encoding='utf-8') as f:
        text = f.read()
    check('no errors in the log', 'ERROR' not in text and 'Traceback' not in text)


if __name__ == '__main__':
    try:
        by_hand()
        asleep()
        wake_by_hand()
        interruptions()
        company()
        three_in_a_row()
        depth()
        parade()
        comfort()
        stack()
        note()
        leapfrog()
        play_at_work()
        by_themselves()
    finally:
        if t.proc is not None and t.proc.poll() is None:
            t.proc.kill()
    print('RESULT: %s' % ('FAILED: %s' % t.fails if t.fails else 'all passed'))
    sys.exit(1 if t.fails else 0)
