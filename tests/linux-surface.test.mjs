import { test } from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { Context } from '@deepseek-ai/cordis'
import ComputerUseService, { Config as HostConfig } from '../src/index.js'
import { Config as ToolConfig, apply as applyTools } from '../src/tool.js'
import { nativeHelperCandidates } from '../src/paths.js'
import { Sidecar, usesPython, pythonCatalog, LINUX_CALLS, WINDOW2_CALLS, callParamsFor, isWindow2Surface } from '../src/sidecar.js'

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

const EXPECTED_WINDOW2_TOOLS = [
  'list_windows',
  'get_window',
  'list_apps',
  'launch_app',
  'get_window_state',
  'click',
  'press_key',
  'type_text',
  'scroll',
  'set_value',
  'drag',
  'perform_secondary_action',
  'activate_window',
]

test('P2-ROUTING WINDOW2_CALLS definition and usesPython routing under backend=linux', () => {
  assert.equal(WINDOW2_CALLS.size, 13)
  for (const name of EXPECTED_WINDOW2_TOOLS) {
    assert.ok(WINDOW2_CALLS.has(name), 'WINDOW2_CALLS must contain ' + name)
  }

  // Under backend='linux', all 13 window2 methods stay on native helper
  for (const name of EXPECTED_WINDOW2_TOOLS) {
    assert.equal(
      usesPython('call', { name }, 'linux'),
      false,
      name + ' must stay on native helper when backend=linux',
    )
  }

  // Under backend='windows', all 13 window2 methods stay on native helper too
  for (const name of EXPECTED_WINDOW2_TOOLS) {
    assert.equal(
      usesPython('call', { name }, 'windows'),
      false,
      name + ' must stay on native helper when backend=windows',
    )
  }

  // Browser calls still use Python on both platforms
  assert.equal(usesPython('call', { name: 'create_tab' }, 'linux'), true)
  assert.equal(usesPython('call', { name: 'create_tab' }, 'windows'), true)

  // batch_actions with window2 actions stays on native helper
  assert.equal(
    usesPython('call', { name: 'batch_actions', arguments: { actions: [{ name: 'click' }, { name: 'set_value' }] } }, 'linux'),
    false,
  )
  // batch_actions with unknown action uses Python
  assert.equal(
    usesPython('call', { name: 'batch_actions', arguments: { actions: [{ name: 'create_tab' }] } }, 'linux'),
    true,
  )
})

test('P2-TOOL-REGISTRATION backend=linux with surface=computer registers 13 window2 tools', async () => {
  const registered = new Map()
  const calls = []

  const dshComputerUse = {
    config: { backend: 'linux', surface: 'computer' },
    tools: async surface => {
      assert.equal(surface, 'computer')
      return {
        surface: 'computer',
        tools: EXPECTED_WINDOW2_TOOLS.map(name => ({
          name,
          description: 'Window2 Tool ' + name,
          parameters: { type: 'object', properties: {} },
        })),
      }
    },
    call: async (name, args, signal, meta) => {
      calls.push({ name, args, meta })
      return { ok: true, name, value: { done: name }, images: [] }
    },
    health: async () => ({ ok: true, codexRequired: false, backend: 'linux', surface: 'computer' }),
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

  for (const name of EXPECTED_WINDOW2_TOOLS) {
    assert.ok(registered.has(name), 'missing registered window2 tool: ' + name)
  }
  assert.ok(registered.has('computer_use_health'), 'must register health tool')
  assert.ok(registered.has('computer_use_experience'), 'must register experience tool')

  // Execute a window2 tool (drag) and check dispatch
  const dragTool = registered.get('drag')
  const res = await dragTool.execute(
    { window: { id: 101, app: 'gedit' }, from_x: 10, from_y: 20, to_x: 100, to_y: 200 },
    { agent: { id: 'test' } },
  )
  assert.deepEqual(res.value, { done: 'drag' })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].name, 'drag')
  assert.deepEqual(calls[0].args, { window: { id: 101, app: 'gedit' }, from_x: 10, from_y: 20, to_x: 100, to_y: 200 })
})

