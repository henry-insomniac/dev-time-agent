from typing import Any

from dev_time_agent.capability_registry import build_default_capability_registry
from dev_time_agent.conversation import evidence_refs_from_bundle
from dev_time_agent.docs_retrieval import retrieve_docs
from dev_time_agent.schemas import EvidenceBundle, PageContext


CAPABILITIES = [
    "风险解释",
    "项目状态",
    "证据追踪",
    "行动计划",
    "PR/CI 排障",
    "GitHub 授权仓库读取",
    "草稿生成",
    "工具调用",
    "长任务跟踪",
]

BOUNDARIES = [
    "不能编造证据",
    "风险结论必须引用 evidence_refs",
    "写操作必须请求用户确认",
    "普通对话不要强行解释当前风险",
    "当前风险上下文只能在相关问题里使用",
    "GitHub 项目、仓库、PR、CI 可见性必须先调用 GitHub 工具确认授权状态",
    "project_id 是内部标识，不能当作用户可见项目名称",
]


def assemble_agent_context(
    *,
    user_message: str,
    project_id: str,
    risk_assessment_id: str,
    memory: dict[str, Any],
    evidence_bundle: EvidenceBundle | None,
    available_tools: list[str],
    page_context: PageContext | None = None,
    tool_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "agent_identity": "Dev Time 项目风险 Agent",
        "capabilities": CAPABILITIES,
        "boundaries": BOUNDARIES,
        "user_message": user_message,
        "project_id": project_id,
        "risk_assessment_id": risk_assessment_id,
        "page_context": summarize_page_context(page_context),
        "session_memory": memory,
        "available_tools": available_tools,
        "capability_registry": capability_registry_context(),
        "tool_results": tool_results or {},
        "retrieved_docs": summarize_retrieved_docs(user_message),
        "evidence_summary": summarize_evidence(evidence_bundle),
    }


def summarize_evidence(evidence_bundle: EvidenceBundle | None) -> dict[str, Any]:
    if evidence_bundle is None:
        return {"available": False, "evidence_refs": []}
    return {
        "available": True,
        "project_name": evidence_bundle.project.name,
        "risk_score": evidence_bundle.assessment.score,
        "risk_level": evidence_bundle.assessment.level,
        "signals": [
            {
                "reason": signal.reason,
                "severity": signal.severity,
                "evidence_refs": signal.evidence_refs,
            }
            for signal in evidence_bundle.signals
        ],
        "evidence_refs": evidence_refs_from_bundle(evidence_bundle),
    }


def summarize_page_context(page_context: PageContext | None) -> dict[str, Any]:
    if page_context is None:
        return {"available": False}
    selected_resource = None
    if page_context.selected_resource is not None:
        selected_resource = page_context.selected_resource.model_dump()
    return {
        "available": True,
        "route": page_context.route,
        "locale": page_context.locale,
        "timezone": page_context.timezone,
        "user_role": page_context.user_role,
        "selected_resource": selected_resource,
        "visible_fields": page_context.visible_fields,
        "recent_actions": page_context.recent_actions,
    }


def capability_registry_context() -> dict[str, dict[str, Any]]:
    registry = build_default_capability_registry()
    grouped: dict[str, dict[str, Any]] = {}
    for capability in registry.for_domain("github"):
        grouped.setdefault(capability.domain, {})[capability.name] = {
            "description": capability.description,
            "required_entities": capability.required_entities,
            "permissions": capability.permissions,
            "result_schema": capability.result_schema,
            "examples": capability.examples,
        }
    return grouped


def summarize_retrieved_docs(user_message: str) -> dict[str, Any]:
    if not should_retrieve_docs(user_message):
        return {"available": False, "chunks": []}
    chunks = retrieve_docs(user_message)
    return {
        "available": len(chunks) > 0,
        "chunks": [chunk.model_dump() for chunk in chunks],
    }


def should_retrieve_docs(user_message: str) -> bool:
    normalized = user_message.lower()
    return any(
        keyword in normalized
        for keyword in [
            "什么是",
            "如何",
            "怎么",
            "文档",
            "docs",
            "架构",
            "排障",
            "troubleshooting",
            "tool layer",
            "github 能力层",
        ]
    )
