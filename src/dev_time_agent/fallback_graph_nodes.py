import re
from collections.abc import Callable

from dev_time_agent.conversation import classify_intent, evidence_refs_from_bundle
from dev_time_agent.entity_resolver import (
    extract_pr_number,
    repository_entity,
    resolve_repository,
)
from dev_time_agent.graph_state import AgentState
from dev_time_agent.github_markdown import (
    format_check_list,
    format_issue_list,
    format_pull_request_list,
    format_repository_list,
)
from dev_time_agent.tools import ToolRegistry


def _no_tool_registry() -> ToolRegistry | None:
    return None


_tool_registry_provider: Callable[[], ToolRegistry | None] = _no_tool_registry


def configure_fallback_graph_node_dependencies(
    *,
    tool_registry_provider: Callable[[], ToolRegistry | None],
) -> None:
    global _tool_registry_provider
    _tool_registry_provider = tool_registry_provider


def intent_router(state: AgentState) -> AgentState:
    classification = classify_intent(state["user_message"])
    memory = state.get("memory", {})
    if is_previous_response_refinement(state["user_message"]):
        if memory_is_current_for_state(state) and memory.get("recent_turns"):
            return {
                **state,
                "intent": "refine_previous_response",
                "confidence": 0.84,
                "requires_evidence": False,
                "current_node": "intent_router",
                "trace_events": [
                    *state.get("trace_events", []),
                    {"node": "intent_router", "title": "识别为上一轮回复改写"},
                ],
            }
    if classification.intent == "clarify" and is_follow_up_action_request(
        state["user_message"]
    ):
        if memory_is_current_for_state(state) and (
            memory.get("last_risk_reason") or memory.get("last_evidence_refs")
        ):
            return {
                **state,
                "intent": "action_plan",
                "confidence": 0.82,
                "requires_evidence": True,
                "current_node": "intent_router",
                "trace_events": [
                    *state.get("trace_events", []),
                    {"node": "intent_router", "title": "识别为上下文追问"},
                ],
            }
    trace_title = "识别为项目状态查询"
    if classification.intent != "project_status":
        trace_title = "完成意图识别"
    return {
        **state,
        "intent": classification.intent,
        "confidence": classification.confidence,
        "requires_evidence": classification.requires_evidence,
        "current_node": "intent_router",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "intent_router", "title": trace_title},
        ],
    }


def route_after_intent(state: AgentState) -> str:
    intent = state.get("intent")
    if intent == "current_context":
        return "current_context_responder"
    if intent == "smalltalk":
        return "smalltalk_responder"
    if intent == "self_intro":
        return "self_intro_responder"
    if intent == "refine_previous_response":
        return "memory_responder"
    if intent in {
        "github_auth_status",
        "github_repository_list",
        "github_repository_detail",
    }:
        return "github_repository_reporter"
    if intent == "github_pr_ci_diagnosis":
        return "github_pr_ci_diagnoser"
    if intent == "github_pull_requests_list":
        return "github_pull_request_reporter"
    if intent == "github_issues_list":
        return "github_issue_reporter"
    if intent == "github_checks_list":
        return "github_check_reporter"
    if intent == "clarify":
        return "clarify_responder"
    if state.get("requires_evidence"):
        return "context_loader"
    return "clarify_responder"


def context_loader(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {})
    evidence_refs = evidence_refs_from_bundle(bundle) if bundle is not None else []
    tool_calls = list(state.get("tool_calls", []))
    tool_trace_events: list[dict[str, str]] = []
    tool_registry = _tool_registry_provider()
    if bundle is None and tool_registry is not None:
        tool_input = {"risk_assessment_id": state["risk_assessment_id"]}
        tool_result = tool_registry.run("risk_evidence.read", tool_input)
        bundle = tool_result.evidence_bundle
        evidence_refs = tool_result.evidence_refs
        tool_calls.append(
            {
                "name": "risk_evidence.read",
                "status": "succeeded",
                "input": tool_input,
                "evidence_refs": evidence_refs,
            }
        )
        tool_trace_events.append({"node": "tool_executor", "title": "调用风险证据工具"})
    memory_used = False
    if not evidence_refs and memory.get("last_evidence_refs"):
        if memory_is_current_for_state(state):
            evidence_refs = list(memory["last_evidence_refs"])
            memory_used = True
    trace_events = [
        *state.get("trace_events", []),
        {"node": "context_loader", "title": "加载风险证据"},
        *tool_trace_events,
    ]
    if memory_used:
        trace_events.append({"node": "memory_retriever", "title": "读取会话记忆"})
    return {
        **state,
        "evidence_bundle": bundle,
        "evidence_refs": evidence_refs,
        "tool_calls": tool_calls,
        "current_node": "context_loader",
        "trace_events": trace_events,
    }


