from dev_time_agent.schemas import AgentArtifact, AgentJob, EvidenceBundle


def run_risk_scout(job: AgentJob, bundle: EvidenceBundle) -> AgentArtifact:
    if not bundle.signals:
        return AgentArtifact(
            job_id=job.job_id,
            project_id=job.project_id,
            risk_assessment_id=job.risk_assessment_id,
            agent_type=job.agent_type,
            status="succeeded",
            summary=f"{bundle.project.name} has no active risk signals.",
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
            f"{bundle.project.name} is {bundle.assessment.level} risk because "
            f"{highest_signal.reason}"
        ),
        evidence_refs=highest_signal.evidence_refs,
    )
