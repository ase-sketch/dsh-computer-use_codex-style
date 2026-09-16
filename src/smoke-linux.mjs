import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Sidecar } from './sidecar.js'

const engineRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
import fs from 'node:fs'
import { nativeHelperCandidates } from './paths.js'

const stubHelperPath = path.join(engineRoot, 'scripts', 'stub-linux-helper.mjs')

// If neither DSH_COMPUTER_USE_HELPER is set nor any native candidate exists, fallback to stub
const hasNative = nativeHelperCandidates(engineRoot).some(p => p && fs.existsSync(p))
if (!process.env.DSH_COMPUTER_USE_HELPER && !hasNative) {
  process.env.DSH_COMPUTER_USE_HELPER = stubHelperPath
}

const EXPECTED_LINUX_TOOLS = [
  'list_apps',
  'get_app_state',
  'screenshot',
  'click',
  'scroll',
  'press_key',
  'type_text',
]

const sidecar = new Sidecar({
  backend: 'linux',
  engineRoot,
})

try {
  // 1. Health check
  const health = await sidecar.request('health')
  if (health.codexRequired) throw new Error('codex must not be required')
  if (health.backend !== 'linux') throw new Error(`expected backend=linux, got ${health.backend}`)

  // 2. Tools list check (default surface should resolve to linux)
  const listed = await sidecar.request('tools')
  const names = (listed.tools || []).map(t => t.name)
  for (const expected of EXPECTED_LINUX_TOOLS) {
    if (!names.includes(expected)) {
      throw new Error(`missing tool ${expected} in linux surface: ${names.join(', ')}`)
    }
  }
  if (names.length !== EXPECTED_LINUX_TOOLS.length) {
    throw new Error(`expected exactly 7 linux tools, got ${names.length}: ${names.join(', ')}`)
  }

  // 3. Verify all 7 tools can be called through sidecar
  // 3.1 list_apps
  const listAppsRes = await sidecar.request('call', { name: 'list_apps', arguments: {} })
  if (!Array.isArray(listAppsRes.value) || listAppsRes.value.length === 0) {
    throw new Error('list_apps did not return expected array')
  }

  // 3.2 get_app_state (verify value & images part)
  const appStateRes = await sidecar.request('call', {
    name: 'get_app_state',
    arguments: { app: 'org.gnome.TextEditor' },
  })
  if (!appStateRes.images?.length) throw new Error('expected get_app_state images[]')
  if (typeof appStateRes.value?.text !== 'string') throw new Error('expected get_app_state text in value')
  if (JSON.stringify(appStateRes.value).includes('data:image')) {
    throw new Error('value must not contain raw image data')
  }

  // 3.3 screenshot
  const shotRes = await sidecar.request('call', {
    name: 'screenshot',
    arguments: { app: 'linux-window:101' },
  })
  if (!shotRes.images?.length) throw new Error('expected screenshot images[]')
  if (JSON.stringify(shotRes.value).includes('data:image')) {
    throw new Error('value must not contain raw image data')
  }

  // 3.4 click
  const clickRes = await sidecar.request('call', {
    name: 'click',
    arguments: { app: 'linux-window:101', x: 250, y: 350 },
  })
  if (!clickRes.value?.ok) throw new Error('click call failed')

  // 3.5 scroll
  const scrollRes = await sidecar.request('call', {
    name: 'scroll',
    arguments: { app: 'linux-window:101', direction: 'down' },
  })
  if (!scrollRes.value?.ok) throw new Error('scroll call failed')

  // 3.6 press_key
  const keyRes = await sidecar.request('call', {
    name: 'press_key',
    arguments: { app: 'linux-window:101', key: 'Return' },
  })
  if (!keyRes.value?.ok) throw new Error('press_key call failed')

  // 3.7 type_text
  const typeRes = await sidecar.request('call', {
    name: 'type_text',
    arguments: { app: 'linux-window:101', text: 'hello linux' },
  })
  if (!typeRes.value?.ok) throw new Error('type_text call failed')

  console.log(JSON.stringify({
    ok: true,
    backend: health.backend,
    surface: health.surface,
    tools: names.length,
    callsVerified: 7,
    images: {
      get_app_state: appStateRes.images.length,
      screenshot: shotRes.images.length,
    },
  }))
} finally {
  await sidecar.request('shutdown').catch(() => {})
  sidecar.dispose()
}
