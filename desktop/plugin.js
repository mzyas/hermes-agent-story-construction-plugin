import { PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, host, usePluginI18n, useQuery, useValue } from '@hermes/plugin-sdk'
// Namespace import: the context-menu components are optional, so an SDK that
// lacks them degrades to no menu instead of failing to link the plugin.
import * as storySdk from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const en = {
  palette: {
    open: 'Story Construction: Show workspace'
  },
  workspace: {
    title: 'Story Construction',
    // Sent with a new project so its starter titles match the UI language.
    localeCode: 'en',
    scope: (connectionId, profile) => `(${connectionId}, ${profile})`,
    loadingProjects: 'Loading projects…',
    projectsUnavailable: 'Could not load projects. Check the Story service and try again.',
    newProject: 'New project',
    projectName: 'Project name',
    projectSlug: 'Project slug (optional)',
    createProject: 'Create project',
    creatingProject: 'Creating project…',
    backToLibrary: 'Back to library',
    changeVaultPath: 'Change Vault path',
    projectTree: 'Project tree',
    loadingProject: 'Loading project…',
    projectUnavailable: error => `Project unavailable: ${error}`,
    needsSession: 'No writing session is linked to this project yet. Create one on the right and the project opens here.'
  },
  library: {
    search: 'Search projects',
    searchPlaceholder: 'Filter by name or ID',
    empty: 'No projects in this Vault yet.',
    noMatch: 'No projects match your search.',
    projectMenu: 'Project actions',
    deleteProject: 'Delete project',
    deleteTitle: name => `Delete “${name}”?`,
    deleteMoves: 'The project folder is moved to the .story-trash folder in your Vault. Nothing is erased, and you can move it back by hand.',
    deleteCounts: (volumes, chapters) => `${volumes} volume(s), ${chapters} chapter(s)`,
    deleteSessions: count => `${count} writing session(s) will lose their link to this project. The Hermes sessions themselves are kept.`,
    deleteTypeName: name => `Type the project name “${name}” to confirm`,
    deleteConfirm: 'Move to trash',
    deleting: 'Moving…',
    deleteFailed: 'Could not delete the project. Check the Story service and try again.',
    deleted: folder => `Moved to the Vault trash: ${folder}`
  },
  dialog: {
    cancel: 'Cancel',
    nameRequired: 'Project name is required.',
    createFailed: 'Could not create project. Check the Story service and try again.'
  },
  record: {
    loading: 'Loading…',
    unavailable: message => `Could not load this record: ${message}`,
    reference: 'Reference note',
    empty: 'This record has no text yet.',
    readOnly: 'Read-only here. Ask the Agent in a session to propose changes.',
    kind: { character: 'Character', world_entry: 'World entry', note: 'Note' }
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
    selectProject: 'Select a project.',
    tabChapters: 'Chapters',
    tabNotes: 'Notes',
    unassignedVolume: 'No volume',
    newVolume: 'New volume',
    newChapter: 'New chapter',
    createConfirm: 'Create',
    createCancel: 'Cancel',
    creating: 'Creating…',
    volumeTitlePlaceholder: 'Volume title',
    chapterTitlePlaceholder: 'Chapter title',
    defaultVolumeTitle: number => `Volume ${number}`,
    defaultChapterTitle: number => `Chapter ${number}`,
    createFailed: 'Could not create it. Try again.',
    createInvalid: 'That title cannot be used.'
  },
  chapter: {
    openPrompt: 'Open a chapter to read or edit it.',
    loading: 'Loading chapter…',
    unavailable: error => `Chapter unavailable: ${error}`,
    version: version => `Version ${version || 'unknown'} · Draft edits stay local until confirmed.`,
    confirmLeave: 'You have an unsaved chapter draft. Leave without saving?',
    saving: 'Saving…',
    saved: 'Saved; chapter version refreshed.',
    saveUnavailable: error => `Save unavailable: ${error}`,
    saveFailed: error => `Save failed: ${error}`,
    saveConfirmed: 'Save'
  },
  proposal: {
    strip: count => `The Agent has ${count} change(s) waiting`,
    review: 'Review',
    pending: 'Waiting for approval',
    approvedLeft: minutes => `Approved · ${minutes} min left`,
    expired: 'Approval expired',
    stale: 'This changed since it was proposed',
    newRecord: (kind, title) => `New ${kind}: ${title}`,
    editRecord: (kind, title) => `Changes to ${kind} ${title}`,
    renameRecord: (kind, from, to) => `Rename ${kind}: ${from} → ${to}`,
    deleteRecord: (kind, title) => `Delete ${kind}: ${title}`,
    renameHint: 'Only the name changes. The text stays as it is.',
    deleteHint: 'The record is moved to the Vault trash folder, not erased. You can undo it from here afterwards.',
    chatHint: 'Approve this in the chat. If the prompt timed out, ask the Agent to propose it again.',
    kind: { chapter: 'chapter', character: 'character', world_entry: 'world entry', note: 'note' },
    close: 'Close',
    discard: 'Discard',
    changeN: (number, op) => `Change ${number} · ${op}`,
    line: number => `line ${number}`,
    warnLeading: 'Looks like an introduction, not story text',
    warnTrailing: 'Looks like a closing remark, not story text',
    warnTitle: 'Repeats the chapter title',
    warnFence: 'A code fence around the text was removed',
    warnNameInUse: 'This name is already used; it will get a number after it when written',
    conflictAt: number => `Change ${number} no longer matches the text.`,
    conflict: 'The text changed and these changes no longer match it.',
    versionChanged: 'The text changed since you opened this. Reopen the proposal.',
    frontmatter: 'Remove the --- header block: only story text is allowed.',
    failed: 'Could not complete that. Try again.',
    undo: title => `Undo the Agent's last write (${title})`,
    undone: 'Restored the text from before the Agent wrote.',
    undoChanged: 'It was edited after the Agent wrote, so it cannot be undone.',
    undoFailed: 'Could not undo that write.',
    op: {
      replace: 'Replace',
      insert_after: 'Insert after',
      insert_before: 'Insert before',
      append: 'Add at the end',
      prepend: 'Add at the start',
      rewrite: 'Rewrite everything'
    }
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
    focusLatest: 'Go to latest session',
    retryFirstTask: 'Retry first task',
    removeStaleBinding: 'Remove stale binding',
    currentSession: 'Current session',
    untitledSession: 'Untitled session',
    boundSession: name => `Bound · ${name}`,
    manageSessions: 'Manage sessions',
    doneManaging: 'Done',
    selectAll: 'Select all',
    clearSelection: 'Clear selection',
    deleteSelected: count => `Delete selected (${count})`,
    deleteOne: 'Delete',
    selectSession: name => `Select ${name}`,
    confirmCount: count => `${count} session(s) selected`,
    confirmUnbindHint: 'Removing the binding keeps the session in Hermes, and you can bind it again later.',
    confirmHardLabel: 'Also permanently delete the session itself (cannot be undone)',
    confirmHardActive: 'The session in use cannot be permanently deleted. Switch to another session first.',
    confirmUnbind: 'Remove binding',
    confirmHard: 'Delete permanently',
    confirmCancel: 'Cancel',
    workspaceUnavailable: 'The session was created, but it is not grouped under a Hermes project because the project folder could not be used.',
    workspaceUnsupported: 'The session was created, but this Profile uses an ssh terminal, so no Hermes project folder is created.',
    removing: 'Working…',
    removed: count => `${count} session(s) done.`,
    removedPartial: (count, failed, error) => `${count} done, ${failed} failed: ${error}`,
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
    changeVault: 'Enter a new Vault path. Saving it replaces the current Vault and clears existing session-to-project bindings.',
    cancelChangeVault: 'Cancel',
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
    localeCode: 'zh',
    scope: (connectionId, profile) => `(${connectionId}, ${profile})`,
    loadingProjects: '正在加载项目…',
    projectsUnavailable: '无法加载项目，请检查故事服务后重试。',
    newProject: '新建项目',
    projectName: '项目名称',
    projectSlug: '项目标识（可选）',
    createProject: '创建项目',
    creatingProject: '正在创建项目…',
    backToLibrary: '返回项目库',
    changeVaultPath: '更换资料库路径',
    projectTree: '项目树',
    loadingProject: '正在加载项目…',
    projectUnavailable: error => `项目不可用：${error}`,
    needsSession: '这个项目还没有关联的写作会话。请在右侧新建一个写作会话，项目就能在这里打开。'
  },
  library: {
    search: '搜索项目',
    searchPlaceholder: '按名称或 ID 筛选',
    empty: '当前资料库还没有项目。',
    noMatch: '没有符合当前搜索的项目。',
    projectMenu: '项目操作',
    deleteProject: '删除项目',
    deleteTitle: name => `删除“${name}”？`,
    deleteMoves: '项目文件夹会被移到资料库里的 .story-trash 文件夹，不会被真正删除，之后可以手动移回。',
    deleteCounts: (volumes, chapters) => `${volumes} 卷，${chapters} 章`,
    deleteSessions: count => `有 ${count} 个写作会话会失去与此项目的绑定，Hermes 里的会话本身会保留。`,
    deleteTypeName: name => `请输入项目名称“${name}”以确认`,
    deleteConfirm: '移到回收目录',
    deleting: '正在移动…',
    deleteFailed: '无法删除项目，请检查故事服务后重试。',
    deleted: folder => `已移到资料库回收目录：${folder}`
  },
  dialog: {
    cancel: '取消',
    nameRequired: '请填写项目名称。',
    createFailed: '无法创建项目，请检查故事服务后重试。'
  },
  record: {
    loading: '正在加载…',
    unavailable: message => `无法加载此记录：${message}`,
    reference: '参考笔记',
    empty: '这条记录还没有内容。',
    readOnly: '这里是只读的。想修改请在会话里让 Agent 提出修改。',
    kind: { character: '角色', world_entry: '世界设定条目', note: '笔记' }
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
    selectProject: '请选择一个项目。',
    tabChapters: '章节',
    tabNotes: '笔记',
    unassignedVolume: '未分卷',
    newVolume: '新建卷',
    newChapter: '新建章节',
    createConfirm: '创建',
    createCancel: '取消',
    creating: '正在创建…',
    volumeTitlePlaceholder: '卷名称',
    chapterTitlePlaceholder: '章节名称',
    defaultVolumeTitle: number => `第${number}卷`,
    defaultChapterTitle: number => `第${number}章`,
    createFailed: '创建失败，请重试。',
    createInvalid: '这个名称无法使用。'
  },
  chapter: {
    openPrompt: '打开一个章节以阅读或编辑。',
    loading: '正在加载章节…',
    unavailable: error => `章节不可用：${error}`,
    version: version => `版本 ${version || '未知'} · 确认前的草稿修改只保存在本地。`,
    confirmLeave: '有未保存的章节草稿，确定离开而不保存吗？',
    saving: '正在保存…',
    saved: '已保存；章节版本已刷新。',
    saveUnavailable: error => `无法保存：${error}`,
    saveFailed: error => `保存失败：${error}`,
    saveConfirmed: '保存'
  },
  proposal: {
    strip: count => `智能体有 ${count} 条修改待处理`,
    review: '审阅',
    pending: '待确认',
    approvedLeft: minutes => `已批准 · 剩余 ${minutes} 分钟`,
    expired: '批准已过期',
    stale: '提案之后内容已被修改',
    newRecord: (kind, title) => `新建${kind}：${title}`,
    editRecord: (kind, title) => `对${kind}《${title}》的修改`,
    renameRecord: (kind, from, to) => `重命名${kind}：${from} → ${to}`,
    deleteRecord: (kind, title) => `删除${kind}：${title}`,
    renameHint: '只改名字，正文不变。',
    deleteHint: '这条记录会被移到资料库的回收目录，不会被彻底删除，之后可以在这里撤销。',
    chatHint: '请在聊天里批准。如果提示已超时，请让助手重新提议。',
    kind: { chapter: '章节', character: '角色', world_entry: '世界设定条目', note: '笔记' },
    close: '关闭',
    discard: '放弃',
    changeN: (number, op) => `第 ${number} 处 · ${op}`,
    line: number => `第 ${number} 行`,
    warnLeading: '看起来是开场白，不是正文',
    warnTrailing: '看起来是结尾说明，不是正文',
    warnTitle: '重复了章节标题',
    warnFence: '已去掉文字外面的代码围栏',
    warnNameInUse: '这个名字已被使用，写入时会在后面加序号',
    conflictAt: number => `第 ${number} 处修改找不到对应的原文。`,
    conflict: '内容已被修改，这些修改和它对不上了。',
    versionChanged: '内容在你打开之后又变了，请重新打开这份提案。',
    frontmatter: '请去掉开头的 --- 头信息块：这里只能是正文。',
    failed: '操作没有完成，请重试。',
    undo: title => `撤销智能体最近一次写入（${title}）`,
    undone: '已恢复到智能体写入之前的文字。',
    undoChanged: '智能体写入之后又被修改过，所以不能撤销。',
    undoFailed: '无法撤销这次写入。',
    op: {
      replace: '替换',
      insert_after: '在其后插入',
      insert_before: '在其前插入',
      append: '追加到末尾',
      prepend: '加到开头',
      rewrite: '重写全文'
    }
  },
  agent: {
    title: '智能体',
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
    focusLatest: '切到最近会话',
    retryFirstTask: '重试首次任务',
    removeStaleBinding: '移除失效绑定',
    currentSession: '当前会话',
    untitledSession: '未命名会话',
    boundSession: name => `已绑定 · ${name}`,
    manageSessions: '管理会话',
    doneManaging: '完成',
    selectAll: '全选',
    clearSelection: '取消全选',
    deleteSelected: count => `删除所选（${count}）`,
    deleteOne: '删除',
    selectSession: name => `选择 ${name}`,
    confirmCount: count => `已选择 ${count} 个会话`,
    confirmUnbindHint: '移除绑定后，会话仍保留在 Hermes 中，之后可以重新绑定。',
    confirmHardLabel: '同时彻底删除会话本身（不可恢复）',
    confirmHardActive: '正在使用的会话无法彻底删除，请先切换到其他会话。',
    confirmUnbind: '移除绑定',
    confirmHard: '彻底删除',
    confirmCancel: '取消',
    workspaceUnavailable: '写作会话已创建，但没有归入 Hermes 项目，因为项目文件夹无法使用。',
    workspaceUnsupported: '写作会话已创建；此 Profile 使用 ssh 终端，所以不会创建 Hermes 项目文件夹。',
    removing: '正在处理…',
    removed: count => `已处理 ${count} 个会话。`,
    removedPartial: (count, failed, error) => `成功 ${count} 个，失败 ${failed} 个：${error}`,
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
    changeVault: '请输入新的资料库路径。保存后将替换当前资料库,并清除已有的会话与项目绑定。',
    cancelChangeVault: '取消',
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

// Chapters grouped under their volume, in volume order. A chapter whose volume
// is missing from the list is kept visible in a trailing group instead of
// vanishing from the sidebar.
export function buildChapterOutline(volumes, chapters, translate = translateEnglishStory) {
  const groups = volumes.map(volume => ({ volume, chapters: [] }))
  const byVolumeId = new Map(groups.map(group => [group.volume.id, group]))
  const unassigned = []
  for (const chapter of chapters) {
    const group = byVolumeId.get(chapter.volume_id)
    ;(group ? group.chapters : unassigned).push(chapter)
  }
  if (unassigned.length) {
    groups.push({ volume: { id: '', title: translate('tree.unassignedVolume') }, chapters: unassigned })
  }
  return groups
}

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
    outline: buildChapterOutline(volumes, chapters, translate),
    branches: [
      { id: 'project', label: translate('tree.project'), children: project ? [project] : [] },
      {
        id: 'worldInfo',
        label: translate('tree.worldInfo'),
        children: worldInfo ? entries.map(entry => ({ ...entry, kind: 'world_entry' })) : []
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

const PROJECT_MEMORY_KEY = 'story-construction.last-project.v1'

function projectMemoryStorage() {
  try {
    return globalThis.localStorage || null
  } catch {
    return null
  }
}

// The project a user last entered, per (connection, Profile), so leaving the
// Story page and coming back resumes it instead of showing the project library.
// In-memory first; localStorage only carries it across restarts, and any
// storage failure just means nothing is remembered.
export function createProjectMemory(storage = projectMemoryStorage()) {
  const cache = new Map()
  let loaded = false
  const keyOf = ({ profile, connectionId } = {}) => JSON.stringify([connectionId || '', profile || ''])
  const load = () => {
    if (loaded) return
    loaded = true
    try {
      const parsed = JSON.parse(storage?.getItem(PROJECT_MEMORY_KEY) || '{}')
      if (parsed && typeof parsed === 'object') {
        for (const [key, value] of Object.entries(parsed)) {
          if (typeof value === 'string' && value) cache.set(key, value)
        }
      }
    } catch {
      // Unreadable memory is the same as an empty one.
    }
  }
  const persist = () => {
    try {
      storage?.setItem(PROJECT_MEMORY_KEY, JSON.stringify(Object.fromEntries(cache)))
    } catch {
      // Still remembered for this run.
    }
  }
  return {
    get(scope) {
      load()
      return cache.get(keyOf(scope)) || null
    },
    set(scope, projectId) {
      load()
      const key = keyOf(scope)
      if (typeof projectId === 'string' && projectId) cache.set(key, projectId)
      else cache.delete(key)
      persist()
    }
  }
}

export const storyProjectMemory = createProjectMemory()

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

// The backend lets a session read a project only if that session is bound to it. The page
// is opened from whatever session happens to be focused, which is often not a Story one,
// so reads use a session that is bound: the one already in use while it stays bound, else
// the focused session if it is bound, else the project's most recent one.
export function pickReadSession({ focusedId, boundIds = [], current = null } = {}) {
  if (current && boundIds.includes(current)) return current
  if (focusedId && boundIds.includes(focusedId)) return focusedId
  return boundIds[0] || focusedId || null
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

function currentStoryConnectionId() {
  try {
    return host.state.connectionId.get()
  } catch {
    return undefined
  }
}

// Story sessions open with the 'tab' intent. A session already on screen (for
// example a tile the person dragged to the side) is only focused, so the page
// keeps its place. One that is not on screen opens as a tab in the centre zone
// and covers the page: Hermes gives plugins no way to dock a session to a side.
export const STORY_SIDE_INTENT = 'tab'

export function storySessionOpenOptions(route, profile, connectionId = currentStoryConnectionId(), intent = 'in-place') {
  // Passing a route makes Hermes force the sidebar to "All profiles", and a
  // bare profile does the same unless keepAllProfilesScope is false. For the
  // connection the user is already on, open by profile and keep the sidebar
  // scoped to it. Only another connection needs the route to be reachable.
  // A tab may be a session nobody has written in yet; there is
  // no history to wait for, and waiting would only time out.
  const base = { intent, awaitHydration: true, expectHistory: intent === 'in-place', forceResume: true }
  const routeConnectionId = typeof route?.connectionId === 'string' ? route.connectionId.trim() : ''
  const activeConnectionId = typeof connectionId === 'string' ? connectionId.trim() : ''
  if (!route || (routeConnectionId && routeConnectionId === activeConnectionId)) {
    const target = (route?.targetProfile || route?.profile || profile || '').trim()
    return { profile: target, keepAllProfilesScope: false, ...base }
  }
  return { route, ...base }
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
  openSession = host.openSession,
  intent = 'in-place'
} = {}) {
  const normalizedSessionId = typeof sessionId === 'string' ? sessionId.trim() : ''
  const normalizedProfile = typeof profile === 'string' ? profile.trim() : ''
  if (!normalizedSessionId || !normalizedProfile) throw new Error('a session and Hermes profile are required')
  if (typeof openSession !== 'function') throw new Error('this Hermes Desktop version cannot open saved sessions')
  const route = await resolveStoryProfileRoute({ profile: normalizedProfile, connectionId, profileRoutes })
  return openSession(normalizedSessionId, storySessionOpenOptions(route, normalizedProfile, undefined, intent))
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
export const createStoryVolume = (projectId, body) =>
  call('/projects/' + encodeURIComponent(projectId) + '/volumes', { method: 'POST', body })
export const createStoryChapter = (projectId, volumeId, body) =>
  call('/projects/' + encodeURIComponent(projectId) + '/volumes/' + encodeURIComponent(volumeId) + '/chapters', { method: 'POST', body })
export const deleteStoryProject = (projectId, scope, confirmName) =>
  call(
    '/projects/' + encodeURIComponent(projectId) + buildStoryScopeQuery(scope) +
      '&confirm_name=' + encodeURIComponent(confirmName),
    { method: 'DELETE' }
  )
export const requestStoryWorkspace = (projectId, { profile, connectionId }) =>
  call('/projects/' + encodeURIComponent(projectId) + '/workspace', {
    method: 'POST',
    body: { profile, connection_id: connectionId }
  })
export const linkStoryWorkspace = (projectId, { profile, connectionId, hermesProjectId, folder }) =>
  call('/projects/' + encodeURIComponent(projectId) + '/workspace/link', {
    method: 'PUT',
    body: { profile, connection_id: connectionId, hermes_project_id: hermesProjectId, folder }
  })
export const fetchProjectProposals = (projectId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/proposals' + buildStoryScopeQuery(scope))
export const discardStoryProposal = (projectId, proposalId, scope) =>
  call(
    '/projects/' + encodeURIComponent(projectId) + '/proposals/' + encodeURIComponent(proposalId) + buildStoryScopeQuery(scope),
    { method: 'DELETE' }
  )
export const undoStoryAgentWrite = (projectId, targetId, { profile, connectionId, targetType }) =>
  call('/projects/' + encodeURIComponent(projectId) + '/chapters/' + encodeURIComponent(targetId) + '/undo', {
    method: 'POST',
    body: { profile, connection_id: connectionId, ...(targetType ? { target_type: targetType } : {}) }
  })
export const fetchStoryWrites = (projectId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/writes' + buildStoryScopeQuery(scope))
export const fetchProjectTree = (projectId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + buildStoryScopeQuery(scope))
export const fetchProjectSessions = (projectId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/sessions' + buildStoryScopeQuery(scope))
export const removeStorySession = (projectId, storedSessionId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/sessions/' + encodeURIComponent(storedSessionId) + buildStoryScopeQuery(scope), { method: 'DELETE' })
export const fetchChapter = (projectId, chapterId, scope) =>
  call('/projects/' + encodeURIComponent(projectId) + '/chapters/' + encodeURIComponent(chapterId) + buildStoryScopeQuery(scope))
export const fetchRecord = (projectId, targetType, recordId, scope) =>
  call(
    '/projects/' + encodeURIComponent(projectId) + '/records/' + encodeURIComponent(targetType) + '/' +
      encodeURIComponent(recordId) + buildStoryScopeQuery(scope)
  )
export const bindStorySession = body => call('/sessions/bind', { method: 'POST', body })
export const saveChapter = (projectId, chapterId, body) =>
  call(`/projects/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(chapterId)}/save`, { method: 'POST', body })

export async function continueStoryProjectSession({
  binding,
  profile,
  connectionId,
  profileRoutes = host.profileRoutes,
  openSession = host.openSession,
  intent = 'in-place'
} = {}) {
  const storedSessionId = requiredSessionId(binding?.stored_session_id, 'stored session')
  try {
    await switchStorySession({
      sessionId: storedSessionId,
      profile,
      connectionId,
      profileRoutes,
      openSession,
      intent
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

// Hermes' own session name (what its sidebar shows), keyed by session id.
export function storySessionTitles(sessions) {
  const titles = {}
  for (const session of Array.isArray(sessions) ? sessions : []) {
    const id = typeof session?.id === 'string' ? session.id : ''
    const title = typeof session?.title === 'string' ? session.title.trim() : ''
    if (id && title) titles[id] = title
  }
  return titles
}

// The name follows Hermes' sidebar; the title saved at bind time is only a
// fallback for when the Hermes list is unavailable.
export function storySessionName(storedSessionId, { titles = {}, bindings = [] } = {}) {
  if (!storedSessionId) return ''
  const binding = bindings.find(row => row.stored_session_id === storedSessionId)
  return titles[storedSessionId] || binding?.title || ''
}

// Hermes refuses session.delete while the gateway still holds the session in
// memory, and every session opened since the gateway started stays there. Close
// the idle ones first; one that is working is left alone so the delete reports
// that it is in use instead of cutting off a running turn.
async function closeLiveStorySession(requestProfile, route, storedSessionId) {
  let live = []
  try {
    const response = await requestProfile(route, 'session.active_list', {})
    live = Array.isArray(response?.sessions) ? response.sessions : []
  } catch {
    return // no live list: let session.delete report what is wrong
  }
  for (const row of live) {
    if (row?.session_key !== storedSessionId || !row?.id) continue
    if (row.status && row.status !== 'idle') throw new Error('the session is still working; try again when it is idle')
    await requestProfile(route, 'session.close', { session_id: row.id })
  }
}

// removeBinding only forgets the project link, so the Hermes session stays and
// can be bound again. deleteSession also deletes the Hermes session itself.
// Sessions are handled one by one so a failure never hides the ones that worked.
export async function removeStoryProjectSessions({
  projectId,
  storedSessionIds,
  profile,
  connectionId,
  deleteSession = false,
  profileRoutes = host.profileRoutes,
  requestProfile = host.requestProfile,
  removeSession = removeStorySession
} = {}) {
  const normalizedProjectId = requiredSessionId(projectId, 'project')
  const ids = [...new Set((Array.isArray(storedSessionIds) ? storedSessionIds : []).map(id => requiredSessionId(id, 'stored session')))]
  if (!ids.length) throw new Error('no sessions selected')
  const normalizedProfile = typeof profile === 'string' ? profile.trim() : ''
  if (!normalizedProfile) throw new Error('a Hermes profile is required')
  let route = null
  if (deleteSession) {
    if (typeof requestProfile !== 'function') throw new Error('this Hermes Desktop version cannot delete saved sessions')
    route = await resolveStoryProfileRoute({ profile: normalizedProfile, connectionId, profileRoutes })
    if (!route) throw new Error('the locked Hermes profile route is unavailable')
  }
  const done = []
  const failed = []
  for (const storedSessionId of ids) {
    try {
      if (deleteSession) {
        // Delete the Hermes session first: if that fails (for example Hermes
        // still has it open) nothing has changed. If it works and the unbind
        // below fails, the leftover is a stale binding with its own removal.
        await closeLiveStorySession(requestProfile, route, storedSessionId)
        try {
          await requestProfile(route, 'session.delete', {
            session_id: storedSessionId,
            profile: route.targetProfile || normalizedProfile
          })
        } catch (error) {
          // An already-missing session is the state we want.
          if (!isSessionGoneError(error)) throw error
        }
      }
      await removeSession(normalizedProjectId, storedSessionId, { profile: normalizedProfile, connectionId })
      done.push(storedSessionId)
    } catch (error) {
      failed.push({ storedSessionId, error })
    }
  }
  return { done, failed }
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

const HERMES_NO_PROJECT = 5062

function samePath(left, right) {
  const normalize = value => String(value || '').replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
  return Boolean(normalize(left)) && normalize(left) === normalize(right)
}

// Makes sure the Story project has its own folder and a Hermes project around
// it, so its writing sessions group together in the Hermes sidebar. The backend
// creates the folder (on the machine that serves this connection); Hermes only
// registers it. Every step is safe to repeat: an existing folder, link or
// Hermes project is reused.
export async function ensureStoryProjectWorkspace({
  project,
  profile,
  connectionId,
  profileRoutes = host.profileRoutes,
  requestProfile = host.requestProfile,
  requestFolder = requestStoryWorkspace,
  linkFolder = linkStoryWorkspace
} = {}) {
  const projectId = requiredSessionId(project?.id, 'project')
  const scope = { profile, connectionId }
  const { folder, link } = await requestFolder(projectId, scope)
  const normalizedFolder = requiredSessionId(folder, 'workspace folder')
  if (typeof requestProfile !== 'function') throw new Error('this Hermes Desktop version cannot create projects')
  const route = await resolveStoryProfileRoute({ profile, connectionId, profileRoutes })
  if (!route) throw new Error('the locked Hermes profile route is unavailable')
  const params = { profile: route.targetProfile || profile }

  if (link && link.folder && samePath(link.folder, normalizedFolder)) {
    try {
      if (link.archived) {
        await requestProfile(route, 'projects.archive', { ...params, id: link.hermes_project_id, restore: true })
      } else {
        await requestProfile(route, 'projects.get', { ...params, id: link.hermes_project_id })
      }
      return { folder: normalizedFolder, hermesProjectId: link.hermes_project_id }
    } catch (error) {
      // The Hermes project was deleted by hand: fall through and register a new one.
      if (error?.code !== HERMES_NO_PROJECT) throw error
    }
  }

  let hermesProjectId
  try {
    const created = await requestProfile(route, 'projects.create', {
      ...params,
      name: project.name || projectId,
      folders: [normalizedFolder],
      primary_path: normalizedFolder
    })
    hermesProjectId = created?.project?.id
  } catch (error) {
    // The folder already belongs to a Hermes project: adopt that one.
    const found = await requestProfile(route, 'projects.for_cwd', { ...params, cwd: normalizedFolder }).catch(() => null)
    hermesProjectId = found?.project?.id
    if (!hermesProjectId) throw error
  }
  hermesProjectId = requiredSessionId(hermesProjectId, 'hermes project')
  await linkFolder(projectId, { ...scope, hermesProjectId, folder: normalizedFolder })
  return { folder: normalizedFolder, hermesProjectId }
}

// Deleting a Story project archives its Hermes project (recoverable) and leaves
// the workspace folder alone.
export async function archiveHermesStoryProject({
  hermesProjectId,
  profile,
  connectionId,
  profileRoutes = host.profileRoutes,
  requestProfile = host.requestProfile
} = {}) {
  const id = requiredSessionId(hermesProjectId, 'hermes project')
  if (typeof requestProfile !== 'function') throw new Error('this Hermes Desktop version cannot archive projects')
  const route = await resolveStoryProfileRoute({ profile, connectionId, profileRoutes })
  if (!route) throw new Error('the locked Hermes profile route is unavailable')
  try {
    await requestProfile(route, 'projects.archive', { profile: route.targetProfile || profile, id })
  } catch (error) {
    if (error?.code !== HERMES_NO_PROJECT) throw error
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
  ensureWorkspace = ensureStoryProjectWorkspace,
  onStage = () => undefined,
  intent = 'in-place'
} = {}) {
  let route
  try {
    route = await resolveStoryProfileRoute({ profile, connectionId, profileRoutes })
    if (!route) throw new Error('the locked Hermes profile route is unavailable')
  } catch (error) {
    throw workflowError('routing', error)
  }

  // The project folder is what groups the session under a Hermes project. A
  // failure here never blocks the session: it is created without a folder and
  // the caller is told why.
  let workspace = null
  let workspaceIssue = null
  try {
    workspace = await ensureWorkspace({ project, profile, connectionId, profileRoutes, requestProfile })
  } catch (error) {
    workspaceIssue = safeStatusFromError(error)?.code || error?.detail?.code || error?.code || 'workspace_unavailable'
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
        follow_profile_config: true,
        ...(workspace ? { cwd: workspace.folder } : {})
      }, undefined, { spawnPriority: 'foreground' })
      runtimeId = requiredSessionId(created?.session_id, 'runtime session')
      storedId = requiredSessionId(created?.stored_session_id, 'stored session')
      // Hermes silently ignores a working directory it cannot use, so check
      // that it was applied instead of assuming.
      if (workspace && !samePath(created?.info?.cwd, workspace.folder)) workspaceIssue = 'workspace_not_applied'
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

    // No first task is submitted: the user speaks first and the Agent decides
    // from their words whether this is story work or a plain chat, learning the
    // bound project through story.get_session_project. The session has no
    // history yet, so the open must not wait for any.
    onStage?.('opening')
    try {
      await openSession(storedId, { ...storySessionOpenOptions(route, profile, undefined, intent), expectHistory: false })
    } catch (error) {
      throw workflowError('opening', error)
    }
    onStage?.('ready')
    return { storedSessionId: storedId, runtimeSessionId: runtimeId, binding, workspaceIssue }
  } finally {
    if (typeof release === 'function') release()
  }
}

export async function retryStoryKickoff({
  recovery,
  requestProfile = host.requestProfile,
  bindSession = bindStorySession,
  openSession = host.openSession,
  intent = 'in-place'
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
    await openSession(recovery.storedId, storySessionOpenOptions(recovery.route, recovery.profile, undefined, intent))
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

// Which kind of readable record a sidebar row is (null for rows that open nothing).
// The sidebar branch that lists each kind of readable record.
const RECORD_BRANCH = { character: 'characters', world_entry: 'worldInfo', note: 'notes' }

// Whether the record being viewed is still in the project (a deletion removes it).
export function recordStillListed(tree, record) {
  if (!record || !tree?.branches) return true
  const branch = tree.branches.find(item => item.id === RECORD_BRANCH[record.type])
  return Boolean(branch?.children.some(child => child.id === record.id))
}

export function recordTypeOf(branchId, child) {
  if (branchId === 'characters') return 'character'
  if (branchId === 'worldInfo') return 'world_entry'
  if (branchId === 'notes' && child?.kind === 'note') return 'note'
  return null
}

function ProjectBranch({ branch, onOpenChapter, onOpenRecord, selectedRecord, t }) {
  const children = branch.children.map(child => {
    const isChapter = branch.id === 'chapters'
    const recordType = recordTypeOf(branch.id, child)
    const open = isChapter
      ? () => onOpenChapter(child.id)
      : recordType && onOpenRecord
        ? () => onOpenRecord({ type: recordType, id: child.id })
        : undefined
    const selected = Boolean(recordType && selectedRecord?.type === recordType && selectedRecord?.id === child.id)
    return jsx(
      'button',
      {
        'aria-current': selected ? 'true' : undefined,
        className:
          'block w-full truncate rounded px-2 py-1 text-left hover:bg-(--chrome-action-hover) ' +
          (selected ? 'bg-(--chrome-action-hover) font-medium' : 'text-(--ui-text-secondary)'),
        onClick: open,
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

const SIDEBAR_NOTE_BRANCHES = ['worldInfo', 'characters', 'notes']

// Right-click menu entries are data, not markup: anything can add one with
// registerStoryMenuItem and it appears wherever its `kinds` apply. `kind` is
// the thing right-clicked: 'sidebar' (empty space), 'volume', or 'chapter'.
const storyMenuItems = []

export function registerStoryMenuItem(item) {
  storyMenuItems.push(item)
  return () => {
    const index = storyMenuItems.indexOf(item)
    if (index >= 0) storyMenuItems.splice(index, 1)
  }
}

export function storyMenuItemsFor(kind, target = {}, context = {}) {
  return storyMenuItems
    .filter(item => item.kinds.includes(kind) && (!item.when || item.when(target, context)))
    .sort((left, right) => (left.order ?? 100) - (right.order ?? 100))
    .map(item => ({
      id: item.id,
      labelKey: item.labelKey,
      disabled: Boolean(item.disabled?.(target, context)),
      run: () => item.run(target, context)
    }))
}

registerStoryMenuItem({
  id: 'story.newChapter',
  kinds: ['volume', 'chapter'],
  labelKey: 'tree.newChapter',
  order: 10,
  when: (target, context) => Boolean(context.onCreate && target.volumeId),
  disabled: (target, context) => Boolean(context.createBusy),
  run: (target, context) => context.onCreate('chapter', target.volumeId)
})

registerStoryMenuItem({
  id: 'story.newVolume',
  kinds: ['sidebar', 'volume', 'chapter'],
  labelKey: 'tree.newVolume',
  order: 20,
  when: (target, context) => Boolean(context.onCreate),
  disabled: (target, context) => Boolean(context.createBusy),
  run: (target, context) => context.onCreate('volume')
})

function StoryContextMenu({ kind, target, context, t, children }) {
  const { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem } = storySdk
  const items = storyMenuItemsFor(kind, target, context)
  if (!ContextMenu || !ContextMenuTrigger || !ContextMenuContent || !ContextMenuItem || !items.length) {
    return children
  }
  return jsxs(ContextMenu, {
    children: [
      jsx(ContextMenuTrigger, { asChild: true, children }),
      jsx(ContextMenuContent, {
        children: items.map(item =>
          jsx(ContextMenuItem, { disabled: item.disabled, onSelect: item.run, children: t(item.labelKey) }, item.id)
        )
      })
    ]
  })
}

function StoryCreateRow({ kind, defaultTitle, busy, error, onSubmit, onCancel, t }) {
  const [title, setTitle] = useState(defaultTitle)
  const submit = () => {
    const value = String(title || '').trim()
    if (value && !busy) onSubmit(value)
  }
  return jsxs('div', {
    className: 'flex flex-col gap-1 border-b border-(--ui-stroke-secondary) p-2',
    children: [
      jsx('input', {
        autoFocus: true,
        className: 'w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1',
        disabled: busy,
        onChange: event => setTitle(event.target.value),
        onKeyDown: event => {
          // Enter that confirms an IME candidate must not create the record.
          if (event.isComposing || event.nativeEvent?.isComposing) return
          if (event.key === 'Enter') {
            event.preventDefault()
            submit()
          } else if (event.key === 'Escape') {
            event.preventDefault()
            onCancel()
          }
        },
        placeholder: t(kind === 'volume' ? 'tree.volumeTitlePlaceholder' : 'tree.chapterTitlePlaceholder'),
        value: title
      }),
      error ? jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: error }) : null,
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          jsx('button', {
            className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hover:bg-(--chrome-action-hover) disabled:opacity-50',
            disabled: busy || !String(title || '').trim(),
            onClick: submit,
            type: 'button',
            children: busy ? t('tree.creating') : t('tree.createConfirm')
          }),
          jsx('button', {
            className: 'rounded px-2 py-1 text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) disabled:opacity-50',
            disabled: busy,
            onClick: onCancel,
            type: 'button',
            children: t('tree.createCancel')
          })
        ]
      })
    ]
  })
}

function ChapterOutline({ outline, onOpenChapter, selectedChapterId, creating, createBusy, createError, onCreate, onSubmitCreate, onCancelCreate, t }) {
  const realGroups = outline.filter(group => group.volume.id)
  const chapterTotal = outline.reduce((total, group) => total + group.chapters.length, 0)
  const menuContext = { onCreate, createBusy }
  // "New chapter" from the toolbar goes to the open chapter's volume, else the last volume.
  const selectedGroup = outline.find(
    group => group.volume.id && group.chapters.some(chapter => chapter.id === selectedChapterId)
  )
  const defaultVolumeId = (selectedGroup || realGroups.at(-1))?.volume.id || null
  const createRow = (kind, defaultTitle) =>
    jsx(
      StoryCreateRow,
      {
        busy: createBusy,
        defaultTitle,
        error: createError,
        kind,
        onCancel: onCancelCreate,
        onSubmit: onSubmitCreate,
        t
      },
      kind + ':' + (creating?.volumeId || '')
    )
  const toolbarButton = (label, onClick, disabled) =>
    jsx(
      'button',
      {
        className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
        disabled,
        onClick,
        type: 'button',
        children: label
      },
      label
    )
  return jsxs('div', {
    className: 'flex min-h-full flex-col',
    children: [
      onCreate
        ? jsxs('div', {
            className: 'flex gap-1 border-b border-(--ui-stroke-secondary) p-2',
            children: [
              toolbarButton(t('tree.newVolume'), () => onCreate('volume'), createBusy),
              toolbarButton(
                t('tree.newChapter'),
                () => defaultVolumeId && onCreate('chapter', defaultVolumeId),
                createBusy || !defaultVolumeId
              )
            ]
          })
        : null,
      creating?.kind === 'volume' ? createRow('volume', t('tree.defaultVolumeTitle', realGroups.length + 1)) : null,
      outline.length
        ? outline.map(group => {
            const summary = jsxs('summary', {
              className: 'flex cursor-pointer items-center gap-2 px-3 py-2',
              children: [
                jsx('span', { className: 'min-w-0 flex-1 truncate font-medium', children: displayName(group.volume, t) }),
                jsx('span', {
                  className: 'shrink-0 text-xs text-(--ui-text-tertiary)',
                  children: String(group.chapters.length)
                })
              ]
            })
            return jsxs(
              'details',
              {
                className: 'border-b border-(--ui-stroke-secondary)',
                open: true,
                children: [
                  group.volume.id
                    ? jsx(StoryContextMenu, {
                        children: summary,
                        context: menuContext,
                        kind: 'volume',
                        t,
                        target: { volumeId: group.volume.id }
                      })
                    : summary,
                  group.chapters.length
                    ? group.chapters.map(chapter => {
                        const button = jsx('button', {
                          'aria-current': chapter.id === selectedChapterId ? 'true' : undefined,
                          className:
                            'block w-full truncate px-4 py-2 text-left hover:bg-(--chrome-action-hover) ' +
                            (chapter.id === selectedChapterId
                              ? 'bg-(--chrome-action-hover) font-medium'
                              : 'text-(--ui-text-secondary)'),
                          onClick: () => onOpenChapter(chapter.id),
                          type: 'button',
                          children: displayName(chapter, t)
                        })
                        return group.volume.id
                          ? jsx(
                              StoryContextMenu,
                              {
                                children: button,
                                context: menuContext,
                                kind: 'chapter',
                                t,
                                target: { chapterId: chapter.id, volumeId: group.volume.id }
                              },
                              chapter.id
                            )
                          : jsx('div', { children: button }, chapter.id)
                      })
                    : jsx('div', { className: 'px-4 py-2 text-(--ui-text-tertiary)', children: t('tree.empty') }),
                  creating?.kind === 'chapter' && creating.volumeId === group.volume.id
                    ? createRow('chapter', t('tree.defaultChapterTitle', chapterTotal + 1))
                    : null
                ]
              },
              group.volume.id || 'unassigned'
            )
          })
        : jsx('div', { className: 'p-3 text-(--ui-text-tertiary)', children: t('tree.empty') }),
      // Empty space below the list is its own right-click target, so the
      // volume and chapter menus never nest inside another one.
      jsx(StoryContextMenu, {
        children: jsx('div', { className: 'min-h-16 flex-1' }),
        context: menuContext,
        kind: 'sidebar',
        t,
        target: {}
      })
    ]
  })
}

export function StorySidebar({ tree, tab = 'chapters', onTab, onOpenChapter, onOpenRecord, selectedRecord, selectedChapterId, creating, createBusy = false, createError = null, onCreate, onSubmitCreate, onCancelCreate, t }) {
  if (!tree) {
    return jsx('div', { className: 'p-3 text-(--ui-text-tertiary)', children: t('tree.selectProject') })
  }
  const tabButton = (id, label) =>
    jsx('button', {
      'aria-selected': tab === id,
      className:
        'flex-1 rounded px-3 py-1.5 text-center ' +
        (tab === id ? 'bg-(--chrome-action-hover) font-medium' : 'text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)'),
      onClick: () => onTab?.(id),
      role: 'tab',
      type: 'button',
      children: label
    }, id)
  const noteBranches = tree.branches.filter(branch => SIDEBAR_NOTE_BRANCHES.includes(branch.id))
  return jsxs('div', {
    className: 'flex min-h-0 flex-1 flex-col',
    children: [
      jsxs('div', {
        className: 'flex gap-1 border-b border-(--ui-stroke-secondary) p-2',
        role: 'tablist',
        children: [tabButton('chapters', t('tree.tabChapters')), tabButton('notes', t('tree.tabNotes'))]
      }),
      jsx('div', {
        className: 'min-h-0 flex-1 overflow-auto',
        children:
          tab === 'notes'
            ? noteBranches.map(branch => jsx(ProjectBranch, { branch, onOpenChapter, onOpenRecord, selectedRecord, t }, branch.id))
            : jsx(ChapterOutline, {
                createBusy,
                createError,
                creating,
                onCancelCreate,
                onCreate,
                onOpenChapter,
                onSubmitCreate,
                outline: tree.outline || [],
                selectedChapterId,
                t
              })
      })
    ]
  })
}

// How often open proposals are refreshed: quickly while the Agent is working
// (a proposal is most likely to appear then), slowly otherwise.
export function proposalPollInterval(busy) {
  return busy ? 5_000 : 30_000
}

export function approvalMinutesLeft(proposal, now = Date.now()) {
  const expires = Date.parse(proposal?.approval?.expires_at || '')
  if (!Number.isFinite(expires)) return 0
  return Math.max(0, Math.ceil((expires - now) / 60_000))
}

// Whitelisted wording for a failed proposal request; never the raw server text.
export function proposalErrorNote(error) {
  const detail = safeStatusFromError(error) || {}
  switch (detail.code) {
    case 'conflict':
      return Number.isInteger(detail.edit)
        ? { key: 'proposal.conflictAt', args: [detail.edit + 1] }
        : { key: 'proposal.conflict', args: [] }
    case 'version_changed':
      return { key: 'proposal.versionChanged', args: [] }
    case 'frontmatter_not_allowed':
      return { key: 'proposal.frontmatter', args: [] }
    case 'chapter_changed':
      return { key: 'proposal.undoChanged', args: [] }
    default:
      return { key: 'proposal.failed', args: [] }
  }
}

function InlineDiff({ parts }) {
  return jsx('pre', {
    className: 'whitespace-pre-wrap break-words rounded border border-(--ui-stroke-secondary) p-2 text-xs',
    children: (Array.isArray(parts) ? parts : []).map((part, index) =>
      jsx('span', {
        className: part.op === 'delete' ? 'hermes-story-diff-del' : part.op === 'insert' ? 'hermes-story-diff-ins' : undefined,
        children: part.text
      }, index)
    )
  })
}

const PROPOSAL_WARNING_KEYS = {
  leading_guidance: 'proposal.warnLeading',
  trailing_guidance: 'proposal.warnTrailing',
  duplicate_title: 'proposal.warnTitle',
  fence_removed: 'proposal.warnFence',
  name_in_use: 'proposal.warnNameInUse'
}

export function ProposalReview({ proposal, projectId, profile, connectionId, onClose, onChanged, t }) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  const scope = { profile, connectionId }
  const approved = proposal.status === 'approved'
  // A rename or a deletion acts on the whole record: nothing to select or edit.
  const isAction = proposal.kind === 'rename' || proposal.kind === 'delete'
  const stale = (proposal.kind === 'edit' || isAction) && proposal.current_version && proposal.current_version !== proposal.base_version
  const targetType = proposal.target_type || 'chapter'
  const isNew = String(proposal.kind || '').startsWith('new_')
  const title = proposal.target_title || proposal.chapter_title || proposal.title || ''

  const run = async work => {
    if (busy) return
    setBusy(true)
    setNote(null)
    try {
      await work()
    } catch (error) {
      setNote(proposalErrorNote(error))
    } finally {
      setBusy(false)
    }
  }

  const discard = () =>
    run(async () => {
      await discardStoryProposal(projectId, proposal.id, scope)
      await onChanged()
      onClose()
    })

  const buttonClass = 'rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50'

  return jsxs('div', {
    className: 'flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4',
    role: 'region',
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-2',
        children: [
          jsx('h2', {
            className: 'min-w-0 flex-1 truncate text-base font-medium',
            children: proposal.kind === 'rename'
              ? t('proposal.renameRecord', t('proposal.kind.' + targetType), title, proposal.new_title || '')
              : proposal.kind === 'delete'
                ? t('proposal.deleteRecord', t('proposal.kind.' + targetType), title)
                : isNew
                  ? t('proposal.newRecord', t('proposal.kind.' + targetType), title)
                  : t('proposal.editRecord', t('proposal.kind.' + targetType), title)
          }),
          jsx('span', {
            className: 'text-xs text-(--ui-text-secondary)',
            children: approved ? t('proposal.approvedLeft', approvalMinutesLeft(proposal)) : proposal.status === 'expired' ? t('proposal.expired') : t('proposal.pending')
          }),
          jsx('button', { className: buttonClass, onClick: onClose, type: 'button', children: t('proposal.close') })
        ]
      }),
      stale ? jsx('div', { className: 'hermes-story-danger text-xs', children: t('proposal.stale') }) : null,
      ...proposal.warnings.map((warning, index) =>
        jsxs('div', {
          className: 'hermes-story-danger text-xs',
          role: 'alert',
          children: [
            warning.kind === 'name_in_use'
              ? t('proposal.warnNameInUse')
              : `${t(PROPOSAL_WARNING_KEYS[warning.kind] || 'proposal.failed')} · ${t('proposal.changeN', warning.edit + 1, t('proposal.op.' + (proposal.edits[warning.edit]?.op || 'replace')))}`,
            warning.text ? jsx('div', { className: 'break-words text-(--ui-text-secondary)', children: warning.text }) : null
          ]
        }, index)
      ),
      isAction
        ? jsx('div', {
            className: 'rounded border border-(--ui-stroke-secondary) p-3 text-sm' + (proposal.kind === 'delete' ? ' hermes-story-danger' : ''),
            children: t(proposal.kind === 'delete' ? 'proposal.deleteHint' : 'proposal.renameHint')
          })
        : jsx('div', {
            className: 'flex flex-col gap-3',
            children: proposal.previews.map(preview =>
              jsxs('div', {
                className: 'flex flex-col gap-2 rounded border border-(--ui-stroke-secondary) p-2',
                children: [
                  jsx('div', {
                    className: 'text-xs text-(--ui-text-secondary)',
                    children: t('proposal.changeN', preview.edit + 1, t('proposal.op.' + preview.op))
                  }),
                  ...preview.regions.map((region, index) =>
                    jsxs('div', {
                      className: 'flex flex-col gap-1',
                      children: [
                        jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: t('proposal.line', region.line) }),
                        jsx(InlineDiff, { parts: region.inline })
                      ]
                    }, index)
                  )
                ]
              }, preview.edit)
            )
          }),
      note ? jsx('div', { className: 'text-xs text-(--ui-text-secondary)', role: 'status', children: t(note.key, ...note.args) }) : null,
      jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: t('proposal.chatHint') }),
      jsx('div', {
        className: 'flex flex-wrap gap-2',
        children: jsx('button', {
          className: buttonClass + ' hermes-story-danger',
          disabled: busy,
          onClick: discard,
          type: 'button',
          children: t('proposal.discard')
        })
      })
    ]
  })
}

// Shows what the Agent has proposed and lets the person review it. The chapter
// editor stays mounted underneath, hidden, so an unsaved draft is never lost.
function ProposalArea({ projectId, profile, connectionId, undoInStrip = true, children }) {
  const t = usePluginI18n('story-construction')
  const busy = useValue(host.state.busy)
  const queryClient = typeof storySdk.useQueryClient === 'function' ? storySdk.useQueryClient() : null
  const enabled = Boolean(projectId && profile && connectionId)
  const scope = { profile, connectionId }
  const proposalsQuery = useQuery({
    enabled,
    queryKey: ['story-construction', 'proposals', profile, connectionId, projectId],
    queryFn: () => fetchProjectProposals(projectId, scope),
    refetchInterval: proposalPollInterval(busy)
  })
  const writesQuery = useQuery({
    enabled,
    queryKey: ['story-construction', 'writes', profile, connectionId, projectId],
    queryFn: () => fetchStoryWrites(projectId, scope),
    refetchInterval: 30_000
  })
  const proposals = Array.isArray(proposalsQuery.data?.proposals) ? proposalsQuery.data.proposals : []
  const writes = Array.isArray(writesQuery.data?.writes) ? writesQuery.data.writes : []
  const [reviewId, setReviewId] = useState(null)
  const [undoNote, setUndoNote] = useState(null)
  const [undoing, setUndoing] = useState(false)
  const wasBusyRef = useMutableRef(busy)
  const lastWriteRef = useMutableRef(undefined)
  const reviewing = proposals.find(proposal => proposal.id === reviewId) || null
  const latestWrite = writes.find(write => !write.undone && ['edit', 'rename', 'delete'].includes(write.kind)) || null
  const openIds = proposals.map(proposal => proposal.id).join(',')
  const writeMark = writes[0] ? `${writes[0].proposal_id}:${writes[0].undone}` : ''

  useEffect(() => {
    setReviewId(null)
    setUndoNote(null)
  }, [projectId, profile, connectionId])

  // The moment the Agent stops working is when a proposal most likely appeared.
  useEffect(() => {
    if (wasBusyRef.current && !busy) {
      void proposalsQuery.refetch?.()
      void writesQuery.refetch?.()
    }
    wasBusyRef.current = busy
  }, [busy])

  // A proposal that left the open list may have been written: look at the log.
  useEffect(() => {
    void writesQuery.refetch?.()
  }, [openIds])

  // A new write (or an undo) changed a chapter: reload chapters and the tree.
  useEffect(() => {
    if (lastWriteRef.current !== undefined && lastWriteRef.current !== writeMark) {
      void queryClient?.invalidateQueries?.({ queryKey: ['story-construction'] })
    }
    lastWriteRef.current = writeMark
  }, [writeMark])

  const refresh = async () => {
    await Promise.allSettled([proposalsQuery.refetch?.(), writesQuery.refetch?.()])
  }

  const undo = () => {
    if (undoing || !latestWrite) return
    setUndoing(true)
    setUndoNote(null)
    void undoStoryAgentWrite(projectId, latestWrite.target_id || latestWrite.chapter_id, {
      ...scope,
      targetType: latestWrite.target_type
    })
      .then(async () => {
        setUndoNote({ key: 'proposal.undone', args: [] })
        await refresh()
        await queryClient?.invalidateQueries?.({ queryKey: ['story-construction'] })
      })
      .catch(error => {
        const note = proposalErrorNote(error)
        setUndoNote(note.key === 'proposal.failed' ? { key: 'proposal.undoFailed', args: [] } : note)
      })
      .finally(() => setUndoing(false))
  }

  const statusLabel = proposal =>
    proposal.status === 'approved'
      ? t('proposal.approvedLeft', approvalMinutesLeft(proposal))
      : proposal.status === 'expired'
        ? t('proposal.expired')
        : t('proposal.pending')

  const undoButton = latestWrite
    ? jsx('button', {
        className: 'rounded border border-(--ui-stroke-secondary) px-2 py-0.5 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
        disabled: undoing,
        onClick: undo,
        type: 'button',
        children: t('proposal.undo', latestWrite.target_title || latestWrite.chapter_title || latestWrite.chapter_id)
      })
    : null

  const strip = proposals.length || (latestWrite && undoInStrip) || undoNote
    ? jsxs('div', {
        className: 'flex flex-col gap-1 border-b border-(--ui-stroke-secondary) px-3 py-2 text-xs',
        children: [
          proposals.length
            ? jsxs('div', {
                className: 'flex flex-wrap items-center gap-2',
                children: [
                  jsx('span', { className: 'font-medium', children: t('proposal.strip', proposals.length) }),
                  ...proposals.map(proposal =>
                    jsx('button', {
                      className: 'rounded border border-(--ui-stroke-secondary) px-2 py-0.5 hover:bg-(--chrome-action-hover)',
                      onClick: () => setReviewId(proposal.id),
                      type: 'button',
                      children: `${proposal.target_title || proposal.chapter_title || proposal.title || proposal.id} · ${statusLabel(proposal)}`
                    }, proposal.id)
                  )
                ]
              })
            : null,
          undoInStrip && undoButton ? jsx('div', { children: undoButton }) : null,
          undoNote ? jsx('div', { className: 'text-(--ui-text-secondary)', role: 'status', children: t(undoNote.key, ...undoNote.args) }) : null
        ]
      })
    : null

  return jsxs('div', {
    className: 'flex min-h-0 flex-1 flex-col',
    children: [
      strip,
      reviewing
        ? jsx(ProposalReview, {
            connectionId,
            onChanged: refresh,
            onClose: () => setReviewId(null),
            profile,
            projectId,
            proposal: reviewing,
            t
          }, reviewing.id)
        : null,
      jsx('div', {
        className: 'flex min-h-0 flex-1 flex-col',
        style: reviewing ? { display: 'none' } : undefined,
        children: typeof children === 'function' ? children(undoButton) : children
      })
    ]
  })
}

// A character, world entry or note, shown as text. Changes go through the Agent's proposals.
function RecordViewer({ projectId, record, profile, connectionId, sessionId }) {
  const t = usePluginI18n('story-construction')
  const query = useQuery({
    enabled: Boolean(projectId && record && sessionId && profile && connectionId),
    queryKey: ['story-construction', 'record', profile, connectionId, sessionId, projectId, record?.type, record?.id],
    queryFn: () => fetchRecord(projectId, record.type, record.id, { sessionId, profile, connectionId })
  })
  if (query.isLoading) {
    return jsx('div', { className: 'p-4 text-(--ui-text-secondary)', children: t('record.loading') })
  }
  if (query.error) {
    return jsx('div', { className: 'p-4 text-(--ui-text-secondary)', children: t('record.unavailable', query.error.message) })
  }
  const row = query.data?.record
  if (!row || row.id !== record.id) return null
  return jsxs('div', {
    className: 'flex min-h-0 flex-1 flex-col',
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
        children: [
          jsx('span', { className: 'text-base font-medium', children: row.title || t('tree.untitled') }),
          jsx('span', { className: 'text-xs text-(--ui-text-tertiary)', children: t('record.kind.' + row.target_type) }),
          row.reference
            ? jsx('span', { className: 'rounded border border-(--ui-stroke-secondary) px-1.5 text-xs', children: t('record.reference') })
            : null
        ]
      }),
      jsx('div', {
        className: 'min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words px-4 py-3 leading-relaxed',
        children: row.content || jsx('span', { className: 'text-(--ui-text-tertiary)', children: t('record.empty') })
      }),
      jsx('div', {
        className: 'border-t border-(--ui-stroke-secondary) px-4 py-2 text-xs text-(--ui-text-tertiary)',
        children: t('record.readOnly')
      })
    ]
  })
}

function ChapterEditor({ projectId, chapterId, profile, connectionId, sessionId, draftStore, onDraftState, leadAction = null }) {
  const t = usePluginI18n('story-construction')
  const chapterQuery = useQuery({
    enabled: Boolean(projectId && chapterId && sessionId && profile && connectionId),
    queryKey: ['story-construction', 'chapter', profile, connectionId, sessionId, projectId, chapterId],
    queryFn: () => fetchChapter(projectId, chapterId, { sessionId, profile, connectionId })
  })
  const chapter = chapterQuery.data?.chapter || chapterQuery.data || null
  const [draft, setDraft] = useState('')
  const [baseline, setBaseline] = useState('')
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
    if (!canConfirmSave({ draft, confirmed: true })) return
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
        className: 'flex items-center gap-2',
        children: [
          jsx('h2', {
            className: 'min-w-0 flex-1 truncate text-base font-medium',
            title: chapter.title || chapter.id,
            children: chapter.title || chapter.id
          }),
          saveState
            ? jsx('span', {
                className: 'shrink-0 text-xs text-(--ui-text-tertiary)',
                children: t(saveState.key, ...saveState.args)
              })
            : null,
          leadAction,
          jsx('button', {
            className: 'shrink-0 rounded border border-(--ui-stroke-secondary) px-3 py-0.5 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
            disabled: saving || draft === baseline || !canConfirmSave({ draft, confirmed: true }) || !sessionId,
            onClick: save,
            type: 'button',
            children: t('chapter.saveConfirmed')
          })
        ]
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
      connection_id: connectionId,
      locale: t('workspace.localeCode')
    })
      .then(async created => {
        const projectId = requiredSessionId(created?.tree?.project?.id, 'created project')
        // Give the project its Hermes project and folder in the background. It
        // is safe to repeat and never blocks creation: opening a writing
        // session tries again and reports what is wrong.
        void ensureStoryProjectWorkspace({
          project: { id: projectId, name: created?.tree?.project?.name || normalized.name },
          profile,
          connectionId
        }).catch(() => undefined)
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

// Deleting is a typed-name confirmation: the folder only moves to the Vault
// trash, but the name is still required so a stray click cannot start it.
function DeleteProjectDialog({ project, profile, connectionId, onDeleted, onClose, getGeneration, t }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const aliveRef = useMutableRef(true)
  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
    }
  }, [])
  const scope = { profile, connectionId }
  const treeQuery = useQuery({
    enabled: Boolean(project?.id && profile && connectionId),
    queryKey: ['story-construction', 'delete-preview', profile, connectionId, project?.id],
    queryFn: () => fetchProjectTree(project.id, scope)
  })
  const sessionsQuery = useQuery({
    enabled: Boolean(project?.id && profile && connectionId),
    queryKey: ['story-construction', 'delete-sessions', profile, connectionId, project?.id],
    queryFn: () => fetchProjectSessions(project.id, scope)
  })
  const volumeCount = Array.isArray(treeQuery.data?.volumes) ? treeQuery.data.volumes.length : null
  const chapterCount = Array.isArray(treeQuery.data?.chapters) ? treeQuery.data.chapters.length : null
  const sessionCount = projectSessionRows(sessionsQuery.data).length
  const matches = Boolean(project?.name) && typed.trim() === String(project.name).trim()

  const submit = event => {
    event.preventDefault()
    if (busy || !matches) return
    const requestGeneration = typeof getGeneration === 'function' ? getGeneration() : null
    const requestLive = () => aliveRef.current &&
      (requestGeneration === null || requestGeneration === (typeof getGeneration === 'function' ? getGeneration() : null))
    setBusy(true)
    setFailed(false)
    void deleteStoryProject(project.id, scope, project.name)
      .then(async result => {
        // Archive, never delete, the Hermes project; a failure only leaves it listed.
        if (result?.hermes_project_id) {
          await archiveHermesStoryProject({ hermesProjectId: result.hermes_project_id, profile, connectionId }).catch(
            () => undefined
          )
        }
        if (!requestLive()) return
        await onDeleted(project.id, { ...scope, generation: requestGeneration, folder: result?.trash_folder || '' })
        if (!requestLive()) return
        onClose()
      })
      .catch(() => {
        if (requestLive()) setFailed(true)
      })
      .finally(() => {
        if (requestLive()) setBusy(false)
      })
  }

  return jsx('div', {
    className: 'hermes-story-overlay fixed inset-0 z-50 flex items-center justify-center p-4',
    onMouseDown: event => {
      if (event.target === event.currentTarget && !busy) onClose()
    },
    children: jsxs('form', {
      'aria-modal': 'true',
      className: 'flex w-full max-w-sm flex-col gap-3 rounded border hermes-story-danger-border border-red-400 p-4 shadow',
      style: { backgroundColor: 'var(--chrome-bg, var(--ui-bg, Canvas))' },
      onKeyDown: event => {
        if (event.key === 'Escape' && !busy) onClose()
      },
      onSubmit: submit,
      role: 'alertdialog',
      children: [
        jsx('h2', { className: 'text-base font-medium', children: t('library.deleteTitle', project.name) }),
        volumeCount !== null && chapterCount !== null
          ? jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: t('library.deleteCounts', volumeCount, chapterCount) })
          : null,
        jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: t('library.deleteMoves') }),
        sessionCount
          ? jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: t('library.deleteSessions', sessionCount) })
          : null,
        jsxs('label', {
          className: 'flex flex-col gap-1 text-xs text-(--ui-text-secondary)',
          children: [
            t('library.deleteTypeName', project.name),
            jsx('input', {
              autoFocus: true,
              className: 'rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs',
              disabled: busy,
              value: typed,
              onChange: event => setTyped(event.target.value)
            })
          ]
        }),
        failed ? jsx('div', { className: 'text-xs hermes-story-danger text-red-400', role: 'alert', children: t('library.deleteFailed') }) : null,
        jsxs('div', {
          className: 'flex justify-end gap-2',
          children: [
            jsx('button', {
              className: 'rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
              disabled: busy,
              onClick: onClose,
              type: 'button',
              children: t('dialog.cancel')
            }),
            jsx('button', {
              className: 'rounded border hermes-story-danger-border border-red-400 px-3 py-1 text-xs hermes-story-danger text-red-400 disabled:opacity-50',
              disabled: busy || !matches,
              type: 'submit',
              children: busy ? t('library.deleting') : t('library.deleteConfirm')
            })
          ]
        })
      ]
    })
  })
}

