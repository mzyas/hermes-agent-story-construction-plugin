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

const loaderDir = mkdtempSync(join(tmpdir(), 'story-save-loader-'))
const loaderPath = join(loaderDir, 'loader.mjs')
writeFileSync(loaderPath, loaderSource, 'utf8')
const child = `
const { buildDiffState, buildSaveRequest, canConfirmSave, preserveSaveConflict } = await import(${JSON.stringify(pathToFileURL(pluginPath).href)})
if (canConfirmSave({ draft: 'draft', confirmed: false })) throw new Error('unconfirmed draft was enabled')
if (!canConfirmSave({ draft: 'draft', confirmed: true })) throw new Error('confirmed draft was disabled')
if (canConfirmSave({ draft: '', confirmed: true })) throw new Error('empty draft was enabled')
const request = buildSaveRequest({ sessionId: 's1', profile: 'writer', connectionId: 'remote', projectId: 'p1', chapterId: 'ch1', content: 'draft', expectedVersion: 'v1' })
if (request.session_id !== 's1' || request.connection_id !== 'remote' || request.expected_version !== 'v1' || request.confirmed !== true) throw new Error('save request lost scope/version/confirmation')
const state = buildDiffState('original', 'draft')
if (state.status !== 'draft' || !state.changed) throw new Error('draft diff state is wrong')
const conflict = preserveSaveConflict(state, { current: { content: 'changed by another editor', version: 'v2' } })
if (conflict.status !== 'conflict' || conflict.original.content !== 'changed by another editor' || conflict.draft !== 'draft') throw new Error('conflict did not preserve both contents')
`

const result = spawnSync(
  process.execPath,
  ['--experimental-loader', pathToFileURL(loaderPath).href, '--input-type=module', '--eval', child],
  { encoding: 'utf8' }
)

assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
