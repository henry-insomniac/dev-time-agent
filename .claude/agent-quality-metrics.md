# Agent 服务质量指标

## 定位

本文件定义 `dev-time-agent` 的 Agent 服务质量指标。它用于产品验收、架构评审、研发排期、测试设计、eval 数据集建设和线上质量监控。

Dev Time 的 Agent 不是泛用聊天助手，而是项目风险驱动的工作流 Agent。好的 Agent 服务必须能围绕项目风险持续工作，并且每一步有证据、有状态、可恢复、可追踪、可评估、可控执行。

## 指标设计原则

- 所有风险结论必须可追溯到 `EvidenceBundle`、工具结果、session memory 或经过授权的知识库。
- 所有指标必须可度量，不能只写“更智能”“更好用”。
- 指标必须能解释为什么重要，并能映射到用户体验、工程可靠性或安全边界。
- MVP 可以先用离线标注集和集成测试度量，生产阶段必须接入 trace、eval、日志和用户反馈。
- 安全、权限、证据可信度是硬门槛，不用平均分抵消。

## 依据

本指标体系参考以下工程原则：

- OpenAI Agents SDK 的 agent 结构：模型、工具、handoff、guardrails、trace。
- OpenAI evals 的评测方法：dataset、grader、eval run、regression。
- LangGraph 的 agent 状态模型：persistence、checkpoint、memory、human-in-the-loop。
- Dev Time 的产品定位：项目风险驱动、证据约束、多轮会话、长任务、工具调用和用户确认。

## 北极星指标

| 指标 | 定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 风险闭环成功率 | Agent 是否把风险从发现推进到可执行下一步 | 成功闭环风险任务数 / 总风险任务数 | >= 70% | >= 85% | Dev Time 的价值不是聊天，而是推动风险处理 | AgentRun、ActionSuggestion、用户确认记录 |
| 有证据有效回答率 | 回答是否正确引用证据并解决用户问题 | 有证据且有效回答数 / 总回答数 | >= 90% | >= 97% | 无证据回答会破坏信任 | ConversationTurn、evidence_refs、人工/LLM grader |
| 用户无二次纠错率 | 用户不需要指出答非所问、没看上下文、证据错误 | 无纠错会话数 / 总会话数 | >= 80% | >= 92% | 直接反映 Agent 是否像可靠助手 | 用户消息分类、反馈按钮、bad case 标注 |
| P0 安全事故数 | 未授权写入、密钥泄露、跨租户泄露等硬事故 | 事故次数 | 0 | 0 | 安全问题不能用体验指标抵消 | 审计日志、安全扫描、事故记录 |

## P0 硬门槛

| 指标 | 合格线 | 不达标处理 |
| --- | --- | --- |
| 未授权写操作 | 0 | 阻断发布 |
| 密钥或 token 泄露 | 0 | 阻断发布并轮换密钥 |
| 跨租户数据污染 | 0 | 阻断发布 |
| 无证据风险结论率 | <= 1% | 阻断风险回答相关发布 |
| evidence_refs 覆盖率 | >= 98% | 阻断风险回答相关发布 |
| Approval gate recall | 100% | 阻断所有写工具发布 |
| Trace completeness | >= 95% | 不允许进入生产观测环境 |

## 1. 意图理解指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Intent Accuracy | 预测意图与标注意图一致 | 正确意图数 / 标注意图样本数 | >= 85% | >= 92% | 意图错会导致上下文、工具、回答路径全错 | intent eval dataset |
| Clarification Precision | Agent 澄清的问题确实需要澄清 | 正确澄清数 / 总澄清数 | >= 85% | >= 92% | 过度澄清会让 Agent 显得无能 | 会话标注 |
| Clarification Recall | 信息不足时能主动澄清 | 正确澄清数 / 应澄清样本数 | >= 90% | >= 95% | 防止证据不足时硬答 | 会话标注 |
| Irrelevant Answer Rate | 回答与用户问题无关的比例 | 无关回答数 / 总回答数 | <= 5% | <= 3% | 用户最容易感知的问题 | bad case 标注 |
| Follow-up Resolution Rate | “下一步呢”“然后呢”“为什么”等追问能接上上下文 | 成功追问数 / 追问样本数 | >= 90% | >= 95% | 多轮对话必须连续 | session replay |
| Intent Confidence Calibration | 置信度与实际正确率匹配 | ECE 或分桶误差 | <= 0.12 | <= 0.08 | 低置信度应触发澄清或加载证据 | eval run |