test('P2-E2E-SMOKE-WINDOW2 sidecar end-to-end window2 surface with stub-linux-helper', async () => {
  const sidecar = new Sidecar({
    backend: 'linux',
    surface: 'computer',
    engineRoot: pluginRoot,
  })

  const origEnv = process.env.DSH_COMPUTER_USE_HELPER
  process.env.DSH_COMPUTER_USE_HELPER = stubHelper

  try {
    const health = await sidecar.request('health')
    assert.equal(health.backend, 'linux')
    assert.equal(health.codexRequired, false)

    const listed = await sidecar.request('tools')
    assert.equal(listed.surface, 'computer')
    const names = listed.tools.map(t => t.name)
    assert.deepEqual(names.sort(), [...EXPECTED_WINDOW2_TOOLS].sort())

    // Test list_windows
    const winList = await sidecar.request('call', { name: 'list_windows', arguments: {} })
    assert.equal(winList.ok, true)
    assert.ok(Array.isArray(winList.value))
    assert.equal(winList.value[0].id, 101)

    // Test get_window
    const win = await sidecar.request('call', { name: 'get_window', arguments: { id: 101 } })
    assert.equal(win.ok, true)
    assert.equal(win.value.id, 101)

    // Test get_window_state
    const state = await sidecar.request('call', {
      name: 'get_window_state',
      arguments: { window: { id: 101, app: 'org.gnome.TextEditor' } },
    })
    assert.equal(state.ok, true)
    assert.equal(state.images.length, 1)
    assert.ok(state.value.accessibility?.tree.includes('TextEditor'))
    assert.equal(state.value.screenshots.length, 1)

    // Test drag (which is rejected on linux 7-tool surface, but allowed on window2)
    const drag = await sidecar.request('call', {
      name: 'drag',
      arguments: {
        window: { id: 101, app: 'org.gnome.TextEditor' },
        from_x: 10,
        from_y: 20,
        to_x: 100,
        to_y: 200,
      },
    })
    assert.equal(drag.ok, true)
    assert.equal(drag.value.action, 'drag')

    // Test set_value
    const setValue = await sidecar.request('call', {
      name: 'set_value',
      arguments: {
        window: { id: 101, app: 'org.gnome.TextEditor' },
        element_index: 1,
        value: 'hello window2',
      },
    })
    assert.equal(setValue.ok, true)
    assert.equal(setValue.value.action, 'set_value')
    assert.equal(setValue.value.value, 'hello window2')

    // Test perform_secondary_action
    const sec = await sidecar.request('call', {
      name: 'perform_secondary_action',
      arguments: {
        window: { id: 101, app: 'org.gnome.TextEditor' },
        element_index: 1,
        action: 'Raise',
      },
    })
    assert.equal(sec.ok, true)
    assert.equal(sec.value.action, 'Raise')

    // Test activate_window
    const act = await sidecar.request('call', {
      name: 'activate_window',
      arguments: { window: { id: 101, app: 'org.gnome.TextEditor' } },
    })
    assert.equal(act.ok, true)
    assert.equal(act.value.action, 'activate_window')
  } finally {
    await sidecar.request('shutdown').catch(() => {})
    sidecar.dispose()
    if (origEnv !== undefined) process.env.DSH_COMPUTER_USE_HELPER = origEnv
    else delete process.env.DSH_COMPUTER_USE_HELPER
  }
})


// The five names both surfaces define. `drag`/`set_value`/... are window2-only and never
// collide, so only these five need a surface tag to resolve unambiguously.
const SHARED_CALL_NAMES = ['list_apps', 'click', 'press_key', 'type_text', 'scroll']
// The four of those that return an object carrying an explicit handler marker. `list_apps`
// answers with an array on both faces, so it is asserted through its shape instead.
const SHARED_OBJECT_CALLS = ['click', 'press_key', 'type_text', 'scroll']

