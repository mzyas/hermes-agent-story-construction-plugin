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

async function loadPluginModule() {
  const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
  return import(dataModule(rewriteDesktopImports(source)))
}

test('gates story readiness on ready plus a matching locked_profile', async () => {
  const { storyReadiness } = await loadPluginModule()

  assert.deepEqual(storyReadiness(null, 'writer'), { ready: false, code: 'unavailable' })
  assert.deepEqual(storyReadiness(undefined, 'writer'), { ready: false, code: 'unavailable' })
  assert.deepEqual(storyReadiness({ ready: false, code: 'runtime_uninitialized' }, 'writer'), {
    ready: false, code: 'runtime_uninitialized'
  })
  assert.deepEqual(storyReadiness({ ready: false, code: 'configuration_incomplete' }, 'writer'), {
    ready: false, code: 'configuration_incomplete'
  })
  assert.deepEqual(storyReadiness({ ready: false, code: 'hermes_home_mismatch' }, 'writer'), {
    ready: false, code: 'hermes_home_mismatch'
  })
  assert.deepEqual(storyReadiness({ ready: false, code: 'vault_not_directory' }, 'writer'), {
    ready: false, code: 'vault_not_directory'
  })
  assert.deepEqual(storyReadiness({ ready: false, code: 'profile_not_selected' }, 'writer'), {
    ready: false, code: 'profile_not_selected'
  })
  assert.deepEqual(storyReadiness({ ready: false, code: 'agent_not_enabled' }, 'writer'), {
    ready: false, code: 'agent_not_enabled'
  })
  assert.deepEqual(storyReadiness({ ready: false, code: 'vault_unavailable' }, 'writer'), {
    ready: false, code: 'unavailable'
  })
  assert.deepEqual(storyReadiness({ ready: true, code: 'ready', locked_profile: 'writer' }, 'writer'), {
    ready: true, code: 'ready'
  })
  assert.deepEqual(storyReadiness({ ready: true, code: 'ready', locked_profile: 'editor' }, 'writer'), {
    ready: false, code: 'profile_mismatch'
  })
  assert.deepEqual(storyReadiness({ ready: true, code: 'ready', locked_profile: null }, 'writer'), {
    ready: false, code: 'profile_mismatch'
  })
})

test('formats diagnostics from whitelisted fields only', async () => {
  const { storyDiagnostic } = await loadPluginModule()

  assert.deepEqual(storyDiagnostic(null, { code: 'runtime_uninitialized' }), {
    httpStatus: null, code: 'runtime_uninitialized'
  })
  assert.deepEqual(storyDiagnostic({ status: 503 }, { code: 'vault_not_directory', message: 'ignored' }), {
    httpStatus: 503, code: 'vault_not_directory'
  })
  assert.deepEqual(storyDiagnostic({ statusCode: 422 }, null), {
    httpStatus: 422, code: null
  })
  assert.deepEqual(storyDiagnostic({ response: { status: 502 } }, { code: 'binding_state_invalid' }), {
    httpStatus: 502, code: null
  })
  assert.deepEqual(storyDiagnostic({ status: 200 }, { code: 'configuration_incomplete' }), {
    httpStatus: null, code: 'configuration_incomplete'
  })
  assert.deepEqual(storyDiagnostic({ status: 'not-a-status' }, null), {
    httpStatus: null, code: null
  })

  const leakyError = new Error(
    'Error invoking remote method \'/api\': 503: {"detail": {"vault_root": "C:\\\\Users\\\\me\\\\vault", "token": "sk-sentinel"}}'
  )
  const diagnostic = storyDiagnostic(leakyError, { code: 'leaked-server-code', message: 'SENTINEL_MESSAGE' })
  assert.deepEqual(diagnostic, { httpStatus: null, code: null })
  const rendered = JSON.stringify(diagnostic)
  assert.ok(!rendered.includes('SENTINEL'), 'diagnostic leaked raw error text')
  assert.ok(!/vault|token|sk-sentinel/i.test(rendered), 'diagnostic leaked Vault path or token')

  const setupError = Object.assign(new Error(
    `Error invoking remote method 'api': 422: ${JSON.stringify({
      detail: { code: 'configuration_incomplete', vault_root: 'PRIVATE_VAULT_PATH', token: 'PRIVATE_TOKEN' }
    })}`
  ), { statusCode: 422 })
  const setupDiagnostic = storyDiagnostic(setupError, null)
  assert.deepEqual(setupDiagnostic, { httpStatus: 422, code: 'configuration_incomplete' })
  assert.ok(!JSON.stringify(setupDiagnostic).includes('PRIVATE'))
})

