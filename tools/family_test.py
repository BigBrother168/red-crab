# Drives the family: number of pets, shared size and its limits, reactions, sleep, walking, restart.
import ctypes, json, os, re, shutil, subprocess, sys, time
from ctypes import wintypes as w

S = os.path.dirname(os.path.abspath(__file__))
T = os.path.dirname(S)
HOME = os.path.join(S, 't', 'family')
EVENT = os.path.join(HOME, 'event')
LOG = os.path.join(HOME, 'pet.log')
STATE = os.path.join(HOME, 'state.json')
u = ctypes.WinDLL('user32', use_last_error=True)
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
WM_LDOWN, WM_LUP, WM_MOVE = 0x201, 0x202, 0x200
fails = []
proc = None


def check(name, ok, detail=''):
    print('%-4s %s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)
    if not ok:
        fails.append(name)


def start(*args, keep_place=True):
    """keep_place: start where state.json says (as the tests set it up); else in the corner, as a user's start."""
    global proc
    proc = subprocess.Popen([r'C:\Python312\pythonw.exe', os.path.join(T, 'clawd_pet.pyw'), "--grow-quiet", '--home', HOME,
                             '--frames-dir', os.path.join(T, 'frames'), '--debug']
                            + (['--keep-place'] if keep_place else []) + list(args)
                            + ([] if '--combo-interval' in args else ['--combo-interval', '9999'])
                            + ([] if '--play-interval' in args else ['--play-interval', '9999'])
                            + ([] if '--mimic-interval' in args else ['--mimic-interval', '9999'])
                            + ([] if '--peek-after' in args else ['--peek-after', '9999']))
    end = time.time() + 8
    while time.time() < end and not windows():
        time.sleep(0.05)
    time.sleep(0.8)


def stop():
    send('quit')
    code = proc.wait(8)
    check('clean exit', code == 0, code)
    time.sleep(1.0)


def send(tok):
    subprocess.run(['D:/git/Git/bin/bash.exe', '-c', 'echo %s >> "%s"' % (tok, EVENT.replace('\\', '/'))], check=True)


def windows(board=False):
    """The pets' visible windows; board=True: the sign's board instead (its window is called ClawdSign)."""
    found = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def f(h, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == proc.pid and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(32)
            u.GetWindowTextW(h, buf, 32)
            if buf.value != 'ClawdTalks' and (buf.value == 'ClawdSign') == board:   # not the conversations' circles
                found.append(h)
        return True
    u.EnumWindows(cb(f), 0)
    return found


def rect(h):
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def state():
    for _ in range(40):
        try:
            with open(STATE, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            time.sleep(0.05)
    return {}


def log_text():
    with open(LOG, encoding='utf-8') as f:
        return f.read()


def mark():
    return os.path.getsize(LOG)


def since(m):
    with open(LOG, encoding='utf-8') as f:
        f.seek(m)
        return f.read()


def wait_for(fn, secs):
    end = time.time() + secs
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return fn()


def count_is(n, secs=3):
    return wait_for(lambda: len(windows()) == n, secs)


def lp(x, y):
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def drag(h, dx, dy):
    l, t, r, b = rect(h)
    cx, cy = (r - l) // 2, (b - t) * 2 // 3
    u.PostMessageW(h, WM_LDOWN, 1, lp(cx, cy))
    time.sleep(0.05)
    for i in range(1, 7):
        wl, wt, _, _ = rect(h)
        u.PostMessageW(h, WM_MOVE, 1, lp(l + cx + dx * i // 6 - wl, t + cy + dy * i // 6 - wt))
        time.sleep(0.04)
    time.sleep(0.15)                       # a hand that puts it down stops first (else it is a throw)
    wl, wt, _, _ = rect(h)
    u.PostMessageW(h, WM_LUP, 0, lp(l + cx + dx - wl, t + cy + dy - wt))
    time.sleep(0.4)


def feet():
    d = state()
    out = {0: (d['x'], d['y'])}
    for k, v in d.get('pos', {}).items():
        if int(k) in d.get('slots', []):
            out[int(k)] = tuple(v[:2])
    return out


def fresh():
    shutil.rmtree(HOME, ignore_errors=True)
    os.makedirs(HOME)
    open(EVENT, 'wb').close()


def test_members():
    print('--- number of pets, size')
    fresh()
    with open(STATE, 'w') as f:
        json.dump({'x': 1800, 'y': 1000, 'scale': 1.0}, f)       # the file of the version before
    start('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999')
    check('old state: one pet', len(windows()) == 1, len(windows()))

    send('family:3')
    check('family:3 gives three windows', count_is(3))
    time.sleep(0.5)
    d = state()
    check('state lists two others', d.get('slots') == [1, 2], d)
    f = feet()
    check('they stand left of the big one, apart', f[1][0] < f[0][0] - 80 and f[2][0] < f[1][0] - 60, f)
    check('feet on one row', abs(f[1][1] - f[0][1]) <= 4 and abs(f[2][1] - f[0][1]) <= 4, f)
    text = log_text()
    check('new ones greet', 'pet1 play hop' in text and 'pet2 play hop' in text)

    send('family:3')
    time.sleep(0.5)
    check('same number again: nothing changes', len(windows()) == 3)

    send('size:50')
    wait_for(lambda: state().get('scale') == 0.834, 3)
    d = state()
    check('three: size 50 stops at 84%', d.get('scale') == 0.834 and d.get('wanted') == 0.5, d)
    send('family:1')
    check('back to one', count_is(1))
    wait_for(lambda: state().get('scale') == 0.5, 3)
    check('one: the size asked for is back', state().get('scale') == 0.5, state())
    send('family:2')
    check('two', count_is(2))
    wait_for(lambda: state().get('scale') == 0.625, 3)
    check('two: stops at 63%', state().get('scale') == 0.625, state())
    send('family:3')
    check('three again', count_is(3))
    wait_for(lambda: state().get('scale') == 0.834, 3)
    check('three again: 84%', state().get('scale') == 0.834, state())

    send('size:200')
    wait_for(lambda: state().get('scale') == 2.0, 3)
    time.sleep(0.6)
    hs = sorted(windows(), key=lambda h: rect(h)[2] - rect(h)[0], reverse=True)
    ws = [rect(h)[2] - rect(h)[0] for h in hs]
    check('size 200: sizes keep the ratios', abs(ws[1] / ws[0] - 0.8) < 0.04 and abs(ws[2] / ws[0] - 0.6) < 0.04, ws)
    f = feet()
    check('size 200: still apart', f[1][0] < f[0][0] - 200 and f[2][0] < f[1][0] - 150, f)
    send('size:100')
    wait_for(lambda: state().get('scale') == 1.0, 3)

    print('--- one at a time, each its own set')
    m = mark()
    send('size:120')
    ok = wait_for(lambda: since(m).count('re-render') >= 6 and since(m).count('finished after') >= 3, 90)
    text = since(m)
    order = re.findall(r're-render (\d+)px (started|finished)', text)
    overlap = any(a[1] == 'started' and b[1] == 'started' for a, b in zip(order, order[1:]))
    check('three renders, one at a time', ok and len(order) >= 6 and not overlap, order)
    sets = [os.path.isfile(os.path.join(HOME, n, 'manifest.json')) for n in ('frames_custom', 'frames_custom_1', 'frames_custom_2')]
    check('each has its own set', all(sets), sets)
    px = sorted(json.load(open(os.path.join(HOME, n, 'manifest.json'), encoding='utf-8')).get('base_body_px', 0)
                for n in ('frames_custom', 'frames_custom_1', 'frames_custom_2'))
    check('of the right sizes', px == [72, 96, 120], px)

    print('--- each on its own')
    time.sleep(1)
    hs = sorted(windows(), key=lambda h: rect(h)[2] - rect(h)[0])
    before = feet()
    drag(hs[0], -120, -200)
    after = feet()
    check('dragging the small one moves only it',
          after[2][0] < before[2][0] - 80 and after[2][1] < before[2][1] - 150 and after[0] == before[0] and after[1] == before[1],
          (before, after))

    print('--- leaving and coming back')
    send('dismiss:1')
    check('the 80% one leaves', count_is(2))
    time.sleep(0.5)
    check('state shows only the 60% one', state().get('slots') == [2], state())
    send('dismiss:0')
    time.sleep(0.5)
    check('the big one cannot leave alone', len(windows()) == 2)
    stop()

    start('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999')
    check('restart: same pets', len(windows()) == 2, len(windows()))
    check('restart: same places', feet()[2] == after[2], (feet(), after))
    check('restart does not greet', 'pet2 play hop' not in log_text()[log_text().rfind('start v2'):])
    send('family:3')
    check('all three again', count_is(3))
    stop()


def who(text, clip):
    return sorted(set(re.findall(r'(pet\d) play %s\b' % clip, text)))


def plays(text):
    return re.findall(r'(\S* ?play \w+)', text)


def react(tok, clip, n, secs=2.5):
    """Send tok; exactly n of the small ones show clip."""
    m = mark()
    send(tok)
    wait_for(lambda: len(who(since(m), clip)) >= n, secs)
    time.sleep(0.7)
    return len(who(since(m), clip)) == n, plays(since(m))


def test_reactions():
    print('--- reactions')
    d = state()                          # side by side, as they start: comfort and notes come only from near by
    d.pop('homes', None)
    d.update(x=1800, y=1000, scale=1.0, wanted=1.0, slots=[1, 2], pos={'1': [1690, 1000], '2': [1600, 1000]})
    with open(STATE, 'w') as f:
        json.dump(d, f)
    start('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999')
    check('three from the saved state', len(windows()) == 3, len(windows()))
    ok, seen = react('listen aaaaaaaa', 'look_at_viewer', 1)
    check('you write: one looks at you', ok, seen)
    m = mark()
    send('read aaaaaaaa')
    send('run aaaaaaaa')
    send('edit aaaaaaaa')
    send('web aaaaaaaa')
    send('think aaaaaaaa')
    time.sleep(3.5)
    text = since(m)
    # one may still be going back to idle after looking at you
    # (the smallest one holds up the sign: that is not a reaction)
    check('tool events are only for the big one', not re.search(r'pet\d play (?!idle\b|sign_)', text), plays(text))
    ok, seen = react('stop aaaaaaaa', 'hop', 1)
    check('a short turn: one hops', ok, seen)
    time.sleep(3.2)
    send('listen aaaaaaaa')
    time.sleep(21)
    ok, seen = react('stop aaaaaaaa', 'hop', 1)
    check('a turn of 20 s: one hops, the other holds up the sign', ok and any('play sign_' in s for s in seen), seen)
    time.sleep(3.2)
    send('listen aaaaaaaa')
    time.sleep(121)
    ok, seen = react('stop aaaaaaaa', 'celebrate', 2, secs=4)    # they run to the big one first
    check('a turn of 2 min: both celebrate', ok, seen)
    time.sleep(4)
    send('listen aaaaaaaa')
    time.sleep(3.2)
    ok, seen = react('fail aaaaaaaa', 'surprised', 1)
    check('first failure: one is startled', ok, seen)
    time.sleep(3.2)
    ok, seen = react('fail aaaaaaaa', 'comfort_(?:left|right)', 2, secs=6)      # they walk to the big one first
    check('failing again: both come to comfort', ok, seen)
    time.sleep(0.5)
    ok, seen = react('fail aaaaaaaa', 'surprised', 0, secs=1.0)
    check('a burst does not keep them jumping', ok, seen)
    time.sleep(5)
    ok, seen = react('agent aaaaaaaa', 'tiptoe_peek', 1)
    check('sub-agent: one peeks', ok, seen)
    time.sleep(3)
    m = mark()
    send('agent_done aaaaaaaa')
    ok = wait_for(lambda: 'combo note over' in since(m), 12)
    check('sub-agent done: a small one brings the note', ok and re.search(r'pet\d play give_', since(m)), plays(since(m)))
    time.sleep(1)
    ok, seen = react('attention aaaaaaaa', 'wave', 1)
    check('a question: one waves', ok, seen)
    send('listen aaaaaaaa')
    time.sleep(3.2)
    ok, seen = react('stopfail aaaaaaaa', 'comfort_(?:left|right)', 2, secs=6)
    check('the turn failed: both come to comfort', ok, seen)
    time.sleep(5)
    ok, seen = react('hello bbbbbbbb', 'wave', 2)
    check('session start: both wave', ok, seen)
    time.sleep(3)
    ok, seen = react('bye bbbbbbbb', 'wave', 2)
    check('session end: both wave', ok, seen)
    time.sleep(3)
    stop()


def test_sleep():
    print('--- sleep')
    d = state()
    d.pop('homes', None)                 # left by the note before: a walk back would keep one awake
    with open(STATE, 'w') as f:
        json.dump(d, f)
    start('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '6')
    m = mark()
    ok = wait_for(lambda: since(m).count('fell asleep') >= 3, 12)
    check('all three fall asleep', ok, since(m).count('fell asleep'))
    m = mark()
    send('listen aaaaaaaa')
    ok = wait_for(lambda: since(m).count('woke up') >= 3, 4)
    check('an event wakes all three', ok, since(m).count('woke up'))
    text = since(m)
    time.sleep(8)
    text = since(m)
    check('the others stay awake while the big one works', text.count('fell asleep') == 0, text.count('fell asleep'))
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()


def closest(secs):
    hs = windows()
    worst = 1e9
    end = time.time() + secs
    while time.time() < end:
        xs = sorted((r[0] + r[2]) / 2 for r in map(rect, hs))
        worst = min(worst, xs[1] - xs[0], xs[2] - xs[1])
        time.sleep(0.05)
    return worst


def test_walking():
    print('--- walking, not into each other')
    d = state()
    d.pop('homes', None)                 # left by the reactions before: a walk back may pass right through another one
    d.update(x=1500, y=1000, scale=1.0, wanted=1.0, pos={'1': [1340, 1000], '2': [1220, 1000]})
    with open(STATE, 'w') as f:
        json.dump(d, f)
    start('--extra-interval', '999', '--wander-interval', '1-2', '--sleep-after', '9999')
    worst = closest(40)
    text = log_text()[log_text().rfind('start v2'):]
    walks = len(re.findall(r'play walk_', text))
    check('they walk', walks >= 6, walks)
    check('with room between them', worst >= 78, 'closest centres %.0f px' % worst)

    send('listen aaaaaaaa')
    time.sleep(6)                        # a walk under way may finish
    m = mark()
    time.sleep(8)
    text = since(m)
    check('while the big one works the others do not walk', 'pet1 play walk' not in text and 'pet2 play walk' not in text, plays(text))
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()

    d = state()
    d.update(x=1500, y=1000, scale=1.0, wanted=1.0, pos={'1': [1450, 1000], '2': [1200, 1000]})
    with open(STATE, 'w') as f:
        json.dump(d, f)
    start('--extra-interval', '999', '--wander-interval', '1-2', '--sleep-after', '9999')
    worst = closest(25)
    check('too close: they only walk apart', worst >= 48, 'closest centres %.0f px' % worst)
    stop()
    check('no errors in the log', 'ERROR' not in log_text() and 'Traceback' not in log_text())


def test_cli():
    print('--- commands')
    sys.path.insert(0, T)
    import clawd, io, contextlib
    fresh()
    calls = []
    clawd.HOME, clawd.STATE_FILE, clawd.EVENT_FILE = HOME, STATE, EVENT
    clawd.cmd_on = lambda quiet=False: calls.append('on') or 0
    clawd.is_running = lambda: False
    with open(STATE, 'w') as f:
        json.dump({'x': 7, 'y': 8, 'scale': 1.5}, f)
    code = clawd.main(['3'])
    d = state()
    check('not running: clawd 3 remembers and starts', code == 0 and calls == ['on'] and d.get('slots') == [1, 2] and d.get('x') == 7, d)
    clawd.is_running = lambda: True
    calls.clear()
    code = clawd.main(['2'])
    check('running: clawd 2 tells the pet', code == 0 and not calls and open(EVENT).read().split()[-1] == 'family:2', open(EVENT).read())
    code = clawd.main(['4'])
    check('clawd 4 is refused', code == 2, code)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        clawd.main(['size', '60'])
    check('clawd size under the limit says so', '84%' in out.getvalue(), out.getvalue())


def centres():
    """slot -> centre x of its window (the biggest window is the big one)."""
    hs = sorted(windows(), key=lambda h: rect(h)[2] - rect(h)[0], reverse=True)
    return {i: (rect(h)[0] + rect(h)[2]) / 2 for i, h in enumerate(hs)}


def drift(secs):
    """The farthest each one gets from where it is now, in that time."""
    ref, worst = centres(), {}
    end = time.time() + secs
    while time.time() < end:
        for k, c in centres().items():
            worst[k] = max(worst.get(k, 0), abs(c - ref[k]))
        time.sleep(0.1)
    return worst


def test_sign():
    print('--- the sign: the smallest one holds it up, the board on top; words for the big one at work')
    d = state()
    d.pop('homes', None)
    d.update(x=1800, y=1000, scale=1.0, wanted=1.0, slots=[1, 2], pos={'1': [1690, 1000], '2': [1600, 1000]}, lang='zh')
    with open(STATE, 'w') as f:
        json.dump(d, f)
    start('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999')
    m = mark()
    send('listen aaaaaaaa')
    time.sleep(0.3)
    send('read aaaaaaaa')
    ok = wait_for(lambda: 'sign up: 在读文件 (pet2)' in since(m), 3)
    check('a tool: the smallest one holds up a sign', ok, [l for l in since(m).splitlines() if 'sign' in l])
    check('its board shows once the stick is up', wait_for(lambda: len(windows(board=True)) == 1, 3), len(windows(board=True)))
    check('the board is not one of the pets', len(windows()) == 3, len(windows()))
    m = mark()
    send('think aaaaaaaa')
    send('read aaaaaaaa')
    time.sleep(0.6)
    check('the same tool again: no new sign', 'sign ' not in since(m), since(m).splitlines()[-3:])
    send('edit aaaaaaaa')
    ok = wait_for(lambda: 'sign now: 在改代码' in since(m), 2)
    check('another tool while it is up: new words, the stick stays up', ok and 'sign down' not in since(m),
          [l for l in since(m).splitlines() if 'sign' in l])
    ok = wait_for(lambda: 'sign down (time)' in since(m), 6)
    check('down after a few seconds', ok)
    check('and the board goes', wait_for(lambda: not windows(board=True), 2))
    m = mark()
    send('run aaaaaaaa')
    time.sleep(1.5)
    check('a tool just after: not up again at once', 'sign up' not in since(m), since(m).splitlines()[-3:])

    time.sleep(3)
    m = mark()
    send('stop aaaaaaaa')
    ok = wait_for(lambda: 'sign up: 做完了！用了' in since(m), 2)
    time.sleep(2)
    text = since(m)
    check('the end of a turn: a sign that says how long it took', ok, [l for l in text.splitlines() if 'sign' in l])
    g = re.search(r'sign up: 做完了！用了 .* \((pet\d)\)', text)     # the smallest free one: the other while one re-renders
    holder = g.group(1) if g else 'pet2'
    other = 'pet1' if holder == 'pet2' else 'pet2'
    check('the one with the sign does not hop, another does', (holder + ' play hop') not in text and (other + ' play hop') in text,
          (holder, plays(text)))
    time.sleep(4)
    m = mark()
    send('attention aaaaaaaa')
    time.sleep(6)
    text = since(m)
    check('a question: the sign stays up while it waits', 'sign up: 等你回复' in text and 'sign down' not in text
          and len(windows(board=True)) == 1, [l for l in text.splitlines() if 'sign' in l])
    send('lang:en')
    check('the language switched while it is up: the words follow', wait_for(lambda: 'sign now: Your turn' in since(m), 2),
          [l for l in since(m).splitlines() if 'sign' in l])
    send('listen aaaaaaaa')
    check('answered: down', wait_for(lambda: 'sign down (answered)' in since(m), 2), [l for l in since(m).splitlines() if 'sign' in l])
    send('lang:zh')
    time.sleep(1.5)

    m = mark()
    send('stop aaaaaaaa')
    wait_for(lambda: 'sign up: 做完了' in since(m), 2)
    time.sleep(1)
    send('listen aaaaaaaa')
    time.sleep(0.3)
    send('web aaaaaaaa')
    ok = wait_for(lambda: 'sign down (a new message)' in since(m) and 'sign up: 在查资料' in since(m), 3)
    check('you write again: the old "done" comes down, the new turn\'s first tool gets its sign', ok,
          [l for l in since(m).splitlines() if 'sign' in l])
    wait_for(lambda: 'sign down (time)' in since(m), 6)
    time.sleep(4.5)

    m = mark()
    send('stop aaaaaaaa')
    wait_for(lambda: len(windows(board=True)) == 1, 3)
    hs = sorted(windows(), key=lambda h: rect(h)[2] - rect(h)[0])
    drag(hs[0], -160, 0)                           # the user takes the one with the sign
    ok = wait_for(lambda: 'sign down (holder taken)' in since(m), 2)
    check('the one with the sign dragged: it comes down', ok and wait_for(lambda: not windows(board=True), 2),
          [l for l in since(m).splitlines() if 'sign' in l])
    time.sleep(4.5)
    m = mark()
    send('stopfail aaaaaaaa')
    ok = wait_for(lambda: 'sign up: 出错停下了 (over the big one)' in since(m), 2)
    check('a turn failed: the board over the big one, the others free to come and comfort', ok,
          [l for l in since(m).splitlines() if 'sign' in l])
    time.sleep(4.5)
    m = mark()
    send('listen aaaaaaaa')
    time.sleep(5)
    check('a short thought: no sign', 'sign up' not in since(m), [l for l in since(m).splitlines() if 'sign' in l])
    ok = wait_for(lambda: 'sign up: 在想…' in since(m), 6)
    check('a long thought with no tool: "thinking..."', ok, [l for l in since(m).splitlines() if 'sign' in l])
    send('read aaaaaaaa')
    ok = wait_for(lambda: 'sign now: 在读文件' in since(m), 2)
    check('then a tool: its words on the same sign', ok, [l for l in since(m).splitlines() if 'sign' in l])
    send('stop aaaaaaaa')
    time.sleep(1)
    stop()

    d = state()
    d['slots'] = []
    with open(STATE, 'w') as f:
        json.dump(d, f)
    start('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999')
    m = mark()
    send('read bbbbbbbb')
    ok = wait_for(lambda: 'sign up: 在读文件 (over the big one)' in since(m), 2)
    check('one pet: the board over its head', ok and wait_for(lambda: len(windows(board=True)) == 1, 2),
          [l for l in since(m).splitlines() if 'sign' in l])
    send('lang:en')
    time.sleep(4.5)
    m = mark()
    send('stop bbbbbbbb')
    check('in English', wait_for(lambda: 'sign up: Done!' in since(m), 2), [l for l in since(m).splitlines() if 'sign' in l])
    send('lang:zh')
    time.sleep(1)
    stop()
    check('no errors in the log', 'ERROR' not in log_text() and 'Traceback' not in log_text())


def test_place():
    print('--- a start is in the corner; walks of their own stay near; far apart, no combo of their own')
    fresh()
    with open(STATE, 'w') as f:
        json.dump({'x': 700, 'y': 900, 'scale': 1.0, 'wanted': 1.0, 'slots': [1, 2],
                   'pos': {'1': [500, 900], '2': [300, 900]}, 'homes': {'2': [200, 900]}}, f)
    start('--extra-interval', '999', '--wander-interval', '1-2', '--sleep-after', '9999', keep_place=False)
    f = feet()
    check('started in the corner, not where it was', f[0][0] > 2300 and f[0][1] == 1504, f)
    check('the others beside it on its row, right to left', f[0][0] > f[1][0] > f[2][0] and f[1][1] == f[2][1] == 1504, f)
    reach = {0: 120, 1: 96, 2: 72}                 # WANDER_AREA of 100, 80, 60 px
    worst = drift(40)
    text = log_text()[log_text().rfind('start v2'):]
    check('they walk', len(re.findall(r'play walk_', text)) >= 6, len(re.findall(r'play walk_', text)))
    check('but no farther than their places allow', all(worst[k] <= reach[k] + 6 for k in reach), worst)

    big = sorted(windows(), key=lambda h: rect(h)[2] - rect(h)[0])[-1]
    drag(big, -900, -300)                          # the user puts the big one somewhere else
    time.sleep(1.5)
    worst = drift(30)
    c = centres()
    check('dragged: it lives there now', worst[0] <= reach[0] + 6 and c[0] < 1900, (worst, c))   # from about 2420
    stop()

    d = state()
    d.pop('homes', None)
    d.update(x=2300, y=1000, scale=1.0, wanted=1.0, pos={'1': [2160, 1000], '2': [500, 1000]})
    with open(STATE, 'w') as f:
        json.dump(d, f)
    start('--extra-interval', '999', '--wander-interval', '9999', '--sleep-after', '9999', '--combo-interval', '1-2')
    m = mark()
    time.sleep(25)
    text = since(m)
    combos = re.findall(r'combo \w+: (pet.*)', text)
    check('combos of their own only with the one near', combos and all('pet2' not in c for c in combos), combos)
    check('the far one is not called over', abs(feet()[2][0] - 500) <= 80, feet()[2])
    m = mark()
    send('combo:celebrate_all')                    # by hand: they come from anywhere
    time.sleep(4)
    text = since(m)
    check('by hand: the far one comes too', re.search(r'combo celebrate_all: .*pet2', text) is not None, plays(text))
    stop()
    check('no errors in the log', 'ERROR' not in log_text() and 'Traceback' not in log_text())


if __name__ == '__main__':
    try:
        test_cli()
        test_members()
        test_reactions()
        test_sleep()
        test_walking()
        test_place()
        test_sign()
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
    print('RESULT: %s' % ('FAILED: %s' % fails if fails else 'all passed'))
    sys.exit(1 if fails else 0)