def route_after_context(state: AgentState) -> str:
    if state.get("requires_evidence") and not state.get("evidence_refs"):
        return "clarify_responder"
    if state.get("intent") == "risk_explain":
        return "risk_analyst"
    if state.get("intent") == "action_plan":
        return "planner"
    return "status_reporter"


def smalltalk_responder(state: AgentState) -> AgentState:
    return {
        **state,
        "response": "你好，我是 Dev Time Agent。你可以让我解释当前风险、查看证据，或生成下一步行动计划。",
        "evidence_refs": [],
        "current_node": "smalltalk_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "smalltalk_responder", "title": "生成普通对话回复"},
        ],
    }


def self_intro_responder(state: AgentState) -> AgentState:
    active_model = state.get("active_model", {})
    provider = active_model.get("provider", "deterministic")
    model = active_model.get("model", "rules-v1")
    return {
        **state,
        "response": (
            "## Dev Time Agent\n\n"
            "我是面向研发交付的**项目风险 Agent**。我基于当前授权项目与风险事件，"
            "定位 PR、测试、CI 和交付阻塞，并给出有证据依据的解释与行动建议。\n\n"
            f"- **当前生效模型**：`{provider} / {model}`\n"
            "- **事实边界**：只把可信项目上下文和工具结果当作事实\n"
            "- **执行边界**：写操作会先生成草稿，并在执行前请求确认"
        ),
        "evidence_refs": [],
        "current_node": "self_intro_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "self_intro_responder", "title": "生成自我介绍回复"},
        ],
    }


def current_context_responder(state: AgentState) -> AgentState:
    trusted_context = state.get("trusted_context")
    if trusted_context is None:
        return {
            **state,
            "intent": "clarify",
            "response": "当前会话还没有绑定可信项目，请先从具体项目的风险页进入 Agent。",
            "evidence_refs": [],
            "current_node": "current_context_responder",
            "trace_events": [
                *state.get("trace_events", []),
                {"node": "current_context_responder", "title": "缺少可信项目上下文"},
            ],
        }
    repository = trusted_context.repository.model_dump()
    return {
        **state,
        "domain": "project_context",
        "entities": {"repository": repository},
        "capabilities": [],
        "response": (
            f"当前项目是 **{repository['full_name']}**。\n\n"
            f"- 项目：`{repository['project_id']}`\n"
            f"- Connected Repository：`{repository['id']}`"
        ),
        "evidence_refs": [],
        "current_node": "current_context_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "current_context_responder", "title": "读取可信项目上下文"},
        ],
    }


def clarify_responder(state: AgentState) -> AgentState:
    return {
        **state,
        "intent": "clarify",
        "response": "你想让我评估当前风险、解释证据，还是生成下一步行动计划？",
        "evidence_refs": [],
        "current_node": "clarify_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "clarify_responder", "title": "生成澄清问题"},
        ],
    }


def memory_responder(state: AgentState) -> AgentState:
    memory = state.get("memory", {})
    recent_turns = list(memory.get("recent_turns", []))
    last_turn = recent_turns[-1] if recent_turns else {}
    agent_summary = str(last_turn.get("agent_summary", "")).strip()
    if not agent_summary:
        agent_summary = "我需要先有上一轮回复，才能继续改写。"
    evidence_refs = list(last_turn.get("evidence_refs", []))
    return {
        **state,
        "response": f"简短版：{agent_summary}",
        "evidence_refs": evidence_refs,
        "current_node": "memory_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "memory_retriever", "title": "读取会话记忆"},
            {"node": "memory_responder", "title": "改写上一轮回复"},
        ],
    }