test('P2-CALL-SURFACE callParamsFor tags only window2 turns and leaves P1 untouched', () => {
  const call = { name: 'click', arguments: { window: { id: 101 }, element_index: 1 } }

  // A window2 turn declares itself, so the helper can route the shared name natively.
  for (const surface of ['computer', 'windows', 'window2']) {
    assert.deepEqual(
      callParamsFor('call', call, { backend: 'linux', surface }),
      { ...call, surface: 'computer' },
      'surface=' + surface + ' must tag the call',
    )
  }

  // `all` is a union, not a face: on Linux it means window2 unless P1's linux was pinned,
  // which is exactly how listTools resolves it.
  assert.deepEqual(callParamsFor('call', call, { backend: 'linux', surface: 'all' }), { ...call, surface: 'computer' })
  assert.deepEqual(callParamsFor('call', {}, { backend: 'linux' }), {})

  // P1 callers keep the request shape they always sent: no new field at all.
  for (const config of [
    { backend: 'linux', surface: 'linux' },
    { backend: 'linux', surface: 'sky.window' },
    { backend: 'linux' },
    { backend: 'windows', surface: 'computer' },
    { backend: 'fake', surface: 'computer' },
  ]) {
    assert.deepEqual(callParamsFor('call', call, config), call, JSON.stringify(config) + ' must not tag')
  }

  // An explicit tag on the request is the caller's own declaration and wins.
  assert.deepEqual(
    callParamsFor('call', { ...call, surface: 'linux' }, { backend: 'linux', surface: 'computer' }),
    { ...call, surface: 'linux' },
  )

  // Only `call` is tagged: `tools` already carries its own surface and must not be rewritten.
  assert.deepEqual(callParamsFor('tools', { surface: 'all' }, { backend: 'linux', surface: 'computer' }), { surface: 'all' })
  assert.deepEqual(callParamsFor('health', {}, { backend: 'linux', surface: 'computer' }), {})
})

test('P2-CALL-SURFACE isWindow2Surface names the official face and its host spellings', () => {
  for (const name of ['computer', 'windows', 'window2', 'COMPUTER', 'Window2']) {
    assert.equal(isWindow2Surface(name), true, name + ' is the window2 face')
  }
  for (const name of ['linux', 'sky.window', 'all', 'desktop', 'browser', '', undefined, null]) {
    assert.equal(isWindow2Surface(name), false, String(name) + ' is not the window2 face')
  }
})

test('P2-CALL-SURFACE-DISPATCH a shared name reaches the window2 handler only when tagged', async () => {
  const sidecar = new Sidecar({ backend: 'linux', surface: 'computer', engineRoot: pluginRoot })
  const origEnv = process.env.DSH_COMPUTER_USE_HELPER
  process.env.DSH_COMPUTER_USE_HELPER = stubHelper

  try {
    await sidecar.request('tools')
    // window2 parameter shape: a window object plus an element index.
    const window2Click = await sidecar.request('call', {
      name: 'click',
      arguments: { window: { id: 101, app: 'org.gnome.TextEditor' }, element_index: 3 },
    })
    assert.equal(window2Click.ok, true)
    assert.equal(window2Click.value.handler, 'window2', 'a window2 turn must reach the window2 handler')
    assert.equal(window2Click.value.element_index, 3, 'the window2 shape must reach the handler intact')
    assert.equal(window2Click.value.window.id, 101, 'the window2 shape must reach the handler intact')

    for (const name of SHARED_OBJECT_CALLS) {
      const res = await sidecar.request('call', { name, arguments: { window: { id: 101 } } })
      assert.equal(res.ok, true, name + ' must answer')
      assert.equal(res.value.handler, 'window2', name + ' must reach the window2 handler on a window2 turn')
    }

    // list_apps is the fifth shared name: on window2 it groups windows under each app.
    const apps = await sidecar.request('call', { name: 'list_apps', arguments: {} })
    assert.equal(apps.ok, true)
    assert.ok(Array.isArray(apps.value) && Array.isArray(apps.value[0]?.windows), 'window2 list_apps must group windows under each app')
  } finally {
    await sidecar.request('shutdown').catch(() => {})
    sidecar.dispose()
    if (origEnv !== undefined) process.env.DSH_COMPUTER_USE_HELPER = origEnv
    else delete process.env.DSH_COMPUTER_USE_HELPER
  }
})

