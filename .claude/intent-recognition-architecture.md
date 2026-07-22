# 意图识别层架构

## 定位

`dev-time-agent` 的意图识别层不是独立的文本分类器，而是会话 Agent 的规划入口。它负责判断用户当前问题属于哪类项目风险请求，并决定后续是否需要读取证据、调用工具、生成行动草稿或进入用户确认门。

一句话定义：

```text
意图识别层把用户自然语言请求转成可执行的 AgentPlan，作为 conversation graph 的路由和安全决策输入。
```

## 解决的问题

Agent 对话不能直接走 `user message -> LLM answer`，否则容易出现以下问题：

- 普通问题被强行解释成当前风险。
- 风险问题没有读取证据就直接生成结论。
- 用户要求写操作时绕过确认边界。
- 模型回答看似合理，但没有 evidence_refs，无法追溯。
- prompt 或模型变化后，意图路由质量无法回归验证。

因此意图识别层要同时回答四个问题：

```text
用户想问什么？
回答是否需要当前风险证据？
需要调用哪些受控工具？
是否涉及写操作和用户确认？
```

## 当前架构

当前采用双路径设计：

```text
生产路径：LLM planner + structured AgentPlan
降级路径：deterministic keyword fallback + session memory
```

### 生产路径

生产路径由 conversation graph 驱动：

```text
context_assembler
-> llm_planner
-> llm_tool_executor
-> response_generator
-> response_verifier
-> approval_gate
```

`context_assembler` 先组装 `agent_context`，包含：

- agent identity。
- capabilities。
- boundaries。
- user_message。
- project_id。
- risk_assessment_id。
- session_memory。
- available_tools。
- tool_results。
- evidence_summary。

`llm_planner` 使用 OpenAI-compatible LLM 对 `agent_context` 做结构化规划，输出 `AgentPlan`：

```text
intent
confidence
needs_evidence
needs_tools
tool_names
answer_strategy
reasoning_summary
safety_notes
```

这里的意图识别不是只给一个分类标签，而是同时给出执行策略。比如用户问“为什么这是高风险？”，planner 应输出类似：

```json
{
  "intent": "risk_explain",
  "confidence": 0.94,
  "needs_evidence": true,
  "needs_tools": true,
  "tool_names": ["risk_evidence.read"],
  "answer_strategy": "explain_risk_with_evidence",
  "reasoning_summary": "用户要求解释高风险，需要读取风险证据。",
  "safety_notes": []
}
```

下游根据 `needs_evidence` 和 `tool_names` 决定是否进入 `llm_tool_executor`。如果 planner 判断需要取证，但没有指定工具，系统默认补充 `risk_evidence.read`。

### 降级路径

未配置 LLM 时，系统使用 deterministic fallback。fallback 通过关键词和短期记忆完成基础路由：

| 用户表达 | 意图 |
| --- | --- |
| `你好`、`hi`、`hello` | `smalltalk` |
| `你是谁`、`你能做什么`、`介绍你自己` | `self_intro` |
| `当前状态`、`项目状态`、`现在怎么样` | `project_status` |
| `查看我的 GitHub 项目`、`有哪些仓库` | `github_repository_list` |
| `查看 dev-time-agent 的 PR` | `github_pull_requests_list` |
| `查看 dev-time-agent 的 issue` | `github_issues_list` |
| `查看 dev-time-agent 的 CI`、`查看 Checks` | `github_checks_list` |
| `风险`、`为什么`、`阻塞`、`测试`、`ci`、`pr` | `risk_explain` |
| `行动`、`计划`、`下一步`、`怎么做` | `action_plan` |
| 无法判断 | `clarify` |

fallback 还会使用 session memory 处理短追问。例如上一轮已解释风险，memory 中存在 `last_risk_reason` 或 `last_evidence_refs`，用户下一轮只问“下一步呢”，系统会识别为 `action_plan`。

## 当前意图集合

当前主要支持以下意图：

