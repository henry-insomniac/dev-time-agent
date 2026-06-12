from fastapi.testclient import TestClient

from dev_time_agent.app import app
from dev_time_agent.schemas import EvidenceBundle


def test_conversation_turn_endpoint_uses_runtime() -> None:
    client = TestClient(app)

    response = client.post(
        "/conversation/turn",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "你好",
            "evidence_bundle": evidence_bundle().model_dump(),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation_project_repo_1001",
        "user_message": "你好",
        "agent_response": (
            "你好，我是 Dev Time Agent。你可以让我解释当前风险、查看证据，"
            "或生成下一步行动计划。"
        ),
        "evidence_refs": [],
        "intent": "smalltalk",
    }


def evidence_bundle() -> EvidenceBundle:
    return EvidenceBundle.model_validate(
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
