# 编码规范

## 适用范围

本文件定义 `dev-time-agent` Agent Runtime 代码规范和行数约束。技术栈、工具链和验证命令以 `tech-stack.md` 为准。

## 基础原则

- Agent 负责推理、解释、结构化输出和行动草稿，不维护 canonical state。
- EvidenceBundle 必须来自 `dev-time-server` internal API。
- 所有 Agent 输出必须包含 evidence refs；证据不足时返回明确状态。
- prompt、schema、workflow 和 eval fixture 必须可独立演进。
- Agent 不直接写 GitHub，不绕过 `dev-time-server` 权限校验。
- Session memory 只保存对话短期上下文摘要，例如上一轮风险原因、证据引用和意图；不得把它当作 canonical 项目状态。

## Python 代码规范

- 遵循 PEP 8；格式化和 lint 使用 Ruff。
- 函数签名必须有类型标注。
- 核心数据契约使用 Pydantic model，不用裸 `dict` 在 workflow 间传递。
- workflow 分层为 context loading、prompt rendering、model call、output validation、artifact mapping。
- prompt 模板和 Python 控制逻辑分离。
- LLM adapter 必须处理 timeout、retry、结构化输出校验和错误分类。
- Memory store 必须隐藏具体存储实现。Graph node 只能通过 store 接口读取/写入 session memory，不直接操作 SQL、文件或全局 dict。
- 日志只记录对象 ID、状态、模型、耗时和错误摘要。

## Agent 工作流规范

- Risk Scout、PR Doctor、Milestone Planner、Scope Guard、Daily Brief、Action Drafter 各自独立目录。
- 每个 workflow 必须声明输入 schema、输出 schema、失败状态和 eval fixture。
- prompt version 必须随 AgentArtifact 或 AgentRun 记录。
- 修改 prompt 或 output schema 时，必须更新 replay fixture 或 snapshot。
- ActionSuggestion 草稿必须包含目标对象、正文、生成原因、证据引用和权限要求。

## 行数规范

| 对象 | 目标上限 | 硬上限 | 处理方式 |
| --- | --- | --- | --- |
| Python 普通模块 | 300 行 | 400 行 | 按 workflow、schema、adapter、mapper 拆分 |
| 单个函数 | 50 行 | 90 行 | 拆 context、validation、mapping 或 prompt rendering |
| workflow 主函数 | 80 行 | 130 行 | 拆成明确阶段函数 |
| Pydantic schema 文件 | 250 行 | 350 行 | 按 AgentJob、EvidenceBundle、Artifact、ActionSuggestion 拆分 |
| LLM provider adapter | 220 行 | 320 行 | 按 provider 或通用 client 分层 |
| prompt 模板文件 | 220 行 | 320 行 | 按 agent type 和 prompt version 拆分 |
| eval / replay 测试文件 | 350 行 | 520 行 | 按 workflow 和 fixture 场景拆分 |

超过硬上限时，PR 必须说明为什么暂不拆分，并补一个后续拆分任务。

## 例外

- fixture、snapshot、golden output 不受普通行数限制，但必须放在 `fixtures` 或 `snapshots` 目录。
- 生成代码不受行数限制，但必须标记 generated。
- prompt 历史版本可以保留较长文件，但活跃版本应按本规范维护。

## 评审检查

代码评审时优先检查：

- Agent 是否只使用 EvidenceBundle 内证据。
- 输出是否结构化并带 evidence refs。
- 证据不足、模型失败、schema 校验失败是否有明确状态。
- prompt 变更是否有 replay 或 snapshot 验证。
- 是否存在绕过 `dev-time-server` 权限和事实源边界的读取或写入。
