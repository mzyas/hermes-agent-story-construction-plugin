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
const { storySessionOpenOptions, switchStorySession, createStoryWritingSession } = await import(
  dataModule(rewriteDesktopImports(source))
)

const localRoute = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }
const remoteRoute = { connectionId: 'remote-1', mode: 'remote', profile: 'writer', targetProfile: 'writer' }
const common = { intent: 'in-place', awaitHydration: true, expectHistory: true, forceResume: true }

test('a route on the active connection opens by profile and keeps the sidebar scope', () => {
  assert.deepEqual(storySessionOpenOptions(localRoute, 'writer', 'local'), {
    profile: 'writer',
    keepAllProfilesScope: false,
    ...common
  })
})

test('the open target is the backend profile, not the display alias', () => {
  const aliased = { ...localRoute, profile: 'alias', targetProfile: 'writer' }
  assert.equal(storySessionOpenOptions(aliased, 'alias', 'local').profile, 'writer')
})

test('a route on another connection keeps the route so the session stays reachable', () => {
  assert.deepEqual(storySessionOpenOptions(remoteRoute, 'writer', 'local'), { route: remoteRoute, ...common })
})

test('an unknown active connection never drops the route', () => {
  assert.deepEqual(storySessionOpenOptions(remoteRoute, 'writer', undefined), { route: remoteRoute, ...common })
})

test('no route falls back to the profile and keeps the sidebar scope', () => {
  assert.deepEqual(storySessionOpenOptions(null, 'writer', 'local'), {
    profile: 'writer',
    keepAllProfilesScope: false,
    ...common
  })
})

test('switching sessions on the active connection does not request the all-profiles view', async () => {
  const calls = []
  await switchStorySession({
    sessionId: 'session-2',
    profile: 'writer',
    connectionId: 'local',
    profileRoutes: async () => [localRoute],
    openSession: async (...args) => calls.push(args)
  })

  assert.equal(calls.length, 1)
  assert.equal('route' in calls[0][1], false)
  assert.equal(calls[0][1].keepAllProfilesScope, false)
  assert.equal(calls[0][1].profile, 'writer')
})

test('creating a writing session on the active connection opens it without a route', async () => {
  const opened = []
  await createStoryWritingSession({
    project: { id: 'novel', name: 'Novel' },
    profile: 'writer',
    connectionId: 'local',
    profileRoutes: async () => [localRoute],
    retainProfile: async () => () => undefined,
    requestProfile: async (_route, method) =>
      method === 'session.create' ? { session_id: 'runtime-1', stored_session_id: 'stored-1' } : {},
    bindSession: async () => ({ context: { project: { id: 'novel', name: 'Novel' }, volumes: [], chapters: [] } }),
    openSession: async (storedId, options) => opened.push([storedId, options])
  })

  assert.equal(opened.length, 1)
  assert.equal('route' in opened[0][1], false)
  assert.equal(opened[0][1].keepAllProfilesScope, false)
})
