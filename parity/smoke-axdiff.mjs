// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// P7: AX diff + screenshot end-to-end against a real window.
import { spawn } from 'node:child_process'
const EXE = repoRoot + '\\helper-rs\\target\\release\\dsh-computer-use.exe'

function run(requests) {
  return new Promise((resolve, reject) => {
    const child = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    let buf = ''
    let stderr = ''
    const replies = new Map()
    child.stderr.on('data', (c) => { stderr += String(c) })
    child.stdout.setEncoding('utf8')
    child.stdout.on('data', (chunk) => {
      buf += chunk
      let idx
      while ((idx = buf.indexOf('\n')) !== -1) {
        const line = buf.slice(0, idx).trim()
        buf = buf.slice(idx + 1)
        if (!line) continue
        try { const m = JSON.parse(line); replies.set(m.id, m) } catch (e) { reject(new Error('bad line ' + line.slice(0, 120))) }
      }
      if (replies.size === requests.length) { child.kill(); resolve({ replies, stderr }) }
    })
    child.on('error', reject)
    for (const r of requests) child.stdin.write(JSON.stringify(r) + '\n')
    setTimeout(() => { child.kill(); resolve({ replies, stderr }) }, 40000)
  })
}

const list = (await run([{ id: 1, method: 'list_windows', params: {} }])).replies.get(1).result
const target = list.find((w) => w.app === 'msedge.exe' && w.title) || list.find((w) => w.title)
console.log('target:', JSON.stringify(target))
const win = { app: target.app, id: target.id }
const approved = { 'x-oai-cua-approved-app': target.app }

const result = await run([
  { id: 2, method: 'get_window_state', params: { window: win, include_screenshot: false, include_text: true }, meta: approved },
  { id: 3, method: 'get_window_state', params: { window: win, include_screenshot: false, include_text: true }, meta: approved },
  { id: 4, method: 'get_window_state', params: { window: win, include_screenshot: false, include_text: true, disableDiffing: true }, meta: approved },
  { id: 5, method: 'get_window_state', params: { window: win, include_screenshot: true, include_text: false }, meta: approved },
  { id: 6, method: 'get_window_state', params: { window: win, include_screenshot: false, include_text: true }, meta: approved },
])
for (const id of [2, 3, 4, 5, 6]) {
  const reply = result.replies.get(id)
  if (!reply) { console.log(id, 'NO REPLY'); continue }
  if (reply.ok !== true) { console.log(id, 'ERROR', reply.error); continue }
  const acc = reply.result.accessibility
  const shots = (reply.result.screenshots || [])
  if (!acc) { console.log(id, 'accessibility=null shots=' + shots.length); continue }
  const tree = String(acc.tree)
  console.log(id, 'diff=' + acc.diff, 'treeLen=' + tree.length, 'shots=' + shots.length)
  console.log('   ' + tree.slice(0, 260).replace(/\n/g, ' / '))
  if (shots.length) {
    const s = shots[0]
    console.log('   shot: id=' + s.id + ' z=' + s.zIndex + ' origin=' + s.originX + ',' + s.originY + ' size=' + s.width + 'x' + s.height + ' urlHead=' + String(s.url).slice(0, 30))
  }
}
if (result.stderr.trim()) console.log('stderr:', result.stderr.trim().slice(0, 300))