def github_repository_reporter(state: AgentState) -> AgentState:
    tool_registry = _tool_registry_provider()
    if tool_registry is None:
        return {
            **state,
            "response": (
                "我现在不能读取 GitHub 项目列表，因为 Agent Runtime 没有配置 "
                "dev-time-server internal API。请先配置 DEV_TIME_SERVER_INTERNAL_BASE_URL。"
            ),
            "evidence_refs": [],
            "current_node": "github_repository_reporter",
            "trace_events": [
                *state.get("trace_events", []),
                {"node": "github_repository_reporter", "title": "GitHub 工具未配置"},
            ],
        }

    tool_calls = list(state.get("tool_calls", []))
    trace_events = list(state.get("trace_events", []))

    auth_result = tool_registry.run("github.auth.status", {})
    tool_calls.append(
        {
            "name": "github.auth.status",
            "status": "succeeded",
            "input": {},
            "evidence_refs": [],
        }
    )
    trace_events.append({"node": "tool_executor", "title": "检查 GitHub 授权"})

    if state.get("intent") == "github_auth_status":
        repositories = auth_result.data.get("repositories", [])
        status = "GitHub 已连接" if auth_result.data.get("connected", False) else "GitHub 未连接"
        response = (
            f"{status}，当前可访问 {len(repositories)} 个仓库；"
            "读取权限包含 metadata、pull requests、checks、issues。"
        )
        return {
            **state,
            "domain": "github",
            "entities": {},
            "capabilities": ["github.auth.status"],
            "response": response,
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_repository_reporter",
            "trace_events": trace_events,
        }

    if not auth_result.data.get("connected", False):
        return {
            **state,
            "response": (
                "当前还没有 GitHub 授权，或没有启用分析的 GitHub 仓库。"
                "请先在 GitHub 设置里完成授权并导入仓库。"
            ),
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_repository_reporter",
            "trace_events": trace_events,
        }

    repos_result = tool_registry.run("github.repos.list", {})
    tool_calls.append(
        {
            "name": "github.repos.list",
            "status": "succeeded",
            "input": {},
            "evidence_refs": [],
        }
    )
    trace_events.append({"node": "tool_executor", "title": "列出 GitHub 仓库"})
    repositories = repos_result.data.get("repositories", [])
    repository_names = repository_full_names(repositories)
    if state.get("intent") == "github_repository_detail":
        repository = resolve_repository(state["user_message"], repositories)
        if repository is None:
            response = "我没有找到你提到的 GitHub 仓库，请先确认仓库名称或完成 GitHub 同步。"
        else:
            response = format_repository_detail(repository)
        return {
            **state,
            "domain": "github",
            "entities": {"repository": repository_entity(repository)}
            if repository is not None
            else {},
            "capabilities": ["github.repo.detail"],
            "response": response,
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_repository_reporter",
            "trace_events": trace_events,
        }

    if not repository_names:
        response = "当前 GitHub 已授权，但没有可用于 Dev Time 分析的仓库。"
    else:
        response = format_repository_list(repository_names)
    return {
        **state,
        "domain": "github",
        "entities": {},
        "capabilities": ["github.repos.list"],
        "response": response,
        "evidence_refs": [],
        "tool_calls": tool_calls,
        "current_node": "github_repository_reporter",
        "trace_events": trace_events,
    }


