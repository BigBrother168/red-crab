"""The connect window (clawd_connect.pyw) and clawd connect / uninstall / hooks refresh, on agents' folders of its own:
USERPROFILE points at a temporary folder (~/.claude, ~/.codex, ~/.dsh, ~/.gemini are made there), so no real setting
is ever read or written.  1: three agents found, one not: the three ticked and connected, the fourth greyed; a hook of
the user's own and the rest of each file stay, each file backed up.  2: again: nothing to change.  3: two unticked:
those disconnected.  4: another copy's paths -> hooks refresh writes them again.  5: uninstall: none left, the save
stays.  6: no agent at all: the window says so and has only Close."""
import glob, json, os, shutil, subprocess, sys, tempfile

T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
fails = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '  %r' % (detail,)))
    if not ok:
        fails.append(name)


tmp = tempfile.mkdtemp(prefix='clawd_connect_')
USER = os.path.join(tmp, 'user')
HOME = os.path.join(tmp, 'home')
ENV = {k: v for k, v in os.environ.items() if k not in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'DSH_HOME')}
ENV.update(USERPROFILE=USER, HOME=USER, CLAWD_HOME=HOME, APPDATA=os.path.join(tmp, 'Roaming'))


def p(*a):
    return os.path.join(USER, *a)


def window(out, *extra):
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([PYW, os.path.join(T, 'clawd_connect.pyw'), '--home', HOME, '--selftest', out] + list(extra),
                   env=ENV, timeout=60)
    try:
        return json.load(open(out, encoding='utf-8'))
    except Exception as e:
        return {'error': repr(e)}


def cli(*args):
    r = subprocess.run([sys.executable, os.path.join(T, 'clawd.py')] + list(args), env=ENV, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=60)
    return r.returncode, r.stdout


def states():
    code, out = cli('hooks', 'status')
    return out


