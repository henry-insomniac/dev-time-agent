# dev-time-agent 架构草案

## 定位

`dev-time-agent` 是 Dev Time 的 Agent Runtime 服务，不是聊天服务，也不是独立产品。它负责从 GitHub 事实和风险信号中构建证据包，运行 Agent 工作流，输出可解释结论和行动草稿。

三服务边界：

```text
dev-time          前端 Web App：风险工作台、Agent 建议展示、用户确认交互
dev-time-server   核心业务后端：事实源、权限、GitHub 集成、风险状态、确认后的写入
dev-time-agent    Agent Runtime：上下文构建、工作流编排、LLM 调用、评估和行动草稿
```

核心原则：server 管事实和权限，agent 管推理和建议。

## 为什么需要独立服务

Agent 是 Dev Time 的核心能力，不只是后端里的一个 LLM helper。真正落地后，Agent 需要：

- 后台持续运行，而不是用户点击后才临时总结。
- 构建复杂上下文：GitHub 事件、历史风险、项目节奏、用户偏好、团队行为。
- 调用受控工具：读取 PR、CI、milestone、历史风险和行动草稿。
- 输出结构化结果，并引用证据。
- 管理 prompt 版本、模型路由、token 成本和失败重试。
- 建立 eval、replay 和 regression snapshot，保证 prompt 变化可评估。

这些能力如果全部放入 `dev-time-server`，会让业务 API、GitHub 同步、风险规则、LLM 调用、Agent 编排和评估体系混在一起，边界会快速失控。

## 目标能力

### Agent Runtime

负责消费 AgentJob，运行对应 workflow，并返回 AgentArtifact。

### Context Builder

负责向 `dev-time-server` 获取受控数据，构建 EvidenceBundle。

### LLM Gateway

负责模型调用、模型路由、结构化输出校验、token 和成本记录。LLM key 的所有权和审计仍归 `dev-time-server`。

MVP 当前通过 `dev-time-server` 的 `GET /internal/llm-provider-config` 读取 active provider，并使用 OpenAI-compatible `/chat/completions` 调用 OpenAI 或 DeepSeek。公开设置 API 不回传明文 key，只有 agent internal 调用能拿到解密后的 provider config。

### Tool Layer

只提供读工具和草稿生成工具，不直接执行 GitHub 写入。

当前已落地工具：

- `risk_evidence.read`：按 `risk_assessment_id` 获取 EvidenceBundle。
- `project_status.read`：读取项目风险分、风险等级、最高风险原因和证据引用。
- `ci_checks.read`：读取当前风险相关 CI/check_run 事实。
- `pull_request.read`：读取当前风险相关 PR 事实。
- `action_suggestion.create`：只创建 `pending_user_confirmation` 行动草稿，不执行 GitHub 写入。

所有工具调用必须写入 `tool_calls`，并在 trace / reasoning_trace 中记录工具执行节点，便于前端和 eval 系统审计。

### Contextual Conversation

负责在当前风险上下文中回答用户追问。它不是泛用聊天能力，只能围绕当前 EvidenceBundle、AgentArtifact、ActionSuggestion 和 allowed actions 解释风险、验证证据、说明影响或生成行动草稿。

会话记忆只保存对话连续性所需的短期摘要，不替代 `dev-time-server` 的事实源。当前 memory 分为 conversation memory 和 fact snapshot memory：conversation memory 通过 `recent_turns` 保存最近几轮用户问题、Agent 回复摘要和 evidence_refs，用于处理“下一步呢”“把刚才的建议改短”这类追问；fact snapshot memory 保存上一轮带证据的风险摘要，但必须绑定 `project_id`、`risk_assessment_id` 和 evidence_refs，只有当前上下文匹配时才能作为风险上下文使用。运行时默认使用进程内 memory；设置 `DEV_TIME_AGENT_SESSION_MEMORY_DB_PATH` 后使用 SQLite store 持久化 session memory，服务重启后仍可继续围绕上一轮风险上下文回答。

当前会话 Agent 已从关键词模板路由升级为 LLM 主导的回路：

