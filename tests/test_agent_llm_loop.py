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


def test_agent_session_turn_checks_github_authorization_before_answering_repo_access() -> None:
    with fake_dev_time_server() as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(
            FakeConversationLLM(
                expected_user_message="你能看到我的 GitHub 项目吗",
                plan=AgentPlan(
                    intent="github_access_status",
                    confidence=0.95,
                    needs_evidence=False,
                    needs_tools=True,
                    tool_names=["github.auth.status"],
                    answer_strategy="check_github_auth_before_explaining_access",
                    reasoning_summary="用户询问 GitHub 可见范围，需要先检查授权状态。",
                    safety_notes=["github_access_requires_authorization"],
                ),
                draft=AgentDraftResponse(
                    answer=(
                        "当前还没有 GitHub 授权，所以我不能查看你的 GitHub 仓库。"
                        "连接 GitHub 后，我可以读取授权范围内的仓库、PR、CI 检查和 issue。"
                    ),
                    evidence_refs=[],
                    suggested_actions=[],
                    reasoning_summary="基于 GitHub 授权状态回答能力边界。",
                    confidence=0.93,
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
                "message": "你能看到我的 GitHub 项目吗",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "github_access_status"
    assert "当前还没有 GitHub 授权" in body["agent_response"]
    assert body["tool_calls"] == [
        {
            "name": "github.auth.status",
            "status": "succeeded",
            "input": {},
            "evidence_refs": [],
        }
    ]
    assert {"node": "tool_executor", "title": "检查 GitHub 授权"} in body[
        "trace_events"
    ]


def test_agent_session_turn_lists_authorized_github_repositories() -> None:
    with fake_dev_time_server(github_connected=True) as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(
            FakeConversationLLM(
                expected_user_message="你能看到我的 GitHub 项目吗",
                plan=AgentPlan(
                    intent="github_repository_list",
                    confidence=0.96,
                    needs_evidence=False,
                    needs_tools=True,
                    tool_names=["github.auth.status", "github.repos.list"],
                    answer_strategy="list_authorized_github_repositories",
                    reasoning_summary="用户询问 GitHub 项目，需要读取授权仓库列表。",
                    safety_notes=[],
                ),
                draft=AgentDraftResponse(
                    answer=(
                        "可以。我当前能看到你授权给 Dev Time 的仓库："
                        "henry-insomniac/dev-time-server、henry-insomniac/dev-time-agent。"
                    ),
                    evidence_refs=[],
                    suggested_actions=[],
                    reasoning_summary="基于 GitHub 仓库工具结果回答。",
                    confidence=0.94,
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
                "message": "你能看到我的 GitHub 项目吗",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "github_repository_list"
    assert "henry-insomniac/dev-time-server" in body["agent_response"]
    assert "henry-insomniac/dev-time-agent" in body["agent_response"]
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "github.auth.status",
        "github.repos.list",
    ]
    assert {"node": "tool_executor", "title": "列出 GitHub 仓库"} in body[
        "trace_events"
    ]


def test_agent_session_turn_corrects_llm_plan_when_github_access_needs_tools() -> None:
    class MisclassifyingGitHubAccessLLM:
        def plan_turn(self, context: dict) -> AgentPlan:
            return AgentPlan(
                intent="ordinary_chat",
                confidence=0.91,
                needs_evidence=False,
                needs_tools=False,
                tool_names=[],
                answer_strategy="answer_from_general_knowledge",
                reasoning_summary="误判为普通能力说明。",
                safety_notes=[],
            )

        def generate_response(
            self,
            context: dict,
            plan: AgentPlan,
        ) -> AgentDraftResponse:
            assert plan.intent == "github_repository_list"
            assert "github.auth.status" in context["tool_results"]
            assert "github.repos.list" in context["tool_results"]
            return AgentDraftResponse(
                answer=(
                    "可以。我当前能看到你授权给 Dev Time 的仓库："
                    "henry-insomniac/dev-time-server、henry-insomniac/dev-time-agent。"
                ),
                evidence_refs=[],
                suggested_actions=[],
                reasoning_summary="基于 GitHub 工具结果回答。",
                confidence=0.94,
            )

        def verify_response(
            self,
            context: dict,
            plan: AgentPlan,
            draft: AgentDraftResponse,
        ) -> ResponseVerification:
            return ResponseVerification(passed=True, issues=[], rewrite_instruction="")

    with fake_dev_time_server(github_connected=True) as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(MisclassifyingGitHubAccessLLM())
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1001/turns",
            json={
                "conversation_id": "conversation_project_repo_1001",
                "project_id": "project_repo_1001",
                "risk_assessment_id": "risk_project_repo_1001",
                "message": "你能看到我的 GitHub 项目吗",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "github_repository_list"
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "github.auth.status",
        "github.repos.list",
    ]


def test_agent_session_turn_returns_collapsible_reasoning_trace() -> None:
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
    reasoning_trace = body["reasoning_trace"]
    assert [step["stage"] for step in reasoning_trace] == [
        "context",
        "planning",
        "tool_call",
        "generation",
        "verification",
    ]
    assert reasoning_trace[1]["title"] == "识别用户意图"
    assert reasoning_trace[1]["summary"] == "用户要求解释高风险，需要读取风险证据。"
    assert reasoning_trace[1]["confidence"] == 0.94
    assert reasoning_trace[2]["tool_call"]["name"] == "risk_evidence.read"
    assert reasoning_trace[2]["evidence_refs"] == ["event_check-run-123"]
    assert reasoning_trace[4]["status"] == "completed"
    serialized_trace = str(reasoning_trace).lower()
    assert "chain-of-thought" not in serialized_trace
    assert "prompt" not in serialized_trace


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
    approval_steps = [
        step for step in body["reasoning_trace"] if step["stage"] == "approval"
    ]
    assert approval_steps == [
        {
            "stage": "approval",
            "title": "等待用户确认写操作",
            "summary": "检测到写操作草稿，用户确认前不会执行。",
            "status": "completed",
            "confidence": None,
            "evidence_refs": ["event_check-run-123"],
            "tool_call": None,
        }
    ]
