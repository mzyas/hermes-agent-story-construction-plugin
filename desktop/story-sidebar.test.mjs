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
  export const usePluginI18n = () => key => key
  export const useQuery = () => ({})
  export const useValue = () => 'default'
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
const { buildChapterOutline, buildProjectTree, recordTypeOf, StorySidebar } = await import(
  dataModule(rewriteDesktopImports(source))
)

// Components are plain functions here: expand them into the element tree they render.
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

const t = key => key
const payload = {
  project: { id: 'p1', name: 'Novel' },
  world_info: { id: 'w1', name: 'World' },
  characters: [{ id: 'c1', name: 'Hero' }],
  notes: [{ id: 'n1', title: 'Reference' }],
  volumes: [{ id: 'v1', title: 'Volume I' }, { id: 'v2', title: 'Volume II' }],
  chapters: [
    { id: 'ch1', volume_id: 'v1', title: 'Opening' },
    { id: 'ch2', volume_id: 'v1', title: 'Rising' },
    { id: 'ch3', volume_id: 'gone', title: 'Orphan' }
  ]
}

test('chapters are grouped under their volume in volume order', () => {
  const outline = buildChapterOutline(payload.volumes, payload.chapters, t)

  assert.deepEqual(outline.map(group => group.volume.id), ['v1', 'v2', ''])
  assert.deepEqual(outline[0].chapters.map(chapter => chapter.id), ['ch1', 'ch2'])
  assert.deepEqual(outline[1].chapters, [])
})

test('a chapter whose volume is missing stays visible in a trailing group', () => {
  const outline = buildChapterOutline(payload.volumes, payload.chapters, t)

  assert.equal(outline.at(-1).volume.title, 'tree.unassignedVolume')
  assert.deepEqual(outline.at(-1).chapters.map(chapter => chapter.id), ['ch3'])
  assert.equal(buildChapterOutline(payload.volumes, [], t).length, 2)
})

test('the project tree carries the outline alongside the existing branches', () => {
  const tree = buildProjectTree(payload, t)

  assert.equal(tree.outline.length, 3)
  assert.equal(tree.branches.map(branch => branch.id).join(','), 'project,worldInfo,characters,notes,volumes,chapters')
})

test('the chapters tab lists volumes with chapter counts and marks the open chapter', () => {
  const opened = []
  const rendered = expand(StorySidebar({
    tree: buildProjectTree(payload, t),
    tab: 'chapters',
    selectedChapterId: 'ch2',
    onOpenChapter: id => opened.push(id),
    t
  }))

  const summaries = find(rendered, node => node.type === 'summary').map(textOf)
  assert.deepEqual(summaries, ['Volume I2', 'Volume II0', 'tree.unassignedVolume1'])
  const chapterButtons = find(rendered, node => node.type === 'button' && node.props.onClick && !node.props.role)
  assert.deepEqual(chapterButtons.map(textOf), ['Opening', 'Rising', 'Orphan'])
  assert.deepEqual(chapterButtons.map(node => node.props['aria-current']), [undefined, 'true', undefined])
  chapterButtons[0].props.onClick()
  assert.deepEqual(opened, ['ch1'])
})

test('the notes tab shows world info, characters, and notes but not volumes or chapters', () => {
  const rendered = expand(StorySidebar({ tree: buildProjectTree(payload, t), tab: 'notes', t }))

  const labels = find(rendered, node => node.type === 'summary').map(textOf)
  assert.deepEqual(labels, ['tree.worldInfo', 'tree.characters', 'tree.notes'])
})

test('the two tabs report which one was picked', () => {
  const picked = []
  const rendered = expand(StorySidebar({ tree: buildProjectTree(payload, t), tab: 'chapters', onTab: id => picked.push(id), t }))

  const tabs = find(rendered, node => node.props?.role === 'tab')
  assert.deepEqual(tabs.map(textOf), ['tree.tabChapters', 'tree.tabNotes'])
  assert.deepEqual(tabs.map(node => node.props['aria-selected']), [true, false])
  tabs[1].props.onClick()
  assert.deepEqual(picked, ['notes'])
})

test('without a project tree it asks for a project', () => {
  assert.equal(textOf(expand(StorySidebar({ tree: null, t }))), 'tree.selectProject')
})

// ----------------------------------------------------- reading characters, entries, notes
const recordPayload = {
  ...payload,
  world_info_entries: [{ id: 'we1', title: 'Clock tower' }],
  categories: [{ id: 'cat1', name: 'Ideas' }],
  notes: [{ id: 'n1', title: 'Spark', reference: false }]
}

function notesTabButtons(props = {}) {
  const rendered = expand(StorySidebar({ tree: buildProjectTree(recordPayload, t), tab: 'notes', t, ...props }))
  return find(rendered, node => node.type === 'button' && !node.props.role)
}

test('which rows open a record is decided by their branch and kind', () => {
  assert.equal(recordTypeOf('characters', { id: 'c1' }), 'character')
  assert.equal(recordTypeOf('worldInfo', { id: 'we1' }), 'world_entry')
  assert.equal(recordTypeOf('notes', { id: 'n1', kind: 'note' }), 'note')
  assert.equal(recordTypeOf('notes', { id: 'cat1', kind: 'category' }), null)
  assert.equal(recordTypeOf('project', { id: 'p1' }), null)
  assert.equal(recordTypeOf('chapters', { id: 'ch1' }), null)
})

test('world entries are listed one by one instead of one world-info container', () => {
  const branch = buildProjectTree(recordPayload, t).branches.find(item => item.id === 'worldInfo')

  assert.deepEqual(branch.children.map(child => child.id), ['we1'])
  assert.equal(branch.children[0].kind, 'world_entry')
})

test('clicking a world entry, character or note asks to open that record', () => {
  const opened = []
  const buttons = notesTabButtons({ onOpenRecord: record => opened.push(record) })

  assert.deepEqual(buttons.map(textOf), ['Clock tower', 'Hero', 'Ideas', 'Spark'])
  for (const button of buttons) button.props.onClick?.()
  assert.deepEqual(opened, [
    { type: 'world_entry', id: 'we1' },
    { type: 'character', id: 'c1' },
    { type: 'note', id: 'n1' }
  ])
})

test('a category row opens nothing and the open record is marked', () => {
  const buttons = notesTabButtons({ onOpenRecord: () => undefined, selectedRecord: { type: 'character', id: 'c1' } })
  const byText = Object.fromEntries(buttons.map(button => [textOf(button), button.props]))

  assert.equal(byText.Ideas.onClick, undefined)
  assert.equal(byText.Hero['aria-current'], 'true')
  assert.equal(byText.Spark['aria-current'], undefined)
  // The same id under another kind is a different record.
  const other = notesTabButtons({ onOpenRecord: () => undefined, selectedRecord: { type: 'note', id: 'c1' } })
  assert.equal(other.find(button => textOf(button) === 'Hero').props['aria-current'], undefined)
})

test('without a handler the rows stay inert rather than throwing', () => {
  assert.doesNotThrow(() => notesTabButtons().forEach(button => button.props.onClick?.()))
})
