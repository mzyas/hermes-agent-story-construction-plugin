import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const pluginUrl = new URL('./plugin.js', import.meta.url)

function dataModule(source) {
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
}

// Unlike the other suites this SDK stub provides the context-menu components,
// as markers, so the wrapped structure can be inspected.
const sdkUrl = dataModule(`
  export const PANES_AREA = 'panes'
  export const PALETTE_AREA = 'palette'
  export const ROUTES_AREA = 'routes'
  export const SIDEBAR_NAV_AREA = 'sidebar.nav'
  export const host = { state: {} }
  export const usePluginI18n = () => key => key
  export const useQuery = () => ({})
  export const useValue = () => 'default'
  export const ContextMenu = 'ContextMenu'
  export const ContextMenuTrigger = 'ContextMenuTrigger'
  export const ContextMenuContent = 'ContextMenuContent'
  export const ContextMenuItem = 'ContextMenuItem'
`)
const reactUrl = dataModule(`
  export const useEffect = () => {}
  export const useState = value => [typeof value === 'function' ? value() : value, () => {}]
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
const {
  StorySidebar,
  buildProjectTree,
  bindWorkspaceApi,
  createStoryChapter,
  createStoryVolume,
  registerStoryMenuItem,
  storyMenuItemsFor
} = await import(dataModule(rewriteDesktopImports(source)))

function expand(node) {
  if (Array.isArray(node)) return node.map(expand)
  if (node && typeof node === 'object' && 'type' in node) {
    if (typeof node.type === 'function') return expand(node.type(node.props))
    return { ...node, props: { ...node.props, children: expand(node.props?.children) } }
  }
  return node
}

function find(node, predicate, found = []) {
  if (Array.isArray(node)) {
    node.forEach(child => find(child, predicate, found))
  } else if (node && typeof node === 'object' && 'type' in node) {
    if (predicate(node)) found.push(node)
    find(node.props?.children, predicate, found)
  }
  return found
}

function textOf(node) {
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (node && typeof node === 'object') return textOf(node.props?.children)
  return node == null ? '' : String(node)
}

// Translation that keeps its arguments visible.
const t = (key, ...args) => (args.length ? `${key}:${args.join(',')}` : key)
const payload = {
  project: { id: 'p1', name: 'Novel' },
  volumes: [{ id: 'v1', title: 'Volume I' }, { id: 'v2', title: 'Volume II' }],
  chapters: [
    { id: 'ch1', volume_id: 'v1', title: 'Opening' },
    { id: 'ch2', volume_id: 'v2', title: 'Rising' }
  ]
}
const tree = buildProjectTree(payload, t)

function sidebar(props = {}) {
  return expand(StorySidebar({ tree, tab: 'chapters', t, ...props }))
}

test('menu entries apply to the places they were registered for', () => {
  const context = { onCreate: () => undefined }

  assert.deepEqual(storyMenuItemsFor('volume', { volumeId: 'v1' }, context).map(item => item.id), ['story.newChapter', 'story.newVolume'])
  assert.deepEqual(storyMenuItemsFor('chapter', { chapterId: 'ch1', volumeId: 'v1' }, context).map(item => item.id), ['story.newChapter', 'story.newVolume'])
  assert.deepEqual(storyMenuItemsFor('sidebar', {}, context).map(item => item.id), ['story.newVolume'])
})

test('menu entries need a way to create and a volume to create in', () => {
  assert.deepEqual(storyMenuItemsFor('volume', { volumeId: 'v1' }, {}), [])
  assert.deepEqual(storyMenuItemsFor('volume', {}, { onCreate: () => undefined }).map(item => item.id), ['story.newVolume'])
})

test('running a menu entry asks to create in the right-clicked volume', () => {
  const calls = []
  const context = { onCreate: (...args) => calls.push(args) }

  storyMenuItemsFor('chapter', { chapterId: 'ch2', volumeId: 'v2' }, context)[0].run()
  storyMenuItemsFor('sidebar', {}, context)[0].run()

  assert.deepEqual(calls, [['chapter', 'v2'], ['volume']])
})

test('entries are disabled while a creation is in flight', () => {
  const items = storyMenuItemsFor('volume', { volumeId: 'v1' }, { onCreate: () => undefined, createBusy: true })

  assert.deepEqual(items.map(item => item.disabled), [true, true])
})

test('a later feature can add a menu entry and remove it again', () => {
  const calls = []
  const remove = registerStoryMenuItem({
    id: 'test.rename',
    kinds: ['chapter'],
    labelKey: 'tree.rename',
    order: 15,
    run: target => calls.push(target.chapterId)
  })

  const items = storyMenuItemsFor('chapter', { chapterId: 'ch1', volumeId: 'v1' }, { onCreate: () => undefined })
  assert.deepEqual(items.map(item => item.id), ['story.newChapter', 'test.rename', 'story.newVolume'])
  items[1].run()
  assert.deepEqual(calls, ['ch1'])

  remove()
  assert.equal(storyMenuItemsFor('chapter', { chapterId: 'ch1', volumeId: 'v1' }, { onCreate: () => undefined }).some(item => item.id === 'test.rename'), false)
})

test('volumes, chapters, and the empty area each get a right-click menu', () => {
  const rendered = sidebar({ onCreate: () => undefined })

  const menus = find(rendered, node => node.type === 'ContextMenu')
  // two volumes + two chapters + the empty area below the list
  assert.equal(menus.length, 5)
  const triggers = find(rendered, node => node.type === 'ContextMenuTrigger')
  assert.equal(triggers.length, 5)
  assert.equal(triggers.every(node => node.props.asChild === true), true)
  const labels = find(menus[0], node => node.type === 'ContextMenuItem').map(textOf)
  assert.deepEqual(labels, ['tree.newChapter', 'tree.newVolume'])
})

test('without a way to create there is no menu and no toolbar', () => {
  const rendered = sidebar()

  assert.equal(find(rendered, node => node.type === 'ContextMenu').length, 0)
  assert.equal(find(rendered, node => node.type === 'button' && textOf(node) === 'tree.newVolume').length, 0)
})

test('the toolbar creates a volume, or a chapter in the open chapter\'s volume', () => {
  const calls = []
  const onCreate = (...args) => calls.push(args)
  const buttons = rendered => find(rendered, node => node.type === 'button' && ['tree.newVolume', 'tree.newChapter'].includes(textOf(node)))

  const withSelection = buttons(sidebar({ onCreate, selectedChapterId: 'ch1' }))
  withSelection[0].props.onClick()
  withSelection[1].props.onClick()
  const withoutSelection = buttons(sidebar({ onCreate }))
  withoutSelection[1].props.onClick()

  assert.deepEqual(calls, [['volume'], ['chapter', 'v1'], ['chapter', 'v2']])
})

test('a project without volumes cannot offer a new chapter', () => {
  const empty = buildProjectTree({ project: { id: 'p1', name: 'Novel' }, volumes: [], chapters: [] }, t)
  const rendered = expand(StorySidebar({ tree: empty, tab: 'chapters', onCreate: () => undefined, t }))

  const newChapter = find(rendered, node => node.type === 'button' && textOf(node) === 'tree.newChapter')[0]
  assert.equal(newChapter.props.disabled, true)
})

test('creating a volume shows one input row with the next volume number', () => {
  const rendered = sidebar({ onCreate: () => undefined, creating: { kind: 'volume', volumeId: null } })

  const inputs = find(rendered, node => node.type === 'input')
  assert.equal(inputs.length, 1)
  assert.equal(inputs[0].props.value, 'tree.defaultVolumeTitle:3')
  assert.equal(inputs[0].props.placeholder, 'tree.volumeTitlePlaceholder')
})

test('creating a chapter shows the input inside that volume only', () => {
  const rendered = sidebar({ onCreate: () => undefined, creating: { kind: 'chapter', volumeId: 'v2' } })

  const details = find(rendered, node => node.type === 'details')
  const holding = details.filter(group => find(group, node => node.type === 'input').length)
  assert.equal(holding.length, 1)
  assert.match(textOf(find(holding[0], node => node.type === 'summary')), /Volume II/)
  assert.equal(find(rendered, node => node.type === 'input')[0].props.value, 'tree.defaultChapterTitle:3')
})

function createRow(overrides = {}) {
  const calls = { submit: [], cancel: 0 }
  const rendered = expand(StorySidebar({
    tree,
    tab: 'chapters',
    t,
    onCreate: () => undefined,
    creating: { kind: 'volume', volumeId: null },
    onSubmitCreate: title => calls.submit.push(title),
    onCancelCreate: () => {
      calls.cancel += 1
    },
    ...overrides
  }))
  return { calls, rendered, input: find(rendered, node => node.type === 'input')[0] }
}

function key(name, extra = {}) {
  let prevented = false
  return { event: { key: name, preventDefault: () => { prevented = true }, ...extra }, wasPrevented: () => prevented }
}

test('Enter creates with the trimmed title and Escape cancels', () => {
  const { calls, input } = createRow()

  const enter = key('Enter')
  input.props.onKeyDown(enter.event)
  const escape = key('Escape')
  input.props.onKeyDown(escape.event)

  assert.deepEqual(calls.submit, ['tree.defaultVolumeTitle:3'])
  assert.equal(calls.cancel, 1)
  assert.equal(enter.wasPrevented() && escape.wasPrevented(), true)
})

test('Enter that confirms an IME candidate does not create anything', () => {
  const { calls, input } = createRow()

  input.props.onKeyDown(key('Enter', { isComposing: true }).event)
  input.props.onKeyDown(key('Enter', { nativeEvent: { isComposing: true } }).event)

  assert.deepEqual(calls.submit, [])
})

test('the Create button is disabled while busy and cannot submit a second time', () => {
  const { calls, rendered, input } = createRow({ createBusy: true })

  const create = find(rendered, node => node.type === 'button' && textOf(node) === 'tree.creating')[0]
  assert.equal(create.props.disabled, true)
  assert.equal(input.props.disabled, true)
  input.props.onKeyDown(key('Enter').event)
  assert.deepEqual(calls.submit, [])
})

test('a failed creation keeps the row open and shows its message', () => {
  const { rendered } = createRow({ createError: 'tree.createFailed' })

  assert.equal(find(rendered, node => node.type === 'input').length, 1)
  assert.equal(find(rendered, node => textOf(node) === 'tree.createFailed').length > 0, true)
})

test('the REST helpers post to the volume and chapter routes with the id escaped', async () => {
  const calls = []
  const unbind = bindWorkspaceApi(async (path, options) => {
    calls.push([path, options])
    return {}
  })

  await createStoryVolume('p 1', { title: 'Two' })
  await createStoryChapter('p 1', 'v:1', { title: 'Opening' })
  unbind()

  assert.deepEqual(calls, [
    ['/projects/p%201/volumes', { method: 'POST', body: { title: 'Two' } }],
    ['/projects/p%201/volumes/v%3A1/chapters', { method: 'POST', body: { title: 'Opening' } }]
  ])
})
