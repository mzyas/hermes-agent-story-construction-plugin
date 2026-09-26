import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
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
  export const useRef = value => ({ current: value })
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

async function loadPlugin() {
  const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
  return import(dataModule(rewriteDesktopImports(source)))
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

test('preserves a later draft when a successful refresh returns', async () => {
  const { runChapterSave, shouldHydrateChapterDraft } = await loadPlugin()
  const save = deferred()
  const refresh = deferred()
  let draftRevision = 4
  const events = []

  const completion = runChapterSave({
    save: () => save.promise,
    refetch: () => refresh.promise,
    isActive: () => true,
    onSaved: () => events.push('saved'),
    onFailed: error => events.push(error.message),
    timeoutMs: 1000
  })

  save.resolve()
  draftRevision = 5
  refresh.resolve({ data: { chapter: { content: 'server content', version: 'v2' } } })
  await completion

  assert.deepEqual(events, ['saved'])
  const draft = 'later draft'
  const hydrated = shouldHydrateChapterDraft({
    saveSnapshot: { scope: 'scope-a', revision: 4 },
    scope: 'scope-a',
    draftRevision
  })
  assert.equal(hydrated, false)
  assert.equal(hydrated ? 'server content' : draft, 'later draft')
})

test('ignores a save promise after the editor scope changes', async () => {
  const { runChapterSave } = await loadPlugin()
  const save = deferred()
  let scope = 'scope-a'
  let refreshCalls = 0
  const events = []

  const completion = runChapterSave({
    save: () => save.promise,
    refetch: () => {
      refreshCalls += 1
      return Promise.resolve()
    },
    isActive: () => scope === 'scope-a',
    onSaved: () => events.push('saved'),
    onFailed: error => events.push(error.message),
    timeoutMs: 1000
  })

  scope = 'scope-b'
  save.resolve()
  await completion

  assert.equal(refreshCalls, 0)
  assert.deepEqual(events, [])
})

test('reports a resolved refetch error and releases the save lifecycle', async () => {
  const { runChapterSave } = await loadPlugin()
  const save = deferred()
  const events = []

  const completion = runChapterSave({
    save: () => save.promise,
    refetch: () => Promise.resolve({ isError: true, error: new Error('refresh failed') }),
    isActive: () => true,
    onSaved: () => events.push('saved'),
    onFailed: error => events.push(error.message),
    timeoutMs: 1000
  })

  save.resolve()
  await completion

  assert.deepEqual(events, ['refresh failed'])
})

test('times out an unresolved save instead of leaving the editor blocked', async () => {
  const { runChapterSave } = await loadPlugin()
  const events = []

  await runChapterSave({
    save: () => new Promise(() => {}),
    refetch: () => Promise.resolve(),
    isActive: () => true,
    onSaved: () => events.push('saved'),
    onFailed: error => events.push(error.message),
    timeoutMs: 5
  })

  assert.deepEqual(events, ['save request timed out'])
})

test('keys retained drafts by five-part scope and gates plugin-initiated leaves', async () => {
  const { canLeaveStoryWorkspace, retainStoryDraft, storyDraftKey } = await loadPlugin()

  const scopeA = { connectionId: 'local', profile: 'writer', sessionId: 's1', projectId: 'p1', chapterId: 'c1' }
  const keyA = storyDraftKey(scopeA)
  // A different Profile, connection, session, project or chapter never shares
  // one draft entry; equal five-part scopes always match.
  assert.equal(keyA, storyDraftKey({ ...scopeA }))
  for (const changed of [
    { profile: 'editor' },
    { connectionId: 'remote-1' },
    { sessionId: 's2' },
    { projectId: 'p2' },
    { chapterId: 'c2' }
  ]) {
    assert.notEqual(keyA, storyDraftKey({ ...scopeA, ...changed }), `scope mix across ${Object.keys(changed)}`)
  }

  // A draft equal to its baseline is clean and drops its entry; anything else
  // is retained, and clearing one scope never touches another.
  let store = retainStoryDraft(new Map(), keyA, 'server content', 'server content')
  assert.equal(store.has(keyA), false)
  store = retainStoryDraft(store, keyA, 'unsaved draft', 'server content')
  assert.equal(store.get(keyA), 'unsaved draft')
  const keyB = storyDraftKey({ ...scopeA, chapterId: 'c2' })
  store = retainStoryDraft(store, keyB, 'other chapter draft', 'other server')
  assert.equal(store.size, 2)
  store = retainStoryDraft(store, keyA, 'server content', 'server content')
  assert.equal(store.has(keyA), false)
  assert.equal(store.get(keyB), 'other chapter draft')
  // Retaining returns a fresh Map so React state updates stay predictable.
  assert.equal(store instanceof Map, true)

  // Plugin-initiated leave: an in-flight save always blocks without asking; a
  // dirty draft needs an explicit confirmation; cancel keeps everything.
  let asked = 0
  const confirmLeave = () => {
    asked += 1
    return false
  }
  assert.equal(canLeaveStoryWorkspace({ dirty: true, saving: true, confirmLeave }), false)
  assert.equal(asked, 0, 'saving must block without prompting')
  assert.equal(canLeaveStoryWorkspace({ dirty: true, saving: false, confirmLeave }), false)
  assert.equal(asked, 1, 'a dirty draft prompts for confirmation')
  assert.equal(canLeaveStoryWorkspace({ dirty: true, saving: false, confirmLeave: () => true }), true)
  assert.equal(canLeaveStoryWorkspace({ dirty: false, saving: false, confirmLeave }), true)
  assert.equal(canLeaveStoryWorkspace({ dirty: false, saving: true, confirmLeave: () => true }), false)
})

test('a deferred A save settles nothing after A→B→A and keeps A\'s later draft', async () => {
  const {
    retainStoryDraft,
    runChapterSave,
    storyChapterSaveGate,
    storyDraftKey
  } = await loadPlugin()

  const keyA = storyDraftKey({ connectionId: 'local', profile: 'writer', sessionId: 's1', projectId: 'p1', chapterId: 'c1' })
  const keyB = storyDraftKey({ connectionId: 'local', profile: 'writer', sessionId: 's1', projectId: 'p2', chapterId: 'c9' })
  const scopeA = 'writer:local:s1:p1:c1'
  const scopeB = 'writer:local:s1:p2:c9'
  const gate = storyChapterSaveGate()
  const save = deferred()
  const events = []
  let currentScope = scopeA
  let refetchCalls = 0
  let drafts = new Map()

  // A's chapter is dirty and its save is issued but answers late.
  drafts = retainStoryDraft(drafts, keyA, 'draft v1', 'server v1')
  const token = gate.begin(scopeA)
  const completion = runChapterSave({
    save: () => save.promise,
    refetch: () => {
      refetchCalls += 1
      return Promise.resolve({ data: { chapter: { content: 'server v2', version: 'v2' } } })
    },
    isActive: () => gate.isActive(token, currentScope),
    onSaved: () => events.push('saved'),
    onFailed: error => events.push(error.message),
    timeoutMs: 1000
  })

  // External switch to B: the editor tears the save gate down and B keeps its
  // own scoped draft.
  currentScope = scopeB
  gate.reset()
  drafts = retainStoryDraft(drafts, keyB, 'b draft', 'b server')

  // Back to A: the scope string matches the original save again, and the user
  // types a LATER draft before the old save answers.
  currentScope = scopeA
  drafts = retainStoryDraft(drafts, keyA, 'draft v2 later', 'server v1')

  save.resolve()
  await completion

  // The dropped token cannot re-claim the gate just because the scope string
  // matches again — a naive `scope === scopeA` check would wrongly settle here.
  assert.equal(gate.isActive(token, scopeA), false)
  assert.deepEqual(events, [], 'the late save must not settle the current view')
  assert.equal(refetchCalls, 0, 'the late save must not refetch into the current view')
  assert.equal(drafts.get(keyA), 'draft v2 later', "A's later draft must survive the late save")
  assert.equal(drafts.get(keyB), 'b draft', "B's draft must not be overwritten")
  assert.equal(gate.isPending(scopeA), false, 'the editor can save again after the stale completion')
})

test('save success rebaselines to the saved content and keeps reverted edits unsaved', async () => {
  const {
    canLeaveStoryWorkspace,
    retainStoryDraft,
    runChapterSave,
    storyDraftAfterSave,
    storyDraftKey
  } = await loadPlugin()

  const key = storyDraftKey({ connectionId: 'local', profile: 'writer', sessionId: 's1', projectId: 'p1', chapterId: 'c1' })
  // Scenario: chapter holds original text A, the user submits B, then edits
  // back to A while the save is still in flight. When B lands, A must still be
  // unsaved — the baseline becomes the confirmed content B, not the old A.
  let baseline = 'A'
  let draft = 'B'
  let drafts = retainStoryDraft(new Map(), key, draft, baseline)
  const save = deferred()
  const savedContent = draft
  const completion = runChapterSave({
    save: () => save.promise,
    refetch: () => Promise.resolve({ data: { chapter: { content: 'B', version: 'v2' } } }),
    isActive: () => true,
    onSaved: () => {
      const settled = storyDraftAfterSave({ draft, savedContent })
      baseline = settled.baseline
      drafts = retainStoryDraft(drafts, key, settled.draft, settled.baseline)
    },
    onFailed: error => {
      throw error
    },
    timeoutMs: 1000
  })

  draft = 'A'
  drafts = retainStoryDraft(drafts, key, draft, baseline)
  save.resolve()
  await completion

  assert.equal(draft, 'A', 'the edit made during the save must not be overwritten')
  assert.equal(baseline, 'B', 'the baseline is the content this save confirmed')
  assert.equal(drafts.get(key), 'A', 'A stays retained as unsaved against the new baseline')
  assert.equal(
    canLeaveStoryWorkspace({ dirty: drafts.has(key), saving: false, confirmLeave: () => false }),
    false,
    'leaving with A on screen must prompt'
  )

  // An unchanged on-screen draft equals the saved content and becomes clean;
  // a newer edit made during the save stays dirty beside the new baseline.
  const clean = storyDraftAfterSave({ draft: 'B', savedContent: 'B' })
  assert.equal(clean.dirty, false)
  assert.equal(retainStoryDraft(drafts, key, clean.draft, clean.baseline).has(key), false)
  const later = storyDraftAfterSave({ draft: 'C', savedContent: 'B' })
  assert.equal(later.draft, 'C')
  assert.equal(later.baseline, 'B')
  assert.equal(later.dirty, true)
  assert.equal(retainStoryDraft(drafts, key, later.draft, later.baseline).get(key), 'C')
})

test('rebases to the persisted content when the server normalizes the submitted text', async () => {
  const {
    canLeaveStoryWorkspace,
    retainStoryDraft,
    runChapterSave,
    shouldHydrateChapterDraft,
    storyDraftAfterSave,
    storyDraftKey
  } = await loadPlugin()

  const key = storyDraftKey({ connectionId: 'local', profile: 'writer', sessionId: 's1', projectId: 'p1', chapterId: 'c1' })
  // Scenario: the user submits 'B\n' but the server persists and returns 'B'.
  // The baseline becomes the persisted 'B'; the unpersisted '\n' difference
  // stays on screen and stays unsaved.
  let baseline = 'A'
  let draft = 'B\n'
  let drafts = retainStoryDraft(new Map(), key, draft, baseline)
  const save = deferred()
  let persistedSeen = null
  const completion = runChapterSave({
    save: () => save.promise,
    refetch: () => Promise.resolve({ data: { chapter: { content: 'B', version: 'v2' } } }),
    isActive: () => true,
    onSaved: persisted => {
      persistedSeen = persisted
      const settled = storyDraftAfterSave({ draft, savedContent: persisted })
      baseline = settled.baseline
      drafts = retainStoryDraft(drafts, key, settled.draft, settled.baseline)
    },
    onFailed: error => {
      throw error
    },
    timeoutMs: 1000
  })
  save.resolve()
  await completion

  assert.equal(persistedSeen, 'B', 'the success callback receives the persisted content')
  assert.equal(baseline, 'B', 'the baseline is what actually persisted, not the submitted bytes')
  assert.equal(draft, 'B\n', 'the unpersisted difference is never overwritten')
  assert.equal(drafts.get(key), 'B\n', 'the unpersisted difference is retained as unsaved')
  assert.equal(
    canLeaveStoryWorkspace({ dirty: drafts.has(key), saving: false, confirmLeave: () => false }),
    false,
    'leaving with the unpersisted difference must prompt'
  )
  // Even with no edits after submission (equal revisions), the save's own
  // refresh must not hydrate over the on-screen difference.
  assert.equal(
    shouldHydrateChapterDraft({ saveSnapshot: { scope: 'scope-a', revision: 3 }, scope: 'scope-a', draftRevision: 3 }),
    false
  )
})
