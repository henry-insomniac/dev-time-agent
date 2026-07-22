# 项目架构

## 项目定位

`dev-time-agent`：Dev Time 的 Agent Runtime 服务，负责 AgentJob 消费、EvidenceBundle 构建、Agent workflow 编排、LLM 调用、结构化输出校验、评估回放和行动草稿生成。

本文件用于记录当前仓库边界、目录职责、关键架构决策和后续扩展原则。跨项目产品定位和三服务架构以 `product-prd.md`、`technical-architecture.md` 和 `dev-time-agent-architecture.md` 为准。

## 跨项目基础文档

以下文档属于 Dev Time 产品级基础文档，必须在 `dev-time`、`dev-time-server` 和 `dev-time-agent` 三个仓库中保持同源更新：

- `product-prd.md`：产品定位、目标用户、MVP、风险模型、Agent 场景、信息架构和视觉方向。
- `technical-architecture.md`：三服务架构、GitHub 集成、事件存储、风险引擎、AgentJob、LLM Gateway、通知层和 API 边界。
- `dev-time-agent-architecture.md`：Agent Runtime 服务的定位、边界、工作流、数据契约、安全约束和 MVP 阶段建议。

## 当前仓库职责

`dev-time-agent` 负责 Agent 智能分析能力：

- 消费 `dev-time-server` 创建的 AgentJob。
- 通过 server internal API 获取 EvidenceBundle。
- 执行 Risk Scout、PR Doctor、Milestone Planner、Scope Guard、Daily Brief、Action Drafter 等 workflow。
- 调用 LLM Gateway，校验结构化输出。
- 生成 AgentArtifact 和 ActionSuggestion 草稿。
- 记录 AgentRun、prompt version、token usage、cost estimate 和 evidence_refs。
- 维护 eval、replay、fixture 和 regression snapshot。

本仓库不负责：

- 用户、团队、权限和 GitHub App installation。
- GitHub webhook 接收和 canonical GitHub 数据落库。
- RiskSignal / RiskAssessment 的最终事实状态。
- 用户确认后的 GitHub 写入。
- 面向用户的 Web UI。

## 当前目录结构

```text
.
├── .env.example
├── .github/
│   └── workflows/
│       └── deploy.yml
├── .gitignore
├── AGENTS.md
├── deploy/
│   └── dev-time-agent.service
├── src/
│   └── dev_time_agent/
│       ├── __init__.py
│       ├── app.py
│       ├── buildinfo.py
│       ├── client.py
│       ├── context.py
│       ├── conversation.py
│       ├── conversation_llm.py
│       ├── fallback_graph_nodes.py
│       ├── graph_state.py
│       ├── graph_runtime.py
│       ├── llm_graph_nodes.py
│       ├── llm.py
│       ├── memory.py
│       ├── runner.py
│       ├── schemas.py
│       ├── tools.py
│       ├── worker.py
│       └── workflows/
│           ├── __init__.py
│           ├── pr_doctor.py
│           └── risk_scout.py
├── tests/
│   ├── test_buildinfo.py
│   ├── test_app.py
│   ├── test_agent_eval_fixtures.py
│   ├── test_agent_llm_loop.py
│   ├── test_conversation_runtime.py
│   ├── test_evidence_bundle_schema.py
│   ├── test_llm_worker.py
│   ├── test_memory.py
│   ├── test_pr_doctor.py
│   ├── test_risk_scout.py
│   ├── test_runner.py
│   ├── test_server_client.py
│   ├── test_tool_layer.py
│   └── test_worker.py
├── pyproject.toml
├── uv.lock
└── .claude/
    ├── README.md
    ├── product-prd.md
    ├── technical-architecture.md
    ├── dev-time-agent-architecture.md
    ├── github-capability-layer.md
    ├── project-architecture.md
    ├── skill-authoring.md
    ├── bug-fix-log.md
    ├── git-collaboration.md
    ├── tech-stack.md
    └── coding-standards.md
```

## 目录职责

### `AGENTS.md`

Agent 入口文件。用于说明项目目标、协作原则和关键文档索引。任何 Agent 开始工作前都应先阅读该文件。

### `.claude/`

项目长期上下文目录。这里保存架构、规范、协作流程和故障记录，避免重要信息散落在对话或临时笔记中。

### `.github/workflows/deploy.yml`

Agent Runtime 生产 CI/CD workflow。Push 到 `main` 或手动触发时，先运行 `uv sync --frozen`、`ruff` 和 `pytest`；验证通过后通过 GitHub Actions Secrets 中的 SSH 凭证上传源码包到服务器，执行 `uv sync --frozen --no-dev` 并重启 `dev-time-agent`。

### `deploy/`

