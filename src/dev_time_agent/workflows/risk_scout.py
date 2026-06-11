from dev_time_agent.schemas import AgentArtifact, AgentJob, EvidenceBundle


def run_risk_scout(job: AgentJob, bundle: EvidenceBundle) -> AgentArtifact:
    if not bundle.signals:
        return AgentArtifact(
            job_id=job.job_id,
            project_id=job.project_id,
            risk_assessment_id=job.risk_assessment_id,
            agent_type=job.agent_type,
            status="succeeded",
            summary=f"{bundle.project.name} 暂无活跃风险信号。",
            evidence_refs=[],
        )

    highest_signal = max(bundle.signals, key=lambda signal: signal.severity)
    return AgentArtifact(
        job_id=job.job_id,
        project_id=job.project_id,
        risk_assessment_id=job.risk_assessment_id,
        agent_type=job.agent_type,
        status="succeeded",
        summary=(
            f"{bundle.project.name} 当前为{risk_level_label(bundle.assessment.level)}风险，"
            f"原因是：{highest_signal.reason}"
        ),
        evidence_refs=highest_signal.evidence_refs,
    )


def risk_level_label(level: str) -> str:
    labels = {
        "stable": "稳定",
        "low": "低",
        "medium": "中",
        "high": "高",
    }
    return labels.get(level, level)
