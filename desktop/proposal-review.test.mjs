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
  export const useState = value => [value, () => {}]
`)
const jsxRuntimeUrl = dataModule(`
  export const jsx = (type, props, key) => ({ type, props, key })
  export const jsxs = (type, props, key) => ({ type, props, key })
`)
const importUrls = { '@hermes/plugin-sdk': sdkUrl, react: reactUrl, 'react/jsx-runtime': jsxRuntimeUrl }

function rewriteDesktopImports(source) {
  return source.replace(/(from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\2/g, (whole, prefix, quote, specifier) =>
    importUrls[specifier] ? `${prefix}${quote}${importUrls[specifier]}${quote}` : whole
  )
}

const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
const {
  ProposalReview,
  approvalMinutesLeft,
  bindWorkspaceApi,
  proposalErrorNote,
  proposalPollInterval,
  undoStoryAgentWrite
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

const t = (key, ...args) => (args.length ? `${key}:${args.join(',')}` : key)
const route = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }

const proposal = {
  id: 'abc123',
  status: 'pending',
  kind: 'edit',
  chapter_id: 'novel:chapter-1',
  chapter_title: '第一章',
  session_id: 'stored-1',
  base_version: 'v1',
  current_version: 'v1',
  edits: [
    { op: 'replace', old_text: '很大', new_text: '很急' },
    { op: 'append', new_text: '天亮了。' }
  ],
  previews: [
    {
      edit: 0,
      op: 'replace',
      regions: [{
        line: 3,
        old: '雨下得很大',
        new: '雨下得很急',
        inline: [{ op: 'equal', text: '雨下得很' }, { op: 'delete', text: '大' }, { op: 'insert', text: '急' }]
      }]
    },
    { edit: 1, op: 'append', regions: [{ line: 5, old: '', new: '天亮了。', inline: [{ op: 'insert', text: '天亮了。' }] }] }
  ],
  warnings: [{ edit: 1, kind: 'trailing_guidance', text: '希望你喜欢。' }],
  result_text: '雨下得很急\n\n天亮了。',
  approval: null
}

function review(overrides = {}, props = {}) {
  return expand(ProposalReview({
    proposal: { ...proposal, ...overrides },
    projectId: 'novel',
    profile: 'writer',
    connectionId: 'local',
    onClose: () => undefined,
    onChanged: async () => undefined,
    t,
    ...props
  }))
}

test('polling is quick while the Agent works and slow otherwise', () => {
  assert.equal(proposalPollInterval(true), 5_000)
  assert.equal(proposalPollInterval(false), 30_000)
})

test('the minutes left on an approval round up and never go negative', () => {
  const now = Date.parse('2026-10-02T12:00:00Z')
  const at = text => ({ approval: { expires_at: text } })
  assert.equal(approvalMinutesLeft(at('2026-10-02T12:14:10Z'), now), 15)
  assert.equal(approvalMinutesLeft(at('2026-10-02T12:00:30Z'), now), 1)
  assert.equal(approvalMinutesLeft(at('2026-10-02T11:00:00Z'), now), 0)
  assert.equal(approvalMinutesLeft({}, now), 0)
})

test('server errors become whitelisted wording and never raw text', () => {
  const http = detail => new Error(`HTTP 409: ${JSON.stringify({ detail })}`)
  assert.deepEqual(proposalErrorNote(http({ code: 'conflict', edit: 1 })), { key: 'proposal.conflictAt', args: [2] })
  assert.deepEqual(proposalErrorNote(http({ code: 'conflict' })), { key: 'proposal.conflict', args: [] })
  assert.equal(proposalErrorNote(http({ code: 'version_changed' })).key, 'proposal.versionChanged')
  assert.equal(proposalErrorNote(http({ code: 'frontmatter_not_allowed' })).key, 'proposal.frontmatter')
  assert.equal(proposalErrorNote(http({ code: 'chapter_changed' })).key, 'proposal.undoChanged')
  assert.deepEqual(proposalErrorNote(new Error('C:\\secret\\path exploded')), { key: 'proposal.failed', args: [] })
})

test('every edit is a card with its diff and no checkbox', () => {
  const tree = review()

  assert.equal(find(tree, node => node.type === 'input').length, 0)
  const deleted = find(tree, node => node.props?.className === 'hermes-story-diff-del')
  const inserted = find(tree, node => node.props?.className === 'hermes-story-diff-ins')
  assert.deepEqual(deleted.map(textOf), ['大'])
  assert.deepEqual(inserted.map(textOf), ['急', '天亮了。'])
  assert.match(textOf(tree), /proposal\.changeN:1,proposal\.op\.replace/)
  assert.match(textOf(tree), /proposal\.line:3/)
})

test('guidance warnings are shown to the person as alerts', () => {
  const alerts = find(review(), node => node.props?.role === 'alert')

  assert.equal(alerts.length, 1)
  assert.match(textOf(alerts[0]), /proposal\.warnTrailing/)
  assert.match(textOf(alerts[0]), /希望你喜欢。/)
})

test('the review only shows the change: no way to approve, edit or withdraw it here', () => {
  const soon = new Date(Date.now() + 5 * 60_000).toISOString()
  for (const tree of [review(), review({ status: 'approved', approval: { mode: 'edits', selected: [1], expires_at: soon } })]) {
    const labels = find(tree, node => node.type === 'button').map(textOf)
    assert.deepEqual(labels, ['proposal.close', 'proposal.discard'])
    assert.equal(find(tree, node => node.type === 'textarea').length, 0)
  }
})

test('a waiting proposal points to the chat for approval', () => {
  assert.match(textOf(review()), /proposal\.chatHint/)
})

function bindRest() {
  const calls = []
  const dispose = bindWorkspaceApi(async (path, options) => {
    calls.push([path, options])
    return {}
  })
  return { calls, dispose }
}

function button(tree, label) {
  return find(tree, node => node.type === 'button' && textOf(node) === label)[0]
}

test('discarding calls its endpoint and closes the review', async () => {
  const { calls, dispose } = bindRest()
  let closed = 0
  try {
    await button(review({}, { onClose: () => { closed += 1 } }), 'proposal.discard').props.onClick()
  } finally {
    dispose()
  }

  assert.deepEqual(calls.map(call => [call[1].method, call[0]]), [
    ['DELETE', '/projects/novel/proposals/abc123?profile=writer&connection_id=local']
  ])
  assert.equal(closed, 1)
})


// ------------------------------------------------ characters, entries and notes
const character = {
  ...proposal,
  chapter_id: undefined,
  chapter_title: undefined,
  target_type: 'character',
  target_id: 'novel:character-1',
  target_title: '林远'
}

test('the heading names the kind of record and its title', () => {
  assert.match(textOf(review()), /proposal\.editRecord:proposal\.kind\.chapter,第一章/)
  assert.match(textOf(review(character)), /proposal\.editRecord:proposal\.kind\.character,林远/)
  const created = review({
    ...character, kind: 'new_record', target_type: 'note', target_title: '灵感', title: '灵感', edits: [], previews: [], warnings: []
  })
  assert.match(textOf(created), /proposal\.newRecord:proposal\.kind\.note,灵感/)
  const newChapter = review({ kind: 'new_chapter', edits: [], previews: [], warnings: [] })
  assert.match(textOf(newChapter), /proposal\.newRecord:proposal\.kind\.chapter,第一章/)
})

test('a name already in use is an alert without a change number', () => {
  const alerts = find(
    review({ ...character, kind: 'new_record', edits: [], previews: [], warnings: [{ edit: 0, kind: 'name_in_use', text: 'novel:character-1' }] }),
    node => node.props?.role === 'alert'
  )

  assert.equal(alerts.length, 1)
  assert.match(textOf(alerts[0]), /proposal\.warnNameInUse/)
  assert.doesNotMatch(textOf(alerts[0]), /changeN/)
  assert.match(textOf(alerts[0]), /novel:character-1/)
})

test('undoing a write says which kind of record it was', async () => {
  const { calls, dispose } = bindRest()
  try {
    await undoStoryAgentWrite('novel', 'novel:character-1', { profile: 'writer', connectionId: 'local', targetType: 'character' })
    await undoStoryAgentWrite('novel', 'novel:chapter-1', { profile: 'writer', connectionId: 'local' })
  } finally {
    dispose()
  }

  assert.deepEqual(calls, [
    ['/projects/novel/chapters/novel%3Acharacter-1/undo', { method: 'POST', body: { profile: 'writer', connection_id: 'local', target_type: 'character' } }],
    ['/projects/novel/chapters/novel%3Achapter-1/undo', { method: 'POST', body: { profile: 'writer', connection_id: 'local' } }]
  ])
})


// ------------------------------------------------------------ renaming and deleting
const renaming = {
  ...character,
  kind: 'rename',
  new_title: '江昼',
  edits: [],
  previews: [],
  warnings: [],
  result_text: ''
}
const deleting = { ...renaming, kind: 'delete', new_title: null }

test('a rename or a deletion is headed by what it does, with no changes to pick', () => {
  const renamed = review(renaming)
  const deleted = review(deleting)

  assert.match(textOf(renamed), /proposal\.renameRecord:proposal\.kind\.character,林远,江昼/)
  assert.match(textOf(deleted), /proposal\.deleteRecord:proposal\.kind\.character,林远/)
  assert.equal(find(renamed, node => node.props?.type === 'checkbox').length, 0)
  assert.match(textOf(renamed), /proposal\.renameHint/)
  assert.match(textOf(deleted), /proposal\.deleteHint/)
  assert.equal(find(deleted, node => String(node.props?.className || '').includes('hermes-story-danger') && textOf(node) === 'proposal.deleteHint').length, 1)
})

test('an action on a record that changed since is marked as stale', () => {
  const changed = review({ ...renaming, current_version: 'v2' })
  const same = review(renaming)

  assert.ok(find(changed, node => textOf(node) === 'proposal.stale').length >= 1)
  assert.equal(find(same, node => textOf(node) === 'proposal.stale').length, 0)
})
