"""The real hook: clawd_hook.py as the agents run it (Claude Code in exec form, no shell), from a copy in a folder of
its own (CLAWD_HOME points it there: it writes the event file beside itself), so the real event file is never written.
What it writes for each kind of stdin, what it costs, and the hooks clawd.py installs."""
import json, os, shutil, subprocess, sys, tempfile, time

T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(tempfile.gettempdir(), 'clawd_hook_test')
os.environ['CLAWD_HOME'] = DIR                 # for the hook runs below and the modules imported here
sys.path.insert(0, T)
import clawd
import clawd_hook

PY = sys.executable
os.makedirs(DIR, exist_ok=True)
shutil.copy(os.path.join(T, 'clawd_hook.py'), DIR)
HOOK = os.path.join(DIR, 'clawd_hook.py')
OUT = os.path.join(DIR, 'event')
fails = []


def check(name, ok, detail=''):
    print('%s %s %s' % ('ok  ' if ok else 'FAIL', name, detail), flush=True)
    if not ok:
        fails.append(name)


def run(word, stdin, agent='claude', keep_open=0.0, extra=(), env=None):
    """-> (what it wrote, exit code, seconds it took).  keep_open: stdin left open that long after the input (an
    agent may not close it), the hook must not wait for it."""
    open(OUT, 'w').close()
    t = time.perf_counter()
    e = {k: v for k, v in os.environ.items() if k not in ('CLAUDE_CODE_ENTRYPOINT', 'WT_SESSION')}
    e.update(env or {})
    p = subprocess.Popen([PY, '-I', '-S', HOOK, word, agent] + list(extra) + [clawd.MARK], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e)
    try:
        p.stdin.write(stdin)
        p.stdin.flush()
        if not keep_open:
            p.stdin.close()
    except OSError:                    # it read the start it needs and is gone (as the bash read of 300 did)
        pass
    try:
        p.wait(max(5.0, keep_open + 5.0))
    except subprocess.TimeoutExpired:
        p.kill()
    took = time.perf_counter() - t
    if keep_open:
        try:
            p.stdin.close()
        except OSError:
            pass
    with open(OUT, encoding='utf-8', errors='replace') as f:
        return f.read().strip(), p.returncode, took