def github_pull_request_reporter(state: AgentState) -> AgentState:
    tool_registry = _tool_registry_provider()
    if tool_registry is None:
        return {
            **state,
            "response": (
                "我现在不能读取 GitHub PR 列表，因为 Agent Runtime 没有配置 "
                "dev-time-server internal API。请先配置 DEV_TIME_SERVER_INTERNAL_BASE_URL。"
            ),
            "evidence_refs": [],
            "current_node": "github_pull_request_reporter",
            "trace_events": [
                *state.get("trace_events", []),
                {"node": "github_pull_request_reporter", "title": "GitHub 工具未配置"},
            ],
        }

    tool_calls = list(state.get("tool_calls", []))
    trace_events = list(state.get("trace_events", []))

    repository = trusted_repository_for_state(state)
    if repository is None:
        repos_result = tool_registry.run("github.repos.list", {})
        repositories = repos_result.data.get("repositories", [])
        tool_calls.append(
            {
                "name": "github.repos.list",
                "status": "succeeded",
                "input": {},
                "evidence_refs": [],
            }
        )
        trace_events.append({"node": "tool_executor", "title": "列出 GitHub 仓库"})
        repository = resolve_repository(state["user_message"], repositories)
    if repository is None:
        return {
            **state,
            "response": "我没有找到你提到的 GitHub 仓库，请先确认仓库名称或完成 GitHub 同步。",
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_pull_request_reporter",
            "trace_events": trace_events,
        }

    repository_id = str(repository["id"])
    prs_result = tool_registry.run(
        "github.pull_requests.list",
        {"repository_id": repository_id},
    )
    pull_requests = prs_result.data.get("pull_requests", [])
    evidence_refs = evidence_refs_from_pull_requests(pull_requests)
    tool_calls.append(
        {
            "name": "github.pull_requests.list",
            "status": "succeeded",
            "input": {"repository_id": repository_id},
            "evidence_refs": evidence_refs,
        }
    )
    trace_events.append({"node": "tool_executor", "title": "列出 GitHub PR"})

    repository_name = repository.get("full_name") or repository.get("name")
    if not pull_requests:
        response = f"{repository_name} 当前没有已记录的 PR。"
    else:
        response = format_pull_request_list(str(repository_name), pull_requests)
    return {
        **state,
        "domain": "github",
        "entities": {"repository": repository_entity(repository)},
        "capabilities": ["github.pull_requests.list"],
        "response": response,
        "evidence_refs": evidence_refs,
        "tool_calls": tool_calls,
        "current_node": "github_pull_request_reporter",
        "trace_events": trace_events,
    }


def github_issue_reporter(state: AgentState) -> AgentState:
    tool_registry = _tool_registry_provider()
    if tool_registry is None:
        return {
            **state,
            "response": (
                "我现在不能读取 GitHub Issue 列表，因为 Agent Runtime 没有配置 "
                "dev-time-server internal API。请先配置 DEV_TIME_SERVER_INTERNAL_BASE_URL。"
            ),
            "evidence_refs": [],
            "current_node": "github_issue_reporter",
            "trace_events": [
                *state.get("trace_events", []),
                {"node": "github_issue_reporter", "title": "GitHub 工具未配置"},
            ],
        }

    tool_calls = list(state.get("tool_calls", []))
    trace_events = list(state.get("trace_events", []))

    repository = trusted_repository_for_state(state)
    if repository is None:
        repos_result = tool_registry.run("github.repos.list", {})
        repositories = repos_result.data.get("repositories", [])
        tool_calls.append(
            {
                "name": "github.repos.list",
                "status": "succeeded",
                "input": {},
                "evidence_refs": [],
            }
        )
        trace_events.append({"node": "tool_executor", "title": "列出 GitHub 仓库"})
        repository = resolve_repository(state["user_message"], repositories)
    if repository is None:
        return {
            **state,
            "response": "我没有找到你提到的 GitHub 仓库，请先确认仓库名称或完成 GitHub 同步。",
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_issue_reporter",
            "trace_events": trace_events,
        }

    repository_id = str(repository["id"])
    issues_result = tool_registry.run(
        "github.issues.list",
        {"repository_id": repository_id},
    )
    issues = issues_result.data.get("issues", [])
    evidence_refs = evidence_refs_from_items(issues)
    tool_calls.append(
        {
            "name": "github.issues.list",
            "status": "succeeded",
            "input": {"repository_id": repository_id},
            "evidence_refs": evidence_refs,
        }
    )
    trace_events.append({"node": "tool_executor", "title": "列出 GitHub Issue"})

    repository_name = repository.get("full_name") or repository.get("name")
    if not issues:
        response = f"{repository_name} 当前没有已记录的 Issue。"
    else:
        response = format_issue_list(str(repository_name), issues)
    return {
        **state,
        "domain": "github",
        "entities": {"repository": repository_entity(repository)},
        "capabilities": ["github.issues.list"],
        "response": response,
        "evidence_refs": evidence_refs,
        "tool_calls": tool_calls,
        "current_node": "github_issue_reporter",
        "trace_events": trace_events,
    }


