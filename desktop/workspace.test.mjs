import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'

const packageRoot = resolve(fileURLToPath(new URL('..', import.meta.url)))
const pluginPath = join(packageRoot, 'desktop', 'plugin.js')
const loaderSource = `
const sdk = 'data:text/javascript,export const PANES_AREA = "panes"; export const PALETTE_AREA = "palette"; export const ROUTES_AREA = "routes"; export const SIDEBAR_NAV_AREA = "sidebar.nav"; export const host = { state: {}, revealPane: () => {}, requestProfile: (route, method) => globalThis.__storyLifecycleCalls.push(method) }; export const usePluginI18n = () => key => key; export const useQuery = () => ({}); export const useValue = () => "default"'
const jsx = 'data:text/javascript,export const jsx = (type, props) => ({ type, props }); export const jsxs = (type, props) => ({ type, props })'
const react = 'data:text/javascript,export const useEffect = () => {}; export const useState = value => [value, () => {}]'
export async function resolve(specifier, context, defaultResolve) {
  if (specifier === '@hermes/plugin-sdk') return { url: sdk, shortCircuit: true }
  if (specifier === 'react/jsx-runtime') return { url: jsx, shortCircuit: true }
  if (specifier === 'react') return { url: react, shortCircuit: true }
  return defaultResolve(specifier, context, defaultResolve)
}
`

const loaderDir = mkdtempSync(join(tmpdir(), 'story-workspace-loader-'))
const loaderPath = join(loaderDir, 'loader.mjs')
writeFileSync(loaderPath, loaderSource, 'utf8')

const child = `
globalThis.__storyLifecycleCalls = []
const {
  bindWorkspaceApi,
  buildProjectTree,
  continueStoryProjectSession,
  normalizeProjectDraft,
  projectDiscoveryQuery,
  projectSessionRows,
  removeStaleStoryBinding,
  resetWorkspaceScope,
  selectedProjectForScope
} = await import(${JSON.stringify(pathToFileURL(pluginPath).href)})
assert.deepEqual(normalizeProjectDraft({ name: '  Novel  ', slug: ' novel-one ' }), {
  name: 'Novel', slug: 'novel-one'
})
assert.throws(() => normalizeProjectDraft({ name: '   ', slug: '' }), /project name/i)
assert.deepEqual(projectSessionRows({ sessions: [
  { stored_session_id: 's1', title: 'First', updated_at: '2026-09-22T01:00:00Z' },
  { stored_session_id: 's2', title: 'Second', updated_at: '2026-09-22T02:00:00Z' }
]}).map(row => row.stored_session_id), ['s2', 's1'])
assert.deepEqual(projectDiscoveryQuery({
  profile: 'writer',
  connectionId: 'remote-1',
  sessionId: 'focused-session',
  ready: true
}), {
  enabled: true,
  queryKey: ['story-construction', 'projects', 'writer', 'remote-1'],
  scope: { profile: 'writer', connectionId: 'remote-1' }
})
assert.deepEqual(projectDiscoveryQuery({
  profile: 'writer',
  connectionId: 'remote-1',
  sessionId: 'focused-session'
}), {
  enabled: false,
  queryKey: ['story-construction', 'projects', 'writer', 'remote-1'],
  scope: { profile: 'writer', connectionId: 'remote-1' }
})
const projectSelection = {
  profile: 'writer',
  connectionId: 'remote-1',
  projectId: 'project-1'
}
assert.equal(selectedProjectForScope(projectSelection, {
  profile: 'editor',
  connectionId: 'remote-1'
}), null)
assert.equal(selectedProjectForScope(projectSelection, {
  profile: 'writer',
  connectionId: 'remote-2'
}), null)
assert.equal(selectedProjectForScope(projectSelection, {
  profile: 'writer',
  connectionId: 'remote-1'
}), 'project-1')
const tree = buildProjectTree({
  project: { id: 'p1', name: 'Novel' },
  world_info: { id: 'w1', name: 'World' },
  world_info_entries: [{ id: 'e1', title: 'Rule' }],
  characters: [{ id: 'c1', name: 'Hero' }],
  categories: [{ id: 'cat1', name: 'Research' }],
  notes: [{ id: 'n1', title: 'Reference' }],
  volumes: [{ id: 'v1', title: 'Volume I' }],
  chapters: [{ id: 'ch1', volume_id: 'v1', title: 'Opening' }]
})
if (tree.branches.map(branch => branch.id).join(',') !== 'project,worldInfo,characters,notes,volumes,chapters') throw new Error('missing project branches')
if (tree.branches.find(branch => branch.id === 'chapters').children[0].id !== 'ch1') throw new Error('missing chapter')
const reset = resetWorkspaceScope(
  { profile: 'default', projectId: 'old', tree, selectedChapterId: 'ch1', status: 'ready' },
  { profile: 'default', projectId: 'new' }
)
if (reset.tree !== null || reset.selectedChapterId !== null) throw new Error('stale workspace survived project switch')
if (reset.projectId !== 'new') throw new Error('new project was not selected')

const lifecycleCalls = globalThis.__storyLifecycleCalls
const route = { connectionId: 'remote-1', profile: 'writer', targetProfile: 'writer' }
const continued = await continueStoryProjectSession({
  binding: { stored_session_id: 'stored-missing' },
  profile: 'writer',
  connectionId: 'remote-1',
  profileRoutes: async () => [route],
  openSession: async () => {
    lifecycleCalls.push('open')
    throw Object.assign(new Error('session not found'), { code: 4001 })
  }
})
assert.equal(continued.status, 'stale')
assert.equal(continued.storedSessionId, 'stored-missing')
assert.deepEqual(lifecycleCalls, ['open'])
assert.equal(lifecycleCalls.filter(call => call === 'session.create' || call === 'prompt.submit').length, 0)
assert.equal(lifecycleCalls.filter(call => call === 'delete').length, 0)
const unbindRest = bindWorkspaceApi(async (path, options) => {
  lifecycleCalls.push(options?.method === 'DELETE' ? 'delete' : 'rest:' + path)
  return { removed: true }
})
await removeStaleStoryBinding({
  projectId: 'p1',
  storedSessionId: continued.storedSessionId,
  profile: 'writer',
  connectionId: 'remote-1'
})
unbindRest()
assert.equal(lifecycleCalls.filter(call => call === 'delete').length, 1)
`

const result = spawnSync(
  process.execPath,
  ['--experimental-loader', pathToFileURL(loaderPath).href, '--input-type=module', '--eval', child],
  { encoding: 'utf8' }
)

assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
