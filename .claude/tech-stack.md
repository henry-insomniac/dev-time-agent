# 技术栈与技术规范

## 当前决策

`dev-time-agent` 是 Dev Time 的 Agent Runtime 服务，负责 AgentJob 消费、EvidenceBundle 构建、Agent workflow 编排、LLM 调用、结构化输出校验、eval/replay 和行动草稿生成。

Agent 服务技术栈定稿如下：

| 类别 | 选型 | 说明 |
| --- | --- | --- |
| 语言 | Python | Agent workflow、LLM provider、eval/replay 生态更成熟，迭代速度更快 |
| 包管理器 | uv | 快速、统一管理依赖、虚拟环境和 lockfile |
| API / Internal Endpoint | FastAPI | 如需 internal HTTP endpoint，使用类型提示和 Pydantic schema |
| Worker | Python worker process | MVP 优先消费 AgentJob，HTTP 只作为内部管理或对话入口 |
| Schema | Pydantic | 定义 EvidenceBundle、AgentArtifact、ConversationTurn、ActionSuggestion |
| Lint / Format | Ruff | 统一 lint 和 format，减少工具链复杂度 |
| 测试 | pytest | 覆盖 workflow、schema、prompt rendering、eval fixture 和 replay |
| 类型检查 | pyright 或 mypy | 项目初始化时二选一；Agent 数据契约必须静态可检查 |
| 存储访问 | dev-time-server internal API 优先 | Agent 不直接维护 canonical state；如需读库必须只读且有明确边界 |

## 为什么 Agent 使用 Python

`dev-time-server` 使用 Go 管事实、权限、同步和写入；`dev-time-agent` 使用 Python 管推理、prompt、模型适配、结构化输出和 eval。

这个拆分的原因：

- Agent 早期会频繁调整 prompt、workflow、schema 和 eval，Python 迭代成本更低。
- Pydantic、FastAPI、pytest、LLM SDK 和评估工具生态更适合 Agent Runtime。
- Go 更适合稳定后端边界，不适合把快速变化的 Agent 编排和核心业务 API 混在一起。
- Python Agent 不维护 canonical state，不直接写 GitHub，因此语言拆分不会破坏事实源边界。

Go 版 Agent 可作为后续实验，但不作为 MVP 默认方案。

## 技术规范来源

技术栈规范优先以官方文档为准：

- Python PEP 8：https://peps.python.org/pep-0008/
- FastAPI：https://fastapi.tiangolo.com/
- FastAPI Python Types：https://fastapi.tiangolo.com/python-types/
- Pydantic：https://pydantic.dev/docs/validation/latest/get-started/
- Ruff：https://docs.astral.sh/ruff/
- uv：https://docs.astral.sh/uv/

## Agent 架构规范

- AgentJob 只携带 ID 和触发上下文，不携带大量 GitHub 原始数据。
- EvidenceBundle 必须通过 `dev-time-server` internal API 获取，避免绕过权限和事实源边界。
- 所有 Agent 输出必须是结构化对象，并包含 `evidence_refs`。
- 证据不足时返回 `insufficient_evidence`，不得编造 GitHub object、风险原因或行动建议。
- Agent 只生成 ActionSuggestion 草稿，不直接执行 GitHub 写入。
- LLM provider key 的所有权和审计归 `dev-time-server`；Agent 不落库明文 key。
- prompt、model、token usage、cost estimate 和 output schema version 必须进入 AgentRun 记录。
- eval fixture 和 replay snapshot 是 Agent 变更的一部分；prompt 调整必须能回放比较。

## 目录建议

项目初始化后建议采用以下结构：

```text
src/
├── dev_time_agent/
│   ├── app/
│   ├── config/
│   ├── context/
│   ├── workflows/
│   │   ├── risk_scout/
│   │   ├── pr_doctor/
│   │   ├── milestone_planner/
│   │   ├── scope_guard/
│   │   ├── daily_brief/
│   │   └── action_drafter/
│   ├── llm/
│   ├── schemas/
│   ├── tools/
│   ├── evals/
│   └── artifacts/
tests/
fixtures/
```

## Python 代码规范

- 遵循 PEP 8；格式化和 lint 由 Ruff 执行。
- 对外数据契约必须使用 Pydantic model，不使用裸 `dict` 在 workflow 间传递核心对象。
- 函数签名必须有类型标注；复杂返回值使用具名 model 或 dataclass。
- workflow 分成 context loading、prompt rendering、model call、output validation、artifact mapping 五段。
- prompt 模板和 Python 控制逻辑分离；不要把长 prompt 字符串塞进 workflow 函数体。
- LLM 调用必须有 timeout、retry 策略和结构化输出校验。
- 日志只记录对象 ID、状态、模型、耗时和错误摘要，不记录密钥或 private repo 非必要全文。
- eval fixture 必须可离线运行，避免依赖实时 GitHub API。

## 行数规范

详见 `coding-standards.md`。核心约束：

- Python 普通模块目标不超过 300 行，超过 400 行必须拆分或在 PR 中说明原因。
- 单个函数目标不超过 50 行；workflow 主函数目标不超过 80 行。
- Pydantic schema 文件目标不超过 250 行，按领域拆分。
- prompt 模板单独存放，单个模板文件目标不超过 220 行。
- fixture、snapshot 和 generated files 不受普通行数上限约束，但必须放在明确目录。

## 脚本规范

项目初始化后建议提供：

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run pytest
```

如引入类型检查：

```bash
uv run pyright
```

## 依赖规范

新增依赖前需要说明：

- 依赖解决什么问题。
- 是否已有标准库、Pydantic、FastAPI 或项目内工具可替代。
- 是否会增加安装、运行或维护成本。
- 是否需要网络、账号或密钥。

MVP 阶段避免过早引入重型 Agent 框架。优先使用薄 workflow 编排、显式 schema、显式 LLM adapter 和可回放 fixture。

## 安全规范

- 不提交 `.env`、密钥、令牌、Cookie、账号凭据。
- 示例配置使用 `.env.example`。
- Agent 日志不得记录 LLM API Key、GitHub token、webhook secret 或 private repo 的非必要全文。
- Agent 不直接写 GitHub；所有写入必须经过 `dev-time-server` 权限校验和用户确认。
- EvidenceBundle 过期或权限不足时，Agent 必须返回明确状态，不生成无证据建议。

## 验证规范

当前仓库尚未初始化 Python 工程。初始化后最小验证命令为：

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

涉及 prompt、workflow、schema 或 provider adapter 时，必须补充 replay fixture 或 snapshot 测试。
