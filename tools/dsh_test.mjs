// tools/dsh_test.mjs: the DeepSeek Harness plugin (clawd_dsh.mjs) against a stand-in for DeepSeek's event bus.
// node tools/dsh_test.mjs   (any Node 18+; DeepSeek's own: set ELECTRON_RUN_AS_NODE=1 and run "DeepSeek Harness.exe")
// It writes into a temporary folder, never into the pets' event file, and checks the lines that come out.
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const plugin = await import(pathToFileURL(join(here, '..', 'clawd_dsh.mjs')).href)
const home = mkdtempSync(join(tmpdir(), 'clawd-dsh-'))
const file = join(home, 'event')

const listeners = {}
const agents = new Map()
const cleanups = []
const ctx = {
  on: (name, fn) => { (listeners[name] ||= []).push(fn) },
  get: (name) => (name === 'agents' ? agents : undefined),
  effect: (fn) => { cleanups.push(fn()) },     // as cordis: the setup runs now, its return runs on dispose
}
plugin.apply(ctx, { home })

let passed = 0, failed = 0
const check = (what, ok, extra) => {
  if (ok) passed++; else failed++
  console.log((ok ? 'ok   ' : 'FAIL ') + what + (ok || extra === undefined ? '' : '  -> ' + JSON.stringify(extra)))
}
const tick = () => new Promise((r) => setTimeout(r, 30))
const lines = () => (existsSync(file) ? readFileSync(file, 'ascii').split('\n').filter(Boolean) : [])
// a waterfall: the plugin must hand on what comes after it, untouched
async function gate(name, ...args) {
  const marker = { kind: 'downstream' }
  let out
  for (const fn of listeners[name] || []) out = await fn(...args, () => Promise.resolve(marker))
  return out === marker
}
const emit = async (name, ...args) => { for (const fn of listeners[name] || []) await fn(...args) }
const mk = (id, parentSession) => {
  const a = { id, session: { header: parentSession ? { id, parentSession } : { id } } }
  agents.set(id, a)
  return a
}

const main = mk('session-1a2b3c4d-0000-4000-8000-000000000001')
const child = mk('session-99998888-0000-4000-8000-000000000002', main.id)
const other = mk('session-abcdef01-0000-4000-8000-000000000003')

check('listens to every event it uses', ['agent/pre-step', 'tools/pre-execute', 'tools/post-execute', 'agent/turn-stopping',
  'agent/error', 'agent/status', 'subagent/start', 'subagent/end', 'user-questions/request', 'approval/request']
  .every((n) => listeners[n]), Object.keys(listeners))

// a turn: a message, a read, a command that fails, an edit, a question, the end
check('a message passes on', await gate('agent/pre-step', { agent: main, messages: [{}], turn: 1 }))
check('a step with nothing new passes on', await gate('agent/pre-step', { agent: main, messages: [], turn: 1 }))
check('a tool passes on', await gate('tools/pre-execute', { agent: main, name: 'read' }))
await gate('tools/post-execute', { agent: main, name: 'read' }, { isError: false })
await gate('tools/pre-execute', { agent: main, name: 'pwsh' })
check('a tool result passes on', await gate('tools/post-execute', { agent: main, name: 'pwsh' }, { isError: true }))
await gate('tools/pre-execute', { agent: main, name: 'str_replace_editor' })
await gate('tools/pre-execute', { agent: main, name: 'todo_write' })     // not one of ours: no line
check('a question passes on', await gate('user-questions/request', { agent: main }))
check('an approval passes on', await gate('approval/request', { agent: main }))
await emit('agent/turn-stopping', { agent: main, turn: 1 })
await emit('agent/status', { agent: main, status: 'idle' })             // after a stop: nothing more
await tick()
check('one turn', JSON.stringify(lines()) === JSON.stringify([
  'listen 1a2b3c4d', 'at 1a2b3c4d 0 deepseek', 'read 1a2b3c4d', 'think 1a2b3c4d', 'run 1a2b3c4d', 'fail 1a2b3c4d',
  'edit 1a2b3c4d', 'attention 1a2b3c4d', 'attention 1a2b3c4d', 'stop 1a2b3c4d']), lines())