test('serializes Story settings writes and leaves the newest Profile selected', async () => {
  const { bindWorkspaceApi, updateStorySettings } = await loadPluginModule()
  const calls = []
  let enterFirst
  let releaseFirst
  const firstEntered = new Promise(resolve => { enterFirst = resolve })
  const firstResponse = new Promise(resolve => { releaseFirst = resolve })
  const dispose = bindWorkspaceApi(async (path, options) => {
    calls.push({ path, options })
    if (calls.length === 1) {
      enterFirst()
      return firstResponse
    }
    return { ready: false }
  })

  try {
    const first = updateStorySettings('writer')
    await firstEntered
    const superseded = updateStorySettings('editor')
    const latest = updateStorySettings('writer', { vaultRoot: ' /mnt/story-vault ' })
    releaseFirst({ ready: false })
    const [, supersededResult] = await Promise.all([first, superseded, latest])

    assert.deepEqual(supersededResult, { superseded: true })
    assert.deepEqual(calls.map(({ path, options }) => [path, options.method, options.body]), [
      ['/settings', 'PUT', { profile: 'writer' }],
      ['/settings', 'PUT', { profile: 'writer', vault_root: '/mnt/story-vault' }]
    ])
  } finally {
    dispose()
  }

  const staleResult = await updateStorySettings('editor', { isCurrent: () => false })
  assert.deepEqual(staleResult, { superseded: true })
  assert.equal(calls.length, 2, 'out-of-scope settings write must be skipped')
})

test('focus refresh GETs a ready matching Profile without writing settings', async () => {
  const { refreshStoryProfileStatus } = await loadPluginModule()
  const calls = []
  const status = await refreshStoryProfileStatus('writer', {
    isCurrent: () => true,
    syncSettings: async () => { calls.push(['PUT']) },
    getStatus: async () => {
      calls.push(['GET'])
      return { ready: true, locked_profile: 'writer' }
    }
  })

  assert.deepEqual(calls, [['GET']])
  assert.deepEqual(status.status, { ready: true, locked_profile: 'writer' })
  assert.equal(status.wroteSettings, false)
})

test('refresh syncs a mismatched Profile once between two status reads', async () => {
  const { refreshStoryProfileStatus } = await loadPluginModule()
  const calls = []
  let reads = 0
  const result = await refreshStoryProfileStatus('writer', {
    isCurrent: () => true,
    syncSettings: async profile => { calls.push(['PUT', profile]); return { ok: true } },
    getStatus: async () => {
      calls.push(['GET'])
      reads += 1
      return reads === 1
        ? { ready: true, locked_profile: 'other' }
        : { ready: true, locked_profile: 'writer' }
    }
  })

  assert.deepEqual(calls, [['GET'], ['PUT', 'writer'], ['GET']])
  assert.deepEqual(result, {
    status: { ready: true, locked_profile: 'writer' },
    superseded: false,
    wroteSettings: true
  })
})