def github_check_reporter(state: AgentState) -> AgentState:
    tool_registry = _tool_registry_provider()
    if tool_registry is None:
        return {
            **state,
            "response": (
                "我现在不能读取 GitHub Checks 列表，因为 Agent Runtime 没有配置 "
                "dev-time-server internal API。请先配置 DEV_TIME_SERVER_INTERNAL_BASE_URL。"
            ),
            "evidence_refs": [],
            "current_node": "github_check_reporter",
            "trace_events": [
                *state.get("trace_events", []),
                {"node": "github_check_reporter", "title": "GitHub 工具未配置"},
            ],
        }

    tool_calls = list(state.get("tool_calls", []))
    trace_events = list(state.get("trace_events", []))

    repos_result = tool_registry.run("github.repos.list", {})
    repositories = repos_result.data.get("repositories", [])
    tool_calls.append(
        {
            "name": "github.repos.list",
            "status": "succeeded",
            "input": {},
            "evidence_refs": [],
        }
    )
    trace_events.append({"node": "tool_executor", "title": "列出 GitHub 仓库"})

    repository = resolve_repository(state["user_message"], repositories)
    if repository is None:
        return {
            **state,
            "response": "我没有找到你提到的 GitHub 仓库，请先确认仓库名称或完成 GitHub 同步。",
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_check_reporter",
            "trace_events": trace_events,
        }

    repository_id = str(repository["id"])
    checks_result = tool_registry.run(
        "github.checks.list",
        {"repository_id": repository_id},
    )
    checks = checks_result.data.get("checks", [])
    evidence_refs = evidence_refs_from_items(checks)
    tool_calls.append(
        {
            "name": "github.checks.list",
            "status": "succeeded",
            "input": {"repository_id": repository_id},
            "evidence_refs": evidence_refs,
        }
    )
    trace_events.append({"node": "tool_executor", "title": "列出 GitHub Checks"})

    repository_name = repository.get("full_name") or repository.get("name")
    if not checks:
        response = f"{repository_name} 当前没有已记录的 CI/Checks。"
    else:
        response = format_check_list(str(repository_name), checks)
    return {
        **state,
        "domain": "github",
        "entities": {"repository": repository_entity(repository)},
        "capabilities": ["github.checks.list"],
        "response": response,
        "evidence_refs": evidence_refs,
        "tool_calls": tool_calls,
        "current_node": "github_check_reporter",
        "trace_events": trace_events,
    }


