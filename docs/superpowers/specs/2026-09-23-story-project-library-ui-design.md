# Story Construction 项目库与就绪状态 UI 设计

状态：待审核

日期：2026-09-23

## 背景与目标

现有页面把项目下拉框、新建表单、项目树、章节编辑和写作会话同时摆在三栏工作区。后端返回 `runtime_uninitialized` 时，页面直接显示完整 IPC/HTTP JSON 错误，并留下三个无法使用的空区域。空章节状态没有占满中间列，会话栏也没有明确宽度。

本次借鉴 [OpenFic](https://github.com/syrizelink/OpenFic) 的项目库优先思路，但保留 Hermes 自身侧栏与视觉变量，不复制独立导航或编造封面、最近编辑等当前接口没有的数据。目标流程是：选择当前 Profile，在共用的 Obsidian Vault 中创建或打开项目，然后创建/继续该 Profile 的写作会话，最后进入章节编辑与 Hermes 主聊天。切换 Profile 时项目文件共用，会话绑定和编辑状态隔离。

## 范围与前置条件

- 只改 Story Construction 插件的 Desktop 页面及相关前端测试。不改 Hermes SDK、Hermes 后端加载器、Markdown 数据格式或现有 Story API 的写入语义。
- 使用现有 `GET /status`、`GET /projects`、`POST /projects` 和项目会话接口。页面门禁不等于修复 503：现场检查时，WSL Dashboard 能挂载 default 安装目录的 API，却未在该进程初始化 Story runtime；相关 Profile 也缺少 Story 设置。状态不为 `ready` 时不得显示项目创建可用。
- “选择 Profile 后更新 `config.yaml`”、共用 Vault 的配置来源、Git 默认安装目录下的安全初始化、非 default Profile 的原生 Story 工具加载，需要单独的插件后端设计与验收。现有 `/status` 没有配置写入能力；本 UI 改造不得自行编辑 YAML、绕过 `locked_profile`，或把请求体里的 `profile` 当作可信身份。
- 本规格交付后，真实环境创建项目仍可能返回 503。只有另行完成后端修复及端到端验证，才能宣称完整工作流恢复。

## 页面状态

先查询 `/status`，只有 `ready=true` 且返回的 `locked_profile` 与当前选中 Profile 一致，才查询项目列表或允许写入；状态查询失败不能当作“项目为空”。进入页面、Profile/连接变化、用户点击重试和窗口重新获得焦点时重新检查状态；成功创建项目后刷新列表。状态查询与项目查询的缓存键都必须包含 `(connectionId, profile)`。

| 状态 | 主体 | 操作 |
| --- | --- | --- |
| 状态加载中 | 简短加载提示 | 无写入 |
| 状态请求失败 | 服务不可用卡片 | 重试、展开技术详情 |
| `ready=false` | 按 `code` 呈现未就绪卡片 | 重试、展开详情；无项目写入 |
| 项目加载中或失败 | 项目库外壳与加载/错误卡片 | 失败可重试，旧数据不可冒充当前结果 |
| 就绪且无项目 | 空项目库与醒目的新建按钮 | 新建项目 |
| 就绪且有项目 | 响应式项目卡片网格 | 搜索、打开、新建 |
| 已打开项目 | 项目工作区 | 返回项目库、章节和会话操作 |

顶部始终显示故事构建、当前 `(connectionId, profile)` 和状态。Profile 候选来自 `host.profileRoutes()`；同名 Profile 需展示连接来源并以完整 route 区分。选择时通过公开 `host.ensureAgent` 激活目标后端并核对 `host.state`；激活不成功则不发送项目请求。UI 选择只改变运行中的视图和路由，不能被描述为已经持久写入 `config.yaml`。进入项目后标题区显示返回项目库、项目名与当前 Profile，不再放内联新建表单。

## 项目库

- “新建项目”打开轻量对话框，复用现有项目名、可选 slug、前端校验和 `POST /projects`。成功后刷新列表并进入新项目；失败后保留输入并在表单内显示错误。
- 卡片只展示 `GET /projects` 当前返回的 `id` 和 `name`，可使用统一书本图标。不增加封面、最近编辑、章节数或导入功能。
- 搜索仅在当前列表按名称和 ID 做大小写不敏感过滤，不新增后端搜索接口。搜索无匹配与 Vault 无项目分别显示不同空状态。
- 网格随容器宽度降列，窄窗口不产生水平滚动。加载列表不再自动选中第一个项目，避免跳过项目库。

## 项目工作区与切换

- 左侧项目树固定合理宽度；中间章节区占剩余空间并有 `min-width: 0`；右侧写作会话栏固定宽度且可收起。窄窗口把会话栏变成可展开区域，避免挤压编辑器。
- 未选章节时居中提示从项目树打开章节；无写作会话时突出“新建写作会话”，手动绑定当前会话退为次要操作。未选项目时不渲染三栏。
- 既有新建并绑定会话、发送首条任务、打开 Hermes 主聊天、继续会话、重试首条任务、移除过期绑定和章节确认保存语义保持不变。
- 由插件发起的项目或 Profile 切换，若有未保存章节草稿，先确认离开；取消则保留原项目与草稿。保存中禁用插件自己的切换按钮。Hermes 其他界面仍可在此时切换 Profile，插件不能拦截：此时立即隐藏旧作用域数据，将未保存草稿只在当前页面生命周期内按 `(connectionId, profile, sessionId, projectId, chapterId)` 暂存；返回同一作用域可恢复草稿，页面重载不承诺恢复。所有异步完成回调必须核对原作用域，不能把旧响应写进新视图。

## 错误与权限

- 对 `runtime_uninitialized`、`configuration_incomplete`、`hermes_home_mismatch`、`vault_not_directory` 提供简洁的中英文说明；未知代码使用通用“插件暂不可用”。不暗示前端已具备后端配置能力。
- 不在页面正文铺开 `Error invoking remote method ... 503: {detail: ...}`。展开的技术详情只展示白名单字段，如状态码与已知 `code`；不直接呈现原始异常字符串或未审查的服务端 `message`，避免泄露 Vault 路径、令牌或配置内容。
- 未就绪时不请求 `/projects`、不提交创建、绑定或保存。已打开项目期间若状态变为未就绪，隐藏可操作工作区并显示可重试状态卡。
- API 的 `profile` 和 `connection_id` 仍是作用域数据，不是后端授权证明。现有 `locked_profile`、会话绑定、Vault 路径与 `confirmed=true` 校验不放宽。

## 实现边界与验收

围绕现有 `ProjectWorkspace`、`NewProjectForm`、`ProjectTree`、`ChapterEditor`、`ProjectSessionsPanel` 拆出小的项目库、状态卡和创建对话框。只用 Hermes 公开 SDK、React 与现有样式变量；磁盘插件仍需通过单文件 Blob ESM 加载，不能引入相对模块导入或新增运行时依赖。中英双语沿用 `STORY_LOCALES` 与 `usePluginI18n()`。

1. `/status` 未就绪或失败时不请求项目列表/创建；显示可重试状态卡，原始 JSON 不横向溢出。
2. 无项目时只显示空项目库；有项目时显示卡片，搜索正确，点击卡片才进入工作区。
3. 创建成功后进入新项目；失败后保留输入且可重试。
4. 在两个 `(connectionId, profile)` 作用域间 A→B→A 切换时，项目、章节和会话状态不串用；插件发起的离开需确认，Hermes 外部切换后的未保存草稿在页面生命周期内可恢复。
5. 宽、窄容器下三栏不重叠，空章节提示占满中间区域，会话栏不漂在页面中央。
6. 中英文文案、会话编排和保存保护保持可用；Desktop 插件通过 Blob 等效加载测试。

上述测试只证明 UI 行为。真实 WSL 503、Profile 配置写入和所选 Profile 的原生工具可用性必须另列插件后端端到端验收。