| Intent | 说明 | 是否通常需要证据 |
| --- | --- | --- |
| `smalltalk` | 普通问候 | 否 |
| `self_intro` | 询问 Agent 是谁、能做什么 | 否 |
| `capability_explain` | 询问如何测试或使用 Agent 能力 | 否 |
| `github_repository_list` | 查询当前授权给 Dev Time 的 GitHub 仓库 | 否，通常需要 GitHub 工具 |
| `github_pull_requests_list` | 查询指定仓库的 Pull Requests | 否，通常需要 GitHub 工具 |
| `github_issues_list` | 查询指定仓库的 Issues | 否，通常需要 GitHub 工具 |
| `github_checks_list` | 查询指定仓库的 CI / Checks | 否，通常需要 GitHub 工具 |
| `project_status` | 查询当前项目状态、风险分、主要阻塞 | 是 |
| `risk_explain` | 解释风险原因、证据、影响 | 是 |
| `action_plan` | 生成下一步处理建议 | 是 |
| `clarify` | 问题过于模糊，需要追问 | 否 |

## 与工具层的关系

意图识别层不直接读取 GitHub，也不直接操作业务数据库。它只能通过 planner 决定是否调用 Tool Layer。

当前可用工具包括：

```text
risk_evidence.read
project_status.read
ci_checks.read
pull_request.read
github.auth.status
github.repos.list
github.pull_requests.list
github.issues.list
github.checks.list
action_suggestion.create
```

读工具通过 `dev-time-server` internal API 获取受控事实。写相关工具只能创建 `ActionSuggestion` 草稿，不能执行 GitHub 写入。

## 与安全边界的关系

意图识别层是安全边界的第一道门：

- 普通对话和能力说明不应强行加载风险证据。
- 风险解释必须基于 EvidenceBundle 或只读工具结果。
- 行动计划必须返回 evidence_refs。
- 写操作必须转成 `approval_request` 或待确认 `ActionSuggestion`。
- 不确定时进入 `clarify`，不要编造用户意图。

后续 `response_verifier` 是第二道门，负责审核回答是否答非所问、是否编造证据、是否绕过写操作确认。

## 当前缺陷

### 意图粒度偏粗

当前意图主要覆盖一级场景，真实用户问题会更细：

- 证据可靠吗？
- 这个风险会影响多久？
- 这是误报吗？
- 帮我生成 PR 评论。
- 只看 CI，不看 PR。
- 重新分析一次。

这些问题目前容易被压到 `risk_explain` 或 `action_plan`，导致后续策略不够精确。

### fallback 泛化能力有限

关键词规则只能覆盖显式表达。比如“卡在哪里了”“这事严重吗”“今天必须处理吗”“红色是什么意思”都可能需要风险证据，但 fallback 可能识别为 `clarify`。

### LLM planner 输出仍需更强约束

当前已经使用 Pydantic 校验结构，但 intent 字段仍需要更严格的 enum 归一化。否则模型可能输出语义相近但名称不同的 intent，影响下游路由。

### 多意图处理不完整

用户可能一句话包含多个目标：

```text
为什么这个 PR 高风险？顺便帮我写个评论。
```

这应拆成取证、解释风险、生成 PR comment 草稿、进入确认门四步。当前结构更偏单一 intent，复杂请求主要依赖模型在 `suggested_actions` 中补充动作，执行计划不够显式。

### 与状态和权限融合不够深

比如“帮我处理掉”可能是行动建议，也可能是写操作请求。系统应该结合 `allowed_actions`、证据新鲜度、已有 ActionSuggestion 状态和权限上下文共同判断，而不是只依赖文本和 planner 判断。

### 缺少专门的 intent eval

当前测试覆盖了典型路径、工具调用、答非所问审核和短追问，但还缺少专门面向意图识别的评估集。prompt、模型或工具列表变化后，缺少稳定的 intent regression gate。

## 未来规划

### 1. 严格 Intent Schema

将 planner 输出升级为严格枚举和更完整的结构化协议：

```json
{
  "primary_intent": "risk_explain",
  "secondary_intents": ["action_draft"],
  "confidence": 0.88,
  "needs_evidence": true,
  "needs_tools": true,
  "tool_names": ["risk_evidence.read", "pull_request.read"],
  "requires_approval": true,
  "missing_context": []
}
```

目标：

- 固定 intent 枚举，避免模型输出漂移。
- 分离 primary intent 和 secondary intents。
- 显式标记 `requires_approval`。
- 显式返回缺失上下文，支持更准确的 `clarify`。

### 2. Multi-step Plan

把复杂请求从单一 intent 升级为多步骤计划：