try:
    os.makedirs(HOME)
    json.dump({'lang': 'zh'}, open(os.path.join(HOME, 'state.json'), 'w'))
    os.makedirs(p('.claude'))
    mine = {'type': 'command', 'command': 'echo mine'}
    json.dump({'model': 'x', 'hooks': {'Stop': [{'hooks': [mine]}]}}, open(p('.claude', 'settings.json'), 'w'))
    os.makedirs(p('.codex'))
    os.makedirs(p('.dsh', 'profiles', 'desktop'))
    open(p('.dsh', 'profiles', 'desktop', 'cordis.patch.yml'), 'w').write('- something: of its own\n')
    # Antigravity never ran here: no ~/.gemini/antigravity

    # 1
    o = window(os.path.join(tmp, 'o1.json'))
    check('1 no error', 'error' not in o, o.get('error'))
    check('1 first start: the found ones ticked, "will connect" beside them, Apply on',
          [o.get('before', {}).get(a) for a in ('claude', 'codex', 'deepseek', 'antigravity')] == ['→ 将连接'] * 3 + ['']
          and o.get('apply_grey_before') is False, (o.get('before'), o.get('apply_grey_before')))
    check('1 after Apply: nothing left to do, Apply grey', o.get('apply_grey') is True
          and not any(o.get(a, {}).get('todo') for a in ('claude', 'codex', 'deepseek')), o.get('apply_grey'))
    check('1 three found and connected', all(o.get(a, {}).get('state') == 'on' for a in ('claude', 'codex', 'deepseek')),
          {a: o.get(a, {}).get('state') for a in ('claude', 'codex', 'deepseek', 'antigravity')})
    check('1 Antigravity greyed, not touched', o.get('antigravity', {}).get('usable') is False
          and not os.path.exists(p('.gemini', 'config', 'hooks.json')), o.get('antigravity'))
    check('1 what is left to do: Codex trust, DeepSeek restart',
          '信任' in o.get('codex', {}).get('more', '') and '重启' in o.get('deepseek', {}).get('more', ''),
          (o.get('codex', {}).get('more'), o.get('deepseek', {}).get('more')))
    s = json.load(open(p('.claude', 'settings.json'), encoding='utf-8'))
    check('1 the user\'s own hook and setting stay', s.get('model') == 'x' and mine in [h for g in s['hooks']['Stop'] for h in g['hooks']], s.get('hooks', {}).get('Stop'))
    check('1 backed up first (the files that were there)', os.path.isfile(p('.claude', 'settings.json.clawd-bak'))
          and os.path.isfile(p('.dsh', 'profiles', 'desktop', 'cordis.patch.yml.clawd-bak'))
          and json.load(open(p('.claude', 'settings.json.clawd-bak'), encoding='utf-8')).get('model') == 'x')
    y = open(p('.dsh', 'profiles', 'desktop', 'cordis.patch.yml'), encoding='utf-8').read()
    check('1 DeepSeek: its own lines stay, ours added', y.startswith('- something: of its own') and 'clawd_dsh.mjs' in y, y)
    # 2
    o = window(os.path.join(tmp, 'o2.json'))
    check('2 again: nothing to change, Apply grey', all(o.get(a, {}).get('result') is None for a in ('claude', 'codex', 'deepseek'))
          and o.get('apply_grey_before') is True, {a: o.get(a, {}).get('result') for a in ('claude', 'codex', 'deepseek')})
    # 3
    os.makedirs(p('.gemini', 'antigravity'))
    o = window(os.path.join(tmp, 'o3a.json'))
    check('3 found later, some already connected: not ticked by itself', o.get('before', {}).get('antigravity') == ''
          and o.get('antigravity', {}).get('state') == 'off' and o.get('antigravity', {}).get('note') == '未连接', o.get('antigravity'))
    o = window(os.path.join(tmp, 'o3.json'), '--check', 'antigravity', '--uncheck', 'codex,deepseek')
    check('3 "will disconnect" beside the unticked, "will connect" beside the ticked',
          o.get('before', {}).get('codex') == '→ 将断开' and o.get('before', {}).get('antigravity') == '→ 将连接',
          o.get('before'))
    check('3 ticked by hand: connected', o.get('antigravity', {}).get('state') == 'on', o.get('antigravity'))
    check('3 unticked: disconnected', o.get('codex', {}).get('state') == 'off' and o.get('deepseek', {}).get('state') == 'off',
          (o.get('codex'), o.get('deepseek')))
    check('3 Claude Code stays connected', o.get('claude', {}).get('state') == 'on', o.get('claude'))
    # 4
    s = json.load(open(p('.claude', 'settings.json'), encoding='utf-8'))
    raw = json.dumps(s).replace(T.replace('\\', '/'), 'D:/elsewhere')
    open(p('.claude', 'settings.json'), 'w', encoding='utf-8').write(raw)
    out = states()
    code, said = cli('hooks', 'refresh')
    s2 = open(p('.claude', 'settings.json'), encoding='utf-8').read()
    check('4 another copy\'s paths: refresh writes them for this one', 'D:/elsewhere' not in s2 and T.replace('\\', '/') in s2, said)
    code, said = cli('hooks', 'refresh')
    check('4 then nothing to change', '不用改' in said or 'nothing to change' in said, said)
    # 5
    for k in range(5):                         # dated backups of the old kind, and a file of the user's that only looks alike
        open(p('.claude', 'settings.json.bak-2026010%d-120000' % (k + 1)), 'w').write('{}')
    open(p('.claude', 'settings.json.bak-mine'), 'w').write('{}')
    code, said = cli('uninstall')
    baks = sorted(n for n in os.listdir(p('.claude')) if n.startswith('settings.json.') and n != 'settings.json.bak-mine')
    check('5 uninstall: no backup of ours left (the one kept, the old dated ones); the user\'s look-alike stays', baks == []
          and os.path.isfile(p('.claude', 'settings.json.bak-mine'))
          and not any(n.endswith('.clawd-bak') for d in ('.codex', os.path.join('.gemini', 'config')) for n in os.listdir(p(d))), baks)
    s = json.load(open(p('.claude', 'settings.json'), encoding='utf-8'))
    ag = json.load(open(p('.gemini', 'config', 'hooks.json'), encoding='utf-8'))
    check('5 uninstall: none of ours left, the user\'s own stays',
          '#clawd-event' not in json.dumps(s) and mine in [h for g in s['hooks']['Stop'] for h in g['hooks']] and 'clawd' not in ag, said)
    check('5 the save stays', os.path.isfile(os.path.join(HOME, 'state.json')) and HOME in said, said)
    # 6
    shutil.rmtree(USER)
    os.makedirs(USER)
    o = window(os.path.join(tmp, 'o6.json'))
    check('6 no agent: all greyed, nothing written', all(o.get(a, {}).get('usable') is False for a in ('claude', 'codex', 'deepseek', 'antigravity'))
          and os.listdir(USER) == [], (o, os.listdir(USER)))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print('connect_test: %d failed: %s' % (len(fails), fails) if fails else 'connect_test: all passed')
