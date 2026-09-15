/**
 * Computer Use system-prompt section.
 *
 * Always-on text is exactly `dsh-header.md` (the session contract plus the
 * "Reference documents (read on demand)" pointer). The three official reference
 * documents travel through the skill's `references/` directory and are read on
 * demand, exactly like the official plugin (its SKILL.md points at
 * `../../docs/*`). Compositing all four files into the always-on section cost
 * 36,615 characters per request against the official ~4,370 (register V2 /
 * PSG-2 / SKILL-01).
 *
 * Missing assets fail loudly, mirroring the official `scripts/launch.mjs`: a
 * resource that cannot be read aborts startup instead of yielding a silently
 * degraded session. A session that loses `guidance.md` must not drive the real
 * desktop (MCP-15). `promptAssetStatus()` is the non-throwing form used by
 * `computer_use_health`.
 */

import fs from 'node:fs'
import path from 'node:path'
import { pluginRoot } from './paths.js'

/** Files whose text is injected into the always-on system prompt. */
export const ALWAYS_ON_FILES = ['dsh-header.md']

/** Official documents delivered on demand through the skill's references. */
export const REFERENCE_FILES = ['guidance.md', 'api.md', 'confirmations.md']

/**
 * Official **browser** documents (PSG-4), delivered through the
 * `computer-use-browser` skill's references. They are a separate channel from the
 * Windows references on purpose: the two files are both called
 * `confirmations.md` and hold *different* policies, so a basename is not an
 * identity. Note the desktop `confirmations.md` scopes itself to Windows UI
 * automation, so reading it must never satisfy the browser
 * `documents.json` `requiredFor` gate.
 */
export const BROWSER_REFERENCE_FILES = ['confirmations.md', 'browser-safety.md']

/** Official `documents.json` `requiredFor` table, path-qualified (PSG-4/PSG-5). */
export const BROWSER_REQUIRED_FOR = {
  'computer-use-browser/references/confirmations.md': [
    'tab_cdp_call',
    'tab_cdp_events',
    'webmcp_list_tools',
    'webmcp_invoke_tool',
  ],
}

/** Every asset the plugin needs before it may control the desktop. */
export const REQUIRED_PROMPT_FILES = [...ALWAYS_ON_FILES, ...REFERENCE_FILES]

export function promptsDir() {
  return path.join(pluginRoot(), 'helper-rs', 'assets', 'prompts')
}

/** The skill directory the reference documents are copied into. */
export function referencesDir() {
  return path.join(pluginRoot(), 'skills', 'computer-use', 'references')
}

/** The browser skill's references directory (PSG-4). */
export function browserReferencesDir() {
  return path.join(pluginRoot(), 'skills', 'computer-use-browser', 'references')
}

/**
 * Read-only asset inventory. Never throws: the health tool and the boot
 * diagnostics need to report a partial install instead of failing to describe it.
 * @param {string} [dir]
 * @returns {{ dir: string, present: string[], missing: string[], ok: boolean }}
 */
export function promptAssetStatus(dir = promptsDir()) {
  const present = []
  const missing = []
  for (const name of REQUIRED_PROMPT_FILES) {
    let readable = false
    try {
      readable = fs.readFileSync(path.join(dir, name), 'utf8').trim().length > 0
    } catch {
      readable = false
    }
    if (readable) present.push(name)
    else missing.push(name)
  }
  return { dir, present, missing, ok: missing.length === 0 }
}

/**
 * Read-only inventory of the browser policy documents (PSG-4). Same
 * never-throws contract as `promptAssetStatus`: health must be able to report a
 * partial install.
 * @param {string} [dir]
 * @returns {{ dir: string, present: string[], missing: string[], ok: boolean }}
 */
export function browserReferenceStatus(dir = browserReferencesDir()) {
  const present = []
  const missing = []
  for (const name of BROWSER_REFERENCE_FILES) {
    let readable = false
    try {
      readable = fs.readFileSync(path.join(dir, name), 'utf8').trim().length > 0
    } catch {
      readable = false
    }
    if (readable) present.push(name)
    else missing.push(name)
  }
  return { dir, present, missing, ok: missing.length === 0 }
}

let cached

/**
 * The always-on Computer Use section.
 *
 * @param {{ dir?: string }} [options] test-only directory override
 * @returns {string}
 * @throws when a required asset is missing or empty (official launch.mjs semantics)
 */
export function computerUsePrompt(options = {}) {
  const dir = options.dir || promptsDir()
  if (options.dir === undefined && cached !== undefined) return cached
  const status = promptAssetStatus(dir)
  if (!status.ok) {
    throw new Error(
      'computer-use prompt assets unavailable in ' +
      status.dir + ': missing ' + status.missing.join(', ') +
      '; refusing to run a Computer Use session without the official guidance documents',
    )
  }
  const text = ALWAYS_ON_FILES
    .map(name => fs.readFileSync(path.join(dir, name), 'utf8').trim())
    .join('\n\n---\n\n')
  if (options.dir === undefined) cached = text
  return text
}

/** Drop the process-lifetime cache (tests and a future runtime override). */
export function resetPromptCache() {
  cached = undefined
}

/**
 * The runtime documentation channel (official `read_documentation()` /
 * MCP-12): a small, always-available pointer the health tool returns on first
 * call so the model knows which reference file answers which question.
 * @returns {object}
 */
export function documentationSummary() {
  return {
    alwaysOn: ALWAYS_ON_FILES,
    references: REFERENCE_FILES,
    directory: referencesDir(),
    readBefore: {
      'guidance.md': 'before controlling Windows apps',
      'confirmations.md': 'before deciding whether a Windows UI action needs confirmation',
      'api.md': 'when you need a tool signature or object shape',
    },
    // PSG-4: the official browser policy documents are reachable through the
    // computer-use-browser skill. Listing them here is the plugin-side wiring, so
    // the model learns about them from health as well as from the skill body.
    browser: {
      directory: browserReferencesDir(),
      references: BROWSER_REFERENCE_FILES,
      status: browserReferenceStatus(),
      readBefore: {
        'confirmations.md': 'before deciding whether a browser action needs confirmation',
        'browser-safety.md': 'before any browser action that can transmit data',
      },
      requiredFor: BROWSER_REQUIRED_FOR,
    },
  }
}
