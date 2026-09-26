# Story Construction 多 Profile 后端与 503 修复设计

状态：待审核

日期：2026-09-23

## 目标与边界

让从 Git 安装的 Story Construction 在 WSL Hermes 中可用：用户在插件 UI 选择当前 Profile，所有 Profile 使用同一个 Obsidian Vault，但会话绑定按 Profile 隔离。Dashboard 与 Gateway 即使是不同进程，项目创建、会话绑定和 Story 工具也必须一致；已准备好的 Profile A→B→A 切换不需要重启。修复当前 API 已挂载却返回 `runtime_uninitialized` 的 503。

本阶段只改 Story Construction 插件的后端、配置契约、测试和安装说明。不改 Hermes SDK、Dashboard/Gateway 核心、项目 Markdown 格式或卡片式项目库前端。前端后续使用本规格的状态与配置接口；本规格不声称 UI 已经完成。模型调用仍由 Hermes 正常 Agent 会话负责，不在插件 API 内另建 LLM 客户端。

## 安装拓扑

同一 Git 子目录是唯一插件包来源，清单名始终为 `story-construction`。默认 Hermes 根目录保留一份正式安装，供 Dashboard 发现并挂载 `/api/plugins/story-construction/`；每个非 default 写作 Profile 再通过 Hermes 的 Profile 作用域正式安装一份，供该 Profile 的 Agent 注册 Story 工具和提示。default 被选为写作 Profile 时复用默认安装。不能通过移动文件夹、手动复制、`Install here` 按钮或客户端 Windows 路径来推断安装完成。

Dashboard 只扫描启动 home 与默认根目录，因此目标 Profile 单独安装不足以提供 API。首次安装或更新默认目录的 API 文件后，Dashboard 需要重新挂载插件；首次在目标 Profile 安装/启用 Agent 部分后，既有 Agent 会话不能中途获得新工具，新建会话或按 Hermes 正式加载流程重载。后续在已安装且就绪的 Profile 之间切换不要求重启。本阶段默认 API 包与目标 Agent 包的 `plugin.yaml` 版本必须相同；不同时拒绝写入并报告版本不匹配。

## 配置来源与 Profile 选择

默认 home 的 `config.yaml` 在 `plugins.entries.story-construction.settings` 下保存唯一的 `selected_profile` 与共用 `vault_root`。每个目标 Profile 的同名 settings 保留现有 `locked_profile`、`locked_hermes_home`、`vault_root`；目标 `vault_root` 必须与默认 home 中规范化后的共用 Vault 路径相同。这样现有 Agent 运行时仍只在自身 Profile home 上授权，而默认 Dashboard API 有明确的共用 Vault 来源。切换 Profile 仅改变默认 home 的 `selected_profile`，不会迁移项目或会话文件，也不会把旧 Profile 的绑定复制到新 Profile。

插件提供后端设置接口，供未来 UI 选择 Profile，并在首次配置时提交 Vault 路径。服务端必须通过 Hermes 的 Profile 解析能力取得目标 home，确认该 Profile 的 `story-construction` 已正式安装且启用、包版本兼容，并检查 Vault 是服务端可读写的目录。不能从请求体接受 `hermes_home`，不能把客户端传来的 `profile` 或 `connection_id` 当作身份凭据。首次设置在目标 Profile 的插件 settings 写入经解析的 `locked_profile`、`locked_hermes_home` 与共用 `vault_root`，再写默认 home 的 `selected_profile`；前一步失败时默认选择保持不变。已有目标配置若指向另一 Vault，返回明确冲突，不静默覆盖。受管理配置或权限拒绝写入时保持原有选择并返回可操作错误。

配置写入只修改上述插件 settings，不重写其他 YAML 键；复用 Hermes 现有的原始配置读取、锁和原子合并写入能力，并在正确的 Profile 作用域内执行。Dashboard API 没有 Agent 进程的 `PluginContext`，因此这一步接受对 Hermes 内部 Python 配置接口的局部依赖；把依赖集中在一个配置适配层，并用真实导入的回归测试防止 SDK 升级时静默失效。不新增 `HERMES_*` 行为配置环境变量。

## API 独立初始化

默认目录的 `dashboard/plugin_api.py` 不能再靠查找 Gateway 曾调用 `register()` 后遗留在 `sys.modules` 的运行时对象。API 根据默认配置中的 `selected_profile` 解析目标 home、读取目标 settings，使用默认安装包中的 Story 组件自行准备 `(插件包, 目标 home)` 运行时和 Vault 仓库；模块加载不得污染全局 `sys.path` 或误用其他 Profile 的同名模块。每次请求都核对当前选择和配置版本；改变选择后，新 API 请求获得新作用域，进行中的 API 写入在提交前再次核对选择，不能把旧 Profile 的结果写入新作用域。UI 选择不是 Gateway 工具的授权依据：另一个 Profile 的既有会话仍按其自身持久绑定受控。