def github_pr_ci_diagnoser(state: AgentState) -> AgentState:
    tool_registry = _tool_registry_provider()
    if tool_registry is None:
        return {
            **state,
            "response": (
                "我现在不能读取 GitHub CI 日志，因为 Agent Runtime 没有配置 "
                "dev-time-server internal API。请先配置 DEV_TIME_SERVER_INTERNAL_BASE_URL。"
            ),
            "evidence_refs": [],
            "current_node": "github_pr_ci_diagnoser",
            "trace_events": [
                *state.get("trace_events", []),
                {"node": "github_pr_ci_diagnoser", "title": "GitHub 工具未配置"},
            ],
        }

    pr_number = extract_pr_number(state["user_message"])
    tool_calls = list(state.get("tool_calls", []))
    trace_events = list(state.get("trace_events", []))

    trusted_context = state.get("trusted_context")
    if trusted_context is not None and trusted_context.risk_episode is not None:
        return diagnose_trusted_risk_episode(
            state,
            tool_registry,
            pr_number,
            tool_calls,
            trace_events,
        )

    repos_result = tool_registry.run("github.repos.list", {})
    repositories = repos_result.data.get("repositories", [])
    tool_calls.append(
        {
            "name": "github.repos.list",
            "status": "succeeded",
            "input": {},
            "evidence_refs": [],
        }
    )
    trace_events.append({"node": "tool_executor", "title": "列出 GitHub 仓库"})

    repository = resolve_repository(state["user_message"], repositories)
    if repository is None or pr_number is None:
        return {
            **state,
            "response": "我需要明确的仓库和 PR 编号，才能诊断这次 CI 失败。",
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_pr_ci_diagnoser",
            "trace_events": trace_events,
        }

    repository_id = str(repository["id"])
    prs_result = tool_registry.run(
        "github.pull_requests.list",
        {"repository_id": repository_id},
    )
    pull_requests = prs_result.data.get("pull_requests", [])
    pr_evidence_refs = evidence_refs_from_pull_requests(pull_requests)
    tool_calls.append(
        {
            "name": "github.pull_requests.list",
            "status": "succeeded",
            "input": {"repository_id": repository_id},
            "evidence_refs": pr_evidence_refs,
        }
    )
    trace_events.append({"node": "tool_executor", "title": "读取 PR 列表"})

    checks_result = tool_registry.run(
        "github.checks.list",
        {"repository_id": repository_id},
    )
    checks = checks_result.data.get("checks", [])
    checks_evidence_refs = evidence_refs_from_items(checks)
    tool_calls.append(
        {
            "name": "github.checks.list",
            "status": "succeeded",
            "input": {"repository_id": repository_id},
            "evidence_refs": checks_evidence_refs,
        }
    )
    trace_events.append({"node": "tool_executor", "title": "读取失败 Checks"})

    failed_check = first_failed_check(checks)
    run_id = failed_check_run_id(failed_check) if failed_check else None
    if run_id is None:
        response = f"PR #{pr_number} 当前没有可诊断的失败 CI run。"
        return {
            **state,
            "domain": "github",
            "entities": {
                "repository": repository_entity(repository),
                "pr_number": pr_number,
            },
            "capabilities": ["github.checks.logs"],
            "response": response,
            "evidence_refs": [*pr_evidence_refs, *checks_evidence_refs],
            "tool_calls": tool_calls,
            "current_node": "github_pr_ci_diagnoser",
            "trace_events": trace_events,
        }

    logs_result = tool_registry.run(
        "github.checks.logs",
        {"repository_id": repository_id, "run_id": run_id},
    )
    log_data = logs_result.data
    log_evidence_refs = logs_result.evidence_refs
    tool_calls.append(
        {
            "name": "github.checks.logs",
            "status": "succeeded",
            "input": {"repository_id": repository_id, "run_id": run_id},
            "evidence_refs": log_evidence_refs,
        }
    )
    trace_events.append({"node": "tool_executor", "title": "读取失败 Check 日志"})

    response = format_ci_log_diagnosis(pr_number, failed_check, log_data)
    return {
        **state,
        "domain": "github",
        "entities": {
            "repository": repository_entity(repository),
            "pr_number": pr_number,
            "run_id": run_id,
        },
        "capabilities": ["github.checks.logs"],
        "response": response,
        "evidence_refs": [*pr_evidence_refs, *checks_evidence_refs, *log_evidence_refs],
        "tool_calls": tool_calls,
        "current_node": "github_pr_ci_diagnoser",
        "trace_events": trace_events,
    }


