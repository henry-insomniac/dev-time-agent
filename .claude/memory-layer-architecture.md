# 记忆层架构

## 定位

`dev-time-agent` 的记忆层是 session-level short-term memory。它负责对话连续性，不负责保存 canonical 项目事实。

核心原则：

```text
Memory 负责对话连续性、用户偏好和历史召回。
EvidenceBundle 负责事实判断。
Memory 不能绕过 EvidenceBundle 成为项目事实源。
```

## 当前实现

当前 memory store 有两种实现：

```text
InMemorySessionMemoryStore
SQLiteSessionMemoryStore
```

默认使用 in-memory store。设置 `DEV_TIME_AGENT_SESSION_MEMORY_DB_PATH` 后使用 SQLite store，支持 runtime 重启后恢复 session memory。

当前 `graph_runtime` 在每轮请求开始时读取 memory：

```text
run_agent_session_turn
-> _SESSION_MEMORY_STORE.get(session_id)
-> context_assembler / fallback router / planner 使用 session_memory
```

每轮回答完成后写入 memory：

```text
persist_session_memory
-> 更新 last_intent
-> 如果有证据，更新 fact snapshot
-> 追加 recent_turns
-> _SESSION_MEMORY_STORE.put(session_id, memory)
```

## 当前记忆结构

当前 memory 包含两类数据。

### Conversation Memory

用于多轮追问和上一轮回复改写。

```json
{
  "recent_turns": [
    {
      "intent": "action_plan",
      "user_summary": "给我下一步行动计划",
      "agent_summary": "行动计划：先确认阻塞证据，再定位失败检查，随后修复并重新运行测试。",
      "evidence_refs": ["event_check-run-1"],
      "project_id": "project_repo_1001",
      "risk_assessment_id": "risk_project_repo_1001"
    }
  ]
}
```

`recent_turns` 当前保留最近 5 轮摘要。它支持：

- “下一步呢”。
- “然后呢”。
- “把刚才的建议改短”。
- “把上一轮回复改写得更委婉”。

### Fact Snapshot Memory

用于保存上一轮带证据的风险摘要，但只能在 freshness 校验通过后使用。

```json
{
  "fact_project_id": "project_repo_1001",
  "fact_risk_assessment_id": "risk_project_repo_1001",
  "last_evidence_refs": ["event_check-run-1"],
  "last_project_name": "dev-time",
  "last_risk_score": 70,
  "last_risk_level": "high",
  "last_risk_reason": "test failed and is blocking progress."
}
```

只有当当前 `project_id` 和 `risk_assessment_id` 与 fact snapshot 一致时，fallback router 才允许使用这部分事实 memory。否则 memory 只能作为对话线索，不能作为当前风险事实依据。

## 当前已落地行为

### 短追问接续

第一轮：

```text
为什么这是高风险？
```

Agent 读取 EvidenceBundle 并保存风险摘要。

第二轮：

```text
下一步呢？
```

如果 `risk_assessment_id` 一致，Agent 可以使用 session memory 继续生成行动计划。

### 上一轮回复改写

第一轮：

```text
给我下一步行动计划
```

第二轮：

```text
把刚才的建议改短
```

Agent 通过 `recent_turns` 找到上一轮回答，生成简短版，并保留上一轮 evidence_refs。

### Stale memory 拒绝

如果同一个 session 切换到新的 `risk_assessment_id`，且请求没有携带新的 EvidenceBundle，也没有工具可读取新证据，Agent 不能使用旧 `last_risk_reason` 回答当前风险问题。

正确行为：

```text
用户：下一步呢？
Agent：你想让我评估当前风险、解释证据，还是生成下一步行动计划？
```

## 设计取舍

### 为什么不直接做长期记忆

Dev Time 的事实源是 GitHub 和 `dev-time-server` 的 EvidenceBundle。风险状态高度时效化，旧 memory 如果被当成事实源，会导致：

- 使用过期风险原因。
- 引用已经不存在或状态变化的 evidence_refs。
- 绕过 server 权限和新鲜度检查。
- 让用户误以为 Agent 看到的是当前 GitHub 状态。

因此当前只做 session short-term memory，不做无约束 long-term memory。

### 为什么不用向量库

当前最核心的问题是短追问和上下文连续性，不是大规模语义召回。直接引入向量库会增加依赖、成本和事实新鲜度风险。后续做 historical risk search 或跨 session 决策召回时，再考虑 FTS 或 embedding。

## 后续规划

### 1. 明确 Memory Schema

将当前 dict memory 升级为 Pydantic schema：

```text
ConversationMemory
TurnSummary
FactSnapshotMemory
FocusRef
```

目标：

- 限制 memory shape 漂移。
- 明确 conversation memory 和 fact snapshot memory 边界。
- 为 future migration 和 eval 提供稳定协议。

### 2. TTL 与 freshness metadata

为 fact snapshot 增加：

```text
captured_at
stale_after_seconds
evidence_bundle_version
```

使用前检查：

```text
project_id 是否一致
risk_assessment_id 是否一致
memory 是否超过 TTL
EvidenceBundle 是否 stale
evidence_refs 是否仍存在
```

### 3. Memory Policy

抽出统一策略层：

```text
MemoryPolicy.should_use_fact_memory(...)
MemoryPolicy.should_use_turn_memory(...)
MemoryPolicy.should_refresh_evidence(...)
MemoryPolicy.should_persist_turn(...)
MemoryPolicy.redact_sensitive_fields(...)
```

目标是避免 graph node 各自决定 memory 读写规则。

### 4. Preference Memory

后续增加受控用户偏好 memory，但由 `dev-time-server` 管归属、权限和持久化，agent 只读取：

```json
{
  "answer_style": "concise",
  "draft_tone": "direct_but_polite",
  "preferred_actions": ["fix_ci_first"],
  "auto_draft_enabled": false
}
```

偏好不能覆盖安全规则。即使用户偏好自动生成草稿，写操作仍必须进入 approval gate。

### 5. Conversation Search

当历史会话增多后，引入按需检索：

```text
agent_conversation_turns
-> FTS / semantic search
-> 按 project_id、risk_assessment_id、user/team scope 过滤
-> 只注入 top-k 摘要
```

适用问题：

- “上次这个风险怎么处理的？”
- “之前有没有类似 CI 失败？”
- “我上次为什么拒绝这个建议？”

### 6. Memory Eval

需要建立专门的 memory eval：

- 短追问是否能接上上一轮。
- 上一轮回复改写是否能使用 recent_turns。
- runtime 重启后是否恢复 memory。
- risk_assessment 变化后是否拒绝旧事实。
- 跨 project / cross-session 是否隔离。
- 用户要求忘记时是否清除当前 session memory。

## 当前验证

当前已通过集成测试覆盖：

- 同 session “下一步呢”能接上上一轮风险上下文。
- “把刚才的建议改短”能读取 recent turn summary。
- SQLite store 重启后仍能恢复 recent turn summary。
- 新 risk assessment 下不会复用旧风险事实。

## 面试描述口径

可以这样描述：

```text
我的 memory 不是长期知识库，而是 session short-term memory。它分 conversation memory 和 fact snapshot memory：前者支持多轮追问和上一轮回复改写，后者保存上一轮风险摘要但必须绑定 project_id、risk_assessment_id 和 evidence_refs。风险事实一旦切换 assessment 或缺少新证据，就不能从 memory 里直接回答，必须回到 EvidenceBundle 或进入澄清。
```