生产部署配置目录。`dev-time-agent.service` 定义 systemd 运行方式，Agent 仅监听 `127.0.0.1:8001`，通过 `DEV_TIME_SERVER_INTERNAL_BASE_URL=http://127.0.0.1:8080` 调用后端 internal API。

### `.claude/dev-time-agent-architecture.md`

Agent Runtime 服务设计草案。定义 AgentJob、EvidenceBundle、AgentArtifact、首批 workflows、通信方式和安全边界。

### `.claude/tech-stack.md`

Agent Runtime 技术栈、工具链、脚本、依赖、安全和验证规范。当前定稿为 Python + uv + Pydantic。

### `.claude/coding-standards.md`

Agent Runtime 编码规范、workflow 边界、Python / Pydantic 约束、行数约束和评审检查项。

### `src/dev_time_agent/`

Agent Runtime Python 包。当前包含 FastAPI runtime、LangGraph conversation graph、LLM 主导的 plan/tool/generate/verify 对话回路、session memory store、LLM adapter、AgentJob / AgentArtifact / EvidenceBundle / ActionSuggestion schema、Server internal HTTP client、AgentJob worker、deterministic Risk Scout workflow 和 PR Doctor workflow。worker 会 claim AgentJob、拉取 EvidenceBundle、按 agent_type 路由 workflow，并将 AgentArtifact / ActionSuggestion 回写 server；对话 runtime 通过 EvidenceBundle、只读工具和 session memory 支持围绕风险上下文的多轮追问。

对话 graph 已拆分为：

- `graph_runtime.py`：运行时依赖配置、LangGraph 装配、session memory 持久化。
- `llm_graph_nodes.py`：LLM planner、工具执行、回复生成、回复审核和审批门。
- `fallback_graph_nodes.py`：未配置 LLM 时的兼容 fallback。
- `conversation_llm.py`：OpenAI-compatible 三段式结构化对话 LLM adapter。
- `graph_state.py`：graph state 和 conversation LLM 协议。

对话 runtime 的公开响应包含两类过程数据：

- `trace_events`：兼容旧前端和 server trace 事件。
- `reasoning_trace`：面向 UI 的可审计思考过程，只包含 stage、title、summary、confidence、evidence_refs 和 tool_call 摘要；写操作门禁必须包含 `approval` 步骤；不得返回模型原始 chain-of-thought、prompt、密钥或完整私有上下文。

### `src/dev_time_agent/tools.py`

Tool Layer 边界。当前提供 `risk_evidence.read`、`project_status.read`、`ci_checks.read`、`pull_request.read`、`github.auth.status`、`github.repos.list`、`github.pull_requests.list`、`github.issues.list`、`github.checks.list` 和 `action_suggestion.create`。读工具通过 `dev-time-server` internal API 根据 `risk_assessment_id`、GitHub 授权状态或 repository_id 获取事实；`action_suggestion.create` 只创建待确认草稿，不执行 GitHub 写入。所有工具调用结果必须记录到 `tool_calls` 和 trace。工具层不得绕过 `dev-time-server` 的事实源和权限边界，不得接触 GitHub token。

GitHub 工具约束：

- `github.auth.status`：确认 server 当前是否拥有 GitHub 授权/导入仓库上下文。
- `github.repos.list`：列出 server 允许 agent 读取的 GitHub 仓库和 project 映射。
- `github.pull_requests.list`：按 repository_id 列出 server 已同步的 PR。
- `github.issues.list`：按 repository_id 列出 server 已同步的 Issue。
- `github.checks.list`：按 repository_id 列出 server 已同步的 CI/Checks。
- 用户询问 GitHub 项目、仓库、PR、Issue 或 CI 可见性时，LLM planner 误判为普通对话也必须被编排层纠正为 GitHub 工具调用。
- Python agent 只能看到工具结果，不能读取、保存或打印 GitHub token。

### `src/dev_time_agent/memory.py`

Session memory 存储边界。默认使用进程内 in-memory store；设置 `DEV_TIME_AGENT_SESSION_MEMORY_DB_PATH` 后使用 SQLite JSON store 持久化每个 session 的风险摘要、证据引用和上一轮意图。该模块只保存 Agent 推理所需的短期上下文，不保存 canonical 项目状态；事实源仍归 `dev-time-server`。

### `tests/`

Agent Runtime 测试目录。测试通过公开包接口验证行为，避免绑定内部实现。

### `.agents/skills/`

可选的项目级 Agent Skills 目录。只有在项目明确需要可复用 Agent 工作流时才创建。新增 skill 时，应同步说明触发条件、输入输出、验证方式和安全边界。

## 架构原则

