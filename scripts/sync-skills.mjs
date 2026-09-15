#!/usr/bin/env node
/**
 * Declarative skill delivery (PKG-02 / SKILL-02).
 *
 * The manifest is the single source of the skill root; this script mirrors it
 * into every install target or verifies the copies byte-for-byte, so skills no
 * longer rely on three hand-maintained copies drifting apart.
 *
 *   node scripts/sync-skills.mjs --check
 *   node scripts/sync-skills.mjs --write --target <skills-dir>
 *   node scripts/sync-skills.mjs --check --defaults
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const pluginRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const manifest = JSON.parse(fs.readFileSync(path.join(pluginRoot, 'dsh-plugin.json'), 'utf8'))
const skillRoot = path.resolve(pluginRoot, manifest.skills || './skills/')

function listFiles(root, prefix = '') {
  const out = []
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const rel = prefix ? prefix + '/' + entry.name : entry.name
    if (entry.isDirectory()) out.push(...listFiles(path.join(root, entry.name), rel))
    else out.push(rel)
  }
  return out.sort()
}

function defaultTargets() {
  const home = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
  return [path.join(home, '.agent-presets', 'computer-use', 'skills'), path.join(home, 'skills')]
}

const args = process.argv.slice(2)
const write = args.includes('--write')
const targets = []
for (let i = 0; i < args.length; i += 1) {
  if (args[i] === '--target' && args[i + 1]) targets.push(path.resolve(args[++i]))
}
if (args.includes('--defaults')) targets.push(...defaultTargets())
if (targets.length === 0) targets.push(skillRoot)

const files = listFiles(skillRoot)
let drift = 0
for (const target of targets) {
  for (const rel of files) {
    const source = path.join(skillRoot, rel)
    const dest = path.join(target, rel)
    const same = fs.existsSync(dest) && fs.readFileSync(source).equals(fs.readFileSync(dest))
    if (same) continue
    drift += 1
    if (write) {
      fs.mkdirSync(path.dirname(dest), { recursive: true })
      fs.copyFileSync(source, dest)
      console.log('synced ' + dest)
    } else {
      console.log('DRIFT ' + dest)
    }
  }
  if (fs.existsSync(target)) {
    for (const rel of listFiles(target)) {
      if (!files.includes(rel)) {
        drift += 1
        console.log((write ? 'removed ' : 'EXTRA ') + path.join(target, rel))
      }
    }
  }
}
console.log(JSON.stringify({ ok: drift === 0, files: files.length, targets: targets.length, drift }))
process.exit(drift === 0 || write ? 0 : 1)
