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

const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
const pluginModule = await import(dataModule(rewriteDesktopImports(source)))
const { createStoryWritingSession, retryStoryKickoff } = pluginModule

const project = { id: 'novel', name: 'Novel' }
const route = { connectionId: 'remote-1', mode: 'remote', profile: 'writer', targetProfile: 'writer' }
const context = {
  project,
  volumes: [{ id: 'novel:volume-1', title: 'Volume One' }],
  chapters: [{ id: 'novel:chapter-1', title: 'Chapter One' }]
}

function workflowHarness(overrides = {}) {
  const calls = []
  const dependencies = {
    project,
    profile: 'writer',
    connectionId: 'remote-1',
    profileRoutes: async () => [route],
    retainProfile: async selectedRoute => {
      calls.push(['retain', selectedRoute])
      return () => calls.push(['release'])
    },
    requestProfile: async (selectedRoute, method, payload, transfer, options) => {
      calls.push([method, selectedRoute, payload, transfer, options])
      if (method === 'session.create') {
        return { session_id: 'runtime-1', stored_session_id: 'stored-1' }
      }
      return {}
    },
    bindSession: async body => {
      calls.push(['bind', body])
      return { context }
    },
    openSession: async (storedId, options) => {
      calls.push(['open', storedId, options])
    },
    ...overrides
  }
  return { calls, dependencies }
}

test('creates, binds, starts, and opens a retained Story writing session', async () => {
  const { calls, dependencies } = workflowHarness()

  const result = await createStoryWritingSession(dependencies)

  assert.deepEqual(calls.map(call => call[0]), [
    'retain',
    'session.create',
    'bind',
    'session.title',
    'prompt.submit',
    'open',
    'release'
  ])
  assert.deepEqual(calls.find(call => call[0] === 'session.create')[2], {
    profile: 'writer',
    title: 'Story: Novel',
    follow_profile_config: true
  })
  assert.deepEqual(calls.find(call => call[0] === 'session.create')[4], { spawnPriority: 'foreground' })
  assert.match(calls.find(call => call[0] === 'prompt.submit')[2].text, /project_id: novel/)
  assert.match(calls.find(call => call[0] === 'prompt.submit')[2].text, /chapter_id: novel:chapter-1/)
  assert.equal(calls.find(call => call[0] === 'open')[1], 'stored-1')
  assert.equal(result.storedSessionId, 'stored-1')
  assert.equal(result.runtimeSessionId, 'runtime-1')
})

test('stops after a bind failure and releases the retained route', async () => {
  const bindError = new Error('bind rejected')
  const { calls, dependencies } = workflowHarness({
    bindSession: async body => {
      calls.push(['bind', body])
      throw bindError
    }
  })

  await assert.rejects(createStoryWritingSession(dependencies), error => {
    assert.equal(error.stage, 'binding')
    assert.equal(error.message, bindError.message)
    assert.equal(error.cause, bindError)
    return true
  })
  assert.deepEqual(calls.map(call => call[0]), ['retain', 'session.create', 'bind', 'release'])
})

test('resumes once when the first kickoff reports a missing runtime session', async () => {
  let promptAttempts = 0
  const { calls, dependencies } = workflowHarness({
    requestProfile: async (selectedRoute, method, payload, transfer, options) => {
      calls.push([method, selectedRoute, payload, transfer, options])
      if (method === 'session.create') {
        return { session_id: 'runtime-1', stored_session_id: 'stored-1' }
      }
      if (method === 'prompt.submit' && promptAttempts++ === 0) {
        throw Object.assign(new Error('session not in memory'), { code: 4001 })
      }
      if (method === 'session.resume') return { session_id: 'runtime-2' }
      return {}
    }
  })

  const result = await createStoryWritingSession(dependencies)

  assert.equal(calls.filter(call => call[0] === 'session.resume').length, 1)
  assert.equal(calls.filter(call => call[0] === 'prompt.submit').length, 2)
  assert.deepEqual(calls.map(call => call[0]), [
    'retain',
    'session.create',
    'bind',
    'session.title',
    'prompt.submit',
    'session.resume',
    'bind',
    'prompt.submit',
    'open',
    'release'
  ])
  assert.deepEqual(calls.find(call => call[0] === 'session.resume')[2], {
    session_id: 'stored-1',
    profile: 'writer',
    omit_messages: true
  })
  assert.deepEqual(calls.filter(call => call[0] === 'bind')[1][1], {
    session_id: 'stored-1',
    stored_session_id: 'stored-1',
    runtime_session_id: 'runtime-2',
    profile: 'writer',
    connection_id: 'remote-1',
    project_id: 'novel',
    project_name: 'Novel',
    title: 'Story: Novel'
  })
  assert.equal(result.runtimeSessionId, 'runtime-2')
  assert.equal(calls.at(-1)[0], 'release')
})

