import { PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, host, usePluginI18n, useQuery, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const en = {
  palette: {
    open: 'Story Construction: Show workspace'
  },
  workspace: {
    title: 'Story Construction',
    scope: (connectionId, profile) => `(${connectionId}, ${profile})`,
    loadingProjects: 'Loading projects…',
    projectsUnavailable: 'Could not load projects. Check the Story service and try again.',
    newProject: 'New project',
    projectName: 'Project name',
    projectSlug: 'Project slug (optional)',
    createProject: 'Create project',
    creatingProject: 'Creating project…',
    backToLibrary: 'Back to library',
    projectTree: 'Project tree',
    loadingProject: 'Loading project…',
    projectUnavailable: error => `Project unavailable: ${error}`
  },
  library: {
    search: 'Search projects',
    searchPlaceholder: 'Filter by name or ID',
    empty: 'No projects in this Vault yet.',
    noMatch: 'No projects match your search.'
  },
  dialog: {
    cancel: 'Cancel',
    nameRequired: 'Project name is required.',
    createFailed: 'Could not create project. Check the Story service and try again.'
  },
  tree: {
    project: 'Project',
    worldInfo: 'WorldInfo',
    characters: 'Characters',
    notes: 'Notes',
    volumes: 'Volumes',
    chapters: 'Chapters',
    empty: 'Empty',
    untitled: 'Untitled',
    selectProject: 'Select a project.'
  },
  chapter: {
    openPrompt: 'Open a chapter to read or edit it.',
    loading: 'Loading chapter…',
    unavailable: error => `Chapter unavailable: ${error}`,
    version: version => `Version ${version || 'unknown'} · Draft edits stay local until confirmed.`,
    confirmOverwrite: 'I confirm this chapter overwrite.',
    confirmLeave: 'You have an unsaved chapter draft. Leave without saving?',
    saving: 'Saving…',
    saved: 'Saved; chapter version refreshed.',
    saveUnavailable: error => `Save unavailable: ${error}`,
    saveFailed: error => `Save failed: ${error}`,
    saveConfirmed: 'Save confirmed draft'
  },
  agent: {
    title: 'Agent',
    binding: 'Binding…',
    bound: 'Bound to focused session',
    bindFailed: error => `Bind failed: ${error}`,
    working: 'Working',
    idle: 'Idle',
    noFocusedSession: 'No focused session',
    bindFocusedSession: 'Bind focused session to project',
    sessions: 'Project writing sessions',
    loadingSessions: 'Loading writing sessions…',
    sessionsUnavailable: error => `Writing sessions unavailable: ${error}`,
    noSessions: 'No writing sessions for this project',
    newWritingSession: 'New writing session',
    continueSession: 'Continue',
    retryFirstTask: 'Retry first task',
    removeStaleBinding: 'Remove stale binding',
    stageCreating: 'Creating session…',
    stageBinding: 'Binding session to project…',
    stageSubmitting: 'Submitting first writing task…',
    stageOpening: 'Opening writing session…',
    stageReady: 'Writing session ready',
    sessionFailed: error => `Writing session failed: ${error}`,
    continueFailed: error => `Could not continue session: ${error}`,
    staleBinding: 'The Hermes session no longer exists.',
    removeFailed: error => `Could not remove stale binding: ${error}`
  },
  status: {
    checking: 'Checking Story service status…',
    retry: 'Retry',
    details: 'Technical details',
    unavailable: 'The Story service is temporarily unavailable.',
    runtime_uninitialized: 'The Story runtime is not initialized in this Hermes installation.',
    configuration_incomplete: 'Story settings are incomplete for this Profile.',
    profile_not_selected: 'Select a Story Profile to initialize the shared Vault.',
    agent_not_installed: 'The Story Construction plugin is not installed for this Profile.',
    agent_not_enabled: 'Enable the Story Construction plugin for this Profile.',
    hermes_home_mismatch: 'This Profile is not the Story-locked installation target.',
    vault_not_directory: 'The configured Story vault is not available.',
    vault_unwritable: 'The Story vault is not writable by the backend.',
    vaultRoot: 'WSL-accessible Vault path',
    vaultRootHelp: 'Enter a path that the WSL backend can access. It will be shared with the selected Profile.',
    saveVault: 'Save Vault path',
    savingVault: 'Saving Vault path…',
    profile_mismatch: 'The active Profile does not match the Story-locked Profile.',
    httpStatus: value => `HTTP ${value}`,
    code: value => `code ${value}`
  },
  profile: {
    label: 'Story Profile',
    activating: 'Switching the Story Profile…',
    activationFailed: 'Could not switch to the selected Story Profile.',
    local: 'local',
    remote: 'remote',
    option: (name, mode, connectionId) => `${name} · ${mode} · ${connectionId}`
  }
}

const zh = {
  palette: {
    open: '故事构建：显示工作区'
  },
  workspace: {
    title: '故事构建',
    scope: (connectionId, profile) => `(${connectionId}, ${profile})`,
    loadingProjects: '正在加载项目…',
    projectsUnavailable: '无法加载项目，请检查故事服务后重试。',
    newProject: '新建项目',
    projectName: '项目名称',
    projectSlug: '项目标识（可选）',
    createProject: '创建项目',
    creatingProject: '正在创建项目…',
    backToLibrary: '返回项目库',
    projectTree: '项目树',
    loadingProject: '正在加载项目…',
    projectUnavailable: error => `项目不可用：${error}`
  },
  library: {
    search: '搜索项目',
    searchPlaceholder: '按名称或 ID 筛选',
    empty: '当前资料库还没有项目。',
    noMatch: '没有符合当前搜索的项目。'
  },
  dialog: {
    cancel: '取消',
    nameRequired: '请填写项目名称。',
    createFailed: '无法创建项目，请检查故事服务后重试。'
  },
  tree: {
    project: '项目',
    worldInfo: '世界设定',
    characters: '角色',
    notes: '笔记',
    volumes: '卷',
    chapters: '章节',
    empty: '为空',
    untitled: '未命名',
    selectProject: '请选择一个项目。'
  },
  chapter: {
    openPrompt: '打开一个章节以阅读或编辑。',
    loading: '正在加载章节…',
    unavailable: error => `章节不可用：${error}`,
    version: version => `版本 ${version || '未知'} · 确认前的草稿修改只保存在本地。`,
    confirmOverwrite: '我确认覆盖此章节。',
    confirmLeave: '有未保存的章节草稿，确定离开而不保存吗？',
    saving: '正在保存…',
    saved: '已保存；章节版本已刷新。',
    saveUnavailable: error => `无法保存：${error}`,
    saveFailed: error => `保存失败：${error}`,
    saveConfirmed: '保存已确认的草稿'
  },
  agent: {
    title: '代理',
    binding: '正在绑定…',
    bound: '已绑定到当前会话',
    bindFailed: error => `绑定失败：${error}`,
    working: '工作中',
    idle: '空闲',
    noFocusedSession: '没有当前会话',
    bindFocusedSession: '将当前会话绑定到项目',
    sessions: '项目写作会话',
    loadingSessions: '正在加载写作会话…',
    sessionsUnavailable: error => `写作会话不可用：${error}`,
    noSessions: '此项目还没有写作会话',
    newWritingSession: '新建写作会话',
    continueSession: '继续',
    retryFirstTask: '重试首次任务',
    removeStaleBinding: '移除失效绑定',
    stageCreating: '正在创建会话…',
    stageBinding: '正在将会话绑定到项目…',
    stageSubmitting: '正在提交首次写作任务…',
    stageOpening: '正在打开写作会话…',
    stageReady: '写作会话已就绪',
    sessionFailed: error => `写作会话失败：${error}`,
    continueFailed: error => `无法继续会话：${error}`,
    staleBinding: '对应的 Hermes 会话已不存在。',
    removeFailed: error => `无法移除失效绑定：${error}`
  },
  status: {
    checking: '正在检查故事服务状态…',
    retry: '重试',
    details: '技术详情',
    unavailable: '故事服务暂不可用。',
    runtime_uninitialized: '当前 Hermes 安装尚未初始化故事运行时。',
    configuration_incomplete: '当前 Profile 的故事配置不完整。',
    profile_not_selected: '请选择 Story Profile 以初始化共享资料库。',
    agent_not_installed: '此 Profile 尚未安装 Story Construction 插件。',
    agent_not_enabled: '请在此 Profile 启用 Story Construction 插件。',
    hermes_home_mismatch: '当前 Profile 不是故事后端锁定的安装目标。',
    vault_not_directory: '配置的故事资料库当前不可用。',
    vault_unwritable: '后端无法写入此故事资料库。',
    vaultRoot: 'WSL 可访问的资料库路径',
    vaultRootHelp: '请输入 WSL 后端可访问的路径。此路径将与所选 Profile 共享。',
    saveVault: '保存资料库路径',
    savingVault: '正在保存资料库路径…',
    profile_mismatch: '当前 Profile 与故事后端锁定的 Profile 不一致。',
    httpStatus: value => `HTTP ${value}`,
    code: value => `代码 ${value}`
  },
  profile: {
    label: '故事 Profile',
    activating: '正在切换故事 Profile…',
    activationFailed: '无法切换到所选的故事 Profile。',
    local: '本地',
    remote: '远程',
    option: (name, mode, connectionId) => `${name} · ${mode} · ${connectionId}`
  }
}

const STORY_LOCALES = { en, zh }
const STORY_ROUTE_PATH = '/story-construction'

function useMutableRef(initialValue) {
  const [ref] = useState({ current: initialValue })
  return ref
}

function translateEnglishStory(key, ...args) {
  const value = key.split('.').reduce((node, part) => node?.[part], en)
  return typeof value === 'function' ? value(...args) : String(value ?? key)
}

let rest = null
let storySettingsBindingRevision = 0
const storySettingsWriteQueues = new Map()
const storySettingsWriteRevisions = new Map()

export function buildProjectTree(payload, translate = translateEnglishStory) {
  const value = payload || {}
  const project = value.project || null
  const worldInfo = value.world_info || null
  const entries = Array.isArray(value.world_info_entries) ? value.world_info_entries : []
  const characters = Array.isArray(value.characters) ? value.characters : []
  const categories = Array.isArray(value.categories) ? value.categories : []
  const notes = Array.isArray(value.notes) ? value.notes : []
  const volumes = Array.isArray(value.volumes) ? value.volumes : []
  const chapters = Array.isArray(value.chapters) ? value.chapters : []

  return {
    project,
    branches: [
      { id: 'project', label: translate('tree.project'), children: project ? [project] : [] },
      {
        id: 'worldInfo',
        label: translate('tree.worldInfo'),
        children: worldInfo ? [{ ...worldInfo, entries }] : []
      },
      { id: 'characters', label: translate('tree.characters'), children: characters },
      {
        id: 'notes',
        label: translate('tree.notes'),
        children: [
          ...categories.map(category => ({ ...category, kind: 'category' })),
          ...notes.map(note => ({ ...note, kind: 'note' }))
        ]
      },
      { id: 'volumes', label: translate('tree.volumes'), children: volumes },
      { id: 'chapters', label: translate('tree.chapters'), children: chapters }
    ]
  }
}

export function buildStoryScopeQuery({ sessionId, profile, connectionId } = {}) {
  const params = new URLSearchParams()
  if (typeof sessionId === 'string' && sessionId.trim()) params.set('session_id', sessionId.trim())
  if (typeof profile === 'string' && profile.trim()) params.set('profile', profile.trim())
  if (typeof connectionId === 'string' && connectionId.trim()) params.set('connection_id', connectionId.trim())
  const query = params.toString()
  return query ? '?' + query : ''
}

export function normalizeProjectDraft({ name, slug } = {}) {
  const normalizedName = typeof name === 'string' ? name.trim() : ''
  const normalizedSlug = typeof slug === 'string' ? slug.trim() : ''
  if (!normalizedName) throw new Error('project name is required')
  return { name: normalizedName, slug: normalizedSlug }
}

export function projectDiscoveryQuery({ profile, connectionId, ready = false } = {}) {
  return {
    enabled: Boolean(profile && connectionId && ready),
    queryKey: ['story-construction', 'projects', profile, connectionId],
    scope: { profile, connectionId }
  }
}

const STORY_STATUS_CODES = new Set([
  'runtime_uninitialized', 'configuration_incomplete', 'hermes_home_mismatch',
  'vault_not_directory', 'profile_not_selected', 'agent_not_installed',
  'agent_not_enabled', 'vault_unwritable'
])

export function storyReadiness(status, profile) {
  if (!status || status.ready !== true) {
    return { ready: false, code: STORY_STATUS_CODES.has(status?.code) ? status.code : 'unavailable' }
  }
  return status.locked_profile === profile
    ? { ready: true, code: 'ready' }
    : { ready: false, code: 'profile_mismatch' }
}

function safeStatusFromError(error) {
  const message = typeof error?.message === 'string' ? error.message : ''
  const match = message.match(/(?:^|:\s*)(\{[\s\S]*\})\s*$/)
  if (!match) return null
  try {
    const detail = JSON.parse(match[1])?.detail
    return detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : null
  } catch {
    return null
  }
}

export function storyDiagnostic(error, status) {
  const candidate = Number(error?.statusCode ?? error?.status ?? error?.response?.status)
  const errorStatus = safeStatusFromError(error)
  return {
    httpStatus: Number.isInteger(candidate) && candidate >= 400 && candidate <= 599 ? candidate : null,
    code: STORY_STATUS_CODES.has(status?.code)
      ? status.code
      : STORY_STATUS_CODES.has(errorStatus?.code)
        ? errorStatus.code
        : null
  }
}

export function selectedProjectForScope(selection, { profile, connectionId } = {}) {
  if (selection?.profile !== profile || selection?.connectionId !== connectionId) {
    return null
  }
  return selection.projectId || null
}

export function projectSessionRows(data) {
  const rows = Array.isArray(data?.sessions) ? [...data.sessions] : []
  return rows.sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')))
}

export function resetWorkspaceScope(previous, next) {
  const oldScope = [previous?.profile, previous?.connectionId, previous?.sessionId, previous?.projectId].map(value => value || '').join(':')
  const newScope = [next?.profile, next?.connectionId, next?.sessionId, next?.projectId].map(value => value || '').join(':')
  if (oldScope === newScope) return previous
  return {
    profile: next?.profile || 'default',
    connectionId: next?.connectionId || 'local',
    sessionId: next?.sessionId || null,
    projectId: next?.projectId || null,
    tree: null,
    selectedChapterId: null,
    status: 'loading'
  }
}

function storyProfileKey(profile) {
  // Mirror the SDK's normalizeProfileKey: trimmed, empty becomes 'default', so
  // activation targets and host.state.profile compare under one representation.
  const value = typeof profile === 'string' ? profile.trim() : ''
  return value || 'default'
}

export function storyRouteKey(route) {
  // Route identity is the full (connectionId, profile, targetProfile) triple —
  // the same fields the SDK's own route registration matches on. Display names
  // alone never distinguish same-named Profiles on different connections.
  return JSON.stringify([
    typeof route?.connectionId === 'string' && route.connectionId.trim() ? route.connectionId.trim() : null,
    typeof route?.profile === 'string' ? route.profile.trim() : '',
    typeof route?.targetProfile === 'string' ? route.targetProfile.trim() : ''
  ])
}

export async function activateStoryRoute(route, ensureAgent = host.ensureAgent, currentOwner = () => ({
  connectionId: host.state.connectionId.get(),
  profile: host.state.profile.get()
})) {
  if (!route?.profile || typeof ensureAgent !== 'function') throw new Error('story route unavailable')
  // ensureAgent(connectionId, profile) activates one backend route and moves
  // host.state.profile onto that key. The backend's own profile name is the
  // route's targetProfile, so the activation target is targetProfile || profile
  // and the owner check compares against that same key.
  const target = storyProfileKey(route.targetProfile || route.profile)
  await ensureAgent(route.connectionId, target)
  const owner = currentOwner()
  const ownerConnectionId = typeof owner?.connectionId === 'string' ? owner.connectionId.trim() : ''
  const routeConnectionId = typeof route.connectionId === 'string' ? route.connectionId.trim() : ''
  // Owner comparison uses the canonical host.state representation: a registry
  // source id ('local' included) stays itself, and a null connectionId is never
  // coerced into an invented 'local' fallback.
  if (ownerConnectionId !== routeConnectionId || owner?.profile !== target) {
    throw new Error('active route did not match selected story Profile')
  }
}

export function storyScopeMatches(selectionRoute, owner) {
  // Backend authorization scope is (connectionId, backend Profile) only.
  // host.state.profile is the actually activated backend Profile, so the pick
  // is in scope only while it equals the route's targetProfile || profile.
  // The route's own profile is a display alias and never widens the scope:
  // same-backend aliases share one scope exactly while the owner really sits
  // on their shared backend target, and an alias-named owner is a different
  // backend, not the old one.
  if (!selectionRoute) return true
  const ownerConnectionKey = typeof owner?.connectionId === 'string' ? owner.connectionId.trim() : ''
  const selectionConnectionKey = typeof selectionRoute.connectionId === 'string' ? selectionRoute.connectionId.trim() : ''
  if (ownerConnectionKey !== selectionConnectionKey) return false
  return storyProfileKey(owner?.profile) === storyProfileKey(selectionRoute.targetProfile || selectionRoute.profile)
}

export function selectStoryProfileRoute(routes, { profile, connectionId } = {}) {
  if (!Array.isArray(routes)) return null
  const normalizedProfile = typeof profile === 'string' ? profile.trim() : ''
  const normalizedConnectionId = typeof connectionId === 'string' ? connectionId.trim() : ''
  const matchingProfile = route => route?.profile === normalizedProfile || route?.targetProfile === normalizedProfile
  if (normalizedConnectionId) {
    return routes.find(route => matchingProfile(route) && route.connectionId === normalizedConnectionId) || null
  }
  return routes.find(matchingProfile) || null
}

export async function resolveStoryProfileRoute({ profile, connectionId, profileRoutes = host.profileRoutes } = {}) {
  if (typeof profileRoutes !== 'function') return null
  return selectStoryProfileRoute(await profileRoutes(), { profile, connectionId })
}

export async function listStorySessions({
  profile,
  connectionId,
  profileRoutes = host.profileRoutes,
  listPersistedSessions = host.listPersistedSessions
} = {}) {
  const normalizedProfile = typeof profile === 'string' ? profile.trim() : ''
  if (!normalizedProfile) throw new Error('a Hermes profile is required')
  if (typeof listPersistedSessions !== 'function') throw new Error('this Hermes Desktop version cannot list saved sessions')
  const route = await resolveStoryProfileRoute({ profile: normalizedProfile, connectionId, profileRoutes })
  const response = await listPersistedSessions(route, { profile: route?.targetProfile || normalizedProfile, limit: 100 })
  return { route, sessions: Array.isArray(response?.sessions) ? response.sessions : [] }
}

export async function switchStorySession({
  sessionId,
  profile,
  connectionId,
  profileRoutes = host.profileRoutes,
  openSession = host.openSession
} = {}) {
  const normalizedSessionId = typeof sessionId === 'string' ? sessionId.trim() : ''
  const normalizedProfile = typeof profile === 'string' ? profile.trim() : ''
  if (!normalizedSessionId || !normalizedProfile) throw new Error('a session and Hermes profile are required')
  if (typeof openSession !== 'function') throw new Error('this Hermes Desktop version cannot open saved sessions')
  const route = await resolveStoryProfileRoute({ profile: normalizedProfile, connectionId, profileRoutes })
  return openSession(normalizedSessionId, {
    ...(route ? { route } : { profile: normalizedProfile }),
    intent: 'in-place',
    awaitHydration: true,
    expectHistory: true,
    forceResume: true
  })
}

function call(path, options) {
  if (!rest) return Promise.reject(new Error('story workspace API is not ready'))
  return rest(path, options)
}

export function bindWorkspaceApi(restFunction) {
  rest = restFunction
  storySettingsBindingRevision += 1
  return () => {
    if (rest === restFunction) {
      rest = null
      storySettingsBindingRevision += 1
    }
  }
}

export const fetchStoryStatus = () => call('/status')
function storyConnectionQueueKey(connectionId) {
  return typeof connectionId === 'string' && connectionId.trim()
    ? `connection:${connectionId.trim()}`
    : 'connection:unscoped'
}

function enqueueStorySettingsWrite(connectionId, operation) {
  const key = storyConnectionQueueKey(connectionId)
  const tail = storySettingsWriteQueues.get(key) || Promise.resolve()
  const pending = tail.then(operation, operation)
  storySettingsWriteQueues.set(key, pending.then(() => undefined, () => undefined))
  return pending
}

function waitForStorySettingsWrites(connectionId) {
  return storySettingsWriteQueues.get(storyConnectionQueueKey(connectionId)) || Promise.resolve()
}

export function updateStorySettings(profile, {
  connectionId,
  vaultRoot,
  isCurrent = () => true,
  onWriteState = () => {}
} = {}) {
  const queueKey = storyConnectionQueueKey(connectionId)
  const revision = (storySettingsWriteRevisions.get(queueKey) || 0) + 1
  storySettingsWriteRevisions.set(queueKey, revision)
  const bindingRevision = storySettingsBindingRevision
  const body = { profile: storyProfileKey(profile) }
  if (typeof vaultRoot === 'string' && vaultRoot.trim()) body.vault_root = vaultRoot.trim()
  const write = () => {
    if (storySettingsWriteRevisions.get(queueKey) !== revision ||
      storySettingsBindingRevision !== bindingRevision || !isCurrent()) return { superseded: true }
    onWriteState(true)
    return Promise.resolve(call('/settings', { method: 'PUT', body })).finally(() => onWriteState(false))
  }
  return enqueueStorySettingsWrite(connectionId, write)
}

export function storyProfileNeedsSettingsSync(status, profile) {
  if (!status || typeof status !== 'object') return false
  if (status.ready === true) return storyProfileKey(status.locked_profile) !== storyProfileKey(profile)
  return status.code === 'profile_not_selected' || status.code === 'configuration_incomplete'
}

export function storyVaultPathCorrectionAvailable(status, diagnostic) {
  const codes = new Set(['configuration_incomplete', 'vault_not_directory', 'vault_unwritable'])
  return codes.has(status?.code) || codes.has(diagnostic?.code) ||
    (status?.code === 'profile_not_selected' && status.vault_root_configured === false)
}

export function storyWorkspaceGate({
  selectionBlocked = false,
  verifiedCurrent = false,
  statusFailure = false,
  settingsFailure = false,
  settingsWritePending = false,
  status,
  profile
} = {}) {
  return !selectionBlocked && verifiedCurrent && !statusFailure && !settingsFailure && !settingsWritePending &&
    storyReadiness(status, profile).ready
}

export function storySettingsFailureAfterStatus(status, profile, previousFailure) {
  return storyReadiness(status, profile).ready ? null : previousFailure
}

export function storySettingsWritePendingForScope(pending, scope) {
  if (!scope) return false
  const candidates = Array.isArray(pending) ? pending : [pending]
  return candidates.some(candidate =>
    candidate && candidate.owner === scope.owner && candidate.generation === scope.generation
  )
}

function storyScopesWithEntry(entries, scope, include) {
  const current = Array.isArray(entries) ? entries : []
  const remaining = current.filter(entry => !storySettingsWritePendingForScope([entry], scope))
  return include ? [...remaining, scope] : remaining
}

export function storyStatusRequestIsCurrent({
  requestId,
  currentRequestId,
  owner,
  generation,
  currentOwner,
  currentGeneration
} = {}) {
  return requestId !== undefined && requestId === currentRequestId &&
    owner === currentOwner && generation === currentGeneration
}

export async function refreshStoryProfileStatus(profile, {
  connectionId,
  isCurrent = () => true,
  canSyncSettings = true,
  onWriteState = () => {},
  onStatus = () => {},
  syncSettings = updateStorySettings,
  getStatus = fetchStoryStatus
} = {}) {
  const bindingRevision = storySettingsBindingRevision
  const isCurrentOperation = () => storySettingsBindingRevision === bindingRevision && isCurrent()
  await waitForStorySettingsWrites(connectionId)
  if (!isCurrentOperation()) return { status: null, superseded: true, wroteSettings: false }
  const status = await getStatus()
  if (!isCurrentOperation()) return { status: null, superseded: true, wroteSettings: false }
  onStatus(status)
  const maySync = typeof canSyncSettings === 'function' ? canSyncSettings() : canSyncSettings
  if (!maySync || !storyProfileNeedsSettingsSync(status, profile)) {
    return { status, superseded: false, wroteSettings: false }
  }
  const updated = await syncSettings(profile, { connectionId, isCurrent: isCurrentOperation, onWriteState })
  if (updated?.superseded || !isCurrentOperation()) return { status: null, superseded: true, wroteSettings: false }
  const refreshedStatus = await getStatus()
  if (!isCurrentOperation()) return { status: null, superseded: true, wroteSettings: true }
  onStatus(refreshedStatus)
  return { status: refreshedStatus, superseded: false, wroteSettings: true }
}

export async function submitStoryVaultPath(profile, vaultRoot, {
  connectionId,
  isCurrent = () => true,
  onWriteState = () => {},
  syncSettings = updateStorySettings,
  getStatus = fetchStoryStatus
} = {}) {
  const path = typeof vaultRoot === 'string' ? vaultRoot.trim() : ''
  if (!path) throw new Error('Vault path is required')
  const updated = await syncSettings(profile, { connectionId, vaultRoot: path, isCurrent, onWriteState })
  if (updated?.superseded || !isCurrent()) return { status: null, superseded: true }
  return { status: await getStatus(), superseded: false }
}

export const fetchProjects = scope => call('/projects' + buildStoryScopeQuery(scope))
export const createStoryProject = body => call('/projects', { method: 'POST', body })
export const fetchProjectTree = (projectId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + buildStoryScopeQuery(scope))
export const fetchProjectSessions = (projectId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/sessions' + buildStoryScopeQuery(scope))
export const removeStorySession = (projectId, storedSessionId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/sessions/' + encodeURIComponent(storedSessionId) + buildStoryScopeQuery(scope), { method: 'DELETE' })
export const fetchChapter = (projectId, chapterId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/chapters/' + encodeURIComponent(chapterId) + buildStoryScopeQuery(scope))
export const bindStorySession = body => call('/sessions/bind', { method: 'POST', body })
export const saveChapter = (projectId, chapterId, body) =>
  call(`/projects/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(chapterId)}/save`, { method: 'POST', body })

export async function continueStoryProjectSession({
  binding,
  profile,
  connectionId,
  profileRoutes = host.profileRoutes,
  openSession = host.openSession
} = {}) {
  const storedSessionId = requiredSessionId(binding?.stored_session_id, 'stored session')
  try {
    await switchStorySession({
      sessionId: storedSessionId,
      profile,
      connectionId,
      profileRoutes,
      openSession
    })
  } catch (error) {
    if (!isSessionGoneError(error)) throw error
    return { status: 'stale', storedSessionId, error }
  }
  return { status: 'opened', storedSessionId }
}

export async function removeStaleStoryBinding({
  projectId,
  storedSessionId,
  profile,
  connectionId,
  removeSession = removeStorySession
} = {}) {
  const normalizedProjectId = requiredSessionId(projectId, 'project')
  const normalizedStoredId = requiredSessionId(storedSessionId, 'stored session')
  return removeSession(normalizedProjectId, normalizedStoredId, { profile, connectionId })
}

export function buildStoryKickoff({ project, volumes = [], chapters = [] }) {
  const volume = volumes[0] || null
  const chapter = chapters[0] || null
  return [
    'Start a Story Construction writing conversation for this existing project.',
    `project_id: ${project.id}`,
    `project_name: ${project.name}`,
    `volume_id: ${volume?.id || '<choose in conversation>'}`,
    `chapter_id: ${chapter?.id || '<choose in conversation>'}`,
    'First discuss and confirm the chapter title, narrative goal, and output scope with me.',
    'Use only story.* tools for Story Vault context. Do not use terminal, shell, Python, or direct filesystem access.',
    'Do not save a chapter until I explicitly confirm the draft in the Story Construction UI.'
  ].join('\n')
}

function workflowError(stage, error, recovery = null) {
  const wrapped = new Error(error instanceof Error ? error.message : String(error), {
    cause: error instanceof Error ? error : undefined
  })
  wrapped.stage = stage
  wrapped.recovery = recovery
  return wrapped
}

function requiredSessionId(value, label) {
  const normalized = typeof value === 'string' ? value.trim() : ''
  if (!normalized) throw new Error(`${label} id is missing`)
  return normalized
}

function isSessionGoneError(error) {
  const message = String(error?.message || error || '')
  return error?.code === 4001 || error?.code === 4007 || /session (?:not found|not in memory)/i.test(message)
}

async function submitStoryKickoff({
  route,
  runtimeId,
  storedId,
  profile,
  text,
  requestProfile,
  bindSession,
  bindingRequest
}) {
  try {
    await requestProfile(route, 'prompt.submit', { session_id: runtimeId, text })
    return runtimeId
  } catch (error) {
    if (!isSessionGoneError(error)) throw error
    const resumed = await requestProfile(route, 'session.resume', {
      session_id: storedId,
      profile,
      omit_messages: true
    })
    const freshRuntimeId = requiredSessionId(resumed?.session_id, 'resumed runtime session')
    if (typeof bindSession !== 'function' || !bindingRequest) {
      throw new Error('story session binding data is missing')
    }
    await bindSession({ ...bindingRequest, runtime_session_id: freshRuntimeId })
    await requestProfile(route, 'prompt.submit', { session_id: freshRuntimeId, text })
    return freshRuntimeId
  }
}

export async function createStoryWritingSession({
  project,
  profile,
  connectionId,
  profileRoutes = host.profileRoutes,
  retainProfile = host.retainProfile,
  requestProfile = host.requestProfile,
  bindSession = bindStorySession,
  openSession = host.openSession,
  onStage = () => undefined
} = {}) {
  let route
  try {
    route = await resolveStoryProfileRoute({ profile, connectionId, profileRoutes })
    if (!route) throw new Error('the locked Hermes profile route is unavailable')
  } catch (error) {
    throw workflowError('routing', error)
  }

  let release
  try {
    release = typeof retainProfile === 'function' ? await retainProfile(route) : () => undefined
  } catch (error) {
    throw workflowError('creating', error)
  }

  try {
    onStage?.('creating')
    let runtimeId
    let storedId
    try {
      const created = await requestProfile(route, 'session.create', {
        profile: route.targetProfile || profile,
        title: `Story: ${project.name}`,
        follow_profile_config: true
      }, undefined, { spawnPriority: 'foreground' })
      runtimeId = requiredSessionId(created?.session_id, 'runtime session')
      storedId = requiredSessionId(created?.stored_session_id, 'stored session')
    } catch (error) {
      throw workflowError('creating', error)
    }

    onStage?.('binding')
    let binding
    const bindingRequest = {
      session_id: storedId,
      stored_session_id: storedId,
      runtime_session_id: runtimeId,
      profile,
      connection_id: connectionId,
      project_id: project.id,
      project_name: project.name,
      title: `Story: ${project.name}`
    }
    try {
      binding = await bindSession(bindingRequest)
    } catch (error) {
      throw workflowError('binding', error)
    }

    try {
      await requestProfile(route, 'session.title', { session_id: runtimeId, title: `Story: ${project.name}` })
    } catch {
      // Older gateways persist the row on prompt.submit instead.
    }

    onStage?.('submitting')
    let text
    let liveRuntimeId
    try {
      text = buildStoryKickoff(binding.context)
      liveRuntimeId = await submitStoryKickoff({
        route,
        runtimeId,
        storedId,
        profile,
        text,
        requestProfile,
        bindSession,
        bindingRequest
      })
    } catch (error) {
      throw workflowError('submitting', error, {
        route,
        runtimeId,
        storedId,
        profile,
        text,
        bindingRequest
      })
    }

    onStage?.('opening')
    try {
      await openSession(storedId, {
        route,
        intent: 'in-place',
        awaitHydration: true,
        expectHistory: true,
        forceResume: true
      })
    } catch (error) {
      throw workflowError('opening', error)
    }
    onStage?.('ready')
    return { storedSessionId: storedId, runtimeSessionId: liveRuntimeId, binding }
  } finally {
    if (typeof release === 'function') release()
  }
}

export async function retryStoryKickoff({
  recovery,
  requestProfile = host.requestProfile,
  bindSession = bindStorySession,
  openSession = host.openSession
} = {}) {
  if (!recovery?.route || !recovery?.storedId || !recovery?.runtimeId || !recovery?.text) {
    throw workflowError('submitting', new Error('story kickoff recovery data is incomplete'))
  }

  let liveRuntimeId
  try {
    liveRuntimeId = await submitStoryKickoff({ ...recovery, requestProfile, bindSession })
  } catch (error) {
    throw workflowError('submitting', error, recovery)
  }

  try {
    await openSession(recovery.storedId, {
      route: recovery.route,
      intent: 'in-place',
      awaitHydration: true,
      expectHistory: true,
      forceResume: true
    })
  } catch (error) {
    throw workflowError('opening', error)
  }
  return { storedSessionId: recovery.storedId, runtimeSessionId: liveRuntimeId }
}

export function canConfirmSave({ draft, confirmed }) {
  return confirmed === true && typeof draft === 'string' && draft.trim().length > 0
}

export function buildSaveRequest({ sessionId, profile, connectionId = 'local', projectId, chapterId, content, expectedVersion }) {
  if (![sessionId, profile, connectionId, projectId, chapterId, expectedVersion].every(value => typeof value === 'string' && value.trim())) {
    throw new Error('save request scope and version are required')
  }
  if (typeof content !== 'string') throw new Error('save content must be a string')
  return {
    session_id: sessionId,
    profile,
    connection_id: connectionId,
    project_id: projectId,
    chapter_id: chapterId,
    content,
    expected_version: expectedVersion,
    confirmed: true
  }
}

function withTimeout(operation, timeoutMs, label) {
  let timer
  const operationPromise = Promise.resolve().then(operation)
  const timeoutPromise = new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out`)), timeoutMs)
  })
  return Promise.race([operationPromise, timeoutPromise]).finally(() => clearTimeout(timer))
}

export function storyChapterSaveGate() {
  // Owns the identity of the one in-flight chapter save. begin() binds a fresh
  // token to the submitting scope; reset() drops the token on any scope change
  // or editor teardown; isActive() accepts a completion only while its token
  // still owns the gate AND the editor scope still matches. After A→B→A the
  // returning A scope is a NEW generation — reset() already dropped the old
  // token — so a late A save can never re-claim the gate just because the
  // scope string matches again.
  let token = null
  let scope = null
  return {
    begin(nextScope) {
      token = Symbol('chapter-save')
      scope = nextScope
      return token
    },
    reset() {
      token = null
      scope = null
    },
    isActive(candidate, currentScope) {
      return token === candidate && scope === currentScope
    },
    isPending(candidateScope) {
      return token !== null && scope === candidateScope
    }
  }
}

function persistedChapterContent(refreshResult) {
  // The post-save refresh confirms what actually reached the Vault. Pull
  // chapter.content out of the query-shaped refetch result the same way the
  // editor reads chapter data, so the success path rebaselines to persisted
  // bytes — server normalization included — and never to the submitted bytes.
  const payload = refreshResult?.data ?? refreshResult
  const chapter = payload?.chapter ?? payload
  return typeof chapter?.content === 'string' ? chapter.content : null
}

export async function runChapterSave({ save, refetch, isActive, onSaved, onFailed, timeoutMs = 30_000 }) {
  try {
    await withTimeout(save, timeoutMs, 'save request')
    if (!isActive()) return false
    const refreshResult = await withTimeout(refetch, timeoutMs, 'chapter refresh')
    if (refreshResult?.isError || refreshResult?.error) {
      throw refreshResult.error || new Error('chapter refresh failed')
    }
    if (!isActive()) return false
    // Hand the success callback the content the refresh confirmed persisted.
    onSaved(persistedChapterContent(refreshResult))
    return true
  } catch (error) {
    if (!isActive()) return false
    onFailed(error)
    return false
  }
}

export function shouldHydrateChapterDraft({ saveSnapshot, scope }) {
  // A pending save snapshot for this scope means this refresh belongs to a
  // save whose completion rebaselines to the persisted content and keeps the
  // current edits. Hydration must not run over that: the on-screen text may
  // still equal the submitted bytes while the persisted result differs (a
  // submitted 'B\n' persisting as 'B'), and that difference stays unsaved.
  return !(saveSnapshot?.scope === scope)
}

export function buildDiffState(original, draft) {
  return { original, draft, changed: original !== draft, status: 'draft' }
}

export function preserveSaveConflict(state, payload) {
  return {
    ...state,
    original: payload?.current || payload?.chapter || state.original,
    status: 'conflict'
  }
}

function projectRows(data) {
  return Array.isArray(data) ? data : Array.isArray(data?.projects) ? data.projects : []
}

export function filterStoryProjects(rows, term) {
  // Local, display-only filtering over whatever the list endpoint returned:
  // rows without a usable id/name are dropped as invalid, and the term matches
  // the returned name or id case-insensitively. Never a backend search.
  const query = String(term || '').trim().toLocaleLowerCase()
  return projectRows(rows)
    .filter(item => item && typeof item.id === 'string' && item.id.trim() && typeof item.name === 'string' && item.name.trim())
    .filter(item => !query || [item.id, item.name].some(value => value.toLocaleLowerCase().includes(query)))
}

export function newProjectFailureState(draft, error) {
  // A failed create keeps the caller's draft and carries only a whitelisted
  // diagnostic; raw error text never reaches the dialog.
  return { draft, failed: true, diagnostic: storyDiagnostic(error, null) }
}

export function storyLayoutMode(width) {
  // Container-width breakpoints for the project workspace: wide keeps a fixed
  // tree, a stretchable editor and a fixed sessions column; compact keeps the
  // editor unsqueezed beside the tree with a collapsible sessions area; narrow
  // stacks the tree above the editor.
  return width >= 980 ? 'wide' : width >= 560 ? 'compact' : 'narrow'
}

export function storyWorkspaceSurface(projectId) {
  // The tree/editor/sessions workspace exists only for a selected project;
  // every other case stays on the project library page.
  return projectId ? 'workspace' : 'library'
}

export function storyDraftKey({ connectionId, profile, sessionId, projectId, chapterId }) {
  // One key per five-part scope: different Profile, connection, session,
  // project or chapter never share a draft. Identity only — no normalization —
  // so two distinct scopes can never collapse into one entry.
  return JSON.stringify([connectionId, profile, sessionId, projectId, chapterId])
}

export function retainStoryDraft(store, key, draft, baseline) {
  // Page-lifetime draft map update: a draft equal to its baseline is clean and
  // drops its entry; anything else is retained under its own scope key. Always
  // returns a new Map so React state updates stay predictable.
  const next = new Map(store)
  if (draft === baseline) next.delete(key)
  else next.set(key, draft)
  return next
}

export function storyDraftAfterSave({ draft, savedContent }) {
  // A successful save rebaselines to the content THIS save confirmed and
  // leaves the visible text alone: the remaining unsaved work is whatever is
  // on screen now compared against the new baseline. Reverting to the old
  // text during the save therefore stays unsaved, and later edits are never
  // overwritten by the completion.
  return { draft, baseline: savedContent, dirty: draft !== savedContent }
}

export function canLeaveStoryWorkspace({ dirty, saving, confirmLeave }) {
  // Plugin-initiated leave: never mid-save; a dirty draft needs an explicit
  // confirmation, and cancel keeps project, chapter and draft untouched.
  return !saving && (!dirty || confirmLeave())
}

function retainedStoryDraftExists(store, matches) {
  // store keys are storyDraftKey JSON arrays; the slot shape of a key matches
  // JSON semantics — an undefined part serializes as null.
  for (const key of store.keys()) {
    let parts
    try {
      parts = JSON.parse(key)
    } catch {
      continue
    }
    if (matches(parts)) return true
  }
  return false
}

const draftSlot = value => (value === undefined ? null : value)

export function displayName(item, t) {
  return item?.title || item?.name || item?.id || t('tree.untitled')
}

function ProjectBranch({ branch, onOpenChapter, t }) {
  const children = branch.children.map(child => {
    const isChapter = branch.id === 'chapters'
    return jsx(
      'button',
      {
        className: 'block w-full truncate rounded px-2 py-1 text-left text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)',
        onClick: isChapter ? () => onOpenChapter(child.id) : undefined,
        type: 'button',
        children: displayName(child, t)
      },
      child.id
    )
  })

  return jsxs('details', {
    className: 'border-b border-(--ui-stroke-secondary) py-1',
    open: branch.id === 'project' || branch.id === 'chapters',
    children: [
      jsx('summary', { className: 'cursor-pointer px-2 py-1 font-medium', children: branch.label }),
      jsx('div', {
        className: 'pl-2',
        children: children.length
          ? children
          : jsx('span', { className: 'px-2 text-(--ui-text-tertiary)', children: t('tree.empty') })
      })
    ]
  }, branch.id)
}

function ProjectTree({ tree, onOpenChapter, t }) {
  if (!tree) {
    return jsx('div', { className: 'p-3 text-(--ui-text-tertiary)', children: t('tree.selectProject') })
  }
  return jsx('div', {
    className: 'min-h-0 flex-1 overflow-auto',
    children: tree.branches.map(branch => jsx(ProjectBranch, { branch, onOpenChapter, t }, branch.id))
  })
}

function ChapterEditor({ projectId, chapterId, profile, connectionId, sessionId, draftStore, onDraftState }) {
  const t = usePluginI18n('story-construction')
  const chapterQuery = useQuery({
    enabled: Boolean(projectId && chapterId && sessionId && profile && connectionId),
    queryKey: ['story-construction', 'chapter', profile, connectionId, sessionId, projectId, chapterId],
    queryFn: () => fetchChapter(projectId, chapterId, { sessionId, profile, connectionId })
  })
  const chapter = chapterQuery.data?.chapter || chapterQuery.data || null
  const [draft, setDraft] = useState('')
  const [baseline, setBaseline] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [saveState, setSaveState] = useState(null)
  const [saving, setSaving] = useState(false)
  const scope = [profile, connectionId, sessionId, projectId, chapterId].map(value => value || '').join(':')
  const draftKey = storyDraftKey({ connectionId, profile, sessionId, projectId, chapterId })
  const currentScopeRef = useMutableRef(scope)
  const draftValueRef = useMutableRef('')
  const baselineRef = useMutableRef('')
  const draftRevisionRef = useMutableRef(0)
  const saveSnapshotRef = useMutableRef(null)
  const saveGateRef = useMutableRef(null)
  if (!saveGateRef.current) saveGateRef.current = storyChapterSaveGate()
  currentScopeRef.current = scope
  draftValueRef.current = draft
  baselineRef.current = baseline

  useEffect(() => {
    saveGateRef.current.reset()
    saveSnapshotRef.current = null
    draftRevisionRef.current = 0
    setDraft('')
    setBaseline('')
    setConfirmed(false)
    setSaveState(null)
    setSaving(false)
    // Scope change reports only the saving flag for the NEW key: a retained
    // draft entry for this key must survive untouched for the restore below.
    onDraftState?.({ key: draftKey, saving: false })
    return () => {
      saveGateRef.current.reset()
      saveSnapshotRef.current = null
      // Unmount/scope-change teardown drops the saving flag too: a save that
      // lost its gate can never settle the UI, so it must not keep leave
      // protection blocked forever.
      onDraftState?.({ key: draftKey, saving: false })
    }
  }, [profile, connectionId, sessionId, projectId, chapterId])

  useEffect(() => {
    if (!chapter || chapter.id !== chapterId) return
    const saveSnapshot = saveSnapshotRef.current
    if (!shouldHydrateChapterDraft({ saveSnapshot, scope })) {
      // This refresh belongs to a save whose completion already rebaselined
      // to the persisted content and kept the current edits — hydrating over
      // it would erase the unpersisted difference (e.g. a submitted 'B\n'
      // that persisted as 'B'). Consume the snapshot for this scope.
      saveSnapshotRef.current = null
      return
    }
    const content = chapter.content || ''
    // Restore the retained dirty draft for this exact five-part scope once its
    // chapter data returns; a clean scope hydrates from the server content.
    const retained = draftStore?.current?.get(draftKey)
    const nextDraft = retained !== undefined ? retained : content
    setDraft(nextDraft)
    setBaseline(content)
    setConfirmed(false)
    setSaveState(null)
    onDraftState?.({ key: draftKey, draft: nextDraft, baseline: content, saving: false })
  }, [scope, chapter?.id, chapter?.version])

  if (!chapterId) {
    // The empty state spans and centers across the whole editor column, so the
    // workspace reads as one focused editing surface instead of a corner note.
    return jsx('div', {
      className: 'flex min-h-0 flex-1 items-center justify-center px-4 text-center text-(--ui-text-tertiary)',
      children: t('chapter.openPrompt')
    })
  }
  if (chapterQuery.isLoading) {
    return jsx('div', { className: 'p-4 text-(--ui-text-secondary)', children: t('chapter.loading') })
  }
  if (chapterQuery.error) {
    return jsx('div', {
      className: 'p-4 text-(--ui-text-secondary)',
      children: t('chapter.unavailable', chapterQuery.error.message)
    })
  }

  const save = () => {
    if (saveGateRef.current.isPending(scope)) return
    if (!canConfirmSave({ draft, confirmed })) return
    let request
    try {
      request = buildSaveRequest({
        sessionId,
        profile,
        connectionId,
        projectId,
        chapterId,
        content: draft,
        expectedVersion: chapter.version
      })
    } catch (error) {
      setSaveState({ key: 'chapter.saveUnavailable', args: [error.message] })
      return
    }
    const token = saveGateRef.current.begin(scope)
    saveSnapshotRef.current = { scope, revision: draftRevisionRef.current }
    setSaveState({ key: 'chapter.saving', args: [] })
    setSaving(true)
    onDraftState?.({ key: draftKey, draft: draftValueRef.current, baseline: baselineRef.current, saving: true })
    const isActive = () => saveGateRef.current.isActive(token, currentScopeRef.current)
    void runChapterSave({
      save: () => saveChapter(projectId, chapterId, request),
      refetch: () => chapterQuery.refetch(),
      isActive,
      onSaved: persisted => {
        saveGateRef.current.reset()
        setSaving(false)
        setConfirmed(false)
        setSaveState({ key: 'chapter.saved', args: [] })
        // Save success rebaselines to the content the post-save refresh
        // CONFIRMED persisted — server normalization included — and recomputes
        // the draft as "current edits vs that baseline": text typed, reverted
        // or otherwise left unpersisted during the save stays unsaved and on
        // screen, and is never overwritten by the completion.
        const settled = storyDraftAfterSave({
          draft: draftValueRef.current,
          savedContent: typeof persisted === 'string' ? persisted : request.content
        })
        setBaseline(settled.baseline)
        onDraftState?.({ key: draftKey, draft: settled.draft, baseline: settled.baseline, saving: false })
      },
      onFailed: error => {
        saveGateRef.current.reset()
        setSaving(false)
        setSaveState({ key: 'chapter.saveFailed', args: [error.message] })
        // Failure and version conflict keep the draft: re-report it so the
        // retained entry definitely survives the save lifecycle.
        onDraftState?.({ key: draftKey, draft: draftValueRef.current, baseline: baselineRef.current, saving: false })
      }
    })
  }

  return jsxs('section', {
    className: 'flex min-h-0 min-w-0 flex-1 flex-col gap-2 p-4',
    children: [
      jsx('div', {
        className: 'flex items-center justify-between gap-2',
        children: jsx('h2', {
          className: 'min-w-0 flex-1 truncate text-base font-medium',
          title: chapter.title || chapter.id,
          children: chapter.title || chapter.id
        })
      }),
      jsx('p', { className: 'break-words text-xs text-(--ui-text-tertiary)', children: t('chapter.version', chapter.version) }),
      jsx('textarea', {
        className: 'hermes-story-focus min-h-0 flex-1 resize-none rounded border border-(--ui-stroke-secondary) bg-transparent p-3 font-mono text-sm outline-none',
        value: draft,
        onChange: event => {
          draftRevisionRef.current += 1
          const value = event.target.value
          setDraft(value)
          onDraftState?.({ key: draftKey, draft: value, baseline: baselineRef.current, saving })
        },
        spellCheck: false
      }),
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-2',
        children: [
          jsx('label', {
            className: 'flex items-center gap-2 text-xs text-(--ui-text-secondary)',
            children: [
              jsx('input', { type: 'checkbox', checked: confirmed, onChange: event => setConfirmed(event.target.checked) }),
              t('chapter.confirmOverwrite')
            ]
          }),
          jsx('button', {
            className: 'rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
            disabled: saving || !canConfirmSave({ draft, confirmed }) || !sessionId,
            onClick: save,
            type: 'button',
            children: t('chapter.saveConfirmed')
          }),
          saveState
            ? jsx('span', {
                className: 'text-xs text-(--ui-text-tertiary)',
                children: t(saveState.key, ...saveState.args)
              })
            : null
        ]
      })
    ]
  })
}

function BookIcon() {
  // One shared book glyph for every library card — no per-project art exists.
  return jsx('svg', {
    'aria-hidden': 'true',
    className: 'h-5 w-5 shrink-0 text-(--ui-text-tertiary)',
    fill: 'none',
    stroke: 'currentColor',
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    strokeWidth: '1.5',
    viewBox: '0 0 24 24',
    children: jsx('path', {
      d: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z'
    })
  })
}

function NewProjectDialog({ profile, connectionId, ready, onCreated, onClose, getGeneration, t }) {
  const [draft, setDraft] = useState({ name: '', slug: '' })
  const [creating, setCreating] = useState(false)
  const [failure, setFailure] = useState(null)
  // Completion acts only while this dialog instance is still mounted: a POST
  // that outlived its dialog must never clear inputs or close a newer view.
  // Setup marks the instance alive again so StrictMode's setup→cleanup→setup
  // remount probe ends alive; only a real unmount's final cleanup flips it.
  const aliveRef = useMutableRef(true)
  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
    }
  }, [])

  const submit = event => {
    event.preventDefault()
    // Submitting is gated on the ready state of the CURRENT Profile/connection:
    // an open dialog can never create through an unverified or mismatched backend.
    if (creating || !ready || !profile || !connectionId) return
    let normalized
    try {
      normalized = normalizeProjectDraft(draft)
    } catch {
      setFailure({ reason: 'validation', diagnostic: { httpStatus: null, code: null } })
      return
    }
    // Capture the request scope AND the view generation at POST start. The
    // generation moves on every owner switch — including A→B→A landing back on
    // the same Profile — so a late completion is checked against the view it
    // was issued from, never against "the Profile is A again".
    const requestScope = { profile, connectionId }
    const requestGeneration = typeof getGeneration === 'function' ? getGeneration() : null
    const requestLive = () => aliveRef.current &&
      (requestGeneration === null || requestGeneration === (typeof getGeneration === 'function' ? getGeneration() : null))
    setCreating(true)
    setFailure(null)
    void createStoryProject({
      ...normalized,
      profile,
      connection_id: connectionId
    })
      .then(async created => {
        const projectId = requiredSessionId(created?.tree?.project?.id, 'created project')
        if (!requestLive()) return
        await onCreated(projectId, { ...requestScope, generation: requestGeneration })
        if (!requestLive()) return
        setDraft({ name: '', slug: '' })
        onClose()
      })
      .catch(error => {
        // A failed create keeps every input and reports only generic copy plus
        // the whitelisted diagnostic — never error.message or IPC JSON.
        if (!requestLive()) return
        setFailure(newProjectFailureState(draft, error))
      })
      .finally(() => {
        if (!requestLive()) return
        setCreating(false)
      })
  }

  return jsx('div', {
    className: 'hermes-story-overlay fixed inset-0 z-50 flex items-center justify-center p-4',
    onMouseDown: event => {
      if (event.target === event.currentTarget && !creating) onClose()
    },
    children: jsxs('form', {
      'aria-labelledby': 'story-new-project-title',
      'aria-modal': 'true',
      className: 'flex w-full max-w-sm flex-col gap-3 rounded border border-(--ui-stroke-secondary) p-4 shadow',
      // Host theme surface with a system-color fallback so the panel stays
      // readable in both themes without inventing a new design token.
      style: { backgroundColor: 'var(--chrome-bg, var(--ui-bg, Canvas))' },
      onKeyDown: event => {
        if (event.key === 'Escape' && !creating) onClose()
      },
      onSubmit: submit,
      role: 'dialog',
      children: [
        jsx('h2', {
          className: 'text-base font-medium',
          id: 'story-new-project-title',
          children: t('workspace.newProject')
        }),
        jsxs('label', {
          className: 'flex flex-col gap-1 text-xs text-(--ui-text-secondary)',
          children: [
            t('workspace.projectName'),
            jsx('input', {
              autoFocus: true,
              className: 'rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs',
              disabled: creating,
              value: draft.name,
              onChange: event => setDraft(previous => ({ ...previous, name: event.target.value }))
            })
          ]
        }),
        jsxs('label', {
          className: 'flex flex-col gap-1 text-xs text-(--ui-text-secondary)',
          children: [
            t('workspace.projectSlug'),
            jsx('input', {
              className: 'rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs',
              disabled: creating,
              value: draft.slug,
              onChange: event => setDraft(previous => ({ ...previous, slug: event.target.value }))
            })
          ]
        }),
        failure
          ? jsxs('div', {
              className: 'text-xs text-(--ui-text-secondary)',
              role: 'alert',
              children: [
                failure.reason === 'validation' ? t('dialog.nameRequired') : t('dialog.createFailed'),
                Number.isInteger(failure.diagnostic?.httpStatus)
                  ? ` · ${t('status.httpStatus', failure.diagnostic.httpStatus)}`
                  : null
              ]
            })
          : null,
        jsxs('div', {
          className: 'flex justify-end gap-2',
          children: [
            jsx('button', {
              className: 'rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
              disabled: creating,
              onClick: onClose,
              type: 'button',
              children: t('dialog.cancel')
            }),
            jsx('button', {
              className: 'hermes-story-btn-primary rounded bg-(--ui-accent) px-3 py-1 text-xs disabled:opacity-50',
              disabled: creating || !ready || !profile || !connectionId,
              type: 'submit',
              children: creating ? t('workspace.creatingProject') : t('workspace.createProject')
            })
          ]
        })
      ]
    })
  })
}

function ProjectLibrary({ projects, loading, error, ready, profile, connectionId, onOpen, onRetry, onCreated, getGeneration, t }) {
  const [term, setTerm] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const valid = filterStoryProjects(projects, '')
  const visible = filterStoryProjects(projects, term)
  // List failures render fixed copy plus, at most, whitelisted diagnostics from
  // storyDiagnostic — never raw error.message, IPC JSON, Vault paths, tokens or
  // server messages.
  const listDiagnostic = error ? storyDiagnostic(error, null) : null
  const listDetails = []
  if (listDiagnostic && Number.isInteger(listDiagnostic.httpStatus)) {
    listDetails.push(t('status.httpStatus', listDiagnostic.httpStatus))
  }
  if (listDiagnostic?.code) listDetails.push(t('status.code', listDiagnostic.code))

  return jsxs('div', {
    className: 'flex min-h-0 flex-1 flex-col gap-3 p-4',
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-3',
        children: [
          jsx('button', {
            className: 'hermes-story-btn-primary rounded bg-(--ui-accent) px-3 py-1 text-xs disabled:opacity-50',
            disabled: !ready,
            onClick: () => setDialogOpen(true),
            type: 'button',
            children: t('workspace.newProject')
          }),
          jsxs('label', {
            className: 'flex min-w-40 flex-1 items-center gap-2 text-xs text-(--ui-text-secondary)',
            children: [
              jsx('span', { className: 'shrink-0', children: t('library.search') }),
              jsx('input', {
                className: 'w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs',
                placeholder: t('library.searchPlaceholder'),
                type: 'search',
                value: term,
                onChange: event => setTerm(event.target.value)
              })
            ]
          })
        ]
      }),
      loading
        ? jsx('div', { className: 'text-(--ui-text-secondary)', children: t('workspace.loadingProjects') })
        : error
          ? jsxs('div', {
              className: 'flex flex-col items-start gap-2 rounded border border-(--ui-stroke-secondary) p-3 text-(--ui-text-secondary)',
              children: [
                jsx('span', { children: t('workspace.projectsUnavailable') }),
                jsx('button', {
                  className: 'rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover)',
                  onClick: onRetry,
                  type: 'button',
                  children: t('status.retry')
                }),
                listDetails.length
                  ? jsxs('details', {
                      className: 'text-xs text-(--ui-text-tertiary)',
                      children: [
                        jsx('summary', { className: 'cursor-pointer', children: t('status.details') }),
                        jsx('div', { className: 'mt-1 break-words', children: listDetails.join(' · ') })
                      ]
                    })
                  : null
              ]
            })
          : !valid.length
            ? jsxs('div', {
                className: 'flex flex-col items-start gap-3 rounded border border-(--ui-stroke-secondary) p-4',
                children: [
                  jsx('p', { className: 'text-(--ui-text-secondary)', children: t('library.empty') }),
                  jsx('button', {
                    className: 'hermes-story-btn-primary rounded bg-(--ui-accent) px-3 py-1 text-xs disabled:opacity-50',
                    disabled: !ready,
                    onClick: () => setDialogOpen(true),
                    type: 'button',
                    children: t('workspace.newProject')
                  })
                ]
              })
            : !visible.length
              ? jsx('div', {
                  className: 'rounded border border-(--ui-stroke-secondary) p-4 text-(--ui-text-secondary)',
                  children: t('library.noMatch')
                })
              : jsx('div', {
                  className: 'hermes-story-library-grid',
                  children: visible.map(item => jsxs('button', {
                    className: 'flex items-center gap-3 rounded border border-(--ui-stroke-secondary) p-3 text-left hover:bg-(--chrome-action-hover)',
                    onClick: () => onOpen(item.id),
                    type: 'button',
                    children: [
                      jsx(BookIcon, {}),
                      jsxs('span', {
                        className: 'min-w-0 flex-1',
                        children: [
                          jsx('span', { className: 'block truncate text-sm', children: item.name }),
                          jsx('span', { className: 'block truncate text-xs text-(--ui-text-tertiary)', children: item.id })
                        ]
                      })
                    ]
                  }, item.id))
                }),
      dialogOpen
        ? jsx(NewProjectDialog, {
            connectionId,
            onClose: () => setDialogOpen(false),
            onCreated,
            getGeneration,
            profile,
            ready,
            t
          })
        : null
    ]
  })
}

const SESSION_STAGE_KEYS = {
  creating: 'agent.stageCreating',
  binding: 'agent.stageBinding',
  submitting: 'agent.stageSubmitting',
  opening: 'agent.stageOpening',
  ready: 'agent.stageReady'
}

function ProjectSessionsPanel({ profile, connectionId, project, sessionId }) {
  const t = usePluginI18n('story-construction')
  const busy = useValue(host.state.busy)
  const [bindingState, setBindingState] = useState(null)
  const [sessionState, setSessionState] = useState(null)
  const [creatingSession, setCreatingSession] = useState(false)
  const [kickoffRecovery, setKickoffRecovery] = useState(null)
  const [staleSessionIds, setStaleSessionIds] = useState({})
  const sessionsQuery = useQuery({
    enabled: Boolean(project?.id && profile && connectionId),
    queryKey: ['story-construction', 'project-sessions', profile, connectionId, project?.id],
    queryFn: () => fetchProjectSessions(project.id, { profile, connectionId }),
    refetchInterval: 60_000
  })
  const sessions = projectSessionRows(sessionsQuery.data)

  useEffect(() => {
    setBindingState(null)
    setSessionState(null)
    setKickoffRecovery(null)
    setStaleSessionIds({})
  }, [project?.id, profile, connectionId])

  const setStage = stage => {
    const key = SESSION_STAGE_KEYS[stage]
    if (key) setSessionState({ key, args: [] })
  }

  const openAfterRefetch = async (...args) => {
    setStage('opening')
    await sessionsQuery.refetch()
    if (typeof host.openSession !== 'function') {
      throw new Error('this Hermes Desktop version cannot open saved sessions')
    }
    return host.openSession(...args)
  }

  const createSession = () => {
    if (creatingSession || !project?.id) return
    setCreatingSession(true)
    setKickoffRecovery(null)
    setSessionState(null)
    void createStoryWritingSession({
      project,
      profile,
      connectionId,
      onStage: setStage,
      openSession: openAfterRefetch
    })
      .then(() => setStage('ready'))
      .catch(error => {
        if (error.stage === 'submitting' && error.recovery) {
          setKickoffRecovery(error.recovery)
          void sessionsQuery.refetch()
        }
        setSessionState({ key: 'agent.sessionFailed', args: [error.message] })
      })
      .finally(() => setCreatingSession(false))
  }

  const retryKickoff = () => {
    if (creatingSession || !kickoffRecovery) return
    setCreatingSession(true)
    setStage('submitting')
    void retryStoryKickoff({ recovery: kickoffRecovery, openSession: openAfterRefetch })
      .then(() => {
        setKickoffRecovery(null)
        setStage('ready')
      })
      .catch(error => {
        if (error.stage === 'submitting' && error.recovery) setKickoffRecovery(error.recovery)
        setSessionState({ key: 'agent.sessionFailed', args: [error.message] })
      })
      .finally(() => setCreatingSession(false))
  }

  const continueSession = binding => {
    if (creatingSession) return
    setCreatingSession(true)
    setStage('opening')
    void continueStoryProjectSession({ binding, profile, connectionId })
      .then(result => {
        if (result.status === 'stale') {
          setStaleSessionIds(previous => ({ ...previous, [result.storedSessionId]: true }))
          setSessionState({ key: 'agent.staleBinding', args: [] })
          return
        }
        setStage('ready')
      })
      .catch(error => setSessionState({ key: 'agent.continueFailed', args: [error.message] }))
      .finally(() => setCreatingSession(false))
  }

  const removeStale = storedSessionId => {
    if (creatingSession || !project?.id) return
    setCreatingSession(true)
    void removeStaleStoryBinding({
      projectId: project.id,
      storedSessionId,
      profile,
      connectionId
    })
      .then(async () => {
        await sessionsQuery.refetch()
        setStaleSessionIds(previous => {
          const next = { ...previous }
          delete next[storedSessionId]
          return next
        })
        setStage('ready')
      })
      .catch(error => setSessionState({ key: 'agent.removeFailed', args: [error.message] }))
      .finally(() => setCreatingSession(false))
  }

  const bind = () => {
    if (creatingSession || !sessionId || !project?.id) return
    setCreatingSession(true)
    setBindingState({ key: 'agent.binding', args: [] })
    void bindStorySession({
      session_id: sessionId,
      profile,
      connection_id: connectionId,
      project_id: project.id,
      project_name: project.name
    })
      .then(async () => {
        await sessionsQuery.refetch()
        setBindingState({ key: 'agent.bound', args: [] })
      })
      .catch(error => setBindingState({ key: 'agent.bindFailed', args: [error.message] }))
      .finally(() => setCreatingSession(false))
  }

  return jsxs('aside', {
    // Docked, stacked, capped or hidden geometry all comes from the
    // .hermes-story-sessions* CSS variants of the parent region: the panel
    // stays mounted in every layout mode and collapsed state so in-flight
    // creation and kickoffRecovery survive collapse/expand and width switches.
    className: 'hermes-story-sessions-panel',
    children: [
      jsx('div', { className: 'font-medium', children: t('agent.title') }),
      jsx('div', {
        className: 'break-words text-(--ui-text-secondary)',
        children: `${busy ? t('agent.working') : t('agent.idle')} · ${sessionId || t('agent.noFocusedSession')}`
      }),
      jsx('div', { className: 'font-medium', children: t('agent.sessions') }),
      jsx('button', {
        className: 'hermes-story-btn-primary rounded bg-(--ui-accent) px-2 py-1 text-left disabled:opacity-50',
        disabled: creatingSession || !project?.id,
        onClick: createSession,
        type: 'button',
        children: t('agent.newWritingSession')
      }),
      sessionsQuery.isLoading
        ? jsx('div', { className: 'text-(--ui-text-tertiary)', children: t('agent.loadingSessions') })
        : sessionsQuery.error
          ? jsx('div', {
              className: 'text-(--ui-text-tertiary)',
              children: t('agent.sessionsUnavailable', sessionsQuery.error.message)
            })
          : !sessions.length
            ? jsx('div', { className: 'text-(--ui-text-tertiary)', children: t('agent.noSessions') })
            : jsx('div', {
                className: 'flex flex-col gap-2',
                children: sessions.map(binding => {
                  const storedSessionId = binding.stored_session_id
                  const stale = Boolean(staleSessionIds[storedSessionId])
                  return jsxs('div', {
                    className: 'rounded border border-(--ui-stroke-secondary) p-2',
                    children: [
                      jsx('div', {
                        className: 'truncate',
                        children: binding.title || storedSessionId
                      }),
                      jsxs('div', {
                        className: 'mt-1 flex flex-wrap gap-2',
                        children: [
                          jsx('button', {
                            className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hover:bg-(--chrome-action-hover) disabled:opacity-50',
                            disabled: creatingSession,
                            onClick: () => continueSession(binding),
                            type: 'button',
                            children: t('agent.continueSession')
                          }),
                          stale
                            ? jsx('button', {
                                className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hover:bg-(--chrome-action-hover) disabled:opacity-50',
                                disabled: creatingSession,
                                onClick: () => removeStale(storedSessionId),
                                type: 'button',
                                children: t('agent.removeStaleBinding')
                              })
                            : null
                        ]
                      })
                    ]
                  }, storedSessionId)
                })
              }),
      kickoffRecovery
        ? jsx('button', {
            className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 text-left hover:bg-(--chrome-action-hover) disabled:opacity-50',
            disabled: creatingSession,
            onClick: retryKickoff,
            type: 'button',
            children: t('agent.retryFirstTask')
          })
        : null,
      sessionState
        ? jsx('div', {
            className: 'break-words text-(--ui-text-tertiary)',
            children: t(sessionState.key, ...sessionState.args)
          })
        : null,
      jsx('button', {
        className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 text-left hover:bg-(--chrome-action-hover) disabled:opacity-50',
        disabled: creatingSession || !sessionId || !project?.id,
        onClick: bind,
        type: 'button',
        children: t('agent.bindFocusedSession')
      }),
      bindingState
        ? jsx('div', {
            className: 'break-words text-(--ui-text-tertiary)',
            children: t(bindingState.key, ...bindingState.args)
          })
        : null
    ]
  })
}

const STORY_STATUS_MESSAGE_KEYS = {
  runtime_uninitialized: 'status.runtime_uninitialized',
  configuration_incomplete: 'status.configuration_incomplete',
  profile_not_selected: 'status.profile_not_selected',
  agent_not_installed: 'status.agent_not_installed',
  agent_not_enabled: 'status.agent_not_enabled',
  hermes_home_mismatch: 'status.hermes_home_mismatch',
  vault_not_directory: 'status.vault_not_directory',
  vault_unwritable: 'status.vault_unwritable',
  profile_mismatch: 'status.profile_mismatch',
  unavailable: 'status.unavailable'
}

function StoryStatusCard({
  mode,
  code,
  diagnostic,
  onRetry,
  vaultSetup = false,
  vaultRoot = '',
  savingVaultRoot = false,
  onVaultRootChange,
  onSubmitVaultRoot,
  t
}) {
  const messageKey = mode === 'checking'
    ? 'status.checking'
    : mode === 'activating'
      ? 'profile.activating'
      : mode === 'activationFailed'
        ? 'profile.activationFailed'
        : mode === 'notReady' || mode === 'error'
          ? (STORY_STATUS_MESSAGE_KEYS[code] || 'status.unavailable')
          : 'status.unavailable'
  // Technical details only ever carry whitelisted fields from storyDiagnostic;
  // raw IPC/HTTP exception text, server messages, Vault paths and tokens stay out.
  const details = []
  if (Number.isInteger(diagnostic?.httpStatus)) details.push(t('status.httpStatus', diagnostic.httpStatus))
  if (diagnostic?.code) details.push(t('status.code', diagnostic.code))
  return jsxs('section', {
    className: 'flex w-full max-w-md flex-col gap-3 rounded border border-(--ui-stroke-secondary) p-4',
    children: [
      jsx('p', { className: 'text-sm text-(--ui-text-secondary)', children: t(messageKey) }),
      typeof onRetry === 'function'
        ? jsx('button', {
            className: 'self-start rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover)',
            onClick: onRetry,
            type: 'button',
            children: t('status.retry')
          })
        : null,
      details.length
        ? jsxs('details', {
            className: 'text-xs text-(--ui-text-tertiary)',
            children: [
              jsx('summary', { className: 'cursor-pointer', children: t('status.details') }),
              jsx('div', { className: 'mt-1 break-words', children: details.join(' · ') })
            ]
          })
        : null,
      vaultSetup
        ? jsxs('form', {
            className: 'flex flex-col gap-2 border-t border-(--ui-stroke-secondary) pt-3',
            onSubmit: event => {
              event.preventDefault()
              onSubmitVaultRoot?.()
            },
            children: [
              jsx('label', { className: 'text-xs text-(--ui-text-secondary)', htmlFor: 'story-vault-root', children: t('status.vaultRoot') }),
              jsx('input', {
                id: 'story-vault-root',
                'aria-label': t('status.vaultRoot'),
                autoComplete: 'off',
                className: 'rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-sm',
                disabled: savingVaultRoot,
                onChange: event => onVaultRootChange?.(event.target.value),
                value: vaultRoot,
                type: 'text'
              }),
              jsx('p', { className: 'text-xs text-(--ui-text-tertiary)', children: t('status.vaultRootHelp') }),
              jsx('button', {
                className: 'self-start rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover)',
                disabled: savingVaultRoot || !String(vaultRoot).trim(),
                type: 'submit',
                children: savingVaultRoot ? t('status.savingVault') : t('status.saveVault')
              })
            ]
          })
        : null
    ]
  })
}

function StoryProfileSelector({ routes, value, onChange, t }) {
  const nameCounts = new Map()
  for (const route of routes) {
    const name = storyProfileKey(route?.profile)
    nameCounts.set(name, (nameCounts.get(name) || 0) + 1)
  }
  return jsx('select', {
    'aria-label': t('profile.label'),
    className: 'min-w-48 rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1',
    disabled: routes.length === 0,
    value,
    // Highlighting or focusing an option changes nothing: only a committed
    // change starts activation, so a merely highlighted route never requests.
    onChange: event => onChange(event.target.value),
    children: [
      jsx('option', { value: '', disabled: true, children: t('profile.label') }),
      ...routes.map(route => {
        const key = storyRouteKey(route)
        const name = storyProfileKey(route?.profile)
        // Same-named Profiles on distinct connections stay distinct options and
        // carry their connection source in the label; identity is the full
        // route key, never the display name.
        const label = (nameCounts.get(name) || 0) > 1
          ? t('profile.option', name, route?.mode === 'remote' ? t('profile.remote') : t('profile.local'), String(route?.connectionId || ''))
          : name
        return jsx('option', { value: key, children: label }, key)
      })
    ]
  })
}

function ProjectWorkspace() {
  const t = usePluginI18n('story-construction')
  const profile = useValue(host.state.profile)
  const connectionId = useValue(host.state.connectionId)
  const sessionId = useValue(host.state.focusedStoredSessionId)
  // Task 4: the plugin page container drives the workspace layout mode. The
  // observer binds to the currently mounted page root and is detached whenever
  // that root swaps or the page unmounts, so no measurement outlives its node.
  const [containerNode, setContainerNode] = useState(null)
  const [layoutWidth, setLayoutWidth] = useState(0)
  const [sessionsOpen, setSessionsOpen] = useState(false)

  useEffect(() => {
    if (!containerNode) return undefined
    const measure = () => setLayoutWidth(containerNode.clientWidth)
    measure()
    if (typeof ResizeObserver !== 'function') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(containerNode)
    return () => observer.disconnect()
  }, [containerNode])
  const ownerKey = JSON.stringify([connectionId || '', profile || ''])
  // Task 5: page-lifetime unsaved draft store and the live editor's saving
  // flag. The map lives in a ref so entries survive every view switch inside
  // this page and die with the page — reload recovery is not promised.
  const draftsRef = useMutableRef(new Map())
  const savingRef = useMutableRef(false)
  // View generation moves on EVERY owner change, including A→B→A returning to
  // the same Profile: async completions capture it at request start and a late
  // response must act on the view it came from, never on "the owner is A again".
  const viewGenerationRef = useMutableRef(0)
  const ownerScopeRef = useMutableRef(ownerKey)
  if (ownerScopeRef.current !== ownerKey) {
    ownerScopeRef.current = ownerKey
    viewGenerationRef.current += 1
  }
  const [verifyState, setVerifyState] = useState({ owner: ownerKey, generation: 0, verifiedGeneration: null, status: null })
  if (verifyState.owner !== ownerKey) {
    // Reset the verification generation for a new owner during render, so a
    // cached ready response can never unlock the workspace of a new activation.
    setVerifyState({ owner: ownerKey, generation: verifyState.generation + 1, verifiedGeneration: null, status: null })
  }
  const verifyRef = useMutableRef(verifyState)
  verifyRef.current = verifyState
  const statusRequestRevisionRef = useMutableRef(0)
  const settingsSyncAttemptRef = useMutableRef([])
  const settingsWritePendingRef = useMutableRef([])
  const [vaultRootInput, setVaultRootInput] = useState('')
  const [settingsWritePending, setSettingsWritePending] = useState([])
  const [statusFailure, setStatusFailure] = useState(null)
  const [settingsFailure, setSettingsFailure] = useState(null)
  const [vaultCorrectionActive, setVaultCorrectionActive] = useState(false)
  const setWritePendingForScope = (writeScope, pending) => {
    settingsWritePendingRef.current = storyScopesWithEntry(settingsWritePendingRef.current, writeScope, pending)
    setSettingsWritePending(previous => storyScopesWithEntry(previous, writeScope, pending))
  }
  useEffect(() => {
    setVaultRootInput('')
    setStatusFailure(null)
    setSettingsFailure(null)
    setVaultCorrectionActive(false)
    settingsSyncAttemptRef.current = settingsSyncAttemptRef.current.filter(attempt => attempt.owner === ownerKey)
  }, [ownerKey])
  // Task 2: explicit Profile selection. Route choices come from the public
  // host.profileRoutes() inventory; a committed pick activates the target via
  // host.ensureAgent and only the verified host.state owner may pass the gate.
  const routesQuery = useQuery({
    enabled: typeof host.profileRoutes === 'function',
    queryKey: ['story-construction', 'profile-routes'],
    queryFn: () => Promise.resolve(host.profileRoutes()).then(rows => (Array.isArray(rows) ? rows : []))
  })
  const routes = Array.isArray(routesQuery.data) ? routesQuery.data : []
  const [selection, setSelection] = useState(null)
  const [activationState, setActivationState] = useState('idle')
  const activationTokenRef = useMutableRef(0)
  const activateRoute = route => {
    if (!route) return
    // Token-bind the pick so a superseded activation can never settle the UI
    // for a newer selection (same owner+generation rule as /status).
    const token = activationTokenRef.current + 1
    activationTokenRef.current = token
    // Keep the picked route's identity for the selector even after activation
    // confirms: host.state can only report the backend target, so it cannot
    // say which same-backend route alias the user picked.
    setSelection({ key: storyRouteKey(route), route, ownerKey })
    setActivationState('pending')
    activateStoryRoute(route).then(
      () => {
        if (activationTokenRef.current !== token) return
        setActivationState('idle')
      },
      () => {
        if (activationTokenRef.current !== token) return
        setActivationState('failed')
      }
    )
  }
  // Scope identity is (connectionId, backend Profile): host.state.profile is
  // the actually activated backend Profile, so the pick stays in scope only
  // while it equals targetProfile || profile. Alias display names never extend
  // the scope — when the owner moves to a differently named backend Profile,
  // the pick is invalid and cleared below.
  const selectionMatchesOwner = storyScopeMatches(selection?.route, { connectionId, profile })
  const routeGone = Boolean(selection) && routes.length > 0 && !routes.some(route => storyRouteKey(route) === selection.key)
  // An external owner move — or a pick whose route left the candidates — is
  // followed as actual state: drop the pick and let the live owner re-verify
  // instead of blocking forever. A pending/failed pick drops only when the
  // owner has left since the pick, so a still-current failure keeps Retry.
  const externalOwnerMove = Boolean(selection) && !selectionMatchesOwner &&
    (activationState === 'idle' || ownerKey !== selection.ownerKey)
  if (routeGone || externalOwnerMove) {
    activationTokenRef.current += 1
    setSelection(null)
    setActivationState('idle')
  }
  // A merely highlighted option changes no state. Once a pick is committed the
  // old scope's operable page and its requests are withheld until the pick is
  // the verified owner: pending activation, failed activation and an
  // owner-unverified pick all keep /status and /projects idle.
  const selectionBlocked =
    activationState === 'pending' ||
    activationState === 'failed' ||
    (selection !== null && !selectionMatchesOwner)
  const ownerProfileKey = storyProfileKey(profile)
  const ownerConnectionKey = typeof connectionId === 'string' ? connectionId.trim() : ''
  const routesForOwner = routes.filter(route =>
    (typeof route?.connectionId === 'string' ? route.connectionId.trim() : '') === ownerConnectionKey
  )
  // Selector fallback when no pick is retained: the live route for the active
  // owner prefers the exact profile identity and falls back to the backend
  // targetProfile name (activation moves host.state.profile onto
  // targetProfile || profile).
  const currentRoute =
    routesForOwner.find(route => storyProfileKey(route?.profile) === ownerProfileKey) ||
    routesForOwner.find(route => storyProfileKey(route?.targetProfile || route?.profile) === ownerProfileKey) ||
    null
  const currentRouteKey = currentRoute ? storyRouteKey(currentRoute) : null
  const statusQuery = useQuery({
    // A plugin-initiated pick that is pending, failed or owner-unverified must
    // not request the target's /status — host.state may already show the target
    // while ensureAgent is still in flight or has just failed. Only after the
    // activation confirms does the current owner sync /settings and then fetch
    // /status. External owner switches carry no retained pick, so they sync too.
    enabled: Boolean(profile && connectionId) && !selectionBlocked,
    queryKey: ['story-construction', 'status', connectionId, profile],
    queryFn: () => {
      // Bind owner AND generation at request start: a response may verify only
      // the exact activation generation it was issued for. A→B→A late responses
      // and reused query caches can never stamp a newer generation ready.
      const startedOwner = verifyRef.current.owner
      const startedGeneration = verifyRef.current.generation
      const requestId = ++statusRequestRevisionRef.current
      const startedConnectionId = typeof connectionId === 'string' ? connectionId.trim() : ''
      const isCurrent = () => {
        const liveOwner = JSON.stringify([
          host.state.connectionId.get() || '',
          host.state.profile.get() || ''
        ])
        return storyStatusRequestIsCurrent({
          requestId,
          currentRequestId: statusRequestRevisionRef.current,
          owner: startedOwner,
          generation: startedGeneration,
          currentOwner: verifyRef.current.owner,
          currentGeneration: verifyRef.current.generation
        }) &&
          liveOwner === startedOwner
      }
      const writeScope = { owner: startedOwner, generation: startedGeneration }
      let settingsWriteStarted = false
      return refreshStoryProfileStatus(storyProfileKey(profile), {
        connectionId: startedConnectionId,
        isCurrent,
        canSyncSettings: () => !storySettingsWritePendingForScope(settingsSyncAttemptRef.current, writeScope),
        onStatus: status => {
          setVerifyState(previous => previous.owner === startedOwner && previous.generation === startedGeneration
            ? { ...previous, status }
            : previous)
        },
        onWriteState: pending => {
          if (pending) {
            settingsWriteStarted = true
            settingsSyncAttemptRef.current = storyScopesWithEntry(settingsSyncAttemptRef.current, writeScope, true)
            setVerifyState(previous => previous.owner === startedOwner && previous.generation === startedGeneration
              ? { ...previous, verifiedGeneration: null }
              : previous)
          }
          setWritePendingForScope(writeScope, pending)
        }
      }).then(result => {
        if (!result || result.superseded || !isCurrent()) return result?.status || null
        const status = result.status
        if (storyReadiness(status, storyProfileKey(profile)).ready) {
          settingsSyncAttemptRef.current = storyScopesWithEntry(settingsSyncAttemptRef.current, writeScope, false)
        }
        setStatusFailure(null)
        if (result.wroteSettings) setSettingsFailure(null)
        else setSettingsFailure(previous => storySettingsFailureAfterStatus(status, storyProfileKey(profile), previous))
        setVerifyState(previous => previous.owner === startedOwner && previous.generation === startedGeneration
          ? { ...previous, verifiedGeneration: startedGeneration, status }
          : previous)
        return status
      }).catch(error => {
        if (isCurrent()) {
          const diagnostic = storyDiagnostic(error, null)
          if (settingsWriteStarted) setSettingsFailure(diagnostic)
          else setStatusFailure(diagnostic)
          setVerifyState(previous => previous.owner === startedOwner && previous.generation === startedGeneration
            ? { ...previous, verifiedGeneration: null }
            : previous)
        }
        throw error
      })
    }
  })
  // The gate reads only the status response bound to the current verification —
  // never a bare query-cache hit from an older request.
  const status = verifyState.status
  const readiness = storyReadiness(status, profile)
  const verifiedCurrent = verifyState.verifiedGeneration !== null && verifyState.verifiedGeneration === verifyState.generation
  const currentWriteScope = { owner: verifyState.owner, generation: verifyState.generation }
  const writePending = storySettingsWritePendingForScope(settingsWritePending, currentWriteScope) ||
    storySettingsWritePendingForScope(settingsWritePendingRef.current, currentWriteScope)
  const statusError = Boolean(statusFailure || settingsFailure)
  const gateOpen = storyWorkspaceGate({
    selectionBlocked,
    verifiedCurrent,
    statusFailure: Boolean(statusFailure),
    settingsFailure: Boolean(settingsFailure),
    settingsWritePending: writePending,
    status,
    profile
  })
  const refetchStatus = () => {
    if (!profile || !connectionId) return
    // refetch() bypasses useQuery's enabled flag, so an unconfirmed pick must
    // block imperative /status here too — Retry, focus and owner-change paths
    // all funnel through this guard.
    if (selectionBlocked) return
    void statusQuery.refetch()
  }
  const refetchStatusRef = useMutableRef(refetchStatus)
  refetchStatusRef.current = refetchStatus

  const submitVaultRoot = async () => {
    const path = vaultRootInput.trim()
    if (!path || selectionBlocked || !profile || !connectionId) return
    const current = verifyRef.current
    const startedOwner = current.owner
    const startedGeneration = current.generation
    const requestId = ++statusRequestRevisionRef.current
    const startedConnectionId = typeof connectionId === 'string' ? connectionId.trim() : ''
    const writeScope = { owner: startedOwner, generation: startedGeneration }
    const isCurrent = () => {
      const liveOwner = JSON.stringify([
        host.state.connectionId.get() || '',
        host.state.profile.get() || ''
      ])
      return storyStatusRequestIsCurrent({
        requestId,
        currentRequestId: statusRequestRevisionRef.current,
        owner: startedOwner,
        generation: startedGeneration,
        currentOwner: verifyRef.current.owner,
        currentGeneration: verifyRef.current.generation
      }) &&
        liveOwner === startedOwner
    }
    const onWriteState = pending => {
      if (pending) {
        settingsSyncAttemptRef.current = storyScopesWithEntry(settingsSyncAttemptRef.current, writeScope, true)
      }
      setWritePendingForScope(writeScope, pending)
    }
    setVaultCorrectionActive(true)
    setSettingsFailure(null)
    setStatusFailure(null)
    setVerifyState(previous => previous.owner === startedOwner && previous.generation === startedGeneration
      ? { ...previous, verifiedGeneration: null }
      : previous)
    try {
      const result = await submitStoryVaultPath(storyProfileKey(profile), path, {
        connectionId: startedConnectionId,
        isCurrent,
        onWriteState
      })
      if (result.superseded || !isCurrent()) return
      const nextStatus = result.status
      setStatusFailure(null)
      setSettingsFailure(null)
      if (storyReadiness(nextStatus, storyProfileKey(profile)).ready) {
        settingsSyncAttemptRef.current = storyScopesWithEntry(settingsSyncAttemptRef.current, writeScope, false)
        setVaultCorrectionActive(false)
        setVaultRootInput('')
      }
      setVerifyState(previous => previous.owner === startedOwner && previous.generation === startedGeneration
        ? { ...previous, verifiedGeneration: startedGeneration, status: nextStatus }
        : previous)
    } catch (error) {
      if (isCurrent()) {
        setSettingsFailure(storyDiagnostic(error, null))
        setVerifyState(previous => previous.owner === startedOwner && previous.generation === startedGeneration
          ? { ...previous, verifiedGeneration: null }
          : previous)
      }
    }
  }

  const retryStatus = () => {
    const diagnostic = settingsFailure || statusFailure || storyDiagnostic(null, status)
    const retryScope = { owner: verifyRef.current.owner, generation: verifyRef.current.generation }
    if (!storyVaultPathCorrectionAvailable(status, diagnostic)) {
      settingsSyncAttemptRef.current = storyScopesWithEntry(settingsSyncAttemptRef.current, retryScope, false)
    }
    setStatusFailure(null)
    setSettingsFailure(null)
    refetchStatus()
  }

  useEffect(() => {
    // selectionBlocked in the deps runs the deferred /status for the current
    // owner once a pick confirms (blocked → false), and is a guarded no-op
    // while the pick is still unconfirmed.
    refetchStatusRef.current()
  }, [connectionId, profile, selectionBlocked])

  useEffect(() => {
    const refetch = () => refetchStatusRef.current()
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refetch()
    }
    window.addEventListener('focus', refetch)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('focus', refetch)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  const discovery = projectDiscoveryQuery({ profile, connectionId, ready: gateOpen })
  const projectsQuery = useQuery({
    queryKey: discovery.queryKey,
    queryFn: () => fetchProjects(discovery.scope),
    enabled: discovery.enabled,
    refetchInterval: 60_000
  })
  const projects = projectRows(projectsQuery.data)
  const [projectSelection, setProjectSelection] = useState({ profile, connectionId, projectId: null })
  const selectedProjectId = selectedProjectForScope(projectSelection, { profile, connectionId })
  const [selectedChapterId, setSelectedChapterId] = useState(null)
  const [scope, setScope] = useState({ profile, connectionId, sessionId, projectId: null, tree: null, selectedChapterId: null, status: 'idle' })

  useEffect(() => {
    setScope(previous => resetWorkspaceScope(previous, { profile, connectionId, sessionId, projectId: selectedProjectId }))
    setSelectedChapterId(null)
  }, [profile, connectionId, sessionId, selectedProjectId])

  const treeQuery = useQuery({
    enabled: Boolean(selectedProjectId && sessionId && profile && connectionId && gateOpen),
    queryKey: ['story-construction', 'project-tree', profile, connectionId, sessionId, selectedProjectId],
    queryFn: () => fetchProjectTree(selectedProjectId, { sessionId, profile, connectionId })
  })
  const tree = treeQuery.data ? buildProjectTree(treeQuery.data.tree || treeQuery.data, t) : scope.tree
  const project = tree?.project || projects.find(item => item.id === selectedProjectId) || null

  const handleDraftState = ({ key, draft, baseline, saving }) => {
    // ChapterEditor reports draft/baseline/saving; only string drafts touch the
    // retain map (retainStoryDraft drops a draft equal to its baseline), and a
    // report without a draft — a scope reset — never deletes a retained entry.
    if (typeof draft === 'string') {
      draftsRef.current = retainStoryDraft(draftsRef.current, key, draft, baseline)
    }
    if (typeof saving === 'boolean') savingRef.current = saving
  }

  // Plugin-initiated leave protection for Back to library, opening another
  // project card and Profile selection. An in-flight save blocks the switch;
  // retained drafts in the left-behind scope need a localized confirmation.
  // Cancel returns false and leaves project, chapter and drafts untouched.
  const guardLeave = ({ kind, projectId }) => {
    const dirty = retainedStoryDraftExists(draftsRef.current, parts => {
      if (parts[0] !== draftSlot(connectionId) || parts[1] !== draftSlot(profile)) return false
      if (kind === 'profile') return true
      if (kind === 'project') return parts[3] === draftSlot(selectedProjectId)
      if (kind === 'openProject') return parts[3] !== draftSlot(projectId)
      return false
    })
    return canLeaveStoryWorkspace({
      dirty,
      saving: savingRef.current,
      confirmLeave: () => window.confirm(t('chapter.confirmLeave'))
    })
  }

  const changeProfile = key => {
    const route = routes.find(candidate => storyRouteKey(candidate) === key) || null
    if (!route) return
    if (!guardLeave({ kind: 'profile' })) return
    activateRoute(route)
  }

  const openProject = projectId => {
    if (!projectId) return
    if (!guardLeave({ kind: 'openProject', projectId })) return
    setProjectSelection({ profile, connectionId, projectId })
    setSelectedChapterId(null)
  }

  const backToLibrary = () => {
    if (!guardLeave({ kind: 'project' })) return
    setProjectSelection({ profile, connectionId, projectId: null })
    setSelectedChapterId(null)
  }

  const handleCreated = async (projectId, request) => {
    // Create completion is checked against the VIEW GENERATION captured when
    // the POST started — not merely against the live owner. After an external
    // A→B→A switch the owner is A again but the view generation has moved, so
    // the late create must not refetch, select a project or touch any view.
    if (request?.generation !== viewGenerationRef.current) return
    await projectsQuery.refetch()
    if (request?.generation !== viewGenerationRef.current) return
    // Enter by the id the POST response returned — never the first list row.
    setProjectSelection({ profile: request.profile, connectionId: request.connectionId, projectId })
    setSelectedChapterId(null)
  }

  if (!gateOpen) {
    // Loading, failed and not-ready status all collapse into one compact Retry
    // card; the operable workspace stays hidden until a fresh matching /status.
    // Pending/failed activation and owner mismatch get their own copy and make
    // no target /status or /projects request.
    const diagnostic = settingsFailure || statusFailure || storyDiagnostic(null, status)
    const statusCode = diagnostic.code || readiness.code
    const mode = activationState === 'pending'
      ? 'activating'
      : selectionBlocked
        ? 'activationFailed'
        : statusError
          ? 'error'
          : verifiedCurrent
            ? 'notReady'
            : 'checking'
    const onRetry = activationState === 'failed' && selection
      ? () => activateRoute(selection.route)
      : selectionBlocked
        ? null
        : retryStatus
    return jsxs('div', {
      className: 'flex h-full min-h-0 flex-col overflow-hidden text-sm',
      ref: setContainerNode,
      children: [
        jsx('header', {
          className: 'flex flex-wrap items-center gap-3 border-b border-(--ui-stroke-secondary) p-3',
          children: [
            jsx('h1', { className: 'text-base font-medium', children: t('workspace.title') }),
            jsx('span', {
              className: 'text-xs text-(--ui-text-tertiary)',
              children: t('workspace.scope', connectionId || '-', profile || '-')
            }),
            jsx(StoryProfileSelector, {
              routes,
              value: selection ? selection.key : currentRouteKey ?? '',
              onChange: changeProfile,
              t
            })
          ]
        }),
        jsx('div', {
          className: 'flex min-h-0 flex-1 items-center justify-center p-4',
          children: jsx(StoryStatusCard, {
            mode,
            code: statusCode,
            diagnostic,
            onRetry,
            vaultSetup: vaultCorrectionActive || storyVaultPathCorrectionAvailable(status, diagnostic),
            vaultRoot: vaultRootInput,
            savingVaultRoot: writePending,
            onVaultRootChange: setVaultRootInput,
            onSubmitVaultRoot: submitVaultRoot,
            t
          })
        })
      ]
    })
  }

  // Task 4: only a selected project reveals the tree/editor/sessions workspace;
  // every other case keeps the library page. The measured container width picks
  // the layout mode, which only switches CSS grid variants (data-layout) on one
  // stable composition: wide docks a fixed sessions column, compact/narrow keep
  // the editor unsqueezed under a collapsible sessions area, and narrow puts
  // the tree above the editor.
  const surface = storyWorkspaceSurface(selectedProjectId)
  const layoutMode = storyLayoutMode(layoutWidth)
  const treeNav = jsxs('nav', {
    className: 'hermes-story-tree',
    children: [
      jsx('div', {
        className: 'truncate border-b border-(--ui-stroke-secondary) px-3 py-2 text-xs text-(--ui-text-tertiary)',
        title: project?.name || selectedProjectId || '',
        children: project?.name || t('workspace.projectTree')
      }),
      treeQuery.isLoading
        ? jsx('div', { className: 'p-3 text-(--ui-text-secondary)', children: t('workspace.loadingProject') })
        : treeQuery.error
          ? jsx('div', {
              className: 'break-words p-3 text-(--ui-text-secondary)',
              children: t('workspace.projectUnavailable', treeQuery.error.message)
            })
          : jsx(ProjectTree, { tree, onOpenChapter: setSelectedChapterId, t })
    ]
  })
  const editorCell = jsx('div', {
    className: 'hermes-story-editor',
    children: jsx(ChapterEditor, {
      chapterId: selectedChapterId,
      connectionId,
      draftStore: draftsRef,
      onDraftState: handleDraftState,
      profile,
      projectId: selectedProjectId,
      sessionId
    })
  })
  // ProjectSessionsPanel is always mounted inside this region — collapse only
  // flips data-open and lets CSS hide the panel, and the region's tree position
  // never changes across layout modes. That keeps creatingSession and
  // kickoffRecovery alive through collapse/expand and wide↔compact↔narrow
  // switches, so a pending creation or Retry first task is never lost.
  const sessionsArea = jsxs('div', {
    className: 'hermes-story-sessions',
    'data-open': sessionsOpen ? 'true' : 'false',
    children: [
      jsxs('button', {
        'aria-expanded': layoutMode === 'wide' || sessionsOpen,
        className: 'hermes-story-sessions-toggle',
        onClick: () => setSessionsOpen(previous => !previous),
        type: 'button',
        children: [
          jsx('span', { className: 'hermes-story-sessions-toggle-label', children: t('agent.sessions') }),
          jsx('span', {
            'aria-hidden': 'true',
            className: 'hermes-story-sessions-toggle-icon',
            children: sessionsOpen ? '▾' : '▸'
          })
        ]
      }),
      jsx(ProjectSessionsPanel, { connectionId, profile, project, sessionId })
    ]
  })
  // One stable composition for every layout mode: the mode only switches the
  // CSS grid template (data-layout), so tree, editor and sessions — and all
  // React state inside them — survive width switches without a remount.
  const workspaceBody = jsxs('div', {
    className: 'hermes-story-workspace',
    'data-layout': layoutMode,
    children: [treeNav, editorCell, sessionsArea]
  })

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col overflow-hidden text-sm',
    ref: setContainerNode,
    children: [
      jsxs('header', {
        className: 'flex flex-wrap items-center gap-3 border-b border-(--ui-stroke-secondary) p-3',
        children: [
          jsx('h1', { className: 'text-base font-medium', children: t('workspace.title') }),
          jsx('span', {
            className: 'text-xs text-(--ui-text-tertiary)',
            children: t('workspace.scope', connectionId || '-', profile || '-')
          }),
          jsx(StoryProfileSelector, {
            routes,
            value: selection ? selection.key : currentRouteKey ?? '',
            onChange: changeProfile,
            t
          }),
          surface === 'workspace'
            ? jsx('span', {
                className: 'min-w-0 flex-1 truncate text-sm font-medium',
                title: project?.name || selectedProjectId || '',
                children: project?.name || selectedProjectId
              })
            : null,
          surface === 'workspace'
            ? jsx('button', {
                className: 'shrink-0 rounded border border-(--ui-stroke-secondary) px-2 py-1 text-xs hover:bg-(--chrome-action-hover)',
                onClick: backToLibrary,
                type: 'button',
                children: t('workspace.backToLibrary')
              })
            : null
        ]
      }),
      surface === 'workspace'
        ? workspaceBody
        : jsx(ProjectLibrary, {
            // Remount per owner so an open dialog or search term from one scope
            // can never carry into another (create completion is guarded too).
            key: ownerKey,
            connectionId,
            error: projectsQuery.error,
            getGeneration: () => viewGenerationRef.current,
            loading: projectsQuery.isLoading,
            onCreated: handleCreated,
            onOpen: openProject,
            onRetry: () => void projectsQuery.refetch(),
            profile,
            ready: gateOpen,
            projects,
            t
          })
    ]
  })
}

// Disk plugins are not scanned by Tailwind, so utilities written only here
// never reach the built CSS. Following the Hermes Radio plugin, all Story page
// geometry and the plugin-only utilities below live in this scoped sheet;
// colors stay on Hermes theme variables.
const CSS = `
.hermes-story-library-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.hermes-story-workspace{display:grid;grid-template-rows:minmax(0,1fr);flex:1;min-width:0;min-height:0;overflow:hidden}
.hermes-story-workspace[data-layout=wide]{grid-template-columns:16rem minmax(0,1fr) 18rem}
.hermes-story-workspace[data-layout=compact]{grid-template-columns:16rem minmax(0,1fr);grid-template-rows:minmax(0,1fr) auto}
.hermes-story-workspace[data-layout=narrow]{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr) auto}
.hermes-story-tree{display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden;border-right:1px solid var(--ui-stroke-secondary)}
.hermes-story-workspace[data-layout=narrow] .hermes-story-tree{max-height:16rem;border-right:0;border-bottom:1px solid var(--ui-stroke-secondary)}
.hermes-story-editor{display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden}
.hermes-story-sessions{display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden;border-left:1px solid var(--ui-stroke-secondary)}
.hermes-story-workspace[data-layout=compact] .hermes-story-sessions,.hermes-story-workspace[data-layout=narrow] .hermes-story-sessions{grid-column:1/-1;border-left:0;border-top:1px solid var(--ui-stroke-secondary)}
.hermes-story-sessions-toggle{display:none}
.hermes-story-workspace[data-layout=compact] .hermes-story-sessions-toggle,.hermes-story-workspace[data-layout=narrow] .hermes-story-sessions-toggle{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;padding:8px 12px;border:0;background:transparent;color:inherit;font-size:12px;line-height:16px;text-align:left;cursor:pointer}
.hermes-story-sessions-toggle:hover{background:var(--chrome-action-hover)}
.hermes-story-sessions-toggle-label{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}
.hermes-story-sessions-toggle-icon{flex-shrink:0;color:var(--ui-text-tertiary)}
.hermes-story-sessions-panel{display:flex;flex-direction:column;gap:8px;min-width:0;min-height:0;flex:1;overflow:auto;padding:12px;font-size:12px;line-height:16px}
.hermes-story-workspace[data-layout=compact] .hermes-story-sessions-panel,.hermes-story-workspace[data-layout=narrow] .hermes-story-sessions-panel{flex:none;max-height:18rem}
.hermes-story-workspace[data-layout=compact] .hermes-story-sessions[data-open=false] .hermes-story-sessions-panel,.hermes-story-workspace[data-layout=narrow] .hermes-story-sessions[data-open=false] .hermes-story-sessions-panel{display:none}
.hermes-story-btn-primary{color:var(--dt-accent-foreground,var(--ui-text-primary))}
.hermes-story-overlay{background:rgba(0,0,0,.5)}
.hermes-story-focus:focus{border-color:var(--ui-accent)}
`

const plugin = {
  id: 'story-construction',
  name: 'story-construction',
  defaultEnabled: false,
  register(ctx) {
    ctx.i18n.register(STORY_LOCALES)
    // Radio-pattern plugin CSS: installed on register, removed on dispose. The
    // document guard keeps Node test loading free of a DOM requirement.
    if (typeof document !== 'undefined') {
      const style = document.createElement('style')
      style.textContent = CSS
      document.head.append(style)
      ctx.onDispose?.(() => style.remove())
    }
    if (typeof ctx.rest === 'function') {
      ctx.onDispose?.(bindWorkspaceApi(ctx.rest))
    }
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: STORY_ROUTE_PATH },
        render: () => jsx(ProjectWorkspace, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 55,
        data: { codicon: 'book', label: ctx.i18n.t('workspace.title'), path: STORY_ROUTE_PATH }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'story-construction.open',
          label: ctx.i18n.t('palette.open'),
          keywords: ['story', 'construction', 'project', 'chapter', 'workspace'],
          run: () => host.navigate(STORY_ROUTE_PATH)
        }
      }
    ])
  }
}

export default plugin
