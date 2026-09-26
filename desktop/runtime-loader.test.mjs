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
  export const host = { state: {}, revealPane() {} }
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
function leafEntries(value, prefix = '') {
  if (typeof value === 'string' || typeof value === 'function') return [[prefix, value]]
  return Object.entries(value).flatMap(([key, child]) => leafEntries(child, prefix ? `${prefix}.${key}` : key))
}

test('loads through the Desktop single-module runtime without local files', async () => {
  const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
  const pluginModule = await import(dataModule(rewriteDesktopImports(source)))
  const locales = []

  pluginModule.default.register({
    registerMany() {},
    i18n: {
      register(bundles) {
        locales.push(bundles)
        return () => {}
      },
      t(key) {
        return key
      }
    }
  })

  assert.equal(pluginModule.default.id, 'story-construction')
  assert.equal(typeof pluginModule.createStoryProject, 'function')
  assert.equal(typeof pluginModule.fetchProjectSessions, 'function')
  assert.equal(typeof pluginModule.removeStorySession, 'function')
  assert.equal(typeof pluginModule.buildStoryKickoff, 'function')
  assert.equal(typeof pluginModule.createStoryWritingSession, 'function')
  assert.equal(typeof pluginModule.retryStoryKickoff, 'function')
  assert.equal(locales.length, 1)
  const [{ en, zh }] = locales
  assert.deepEqual(leafEntries(zh).map(([path]) => path), leafEntries(en).map(([path]) => path))
  for (const path of [
    'workspace.newProject',
    'workspace.projectName',
    'workspace.projectSlug',
    'workspace.createProject',
    'workspace.creatingProject',
    'workspace.backToLibrary',
    'workspace.projectsUnavailable',
    'library.search',
    'library.empty',
    'library.noMatch',
    'dialog.cancel',
    'dialog.nameRequired',
    'dialog.createFailed',
    'chapter.confirmLeave',
    'agent.newWritingSession',
    'agent.continueSession',
    'agent.retryFirstTask',
    'agent.removeStaleBinding',
    'agent.noSessions',
    'agent.stageCreating',
    'agent.stageBinding',
    'agent.stageSubmitting',
    'agent.stageOpening',
    'agent.stageReady',
    'agent.sessionFailed',
    'agent.continueFailed',
    'agent.removeFailed'
  ]) {
    assert.ok(leafEntries(en).some(([key]) => key === path), `missing English locale: ${path}`)
    assert.ok(leafEntries(zh).some(([key]) => key === path), `missing Chinese locale: ${path}`)
  }
  assert.equal(zh.workspace.title, '故事构建')
  assert.notEqual(zh.chapter.saveConfirmed, en.chapter.saveConfirmed)
  assert.notEqual(zh.workspace.newProject, en.workspace.newProject)
  assert.notEqual(zh.agent.newWritingSession, en.agent.newWritingSession)
  // Create and project-list failures show static safe copy only — the messages
  // never interpolate raw error text, IPC JSON, Vault paths, tokens or server
  // messages. The leave confirmation is static localized copy for the same
  // reason.
  assert.equal(typeof en.chapter.confirmLeave, 'string')
  assert.equal(typeof zh.chapter.confirmLeave, 'string')
  assert.notEqual(zh.chapter.confirmLeave, en.chapter.confirmLeave)
  assert.equal(typeof en.dialog.createFailed, 'string')
  assert.equal(typeof zh.dialog.createFailed, 'string')
  assert.notEqual(zh.dialog.createFailed, en.dialog.createFailed)
  assert.equal(typeof en.workspace.projectsUnavailable, 'string')
  assert.equal(typeof zh.workspace.projectsUnavailable, 'string')
  assert.notEqual(zh.workspace.projectsUnavailable, en.workspace.projectsUnavailable)
  assert.match(zh.agent.continueFailed('CONTINUE_SENTINEL'), /CONTINUE_SENTINEL/)
  assert.match(zh.agent.removeFailed('REMOVE_SENTINEL'), /REMOVE_SENTINEL/)
  assert.match(zh.chapter.saveFailed('VERSION_SENTINEL'), /VERSION_SENTINEL/)
})

test('localizes an empty story item title through the active plugin locale', async () => {
  const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
  const pluginModule = await import(dataModule(rewriteDesktopImports(source)))

  assert.equal(pluginModule.displayName({}, key => ({ 'tree.untitled': '未命名' })[key]), '未命名')
  assert.equal(pluginModule.displayName({ id: 'chapter-1' }, () => '未命名'), 'chapter-1')
})