function ProjectLibrary({ projects, loading, error, ready, profile, connectionId, onOpen, onRetry, onCreated, onDeleted, getGeneration, t }) {
  const [term, setTerm] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [menuFor, setMenuFor] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [notice, setNotice] = useState(null)
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
      notice
        ? jsx('div', { className: 'text-xs text-(--ui-text-secondary)', role: 'status', children: t('library.deleted', notice) })
        : null,
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
                  children: visible.map(item => jsxs('div', {
                    className: 'relative flex',
                    onKeyDown: event => {
                      if (event.key === 'Escape') setMenuFor(null)
                    },
                    children: [
                      jsxs('button', {
                        className: 'flex min-w-0 flex-1 items-center gap-3 rounded border border-(--ui-stroke-secondary) p-3 pr-10 text-left hover:bg-(--chrome-action-hover)',
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
                      }),
                      jsx('button', {
                        'aria-expanded': menuFor === item.id,
                        'aria-haspopup': 'menu',
                        'aria-label': t('library.projectMenu'),
                        className: 'absolute right-2 top-2 rounded px-2 text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        disabled: !ready,
                        onClick: () => setMenuFor(previous => (previous === item.id ? null : item.id)),
                        type: 'button',
                        children: '⋯'
                      }),
                      menuFor === item.id
                        ? jsx('div', {
                            className: 'fixed inset-0 z-10',
                            onMouseDown: () => setMenuFor(null)
                          })
                        : null,
                      menuFor === item.id
                        ? jsx('div', {
                            className: 'absolute right-2 top-9 z-20 flex flex-col rounded border border-(--ui-stroke-secondary) py-1 shadow',
                            role: 'menu',
                            style: { backgroundColor: 'var(--chrome-bg, var(--ui-bg, Canvas))' },
                            children: jsx('button', {
                              className: 'px-3 py-1 text-left text-xs hermes-story-danger text-red-400 hover:bg-(--chrome-action-hover)',
                              onClick: () => {
                                setMenuFor(null)
                                setDeleting(item)
                              },
                              role: 'menuitem',
                              type: 'button',
                              children: t('library.deleteProject')
                            })
                          })
                        : null
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
        : null,
      deleting
        ? jsx(DeleteProjectDialog, {
            connectionId,
            getGeneration,
            onClose: () => setDeleting(null),
            onDeleted: async (projectId, request) => {
              await onDeleted(projectId, request)
              setNotice(request.folder || projectId)
            },
            profile,
            project: deleting,
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
  const [managing, setManaging] = useState(false)
  const [selectedIds, setSelectedIds] = useState({})
  const [confirm, setConfirm] = useState(null)
  const sessionsQuery = useQuery({
    enabled: Boolean(project?.id && profile && connectionId),
    queryKey: ['story-construction', 'project-sessions', profile, connectionId, project?.id],
    queryFn: () => fetchProjectSessions(project.id, { profile, connectionId }),
    refetchInterval: 60_000
  })
  const sessions = projectSessionRows(sessionsQuery.data)
  // Hermes' own session names, so this panel follows its sidebar.
  const titlesQuery = useQuery({
    enabled: Boolean(profile && connectionId),
    queryKey: ['story-construction', 'session-titles', profile, connectionId],
    queryFn: () => listStorySessions({ profile, connectionId }),
    refetchInterval: 30_000
  })
  const titles = storySessionTitles(titlesQuery.data?.sessions)
  const nameOf = id => storySessionName(id, { titles, bindings: sessions }) || t('agent.untitledSession')
  const focusedBound = Boolean(sessionId && sessions.some(row => row.stored_session_id === sessionId))
  const selectedCount = Object.keys(selectedIds).length

  useEffect(() => {
    setBindingState(null)
    setSessionState(null)
    setKickoffRecovery(null)
    setStaleSessionIds({})
    setManaging(false)
    setSelectedIds({})
    setConfirm(null)
  }, [project?.id, profile, connectionId])

  const toggleManaging = () => {
    if (creatingSession) return
    setManaging(previous => !previous)
    setSelectedIds({})
    setConfirm(null)
  }

  const toggleSelected = id => {
    setSelectedIds(previous => {
      const next = { ...previous }
      if (next[id]) delete next[id]
      else next[id] = true
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelectedIds(
      selectedCount === sessions.length ? {} : Object.fromEntries(sessions.map(row => [row.stored_session_id, true]))
    )
  }

  const runRemove = () => {
    if (creatingSession || !confirm || !project?.id) return
    // Hermes refuses to delete the session that is open, so do not even try.
    if (confirm.hard && confirm.ids.includes(sessionId)) return
    setCreatingSession(true)
    setSessionState({ key: 'agent.removing', args: [] })
    void removeStoryProjectSessions({
      projectId: project.id,
      storedSessionIds: confirm.ids,
      profile,
      connectionId,
      deleteSession: confirm.hard
    })
      .then(async ({ done, failed }) => {
        await Promise.allSettled([sessionsQuery.refetch(), titlesQuery.refetch?.()])
        setSelectedIds({})
        setConfirm(null)
        setSessionState(
          failed.length
            ? { key: 'agent.removedPartial', args: [done.length, failed.length, failed[0].error?.message || 'unknown error'] }
            : { key: 'agent.removed', args: [done.length] }
        )
      })
      .catch(error => setSessionState({ key: 'agent.removeFailed', args: [error.message] }))
      .finally(() => setCreatingSession(false))
  }

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
      openSession: openAfterRefetch,
      intent: STORY_SIDE_INTENT
    })
      .then(result => {
        setStage('ready')
        if (result?.workspaceIssue) {
          setSessionState({
            key: result.workspaceIssue === 'workspace_unsupported_backend' ? 'agent.workspaceUnsupported' : 'agent.workspaceUnavailable',
            args: []
          })
        }
      })
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
    void retryStoryKickoff({ recovery: kickoffRecovery, openSession: openAfterRefetch, intent: STORY_SIDE_INTENT })
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
    void continueStoryProjectSession({ binding, profile, connectionId, intent: STORY_SIDE_INTENT })
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
      project_name: project.name,
      ...(storySessionName(sessionId, { titles }) ? { title: storySessionName(sessionId, { titles }) } : {})
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
      jsx('div', { className: 'font-medium', children: t('agent.currentSession') }),
      jsx('div', {
        className: 'break-words text-(--ui-text-secondary)',
        children: `${busy ? t('agent.working') : t('agent.idle')} · ${sessionId ? nameOf(sessionId) : t('agent.noFocusedSession')}`
      }),
      sessions.length
        ? jsx('button', {
            className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 text-left hover:bg-(--chrome-action-hover) disabled:opacity-50',
            disabled: creatingSession,
            onClick: () => continueSession(sessions[0]),
            type: 'button',
            children: t('agent.focusLatest')
          })
        : null,
      jsx('div', { className: 'font-medium', children: t('agent.sessions') }),
      jsx('button', {
        className: 'hermes-story-btn-primary rounded bg-(--ui-accent) px-2 py-1 text-left disabled:opacity-50',
        disabled: creatingSession || !project?.id,
        onClick: createSession,
        type: 'button',
        children: t('agent.newWritingSession')
      }),
      sessions.length
        ? jsxs('div', {
            className: 'flex flex-wrap gap-2',
            children: [
              jsx('button', {
                className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hover:bg-(--chrome-action-hover) disabled:opacity-50',
                disabled: creatingSession,
                onClick: toggleManaging,
                type: 'button',
                children: managing ? t('agent.doneManaging') : t('agent.manageSessions')
              }),
              managing
                ? jsx('button', {
                    className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hover:bg-(--chrome-action-hover) disabled:opacity-50',
                    disabled: creatingSession,
                    onClick: toggleSelectAll,
                    type: 'button',
                    children: selectedCount === sessions.length ? t('agent.clearSelection') : t('agent.selectAll')
                  })
                : null,
              managing
                ? jsx('button', {
                    className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hermes-story-danger text-red-400 hover:bg-(--chrome-action-hover) disabled:opacity-50',
                    disabled: creatingSession || !selectedCount,
                    onClick: () => setConfirm({ ids: Object.keys(selectedIds), hard: false }),
                    type: 'button',
                    children: t('agent.deleteSelected', selectedCount)
                  })
                : null
            ]
          })
        : null,
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
                      jsxs('div', {
                        className: 'flex items-center gap-2',
                        children: [
                          managing
                            ? jsx('input', {
                                'aria-label': t('agent.selectSession', nameOf(storedSessionId)),
                                checked: Boolean(selectedIds[storedSessionId]),
                                disabled: creatingSession,
                                onChange: () => toggleSelected(storedSessionId),
                                type: 'checkbox'
                              })
                            : null,
                          jsx('div', { className: 'min-w-0 flex-1 truncate', children: nameOf(storedSessionId) })
                        ]
                      }),
                      jsxs('div', {
                        className: 'mt-1 flex flex-wrap gap-2',
                        children: [
                          managing
                            ? jsx('button', {
                                className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hermes-story-danger text-red-400 hover:bg-(--chrome-action-hover) disabled:opacity-50',
                                disabled: creatingSession,
                                onClick: () => setConfirm({ ids: [storedSessionId], hard: false }),
                                type: 'button',
                                children: t('agent.deleteOne')
                              })
                            : jsx('button', {
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
      confirm
        ? jsxs('div', {
            className: 'flex flex-col gap-2 rounded border hermes-story-danger-border border-red-400 p-2',
            role: 'alertdialog',
            children: [
              jsx('div', { className: 'font-medium', children: t('agent.confirmCount', confirm.ids.length) }),
              jsx('div', { className: 'text-(--ui-text-tertiary)', children: t('agent.confirmUnbindHint') }),
              jsxs('label', {
                className: 'flex items-start gap-2',
                children: [
                  jsx('input', {
                    checked: confirm.hard,
                    disabled: creatingSession,
                    onChange: () => setConfirm(previous => ({ ...previous, hard: !previous.hard })),
                    type: 'checkbox'
                  }),
                  jsx('span', { children: t('agent.confirmHardLabel') })
                ]
              }),
              confirm.hard && confirm.ids.includes(sessionId)
                ? jsx('div', { className: 'hermes-story-danger text-red-400', children: t('agent.confirmHardActive') })
                : null,
              jsxs('div', {
                className: 'flex flex-wrap gap-2',
                children: [
                  jsx('button', {
                    className:
                      'rounded border px-2 py-1 disabled:opacity-50 ' +
                      (confirm.hard ? 'hermes-story-danger-border border-red-400 hermes-story-danger text-red-400' : 'border-(--ui-stroke-secondary)'),
                    disabled: creatingSession || (confirm.hard && confirm.ids.includes(sessionId)),
                    onClick: runRemove,
                    type: 'button',
                    children: confirm.hard ? t('agent.confirmHard') : t('agent.confirmUnbind')
                  }),
                  jsx('button', {
                    className: 'rounded border border-(--ui-stroke-secondary) px-2 py-1 hover:bg-(--chrome-action-hover) disabled:opacity-50',
                    disabled: creatingSession,
                    onClick: () => setConfirm(null),
                    type: 'button',
                    children: t('agent.confirmCancel')
                  })
                ]
              })
            ]
          })
        : null,
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
      focusedBound
        ? jsx('div', {
            className: 'break-words text-(--ui-text-secondary)',
            children: t('agent.boundSession', nameOf(sessionId))
          })
        : jsx('button', {
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
  onCancelVaultChange,
  t
}) {
  const messageKey = mode === 'changeVault'
    ? 'status.changeVault'
    : mode === 'checking'
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
              }),
              typeof onCancelVaultChange === 'function'
                ? jsx('button', {
                    className: 'self-start rounded border border-(--ui-stroke-secondary) px-3 py-1 text-xs hover:bg-(--chrome-action-hover)',
                    disabled: savingVaultRoot,
                    onClick: onCancelVaultChange,
                    type: 'button',
                    children: t('status.cancelChangeVault')
                  })
                : null
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
  const changingVault = vaultCorrectionActive && readiness.ready && !writePending
  const gateOpen = !changingVault && storyWorkspaceGate({
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
        // The previous Vault's projects and bindings no longer apply.
        storyProjectMemory.set({ profile, connectionId }, null)
        setProjectSelection({ profile, connectionId, projectId: null })
        void projectsQuery.refetch()
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
  const [projectSelection, setProjectSelection] = useState(() => ({
    profile,
    connectionId,
    projectId: storyProjectMemory.get({ profile, connectionId })
  }))
  const selectedProjectId = selectedProjectForScope(projectSelection, { profile, connectionId })
  const [selectedChapterId, setSelectedChapterId] = useState(null)
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [sidebarTab, setSidebarTab] = useState('chapters')
  const [creatingRecord, setCreatingRecord] = useState(null)
  const [createState, setCreateState] = useState({ busy: false, error: null })
  const selectedProjectIdRef = useMutableRef(selectedProjectId)
  selectedProjectIdRef.current = selectedProjectId

  // A different (connection, Profile) resumes whatever that scope last had open.
  useEffect(() => {
    setProjectSelection(previous =>
      previous.profile === profile && previous.connectionId === connectionId
        ? previous
        : { profile, connectionId, projectId: storyProjectMemory.get({ profile, connectionId }) }
    )
  }, [profile, connectionId])

  // A remembered project that no longer exists (deleted, or another Vault) must
  // not strand the page on an empty workspace: fall back to the library.
  useEffect(() => {
    if (!selectedProjectId || !projectsQuery.data || projectsQuery.isFetching) return
    if (projects.some(item => item.id === selectedProjectId)) return
    storyProjectMemory.set({ profile, connectionId }, null)
    setProjectSelection({ profile, connectionId, projectId: null })
  }, [selectedProjectId, projectsQuery.data, projectsQuery.isFetching, profile, connectionId])
  // Same query as the sessions panel, so the list is fetched once.
  const boundQuery = useQuery({
    enabled: Boolean(selectedProjectId && profile && connectionId && gateOpen),
    queryKey: ['story-construction', 'project-sessions', profile, connectionId, selectedProjectId],
    queryFn: () => fetchProjectSessions(selectedProjectId, { profile, connectionId }),
    refetchInterval: 60_000
  })
  const boundIds = projectSessionRows(boundQuery.data).map(row => row.stored_session_id)
  const readSessionRef = useMutableRef(null)
  const readSessionId = pickReadSession({ focusedId: sessionId, boundIds, current: readSessionRef.current })
  readSessionRef.current = readSessionId
  const [scope, setScope] = useState({ profile, connectionId, sessionId: readSessionId, projectId: null, tree: null, selectedChapterId: null, status: 'idle' })

  useEffect(() => {
    setScope(previous => resetWorkspaceScope(previous, { profile, connectionId, sessionId: readSessionId, projectId: selectedProjectId }))
    setSelectedChapterId(null)
    setSelectedRecord(null)
  }, [profile, connectionId, readSessionId, selectedProjectId])

  const treeQuery = useQuery({
    // Wait for the bound sessions, or the first read would use an unbound one and fail.
    enabled: Boolean(selectedProjectId && readSessionId && profile && connectionId && gateOpen && !boundQuery.isLoading),
    queryKey: ['story-construction', 'project-tree', profile, connectionId, readSessionId, selectedProjectId],
    queryFn: () => fetchProjectTree(selectedProjectId, { sessionId: readSessionId, profile, connectionId })
  })
  const tree = treeQuery.data ? buildProjectTree(treeQuery.data.tree || treeQuery.data, t) : scope.tree
  const project = tree?.project || projects.find(item => item.id === selectedProjectId) || null

  // A record that was deleted while it was open: close the viewer instead of showing an error.
  useEffect(() => {
    if (treeQuery.data && !treeQuery.isFetching && !recordStillListed(tree, selectedRecord)) setSelectedRecord(null)
  }, [treeQuery.data, treeQuery.isFetching, selectedRecord])

  // A creation row belongs to the project it was opened in.
  useEffect(() => {
    setCreatingRecord(null)
    setCreateState({ busy: false, error: null })
  }, [selectedProjectId, profile, connectionId])

  const cancelCreate = () => {
    setCreatingRecord(null)
    setCreateState({ busy: false, error: null })
  }

  const startCreate = (kind, volumeId) => {
    if (!selectedProjectId || createState.busy) return
    setSidebarTab('chapters')
    setCreatingRecord({ kind, volumeId: kind === 'chapter' ? volumeId : null })
    setCreateState({ busy: false, error: null })
  }

  const submitCreate = title => {
    const request = creatingRecord
    if (!request || !selectedProjectId || createState.busy) return
    // Like project creation, a late answer must not touch a view it did not come from.
    const generation = viewGenerationRef.current
    const projectId = selectedProjectId
    const live = () => generation === viewGenerationRef.current && selectedProjectIdRef.current === projectId
    const body = { title, profile, connection_id: connectionId }
    setCreateState({ busy: true, error: null })
    const created = request.kind === 'volume'
      ? createStoryVolume(projectId, body)
      : createStoryChapter(projectId, request.volumeId, body)
    void created
      .then(async result => {
        await treeQuery.refetch()
        if (!live()) return
        setCreatingRecord(null)
        setCreateState({ busy: false, error: null })
        if (request.kind === 'chapter' && result?.chapter?.id) setSelectedChapterId(result.chapter.id)
      })
      .catch(error => {
        if (!live()) return
        // Generic copy plus a whitelisted status, never the raw error text.
        const invalid = storyDiagnostic(error, null).httpStatus === 422
        setCreateState({ busy: false, error: t(invalid ? 'tree.createInvalid' : 'tree.createFailed') })
      })
  }

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
    storyProjectMemory.set({ profile, connectionId }, projectId)
    setProjectSelection({ profile, connectionId, projectId })
    setSelectedChapterId(null)
  }

  const backToLibrary = () => {
    if (!guardLeave({ kind: 'project' })) return
    storyProjectMemory.set({ profile, connectionId }, null)
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
    storyProjectMemory.set({ profile: request.profile, connectionId: request.connectionId }, projectId)
    setProjectSelection({ profile: request.profile, connectionId: request.connectionId, projectId })
    setSelectedChapterId(null)
  }

  const handleDeleted = async (projectId, request) => {
    if (request?.generation !== viewGenerationRef.current) return
    // The deleted project must not be reopened from the remembered selection.
    if (storyProjectMemory.get({ profile: request.profile, connectionId: request.connectionId }) === projectId) {
      storyProjectMemory.set({ profile: request.profile, connectionId: request.connectionId }, null)
    }
    await projectsQuery.refetch()
  }

  if (!gateOpen) {
    // Loading, failed and not-ready status all collapse into one compact Retry
    // card; the operable workspace stays hidden until a fresh matching /status.
    // Pending/failed activation and owner mismatch get their own copy and make
    // no target /status or /projects request.
    const diagnostic = settingsFailure || statusFailure || storyDiagnostic(null, status)
    const statusCode = diagnostic.code || readiness.code
    const mode = changingVault
      ? 'changeVault'
      : activationState === 'pending'
      ? 'activating'
      : selectionBlocked
        ? 'activationFailed'
        : statusError
          ? 'error'
          : verifiedCurrent
            ? 'notReady'
            : 'checking'
    const onRetry = changingVault
      ? null
      : activationState === 'failed' && selection
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
            onCancelVaultChange: changingVault
              ? () => {
                  setVaultCorrectionActive(false)
                  setVaultRootInput('')
                }
              : null,
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
              children: storyDiagnostic(treeQuery.error, null).httpStatus === 403 && !boundIds.length
                ? t('workspace.needsSession')
                : t('workspace.projectUnavailable', treeQuery.error.message)
            })
          : jsx(StorySidebar, {
              createBusy: createState.busy,
              createError: createState.error,
              creating: creatingRecord,
              onCancelCreate: cancelCreate,
              onCreate: startCreate,
              onOpenChapter: id => {
                setSelectedChapterId(id)
                setSelectedRecord(null)
              },
              onOpenRecord: setSelectedRecord,
              onSubmitCreate: submitCreate,
              selectedRecord,
              onTab: setSidebarTab,
              selectedChapterId,
              t,
              tab: sidebarTab,
              tree
            })
    ]
  })
  const editorCell = jsx('div', {
    className: 'hermes-story-editor',
    children: jsx(ProposalArea, {
      connectionId,
      profile,
      projectId: selectedProjectId,
      // Undo sits beside Save in the chapter header; with no chapter on screen it stays in the strip.
      undoInStrip: Boolean(selectedRecord || !selectedChapterId),
      // The chapter editor stays mounted (hidden) while a record is shown, so an
      // unsaved draft and an in-flight save are never lost by looking at a character.
      children: undoButton => [
        jsx('div', {
          className: 'flex min-h-0 flex-1 flex-col',
          style: selectedRecord ? { display: 'none' } : undefined,
          children: jsx(ChapterEditor, {
            chapterId: selectedChapterId,
            connectionId,
            draftStore: draftsRef,
            leadAction: undoButton,
            onDraftState: handleDraftState,
            profile,
            projectId: selectedProjectId,
            sessionId: readSessionId
          })
        }, 'chapter'),
        selectedRecord
          ? jsx(RecordViewer, {
              connectionId,
              profile,
              projectId: selectedProjectId,
              record: selectedRecord,
              sessionId: readSessionId
            }, 'record')
          : null
      ]
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
          surface !== 'workspace'
            ? jsx('button', {
                className: 'ml-auto shrink-0 rounded border border-(--ui-stroke-secondary) px-2 py-1 text-xs hover:bg-(--chrome-action-hover)',
                onClick: () => setVaultCorrectionActive(true),
                type: 'button',
                children: t('workspace.changeVaultPath')
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
            onDeleted: handleDeleted,
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
.hermes-story-danger{color:#f87171}
.hermes-story-danger-border{border-color:#f87171}
.hermes-story-diff-del{background:rgba(239,68,68,.22);text-decoration:line-through}
.hermes-story-diff-ins{background:rgba(34,197,94,.22)}
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
      }
    ])
    // The sidebar and palette labels are plain strings, so they are registered
    // again whenever the Hermes language changes. Registering them once would
    // freeze whatever language was active at load time.
    const registerLabels = () =>
      ctx.registerMany([
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
    let disposeLabels = registerLabels()
    if (typeof ctx.i18n.onLocaleChange === 'function') {
      const stopWatching = ctx.i18n.onLocaleChange(() => {
        disposeLabels?.()
        disposeLabels = registerLabels()
      })
      ctx.onDispose?.(() => {
        if (typeof stopWatching === 'function') stopWatching()
        disposeLabels?.()
      })
    }
  }
}

export default plugin
