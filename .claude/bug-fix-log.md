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