## 2. 证据可信度指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Evidence Citation Coverage | 涉及风险事实的回答是否带 evidence_refs | 带证据回答数 / 风险事实回答数 | >= 95% | >= 98% | 风险结论必须可追溯 | ConversationTurn |
| Unsupported Claim Rate | 没有证据支撑的事实断言比例 | 无支撑断言数 / 事实断言数 | <= 2% | <= 1% | 防止幻觉 | answer grader |
| Evidence Precision | 引用证据是否支持结论 | 有效引用数 / 总引用数 | >= 92% | >= 97% | 不能乱挂证据 | evidence grader |
| Evidence Recall | 关键证据是否被使用 | 被引用关键证据数 / 关键证据数 | >= 85% | >= 92% | 漏关键 CI/PR 会误判 | fixture 标注 |
| Stale Evidence Rejection | 证据过期时能拒答或重新加载 | 正确处理过期证据数 / 过期证据样本数 | >= 90% | >= 97% | 项目风险高度时效化 | EvidenceBundle version、trace |
| Contradiction Detection | 多证据冲突时能指出冲突 | 识别冲突数 / 冲突样本数 | >= 80% | >= 90% | CI、PR、issue 状态可能不一致 | conflict fixture |

## 3. 风险判断指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Risk Level Accuracy | high/medium/low 与标注一致 | 正确等级数 / 样本数 | >= 80% | >= 88% | 风险等级是产品核心 | risk eval dataset |
| Risk Score MAE | Agent 风险分与标注分平均误差 | mean(abs(pred - label)) | <= 10 | <= 8 | 比等级更细 | risk eval dataset |
| Root Cause Accuracy | 是否识别真正风险原因 | 正确根因数 / 样本数 | >= 80% | >= 88% | 决定后续行动方向 | 人工标注 |
| Impact Accuracy | 是否正确判断影响范围 | 正确影响判断数 / 样本数 | >= 75% | >= 85% | 决定优先级 | 人工标注 |
| Priority Ranking NDCG@3 | Top 3 风险排序质量 | NDCG@3 | >= 0.80 | >= 0.88 | 多风险场景要知道先处理什么 | 排序 eval |
| Uncertainty Calibration | 不确定时是否明确表达不确定或请求证据 | 正确不确定处理数 / 不确定样本数 | >= 85% | >= 93% | 防止装懂 | eval grader |

## 4. 记忆指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Session Continuity | 同 session 后续追问能使用上一轮上下文 | 成功连续追问数 / 追问数 | >= 90% | >= 97% | Agent 必须像连续对话 | session replay |
| Memory Precision | 恢复的记忆是否正确 | 正确记忆项 / 恢复记忆项 | >= 95% | >= 99% | 记错比不记更危险 | memory eval |
| Memory Recall | 应记住的关键信息是否恢复 | 恢复关键项 / 应恢复关键项 | >= 85% | >= 95% | 风险原因、证据、计划不能丢 | memory eval |
| Cross-session Pollution | A 会话信息污染 B 会话比例 | 污染会话数 / 总会话数 | 0 | 0 | 权限和隐私底线 | isolation test |
| Restart Recovery | Runtime 重启后记忆可恢复 | 恢复成功数 / 重启样本数 | >= 95% | >= 99% | 长任务和生产服务必需 | integration test |
| TTL Compliance | 过期记忆按策略失效 | 正确失效数 / 过期样本数 | >= 95% | >= 99% | 防止旧风险误导新判断 | memory store audit |
| Turn Summary Recovery | 可从 recent_turns 恢复上一轮回复摘要 | 正确恢复 turn summary 数 / 需要恢复样本数 | >= 90% | >= 97% | 支持“把刚才建议改短”等自然追问 | memory eval |
| Stale Fact Rejection | risk_assessment 变化后拒绝使用旧风险事实 | 正确拒绝旧事实数 / stale memory 样本数 | >= 95% | >= 99% | 防止旧风险原因污染新判断 | integration test |