def diagnose_trusted_risk_episode(
    state: AgentState,
    tool_registry: ToolRegistry,
    pr_number: int | None,
    tool_calls: list[dict],
    trace_events: list[dict],
) -> AgentState:
    trusted_context = state["trusted_context"]
    episode = trusted_context.risk_episode
    assert episode is not None
    repository = trusted_context.repository.model_dump()
    if pr_number is None or pr_number != episode.pull_request:
        return {
            **state,
            "response": (
                f"当前可信风险事件绑定的是 PR #{episode.pull_request}；"
                "请确认要诊断的 PR 编号，避免把其他 CI 失败错误归因到当前 PR。"
            ),
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_pr_ci_diagnoser",
            "trace_events": trace_events,
        }
    if episode.check_run_id <= 0:
        return {
            **state,
            "domain": "github",
            "entities": {
                "repository": repository_entity(repository),
                "pr_number": pr_number,
                "head_sha": episode.head_sha,
            },
            "capabilities": ["github.checks.logs"],
            "response": (
                f"PR #{pr_number} 的风险事件已绑定到 head `{episode.head_sha}`，"
                "但当前没有可信的 check run ID，不能安全读取失败日志。"
            ),
            "evidence_refs": [],
            "tool_calls": tool_calls,
            "current_node": "github_pr_ci_diagnoser",
            "trace_events": trace_events,
        }

    tool_input = {
        "repository_id": repository["id"],
        "run_id": episode.check_run_id,
    }
    logs_result = tool_registry.run("github.checks.logs", tool_input)
    tool_calls.append(
        {
            "name": "github.checks.logs",
            "status": "succeeded",
            "input": tool_input,
            "evidence_refs": logs_result.evidence_refs,
        }
    )
    trace_events.append(
        {"node": "tool_executor", "title": "读取风险事件绑定的 Check 日志"}
    )
    check = {
        "run_id": episode.check_run_id,
        "name": episode.failed_gate,
        "url": episode.evidence_url,
    }
    return {
        **state,
        "domain": "github",
        "entities": {
            "repository": repository_entity(repository),
            "risk_episode_id": episode.id,
            "pr_number": pr_number,
            "head_sha": episode.head_sha,
            "run_id": episode.check_run_id,
        },
        "capabilities": ["github.checks.logs"],
        "response": format_ci_log_diagnosis(pr_number, check, logs_result.data),
        "evidence_refs": logs_result.evidence_refs,
        "tool_calls": tool_calls,
        "current_node": "github_pr_ci_diagnoser",
        "trace_events": trace_events,
    }


def status_reporter(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {}) if memory_is_current_for_state(state) else {}
    if state.get("intent") != "project_status" or bundle is None:
        if memory.get("last_project_name") and memory.get("last_risk_level"):
            response = (
                f"当前项目 {memory['last_project_name']} 处于"
                f"{format_risk_level(memory['last_risk_level'])}状态，"
                f"风险分 {memory.get('last_risk_score', '未知')}。"
                f"主要阻塞：{memory.get('last_risk_reason', '暂无活跃风险信号')}"
            )
        else:
            response = "你想让我评估当前风险、解释证据，还是生成下一步行动计划？"
    else:
        reason = bundle.signals[0].reason if bundle.signals else "暂无活跃风险信号"
        response = (
            f"当前项目 {bundle.project.name} 处于{format_risk_level(bundle.assessment.level)}状态，"
            f"风险分 {bundle.assessment.score}。主要阻塞：{reason}"
        )
    return {
        **state,
        "response": response,
        "current_node": "status_reporter",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "status_reporter", "title": "生成项目状态回复"},
        ],
    }


def risk_analyst(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {}) if memory_is_current_for_state(state) else {}
    reason = memory.get("last_risk_reason", "暂无活跃风险信号")
    if bundle is not None and bundle.signals:
        reason = bundle.signals[0].reason
    return {
        **state,
        "response": f"当前风险原因：{reason}",
        "current_node": "risk_analyst",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "risk_analyst", "title": "生成风险解释"},
        ],
    }


def planner(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {}) if memory_is_current_for_state(state) else {}
    reason = memory.get("last_risk_reason", "暂无活跃风险信号")
    if bundle is not None and bundle.signals:
        reason = bundle.signals[0].reason
    return {
        **state,
        "response": (
            "行动计划：先确认阻塞证据，再定位失败检查，随后修复并重新运行测试。"
            f"当前依据：{reason}"
        ),
        "current_node": "planner",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "planner", "title": "生成行动计划"},
        ],
    }


def format_risk_level(level: str) -> str:
    labels = {
        "high": "高风险",
        "medium": "中风险",
        "low": "低风险",
    }
    return labels.get(level, level)


def is_follow_up_action_request(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"下一步呢", "然后呢", "接下来呢", "继续呢", "那怎么办"}


def is_previous_response_refinement(message: str) -> bool:
    normalized = message.strip().lower()
    mentions_previous = any(
        keyword in normalized for keyword in {"刚才", "上一轮", "前面", "刚刚"}
    )
    asks_refinement = any(
        keyword in normalized for keyword in {"改短", "简短", "精简", "委婉", "改写"}
    )
    return mentions_previous and asks_refinement


