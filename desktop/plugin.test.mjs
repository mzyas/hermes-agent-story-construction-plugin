import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'

const packageRoot = resolve(fileURLToPath(new URL('..', import.meta.url)))
const pluginPath = join(packageRoot, 'desktop', 'plugin.js')

const loaderSource = `
const sdk = 'data:text/javascript,globalThis.navigatedPaths = []; export const PANES_AREA = "panes"; export const PALETTE_AREA = "palette"; export const ROUTES_AREA = "routes"; export const SIDEBAR_NAV_AREA = "sidebar.nav"; export const host = { state: {}, navigate: path => globalThis.navigatedPaths.push(path) }; export const usePluginI18n = () => key => key; export const useQuery = () => ({}); export const useValue = () => "default"'
const jsx = 'data:text/javascript,export const jsx = (type, props) => ({ type, props }); export const jsxs = (type, props) => ({ type, props })'
const react = 'data:text/javascript,export const useEffect = () => {}; export const useState = value => [value, () => {}]'
export async function resolve(specifier, context, defaultResolve) {
  if (specifier === '@hermes/plugin-sdk') return { url: sdk, shortCircuit: true }
  if (specifier === 'react/jsx-runtime') return { url: jsx, shortCircuit: true }
  if (specifier === 'react') return { url: react, shortCircuit: true }
  return defaultResolve(specifier, context, defaultResolve)
}
`

const loaderDir = mkdtempSync(join(tmpdir(), 'story-plugin-loader-'))
const loaderPath = join(loaderDir, 'loader.mjs')
writeFileSync(loaderPath, loaderSource, 'utf8')

const child = `
const plugin = (await import(${JSON.stringify(pathToFileURL(pluginPath).href)})).default
const contributions = []
const registeredLocales = []
plugin.register({
  registerMany(items) { contributions.push(...items) },
  i18n: {
    register(bundles) { registeredLocales.push(bundles); return () => {} },
    t(key) { return key }
  }
})
if (plugin.id !== 'story-construction') throw new Error('wrong plugin id')
if (registeredLocales.length !== 1 || !registeredLocales[0].zh) throw new Error('missing story locale bundle')
if (contributions.some(item => item.area === 'panes')) throw new Error('Story Construction still registers a layout pane')
const page = contributions.find(item => item.id === 'page')
if (!page || page.area !== 'routes' || page.data?.path !== '/story-construction') throw new Error('missing Story Construction page')
const nav = contributions.find(item => item.id === 'nav')
if (!nav || nav.area !== 'sidebar.nav' || nav.data?.path !== '/story-construction') throw new Error('missing Story Construction sidebar navigation')
const open = contributions.find(item => item.area === 'palette')
if (!open) throw new Error('missing palette opener')
open.data.run()
if (globalThis.navigatedPaths[0] !== '/story-construction') throw new Error('palette opener did not open the Story Construction page')
`

const result = spawnSync(
  process.execPath,
  ['--experimental-loader', pathToFileURL(loaderPath).href, '--input-type=module', '--eval', child],
  { encoding: 'utf8' }
)

assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