// a sub-agent: its tools count for the conversation that sent it; its own steps and end do not end that turn
rmSync(file, { force: true })
await gate('agent/pre-step', { agent: main, messages: [{}], turn: 2 })
await emit('subagent/start', { id: child.id, runId: 'r1' })
await gate('agent/pre-step', { agent: child, messages: [{}], turn: 1 })
await gate('tools/pre-execute', { agent: child, name: 'grep' })
await emit('agent/turn-stopping', { agent: child, turn: 1 })
await emit('agent/status', { agent: child, status: 'idle' })
await emit('subagent/end', { id: child.id, runId: 'r1' })
await emit('agent/turn-stopping', { agent: main, turn: 2 })
await tick()
check('a sub-agent', JSON.stringify(lines()) === JSON.stringify([
  'listen 1a2b3c4d', 'at 1a2b3c4d 0 deepseek', 'agent 1a2b3c4d', 'read 1a2b3c4d', 'agent_done 1a2b3c4d', 'stop 1a2b3c4d']), lines())

// stopped by you (no stop, no error: just idle), an error, and an abort
rmSync(file, { force: true })
await gate('agent/pre-step', { agent: main, messages: [{}], turn: 3 })
await emit('agent/status', { agent: main, status: 'idle' })
await gate('agent/pre-step', { agent: other, messages: [{}], turn: 1 })
await emit('agent/error', { agent: other, error: new Error('rate limit') })
await emit('agent/status', { agent: other, status: 'idle' })
await gate('agent/pre-step', { agent: main, messages: [{}], turn: 4 })
const abort = new Error('aborted'); abort.name = 'AbortError'
await emit('agent/error', { agent: main, error: abort })
await emit('agent/status', { agent: main, status: 'idle' })
await tick()
check('stopped (cut), error, abort (cut)', JSON.stringify(lines()) === JSON.stringify([
  'listen 1a2b3c4d', 'at 1a2b3c4d 0 deepseek', 'cut 1a2b3c4d',
  'listen abcdef01', 'at abcdef01 0 deepseek', 'stopfail abcdef01',
  'listen 1a2b3c4d', 'at 1a2b3c4d 0 deepseek', 'cut 1a2b3c4d']), lines())

// DeepSeek quits mid-turn: every conversation that worked says bye (the pets stop and their circles go)
rmSync(file, { force: true })
await gate('agent/pre-step', { agent: main, messages: [{}], turn: 5 })
await gate('tools/pre-execute', { agent: main, name: 'pwsh' })
check('one cleanup for quitting', cleanups.length === 1 && typeof cleanups[0] === 'function', cleanups.length)
await cleanups[0]()
await tick()
check('quitting: bye for each', JSON.stringify(lines()) === JSON.stringify([
  'listen 1a2b3c4d', 'at 1a2b3c4d 0 deepseek', 'run 1a2b3c4d', 'bye 1a2b3c4d', 'bye abcdef01']), lines())

// odd input never throws and writes nothing it cannot name
rmSync(file, { force: true })
let threw = false
try {
  await gate('tools/pre-execute', { name: 'pwsh' })
  await gate('tools/post-execute', { agent: { session: null } }, null)
  await gate('agent/pre-step', { agent: { session: { header: { id: 'weird id' } } }, messages: [{}] })
  await emit('agent/turn-stopping', {})
  await emit('subagent/start', undefined)
  await gate('approval/request', undefined)
} catch (e) { threw = e }
await tick()
check('odd input: no throw, no line', !threw && lines().length === 0, threw ? String(threw) : lines())

rmSync(home, { recursive: true, force: true })
console.log(`dsh_test: ${passed} passed, ${failed} failed`)
process.exit(failed ? 1 : 0)
