import * as host from './index.js'
import * as tool from './tool.js'
import { mergeToolLists, usesPython } from './sidecar.js'

if (typeof host.default !== 'function') throw new Error('HOST plugin must default-export a Service class')
if (host.default.inject === undefined) throw new Error('HOST Service class must declare static inject')
if (typeof host.Config !== 'function') throw new Error('HOST Config must be a Schemastery schema')
if (tool.default !== undefined) throw new Error('tool plugin must not default-export apply')
if (tool.name !== 'tool-computer-use') throw new Error(`unexpected tool name ${tool.name}`)
if (!Array.isArray(tool.inject) || !tool.inject.includes('tools') || !tool.inject.includes('dshComputerUse') || !tool.inject.includes('systemPrompt')) {
  throw new Error(`tool inject must include tools, dshComputerUse, and systemPrompt, got ${JSON.stringify(tool.inject)}`)
}
if (tool.inject.includes('attachments') || tool.inject.includes('approval')) {
  throw new Error('optional services must use ctx.get, not inject')
}
if (typeof tool.apply !== 'function') throw new Error('tool plugin must export apply')
if (typeof tool.Config !== 'function') throw new Error('tool Config must be a Schemastery schema')
if (!usesPython('tools', { surface: 'browser' })) throw new Error('tools(surface=browser) must use Python')
if (!usesPython('tools', { surface: 'all' })) throw new Error('tools(surface=all) must use Python')
if (usesPython('call', { name: 'click' })) throw new Error('click stays on the native helper')
if (!usesPython('call', { name: 'create_tab' })) throw new Error('create_tab must use Python')
if (!usesPython('call', { name: 'paste' })) throw new Error('paste must use Python')
if (!usesPython('call', { name: 'batch_actions', arguments: { actions: [{ name: 'tab_new' }] } })) {
  throw new Error('batch_actions with tab_* must use Python')
}
const merged = mergeToolLists(
  { tools: [{ name: 'list_windows' }] },
  { tools: [{ name: 'list_windows' }, { name: 'create_tab' }] },
  'all',
)
if (merged.tools.length !== 2 || merged.tools[1].name !== 'create_tab') {
  throw new Error('mergeToolLists should keep native window2 and add Python browser tools')
}
console.log(JSON.stringify({ ok: true, host: host.default.name, tool: tool.name, inject: tool.inject }))