- 让目录结构表达职责边界。
- 优先遵循项目已有模式，不为了新功能随意引入新风格。
- 共享逻辑需要有清晰调用边界和验证方式。
- 外部服务、账号、密钥、网络访问和数据写入必须明确安全边界。
- 项目级 skills 应保持触发条件明确，避免把泛用提示词或个人偏好写成长期能力。
- Agent 只生成可追溯的结构化结论和行动草稿，不直接写入 GitHub。
- 所有 Agent 输出必须引用 evidence_refs，便于前端展示证据链。
- prompt、模型和输出结构变更必须可 replay、可 eval、可回归比较。
- 架构变更必须同步更新本文件。

## 架构变更记录

| 日期 | 变更 | 原因 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 初始化 Agent 项目文档 | 建立项目长期上下文和协作基线 | 已创建 `AGENTS.md` 与 `.claude` 文档 |
| 2026-06-11 | 同步 Dev Time 三服务架构和 Agent Runtime 草案 | 明确 `dev-time-agent` 作为独立 Agent 服务的边界 | 已同步 `product-prd.md`、`technical-architecture.md` 与 `dev-time-agent-architecture.md` |
| 2026-06-16 | 增加 Agent GitHub Actions 生产部署 workflow | 1.0 需要通过 CI/CD 验证并发布 Agent Runtime 到服务器 systemd | `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/deploy.yml")'` |
| 2026-06-11 | 初始化 Python Agent 工程骨架 | 建立 M0 可验证 Agent Runtime 基础 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 AgentJob worker 骨架 | 建立 M8 AgentJob 消费和 AgentArtifact 回写切片 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 EvidenceBundle schema | Agent 可校验 server internal evidence bundle payload | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 Risk Scout workflow | EvidenceBundle 可生成带 evidence_refs 的 AgentArtifact | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 PR Doctor workflow | PR/CI 证据可生成 PR comment ActionSuggestion 草稿 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 接入 Server internal HTTP client 和 workflow 路由 | Agent worker 可 claim、获取 EvidenceBundle、运行 Risk Scout / PR Doctor 并回写结果 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 接入 OpenAI-compatible LLM 调用 | Agent worker 可从 server internal API 获取 active OpenAI/DeepSeek 配置，并用结构化 JSON 输出生成 AgentArtifact | `uv run ruff check . && uv run pytest` |
| 2026-06-12 | 增加 LangGraph 会话 runtime 与可持久化 session memory | Agent 对话需要支持围绕同一风险上下文的多轮追问，服务重载后仍可继续使用上一轮风险摘要 | `uv run ruff check . && uv run pytest -q` |
| 2026-06-13 | 增加 Tool Layer 首个只读工具 | Agent Runtime 可在缺少请求内 EvidenceBundle 时自行调用 `risk_evidence.read` 获取证据，并返回 `tool_calls` 追踪 | `uv run ruff check . && uv run pytest -q` |
| 2026-06-13 | 会话 Agent 接入 LLM 主导回路和审批门 | 解决关键词路由导致答非所问、未真实调用配置 LLM、写操作缺少确认边界的问题 | `uv run ruff check . && uv run pytest -q` |
| 2026-06-13 | 增加可展示 reasoning_trace | 前端需要默认折叠、手动展开的可审计思考过程，而不是暴露原始模型推理 | `uv run ruff check . && uv run pytest -q` |
| 2026-06-13 | 增加 GitHub 只读工具入口 | Agent 需要在用户询问 GitHub 项目可见性时先检查授权并读取仓库列表，而不是凭空说明能力 | `uv run pytest tests/test_agent_llm_loop.py -q` |
| 2026-06-15 | 扩展 GitHub 对象级只读能力 | Agent 需要能查询授权仓库的 repo、PR、Issue、Checks，而不是把 GitHub 查询误判为风险澄清 | `uv run pytest tests/test_tool_layer.py -q` |
# 2026-07 Runtime deepening

`RiskEpisodeConversationRuntime` 是新的深 Module：公共 Interface 只接收会话消息和 `TrustedRiskContext`，内部隐藏确定性路由、workspace model Adapter、GitHub capability execution 与 Grounded Turn 验证。Server 与 Runtime 之间的 Seam 由 Pydantic/JSON schema 固定；不再让 PageContext、server classifier 和 LLM planner 三处重复决定同一仓库。

## Conversation Runtime failure isolation

会话调用链为 `context_assembler -> conversation_control_plane -> (intent_router | model_resolver)`。`model_resolver` 是 Workspace 模型 Adapter 的唯一按需入口；确定性路径不得跨越该 Seam。`RiskEpisodeConversationRuntime.run()` 是外部依赖错误的收敛 Interface：网络、上游 HTTP、超时、JSON 或上游 schema 错误转换为结构化 `runtime_dependency_unavailable`，而非 FastAPI 500。
