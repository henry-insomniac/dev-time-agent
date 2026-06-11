from typing import Any

from dev_time_agent.schemas import (
    ActionSuggestion,
    AgentArtifact,
    AgentJob,
    EvidenceBundle,
    EvidenceEvent,
)


def run_pr_doctor(job: AgentJob, bundle: EvidenceBundle) -> AgentArtifact:
    failed_check = first_event(bundle.events, "check_run")
    pull_request = first_event(bundle.events, "pull_request")
    evidence_refs = related_evidence_refs(bundle)

    if failed_check is None or pull_request is None:
        return AgentArtifact(
            job_id=job.job_id,
            project_id=job.project_id,
            risk_assessment_id=job.risk_assessment_id,
            agent_type=job.agent_type,
            status="succeeded",
            summary="PR Doctor 没有找到足够的 PR 和 CI 证据，暂不生成行动草稿。",
            evidence_refs=evidence_refs,
        )

    check_name = nested_value(failed_check.payload, "check_run", "name") or "CI"
    pr_number = nested_value(pull_request.payload, "pull_request", "number")
    pr_title = nested_value(pull_request.payload, "pull_request", "title") or "this PR"

    suggestion = ActionSuggestion(
        action_type="pr_comment",
        target_ref=f"pull_request:{pr_number}",
        draft_body=(
            f"PR #{pr_number}（{pr_title}）当前的 {check_name} 检查失败。"
            "请先修复失败检查，再请求下一轮 Review。"
        ),
        reason="失败的 check run 正在阻塞 PR Review 进度。",
        evidence_refs=evidence_refs,
        required_permission="pull_request:write",
    )

    return AgentArtifact(
        job_id=job.job_id,
        project_id=job.project_id,
        risk_assessment_id=job.risk_assessment_id,
        agent_type=job.agent_type,
        status="succeeded",
        summary=f"PR #{pr_number} 被失败的 {check_name} 检查阻塞。",
        evidence_refs=evidence_refs,
        action_suggestions=[suggestion],
    )


def first_event(events: list[EvidenceEvent], event_type: str) -> EvidenceEvent | None:
    return next((event for event in events if event.event_type == event_type), None)


def related_evidence_refs(bundle: EvidenceBundle) -> list[str]:
    refs: list[str] = []
    for signal in bundle.signals:
        refs.extend(signal.evidence_refs)
    return list(dict.fromkeys(refs))


def nested_value(payload: dict[str, Any], *path: str) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
