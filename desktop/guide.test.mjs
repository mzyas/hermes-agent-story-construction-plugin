import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { afterEach } from 'node:test'
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
  export const useEffect = effect => { globalThis.effectCleanup = effect() }
  export const useState = value => {
    const slot = { value: globalThis.forcedMode ?? value }
    const set = next => {
      slot.value = typeof next === 'function' ? next(slot.value) : next
      globalThis.lastState = slot.value
    }
    return [slot.value, set]
  }
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
const { StoryGuide, StoryPage, nextLayoutWidth, nextStoryMode, storyGuideEntries, useLayoutWidth } = await import(dataModule(rewriteDesktopImports(source)))

// Tests drive the mocks through globals; reset them all after every test so a
// failing assertion cannot leak state into the next one.
afterEach(() => {
  for (const name of ['forcedMode', 'guideQuery', 'lastQueryOptions', 'lastState', 'effectCleanup', 'document', 'window', 'ResizeObserver']) {
    delete globalThis[name]
  }
})

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

test('the measured width ignores a hidden (zero-width) container and detaches on cleanup', () => {
  let observed = null
  let disconnected = false
  let notify = null
  globalThis.ResizeObserver = class {
    constructor(callback) { notify = callback }
    observe(node) { observed = node }
    disconnect() { disconnected = true }
  }
  const node = { clientWidth: 900 }
  useLayoutWidth(node)
  assert.equal(observed, node)
  assert.equal(globalThis.lastState, 900)

  node.clientWidth = 0
  notify()
  assert.equal(globalThis.lastState, 900)
  node.clientWidth = 640
  notify()
  assert.equal(globalThis.lastState, 640)

  globalThis.effectCleanup()
  assert.equal(disconnected, true)

  observed = null
  useLayoutWidth(null)
  assert.equal(observed, null)
})

test('without ResizeObserver the width follows window resize and the listener is removed', () => {
  const listeners = new Map()
  globalThis.window = {
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: (name, fn) => { if (listeners.get(name) === fn) listeners.delete(name) }
  }
  const node = { clientWidth: 900 }
  useLayoutWidth(node)
  assert.equal(globalThis.lastState, 900)

  node.clientWidth = 0
  listeners.get('resize')()
  assert.equal(globalThis.lastState, 900)
  node.clientWidth = 700
  listeners.get('resize')()
  assert.equal(globalThis.lastState, 700)

  globalThis.effectCleanup()
  assert.equal(listeners.has('resize'), false)
})

test('arrow keys, Home and End move between the page modes', () => {
  assert.equal(nextStoryMode('story', 'ArrowRight'), 'guide')
  assert.equal(nextStoryMode('guide', 'ArrowRight'), 'story')
  assert.equal(nextStoryMode('story', 'ArrowLeft'), 'guide')
  assert.equal(nextStoryMode('guide', 'Home'), 'story')
  assert.equal(nextStoryMode('story', 'End'), 'guide')
  assert.equal(nextStoryMode('story', 'a'), null)
})

test('a query that has neither data nor an error yet (paused) still reads as loading', () => {
  globalThis.guideQuery = {}
  assert.equal(StoryGuide({}).props.children, 'guide.loading')
})

test('a query that succeeded with an empty body shows the empty state, not loading', () => {
  globalThis.guideQuery = { status: 'success', data: null }
  assert.equal(StoryGuide({}).props.children, 'guide.empty')
  globalThis.guideQuery = { status: 'success' }
  assert.equal(StoryGuide({}).props.children, 'guide.empty')
})

test('the guide query is scoped to the connection and profile', () => {
  globalThis.guideQuery = { data: guide }
  StoryGuide({})
  assert.deepEqual(globalThis.lastQueryOptions.queryKey, ['story-construction', 'guide', 'p1', 'c1'])
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
})

test('the page shows the Story workspace by default and keeps it mounted under the Guide', () => {
  const story = StoryPage({})
  const tabs = flat(story).filter(node => node.props?.role === 'tab')
  assert.deepEqual(tabs.map(tab => tab.props.children), ['page.modeStory', 'page.modeGuide'])
  assert.deepEqual(tabs.map(tab => tab.props['aria-selected']), [true, false])
  const pane = story.props.children[1]
  assert.equal(pane.props.style, undefined)
  const hiddenGuidePanel = story.props.children[2]
  assert.equal(hiddenGuidePanel.props.id, 'hermes-story-panel-guide')
  assert.deepEqual(hiddenGuidePanel.props.style, { display: 'none' })
  assert.equal(hiddenGuidePanel.props.children, null)
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
  assert.equal(guidePanel.props.style, undefined)
  assert.equal(typeof guidePanel.props.children.type, 'function')
})

test('arrow keys on a tab prevent the default and focus the newly selected tab', () => {
  const focused = []
  globalThis.document = { getElementById: id => ({ focus: () => focused.push(id) }) }
  const [storyTab] = flat(StoryPage({})).filter(node => node.props?.role === 'tab')

  let prevented = 0
  storyTab.props.onKeyDown({ key: 'ArrowRight', preventDefault: () => { prevented += 1 } })
  assert.equal(prevented, 1)
  assert.deepEqual(focused, ['hermes-story-tab-guide'])
  assert.equal(globalThis.lastState, 'guide')

  storyTab.props.onKeyDown({ key: 'a', preventDefault: () => { prevented += 1 } })
  assert.equal(prevented, 1)
  assert.equal(focused.length, 1)
})
