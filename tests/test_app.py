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


def test_conversation_intent_endpoint_does_not_require_evidence_bundle() -> None:
    client = TestClient(app)

    response = client.post(
        "/conversation/intent",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "missing-risk",
            "message": "你怎么看",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "intent": "clarify",
        "confidence": 0.35,
        "requires_evidence": False,
        "requires_tool": False,
        "requires_approval": False,
        "clarifying_question": "你想让我评估当前风险、解释证据，还是生成下一步行动计划？",
    }


def test_agent_session_turn_reports_project_status_through_graph() -> None:
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_project_repo_1001/turns",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "介绍当前状态",
            "evidence_bundle": evidence_bundle().model_dump(),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session_project_repo_1001",
        "conversation_id": "conversation_project_repo_1001",
        "user_message": "介绍当前状态",
        "agent_response": (
            "当前项目 dev-time 处于高风险状态，风险分 70。"
            "主要阻塞：test failed and is blocking progress."
        ),
        "intent": "project_status",
        "confidence": 0.9,
        "evidence_refs": ["event_check-run-1"],
        "current_node": "status_reporter",
        "trace_events": [
            {
                "node": "intent_router",
                "title": "识别为项目状态查询",
            },
            {
                "node": "context_loader",
                "title": "加载风险证据",
            },
            {
                "node": "status_reporter",
                "title": "生成项目状态回复",
            },
        ],
        "tool_calls": [],
        "approval_request": None,
    }


def test_legacy_conversation_turn_uses_graph_for_project_status() -> None:
    client = TestClient(app)

    response = client.post(
        "/conversation/turn",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "介绍当前状态",
            "evidence_bundle": evidence_bundle().model_dump(),
        },
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "project_status"
    assert "当前项目 dev-time 处于高风险状态" in response.json()["agent_response"]
    assert response.json()["evidence_refs"] == ["event_check-run-1"]


def test_agent_session_turn_explains_how_to_use_agent() -> None:
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_project_repo_1001/turns",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "怎么认识你",
        },
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "self_intro"
    assert response.json()["current_node"] == "self_intro_responder"
    assert "Dev Time Agent" in response.json()["agent_response"]
    assert "当前风险" not in response.json()["agent_response"]
    assert response.json()["evidence_refs"] == []


def test_agent_session_turn_explains_risk_through_graph() -> None:
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_project_repo_1001/turns",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "为什么这是高风险？",
            "evidence_bundle": evidence_bundle().model_dump(),
        },
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "risk_explain"
    assert response.json()["current_node"] == "risk_analyst"
    assert "当前风险原因" in response.json()["agent_response"]
    assert "test failed and is blocking progress." in response.json()["agent_response"]
    assert response.json()["evidence_refs"] == ["event_check-run-1"]


def test_agent_session_turn_plans_next_action_through_graph() -> None:
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_project_repo_1001/turns",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "给我下一步行动计划",
            "evidence_bundle": evidence_bundle().model_dump(),
        },
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "action_plan"
    assert response.json()["current_node"] == "planner"
    assert "行动计划" in response.json()["agent_response"]
    assert "test failed and is blocking progress." in response.json()["agent_response"]
    assert response.json()["evidence_refs"] == ["event_check-run-1"]


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