```json
{
  "steps": [
    {
      "type": "read_evidence",
      "tool": "risk_evidence.read"
    },
    {
      "type": "explain_risk",
      "depends_on": ["read_evidence"]
    },
    {
      "type": "draft_action",
      "action_type": "pr_comment",
      "requires_approval": true
    }
  ]
}
```

目标：

- 支持一轮请求中的多个目标。
- 明确工具调用顺序和依赖关系。
- 把行动草稿生成从回答生成中拆出来。
- 让 approval gate 基于计划步骤触发，而不是只依赖最终 draft。

### 3. Intent Eval

建立专门的意图识别评估集，覆盖真实中文表达、短追问、多意图、越权请求和证据不足请求。

示例：

```json
{
  "input": "卡在哪里了？",
  "expected_intent": "risk_explain",
  "expected_needs_evidence": true,
  "expected_tools": ["risk_evidence.read"]
}
```

```json
{
  "input": "下一步呢？",
  "memory": {
    "last_intent": "risk_explain",
    "last_evidence_refs": ["event_check-run-1"]
  },
  "expected_intent": "action_plan",
  "expected_needs_evidence": true
}
```

目标：

- prompt 修改后可回归验证。
- 模型切换后可比较行为差异。
- 工具列表变化后可检查路由是否退化。
- 防止把“证据是什么”误判为“行动计划”，或把“帮我发评论”误判为普通问答。

### 4. 与权限和状态上下文融合

后续 planner 输入应纳入更多状态：

- EvidenceBundle 是否 stale。
- allowed_actions。
- 当前项目是否已存在 pending ActionSuggestion。
- 用户是否请求重新分析。
- 当前工具是否可用。
- GitHub 权限是否失效。

目标是让意图识别不只是文本理解，而是面向产品状态的 Agent policy decision。

### 5. 可观测指标

为意图识别层补充质量指标：

- intent accuracy。
- tool selection accuracy。
- clarify rate。
- unnecessary evidence load rate。
- missed approval rate。
- multi-intent completion rate。
- verifier rejection rate by intent。

这些指标应进入 `agent-quality-metrics.md`，用于后续发布门禁。

## 面试描述口径

可以这样描述：

```text
我把意图识别设计成 Agent 的规划层，而不是简单分类器。生产路径使用 LLM planner 输出结构化 AgentPlan，决定 intent、是否需要证据、是否调用工具和是否涉及审批；没有 LLM 时使用关键词和 session memory 做 deterministic fallback。这样既能支持复杂自然语言，又保留本地可测的降级路径。
```

如果被问到是不是主流方案：

```text
底层思路是主流 Agent 工程范式，包括 planner、tool selection、structured output、guardrail 和 human-in-the-loop。我的工作是把它落到 GitHub 项目风险分析场景：用 EvidenceBundle 限定事实边界，用 Tool Layer 限定能力边界，用 Pydantic schema 限定输出边界，用 verifier 和 approval gate 限定安全边界。
```

如果被问到下一步怎么优化：

```text
下一步会把 planner 升级为严格 Intent Schema，支持 multi-step plan，并建设 intent eval 数据集。这样意图识别就不是靠 prompt 感觉，而是有协议、有执行计划、有回归测试。
```
# 2026-07 确定性意图边界

`current_context`、`self_intro` 以及带 Trusted Risk Context 的 Issue/PR/Checks 查询在 LLM planner 之前路由。这些意图的答案由可信上下文或工具结果唯一决定，模型没有额外判断价值。

PR CI 诊断只有在消息 PR 编号与 Risk Episode 的 `pull_request` 一致时才读取 `check_run_id`；不一致时必须澄清。无 Risk Episode 的旧路径仅作为未配置 Runtime 的兼容 Adapter。
# 2026-07-22 Deterministic Conversation Control Plane

意图识别不再等同于“调用模型”。Runtime 先通过 `decide_conversation_execution(message, has_trusted_context)` 决定执行路径，再按需跨越模型 Adapter Seam。当前项目身份采用组合语义谓词（上下文锚点 + 项目主体 + 身份问法），而不是完整句子白名单，因此“当前项目是什么”“当前的项目是什么”“这个仓库叫什么”等表达共享同一规则。状态、风险、进度类问题显式排除，避免被身份问题吞掉。

控制平面只负责选择 direct/model，不生成业务答案；事实回答仍由 responder 和 Trusted Risk Context 负责。这样保持路由、事实与文案的 Locality，并允许模型不可用时继续回答确定性问题。