def memory_is_current_for_state(state: AgentState) -> bool:
    memory = state.get("memory", {})
    if not memory:
        return False
    memory_project_id = memory.get("fact_project_id") or memory.get("project_id")
    memory_risk_assessment_id = memory.get("fact_risk_assessment_id") or memory.get(
        "risk_assessment_id"
    )
    if memory_project_id and memory_project_id != state.get("project_id"):
        return False
    if memory_risk_assessment_id and memory_risk_assessment_id != state.get(
        "risk_assessment_id"
    ):
        return False
    return True


def repository_full_names(repositories: list[dict]) -> list[str]:
    names: list[str] = []
    for repository in repositories:
        full_name = repository.get("full_name")
        if full_name:
            names.append(str(full_name))
            continue
        owner = repository.get("owner")
        name = repository.get("name")
        if owner and name:
            names.append(f"{owner}/{name}")
    return names


def format_repository_detail(repository: dict) -> str:
    full_name = repository.get("full_name") or repository.get("name") or "unknown"
    repository_id = repository.get("id") or "unknown"
    github_id = repository.get("github_id") or "unknown"
    project_id = repository.get("project_id") or "未绑定"
    analysis_enabled = repository.get("analysis_enabled", True)
    analysis_label = "已启用" if analysis_enabled is not False else "已关闭"
    sync_status = repository.get("sync_status") or "unknown"
    return (
        f"我能看到 GitHub 项目 {full_name}。"
        f"仓库 ID：{repository_id}；GitHub ID：{github_id}；"
        f"绑定项目：{project_id}；分析状态：{analysis_label}；同步状态：{sync_status}。"
    )


def evidence_refs_from_pull_requests(pull_requests: list[dict]) -> list[str]:
    return evidence_refs_from_items(pull_requests)


def trusted_repository_for_state(state: AgentState) -> dict | None:
    trusted_context = state.get("trusted_context")
    if trusted_context is None:
        return None
    return trusted_context.repository.model_dump()


def evidence_refs_from_items(items: list[dict]) -> list[str]:
    refs: list[str] = []
    for item in items:
        evidence_ref = item.get("evidence_ref")
        if evidence_ref:
            refs.append(str(evidence_ref))
    return refs


def first_failed_check(checks: list[dict]) -> dict | None:
    for check in checks:
        if str(check.get("conclusion", "")).lower() == "failure":
            return check
    return checks[0] if checks else None


def failed_check_run_id(check: dict | None) -> int | None:
    if check is None:
        return None
    raw_run_id = check.get("run_id") or check.get("id")
    if raw_run_id:
        try:
            return int(raw_run_id)
        except (TypeError, ValueError):
            pass
    match = re.search(r"/runs/(\d+)", str(check.get("url", "")))
    if match is None:
        return None
    return int(match.group(1))


def format_ci_log_diagnosis(pr_number: int, check: dict, log_data: dict) -> str:
    log_excerpt = str(log_data.get("log_excerpt") or "")
    check_name = str(log_data.get("check_name") or check.get("name") or "CI")
    linter_name = (
        "ESLint"
        if "eslint" in check_name.lower() or "eslint" in log_excerpt.lower()
        else check_name
    )
    unused_error_count = log_excerpt.count("no-unused-vars")
    first_location = first_log_location(log_excerpt)
    if unused_error_count > 0:
        root_cause = (
            f"PR #{pr_number} 的 CI 失败是因为 {linter_name} 报了 "
            f"{unused_error_count} 个 no-unused-vars 错误。"
        )
    else:
        root_cause = f"PR #{pr_number} 的 CI 失败来自 {check_name}。"
    next_step = "Next Step：查看失败日志片段并修复对应代码。"
    if first_location:
        next_step = f"Next Step：先检查 {first_location}，移除未使用变量或补上实际使用。"
    return f"{root_cause}{next_step}"


def first_log_location(log_excerpt: str) -> str:
    match = re.search(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9]+):(\d+)", log_excerpt)
    if match is None:
        return ""
    return f"{match.group(1)} 第 {match.group(2)} 行"
