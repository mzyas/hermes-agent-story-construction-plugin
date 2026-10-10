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
  export const usePluginI18n = () => (key, ...args) => [key, ...args].join('|')
  export const useQuery = () => globalThis.guideQuery || {}
  export const useValue = () => 'default'
`)
// A test can force the first useState value (the page mode) through a global.
const reactUrl = dataModule(`
  export const useEffect = () => {}
  export const useState = value => [globalThis.forcedMode ?? value, () => {}]
`)
const jsxRuntimeUrl = dataModule(`
  export const jsx = (type, props, key) => ({ type, props, key })
  export const jsxs = (type, props, key) => ({ type, props, key })
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
const { StoryPage, storyGuideEntries } = await import(dataModule(rewriteDesktopImports(source)))

const t = (key, ...args) => [key, ...args].join('|')
const guide = {
  prompts: [
    { id: 'global', version: 'G v8', text: 'main', chars: 4, max_chars: 4000 },
    { id: 'worker', version: 'W v1', text: 'worker', chars: 6, max_chars: null }
  ],
  skills: [{ id: 'record-format', name: 'story-construction:record-format', description: 'Format', text: 'skill', chars: 5 }]
}

function flat(node, out = []) {
  if (Array.isArray(node)) node.forEach(child => flat(child, out))
  else if (node && typeof node === 'object' && 'type' in node) {
    out.push(node)
    flat(node.props?.children, out)
  }
  return out
}

test('guide entries list both prompts then the skills, read from the payload', () => {
  const entries = storyGuideEntries(guide, t)
  assert.deepEqual(entries.map(entry => entry.id), ['prompt:global', 'prompt:worker', 'skill:record-format'])
  assert.equal(entries[0].version, 'G v8')
  assert.equal(entries[0].maxChars, 4000)
  assert.equal(entries[1].maxChars, null)
  assert.equal(entries[1].note, 'guide.workerNote')
  assert.equal(entries[2].label, 'story-construction:record-format')
  assert.equal(entries[2].note, 'Format')
})

test('guide entries tolerate a missing payload', () => {
  assert.deepEqual(storyGuideEntries(undefined, t), [])
})

test('the page shows the Story workspace by default and keeps it mounted under the Guide', () => {
  globalThis.forcedMode = undefined
  const story = StoryPage({})
  const tabs = flat(story).filter(node => node.props?.role === 'tab')
  assert.deepEqual(tabs.map(tab => tab.props.children), ['page.modeStory', 'page.modeGuide'])
  assert.deepEqual(tabs.map(tab => tab.props['aria-selected']), [true, false])
  const pane = story.props.children[1]
  assert.equal(pane.props.style, undefined)
  assert.equal(story.props.children[2], null)

  globalThis.forcedMode = 'guide'
  const guideView = StoryPage({})
  const hiddenPane = guideView.props.children[1]
  assert.deepEqual(hiddenPane.props.style, { display: 'none' })
  assert.equal(hiddenPane.props.children.type.name, 'ProjectWorkspace')
  assert.notEqual(guideView.props.children[2], null)
  globalThis.forcedMode = undefined
})