## 5. 工具调用指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Tool Selection Accuracy | 是否选对工具 | 正确工具选择数 / 工具需求样本数 | >= 85% | >= 93% | 查 CI、PR、issue 不能混 | tool eval |
| Tool Call Validity | 参数 schema 合法比例 | 合法调用数 / 总工具调用数 | >= 97% | >= 99.5% | 工具调用不能经常失败 | tool trace |
| Tool Necessity Precision | 不该调用工具时不调用 | 必要调用数 / 总调用数 | >= 85% | >= 92% | 控成本和延迟 | trace eval |
| Tool Necessity Recall | 该调用工具时必须调用 | 已调用必要工具数 / 必要工具样本数 | >= 90% | >= 97% | 不能靠猜 | trace eval |
| Tool Result Grounding | 回答是否基于工具结果 | grounded 回答数 / 工具后回答数 | >= 95% | >= 98% | 工具调用不能只是摆设 | answer grader |
| Retry Recovery | 工具失败后可恢复比例 | 成功恢复数 / 工具失败数 | >= 70% | >= 85% | 外部 API 失败是常态 | failure trace |

## 6. 行动计划指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Plan Specificity | 是否包含对象、动作、顺序、验证方式 | 合格计划数 / 计划数 | >= 85% | >= 93% | “修复问题”不是计划 | plan grader |
| Plan Executability | 工程师能否直接执行 | 可执行计划数 / 计划数 | >= 80% | >= 90% | Dev Time 目标是推进交付 | 人工评审 |
| Dependency Order Accuracy | 步骤顺序是否合理 | 顺序正确计划数 / 计划数 | >= 85% | >= 93% | 例如先修 CI 再请求 review | plan grader |
| Minimal Next Action | 是否给出最小下一步 | 合格下一步数 / 计划数 | >= 85% | >= 93% | 降低用户行动成本 | plan grader |
| Action Draft Acceptance | 用户接受草稿比例 | 接受草稿数 / 总草稿数 | >= 40% | >= 65% | 衡量建议是否真的有用 | ActionSuggestion |
| Rework Rate | 用户大幅修改 Agent 草稿比例 | 大改草稿数 / 被使用草稿数 | <= 45% | <= 30% | 衡量草稿质量 | diff audit |

## 7. 人类确认与安全指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Approval Gate Recall | 高风险写操作是否全部要求确认 | 要确认且已确认数 / 要确认操作数 | 100% | 100% | 写操作必须可控 | approval audit |
| Unauthorized Execution | 未授权写操作次数 | 次数 | 0 | 0 | P0 安全指标 | audit log |
| Approval Context Completeness | 确认前展示原因、目标、草稿、证据 | 完整确认数 / 确认请求数 | >= 95% | >= 99% | 用户必须知道批准什么 | UI/API audit |
| Rejection Handling | 用户拒绝后停止或调整 | 正确处理拒绝数 / 拒绝数 | >= 98% | >= 99.5% | 不能顶着拒绝继续 | audit log |
| Permission Boundary Violations | 越权读写次数 | 次数 | 0 | 0 | 多租户和 GitHub 权限底线 | permission audit |

## 8. 长任务指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Task Resume Success | 中断后恢复成功率 | 恢复成功数 / 中断任务数 | >= 90% | >= 97% | 长任务必须可恢复 | checkpoint test |
| Checkpoint Coverage | 关键节点是否落 checkpoint | 已 checkpoint 节点数 / 关键节点数 | >= 90% | >= 98% | 无 checkpoint 无法恢复 | trace |
| Progress Visibility | 用户能看到当前阶段 | 有进度任务数 / 长任务数 | >= 90% | >= 98% | 防止黑盒等待 | AgentRun steps |
| Long-task Completion | 长任务最终完成比例 | 完成任务数 / 长任务数 | >= 80% | >= 90% | Agent 不能只会开头 | AgentRun |
| Deadlock Rate | 卡住不动比例 | deadlock 任务数 / 长任务数 | <= 5% | <= 2% | 长任务常见失败 | watchdog |
| Timeout Recovery | 超时后给出可操作下一步 | 正确超时处理数 / 超时数 | >= 85% | >= 95% | 用户不能被挂死 | failure trace |

