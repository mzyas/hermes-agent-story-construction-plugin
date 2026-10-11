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
  export const useState = value => [value, () => {}]
`)
const jsxRuntimeUrl = dataModule(`
  export const jsx = (type, props) => ({ type, props })
  export const jsxs = (type, props) => ({ type, props })
`)
const importUrls = { '@hermes/plugin-sdk': sdkUrl, react: reactUrl, 'react/jsx-runtime': jsxRuntimeUrl }

function rewriteDesktopImports(source) {
  return source.replace(/(from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\2/g, (whole, prefix, quote, specifier) =>
    importUrls[specifier] ? `${prefix}${quote}${importUrls[specifier]}${quote}` : whole
  )
}

const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
const { storySessionTitles, storySessionName, removeStoryProjectSessions } = await import(
  dataModule(rewriteDesktopImports(source))
)

const route = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }

function harness({ failDelete = {}, failUnbind = {}, live = [] } = {}) {
  const calls = []
  return {
    calls,
    options: {
      projectId: 'novel',
      profile: 'writer',
      connectionId: 'local',
      profileRoutes: async () => [route],
      requestProfile: async (_route, method, payload) => {
        if (method === 'session.active_list') return { sessions: live }
        if (method === 'session.close') {
          calls.push(['close', payload.session_id])
          return { closed: true }
        }
        calls.push(['delete', payload.session_id])
        if (failDelete[payload.session_id]) throw failDelete[payload.session_id]
        return {}
      },
      removeSession: async (_project, id) => {
        calls.push(['unbind', id])
        if (failUnbind[id]) throw failUnbind[id]
      }
    }
  }
}

test('session names follow the Hermes list and fall back to the saved title', () => {
  const titles = storySessionTitles([{ id: 'a', title: ' Story: test1 ' }, { id: 'b', title: '' }, { title: 'x' }])
  assert.deepEqual(titles, { a: 'Story: test1' })
  const bindings = [{ stored_session_id: 'b', title: 'Saved title' }]
  assert.equal(storySessionName('a', { titles, bindings }), 'Story: test1')
  assert.equal(storySessionName('b', { titles, bindings }), 'Saved title')
  assert.equal(storySessionName('c', { titles, bindings }), '')
  assert.equal(storySessionName('', { titles, bindings }), '')
})

test('removing a binding never touches the Hermes session', async () => {
  const { calls, options } = harness()
  const result = await removeStoryProjectSessions({ ...options, storedSessionIds: ['s1', 's2', 's1'] })
  assert.deepEqual(calls, [['unbind', 's1'], ['unbind', 's2']])
  assert.deepEqual(result.done, ['s1', 's2'])
  assert.deepEqual(result.failed, [])
})

test('permanent delete removes the Hermes session before the binding', async () => {
  const { calls, options } = harness()
  const result = await removeStoryProjectSessions({ ...options, storedSessionIds: ['s1'], deleteSession: true })
  assert.deepEqual(calls, [['delete', 's1'], ['unbind', 's1']])
  assert.deepEqual(result.done, ['s1'])
})

test('a refused delete keeps that binding and does not stop the others', async () => {
  const refused = Object.assign(new Error('session is active'), { code: 4023 })
  const { calls, options } = harness({ failDelete: { s1: refused } })
  const result = await removeStoryProjectSessions({ ...options, storedSessionIds: ['s1', 's2'], deleteSession: true })
  assert.deepEqual(calls, [['delete', 's1'], ['delete', 's2'], ['unbind', 's2']])
  assert.deepEqual(result.done, ['s2'])
  assert.equal(result.failed.length, 1)
  assert.equal(result.failed[0].storedSessionId, 's1')
})

test('an already missing Hermes session still loses its binding', async () => {
  const gone = Object.assign(new Error('session not found'), { code: 4001 })
  const { calls, options } = harness({ failDelete: { s1: gone } })
  const result = await removeStoryProjectSessions({ ...options, storedSessionIds: ['s1'], deleteSession: true })
  assert.deepEqual(calls, [['delete', 's1'], ['unbind', 's1']])
  assert.deepEqual(result.done, ['s1'])
})

test('nothing selected is rejected', async () => {
  const { options } = harness()
  await assert.rejects(removeStoryProjectSessions({ ...options, storedSessionIds: [] }), /no sessions/)
})

test('an idle live session is closed before it is deleted', async () => {
  const live = [
    { id: 'rt-1', session_key: 's1', status: 'idle' },
    { id: 'rt-2', session_key: 'other', status: 'idle' }
  ]
  const { calls, options } = harness({ live })
  const result = await removeStoryProjectSessions({ ...options, storedSessionIds: ['s1'], deleteSession: true })
  assert.deepEqual(calls, [['close', 'rt-1'], ['delete', 's1'], ['unbind', 's1']])
  assert.deepEqual(result.done, ['s1'])
})

test('a working live session is not closed or deleted', async () => {
  const { calls, options } = harness({ live: [{ id: 'rt-1', session_key: 's1', status: 'working' }] })
  const result = await removeStoryProjectSessions({ ...options, storedSessionIds: ['s1'], deleteSession: true })
  assert.deepEqual(calls, [])
  assert.deepEqual(result.done, [])
  assert.match(result.failed[0].error.message, /still working/)
})

test('an existing chat cannot be bound from the panel; only a new writing session is', () => {
  // Hermes freezes the Story prompt on a chat's first render, so late binding is gone.
  const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
  assert.equal(source.includes('bindFocusedSession'), false)
  assert.equal(source.includes("t('agent.boundSession'"), true)
})
