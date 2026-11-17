"""DeepSeek Harness: the plugin (clawd_dsh.mjs, through tools/dsh_test.mjs under Node) and clawd.py hooks on/off
deepseek on a copy of a profile patch.  No pets, nothing of DeepSeek's own files is touched."""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import clawd

fails = []


def check(name, ok, detail=''):
    print('%s %s %s' % ('ok  ' if ok else 'FAIL', name, detail), flush=True)
    if not ok:
        fails.append(name)


def node():
    """Node from PATH, else DeepSeek Harness's own (its exe runs as Node with ELECTRON_RUN_AS_NODE=1)."""
    n = shutil.which('node')
    if n:
        return [n], None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\dsh\shell\open\command') as k:
            cmd = winreg.QueryValue(k, None)
        exe = cmd.split('"')[1]
        if os.path.isfile(exe):
            return [exe], dict(os.environ, ELECTRON_RUN_AS_NODE='1')
    except OSError:
        pass
    return None, None


# the plugin
cmd, env = node()
if cmd is None:
    print('skip the plugin: no Node and no DeepSeek Harness found')
else:
    p = subprocess.run(cmd + [os.path.join(HERE, 'tools', 'dsh_test.mjs')], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=60, env=env)
    out = p.stdout.decode('utf-8', 'replace')
    print(out.rstrip())
    check('the plugin (dsh_test.mjs)', p.returncode == 0 and ' 0 failed' in out, 'exit %s' % p.returncode)

# hooks on / status / off deepseek on a copy
tmp = tempfile.mkdtemp(prefix='clawd-dsh-')
try:
    path = os.path.join(tmp, 'cordis.patch.yml')
    original = ('# Your patch layer for this dsh profile\n- id: locale\n  name: "@deepseek-ai/dsh-client-locale"\n'
                '  config:\n    preference: zh\n')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(original)

    def run(*args):
        r = subprocess.run([sys.executable, os.path.join(HERE, 'clawd.py'), 'hooks'] + list(args) + ['deepseek', '--settings', path],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        return r.returncode, r.stdout.decode('utf-8', 'replace')

    def text():
        with open(path, encoding='utf-8') as f:
            return f.read()

    code, out = run('status')
    check('status before: not installed', code == 0 and ('未安装' in out or 'not installed' in out), out.strip())
    code, out = run('on')
    t = text()
    url = 'file:///' + os.path.join(HERE, 'clawd_dsh.mjs').replace('\\', '/').lstrip('/')
    check('on: our row, after what was there', code == 0 and t.startswith(original) and clawd.dsh_block() in t
          and "name: '%s'" % url in t, t[len(original):])
    check('on: a backup', any(n.startswith('cordis.patch.yml.bak-') for n in os.listdir(tmp)))
    code, out = run('on')
    check('on again: nothing to change', code == 0 and text() == t, out.strip())
    code, out = run('status')
    check('status: installed', code == 0 and ('已安装' in out or 'installed' in out), out.strip())
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write('- id: later\n  disabled: true\n')       # something DeepSeek adds after ours stays
    code, out = run('off')
    check('off: only our lines go', code == 0 and text() == original + '- id: later\n  disabled: true\n', repr(text()))
    code, out = run('off')
    check('off again: nothing to remove', code == 0 and ('没有' in out or 'No Clawd' in out), out.strip())
    os.remove(path)
    code, out = run('on')
    check('on without DeepSeek: says so, writes nothing', code == 1 and not os.path.exists(path), out.strip())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('dsh_test: %s' % ('all passed' if not fails else '%d failed: %s' % (len(fails), ', '.join(fails))))
sys.exit(1 if fails else 0)
