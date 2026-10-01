import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const pluginUrl = new URL('./plugin.js', import.meta.url)

function dataModule(source) {
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
}

const sdkUrl = dataModule(`
  export const PANES_AREA = 'panes'
  export const PALETTE_AREA = 'palette'
  export const ROUTES_AREA = 'routes'
  export const SIDEBAR_NAV_AREA = 'sidebar.nav'
  export const host = { state: {} }
  export const usePluginI18n = () => key => key
  export const useQuery = () => ({})
  export const useValue = () => 'default'
`)
const reactUrl = dataModule(`
  export const useEffect = () => {}
  export const useState = value => [typeof value === 'function' ? value() : value, () => {}]
`)
const jsxRuntimeUrl = dataModule(`
  export const jsx = (type, props) => ({ type, props })
  export const jsxs = (type, props) => ({ type, props })
`)
const importUrls = {
  '@hermes/plugin-sdk': sdkUrl,
  react: reactUrl,
  'react/jsx-runtime': jsxRuntimeUrl
}

function rewriteDesktopImports(source) {
  return source.replace(/(from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\2/g, (whole, prefix, quote, specifier) =>
    importUrls[specifier] ? `${prefix}${quote}${importUrls[specifier]}${quote}` : whole
  )
}

const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
const { createProjectMemory } = await import(dataModule(rewriteDesktopImports(source)))

function fakeStorage(initial = {}) {
  const data = { ...initial }
  return {
    data,
    getItem: key => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = String(value)
    }
  }
}

const scopeA = { profile: 'default', connectionId: 'local' }
const scopeB = { profile: 'writer', connectionId: 'local' }

test('remembers the entered project per connection and profile', () => {
  const memory = createProjectMemory(fakeStorage())

  assert.equal(memory.get(scopeA), null)
  memory.set(scopeA, 'novel')
  memory.set(scopeB, 'other')

  assert.equal(memory.get(scopeA), 'novel')
  assert.equal(memory.get(scopeB), 'other')
  assert.equal(memory.get({ profile: 'default', connectionId: 'remote-1' }), null)
})

test('clearing a scope forgets only that scope', () => {
  const memory = createProjectMemory(fakeStorage())
  memory.set(scopeA, 'novel')
  memory.set(scopeB, 'other')

  memory.set(scopeA, null)

  assert.equal(memory.get(scopeA), null)
  assert.equal(memory.get(scopeB), 'other')
})

test('survives a restart through storage', () => {
  const storage = fakeStorage()
  createProjectMemory(storage).set(scopeA, 'novel')

  assert.equal(createProjectMemory(storage).get(scopeA), 'novel')
})

test('a cleared scope stays cleared after a restart', () => {
  const storage = fakeStorage()
  const first = createProjectMemory(storage)
  first.set(scopeA, 'novel')
  first.set(scopeA, null)

  assert.equal(createProjectMemory(storage).get(scopeA), null)
})

test('unreadable or malformed storage means nothing is remembered', () => {
  for (const initial of [{ 'story-construction.last-project.v1': '{not json' }, { 'story-construction.last-project.v1': '[1,2]' }, { 'story-construction.last-project.v1': '{"k":5}' }]) {
    assert.equal(createProjectMemory(fakeStorage(initial)).get(scopeA), null)
  }
})

test('storage that throws never breaks remembering for this run', () => {
  const broken = {
    getItem: () => {
      throw new Error('blocked')
    },
    setItem: () => {
      throw new Error('blocked')
    }
  }
  const memory = createProjectMemory(broken)

  memory.set(scopeA, 'novel')

  assert.equal(memory.get(scopeA), 'novel')
})

test('runs without any storage at all', () => {
  const memory = createProjectMemory(null)

  memory.set(scopeA, 'novel')

  assert.equal(memory.get(scopeA), 'novel')
})
