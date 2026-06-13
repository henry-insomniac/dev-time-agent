from typing import Any

from dev_time_agent.conversation import evidence_refs_from_bundle
from dev_time_agent.schemas import EvidenceBundle


CAPABILITIES = [
    "风险解释",
    "项目状态",
    "证据追踪",
    "行动计划",
    "PR/CI 排障",
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
]


def assemble_agent_context(
    *,
    user_message: str,
    project_id: str,
    risk_assessment_id: str,
    memory: dict[str, Any],
    evidence_bundle: EvidenceBundle | None,
    available_tools: list[str],
) -> dict[str, Any]:
    return {
        "agent_identity": "Dev Time 项目风险 Agent",
        "capabilities": CAPABILITIES,
        "boundaries": BOUNDARIES,
        "user_message": user_message,
        "project_id": project_id,
        "risk_assessment_id": risk_assessment_id,
        "session_memory": memory,
        "available_tools": available_tools,
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