def payload(**extra):
    return json.dumps({'session_id': 'abcdef12-3456-7890-abcd-ef1234567890', 'transcript_path': 'C:\\Users\\me\\.claude\\projects\\x.jsonl',
                       'cwd': 'C:\\work', 'hook_event_name': 'PreToolUse', **extra}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


out, code, _ = run('read', payload(tool_name='Read'))
check('normal input', out == 'read abcdef12' and code == 0, repr(out))
out, code, _ = run('read', json.dumps({'session_id': 'abcdef12-3456'}).encode())
check('a space after the colon', out == 'read abcdef12' and code == 0, repr(out))
out, code, _ = run('read', b'')
check('empty stdin', out.split()[:1] == ['read'] and code == 0, repr(out))
out, code, _ = run('read', b'not json at all')
check('not json: still writes the word', out.split()[:1] == ['read'] and code == 0, repr(out))
out, code, _ = run('listen', payload(prompt='say "session_id":"deadbeef" and $(touch pwned) `id`'))
check('prompt text is not taken or run', out == 'listen abcdef12' and code == 0 and not os.path.exists('pwned'), repr(out))
out, code, big = run('edit', payload(tool_input={'content': '中文内容\n' * 200000}))
check('2 MB of input: finishes at once', out == 'edit abcdef12' and code == 0 and big < 1.0, '%.0f ms' % (big * 1000))
short = json.dumps({'session_id': 'abcdef12-3456-7890-abcd-ef1234567890', 'hook_event_name': 'SessionEnd', 'reason': 'other'}).encode()
out, code, took = run('bye', short, keep_open=4.0)
check('short input, stdin left open: finishes at once (the old bash read waited for it)',
      out == 'bye abcdef12' and code == 0 and took < 1.5, '%.0f ms, %r' % (took * 1000, out))
out, code, _ = run('think', payload(), agent='codex')
check('a Codex id: its last 8', out == 'think 34567890' and code == 0, repr(out))
out, code, _ = run('bad word!', payload())
check('a word that is not one: nothing written', out == '' and code == 0, repr(out))

# where a conversation is: desktop app or terminal (CLAUDE_CODE_ENTRYPOINT), its Windows Terminal tab (WT_SESSION)
WT = 'dbec3e68-58fc-4baa-9a55-2944f3ad6f7d'
out, code, _ = run('listen', payload(hook_event_name='UserPromptSubmit', prompt='hi'), extra=['--at'],
                   env={'CLAUDE_CODE_ENTRYPOINT': 'cli', 'WT_SESSION': WT})
L = out.splitlines()
check('listen --at: the word, then where (entry, tab)', len(L) == 2 and L[0] == 'listen abcdef12'
      and L[1].startswith('at abcdef12 ') and L[1].endswith(' claude cli ' + WT), repr(out))
out, code, _ = run('hello', payload(hook_event_name='SessionStart', source='startup'), extra=['--at'],
                   env={'CLAUDE_CODE_ENTRYPOINT': 'claude-desktop'})
check('the desktop app: its entry, no tab', out.splitlines()[-1:] and out.splitlines()[-1].endswith(' claude claude-desktop -'), repr(out))
out, code, _ = run('listen', payload(hook_event_name='UserPromptSubmit', prompt='x' * 9000, source='poll_event'), extra=['--at'])
check("Code Mode handing back a script's output (source poll_event): nothing written", out == '' and code == 0, repr(out))
out, code, _ = run('listen', payload(hook_event_name='UserPromptSubmit', prompt='talk about "source":"poll_event" please'), extra=['--at'])
check('a prompt that only says poll_event: still you', out.startswith('listen abcdef12'), repr(out))
out, code, _ = run('hello', payload(hook_event_name='SessionStart', source='compact'), extra=['--at'])
check('a compaction: hello, no at line (the window in front may be any)', out == 'hello abcdef12', repr(out))
out, code, took = run('listen', payload(hook_event_name='UserPromptSubmit', prompt='hi'), extra=['--at'], keep_open=4.0)
check('listen --at, stdin left open: finishes at once', out.startswith('listen abcdef12') and took < 2.5, '%.0f ms, %r' % (took * 1000, out))
out, code, took = run('listen', payload(hook_event_name='UserPromptSubmit', prompt='中文' * 300000), extra=['--at'])
check('listen --at, a long prompt: finishes at once', out.startswith('listen abcdef12') and took < 2.5, '%.0f ms, %r' % (took * 1000, out[:80]))

ts = sorted(run('think', payload())[2] for _ in range(20))
print('wall time per hook: median %.0f ms, slowest %.0f ms' % (ts[10] * 1000, ts[-1] * 1000))

# clawd_hook.py's keys
K = clawd_hook.session_key
check('key: the first 8 of an id', K('abcdef12-3456-7890-abcd-ef1234567890') == 'abcdef12', K('abcdef12-3456-7890-abcd-ef1234567890'))
check('key: a word before the id dropped', K('session-1a2b3c4d-0000') == '1a2b3c4d', K('session-1a2b3c4d-0000'))
check('key: Codex: the last 8 of its id', K('01a1dcaa-a2a4-74b3-94d3-f48f6b2260b0', 'codex') == '6b2260b0', K('01a1dcaa-a2a4-74b3-94d3-f48f6b2260b0', 'codex'))
check('key: Codex: two ids of one minute, two keys', K('01a1dcaa-ef21-7000-8000-000000000001', 'codex') != K('01a1dcaa-a2a4-74b3-94d3-f48f6b2260b0', 'codex'))
check('key: Codex: not a whole id: the first 8', K('01a1dcaa-a2a4', 'codex') == '01a1dcaa', K('01a1dcaa-a2a4', 'codex'))
check('key: junk: none', K('$(touch x)') == '' and K('') == '', K('$(touch x)'))

# what clawd.py installs for Claude Code: exec form (no shell), all marked, all async, at lines with listen and hello
e = clawd.hook_entries('claude')
check('Claude Code: 17 hooks, one a word', len(e) == len(clawd.HOOK_MAP), len(e))
check('Claude Code: all in exec form, marked, async', all(isinstance(h.get('args'), list) and h['args'][-1] == clawd.MARK
                                                         and h.get('async') and clawd.is_ours(h) for _, _, h in e))
at = sorted(ev for ev, _, h in e if '--at' in h['args'])
check('Claude Code: where it is, with SessionStart and UserPromptSubmit', at == sorted(clawd.WHERE_EVENTS), at)
check('an old shell-form hook of ours is still known as ours (hooks on replaces it)',
      clawd.is_ours({'type': 'command', 'command': 'read -r -n 300 j; echo x #clawd-event'}))
check("someone else's exec-form hook is not ours", not clawd.is_ours({'type': 'command', 'command': 'node', 'args': ['x.js']}))
# Antigravity (ag_*): it waits for each hook and reads its answer, so whatever comes in, the answer is {} at once
# and the agent goes on; the words come from its events, a turn kept in ag_turns.json (beside the hook)
AGT = os.path.join(DIR, 'ag_turns.json')
if os.path.exists(AGT):
    os.remove(AGT)
CID = '1a2b3c4d-0000-4000-8000-00000000abcd'


def ag(word, data):
    """-> (what it wrote, what it answered, exit code, seconds)"""
    open(OUT, 'w').close()
    t = time.perf_counter()
    raw = data if isinstance(data, bytes) else json.dumps(data).encode('utf-8')
    p = subprocess.run([PY, '-I', '-S', HOOK, word, 'antigravity', clawd.MARK], input=raw, capture_output=True, timeout=10)
    with open(OUT, encoding='utf-8', errors='replace') as f:
        return f.read().strip(), p.stdout.decode('utf-8', 'replace'), p.returncode, time.perf_counter() - t


def words(out):
    return [l for l in out.splitlines() if not l.startswith('at ')]


slow, answers = [], []
seq = [('ag_start', {}, ['hello 1a2b3c4d'], True, 'a conversation starts: hello, and where it is'),
       ('ag_turn', {}, ['listen 1a2b3c4d'], True, 'its first model call: a new turn'),
       ('ag_turn', {}, [], False, 'its next model call in the same turn: nothing'),
       ('ag_done', {'toolCall': {'name': 'view_file'}}, ['read 1a2b3c4d', 'think 1a2b3c4d'], False, 'a file read'),
       ('ag_done', {'toolCall': {'name': 'run_command'}, 'error': 'exit 1'}, ['run 1a2b3c4d', 'fail 1a2b3c4d'], False,
        'a command that failed'),
       ('ag_done', {'toolCall': {'name': 'invoke_subagent'}}, ['agent_done 1a2b3c4d'], False, 'a sub-agent back'),
       ('ag_done', {'toolCall': {'name': 'browser_click_element'}}, ['web 1a2b3c4d', 'think 1a2b3c4d'], False, 'a browser tool'),
       ('ag_done', {'toolCall': {'name': 'some_new_tool'}}, ['think 1a2b3c4d'], False, 'a tool it does not know: think'),
       ('ag_stop', {'terminationReason': 'COMPLETED'}, ['stop 1a2b3c4d'], False, 'its turn done: stop'),
       ('ag_turn', {}, ['listen 1a2b3c4d'], True, 'after a stop: a new turn'),
       ('ag_stop', {'terminationReason': 'USER_CANCELED'}, ['cut 1a2b3c4d'], False, 'the stop button: cut'),
       ('ag_turn', {}, ['listen 1a2b3c4d'], True, 'after a cut: a new turn'),
       ('ag_stop', {'terminationReason': 'ERROR'}, ['stopfail 1a2b3c4d'], False, 'stopped by an error: stopfail')]
for word, data, want, at, name in seq:
    out, ans, code, took = ag(word, dict(data, conversationId=CID))
    slow.append(took)
    answers.append(ans)
    L = out.splitlines()
    ok = words(out) == want and code == 0 and ans == '{}'
    if at:
        ok = ok and L[-1:] and L[-1].startswith('at 1a2b3c4d ') and L[-1].endswith(' antigravity')
    else:
        ok = ok and not any(l.startswith('at ') for l in L)
    check('Antigravity: ' + name, ok, repr((out, ans, code)))
# a turn left open by a crash (no Stop for 10 minutes): its next model call is a new turn
json.dump({'1a2b3c4d': [1, time.time() - 700]}, open(AGT, 'w'))
out, ans, code, _ = ag('ag_turn', {'conversationId': CID})
check('Antigravity: a turn with no hook for 10 minutes was over: a new turn', words(out) == ['listen 1a2b3c4d'], repr(out))
open(AGT, 'w').write('{not json')
out, ans, code, _ = ag('ag_stop', {'conversationId': CID})
check('Antigravity: its turns file broken: still a word, the answer {}', words(out) == ['stop 1a2b3c4d'] and ans == '{}', repr((out, ans)))
check('Antigravity: ... and the file written anew', json.load(open(AGT)).get('1a2b3c4d', [9])[0] == 0, open(AGT).read())
for name, raw in (('empty input', b''), ('not JSON', b'{oops'), ('a JSON list', b'[1,2]'), ('no conversation id', b'{"x":1}'),
                  ('an id that is not one', json.dumps({'conversationId': '$(rm -rf x)'}).encode()),
                  ('a tool call that is not an object', json.dumps({'conversationId': CID, 'toolCall': 'view_file'}).encode()),
                  ('2 MB of input', json.dumps({'conversationId': CID, 'pad': 'x' * (2 << 20)}).encode())):
    out, ans, code, took = ag('ag_done', raw)
    want = ['think 1a2b3c4d'] if CID in raw.decode('utf-8', 'ignore') else []
    check('Antigravity: %s: the answer {}, exit 0, %s' % (name, 'think' if want else 'nothing written'),
          ans == '{}' and code == 0 and words(out) == want and took < 2.0, repr((out[:60], ans, code, '%.0f ms' % (took * 1000))))
out, ans, code, _ = ag('ag_unknown_event', {'conversationId': CID})
check('Antigravity: an event it does not have: nothing, the answer {}', out == '' and ans == '{}' and code == 0, repr((out, ans)))
slow.sort()
print('Antigravity hook wall time: median %.0f ms, slowest %.0f ms' % (slow[len(slow) // 2] * 1000, slow[-1] * 1000))
check('Antigravity: each hook done within 1 s (it waits for them)', slow[-1] < 1.0, '%.0f ms' % (slow[-1] * 1000))

# what is installed for Antigravity and Codex: none that takes part in the agent's decisions
spec = clawd.ag_spec()
check('Antigravity: 4 events, no PreToolUse (an empty answer there denied every tool)',
      sorted(spec) == sorted(ev for ev, _ in clawd.AG_EVENTS) and 'PreToolUse' not in spec, sorted(spec))
hs = [h for v in spec.values() for x in v for h in (x.get('hooks') or [x])]
check('Antigravity: each answers {} itself if Python or the hook is gone', len(hs) == 4 and
      all(h['command'].endswith('|| echo {}') and h.get('timeout') for h in hs), [h['command'][-30:] for h in hs])
e = clawd.hook_entries('codex')
check('Codex: all in the background but SessionEnd (short, foreground)', all(h.get('async') for ev, _, h in e if ev != 'SessionEnd')
      and all('async' not in h and h.get('timeout') for ev, _, h in e if ev == 'SessionEnd'), [(ev, h.get('async')) for ev, _, h in e])
print('FAILED: %s' % fails if fails else 'all ok')
sys.exit(1 if fails else 0)