test('does not reuse a route from another connection scope', async () => {
  const localRoute = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }
  const { calls, dependencies } = workflowHarness({ profileRoutes: async () => [localRoute] })

  await assert.rejects(createStoryWritingSession(dependencies), error => {
    assert.equal(error.stage, 'routing')
    return true
  })
  assert.deepEqual(calls, [])
})

test('selects the route for the current connection and profile scope', async () => {
  const localRoute = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }
  let selectedRoute
  const { dependencies } = workflowHarness({
    profileRoutes: async () => [localRoute, route],
    retainProfile: async currentRoute => {
      selectedRoute = currentRoute
      return () => undefined
    }
  })

  await createStoryWritingSession(dependencies)

  assert.equal(selectedRoute.connectionId, 'remote-1')
  assert.equal(selectedRoute.targetProfile, 'writer')
})

for (const scenario of [
  {
    name: 'wraps profile route failures as routing errors',
    stage: 'routing',
    overrides: { profileRoutes: async () => { throw new Error('route lookup failed') } }
  },
  {
    name: 'wraps session creation failures as creating errors',
    stage: 'creating',
    overrides: {
      requestProfile: async (selectedRoute, method) => {
        if (method === 'session.create') throw new Error('create failed')
      }
    }
  },
  {
    name: 'wraps kickoff failures as submitting errors',
    stage: 'submitting',
    overrides: {
      requestProfile: async (selectedRoute, method) => {
        if (method === 'session.create') return { session_id: 'runtime-1', stored_session_id: 'stored-1' }
        if (method === 'prompt.submit') throw new Error('submit failed')
        return {}
      }
    }
  },
  {
    name: 'wraps session opening failures as opening errors',
    stage: 'opening',
    overrides: { openSession: async () => { throw new Error('open failed') } }
  }
]) {
  test(scenario.name, async () => {
    const { dependencies } = workflowHarness(scenario.overrides)

    await assert.rejects(createStoryWritingSession(dependencies), error => {
      assert.equal(error.stage, scenario.stage)
      assert.match(error.message, /failed/)
      assert.ok(error.cause instanceof Error)
      if (scenario.stage === 'submitting') {
        assert.equal(error.recovery.storedId, 'stored-1')
        assert.equal(error.recovery.runtimeId, 'runtime-1')
      }
      return true
    })
  })
}

test('retries an existing kickoff without creating or binding another session', async () => {
  const calls = []
  const recovery = {
    route,
    runtimeId: 'runtime-1',
    storedId: 'stored-1',
    profile: 'writer',
    text: 'project_id: novel'
  }

  const result = await retryStoryKickoff({
    recovery,
    requestProfile: async (selectedRoute, method, payload) => calls.push([method, selectedRoute, payload]),
    openSession: async (storedId, options) => calls.push(['open', storedId, options])
  })

  assert.deepEqual(calls.map(call => call[0]), ['prompt.submit', 'open'])
  assert.equal(result.storedSessionId, 'stored-1')
  assert.equal(result.runtimeSessionId, 'runtime-1')
})

test('retry rebinds a fresh resumed runtime before submitting the kickoff again', async () => {
  const calls = []
  let promptAttempts = 0
  const bindingRequest = {
    session_id: 'stored-1',
    stored_session_id: 'stored-1',
    runtime_session_id: 'runtime-1',
    profile: 'writer',
    connection_id: 'remote-1',
    project_id: 'novel',
    project_name: 'Novel',
    title: 'Story: Novel'
  }
  const recovery = {
    route,
    runtimeId: 'runtime-1',
    storedId: 'stored-1',
    profile: 'writer',
    text: 'project_id: novel',
    bindingRequest
  }

  const result = await retryStoryKickoff({
    recovery,
    requestProfile: async (selectedRoute, method, payload) => {
      calls.push([method, selectedRoute, payload])
      if (method === 'prompt.submit' && promptAttempts++ === 0) {
        throw Object.assign(new Error('session not in memory'), { code: 4001 })
      }
      if (method === 'session.resume') return { session_id: 'runtime-2' }
      return {}
    },
    bindSession: async body => calls.push(['bind', body]),
    openSession: async (storedId, options) => calls.push(['open', storedId, options])
  })

  assert.deepEqual(calls.map(call => call[0]), [
    'prompt.submit',
    'session.resume',
    'bind',
    'prompt.submit',
    'open'
  ])
  assert.deepEqual(calls[2][1], { ...bindingRequest, runtime_session_id: 'runtime-2' })
  assert.equal(result.runtimeSessionId, 'runtime-2')
})

test('rejects incomplete kickoff recovery at the submitting stage', async () => {
  await assert.rejects(retryStoryKickoff({ recovery: { storedId: 'stored-1' } }), error => {
    assert.equal(error.stage, 'submitting')
    assert.match(error.message, /incomplete/)
    return true
  })
})
