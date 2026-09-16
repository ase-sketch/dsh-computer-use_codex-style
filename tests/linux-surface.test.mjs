import { test } from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { Context } from '@deepseek-ai/cordis'
import ComputerUseService, { Config as HostConfig } from '../src/index.js'
import { Config as ToolConfig, apply as applyTools } from '../src/tool.js'
import { nativeHelperCandidates } from '../src/paths.js'
import { Sidecar, usesPython, pythonCatalog, LINUX_CALLS } from '../src/sidecar.js'

const pluginRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const stubHelper = path.join(pluginRoot, 'scripts', 'stub-linux-helper.mjs')

const EXPECTED_7_TOOLS = [
  'list_apps',
  'get_app_state',
  'screenshot',
  'click',
  'scroll',
  'press_key',
  'type_text',
]

test('P1-PATHS linux candidate paths use helper-linux/ and support DSH_COMPUTER_USE_HELPER override', () => {
  const origPlatform = process.platform
  const origEnv = process.env.DSH_COMPUTER_USE_HELPER

  try {
    delete process.env.DSH_COMPUTER_USE_HELPER
    const candidates = nativeHelperCandidates(pluginRoot)
    if (process.platform === 'linux') {
      assert.ok(
        candidates.some(p => p.includes(path.join('helper-linux', 'target', 'release', 'dsh-computer-use'))),
        'must include helper-linux release target',
      )
      assert.ok(
        candidates.some(p => p.includes(path.join('helper-linux', 'target', 'debug', 'dsh-computer-use'))),
        'must include helper-linux debug target',
      )
      assert.ok(
        candidates.some(p => p.includes(path.join('helper-linux', 'bin', 'linux-x64', 'dsh-computer-use'))),
        'must include helper-linux bin linux-x64 target',
      )
      assert.ok(
        candidates.some(p => p === path.join(pluginRoot, 'dsh-computer-use')),
        'must include repo-root dsh-computer-use fallback',
      )
    }

    // Test DSH_COMPUTER_USE_HELPER override
    process.env.DSH_COMPUTER_USE_HELPER = '/custom/path/to/helper'
    const overridden = nativeHelperCandidates(pluginRoot)
    assert.equal(overridden[0], '/custom/path/to/helper', 'DSH_COMPUTER_USE_HELPER must be first candidate')
  } finally {
    if (origEnv !== undefined) process.env.DSH_COMPUTER_USE_HELPER = origEnv
    else delete process.env.DSH_COMPUTER_USE_HELPER
  }
})

test('P1-SIDECAR LINUX_CALLS and usesPython routing', () => {
  assert.equal(LINUX_CALLS.size, 7)
  for (const name of EXPECTED_7_TOOLS) {
    assert.ok(LINUX_CALLS.has(name), 'LINUX_CALLS must contain ' + name)
  }

  assert.equal(pythonCatalog('linux'), false, 'linux surface catalog does not use Python')
  assert.equal(usesPython('tools', { surface: 'linux' }), false)

  // Under backend='linux', all 7 tools stay on native helper
  for (const name of EXPECTED_7_TOOLS) {
    assert.equal(
      usesPython('call', { name }, 'linux'),
      false,
      name + ' must stay on native helper when backend=linux',
    )
  }

  // Under backend='windows', get_app_state and screenshot fall back to Python
  assert.equal(usesPython('call', { name: 'screenshot' }, 'windows'), true)
  assert.equal(usesPython('call', { name: 'get_app_state' }, 'windows'), true)
  assert.equal(usesPython('call', { name: 'click' }, 'windows'), false)

  // Browser calls still use Python
  assert.equal(usesPython('call', { name: 'create_tab' }, 'linux'), true)
})