## 9. 多 Agent 协作指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Handoff Accuracy | 是否交给正确 specialist agent | 正确 handoff 数 / handoff 数 | >= 85% | >= 93% | PR Doctor、Risk Scout 不能混 | handoff eval |
| Handoff Context Completeness | 交接是否带目标、证据、状态 | 完整 handoff 数 / handoff 数 | >= 90% | >= 97% | 下游 Agent 不能重新猜 | handoff trace |
| Duplicate Work Rate | 多 Agent 重复做同一件事比例 | 重复任务数 / 协作任务数 | <= 8% | <= 4% | 浪费成本且制造冲突 | task trace |
| Conflict Detection | Agent 结论冲突时能识别 | 识别冲突数 / 冲突数 | >= 80% | >= 90% | 多 Agent 必然会有冲突 | conflict eval |
| Arbitration Accuracy | 主控 Agent 仲裁是否合理 | 正确仲裁数 / 仲裁样本数 | >= 75% | >= 85% | 需要统一行动方向 | 人工评审 |

## 10. 交互体验指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| First Response Latency P95 | 首次可见响应时间 | P95 latency | <= 2s | <= 1.5s | 用户感知关键 | frontend RUM |
| Full Answer Latency P95 | 普通回答完成时间 | P95 latency | <= 8s | <= 5s | 太慢会被认为坏了 | trace |
| Streaming Availability | 长回答是否流式输出 | 流式长回答数 / 长回答数 | >= 80% | >= 95% | 长任务需要反馈 | frontend trace |
| Input Availability | 输入框始终可见可用 | 可用状态检查通过率 | 100% | 100% | 对话基本功能 | Playwright QA |
| Message Order Correctness | 最新消息在底部 | 顺序正确检查通过率 | 100% | 100% | 对话基本体验 | Playwright QA |
| Error Recovery UX | 失败后有可操作错误 | 可操作错误数 / 错误数 | >= 90% | >= 97% | 不能只说失败 | UI QA |

## 11. 可观测性指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Trace Completeness | 每轮记录 intent、node、tool、evidence、decision | 完整 trace 数 / 总 turn 数 | >= 95% | >= 99% | 无 trace 无法调试 | trace audit |
| Replayability | 历史 bad case 可重放 | 可重放 case 数 / bad case 数 | >= 90% | >= 97% | Agent 质量靠 replay 改 | eval repo |
| Span Coverage | graph node、tool、LLM 是否都有 span | 有 span 节点数 / 应追踪节点数 | >= 90% | >= 98% | 定位问题需要链路 | tracing |
| Cost Attribution | token 和成本能归因到任务 | 可归因调用数 / LLM 调用数 | >= 90% | >= 98% | Agent 成本必须可控 | LLM trace |
| Failure Classification | 失败按 intent/tool/LLM/evidence/permission 分类 | 已分类失败数 / 失败数 | >= 85% | >= 95% | 不分类无法改进 | error log |

## 12. Eval 体系指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Golden Set Coverage | 核心场景有评测集 | 已覆盖核心场景数 / 核心场景数 | >= 80% | >= 95% | 没数据集就靠感觉 | eval inventory |
| Regression Pass Rate | 每次变更通过核心回归 | 通过 case 数 / 总 case 数 | >= 90% | >= 97% | 防止越改越坏 | CI eval |
| Bad Case Turnaround | bad case 到测试覆盖时间 | P90 天数 | <= 3 天 | <= 2 天 | 真实反馈必须进入 eval | issue/eval link |
| Model Upgrade Safety | 换模型后核心指标下降 | 指标下降幅度 | <= 5% | <= 2% | OpenAI/DeepSeek 切换必须可控 | model eval |
| Prompt Drift Detection | prompt 改动导致行为漂移可发现 | 发现漂移数 / 漂移样本数 | >= 90% | >= 97% | Agent 常死于 prompt 漂移 | snapshot eval |

## 13. 可靠性与成本指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| API Availability | runtime 可用性 | 可用时间 / 总时间 | >= 99% | >= 99.9% | Agent 是核心链路 | uptime |
| Error Rate | 5xx 比例 | 5xx / 总请求 | <= 1% | <= 0.3% | 基础服务质量 | API metrics |
| Idempotency Success | 重试不重复创建草稿或任务 | 幂等成功数 / 重试数 | >= 98% | >= 99.5% | 工具执行必须幂等 | action audit |
| Token Cost Per Resolved Risk | 每个闭环风险的 token 成本 | 总 token 成本 / 闭环风险数 | 持续下降 | 持续下降 | 成本必须和价值挂钩 | LLM trace |
| Cache Hit Rate | 可复用上下文命中率 | 命中数 / 可缓存读取数 | >= 30% | >= 50% | 控成本和延迟 | cache metrics |
| Queue Lag P95 | AgentJob 等待时间 | P95 lag | <= 30s | <= 10s | 风险响应要及时 | queue metrics |

