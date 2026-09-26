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

const loaderDir = mkdtempSync(join(tmpdir(), 'story-scope-loader-'))
const loaderPath = join(loaderDir, 'loader.mjs')
writeFileSync(loaderPath, loaderSource, 'utf8')
const child = `
import assert from 'node:assert/strict'
const {
  bindWorkspaceApi,
  buildStoryScopeQuery,
  createStoryProject,
  fetchProjectSessions,
  removeStorySession,
  resetWorkspaceScope
} = await import(${JSON.stringify(pathToFileURL(pluginPath).href)})
const query = new URLSearchParams(buildStoryScopeQuery({ sessionId: 's 1', profile: 'writer', connectionId: 'remote' }))
if (query.get('session_id') !== 's 1' || query.get('profile') !== 'writer' || query.get('connection_id') !== 'remote') throw new Error('request scope was not encoded')
const reset = resetWorkspaceScope(
  { profile: 'writer', connectionId: 'local', sessionId: 's1', projectId: 'p1', tree: { stale: true }, selectedChapterId: 'ch1', status: 'ready' },
  { profile: 'writer', connectionId: 'remote', sessionId: 's1', projectId: 'p1' }
)
if (reset.tree !== null || reset.selectedChapterId !== null) throw new Error('connection switch retained stale workspace')

const calls = []
const dispose = bindWorkspaceApi(async (path, options) => {
  calls.push([path, options])
  return { ok: true }
})
await createStoryProject({ id: 'novel draft', name: 'Novel Draft' })
await fetchProjectSessions('novel draft', { sessionId: 's 1', profile: 'writer', connectionId: 'remote/1' })
await removeStorySession('novel draft', 'stored/1', { sessionId: 's 1', profile: 'writer', connectionId: 'remote/1' })
dispose()
assert.deepEqual(calls, [
  ['/projects', { method: 'POST', body: { id: 'novel draft', name: 'Novel Draft' } }],
  ['/projects/novel%20draft/sessions?session_id=s+1&profile=writer&connection_id=remote%2F1', undefined],
  ['/projects/novel%20draft/sessions/stored%2F1?session_id=s+1&profile=writer&connection_id=remote%2F1', { method: 'DELETE' }]
])
`

const result = spawnSync(
  process.execPath,
  ['--experimental-loader', pathToFileURL(loaderPath).href, '--input-type=module', '--eval', child],
  { encoding: 'utf8' }
)

assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
