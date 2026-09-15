import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Sidecar } from './sidecar.js'

const engineRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sidecar = new Sidecar({
  backend: 'fake',
  surface: 'desktop',
  engineRoot,
  pythonPath: process.env.PYTHON || '',
})

try {
  const health = await sidecar.request('health')
  if (health.codexRequired) throw new Error('codex must not be required')
  const listed = await sidecar.request('tools', { surface: 'computer' })
  const names = listed.tools.map(tool => tool.name)
  if (!names.includes('get_window_state')) throw new Error(`missing get_window_state in ${names}`)
  if (names.some(name => String(name).startsWith('tab_') || name === 'create_tab')) {
    throw new Error(`computer surface leaked browser tools: ${names}`)
  }
  const browser = await sidecar.request('tools', { surface: 'browser' })
  const browserNames = (browser.tools || []).map(tool => tool.name)
  if (!browserNames.includes('create_tab') && !browserNames.includes('tab_new')) {
    throw new Error(`browser surface missing tab tools after native prefer: ${browserNames.slice(0, 12)}`)
  }
  const shot = await sidecar.request('call', {
    name: 'get_window_state',
    arguments: { window: { app: 'notepad.exe', id: 1 } },
  })
  if (!shot.images?.length) throw new Error('expected screenshot images[]')
  if (JSON.stringify(shot.value).includes('data:image')) throw new Error('value still contains data:image')
  console.log(JSON.stringify({
    ok: true,
    backend: health.resolved,
    tools: names.length,
    browserTools: browserNames.length,
    images: shot.images.length,
  }))
} finally {
  sidecar.dispose()
}
