# Work clips: seams in the rendered sets, then one isolated test pet driven by hook-like bash writes.
import json, os, re, struct, subprocess, sys, time, zlib

S = os.path.dirname(os.path.abspath(__file__))
T = os.path.dirname(S)
HOME = os.path.join(S, 't', 'work')
EVENT, LOG = os.path.join(HOME, 'event'), os.path.join(HOME, 'pet.log')
fails = []


def check(name, ok, detail=''):
    print('%-4s %s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)
    if not ok:
        fails.append(name)


# ------------------------------------------------------------------ frames
def load(setdir, name):
    data = open(os.path.join(setdir, name + '.frames'), 'rb').read()
    out, off = [], 0
    while off + 4 <= len(data):
        n = struct.unpack_from('<I', data, off)[0]
        out.append(zlib.decompress(data[off + 4:off + 4 + n]))
        off += 4 + n
    return out


def check_seams():
    for s in ('frames', 'frames_hi', 'frames_custom'):
        d = os.path.join(T, s)
        if not os.path.isfile(os.path.join(d, 'manifest.json')):
            continue
        for name in ('work_read', 'work_edit', 'work_run', 'work_compact'):
            fr = load(d, name)
            a = int(len(fr) * 0.2)
            worst = max(max(abs(p - q) for p, q in zip(fr[a + k][::37], fr[a + k + 24][::37])) for k in (0, 3, 7))
            check('%s %s repeats after 24 frames' % (s, name), worst <= 2, 'worst byte difference %d' % worst)
        for name in ('work_read', 'work_edit', 'work_run', 'work_web', 'work_compact', 'work_agent', 'thumbs_up', 'celebrate', 'wave', 'proud', 'look_at_viewer', 'confused', 'shake_head'):
            fr = load(d, name)
            check('%s %s starts and ends alike' % (s, name), fr[0] == fr[-1])


# ------------------------------------------------------------------ pet
def send(*tokens):
    subprocess.run(['D:/git/Git/bin/bash.exe', '-c', ' ; '.join('echo %s >> "%s"' % (t, EVENT.replace('\\', '/')) for t in tokens)], check=True)


def mark():
    return os.path.getsize(LOG)


def plays(since):
    with open(LOG, encoding='utf-8') as f:
        f.seek(since)
        return re.findall(r'\bplay (\w+) \[', f.read())


def wait_for(since, name, secs):
    end = time.time() + secs
    while time.time() < end:
        if name in plays(since):
            return True
        time.sleep(0.05)
    return False


def settle():
    send('stop')
    time.sleep(0.2)
    m = mark()
    end = time.time() + 6
    while time.time() < end:             # wait until the reaction is over and idle is on again
        if 'idle' in plays(m):
            return
        time.sleep(0.05)


def run_pet():
    os.makedirs(HOME, exist_ok=True)
    for n in ('pet.log', 'event'):
        p = os.path.join(HOME, n)
        if os.path.exists(p):
            os.remove(p)
    open(EVENT, 'wb').close()
    with open(os.path.join(HOME, 'state.json'), 'w') as f:
        json.dump({'x': 1280, 'y': 1400, 'scale': 1.0}, f)
    pet = subprocess.Popen([r'C:\Python312\pythonw.exe', os.path.join(T, 'clawd_pet.pyw'), "--grow-quiet", '--home', HOME,
                            '--frames-dir', os.path.join(T, 'frames'), '--debug', '--keep-place',
                            '--extra-interval', '1-1', '--wander-interval', '9999'])
    try:
        time.sleep(1.5)
        scenarios()
        send('quit')
        pet.wait(5)
    finally:
        if pet.poll() is None:
            pet.kill()
    with open(LOG, encoding='utf-8') as f:
        text = f.read()
    check('no errors in the log', 'ERROR' not in text and 'unavailable' not in text)


def scenarios():
    # idle extras: no head tilt any more
    m = mark()
    time.sleep(14)
    extras = plays(m)
    check('idle extras without head_tilt', 'head_tilt' not in extras and len(extras) >= 3, ' '.join(extras))
    send('listen')
    time.sleep(0.3)
    settle()

    # fast tool changes: the first shows its minimum, then only the latest
    send('listen')
    time.sleep(0.8)
    m = mark()
    send('read')
    wait_for(m, 'work_read', 5)          # the listen clip leaves first; until then only the latest counts
    t0 = time.time()
    time.sleep(0.3)
    send('think', 'edit', 'think', 'run', 'think')
    time.sleep(0.2)
    send('web')
    ok = wait_for(m, 'work_web', 6)
    took = time.time() - t0
    seen = plays(m)
    check('only the latest tool is shown', ok and seen == ['work_read', 'work_web'], ' '.join(seen))
    check('first tool shown at least 2.5 s', took >= 2.5, '%.2f s until the next clip' % took)

    # the same tool again: no restart
    m = mark()
    send('think', 'web', 'think', 'web')
    time.sleep(1.5)
    check('same tool again does not restart', plays(m) == [], ' '.join(plays(m)))

    # a hold returns to think after its minimum
    m = mark()
    send('read')
    wait_for(m, 'work_read', 5)
    m = mark()
    send('think')
    check('back to think after the tool', wait_for(m, 'think', 12), ' '.join(plays(m)))

    # failures
    settle()
    send('listen')
    time.sleep(0.5)
    send('run')
    time.sleep(0.6)
    m = mark()
    send('fail')
    check('one failure: surprised', wait_for(m, 'surprised', 4), ' '.join(plays(m)))
    check('after a failure: think', wait_for(m, 'think', 5), ' '.join(plays(m)))
    m = mark()
    send('fail')
    check('second failure: confused', wait_for(m, 'confused', 4), ' '.join(plays(m)))
    settle()

    # compact, in a turn and between turns
    send('listen')
    time.sleep(0.5)
    m = mark()
    send('compact')
    wait_for(m, 'work_compact', 4)
    m = mark()
    send('compact_end')
    check('compact in a turn: back to think', wait_for(m, 'think', 5), ' '.join(plays(m)))
    settle()
    m = mark()
    send('compact')
    wait_for(m, 'work_compact', 4)
    m = mark()
    send('compact_end')
    ok = wait_for(m, 'idle', 6)
    check('compact between turns: back to idle', ok and 'think' not in plays(m), ' '.join(plays(m)))

    # sub-agents: one plane, one nod, the clip of the turn continues
    send('listen')
    time.sleep(0.5)
    m = mark()
    send('agent')
    check('agent: paper plane', wait_for(m, 'work_agent', 4), ' '.join(plays(m)))
    check('after the plane: the turn goes on', wait_for(m, 'listen', 5), ' '.join(plays(m)))
    m = mark()
    send('agent_done')
    check('agent_done: nod', wait_for(m, 'nod', 4), ' '.join(plays(m)))
    time.sleep(0.5)
    m = mark()
    send('stop', 'agent_done')
    check('stop is not replaced by agent_done', wait_for(m, 'hop', 4) and 'nod' not in plays(m), ' '.join(plays(m)))
    wait_for(m, 'idle', 6)

    # the turn-end reaction, every time and whatever was going on
    lost = []
    for i, (tool, wait) in enumerate((('read', 0.0), ('edit', 0.2), ('run', 0.7), ('web', 1.3), ('read', 2.7), ('edit', 3.0))):
        send('listen')
        time.sleep(0.3)
        send(tool)
        time.sleep(wait)
        m = mark()
        send('stop')
        if not wait_for(m, 'hop', 5):
            lost.append(tool)
        wait_for(m, 'idle', 6)
    check('reaction played after all 6 turns', not lost, ' '.join(lost))

    # a tool's clip stays a moment after the tool
    send('listen')
    time.sleep(0.3)
    m = mark()
    send('web')
    wait_for(m, 'work_web', 4)
    send('think')
    t0 = time.time()
    time.sleep(4.5)
    check('the clip stays after the tool', 'think' not in plays(m), ' '.join(plays(m)))
    ok = wait_for(m, 'think', 6)
    check('then think', ok and 5 <= time.time() - t0 <= 9.5, '%.1f s' % (time.time() - t0))
    # meanwhile a tool without a clip of its own ends too (an agent, a search for tools): no longer
    m = mark()
    send('web')
    wait_for(m, 'work_web', 4)
    send('think')
    t0 = time.time()
    time.sleep(3)
    send('think')
    ok = wait_for(m, 'think', 9)
    check('another tool over meanwhile: the clip does not stay longer', ok and 5 <= time.time() - t0 <= 8.5,
          '%.1f s' % (time.time() - t0))
    m = mark()
    send('read')
    wait_for(m, 'work_read', 5)
    send('think')
    time.sleep(1)
    m = mark()
    send('run')
    check('a new tool in that time: at once', wait_for(m, 'work_run', 5), ' '.join(plays(m)))
    send('think')
    time.sleep(0.5)
    m = mark()
    send('stop')
    check('stop in that time: at once', wait_for(m, 'hop', 5) or wait_for(m, 'thumbs_up', 1), ' '.join(plays(m)))
    wait_for(m, 'idle', 8)

    # a sub-agent of the last turn still works when the next message comes: the turn counts from there
    for _ in range(3):
        send('read')
        time.sleep(10)
    send('listen')
    time.sleep(1)
    m = mark()
    send('stop')
    wait_for(m, 'idle', 8)
    with open(LOG, encoding='utf-8') as f:
        f.seek(m)
        took = re.search(r'turn took ([\d.]+)s', f.read())
    check('a new turn during a background agent: counted from the message', took and float(took.group(1)) < 5,
          took and took.group(0))

    # background agent after the turn: busy only for a while
    m = mark()
    send('read')
    t0 = time.time()
    wait_for(m, 'work_read', 4)
    send('think')
    ok = wait_for(m, 'idle', 28)
    check('background tool: idle again after ~20 s', ok and 18 <= time.time() - t0 <= 28, '%.1f s' % (time.time() - t0))

    # two sessions: A's stop must not cut B short, whatever the gap between B's events
    A, B = 'aaaaaaaa', 'bbbbbbbb'
    send('listen ' + A)
    send('listen ' + B)
    time.sleep(0.3)
    send('read ' + A)
    time.sleep(3)
    send('run ' + B)
    time.sleep(3)
    m = mark()
    send('stop ' + A)
    check('A stops: its reaction plays', wait_for(m, 'hop', 4), ' '.join(plays(m)))
    check('then back to what B is doing', wait_for(m, 'work_run', 6), ' '.join(plays(m)))
    m = mark()
    time.sleep(25)
    check('B silent for 25 s: still working', 'idle' not in plays(m), ' '.join(plays(m)))
    m = mark()
    send('stop ' + B)
    check('B stops: its long turn gets a thumb, then idle', wait_for(m, 'thumbs_up', 4) and wait_for(m, 'idle', 8), ' '.join(plays(m)))

    # a background agent of a finished session still gets only the short grace
    m = mark()
    send('read ' + A)
    t0 = time.time()
    wait_for(m, 'work_read', 4)
    ok = wait_for(m, 'idle', 28)
    check('background tool with a session: idle after ~20 s', ok and 18 <= time.time() - t0 <= 28, '%.1f s' % (time.time() - t0))

    # compact of one session does not end the other
    send('listen ' + A)
    send('listen ' + B)
    time.sleep(0.3)
    send('edit ' + B)
    time.sleep(3)
    m = mark()
    send('compact ' + A)
    check('compact shows while B works', wait_for(m, 'work_compact', 5), ' '.join(plays(m)))
    send('compact_end ' + A)
    send('stop ' + A)
    check('after A is done: B again', wait_for(m, 'work_edit', 8), ' '.join(plays(m)))
    send('stop ' + B)
    time.sleep(0.2)

    # a question of A is not answered by B's work, only by A
    m = mark()
    wait_for(m, 'idle', 6)
    send('listen ' + B)
    send('attention ' + A)
    time.sleep(1)
    m = mark()
    send('read ' + B)
    time.sleep(4)
    check('B works while A asks: the question stays', 'work_read' not in plays(m), ' '.join(plays(m)))
    send('think ' + A)
    check('A goes on: the question is gone', wait_for(m, 'think', 6) or wait_for(m, 'work_read', 1), ' '.join(plays(m)))
    send('stop ' + A)
    send('stop ' + B)
    time.sleep(0.2)
    m = mark()
    wait_for(m, 'idle', 6)

    # a malformed session counts as no session
    send('run zzzzzzzz')
    m = mark()
    wait_for(m, 'work_run', 4)
    send('stop')
    check('malformed session: a plain stop ends it', wait_for(m, 'idle', 8), ' '.join(plays(m)))

    # the menu way (by name) still plays them, for 3 s
    for name in ('work_read', 'work_web'):
        m = mark()
        send(name)
        check('by name: %s' % name, wait_for(m, name, 3) and wait_for(m, 'idle', 7), ' '.join(plays(m)))
    m = mark()
    send('work_agent')
    check('by name: work_agent', wait_for(m, 'work_agent', 3), ' '.join(plays(m)))


if __name__ == '__main__':
    check_seams()
    run_pet()
    print('FAILED: %s' % fails if fails else 'all ok')
    sys.exit(1 if fails else 0)