```text
context_assembler
-> llm_planner
-> llm_tool_executor  # 按计划读取受控证据
-> response_generator
-> response_verifier  # 审核答非所问、证据编造和安全边界
-> approval_gate      # 写操作只返回待确认请求
```

生产路径通过 `DEV_TIME_SERVER_INTERNAL_BASE_URL` 调用 `dev-time-server` 的 `GET /internal/llm-provider-config` 获取 active OpenAI/DeepSeek provider，再使用 OpenAI-compatible `/chat/completions` 完成 `plan_turn`、`generate_response` 和 `verify_response` 三段式结构化 JSON 调用。没有配置 LLM 时保留 deterministic fallback，用于本地降级和旧接口兼容。

关键行为边界：

- 普通对话和能力说明必须围绕用户问题回答，不得强行解释当前风险。
- 风险解释或行动计划必须在需要时调用 `risk_evidence.read`，并返回 evidence_refs。
- LLM 草稿必须经过 verifier；答非所问时使用 verifier 提供的改写。
- LLM 生成写操作草稿时只能返回 `approval_request`，用户确认前不得执行外部写入。
- 每轮对话必须返回 `reasoning_trace`，供前端默认折叠展示可审计思考过程；写操作门禁必须追加 `approval` 步骤；该字段只能包含摘要、阶段、证据和工具调用，不得包含模型原始 chain-of-thought、prompt 或密钥。

### Eval System

负责 fixture、replay、snapshot 和质量回归，保证 Agent 可迭代。

## 首批 Agent

### Risk Scout

发现项目风险变化。

输出：风险等级、风险变化、风险类别、影响说明、证据引用、建议下一步。

### PR Doctor

分析 PR 风险。

能力：判断 PR 是否过大、CI 是否阻塞、review 是否停滞、是否需要拆 PR、生成 reviewer comment 草稿。

### Milestone Planner

分析 milestone 是否现实。

能力：判断剩余工作是否超过剩余时间、识别延期风险、建议砍 scope 或调整优先级。

### Scope Guard

识别范围膨胀。

能力：检测 milestone 内新增 issue、需求描述变化、临时插入项和范围漂移语言。

### Daily Brief

生成每日简报。

输出：今天最该处理的 1-3 件事、风险升高项目、风险降低项目、需要确认的行动草稿。

### Action Drafter

将分析结论转成行动草稿。

输出：issue 草稿、PR comment 草稿、label 建议、milestone 调整建议、reviewer 请求草稿。

## 核心数据契约

### AgentJob

```json
{
  "job_id": "job_123",
  "tenant_id": "team_123",
  "project_id": "project_123",
  "risk_assessment_id": "risk_123",
  "agent_type": "pr_doctor",
  "trigger": "ci_failed",
  "requested_by": "system",
  "created_at": "2026-06-11T00:00:00Z"
}
```

AgentJob 只携带 ID 和触发上下文，不直接携带大量 GitHub 原始数据。

### EvidenceBundle

```text
EvidenceBundle
├── project summary
├── current risk assessment
├── risk signals
├── related GitHub objects
│   ├── issues
│   ├── pull requests
│   ├── CI runs
│   ├── commits
│   └── milestones
├── activity timeline
├── historical risk trend
├── user/team preferences
└── allowed actions
```

### AgentArtifact

```json
{
  "agent_type": "pr_doctor",
  "risk_summary": "CI 失败正在阻塞 PR review",
  "evidence_refs": ["ci_run_421", "pr_18", "milestone_v01"],
  "impact": "可能延迟 1-2 天",
  "next_action": "先修复 CI，再请求 review",
  "action_suggestions": ["draft_789"],
  "confidence": "medium",
  "model": "configured-model",
  "prompt_version": "pr-doctor@v1",
  "token_usage": {
    "input": 0,
    "output": 0
  }
}
```

### ConversationTurn

```json
{
  "conversation_id": "conv_123",
  "turn_id": "turn_123",
  "project_id": "project_123",
  "risk_assessment_id": "risk_123",
  "agent_artifact_id": "artifact_123",
  "role": "agent",
  "message": "CI run #421 是当前硬阻塞，先修 CI 比调整 scope 更有效。",
  "evidence_refs": ["ci_run_421", "pr_18"],
  "action_suggestions": ["draft_789"],
  "model": "configured-model",
  "prompt_version": "conversation@v1"
}
```