test('P1-DEFAULT-SURFACE backend=linux defaults surface to linux when unspecified', () => {
  // Sidecar
  const sidecarLinux = new Sidecar({ backend: 'linux' })
  assert.equal(sidecarLinux.config.surface, 'linux')

  const sidecarExplicit = new Sidecar({ backend: 'linux', surface: 'computer' })
  assert.equal(sidecarExplicit.config.surface, 'computer')

  const sidecarWin = new Sidecar({ backend: 'windows' })
  assert.equal(sidecarWin.config.surface, undefined)

  // ComputerUseService
  const serviceLinux = new ComputerUseService(new Context(), { backend: 'linux' })
  assert.equal(serviceLinux.config.surface, 'linux')

  const serviceExplicit = new ComputerUseService(new Context(), { backend: 'linux', surface: 'custom' })
  assert.equal(serviceExplicit.config.surface, 'custom')

  const serviceWin = new ComputerUseService(new Context(), { backend: 'windows' })
  assert.equal(serviceWin.config.surface, 'computer')
})

test('P1-TOOL-REGISTRATION linux surface registers the 7 tools via stub helper', async () => {
  const registered = new Map()
  const calls = []

  const dshComputerUse = {
    config: { backend: 'linux', surface: 'linux' },
    tools: async surface => {
      assert.equal(surface, 'linux')
      return {
        surface: 'linux',
        tools: EXPECTED_7_TOOLS.map(name => ({
          name,
          description: 'Tool ' + name,
          parameters: { type: 'object', properties: {} },
        })),
      }
    },
    call: async (name, args, signal, meta) => {
      calls.push({ name, args, meta })
      return { ok: true, name, value: { done: name }, images: [] }
    },
    health: async () => ({ ok: true, codexRequired: false, backend: 'linux', surface: 'linux' }),
    releaseOverlay: async () => ({ ok: true }),
    shutdownSidecar: async () => {},
  }

  const ctx = {
    dshComputerUse,
    on() {},
    effect(fn) { fn() },
    get() { return undefined },
    tools: {
      register(tool) {
        registered.set(tool.name, tool)
      },
    },
    systemPrompt: { section() {} },
  }

  await applyTools(ctx, ToolConfig({}))

  for (const name of EXPECTED_7_TOOLS) {
    assert.ok(registered.has(name), 'missing registered tool: ' + name)
  }
  assert.ok(registered.has('computer_use_health'), 'must register health tool')
  assert.ok(registered.has('computer_use_experience'), 'must register experience tool')

  // Execute a tool and check dispatch
  const clickTool = registered.get('click')
  const res = await clickTool.execute({ app: 'linux-window:1', x: 10, y: 20 }, { agent: { id: 'test' } })
  assert.deepEqual(res.value, { done: 'click' })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].name, 'click')
  assert.deepEqual(calls[0].args, { app: 'linux-window:1', x: 10, y: 20 })
})

test('P1-E2E-SMOKE sidecar end-to-end with stub-linux-helper', async () => {
  const sidecar = new Sidecar({
    backend: 'linux',
    engineRoot: pluginRoot,
  })

  // Point to stub helper
  const origEnv = process.env.DSH_COMPUTER_USE_HELPER
  process.env.DSH_COMPUTER_USE_HELPER = stubHelper

  try {
    const health = await sidecar.request('health')
    assert.equal(health.backend, 'linux')
    assert.equal(health.codexRequired, false)

    const listed = await sidecar.request('tools')
    assert.equal(listed.surface, 'linux')
    const names = listed.tools.map(t => t.name)
    assert.deepEqual(names.sort(), [...EXPECTED_7_TOOLS].sort())

    // Test get_app_state returns images
    const state = await sidecar.request('call', {
      name: 'get_app_state',
      arguments: { app: 'org.gnome.TextEditor' },
    })
    assert.equal(state.ok, true)
    assert.equal(state.images.length, 1)
    assert.ok(state.value.text.includes('TextEditor'))

    // Test screenshot returns images
    const shot = await sidecar.request('call', {
      name: 'screenshot',
      arguments: { app: 'linux-window:101' },
    })
    assert.equal(shot.ok, true)
    assert.equal(shot.images.length, 1)
    assert.equal(shot.value.width, 1920)

    // Test click
    const click = await sidecar.request('call', {
      name: 'click',
      arguments: { app: 'linux-window:101', x: 100, y: 200 },
    })
    assert.equal(click.value.action, 'click')
  } finally {
    await sidecar.request('shutdown').catch(() => {})
    sidecar.dispose()
    if (origEnv !== undefined) process.env.DSH_COMPUTER_USE_HELPER = origEnv
    else delete process.env.DSH_COMPUTER_USE_HELPER
  }
})
