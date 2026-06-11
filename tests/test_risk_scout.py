from dev_time_agent.schemas import AgentJob, EvidenceBundle
from dev_time_agent.workflows.risk_scout import run_risk_scout


def test_risk_scout_explains_highest_risk_with_evidence_refs() -> None:
    job = AgentJob(
        job_id="job_123",
        project_id="project_repo_1001",
        risk_assessment_id="risk_project_repo_1001",
        agent_type="risk_scout",
        trigger="risk.assessment.created",
    )
    bundle = EvidenceBundle.model_validate(
        {
            "project": {
                "id": "project_repo_1001",
                "name": "dev-time",
                "risk_score": 70,
                "risk_level": "high",
            },
            "assessment": {
                "id": "risk_project_repo_1001",
                "project_id": "project_repo_1001",
                "score": 70,
                "level": "high",
                "trend": "new",
            },
            "signals": [
                {
                    "id": "signal_event_check-run-1",
                    "project_id": "project_repo_1001",
                    "category": "blocked",
                    "severity": 70,
                    "reason": "test failed and is blocking progress.",
                    "evidence_refs": ["event_check-run-1"],
                }
            ],
            "events": [
                {
                    "id": "event_check-run-1",
                    "event_type": "check_run",
                    "payload": {"check_run": {"conclusion": "failure"}},
                }
            ],
            "allowed_actions": ["create_issue", "create_pr_comment"],
        }
    )

    artifact = run_risk_scout(job, bundle)

    assert artifact.status == "succeeded"
    assert artifact.agent_type == "risk_scout"
    assert "当前为高风险" in artifact.summary
    assert "test failed" in artifact.summary
    assert artifact.evidence_refs == ["event_check-run-1"]
