import { spawn } from 'node:child_process'
// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

const EXE = repoRoot + '\\helper-rs\\target\\release\\dsh-computer-use.exe'
function run(requests) {
  return new Promise((resolve, reject) => {
    const child = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
    let buf = ''; let stderr = ''; const replies = new Map()
    child.stderr.on('data', (c) => { stderr += String(c) })
    child.stdout.setEncoding('utf8')
    child.stdout.on('data', (chunk) => {
      buf += chunk; let idx
      while ((idx = buf.indexOf('\n')) !== -1) {
        const line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 1)
        if (!line) continue
        try { replies.set(JSON.parse(line).id, JSON.parse(line)) } catch {}
      }
      if (replies.size === requests.length) { child.kill(); resolve({ replies, stderr }) }
    })
    child.on('error', reject)
    for (const r of requests) child.stdin.write(JSON.stringify(r) + '\n')
    setTimeout(() => { child.kill(); resolve({ replies, stderr }) }, 60000)
  })
}
const list = (await run([{ id: 1, method: 'list_windows', params: {} }])).replies.get(1).result
const target = list.find((w) => w.app === 'msedge.exe' && w.title)
const win = { app: target.app, id: target.id }
const meta = { 'x-oai-cua-approved-app': target.app }
const text = (extra = {}) => ({ method: 'get_window_state', params: { window: win, include_screenshot: false, include_text: true, ...extra }, meta })
const shot = () => ({ method: 'get_window_state', params: { window: win, include_screenshot: true, include_text: false }, meta })
// Deliberate sequence: observe, observe, screenshot-only, observe
const reqs = [
  { id: 11, ...text() },
  { id: 12, ...text() },
  { id: 13, ...shot() },
  { id: 14, ...text() },
  { id: 15, ...shot() },
  { id: 16, ...text() },
]
const res = await run(reqs)
const describe = (r, label) => {
  if (!r) return console.log(label, 'NO REPLY')
  if (r.ok !== true) return console.log(label, 'ERR', r.error)
  const acc = r.result.accessibility
  const shots = (r.result.screenshots || []).length
  if (!acc) return console.log(label, 'accessibility=null shots=' + shots)
  const t = String(acc.tree)
  const kind = t === 'no accessibility-tree change' ? 'NO-CHANGE' : (t.startsWith('removed:') || t.startsWith('added/changed:') ? 'DIFF' : 'FULL')
  console.log(label, 'kind=' + kind, 'diff=' + acc.diff, 'len=' + t.length, 'shots=' + shots)
}
for (const action of ['text', 'text', 'shot', 'text', 'shot', 'text']) {}
for (const id of [11, 12, 13, 14, 15, 16]) {
  const label = { 11: '1 observe', 12: '2 observe', 13: '3 screenshot-only', 14: '4 observe(after screenshot)', 15: '5 screenshot-only', 16: '6 observe(after screenshot)' }[id]
  describe(res.replies.get(id), label)
}
if (res.stderr.trim()) console.log('stderr:', res.stderr.trim().slice(0, 300))