from dev_time_agent.schemas import AgentJob, EvidenceBundle
from dev_time_agent.workflows.pr_doctor import run_pr_doctor


def test_pr_doctor_generates_pr_comment_draft_for_failed_check() -> None:
    job = AgentJob(
        job_id="job_456",
        project_id="project_repo_1001",
        risk_assessment_id="risk_project_repo_1001",
        agent_type="pr_doctor",
        trigger="ci.failed",
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
                    "evidence_refs": ["event_check-run-1", "event_pr-18"],
                }
            ],
            "events": [
                {
                    "id": "event_check-run-1",
                    "event_type": "check_run",
                    "payload": {"check_run": {"conclusion": "failure", "name": "test"}},
                },
                {
                    "id": "event_pr-18",
                    "event_type": "pull_request",
                    "payload": {
                        "pull_request": {
                            "number": 18,
                            "title": "Add risk dashboard",
                            "html_url": "https://github.com/example/repo/pull/18",
                        }
                    },
                },
            ],
            "allowed_actions": ["create_pr_comment"],
        }
    )

    artifact = run_pr_doctor(job, bundle)

    assert artifact.status == "succeeded"
    assert artifact.action_suggestions
    suggestion = artifact.action_suggestions[0]
    assert suggestion.action_type == "pr_comment"
    assert suggestion.target_ref == "pull_request:18"
    assert "test" in suggestion.draft_body
    assert suggestion.evidence_refs == ["event_check-run-1", "event_pr-18"]
