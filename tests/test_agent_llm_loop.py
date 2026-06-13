import os
from typing import Any

from fastapi.testclient import TestClient

from dev_time_agent.app import app
from dev_time_agent.client import HTTPServerClient
from dev_time_agent.graph_runtime import (
    configure_conversation_llm_for_tests,
    configure_session_memory_store_for_tests,
    configure_tool_registry_for_tests,
)
from dev_time_agent.memory import InMemorySessionMemoryStore
from dev_time_agent.schemas import AgentDraftResponse, AgentPlan, ResponseVerification
from dev_time_agent.tools import build_default_tool_registry
from fake_agent_llm import (
    FakeConversationLLM,
    fake_dev_time_server,
    fake_llm_provider_server,
    fake_openai_compatible_conversation_llm,
)


def setup_function() -> None:
    os.environ.pop("DEV_TIME_SERVER_INTERNAL_BASE_URL", None)
    configure_session_memory_store_for_tests(InMemorySessionMemoryStore())
    configure_tool_registry_for_tests(None)
    configure_conversation_llm_for_tests(None)


def test_agent_session_turn_explains_how_to_test_agent_through_llm_loop() -> None:
    configure_conversation_llm_for_tests(
        FakeConversationLLM(
            expected_user_message="如何测试你",
            plan=AgentPlan(
                intent="capability_explain",
                confidence=0.93,
                needs_evidence=False,
                needs_tools=False,
                tool_names=[],
                answer_strategy="explain_agent_capabilities_with_examples",
                reasoning_summary="用户在询问如何测试 Agent 能力，不是在询问当前风险。",
                safety_notes=[],
            ),
            draft=AgentDraftResponse(
                answer=(
                    "我是 Dev Time 的项目风险 Agent。你可以这样测试我：\n"
                    "- 风险解释：为什么这个项目是高风险？\n"
                    "- 证据追踪：证据是什么？\n"
                    "- 行动计划：下一步先做什么？\n"
                    "- 草稿生成：帮我生成 PR 评论草稿。"
                ),
                evidence_refs=[],
                suggested_actions=[],
                reasoning_summary="已按能力说明回答，并给出测试问题。",
                confidence=0.92,
            ),
            verification=ResponseVerification(
                passed=True,
                issues=[],
                rewrite_instruction="",
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_project_repo_1001/turns",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "如何测试你",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "capability_explain"
    assert "你可以这样测试我" in body["agent_response"]
    assert "为什么这个项目是高风险" in body["agent_response"]
    assert "当前风险原因" not in body["agent_response"]
    assert body["evidence_refs"] == []
    assert body["current_node"] == "response_verifier"
    assert {"node": "context_assembler", "title": "组装 Agent 上下文"} in body[
        "trace_events"
    ]
    assert {"node": "llm_planner", "title": "完成 LLM 规划"} in body["trace_events"]
    assert {"node": "response_generator", "title": "生成 LLM 回复"} in body[
        "trace_events"
    ]
    assert {"node": "response_verifier", "title": "审核回复通过"} in body[
        "trace_events"
    ]


def test_agent_session_turn_blocks_off_topic_llm_response() -> None:
    configure_conversation_llm_for_tests(
        FakeConversationLLM(
            expected_user_message="如何测试你",
            plan=AgentPlan(
                intent="capability_explain",
                confidence=0.91,
                needs_evidence=False,
                needs_tools=False,
                tool_names=[],
                answer_strategy="explain_agent_capabilities_with_examples",
                reasoning_summary="用户在询问如何测试 Agent。",
                safety_notes=[],
            ),
            draft=AgentDraftResponse(
                answer="当前风险原因：go test failed and is blocking progress.",
                evidence_refs=[],
                suggested_actions=[],
                reasoning_summary="错误地回答成风险解释。",
                confidence=0.6,
            ),
            verification=ResponseVerification(
                passed=False,
                issues=["off_topic"],
                rewrite_instruction=(
                    "我可以帮你测试风险解释、证据追踪、行动计划和草稿生成。"
                    "例如你可以问：为什么这个项目是高风险？"
                ),
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_project_repo_1001/turns",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "如何测试你",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "capability_explain"
    assert "可以帮你测试风险解释" in body["agent_response"]
    assert "当前风险原因" not in body["agent_response"]
    assert {"node": "response_verifier", "title": "审核回复未通过"} in body[
        "trace_events"
    ]


def test_agent_session_turn_executes_planned_read_tool_before_generating_response() -> None:
    with fake_dev_time_server() as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(
            FakeConversationLLM(
                expected_user_message="为什么这是高风险？",
                plan=AgentPlan(
                    intent="risk_explain",
                    confidence=0.94,
                    needs_evidence=True,
                    needs_tools=True,
                    tool_names=["risk_evidence.read"],
                    answer_strategy="explain_risk_with_evidence",
                    reasoning_summary="用户要求解释高风险，需要读取风险证据。",
                    safety_notes=[],
                ),
                draft=AgentDraftResponse(
                    answer="当前高风险来自 go test failed，正在阻塞交付。",
                    evidence_refs=["event_check-run-123"],
                    suggested_actions=[],
                    reasoning_summary="基于风险证据生成解释。",
                    confidence=0.9,
                ),
                verification=ResponseVerification(
                    passed=True,
                    issues=[],
                    rewrite_instruction="",
                ),
            )
        )
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1001/turns",
            json={
                "conversation_id": "conversation_project_repo_1001",
                "project_id": "project_repo_1001",
                "risk_assessment_id": "risk_123",
                "message": "为什么这是高风险？",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "risk_explain"
    assert "go test failed" in body["agent_response"]
    assert body["evidence_refs"] == ["event_check-run-123"]
    assert body["tool_calls"] == [
        {
            "name": "risk_evidence.read",
            "status": "succeeded",
            "input": {"risk_assessment_id": "risk_123"},
            "evidence_refs": ["event_check-run-123"],
        }
    ]
    assert {"node": "tool_executor", "title": "调用风险证据工具"} in body[
        "trace_events"
    ]


def test_agent_session_turn_uses_server_llm_provider_config(monkeypatch) -> None:
    llm_state: dict[str, Any] = {"requests": []}
    with (
        fake_openai_compatible_conversation_llm(llm_state) as llm_base_url,
        fake_llm_provider_server(llm_base_url) as server_base_url,
    ):
        monkeypatch.setenv("DEV_TIME_SERVER_INTERNAL_BASE_URL", server_base_url)
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1001/turns",
            json={
                "conversation_id": "conversation_project_repo_1001",
                "project_id": "project_repo_1001",
                "risk_assessment_id": "risk_project_repo_1001",
                "message": "如何测试你",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "capability_explain"
    assert "你可以这样测试我" in body["agent_response"]
    assert body["current_node"] == "response_verifier"
    assert [request["payload"]["model"] for request in llm_state["requests"]] == [
        "deepseek-chat",
        "deepseek-chat",
        "deepseek-chat",
    ]
    assert {request["authorization"] for request in llm_state["requests"]} == {
        "Bearer sk-deepseek-test"
    }


def test_agent_session_turn_requests_approval_for_suggested_write_actions() -> None:
    configure_conversation_llm_for_tests(
        FakeConversationLLM(
            expected_user_message="帮我生成 PR 评论",
            plan=AgentPlan(
                intent="draft_pr_comment",
                confidence=0.91,
                needs_evidence=False,
                needs_tools=False,
                tool_names=[],
                answer_strategy="draft_comment_requires_user_approval",
                reasoning_summary="用户要求生成 PR 评论草稿，写入前需要确认。",
                safety_notes=["write_action_requires_approval"],
            ),
            draft=AgentDraftResponse(
                answer="我可以生成 PR 评论草稿，但发布前需要你确认。",
                evidence_refs=["event_check-run-123"],
                suggested_actions=[
                    {
                        "action_type": "pr_comment",
                        "target_ref": "pull_request:18",
                        "draft_body": "go test 失败阻塞交付，请先修复后再继续合并。",
                        "reason": "测试失败是当前交付阻塞。",
                        "evidence_refs": ["event_check-run-123"],
                        "required_permission": "pull_request:write",
                    }
                ],
                reasoning_summary="只返回待确认草稿，不直接执行。",
                confidence=0.88,
            ),
            verification=ResponseVerification(
                passed=True,
                issues=[],
                rewrite_instruction="",
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_project_repo_1001/turns",
        json={
            "conversation_id": "conversation_project_repo_1001",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "帮我生成 PR 评论",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_request"] == {
        "status": "pending",
        "reason": "LLM 生成了需要用户确认的写操作。",
        "actions": [
            {
                "action_type": "pr_comment",
                "target_ref": "pull_request:18",
                "draft_body": "go test 失败阻塞交付，请先修复后再继续合并。",
                "reason": "测试失败是当前交付阻塞。",
                "evidence_refs": ["event_check-run-123"],
                "required_permission": "pull_request:write",
            }
        ],
    }
    assert {"node": "approval_gate", "title": "等待用户确认写操作"} in body[
        "trace_events"
    ]
