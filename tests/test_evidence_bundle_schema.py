from dev_time_agent.schemas import EvidenceBundle


def test_evidence_bundle_schema_accepts_server_payload() -> None:
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

    assert bundle.assessment.level == "high"
    assert bundle.signals[0].evidence_refs == ["event_check-run-1"]
    assert bundle.events[0].payload["check_run"]["conclusion"] == "failure"