## 14. 安全与隐私指标

| 指标 | 可度量定义 | 公式 | MVP 合格线 | 生产合格线 | 理由 | 采集来源 |
| --- | --- | --- | --- | --- | --- | --- |
| Secret Leakage | 回复或日志泄露 key/token 次数 | 次数 | 0 | 0 | P0 | secret scan |
| Prompt Injection Success | 注入绕过规则比例 | 成功注入数 / 注入测试数 | <= 2% | <= 1% | 工具型 Agent 必须防注入 | red team eval |
| Tenant Isolation | 跨租户数据泄漏次数 | 次数 | 0 | 0 | P0 | isolation test |
| Private Data Overexposure | 非必要私有内容进入 prompt 比例 | 过曝 prompt 数 / prompt 数 | <= 5% | <= 2% | 最小化上下文 | prompt audit |
| Audit Log Completeness | 写操作审计完整率 | 完整审计数 / 写操作数 | 100% | 100% | 权限和追责 | audit log |

## Dev Time 指标权重

| 维度 | 权重 | 原因 |
| --- | --- | --- |
| 证据可信度 | 20% | 风险产品的信任底座 |
| 风险判断质量 | 15% | 决定 Agent 是否抓住真正问题 |
| 行动计划质量 | 12% | 决定用户是否能推进交付 |
| 意图理解 | 10% | 决定路由和上下文加载是否正确 |
| 记忆与上下文连续性 | 10% | 决定 Agent 是否像一个持续工作的助手 |
| 工具调用 | 10% | 决定 Agent 是否能读取和操作真实系统 |
| 人类确认与安全 | 10% | 决定写操作和权限是否可控 |
| 可观测性与 eval | 8% | 决定系统能否持续改进 |
| 交互体验 | 5% | 决定日常使用是否顺畅 |

## MVP 阶段必须先落地的度量

| 优先级 | 指标 | 最小实现 |
| --- | --- | --- |
| P0 | Evidence Citation Coverage | 所有风险回答校验 `evidence_refs` 非空 |
| P0 | Unsupported Claim Rate | 用 golden set + 人工抽检标注 |
| P0 | Session Continuity | 多轮追问集成测试和 replay |
| P0 | Approval Gate Recall | 写工具调用必须产生 `approval_request` |
| P0 | Trace Completeness | 每轮记录 intent、current_node、evidence_refs、tool_calls |
| P1 | Intent Accuracy | 建立 50 到 100 条中文意图样本 |
| P1 | Plan Specificity | 计划回答必须包含对象、动作、顺序、验证方式 |
| P1 | Restart Recovery | session memory store 重启测试 |
| P1 | Tool Call Validity | 工具参数 schema 测试 |
| P1 | Bad Case Turnaround | bad case 进入测试集的流程 |

## 发布门禁建议

### MVP 发布门禁

- `Evidence Citation Coverage >= 95%`
- `Unsupported Claim Rate <= 2%`
- `Session Continuity >= 90%`
- `Intent Accuracy >= 85%`
- `Trace Completeness >= 95%`
- `Unauthorized Execution = 0`
- `Secret Leakage = 0`
- `Cross-session Pollution = 0`

### 生产发布门禁

- `Evidence Citation Coverage >= 98%`
- `Unsupported Claim Rate <= 1%`
- `Session Continuity >= 97%`
- `Intent Accuracy >= 92%`
- `Risk Level Accuracy >= 88%`
- `Trace Completeness >= 99%`
- `Approval Gate Recall = 100%`
- `P0 安全事故 = 0`

## 后续实施顺序

1. 建立 `evals/`：意图识别、风险解释、行动计划、多轮追问、证据引用。
2. 完善 trace：intent、graph node、memory read/write、tool call、LLM call、evidence refs。
3. 增加 evidence grader：检查回答中的风险事实是否被 evidence_refs 支撑。
4. 增加 plan grader：检查行动计划是否包含对象、动作、顺序和验证方式。
5. 增加 tool layer 指标：工具选择、参数合法性、失败恢复。
6. 增加 human-in-the-loop 指标：写操作确认、拒绝处理、审计完整性。
7. 增加长任务 checkpoint 指标：恢复、进度、超时处理。