test('same-connection status decisions wait for an earlier Profile write to commit', async () => {
  const { bindWorkspaceApi, refreshStoryProfileStatus, updateStorySettings } = await loadPluginModule()
  const calls = []
  let selectedProfile = 'writer-b'
  let signalWriteStarted
  let releaseWrite
  const writeStarted = new Promise(resolve => { signalWriteStarted = resolve })
  const writeResponse = new Promise(resolve => { releaseWrite = resolve })
  const dispose = bindWorkspaceApi(async (path, options) => {
    if (path === '/settings') {
      const target = options.body.profile
      calls.push(['PUT', target])
      if (target === 'writer-a') {
        signalWriteStarted()
        await writeResponse
      }
      selectedProfile = target
      return { ok: true }
    }
    calls.push(['GET', selectedProfile])
    return { ready: true, locked_profile: selectedProfile }
  })

  try {
    const writeA = updateStorySettings('writer-a', { connectionId: 'shared-backend' })
    await writeStarted
    const refreshB = refreshStoryProfileStatus('writer-b', {
      connectionId: 'shared-backend',
      isCurrent: () => true
    })

    assert.deepEqual(calls, [['PUT', 'writer-a']], 'B must not inspect stale ready state while A commit is pending')
    releaseWrite()
    const [writeResult, refreshResult] = await Promise.all([writeA, refreshB])

    assert.deepEqual(writeResult, { ok: true })
    assert.deepEqual(calls, [
      ['PUT', 'writer-a'],
      ['GET', 'writer-a'],
      ['PUT', 'writer-b'],
      ['GET', 'writer-b']
    ])
    assert.deepEqual(refreshResult.status, { ready: true, locked_profile: 'writer-b' })
  } finally {
    releaseWrite()
    dispose()
  }
})

test('a pending write on another connection does not block a ready workspace', async () => {
  const { bindWorkspaceApi, refreshStoryProfileStatus, storySettingsWritePendingForScope, storyWorkspaceGate, updateStorySettings } = await loadPluginModule()
  let signalWriteStarted
  let releaseWrite
  const writeStarted = new Promise(resolve => { signalWriteStarted = resolve })
  const writeResponse = new Promise(resolve => { releaseWrite = resolve })
  let writeA
  const dispose = bindWorkspaceApi(async path => {
    if (path === '/settings') {
      signalWriteStarted()
      await writeResponse
      return { ok: true }
    }
    return {}
  })

  try {
    writeA = updateStorySettings('writer-a', { connectionId: 'connection-a' })
    await writeStarted
    const statusB = await refreshStoryProfileStatus('writer-b', {
      connectionId: 'connection-b',
      getStatus: async () => ({ ready: true, locked_profile: 'writer-b' })
    })
    const pendingA = { owner: '["connection-a","writer-a"]', generation: 1 }
    const scopeB = { owner: '["connection-b","writer-b"]', generation: 1 }
    assert.equal(storySettingsWritePendingForScope([pendingA, scopeB], scopeB), true)
    assert.equal(storySettingsWritePendingForScope([pendingA], { ...pendingA, generation: 2 }), false)
    const gateOpen = storyWorkspaceGate({
      verifiedCurrent: true,
      settingsWritePending: storySettingsWritePendingForScope(pendingA, scopeB),
      status: statusB.status,
      profile: 'writer-b'
    })

    assert.equal(gateOpen, true)
  } finally {
    releaseWrite()
    await writeA.catch(() => {})
    dispose()
  }
})

