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
  export const host = { state: { connectionId: { get: () => 'local' } } }
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
const {
  STORY_SIDE_INTENT,
  storySessionOpenOptions,
  switchStorySession,
  continueStoryProjectSession,
  createStoryWritingSession,
  retryStoryKickoff,
  sideBySideKey,
  sideBySideTarget,
  markSideBySideOpened,
  forgetSideBySideOpened
} = await import(dataModule(rewriteDesktopImports(source)))

const localRoute = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }
const profileRoutes = async () => [localRoute]

test('Story sessions open as a tab beside the page, not in the main area', () => {
  assert.equal(STORY_SIDE_INTENT, 'tab')
  assert.equal(storySessionOpenOptions(localRoute, 'writer', 'local').intent, 'in-place')
  assert.equal(storySessionOpenOptions(localRoute, 'writer', 'local', STORY_SIDE_INTENT).intent, 'tab')
})

test('a tab beside the page does not wait for history, an in-place open does', () => {
  assert.equal(storySessionOpenOptions(localRoute, 'writer', 'local').expectHistory, true)
  assert.equal(storySessionOpenOptions(localRoute, 'writer', 'local', STORY_SIDE_INTENT).expectHistory, false)
})

test('switching and continuing pass the requested intent and default to in-place', async () => {
  const calls = []
  const openSession = async (...args) => calls.push(args)
  await switchStorySession({ sessionId: 's1', profile: 'writer', connectionId: 'local', profileRoutes, openSession })
  await switchStorySession({ sessionId: 's1', profile: 'writer', connectionId: 'local', profileRoutes, openSession, intent: 'tab' })
  const binding = { stored_session_id: 's2' }
  const continued = await continueStoryProjectSession({
    binding, profile: 'writer', connectionId: 'local', profileRoutes, openSession, intent: 'tab'
  })

  assert.deepEqual(calls.map(call => call[1].intent), ['in-place', 'tab', 'tab'])
  assert.deepEqual(continued, { status: 'opened', storedSessionId: 's2' })
})

test('a vanished session still reports stale when continued beside the page', async () => {
  const result = await continueStoryProjectSession({
    binding: { stored_session_id: 'gone' },
    profile: 'writer',
    connectionId: 'local',
    profileRoutes,
    openSession: async () => {
      throw Object.assign(new Error('session not found'), { code: 4007 })
    },
    intent: 'tab'
  })

  assert.equal(result.status, 'stale')
  assert.equal(result.storedSessionId, 'gone')
})

test('creating a writing session opens it with the requested intent', async () => {
  const opened = []
  const run = intent =>
    createStoryWritingSession({
      project: { id: 'novel', name: 'Novel' },
      profile: 'writer',
      connectionId: 'local',
      profileRoutes,
      retainProfile: async () => () => undefined,
      requestProfile: async (_route, method) =>
        method === 'session.create' ? { session_id: 'runtime-1', stored_session_id: 'stored-1' } : {},
      bindSession: async () => ({}),
      ensureWorkspace: async () => null,
      openSession: async (storedId, options) => opened.push([storedId, options]),
      ...(intent ? { intent } : {})
    })

  await run()
  await run('tab')

  assert.deepEqual(opened.map(entry => entry[1].intent), ['in-place', 'tab'])
  assert.equal(opened[1][1].expectHistory, false)
})

test('retrying the kickoff opens with the requested intent', async () => {
  const opened = []
  const recovery = {
    route: localRoute, storedId: 's1', runtimeId: 'r1', profile: 'writer', projectId: 'novel', text: 'hello'
  }
  const deps = {
    recovery,
    requestProfile: async () => ({ session_id: 'r1' }),
    bindSession: async () => ({}),
    openSession: async (storedId, options) => opened.push([storedId, options])
  }

  await retryStoryKickoff(deps)
  await retryStoryKickoff({ ...deps, intent: 'tab' })

  assert.deepEqual(opened.map(entry => entry[1].intent), ['in-place', 'tab'])
})

test('the latest bound session opens beside the page once per project', () => {
  const rows = [{ stored_session_id: 'new' }, { stored_session_id: 'old' }]
  const opened = new Set()
  const key = sideBySideKey({ profile: 'writer', connectionId: 'local', projectId: 'novel' })

  assert.equal(key, 'writer:local:novel')
  assert.equal(sideBySideTarget({ rows, focusedBound: false, key, opened }).stored_session_id, 'new')
  markSideBySideOpened(key, opened)
  assert.equal(sideBySideTarget({ rows, focusedBound: false, key, opened }), null)
  assert.equal(sideBySideTarget({ rows, focusedBound: false, key: 'writer:local:other', opened }).stored_session_id, 'new')
})

test('leaving a project lets the next visit open the session again', () => {
  const rows = [{ stored_session_id: 'a' }]
  const opened = new Set()
  const key = 'writer:local:novel'

  markSideBySideOpened(key, opened)
  forgetSideBySideOpened(key, opened)

  assert.equal(sideBySideTarget({ rows, focusedBound: false, key, opened }).stored_session_id, 'a')
})

test('nothing opens when a bound session is on screen, while busy, or with no sessions', () => {
  const rows = [{ stored_session_id: 'a' }]
  const key = 'writer:local:novel'

  assert.equal(sideBySideTarget({ rows, focusedBound: true, key, opened: new Set() }), null)
  assert.equal(sideBySideTarget({ rows, focusedBound: false, key, busy: true, opened: new Set() }), null)
  assert.equal(sideBySideTarget({ rows: [], focusedBound: false, key, opened: new Set() }), null)
  assert.equal(sideBySideTarget({ rows: undefined, focusedBound: false, key, opened: new Set() }), null)
  assert.equal(sideBySideTarget({ rows, focusedBound: false, key: '', opened: new Set() }), null)
})
