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
  export const host = { state: { profile: { v: 'p1' }, connectionId: { v: 'c1' } } }
  export const usePluginI18n = () => (key, ...args) => [key, ...args].join('|')
  export const useQuery = options => { globalThis.lastQueryOptions = options; return globalThis.guideQuery || {} }
  export const useValue = state => state.v
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
const { StoryGuide, StoryPage, nextLayoutWidth, nextStoryMode, storyGuideEntries } = await import(dataModule(rewriteDesktopImports(source)))

const t = (key, ...args) => [key, ...args].join('|')
const guide = {
  prompts: [
    { id: 'global', version: 'G v8', text: 'main', chars: 4, max_chars: 4000, injected: true },
    { id: 'worker', version: 'W v1', text: 'worker', chars: 6, max_chars: null, injected: false },
    { id: 'future', version: 'F v1', text: 'later', chars: 5, max_chars: null, injected: true }
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

test('guide entries list the prompts then the skills, read from the payload', () => {
  const entries = storyGuideEntries(guide, t)
  assert.deepEqual(entries.map(entry => entry.id), ['prompt:global', 'prompt:worker', 'prompt:future', 'skill:record-format'])
  assert.equal(entries[0].version, 'G v8')
  assert.equal(entries[0].maxChars, 4000)
  assert.equal(entries[0].note, '')
  assert.equal(entries[1].maxChars, null)
  assert.equal(entries[3].label, 'story-construction:record-format')
  assert.equal(entries[3].note, 'Format')
})

test('a prompt that nothing injects is marked as such', () => {
  const [, worker] = storyGuideEntries(guide, t)
  assert.equal(worker.note, 'guide.notInjected')
})

test('a prompt id with no label falls back to the id', () => {
  const [global, , future] = storyGuideEntries(guide, key => (key === 'guide.global' ? 'Global prompt' : key))
  assert.equal(global.label, 'Global prompt')
  assert.equal(future.label, 'future')
})

test('guide entries tolerate a missing payload', () => {
  assert.deepEqual(storyGuideEntries(undefined, t), [])
})

test('a hidden page keeps the last real width', () => {
  assert.equal(nextLayoutWidth(900, 0), 900)
  assert.equal(nextLayoutWidth(0, 0), 0)
  assert.equal(nextLayoutWidth(900, 640), 640)
})

test('arrow keys, Home and End move between the page modes', () => {
  assert.equal(nextStoryMode('story', 'ArrowRight'), 'guide')
  assert.equal(nextStoryMode('guide', 'ArrowRight'), 'story')
  assert.equal(nextStoryMode('story', 'ArrowLeft'), 'guide')
  assert.equal(nextStoryMode('guide', 'Home'), 'story')
  assert.equal(nextStoryMode('story', 'End'), 'guide')
  assert.equal(nextStoryMode('story', 'a'), null)
})

test('the guide query is scoped to the connection and profile', () => {
  globalThis.guideQuery = { data: guide }
  StoryGuide({})
  assert.deepEqual(globalThis.lastQueryOptions.queryKey, ['story-construction', 'guide', 'p1', 'c1'])
  globalThis.guideQuery = undefined
})

test('the guide shows loading, error with retry, empty and the first entry selected', () => {
  globalThis.guideQuery = { isLoading: true }
  assert.equal(StoryGuide({}).props.children, 'guide.loading')

  let refetched = false
  globalThis.guideQuery = { error: new Error('down'), refetch: () => { refetched = true } }
  const failed = flat(StoryGuide({}))
  const retry = failed.find(node => node.type === 'button')
  assert.equal(retry.props.children, 'guide.retry')
  retry.props.onClick()
  assert.equal(refetched, true)

  globalThis.guideQuery = { data: { prompts: [], skills: [] } }
  const empty = StoryGuide({})
  assert.equal(empty.props.children, 'guide.empty')
  assert.equal(flat(empty).some(node => node.type === 'button'), false)

  globalThis.guideQuery = { data: guide }
  const nodes = flat(StoryGuide({}))
  assert.equal(nodes.find(node => node.type === 'pre').props.children, 'main')
  const current = nodes.filter(node => node.props?.['aria-current'] === 'true')
  assert.equal(current.length, 1)
  assert.equal(current[0].props.children, 'global')
  globalThis.guideQuery = undefined
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
  assert.equal(pane.props.role, 'tabpanel')
  assert.deepEqual(tabs.map(tab => tab.props.tabIndex), [0, -1])
  assert.deepEqual(tabs.map(tab => tab.props['aria-controls']), ['hermes-story-panel-story', 'hermes-story-panel-guide'])

  globalThis.forcedMode = 'guide'
  const guideView = StoryPage({})
  const hiddenPane = guideView.props.children[1]
  assert.deepEqual(hiddenPane.props.style, { display: 'none' })
  assert.equal(hiddenPane.props.children.type.name, 'ProjectWorkspace')
  const guidePanel = guideView.props.children[2]
  assert.equal(guidePanel.props.role, 'tabpanel')
  assert.equal(guidePanel.props.id, 'hermes-story-panel-guide')
  globalThis.forcedMode = undefined
})