test('a manual Vault submit invalidates an older in-flight status response', async () => {
  const { refreshStoryProfileStatus, storyStatusRequestIsCurrent, submitStoryVaultPath } = await loadPluginModule()
  const owner = '["connection-a","writer"]'
  const generation = 3
  let currentRequestId = 1
  let signalStatusStarted
  let resolveOldStatus
  const statusStarted = new Promise(resolve => { signalStatusStarted = resolve })
  const oldStatus = new Promise(resolve => { resolveOldStatus = resolve })
  const committedStatuses = []
  const isRequestCurrent = requestId => storyStatusRequestIsCurrent({
    requestId,
    currentRequestId,
    owner,
    generation,
    currentOwner: owner,
    currentGeneration: generation
  })
  const oldFocusRequest = refreshStoryProfileStatus('writer', {
    connectionId: 'connection-a',
    isCurrent: () => isRequestCurrent(1),
    getStatus: async () => {
      signalStatusStarted()
      return oldStatus
    },
    onStatus: status => committedStatuses.push(status)
  })

  await statusStarted
  currentRequestId = 2
  const manualResult = await submitStoryVaultPath('writer', '/mnt/story-vault', {
    connectionId: 'connection-a',
    isCurrent: () => isRequestCurrent(2),
    syncSettings: async () => ({ ok: true }),
    getStatus: async () => ({ ready: true, locked_profile: 'writer' })
  })
  committedStatuses.push(manualResult.status)
  resolveOldStatus({ ready: false, code: 'configuration_incomplete' })
  const staleResult = await oldFocusRequest

  assert.deepEqual(staleResult, { status: null, superseded: true, wroteSettings: false })
  assert.deepEqual(committedStatuses, [{ ready: true, locked_profile: 'writer' }])
})

test('a failed settings write closes the gate and focus does not repeat it', async () => {
  const { bindWorkspaceApi, refreshStoryProfileStatus, storyWorkspaceGate } = await loadPluginModule()
  const calls = []
  let attempted = false
  let gateWhileWriting = true
  const dispose = bindWorkspaceApi(async (path, options) => {
    calls.push([path, options?.method || 'GET'])
    if (path === '/settings') {
      throw Object.assign(new Error('settings unavailable'), { statusCode: 503 })
    }
    return calls.filter(([calledPath]) => calledPath === '/status').length === 1
      ? { ready: true, locked_profile: 'other' }
      : { ready: false, code: 'profile_not_selected' }
  })

  try {
    await assert.rejects(refreshStoryProfileStatus('writer', {
      canSyncSettings: () => !attempted,
      onWriteState: pending => {
        if (!pending) return
        attempted = true
        gateWhileWriting = storyWorkspaceGate({
          verifiedCurrent: true,
          settingsWritePending: true,
          status: { ready: true, locked_profile: 'writer' },
          profile: 'writer'
        })
      }
    }), /settings unavailable/)
    assert.equal(gateWhileWriting, false)
    assert.equal(storyWorkspaceGate({
      verifiedCurrent: true,
      settingsFailure: true,
      status: { ready: true, locked_profile: 'writer' },
      profile: 'writer'
    }), false, 'a failed settings write must not leave a cached ready gate open')

    const focused = await refreshStoryProfileStatus('writer', {
      canSyncSettings: () => !attempted
    })
    assert.deepEqual(focused.status, { ready: false, code: 'profile_not_selected' })
    assert.deepEqual(calls, [['/status', 'GET'], ['/settings', 'PUT'], ['/status', 'GET']])
  } finally {
    dispose()
  }
})

test('a rejected Vault path remains correctable and a resubmit uses the edited path', async () => {
  const { storyDiagnostic, storyVaultPathCorrectionAvailable, submitStoryVaultPath } = await loadPluginModule()
  const calls = []
  const invalidPath = 'C:\\Users\\writer\\vault'
  const correctedPath = '/mnt/c/Users/writer/vault'
  const invalidVaultError = Object.assign(new Error(
    `IPC failure: 400: ${JSON.stringify({ detail: { code: 'vault_not_directory', vault_root: invalidPath, token: 'PRIVATE_TOKEN' } })}`
  ), { statusCode: 400 })

  await assert.rejects(submitStoryVaultPath('writer', invalidPath, {
    syncSettings: async (_profile, options) => {
      calls.push(options.vaultRoot)
      throw invalidVaultError
    }
  }), error => {
    const diagnostic = storyDiagnostic(error, null)
    assert.deepEqual(diagnostic, { httpStatus: 400, code: 'vault_not_directory' })
    assert.equal(storyVaultPathCorrectionAvailable(null, diagnostic), true)
    assert.ok(!JSON.stringify(diagnostic).includes('PRIVATE'))
    return true
  })

  // The card keeps its state-owned input after a rejected submit; editing it
  // supplies the corrected value to the same explicit submit operation.
  let editedInput = invalidPath
  editedInput = correctedPath
  const result = await submitStoryVaultPath('writer', editedInput, {
    syncSettings: async (_profile, options) => { calls.push(options.vaultRoot); return { ok: true } },
    getStatus: async () => ({ ready: true, locked_profile: 'writer' })
  })

  assert.deepEqual(calls, [invalidPath, correctedPath])
  assert.deepEqual(result.status, { ready: true, locked_profile: 'writer' })
})

