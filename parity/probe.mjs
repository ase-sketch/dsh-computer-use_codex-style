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
const child = spawn(EXE, ['--parent-pid', '0'], { stdio: ['pipe', 'pipe', 'pipe'] })
let out = ''
let err = ''
child.stdout.setEncoding('utf8')
child.stderr.setEncoding('utf8')
child.stdout.on('data', (c) => { out += c })
child.stderr.on('data', (c) => { err += c })
child.stdin.write(JSON.stringify({ id: 1, method: 'diagnostic_state', params: {} }) + '\n')
await new Promise((r) => setTimeout(r, 6000))
for (const line of out.trim().split('\n')) {
  try {
    const m = JSON.parse(line)
    const d = m.result
    console.log('foreground:', JSON.stringify(d.foreground))
    console.log('inputHwnd:', d.inputHwnd, 'processId:', d.processId, 'processName:', JSON.stringify(d.processName))
  } catch { console.log('raw:', line.slice(0, 200)) }
}
// Compare with a same-instant PowerShell probe is done separately.
if (err.trim()) console.log('STDERR:', err.trim().slice(0, 400))
child.kill()
