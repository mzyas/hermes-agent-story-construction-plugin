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
  notifyAgentOfApproval,
  proposalApprovalMessage,
  proposalErrorNote,
  proposalPollInterval,
  storyDraftKey,
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
    draftStore: { current: new Map() },
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

test('the approval message is fixed wording that names the proposal', () => {
  assert.equal(proposalApprovalMessage({ id: 'abc123' }, t), 'proposal.approvalMessage:abc123')
})

test('server errors become whitelisted wording and never raw text', () => {
  const http = detail => new Error(`HTTP 409: ${JSON.stringify({ detail })}`)
  assert.deepEqual(proposalErrorNote(http({ code: 'conflict', edit: 1 })), { key: 'proposal.conflictAt', args: [2] })
  assert.deepEqual(proposalErrorNote(http({ code: 'conflict' })), { key: 'proposal.conflict', args: [] })
  assert.equal(proposalErrorNote(http({ code: 'version_changed' })).key, 'proposal.versionChanged')
  assert.equal(proposalErrorNote(http({ code: 'frontmatter_not_allowed' })).key, 'proposal.frontmatter')
  assert.equal(proposalErrorNote(http({ code: 'invalid_selection' })).key, 'proposal.nothingSelected')
  assert.equal(proposalErrorNote(http({ code: 'chapter_changed' })).key, 'proposal.undoChanged')
  assert.deepEqual(proposalErrorNote(new Error('C:\\secret\\path exploded')), { key: 'proposal.failed', args: [] })
})

function notifyHarness({ active = { sessions: [] }, resumeFails = false, submitFails = false } = {}) {
  const calls = []
  return {
    calls,
    options: {
      proposal,
      profile: 'writer',
      connectionId: 'local',
      text: 'approved',
      profileRoutes: async () => [route],
      requestProfile: async (_route, method, params) => {
        calls.push([method, params])
        if (method === 'session.active_list') return active
        if (method === 'session.resume') {
          if (resumeFails) throw new Error('gone')
          return { session_id: 'runtime-9' }
        }
        if (method === 'prompt.submit' && submitFails) throw new Error('busy')
        return {}
      }
    }
  }
}

test('the Agent is told through its live session when there is one', async () => {
  const { calls, options } = notifyHarness({
    active: { sessions: [{ id: 'rt-1', session_key: 'other' }, { id: 'rt-2', session_key: 'stored-1' }] }
  })

  assert.deepEqual(await notifyAgentOfApproval(options), { sent: true })
  assert.deepEqual(calls.at(-1), ['prompt.submit', { session_id: 'rt-2', text: 'approved' }])
  assert.equal(calls.some(call => call[0] === 'session.resume'), false)
})

test('a session that is not live is resumed first', async () => {
  const { calls, options } = notifyHarness()

  assert.deepEqual(await notifyAgentOfApproval(options), { sent: true })
  assert.deepEqual(calls.map(call => call[0]), ['session.active_list', 'session.resume', 'prompt.submit'])
  assert.equal(calls.at(-1)[1].session_id, 'runtime-9')
})

test('a message that cannot be delivered is reported, not thrown', async () => {
  assert.deepEqual(await notifyAgentOfApproval(notifyHarness({ resumeFails: true }).options), { sent: false })
  assert.deepEqual(
    await notifyAgentOfApproval(notifyHarness({ active: { sessions: [{ id: 'rt-2', session_key: 'stored-1' }] }, submitFails: true }).options),
    { sent: false }
  )
  assert.deepEqual(await notifyAgentOfApproval({ ...notifyHarness().options, text: '' }), { sent: false })
  assert.deepEqual(await notifyAgentOfApproval({ ...notifyHarness().options, proposal: { id: 'x' } }), { sent: false })
})

test('every edit is a card with its diff and a checkbox', () => {
  const tree = review()

  const checkboxes = find(tree, node => node.type === 'input' && node.props.type === 'checkbox')
  assert.equal(checkboxes.length, 2)
  assert.ok(checkboxes.every(node => node.props.checked === true))
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

test('an approved proposal shows the time left and a way to withdraw', () => {
  const soon = new Date(Date.now() + 5 * 60_000).toISOString()
  const tree = review({ status: 'approved', approval: { mode: 'edits', selected: [1], expires_at: soon } })

  assert.match(textOf(tree), /proposal\.approvedLeft:[45]/)
  assert.ok(find(tree, node => node.type === 'button' && textOf(node) === 'proposal.revoke').length === 1)
  const boxes = find(tree, node => node.type === 'input' && node.props.type === 'checkbox')
  assert.deepEqual(boxes.map(node => node.props.checked), [false, true])
  assert.equal(find(review(), node => node.type === 'button' && textOf(node) === 'proposal.revoke').length, 0)
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

test('approving sends the selected edits for this project and scope, then refreshes', async () => {
  const { calls, dispose } = bindRest()
  let refreshed = 0
  try {
    await button(review({}, { onChanged: async () => { refreshed += 1 } }), 'proposal.approve').props.onClick()
  } finally {
    dispose()
  }

  assert.deepEqual(calls, [[
    '/projects/novel/proposals/abc123/approve',
    { method: 'POST', body: { profile: 'writer', connection_id: 'local', selected: [0, 1] } }
  ]])
  assert.equal(refreshed, 1)
})

test('an unsaved draft of the same chapter stops the approval', async () => {
  const { calls, dispose } = bindRest()
  const key = storyDraftKey({
    connectionId: 'local', profile: 'writer', sessionId: 'stored-1', projectId: 'novel', chapterId: 'novel:chapter-1'
  })
  try {
    await button(review({}, { draftStore: { current: new Map([[key, 'unsaved words']]) } }), 'proposal.approve').props.onClick()
  } finally {
    dispose()
  }

  assert.deepEqual(calls, [])
})

test('a draft of another chapter does not stop the approval', async () => {
  const { calls, dispose } = bindRest()
  const key = storyDraftKey({
    connectionId: 'local', profile: 'writer', sessionId: 'stored-1', projectId: 'novel', chapterId: 'novel:chapter-2'
  })
  try {
    await button(review({}, { draftStore: { current: new Map([[key, 'unsaved words']]) } }), 'proposal.approve').props.onClick()
  } finally {
    dispose()
  }

  assert.equal(calls.length, 1)
})

test('discarding and withdrawing call their own endpoints', async () => {
  const { calls, dispose } = bindRest()
  let closed = 0
  try {
    await button(review({}, { onClose: () => { closed += 1 } }), 'proposal.discard').props.onClick()
    const soon = new Date(Date.now() + 60_000).toISOString()
    await button(review({ status: 'approved', approval: { mode: 'edits', selected: [0], expires_at: soon } }), 'proposal.revoke').props.onClick()
  } finally {
    dispose()
  }

  assert.deepEqual(calls.map(call => [call[1].method, call[0]]), [
    ['DELETE', '/projects/novel/proposals/abc123?profile=writer&connection_id=local'],
    ['POST', '/projects/novel/proposals/abc123/revoke']
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

test('only chapters can hold an unsaved draft that blocks an approval', async () => {
  const { calls, dispose } = bindRest()
  const key = storyDraftKey({
    connectionId: 'local', profile: 'writer', sessionId: 'stored-1', projectId: 'novel', chapterId: 'novel:character-1'
  })
  try {
    await button(review(character, { draftStore: { current: new Map([[key, 'unsaved words']]) } }), 'proposal.approve').props.onClick()
  } finally {
    dispose()
  }

  assert.equal(calls.length, 1)
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