test('fresh ready status after Vault submit replaces old query and settings failures', async () => {
  const { storySettingsFailureAfterStatus, storyWorkspaceGate, submitStoryVaultPath } = await loadPluginModule()
  const staleQueryState = { error: Object.assign(new Error('old setup failure'), { statusCode: 422 }) }
  const previousSettingsFailure = { httpStatus: 422, code: 'configuration_incomplete' }
  const result = await submitStoryVaultPath('writer', '/mnt/story-vault', {
    syncSettings: async () => ({ ok: true }),
    getStatus: async () => ({ ready: true, locked_profile: 'writer' })
  })
  const settingsFailure = storySettingsFailureAfterStatus(
    result.status,
    'writer',
    previousSettingsFailure
  )

  assert.ok(staleQueryState.error instanceof Error, 'the earlier React Query error remains stale in cache')
  assert.equal(settingsFailure, null, 'a fresh matching-ready response clears the previous settings failure')
  assert.equal(storyWorkspaceGate({
    verifiedCurrent: true,
    statusFailure: false,
    settingsFailure: Boolean(settingsFailure),
    settingsWritePending: false,
    status: result.status,
    profile: 'writer'
  }), true, 'the explicit setup response opens the gate without waiting for focus/refetch')
})

test('keys story routes by the full route identity, never by display name', async () => {
  const { storyRouteKey } = await loadPluginModule()

  const local = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }
  const otherConnection = { connectionId: 'connection-abc', mode: 'remote', profile: 'writer', targetProfile: 'writer' }
  const remapped = { connectionId: 'connection-abc', mode: 'remote', profile: 'writer', targetProfile: 'backend-worker' }
  const otherProfile = { connectionId: 'local', mode: 'local', profile: 'editor', targetProfile: 'writer' }

  // Same-named Profiles on different connections stay distinct.
  assert.notEqual(storyRouteKey(local), storyRouteKey(otherConnection))
  // The same (connectionId, profile) serving a different backend name stays distinct.
  assert.notEqual(storyRouteKey(otherConnection), storyRouteKey(remapped))
  // Identity covers profile and targetProfile separately — a matching display
  // name (or target) alone never merges two routes.
  assert.notEqual(storyRouteKey(local), storyRouteKey(otherProfile))
  // Whitespace variants of one route normalize to one key; equal triples match.
  assert.equal(storyRouteKey({ connectionId: ' local ', profile: ' writer ', targetProfile: 'writer' }), storyRouteKey(local))
  assert.equal(storyRouteKey({ ...local }), storyRouteKey(local))
})

