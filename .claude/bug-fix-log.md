# Bug 修复记录

本文件用于记录 `dev-time-agent` 的重要 bug、回归、排障结论和修复验证。轻微拼写或纯格式调整不需要记录。

## 记录模板

```markdown
## YYYY-MM-DD - 问题标题

### 现象

用户或系统看到的具体问题。

### 影响

说明影响范围、严重程度和是否阻塞主要流程。

### 原因

定位到的根因。避免只写“逻辑错误”。

### 修复

说明改了什么文件、什么逻辑，以及为什么这样修。

### 验证

列出执行过的命令、手动检查或回归测试。

### 后续

可选。记录需要补充的测试、文档或重构。
```

## 修复记录

## 2026-06-15 - GitHub 对象查询缺少 PR/Issue/Checks 覆盖

### 现象

用户要求“查看 dev-time-agent 的 CI”时，Agent 仍可能进入风险解释或澄清路径，而不是列出该仓库的 GitHub Checks。类似地，PR、Issue 查询也缺少完整对象级能力口径。

### 影响

影响 Dev Time 的核心定位。项目深度依赖 GitHub 事实源，Agent 不能只解释风险，还必须能查询授权范围内的 GitHub repo、PR、Issue 和 CI/Checks。

### 原因

早期 GitHub 工具层只覆盖授权状态和仓库列表，Agent 的 fallback router 没有为 PR、Issue、Checks 建立独立 intent、tool 和 reporter。用户查询 GitHub 对象时，容易被旧的 `risk_explain` 关键词规则吞掉。

### 修复

补齐 `github_pull_requests_list`、`github_issues_list`、`github_checks_list` 三类 intent。新增 `github.pull_requests.list`、`github.issues.list`、`github.checks.list` 工具，分别调用 `dev-time-server` internal API。fallback graph 增加 PR、Issue、Checks reporter，先列仓库定位 repository_id，再读取对应对象并返回 `tool_calls` 和 evidence_refs。

### 验证

- `uv run pytest tests/test_tool_layer.py::test_agent_session_turn_lists_repository_checks_through_fallback_tools -q`
- `uv run pytest tests/test_tool_layer.py::test_agent_session_turn_lists_github_repositories_through_fallback_tools tests/test_tool_layer.py::test_agent_session_turn_lists_repository_pull_requests_through_fallback_tools tests/test_tool_layer.py::test_agent_session_turn_lists_repository_issues_through_fallback_tools tests/test_tool_layer.py::test_agent_session_turn_lists_repository_checks_through_fallback_tools -q`

### 后续

继续补齐 commits、branches、releases、milestones、workflow runs、review comments 等 GitHub 对象，并建立 GitHub intent eval。

## 2026-06-15 - GitHub 项目查询被误路由为风险澄清

### 现象

用户在 Agent dock 输入“查看我的 github 项目”时，Agent 返回“你想让我评估当前风险、解释证据，还是生成下一步行动计划？”，意图显示为“需要澄清”。

### 影响

影响 GitHub 授权和仓库可见性查询的基础体验。用户明确要求查看 GitHub 项目时，Agent 不应进入风险解释澄清路径。

### 原因

`github.auth.status` 和 `github.repos.list` 工具已经存在，LLM planner 路径也有 GitHub 仓库访问计划归一化，但 deterministic fallback 路径只识别风险、状态、行动计划和自我介绍。未配置 LLM 或走 fallback 时，“查看我的 github 项目”会落入 `clarify`。

### 修复

在 `conversation.py` 增加 GitHub 仓库访问意图识别，返回 `github_repository_list` 和 `requires_tool=true`。在 `fallback_graph_nodes.py` 增加 `github_repository_reporter`，通过 ToolRegistry 调用 `github.auth.status` 和 `github.repos.list`，根据授权状态返回仓库列表或明确的授权提示。同步在 `graph_runtime.py` 接入新 graph node。

### 验证

- `uv run pytest tests/test_tool_layer.py::test_agent_session_turn_lists_github_repositories_through_fallback_tools -q`
- `uv run ruff check . && uv run pytest -q`

### 后续

需要继续把 GitHub 相关意图纳入 intent eval，覆盖“有哪些仓库”“能看到我的 repo 吗”“GitHub 授权了吗”等同义表达。

## 2026-06-13 - Agent 对话未走真实 LLM 且答非所问

### 现象

用户问“如何测试你”或“你好”时，Agent 会把问题误判成当前风险解释，返回“当前风险原因：go test failed...”。即使前端已配置 DeepSeek/OpenAI，会话 runtime 仍主要依赖本地关键词和模板路径，没有真正通过配置的 LLM 完成意图理解、回复生成和审核。

### 影响

影响 Agent dock 的核心可信度。用户无法把它当成项目风险驱动 Agent 使用，只会看到固定模板和错误路由；写操作草稿也缺少明确的人类确认门。

### 原因

会话 graph 只有 deterministic intent router 和固定 responder。之前的 LLM 能力主要服务 AgentJob artifact 生成，没有接入 session turn 的公开 HTTP 路径；同时缺少 verifier 节点审核答非所问和 approval gate 处理写操作建议。

### 修复

新增 `conversation_llm.py`，通过 `DEV_TIME_SERVER_INTERNAL_BASE_URL` 从 `dev-time-server` 获取 active OpenAI/DeepSeek provider config，再调用 OpenAI-compatible `/chat/completions`。会话 graph 升级为 `context_assembler -> llm_planner -> llm_tool_executor -> response_generator -> response_verifier`，并在 LLM 草稿包含写操作时返回 `approval_request`。同时将 LLM 节点、fallback 节点和 graph state 拆分到独立模块，保持文件低于行数规范。