test('P2-CALL-SURFACE-P1-COMPAT an untagged P1 call keeps the sky.window handler', async () => {
  const sidecar = new Sidecar({ backend: 'linux', surface: 'linux', engineRoot: pluginRoot })
  const origEnv = process.env.DSH_COMPUTER_USE_HELPER
  process.env.DSH_COMPUTER_USE_HELPER = stubHelper

  try {
    await sidecar.request('tools')
    // The P1 parameter shape: an app id and absolute coordinates, no window object.
    const click = await sidecar.request('call', {
      name: 'click',
      arguments: { app: 'linux-window:101', x: 250, y: 350 },
    })
    assert.equal(click.ok, true)
    assert.equal(click.value.handler, 'sky.window', 'a P1 turn must keep the sky.window handler')
    assert.equal(click.value.x, 250)
    assert.equal(click.value.y, 350)

    for (const name of SHARED_OBJECT_CALLS) {
      const res = await sidecar.request('call', { name, arguments: { app: 'linux-window:101' } })
      assert.equal(res.ok, true, name + ' must answer')
      assert.equal(res.value.handler, 'sky.window', name + ' must keep the sky.window handler untagged')
    }

    // P1 list_apps answers with a flat catalog, not the window2 grouping.
    const apps = await sidecar.request('call', { name: 'list_apps', arguments: {} })
    assert.equal(apps.ok, true)
    assert.equal(apps.value[0].windows, undefined, 'P1 list_apps must not group windows')

    // A window2-only name has no P1 handler, so it goes to the native window2 dispatcher
    // even on a P1 face. It fails there for want of a window, not with an unsupported
    // name, which is what proves it reached a window2 handler at all.
    const drag = await sidecar.request('call', { name: 'drag', arguments: {} }).catch(err => ({ ok: false, error: err.message }))
    assert.equal(drag.ok, false, 'drag without a window must fail in the window2 handler')
    assert.match(
      String(drag.error || drag.value?.error || ''),
      /window is required/,
      'drag must be refused by the window2 handler, not as an unknown name',
    )
    assert.doesNotMatch(String(drag.error || drag.value?.error || ''), /unsupported method/, 'drag is not an unknown name')
  } finally {
    await sidecar.request('shutdown').catch(() => {})
    sidecar.dispose()
    if (origEnv !== undefined) process.env.DSH_COMPUTER_USE_HELPER = origEnv
    else delete process.env.DSH_COMPUTER_USE_HELPER
  }
})

test('P2-SIDECAR-ALL-SURFACE surface=all merges native window2 with python browser tools under backend=linux', async () => {
  const sidecarWindow2 = new Sidecar({
    backend: 'linux',
    surface: 'computer',
    engineRoot: pluginRoot,
  })

  let nativeRequestedSurface = null
  let pythonRequestedSurface = null

  sidecarWindow2.primary = {
    alive: true,
    rawRequest: async (method, payload) => {
      if (method === 'tools') {
        nativeRequestedSurface = payload.surface
        return {
          tools: EXPECTED_WINDOW2_TOOLS.map(name => ({ name })),
          surface: payload.surface,
        }
      }
      return { ok: true }
    },
  }

  sidecarWindow2.ensurePython = async () => ({
    rawRequest: async (method, payload) => {
      if (method === 'tools') {
        pythonRequestedSurface = payload.surface
        return {
          tools: [{ name: 'create_tab' }, { name: 'click' }], // click is duplicate, create_tab is extra
          surface: payload.surface,
        }
      }
      return { ok: true }
    },
  })

  const resAll = await sidecarWindow2.listTools({ surface: 'all' })
  assert.equal(nativeRequestedSurface, 'computer', 'native helper should receive surface=computer for window2 when surface=all')
  assert.equal(pythonRequestedSurface, 'all', 'python should receive surface=all')
  assert.equal(resAll.surface, 'all')
  const names = resAll.tools.map(t => t.name)
  for (const exp of EXPECTED_WINDOW2_TOOLS) {
    assert.ok(names.includes(exp), 'missing ' + exp)
  }
  assert.ok(names.includes('create_tab'), 'merged list must include create_tab from python')
  assert.equal(names.filter(n => n === 'click').length, 1, 'duplicate tools like click must be deduplicated')

  // Test P1 backward compatibility: when surface was configured as 'linux', surface='all' passes nativeSurface='linux'
  const sidecarP1 = new Sidecar({
    backend: 'linux',
    surface: 'linux',
    engineRoot: pluginRoot,
  })

  let p1NativeRequested = null
  sidecarP1.primary = {
    alive: true,
    rawRequest: async (method, payload) => {
      if (method === 'tools') {
        p1NativeRequested = payload.surface
        return {
          tools: EXPECTED_7_TOOLS.map(name => ({ name })),
          surface: payload.surface,
        }
      }
      return { ok: true }
    },
  }
  sidecarP1.ensurePython = async () => ({
    rawRequest: async () => ({ tools: [{ name: 'create_tab' }] }),
  })

  const resP1All = await sidecarP1.listTools({ surface: 'all' })
  assert.equal(p1NativeRequested, 'linux', 'native helper should receive surface=linux for P1 when surface=all')
  assert.ok(resP1All.tools.map(t => t.name).includes('create_tab'))
})


