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
├── .gitignore
├── AGENTS.md
├── src/
│   └── dev_time_agent/
│       ├── __init__.py
│       ├── app.py
│       ├── buildinfo.py
│       ├── client.py
│       ├── conversation.py
│       ├── graph_runtime.py
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

### `.claude/dev-time-agent-architecture.md`

Agent Runtime 服务设计草案。定义 AgentJob、EvidenceBundle、AgentArtifact、首批 workflows、通信方式和安全边界。

### `.claude/tech-stack.md`

Agent Runtime 技术栈、工具链、脚本、依赖、安全和验证规范。当前定稿为 Python + uv + Pydantic。

### `.claude/coding-standards.md`

Agent Runtime 编码规范、workflow 边界、Python / Pydantic 约束、行数约束和评审检查项。

### `src/dev_time_agent/`

Agent Runtime Python 包。当前包含 FastAPI runtime、LangGraph conversation graph、session memory store、LLM adapter、AgentJob / AgentArtifact / EvidenceBundle / ActionSuggestion schema、Server internal HTTP client、AgentJob worker、deterministic Risk Scout workflow 和 PR Doctor workflow。worker 会 claim AgentJob、拉取 EvidenceBundle、按 agent_type 路由 workflow，并将 AgentArtifact / ActionSuggestion 回写 server；对话 runtime 通过 EvidenceBundle 和 session memory 支持围绕风险上下文的多轮追问。

### `src/dev_time_agent/tools.py`

Tool Layer 边界。当前提供 `risk_evidence.read` 只读工具，通过 `dev-time-server` internal API 根据 `risk_assessment_id` 获取 EvidenceBundle，并把工具调用结果记录到 `tool_calls` 和 trace。工具层不得直接写 GitHub，不得绕过 `dev-time-server` 的事实源和权限边界。

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
| 2026-06-11 | 初始化 Python Agent 工程骨架 | 建立 M0 可验证 Agent Runtime 基础 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 AgentJob worker 骨架 | 建立 M8 AgentJob 消费和 AgentArtifact 回写切片 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 EvidenceBundle schema | Agent 可校验 server internal evidence bundle payload | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 Risk Scout workflow | EvidenceBundle 可生成带 evidence_refs 的 AgentArtifact | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 增加 PR Doctor workflow | PR/CI 证据可生成 PR comment ActionSuggestion 草稿 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 接入 Server internal HTTP client 和 workflow 路由 | Agent worker 可 claim、获取 EvidenceBundle、运行 Risk Scout / PR Doctor 并回写结果 | `uv run ruff check . && uv run pytest` |
| 2026-06-11 | 接入 OpenAI-compatible LLM 调用 | Agent worker 可从 server internal API 获取 active OpenAI/DeepSeek 配置，并用结构化 JSON 输出生成 AgentArtifact | `uv run ruff check . && uv run pytest` |
| 2026-06-12 | 增加 LangGraph 会话 runtime 与可持久化 session memory | Agent 对话需要支持围绕同一风险上下文的多轮追问，服务重载后仍可继续使用上一轮风险摘要 | `uv run ruff check . && uv run pytest -q` |
| 2026-06-13 | 增加 Tool Layer 首个只读工具 | Agent Runtime 可在缺少请求内 EvidenceBundle 时自行调用 `risk_evidence.read` 获取证据，并返回 `tool_calls` 追踪 | `uv run ruff check . && uv run pytest -q` |