### 验证

- `uv run ruff check . && uv run pytest -q`
- 新增测试覆盖生产路径读取 DeepSeek provider 配置并完成三次 LLM 调用。
- 新增测试覆盖“如何测试你”不会被误答成风险原因。
- 新增测试覆盖 verifier 改写答非所问草稿。
- 新增测试覆盖写操作草稿必须产生 `approval_request`。

### 后续

需要继续扩展真实工具集、长任务 checkpoint、多 Agent handoff 和可量化 eval runner。

## 2026-06-12 - Agent 多轮追问丢失上一轮风险上下文

### 现象

用户先问“为什么这是高风险？”，Agent 能基于 EvidenceBundle 解释风险；随后继续问“下一步呢”时，如果请求没有携带新的 EvidenceBundle，Agent 只能回退到空上下文或泛化回答，无法延续上一轮风险原因和 evidence_refs。

### 影响

影响 Agent dock 的核心体验。用户无法像 Codex 类对话一样围绕同一风险连续追问，Agent 显得无记忆、不智能。

### 原因

LangGraph runtime 每轮调用只使用当前请求状态，上一轮风险摘要只存在进程内 dict，且没有持久化 store。服务重载或没有新证据包的后续请求无法恢复上一轮上下文。

### 修复

新增 `src/dev_time_agent/memory.py`，提供 `InMemorySessionMemoryStore` 和 `SQLiteSessionMemoryStore`。`graph_runtime.py` 通过 store 接口读取/写入 session memory，保存上一轮意图、风险原因、风险等级、风险分和 evidence_refs。设置 `DEV_TIME_AGENT_SESSION_MEMORY_DB_PATH` 后使用 SQLite 持久化，未设置时保持进程内存。

### 验证

- `uv run ruff check . && uv run pytest -q`
- 新增测试覆盖同一 session 的两轮追问。
- 新增测试覆盖 SQLite store 重载后仍可继续基于上一轮风险生成行动计划。

## 已知风险

- 本文件由脚手架初始化，后续应根据项目真实问题持续维护。
- 如果项目尚未建立自动化测试、格式化或 lint 流程，应在 `tech-stack.md` 中补充验证策略。

## 2026-07-22 - Agent 错项目、错 PR 归因与模型身份不透明

### 现象

“当前项目是什么”被路由为澄清；项目 Issue 查询重新枚举仓库；PR #12 诊断读取仓库第一个失败 check；空 signals/events 被序列化为 null；Agent 介绍不说明实际模型。Server 还会在 Runtime 前抢答 GitHub 问题，并在 Runtime 失败后静默走旧直连 LLM。

### 原因

会话没有 Server 授权的统一事实边界，PageContext、Server classifier、LLM planner 和 fallback reporter 各自解析对象，provenance 无法保持。

### 修复

引入 Trusted Risk Context 和 Risk Episode Conversation Runtime Seam；可信仓库直接驱动 Issue 查询，Risk Episode 的 PR/head/check run 驱动日志诊断；模型按 Workspace 加载并在自我介绍中展示；配置 Runtime 时移除预路由、直连 LLM 与静默回退；空集合稳定输出 `[]`。

### 验证

- 可执行 eval 真实调用 Runtime 公共接口并断言四个核心 bad case。
- `uv run pytest -q`
- `uv run ruff check .`

## 2026-07-22 - 未配置 Workspace 模型导致自我介绍接口 5xx

### 现象

已配置 Agent Runtime、但当前 Workspace 没有 active LLM provider 时，请求“介绍自己”会在 context assembler 中因内部模型配置 404 而失败。

### 原因与修复

Runtime 在确定性意图路由前急切加载模型，却没有把配置 404 映射为合法的 deterministic adapter。现在只对 404 返回无 LLM，并由自我介绍明确展示 `deterministic / rules-v1`；其他 HTTP 或网络错误继续显式失败。

### 验证

新增同生产 payload 结构的回归测试，使用 Workspace-scoped 模型配置 404，断言自我介绍返回 200 和 deterministic identity。

## 2026-07-22 - 当前项目查询被模型依赖拖成 5xx

### 现象

生产请求“当前的项目是什么”同时在 `/turns` 与 `/turns/stream` 报错。此前补充“当前项目是什么”的整句匹配后仍可被一个虚词变体绕过。

### 影响

用户已经提供 Trusted Risk Context，Runtime 本可直接回答当前仓库，却仍依赖模型配置与模型网络；任一依赖异常都会让普通与流式会话共同失败。

### 原因

`context_assembler` 在意图路由前急切解析 Workspace 模型，模型 Adapter Seam 位于确定性控制之前；当前项目识别又使用完整句子白名单。两个 HTTP 入口共享同一 Runtime 调用链，因此同时暴露同一缺陷。

### 修复

新增 Deterministic Conversation Control Plane Module，以组合语义谓词识别当前项目身份问题，并在模型 Adapter 之前选择 direct/model 路径。模型解析移动到独立的 lazy `model_resolver`。`RiskEpisodeConversationRuntime` 统一将外部网络、HTTP、超时与上游 payload/schema 故障转换为 `runtime_dependency_unavailable` Markdown Grounded Turn，不再返回 5xx 或伪造风险结论。

### 验证

- 精确生产句式的公开 Runtime 回归与 executable eval。
- 强制模型配置解析抛错，断言当前项目请求仍为 200 且模型解析次数为 0。
- 强制模型端口不可达，断言返回结构化降级响应而非 500。
- Server 普通 JSON 与 SSE 两入口均以相同原句返回 `current_context`。
- `uv run pytest -q && uv run ruff check .`。
