// clawd_dsh.mjs: DeepSeek Harness -> the desktop pets.  A plugin of DeepSeek Harness (loaded by its plugin loader from
// a row `clawd hooks on deepseek` adds to the profile's cordis.patch.yml), not a hook: DeepSeek runs hook commands in
// its sandbox, which may not write outside the workspace, while a plugin runs in its own process.
//
// It only listens.  Each thing the agent does becomes one line in the pets' event file, the same words the other
// agents' hooks write ("run 1a2b3c4d", "stop 1a2b3c4d", ...; see clawd.py HOOK_MAP), and once per message an "at" line
// ("at 1a2b3c4d 0 deepseek": the window is DeepSeek's own, which the pets find by its program).  Nothing of a prompt,
// a command or a file is written.  It never blocks, changes or slows what DeepSeek does: every gate is passed straight
// on (next()), every note is wrapped, a failed write is dropped.
//
// Uses DeepSeek Harness's own events (0.2.1): agent/pre-step, tools/pre-execute, tools/post-execute,
// agent/turn-stopping, agent/error, agent/status, subagent/start, subagent/end, user-questions/request,
// approval/request; and on quitting (ctx.effect's cleanup) "bye" for each conversation that worked.  If a later
// version renames one, that one just stops showing.

import { existsSync } from 'node:fs'
import { appendFile, mkdir } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'clawd-pet'

// where the pets read their events, found as clawd_pet.pyw finds it (default_home): CLAWD_HOME; this folder if a
// save is already here (a copy run from source); else %APPDATA%\Clawd (an install)
function dataHome() {
  if (process.env.CLAWD_HOME) return process.env.CLAWD_HOME
  const here = dirname(fileURLToPath(import.meta.url))
  if (existsSync(join(here, 'state.json')) || existsSync(join(here, 'grow.json'))) return here
  return join(process.env.APPDATA || homedir(), 'Clawd')
}

// the tools of DeepSeek Harness -> the pets' words; others keep the current action
const TOOLS = {
  pwsh: 'run', bash: 'run', terminal_open: 'run', terminal_send: 'run',
  read: 'read', read_image: 'read', glob: 'read', grep: 'read',
  edit: 'edit', write: 'edit', str_replace_editor: 'edit',
  web_fetch: 'web', web_search: 'web',
}

export function apply(ctx, config) {
  const home = (config && typeof config.home === 'string' && config.home) || dataHome()
  const file = join(home, 'event')
  const open = new Map()                 // top-level session -> true while its turn has not been reported ended
  let queue = Promise.resolve()          // one write after another: the lines keep their order

  const write = (text) => {              // the home is made if the pets never ran
    queue = queue.then(() => appendFile(file, text, 'ascii')
      .catch(() => mkdir(home, { recursive: true }).then(() => appendFile(file, text, 'ascii')))).catch(() => {})
  }
  const short = (id) => {                // "session-1a2b3c4d-..." -> "1a2b3c4d"
    const s = typeof id === 'string' ? id.replace(/^[a-z]+[-_]/i, '').slice(0, 8).toLowerCase() : ''
    return /^[0-9a-f-]{8}$/.test(s) ? s : ''
  }
  // a sub-agent's work counts for the conversation that sent it (as Claude Code's hooks report it)
  const top = (agent) => {
    let header = agent && agent.session && agent.session.header
    let id = header && header.id
    let child = false
    for (let i = 0; i < 8 && header && header.parentSession; i++) {
      child = true
      id = header.parentSession
      const parent = ctx.get && ctx.get('agents') && ctx.get('agents').get(id)
      header = parent && parent.session && parent.session.header
    }
    return { id: short(id), child }
  }
  const note = (fn) => {
    try { fn() } catch (_) {}
  }
  const seen = new Set()                 // top-level sessions that worked while this ran
  const say = (word, sid) => {
    if (sid) write(word + ' ' + sid + '\n')
  }

  // DeepSeek quits (or the plugin is turned off): its conversations end here, so the pets stop working on them now
  // and their circles go (else a turn cut short stayed "busy" till the pets' 10-minute safety net)
  if (typeof ctx.effect === 'function') {
    ctx.effect(() => () => {
      for (const sid of seen) write('bye ' + sid + '\n')
      seen.clear()
      open.clear()
      return queue
    }, 'clawd-pet: the pets hear its conversations end')
  }

  // a message (or anything else) starts a step with something new in it: the turn is on
  ctx.on('agent/pre-step', (ev, next) => {
    note(() => {
      const t = top(ev.agent)
      if (!t.child && t.id && ev.messages && ev.messages.length) {
        open.set(t.id, true)
        seen.add(t.id)
        write('listen ' + t.id + '\nat ' + t.id + ' 0 deepseek\n')
      }
    })
    return next()
  })
  ctx.on('tools/pre-execute', (exec, next) => {
    note(() => {
      const word = TOOLS[exec.name]
      if (word) say(word, top(exec.agent).id)
    })
    return next()
  })
  ctx.on('tools/post-execute', (exec, result, next) => {
    note(() => say(result && result.isError ? 'fail' : 'think', top(exec.agent).id))
    return next()
  })
  ctx.on('agent/turn-stopping', (ev) => {
    note(() => {
      const t = top(ev.agent)
      if (!t.child && open.delete(t.id)) say('stop', t.id)
    })
  })
  ctx.on('agent/error', (ev) => {
    note(() => {
      const t = top(ev.agent)
      const e = ev.error
      const stopped = e && (e.name === 'AbortError' || /abort/i.test(String(e.code || '')))
      if (!t.child && !stopped && open.delete(t.id)) say('stopfail', t.id)
    })
  })
  // idle with the turn not reported ended: you stopped it (no event says so): "cut", the pets take it as an
  // interrupt (they stop, no "done"; it was "stop" before 2026-11-14 and showed as done)
  ctx.on('agent/status', (ev) => {
    note(() => {
      const t = top(ev.agent)
      if (!t.child && ev.status === 'idle' && open.delete(t.id)) say('cut', t.id)
    })
  })
  const parentOf = (info, parent) => {
    if (parent && parent.session) return top(parent).id
    const child = ctx.get && ctx.get('agents') && ctx.get('agents').get(info && info.id)
    return child ? top(child).id : ''
  }
  ctx.on('subagent/start', (info, parent) => {
    note(() => say('agent', parentOf(info, parent)))
  })
  ctx.on('subagent/end', (info, parent) => {
    note(() => say('agent_done', parentOf(info, parent)))
  })
  // it asks you something, or asks to be allowed to do something: your turn
  ctx.on('user-questions/request', (req, next) => {
    note(() => say('attention', top(req && req.agent).id))
    return next()
  })
  ctx.on('approval/request', (req, next) => {
    note(() => say('attention', top(req && req.agent).id))
    return next()
  })
}
