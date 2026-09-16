#!/usr/bin/env node
import readline from 'node:readline'

const LINUX_TOOLS = [
  {
    name: 'list_apps',
    description: 'List apps that can be targeted by the Linux window API.',
    parameters: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: 'get_app_state',
    description: 'Capture the current state, screenshot, and accessibility text for an app window.',
    parameters: {
      type: 'object',
      properties: {
        app: { type: 'string', description: 'App identifier or linux-window:<id>' },
        disableDiff: { type: 'boolean', description: 'Return full accessibility tree instead of diff' },
      },
      required: ['app'],
      additionalProperties: false,
    },
  },
  {
    name: 'screenshot',
    description: 'Capture a screenshot of an app window or the desktop.',
    parameters: {
      type: 'object',
      properties: {
        app: { type: 'string', description: 'App identifier or linux-window:<id>' },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'click',
    description: 'Click either an indexed element or a coordinate in the app window.',
    parameters: {
      type: 'object',
      properties: {
        app: { type: 'string', description: 'App identifier or linux-window:<id>' },
        click_count: { type: 'number' },
        mouse_button: { type: 'string', enum: ['left', 'right', 'middle'] },
        x: { type: 'number' },
        y: { type: 'number' },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'scroll',
    description: 'Scroll in an app window.',
    parameters: {
      type: 'object',
      properties: {
        app: { type: 'string', description: 'App identifier or linux-window:<id>' },
        direction: { type: 'string', enum: ['up', 'down', 'left', 'right'] },
        pages: { type: 'number' },
        x: { type: 'number' },
        y: { type: 'number' },
      },
      required: ['direction'],
      additionalProperties: false,
    },
  },
  {
    name: 'press_key',
    description: 'Press a key or +-separated keyboard chord in an app window.',
    parameters: {
      type: 'object',
      properties: {
        app: { type: 'string', description: 'App identifier or linux-window:<id>' },
        key: { type: 'string', description: 'Key or key chord (e.g. Return, Control_L+c)' },
      },
      required: ['key'],
      additionalProperties: false,
    },
  },
  {
    name: 'type_text',
    description: 'Type text into the current focus in an app window.',
    parameters: {
      type: 'object',
      properties: {
        app: { type: 'string', description: 'App identifier or linux-window:<id>' },
        text: { type: 'string', description: 'Text to type' },
      },
      required: ['text'],
      additionalProperties: false,
    },
  },
]

// 1x1 transparent PNG base64
const DUMMY_PNG_BASE64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='

function handleCall(name, args = {}) {
  switch (name) {
    case 'list_apps':
      return {
        value: [
          { id: 'org.gnome.TextEditor', displayName: 'Text Editor', isRunning: true },
          { id: 'linux-window:101', displayName: 'Terminal', isRunning: true },
        ],
        images: [],
      }
    case 'get_app_state':
      return {
        value: {
          app: args.app || 'org.gnome.TextEditor',
          text: 'Window: "Untitled Document", App: org.gnome.TextEditor\n1 edit [Document content]',
        },
        images: [
          {
            data: DUMMY_PNG_BASE64,
            mimeType: 'image/png',
            name: 'screenshot.png',
          },
        ],
      }
    case 'screenshot':
      return {
        value: {
          app: args.app || 'linux-window:101',
          width: 1920,
          height: 1080,
        },
        images: [
          {
            data: DUMMY_PNG_BASE64,
            mimeType: 'image/png',
            name: 'screenshot.png',
          },
        ],
      }
    case 'click':
      return {
        value: {
          ok: true,
          action: 'click',
          app: args.app || 'linux-window:101',
          x: args.x ?? 100,
          y: args.y ?? 200,
        },
        images: [],
      }
    case 'scroll':
      return {
        value: {
          ok: true,
          action: 'scroll',
          app: args.app || 'linux-window:101',
          direction: args.direction || 'down',
          pages: args.pages ?? 1,
        },
        images: [],
      }
    case 'press_key':
      return {
        value: {
          ok: true,
          action: 'press_key',
          app: args.app || 'linux-window:101',
          key: args.key || 'Return',
        },
        images: [],
      }
    case 'type_text':
      return {
        value: {
          ok: true,
          action: 'type_text',
          app: args.app || 'linux-window:101',
          text: args.text || '',
        },
        images: [],
      }
    default:
      throw new Error(`unsupported method: ${name}`)
  }
}

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false,
})

rl.on('line', line => {
  const text = line.trim()
  if (!text) return
  let req
  try {
    req = JSON.parse(text)
  } catch (err) {
    return
  }

  const { id, method, params } = req
  try {
    if (method === 'health') {
      console.log(JSON.stringify({
        id,
        ok: true,
        result: {
          ok: true,
          codexRequired: false,
          backend: 'linux',
          surface: 'linux',
        },
      }))
      return
    }

    if (method === 'tools') {
      console.log(JSON.stringify({
        id,
        ok: true,
        result: {
          tools: LINUX_TOOLS,
          surface: 'linux',
        },
      }))
      return
    }

    if (method === 'call') {
      const toolName = params?.name
      const toolArgs = params?.arguments || {}
      const res = handleCall(toolName, toolArgs)
      console.log(JSON.stringify({
        id,
        ok: true,
        result: {
          ok: true,
          name: toolName,
          value: res.value,
          images: res.images,
        },
      }))
      return
    }

    if (method === 'shutdown') {
      console.log(JSON.stringify({
        id,
        ok: true,
        result: { ok: true },
      }))
      setTimeout(() => process.exit(0), 10)
      return
    }

    if (method === 'end_turn' || method === 'interrupt' || method === 'cancel' || method === 'prompt') {
      console.log(JSON.stringify({
        id,
        ok: true,
        result: { ok: true },
      }))
      return
    }

    console.log(JSON.stringify({
      id,
      ok: false,
      error: `unsupported method: ${method}`,
    }))
  } catch (error) {
    console.log(JSON.stringify({
      id,
      ok: false,
      error: error.message || String(error),
    }))
  }
})