test('matches backend scope by connection and backend Profile only', async () => {
  const { storyScopeMatches } = await loadPluginModule()

  const writerAlias = { connectionId: 'connection-abc', mode: 'remote', profile: 'writer', targetProfile: 'work' }
  const editorAlias = { connectionId: 'connection-abc', mode: 'remote', profile: 'editor', targetProfile: 'work' }
  const otherBackend = { connectionId: 'connection-abc', mode: 'remote', profile: 'drafts', targetProfile: 'sandbox' }
  const identityRoute = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }

  // owner=work is the shared backend Profile — both aliases are in that scope.
  assert.equal(storyScopeMatches(writerAlias, { connectionId: 'connection-abc', profile: 'work' }), true)
  assert.equal(storyScopeMatches(editorAlias, { connectionId: 'connection-abc', profile: 'work' }), true)
  // An alias's display name is not backend identity: owner=writer/editor is a
  // different actual backend than work — even for the same-named alias route.
  assert.equal(storyScopeMatches(writerAlias, { connectionId: 'connection-abc', profile: 'writer' }), false)
  assert.equal(storyScopeMatches(editorAlias, { connectionId: 'connection-abc', profile: 'editor' }), false)
  assert.equal(storyScopeMatches(writerAlias, { connectionId: 'connection-abc', profile: 'editor' }), false)
  assert.equal(storyScopeMatches(editorAlias, { connectionId: 'connection-abc', profile: 'writer' }), false)
  // A different connectionId or a different targetProfile never matches.
  assert.equal(storyScopeMatches(writerAlias, { connectionId: 'local', profile: 'work' }), false)
  assert.equal(storyScopeMatches(writerAlias, { connectionId: 'connection-abc', profile: 'sandbox' }), false)
  assert.equal(storyScopeMatches(otherBackend, { connectionId: 'connection-abc', profile: 'work' }), false)
  // A route without targetProfile activates its own profile as the backend.
  assert.equal(
    storyScopeMatches({ connectionId: 'connection-abc', mode: 'remote', profile: 'writer', targetProfile: '' }, { connectionId: 'connection-abc', profile: 'writer' }),
    true
  )
  // A local-style route never matches a null owner connectionId; whitespace
  // variants normalize the way host.state profile keys do.
  assert.equal(storyScopeMatches(identityRoute, { connectionId: null, profile: 'writer' }), false)
  assert.equal(storyScopeMatches(identityRoute, { connectionId: 'local', profile: 'writer' }), true)
  assert.equal(
    storyScopeMatches({ connectionId: ' connection-abc ', profile: ' writer ', targetProfile: ' work ' }, { connectionId: 'connection-abc', profile: 'work' }),
    true
  )
  // No pick never blocks; a missing owner stays out of every real route's scope.
  assert.equal(storyScopeMatches(null, { connectionId: null, profile: 'default' }), true)
  assert.equal(storyScopeMatches(writerAlias, { connectionId: null, profile: 'work' }), false)
})

