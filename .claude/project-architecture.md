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

请在项目初始化后补充真实目录结构。

```text
.
├── .gitignore
├── AGENTS.md
└── .claude/
    ├── README.md
    ├── product-prd.md
    ├── technical-architecture.md
    ├── dev-time-agent-architecture.md
    ├── project-architecture.md
    ├── skill-authoring.md
    ├── bug-fix-log.md
    ├── git-collaboration.md
    └── tech-stack.md
```

## 目录职责

### `AGENTS.md`

Agent 入口文件。用于说明项目目标、协作原则和关键文档索引。任何 Agent 开始工作前都应先阅读该文件。

### `.claude/`

项目长期上下文目录。这里保存架构、规范、协作流程和故障记录，避免重要信息散落在对话或临时笔记中。

### `.claude/dev-time-agent-architecture.md`

Agent Runtime 服务设计草案。定义 AgentJob、EvidenceBundle、AgentArtifact、首批 workflows、通信方式和安全边界。

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
