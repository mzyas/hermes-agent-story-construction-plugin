import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'

const packageRoot = resolve(fileURLToPath(new URL('..', import.meta.url)))
const pluginPath = join(packageRoot, 'desktop', 'plugin.js')
const loaderSource = `
const sdk = 'data:text/javascript,export const PANES_AREA = "panes"; export const PALETTE_AREA = "palette"; export const ROUTES_AREA = "routes"; export const SIDEBAR_NAV_AREA = "sidebar.nav"; export const host = { state: {}, revealPane: () => {} }; export const usePluginI18n = () => key => key; export const useQuery = () => ({}); export const useValue = () => "default"'
const jsx = 'data:text/javascript,export const jsx = (type, props) => ({ type, props }); export const jsxs = (type, props) => ({ type, props })'
const react = 'data:text/javascript,export const useEffect = () => {}; export const useState = value => [value, () => {}]'
export async function resolve(specifier, context, defaultResolve) {
  if (specifier === '@hermes/plugin-sdk') return { url: sdk, shortCircuit: true }
  if (specifier === 'react/jsx-runtime') return { url: jsx, shortCircuit: true }
  if (specifier === 'react') return { url: react, shortCircuit: true }
  return defaultResolve(specifier, context, defaultResolve)
}
`

const loaderDir = mkdtempSync(join(tmpdir(), 'story-session-switcher-loader-'))
const loaderPath = join(loaderDir, 'loader.mjs')
writeFileSync(loaderPath, loaderSource, 'utf8')

const child = `
const { listStorySessions, switchStorySession } = await import(${JSON.stringify(pathToFileURL(pluginPath).href)})
const routes = [
  { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' },
  { connectionId: 'remote-1', mode: 'remote', profile: 'writer', targetProfile: 'writer' }
]
const listCalls = []
const listed = await listStorySessions({
  profile: 'writer',
  connectionId: 'remote-1',
  profileRoutes: async () => routes,
  listPersistedSessions: async (route, options) => {
    listCalls.push({ route, options })
    return { sessions: [{ id: 'session-2', title: 'Draft two' }, { id: 'session-1', preview: 'Earlier draft' }] }
  }
})
assert.deepEqual(listed.sessions.map(session => session.id), ['session-2', 'session-1'])
assert.deepEqual(listCalls, [{
  route: routes[1],
  options: { profile: 'writer', limit: 100 }
}])
const openCalls = []
await switchStorySession({
  sessionId: 'session-2',
  profile: 'writer',
  connectionId: 'remote-1',
  profileRoutes: async () => routes,
  openSession: async (...args) => openCalls.push(args)
})
assert.deepEqual(openCalls, [[
  'session-2',
  {
    route: routes[1],
    intent: 'in-place',
    awaitHydration: true,
    expectHistory: true,
    forceResume: true
  }
]])
`

const result = spawnSync(
  process.execPath,
  ['--experimental-loader', pathToFileURL(loaderPath).href, '--input-type=module', '--eval', child],
  { encoding: 'utf8' }
)

assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