ConversationTurn 必须绑定当前风险上下文。证据不足时返回 insufficient_evidence，不允许编造 GitHub 对象或风险原因。

## 服务通信

推荐流程：

```text
dev-time-server
-> 创建 AgentJob
-> 放入 queue
-> dev-time-agent 消费 job
-> dev-time-agent 调用 server internal API 获取 EvidenceBundle
-> dev-time-agent 运行 workflow
-> dev-time-agent 返回 AgentArtifact
-> dev-time-server 保存并展示给前端
```

上下文对话流程：

```text
dev-time
-> 用户在 Agent dock 提问
-> dev-time-server 校验项目权限和 EvidenceBundle 新鲜度
-> dev-time-agent 使用 EvidenceBundle + AgentArtifact + session memory 生成回答
-> 如请求未携带 EvidenceBundle，dev-time-agent 可通过只读工具从 server internal API 拉取证据
-> dev-time-agent 返回 ConversationTurn 和 evidence_refs
-> dev-time-server 保存 turn
-> dev-time 展示回答并高亮证据
```

推荐事件：

```text
risk.assessment.created
risk.assessment.changed
project.synced
pr.blocked
ci.failed
milestone.deadline_near
daily.brief.requested
agent.action.confirmed
```

## 安全边界

- `dev-time-agent` 不直接执行 GitHub 写入。
- `dev-time-agent` 只能生成 ActionSuggestion 草稿。
- `dev-time-agent` 工具层只能通过 `dev-time-server` internal API 读取受控事实，不直接读写 GitHub 或业务数据库。
- 用户确认后，由 `dev-time-server` 校验权限并执行 GitHub 写入。
- LLM provider key 由 `dev-time-server` 加密存储和审计。
- Agent 日志不得记录明文 key、private repo 的非必要完整内容或敏感用户数据。
- 所有 Agent 输出必须引用 evidence_refs，便于前端展示证据链。
- 上下文对话不得绕过 `dev-time-server` 权限校验，也不得读取 EvidenceBundle 之外的 GitHub 数据。

## 目录建议

```text
dev-time-agent/
├── src/
│   ├── workflows/
│   │   ├── risk-scout/
│   │   ├── pr-doctor/
│   │   ├── milestone-planner/
│   │   ├── scope-guard/
│   │   ├── daily-brief/
│   │   └── action-drafter/
│   ├── context/
│   │   ├── evidence-bundle-builder/
│   │   ├── project-context-builder/
│   │   └── memory-loader/
│   ├── tools/
│   │   ├── github-read-tools/
│   │   ├── risk-read-tools/
│   │   └── action-draft-tools/
│   ├── llm/
│   │   ├── provider-router/
│   │   ├── prompt-registry/
│   │   ├── structured-output-validator/
│   │   └── token-cost-tracker/
│   ├── evals/
│   │   ├── fixtures/
│   │   ├── replay-runs/
│   │   ├── regression-snapshots/
│   │   └── judge-rubrics/
│   └── artifacts/
└── AGENTS.md
```

## MVP 阶段建议

阶段 1 只实现骨架和两类 Agent：

- AgentJob consumer。
- EvidenceBundle schema。
- Risk Scout workflow。
- PR Doctor workflow。
- Contextual Conversation workflow。
- ActionSuggestion schema。
- AgentRun log。
- OpenAI-compatible LLM provider adapter。

阶段 2 增加评估：

- fixtures。
- replay runner。
- prompt version。
- output snapshot。
- regression report。

阶段 3 增加自动化：

- daily brief scheduler。
- team preference memory。
- risk trend learning。
- notification priority tuning。

## 暂不做

- 不做泛用聊天助手。
- 不让 Agent 自动写 GitHub。
- 不让 LLM 直接决定最终风险分。
- 不在 Agent 服务中维护 canonical 业务状态。
- 不把 dev-time-agent 做成独立面向用户的产品。