API 已挂载时，`GET /status` 返回不含 Vault 实际路径和凭据的状态：所选 Profile、目标安装/启用状态、配置是否完整、Vault 是否可用、绑定文件是否有效以及 `ready`。API 未挂载时该端点不存在，客户端必须将 404 视为安装/重载问题。`GET/POST /projects`、会话绑定与章节保存只在目标 Profile 就绪时执行。未就绪应区分未安装、未启用、配置缺失、Profile/Vault 不匹配、Vault 不可用、包版本不兼容和绑定损坏；不得在有可恢复原因时笼统返回 `runtime_uninitialized`。插件 API 仍走 Hermes 已有的受保护命名空间，不创建无鉴权旁路。

## 跨进程绑定与权限

目标 Profile 的 `$HERMES_HOME/plugin-data/story-construction/sessions.json` 是该 Profile 会话绑定的唯一持久来源。Dashboard API 是绑定/解绑的写入方：写前读取最新文件，序列化同一文件的并发写，原子替换；写失败时不保留只有本进程可见的授权。Gateway 的工具处理器不能继续依赖 `register()` 时载入的一次性 `StoryPermissionGate`：每次工具授权前从该 Profile 的文件读取并校验最新绑定，文件丢失或损坏时拒绝而非退回到旧内存授权。Dashboard 的会话列表、读取和保存也遵守同一规则。绑定后下一次工具调用立即可见；解绑后下一次调用立即拒绝；两个进程重启后结果不变。

校验继续匹配会话 ID、来源、Profile、连接和项目，不允许仅凭请求里的 Profile 或项目 ID 扩权。项目创建可在尚无聊天会话时进行，但仅在已选择且就绪的 Profile/Vault 下开放。章节写入仍要求 Desktop 会话绑定、`confirmed=true` 和现有版本冲突检查。系统提示在会话开始时按已有注册方式确定，不因绑定文件变化而重建当前对话提示或动态变更工具集；新安装/启用的工具只对重新建立的 Agent 会话生效。

## 失败与恢复

- 默认 API 包未安装或 Dashboard 尚未重新挂载：插件 API 不存在；安装/更新后按 Hermes 正式流程重新加载 Dashboard，不能将 404 伪装成空项目。
- 目标包未安装或未启用：状态指出目标 Profile 和所需安装动作，不尝试在 Story API 中私自复制或移动包。
- 设置缺失、受管理配置、Vault 路径不可用或版本不兼容：返回稳定错误码与非敏感说明，禁止项目写入和绑定；不泄露绝对 Vault 路径。
- 绑定文件损坏或跨进程写入冲突：拒绝授权及写入，保留文件供排查，不自动清空或覆盖。
- 首次配置/安装后已有会话没有 Story 工具：提示新建会话或执行 Hermes 正式重载，不在活动会话中破坏提示缓存。

## 验收

使用临时默认 home、Profile A 和 Profile B，不触碰真实用户配置或 Vault。测试加载真实插件模块，并让 Dashboard API 与 Agent 工具在不同进程中运行；不能只用一个进程共享的 mock 状态代替跨进程验证。

1. 仅默认安装时 API 可挂载但报告目标 Profile 未安装；仅目标 Profile 安装时不能假定 Dashboard 已挂载 API。两处安装且版本一致后，设置 API 写入正确的两个 `config.yaml` 作用域，其他键保持不变。
2. API 在没有 Gateway `register()` 的进程中独立返回 ready 并创建 Obsidian 项目；Vault 只在指定临时目录出现。无会话创建项目后可创建/绑定 Hermes 会话。
3. Dashboard 绑定后，未重启的 Gateway 下一次 Story 工具调用立即成功；解绑后立即拒绝。重启两个进程后绑定按文件恢复；损坏文件 fail closed。
4. A→B→A 切换共享同一 Vault，但各自只看到自己的会话绑定；错误 Profile、连接、项目及另一个 Vault 均不能获得授权。
5. 测试首次安装/启用后的旧会话不热注入工具、错误码可区分、配置写入失败不改变默认选择，以及两个并发绑定写不会丢失已确认的记录。

验收通过后再单独规划前端 Profile 选择与卡片式项目库；本规格本身不宣称已解决现场 503。
