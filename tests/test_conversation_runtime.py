from dev_time_agent.conversation import answer_conversation_turn
from dev_time_agent.schemas import ConversationTurnRequest, EvidenceBundle


def test_conversation_runtime_handles_greeting_without_risk_evidence() -> None:
    response = answer_conversation_turn(
        ConversationTurnRequest(
            conversation_id="conversation_project_repo_1001",
            project_id="project_repo_1001",
            risk_assessment_id="risk_project_repo_1001",
            message="你好",
        ),
        evidence_bundle(),
    )

    assert response.intent == "smalltalk"
    assert "你好" in response.agent_response
    assert response.evidence_refs == []


def test_conversation_runtime_introduces_itself_without_risk_evidence() -> None:
    response = answer_conversation_turn(
        ConversationTurnRequest(
            conversation_id="conversation_project_repo_1001",
            project_id="project_repo_1001",
            risk_assessment_id="risk_project_repo_1001",
            message="介绍你自己",
        ),
        evidence_bundle(),
    )

    assert response.intent == "self_intro"
    assert "Dev Time Agent" in response.agent_response
    assert "项目风险" in response.agent_response
    assert response.evidence_refs == []


def test_conversation_runtime_explains_risk_with_evidence_refs() -> None:
    response = answer_conversation_turn(
        ConversationTurnRequest(
            conversation_id="conversation_project_repo_1001",
            project_id="project_repo_1001",
            risk_assessment_id="risk_project_repo_1001",
            message="为什么这是高风险？",
        ),
        evidence_bundle(),
    )

    assert response.intent == "risk_explain"
    assert "test failed" in response.agent_response
    assert response.evidence_refs == ["event_check-run-1"]


def test_conversation_runtime_routes_action_plan_requests() -> None:
    response = answer_conversation_turn(
        ConversationTurnRequest(
            conversation_id="conversation_project_repo_1001",
            project_id="project_repo_1001",
            risk_assessment_id="risk_project_repo_1001",
            message="给我下一步行动计划",
        ),
        evidence_bundle(),
    )

    assert response.intent == "action_plan"
    assert "行动计划" in response.agent_response
    assert response.evidence_refs == ["event_check-run-1"]


def test_conversation_runtime_clarifies_ambiguous_requests_without_risk_evidence() -> None:
    response = answer_conversation_turn(
        ConversationTurnRequest(
            conversation_id="conversation_project_repo_1001",
            project_id="project_repo_1001",
            risk_assessment_id="risk_project_repo_1001",
            message="你怎么看",
        ),
        evidence_bundle(),
    )

    assert response.intent == "clarify"
    assert "当前风险原因" not in response.agent_response
    assert "test failed" not in response.agent_response
    assert "你想让我" in response.agent_response
    assert response.evidence_refs == []


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
