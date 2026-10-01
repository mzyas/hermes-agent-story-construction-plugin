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
const importUrls = { '@hermes/plugin-sdk': sdkUrl, react: reactUrl, 'react/jsx-runtime': jsxRuntimeUrl }

function rewriteDesktopImports(source) {
  return source.replace(/(from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\2/g, (whole, prefix, quote, specifier) =>
    importUrls[specifier] ? `${prefix}${quote}${importUrls[specifier]}${quote}` : whole
  )
}

const source = readFileSync(fileURLToPath(pluginUrl), 'utf8')
const { ensureStoryProjectWorkspace, archiveHermesStoryProject, createStoryWritingSession } = await import(
  dataModule(rewriteDesktopImports(source))
)

const route = { connectionId: 'local', mode: 'local', profile: 'writer', targetProfile: 'writer' }
const project = { id: 'novel', name: 'Novel' }
const FOLDER = '/work/story/novel'

function harness({ link = null, rpc = {}, folder = FOLDER } = {}) {
  const calls = []
  return {
    calls,
    options: {
      project,
      profile: 'writer',
      connectionId: 'local',
      profileRoutes: async () => [route],
      requestFolder: async (projectId, scope) => {
        calls.push(['folder', projectId, scope])
        return { folder, created: !link, link }
      },
      linkFolder: async (projectId, body) => {
        calls.push(['link', projectId, body])
        return { link: body }
      },
      requestProfile: async (_route, method, params) => {
        calls.push([method, params])
        if (rpc[method]) return rpc[method](params)
        return {}
      }
    }
  }
}

test('a new project gets a Hermes project around its folder and the link is saved', async () => {
  const { calls, options } = harness({ rpc: { 'projects.create': () => ({ project: { id: 'p_1' } }) } })

  const result = await ensureStoryProjectWorkspace(options)

  assert.deepEqual(result, { folder: FOLDER, hermesProjectId: 'p_1' })
  assert.deepEqual(calls, [
    ['folder', 'novel', { profile: 'writer', connectionId: 'local' }],
    ['projects.create', { profile: 'writer', name: 'Novel', folders: [FOLDER], primary_path: FOLDER }],
    ['link', 'novel', { profile: 'writer', connectionId: 'local', hermesProjectId: 'p_1', folder: FOLDER }]
  ])
})

test('an existing live link is verified and reused without creating anything', async () => {
  const link = { hermes_project_id: 'p_1', folder: FOLDER, archived: false }
  const { calls, options } = harness({ link })

  const result = await ensureStoryProjectWorkspace(options)

  assert.equal(result.hermesProjectId, 'p_1')
  assert.deepEqual(calls.map(call => call[0]), ['folder', 'projects.get'])
})

test('an archived link restores its Hermes project', async () => {
  const link = { hermes_project_id: 'p_1', folder: FOLDER, archived: true }
  const { calls, options } = harness({ link })

  await ensureStoryProjectWorkspace(options)

  assert.deepEqual(calls[1], ['projects.archive', { profile: 'writer', id: 'p_1', restore: true }])
})

test('a Hermes project deleted by hand is registered again', async () => {
  const link = { hermes_project_id: 'p_old', folder: FOLDER, archived: false }
  const gone = Object.assign(new Error('no such project'), { code: 5062 })
  const { calls, options } = harness({
    link,
    rpc: {
      'projects.get': () => {
        throw gone
      },
      'projects.create': () => ({ project: { id: 'p_new' } })
    }
  })

  const result = await ensureStoryProjectWorkspace(options)

  assert.equal(result.hermesProjectId, 'p_new')
  assert.deepEqual(calls.at(-1)[2].hermesProjectId, 'p_new')
})

test('a folder that already belongs to a Hermes project is adopted', async () => {
  const duplicate = Object.assign(new Error('folder already belongs to project'), { code: 5063 })
  const { options } = harness({
    rpc: {
      'projects.create': () => {
        throw duplicate
      },
      'projects.for_cwd': () => ({ project: { id: 'p_existing' } })
    }
  })

  assert.equal((await ensureStoryProjectWorkspace(options)).hermesProjectId, 'p_existing')
})

test('a failed create with nothing to adopt is reported', async () => {
  const failure = Object.assign(new Error('boom'), { code: 5061 })
  const { calls, options } = harness({
    rpc: {
      'projects.create': () => {
        throw failure
      },
      'projects.for_cwd': () => ({ project: null })
    }
  })

  await assert.rejects(ensureStoryProjectWorkspace(options), failure)
  assert.equal(calls.some(call => call[0] === 'link'), false)
})

test('archiving ignores a Hermes project that is already gone', async () => {
  const calls = []
  await archiveHermesStoryProject({
    hermesProjectId: 'p_1',
    profile: 'writer',
    connectionId: 'local',
    profileRoutes: async () => [route],
    requestProfile: async (_route, method, params) => {
      calls.push([method, params])
      throw Object.assign(new Error('no such project'), { code: 5062 })
    }
  })
  assert.deepEqual(calls, [['projects.archive', { profile: 'writer', id: 'p_1' }]])
})

function sessionHarness({ ensureWorkspace, createdCwd }) {
  const calls = []
  return {
    calls,
    options: {
      project,
      profile: 'writer',
      connectionId: 'local',
      profileRoutes: async () => [route],
      retainProfile: async () => () => undefined,
      ensureWorkspace,
      requestProfile: async (_route, method, params) => {
        calls.push([method, params])
        if (method === 'session.create') {
          return { session_id: 'runtime-1', stored_session_id: 'stored-1', info: { cwd: createdCwd } }
        }
        return {}
      },
      bindSession: async body => ({ body }),
      openSession: async () => undefined
    }
  }
}

test('the writing session is created inside the project folder', async () => {
  const { calls, options } = sessionHarness({
    ensureWorkspace: async () => ({ folder: FOLDER, hermesProjectId: 'p_1' }),
    createdCwd: FOLDER
  })

  const result = await createStoryWritingSession(options)

  assert.equal(calls.find(call => call[0] === 'session.create')[1].cwd, FOLDER)
  assert.equal(result.workspaceIssue, null)
})

test('a folder Hermes did not apply is reported, not hidden', async () => {
  const { options } = sessionHarness({
    ensureWorkspace: async () => ({ folder: FOLDER, hermesProjectId: 'p_1' }),
    createdCwd: '/somewhere/else'
  })

  assert.equal((await createStoryWritingSession(options)).workspaceIssue, 'workspace_not_applied')
})

test('a workspace failure still creates the session, without a folder', async () => {
  const unsupported = Object.assign(new Error('refused'), { detail: { code: 'workspace_unsupported_backend' } })
  const { calls, options } = sessionHarness({
    ensureWorkspace: async () => {
      throw unsupported
    },
    createdCwd: ''
  })

  const result = await createStoryWritingSession(options)

  assert.equal('cwd' in calls.find(call => call[0] === 'session.create')[1], false)
  assert.equal(result.workspaceIssue, 'workspace_unsupported_backend')
  assert.equal(result.storedSessionId, 'stored-1')
})

test('the backend error code is read from an HTTP error message', async () => {
  const refused = new Error('HTTP 409: {"detail":{"code":"workspace_unsupported_backend"}}')
  const { options } = sessionHarness({
    ensureWorkspace: async () => {
      throw refused
    },
    createdCwd: ''
  })

  assert.equal((await createStoryWritingSession(options)).workspaceIssue, 'workspace_unsupported_backend')
})
