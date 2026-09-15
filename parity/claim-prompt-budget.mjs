// Derived paths only: no machine-specific absolute path belongs in a tracked script.
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const codexApp = path.join(localAppData, 'OpenAI', 'Codex')

// C1: the prompt budget must be measured on the plane the MODEL actually reads.
//
// `helper-rs/src/prompt.rs::native_prompt()` returns only the DSH header, and its Rust test
// asserts < 12,000 chars -- but the model in a Computer Use session reads the DSH
// system-prompt section, which is built by `src/prompt.js` and concatenates
// dsh-header + api + confirmations + guidance. Measuring the first while claiming the
// second is how "~2.5k tokens always-on" survived (register V2).
import { computerUsePrompt } from '../src/prompt.js'

const BUDGET = 12_288
const text = computerUsePrompt()
const officialAlwaysOn = 1_497 + 2_873 // official SKILL.md + the js tool description
const ok = text.length <= BUDGET
console.log(JSON.stringify({
  alwaysOnChars: text.length,
  budget: BUDGET,
  officialAlwaysOn,
  ratio: Number((text.length / officialAlwaysOn).toFixed(2)),
  ok,
}))
process.exit(ok ? 0 : 1)