test('activates a story route with the backend target and verifies the owner', async () => {
  const { activateStoryRoute } = await loadPluginModule()

  const calls = []
  const record = async (connectionId, profile) => {
    calls.push([connectionId, profile])
  }
  const remapped = { connectionId: 'connection-abc', mode: 'remote', profile: 'writer', targetProfile: 'backend-worker' }

  // ensureAgent(connectionId, targetProfile) lands and host.state matches.
  await activateStoryRoute(
    remapped,
    record,
    () => ({ connectionId: 'connection-abc', profile: 'backend-worker' })
  )
  assert.deepEqual(calls, [['connection-abc', 'backend-worker']])

  // A Profile without targetProfile activates with its own name, normalized
  // the way the SDK normalizes host.state.profile.
  calls.length = 0
  await activateStoryRoute(
    { connectionId: 'local', mode: 'local', profile: ' writer ', targetProfile: '' },
    record,
    () => ({ connectionId: 'local', profile: 'writer' })
  )
  assert.deepEqual(calls, [['local', 'writer']])

  // An activation that resolves without landing the owner fails closed.
  await assert.rejects(
    activateStoryRoute(remapped, record, () => ({ connectionId: 'connection-abc', profile: 'writer' })),
    /did not match/
  )
  // A local route never matches a null owner connectionId — no invented 'local'.
  await assert.rejects(
    activateStoryRoute(
      { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' },
      record,
      () => ({ connectionId: null, profile: 'writer' })
    ),
    /did not match/
  )
  // A rejected activation propagates and verifies nothing.
  await assert.rejects(
    activateStoryRoute(remapped, async () => {
      throw new Error('dial failed')
    }, () => ({ connectionId: 'connection-abc', profile: 'backend-worker' })),
    /dial failed/
  )
  // Missing route identity or a Desktop without ensureAgent stays unusable.
  await assert.rejects(activateStoryRoute({}, record, () => ({ connectionId: 'local', profile: 'default' })), /unavailable/)
  await assert.rejects(
    activateStoryRoute(remapped, undefined, () => ({ connectionId: 'connection-abc', profile: 'backend-worker' })),
    /unavailable/
  )
})

test('chooses the workspace layout mode from the container width', async () => {
  const { storyLayoutMode } = await loadPluginModule()

  // Wide keeps a fixed project tree, a stretchable editor and a fixed-width
  // sessions column.
  assert.equal(storyLayoutMode(1100), 'wide')
  assert.equal(storyLayoutMode(980), 'wide')
  // Compact keeps the editor unsqueezed with a collapsible sessions area.
  assert.equal(storyLayoutMode(979), 'compact')
  assert.equal(storyLayoutMode(700), 'compact')
  assert.equal(storyLayoutMode(560), 'compact')
  // Narrow stacks the project tree above the editor.
  assert.equal(storyLayoutMode(559), 'narrow')
  assert.equal(storyLayoutMode(400), 'narrow')
  assert.equal(storyLayoutMode(0), 'narrow')
})

test('switches between the library and project workspace surfaces', async () => {
  const { storyWorkspaceSurface } = await loadPluginModule()

  // Only a selected project reveals the tree/editor/sessions workspace; every
  // other case stays on the project library page.
  assert.equal(storyWorkspaceSurface('project-1'), 'workspace')
  assert.equal(storyWorkspaceSurface(null), 'library')
  assert.equal(storyWorkspaceSurface(undefined), 'library')
  assert.equal(storyWorkspaceSurface(''), 'library')
})

test('installs scoped Story page CSS on register and removes it on dispose', async () => {
  const pluginModule = await loadPluginModule()
  const appended = []
  const removed = []
  const previousDocument = globalThis.document
  globalThis.document = {
    createElement: () => ({
      textContent: '',
      remove() { removed.push(this) }
    }),
    head: { append: node => appended.push(node) }
  }
  try {
    const disposers = []
    pluginModule.default.register({
      registerMany() {},
      onDispose: dispose => disposers.push(dispose),
      i18n: { register() {}, t: key => key }
    })
    assert.equal(appended.length, 1, 'register must install exactly one style element')
    const css = appended[0].textContent
    // Task 4 three-tier workspace geometry: fixed tree / stretchable editor /
    // fixed sessions column at wide, stacked collapsible sessions below.
    assert.ok(css.includes('.hermes-story-workspace[data-layout=wide]{grid-template-columns:16rem minmax(0,1fr) 18rem}'))
    assert.ok(css.includes('.hermes-story-workspace[data-layout=compact]{grid-template-columns:16rem minmax(0,1fr)'))
    assert.ok(css.includes('.hermes-story-workspace[data-layout=narrow]'))
    assert.ok(css.includes('minmax(0,1fr)'))
    // Narrow keeps the tree above the editor with a height cap; stacked
    // sessions cap their height so the editor keeps the remaining space.
    assert.ok(css.includes('max-height:16rem'))
    assert.ok(css.includes('max-height:18rem'))
    // A collapsed sessions area hides the panel via CSS instead of unmounting.
    assert.ok(css.includes('[data-open=false]'))
    // Task 3 project card grid geometry.
    assert.ok(css.includes('.hermes-story-library-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr))'))
    // Geometry and chrome stay on Hermes theme variables.
    assert.ok(css.includes('var(--ui-stroke-secondary)'))
    assert.ok(css.includes('var(--chrome-action-hover)'))
    assert.ok(css.includes('var(--ui-accent)'))
    for (const dispose of disposers) dispose()
    assert.equal(removed.length, 1, 'dispose must remove the installed style element')
  } finally {
    if (previousDocument === undefined) delete globalThis.document
    else globalThis.document = previousDocument
  }
})
