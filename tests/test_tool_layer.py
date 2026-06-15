from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from threading import Thread
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
from dev_time_agent.tools import build_default_tool_registry


def setup_function() -> None:
    os.environ.pop("DEV_TIME_SERVER_INTERNAL_BASE_URL", None)
    configure_conversation_llm_for_tests(None)
    configure_session_memory_store_for_tests(InMemorySessionMemoryStore())
    configure_tool_registry_for_tests(None)


def test_agent_session_turn_reads_evidence_through_tool_when_bundle_is_absent() -> None:
    with fake_dev_time_server() as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
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
    assert body["current_node"] == "risk_analyst"
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
    assert {
        "node": "tool_executor",
        "title": "调用风险证据工具",
    } in body["trace_events"]


def test_agent_session_turn_reads_project_ci_and_pr_tools_for_status() -> None:
    from dev_time_agent.schemas import (
        AgentDraftResponse,
        AgentPlan,
        ResponseVerification,
    )
    from fake_agent_llm import FakeConversationLLM

    with fake_dev_time_server() as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(
            FakeConversationLLM(
                expected_user_message="介绍当前状态",
                plan=AgentPlan(
                    intent="project_status",
                    confidence=0.93,
                    needs_evidence=False,
                    needs_tools=True,
                    tool_names=[
                        "project_status.read",
                        "ci_checks.read",
                        "pull_request.read",
                    ],
                    answer_strategy="summarize_project_status_with_tools",
                    reasoning_summary="用户要当前状态，需要读取项目、CI 和 PR 工具。",
                    safety_notes=[],
                ),
                draft=AgentDraftResponse(
                    answer="当前 dev-time-server 为高风险，test 检查失败，相关 PR 为 #18。",
                    evidence_refs=[
                        "event_check-run-123",
                        "event_pull-request-18",
                    ],
                    suggested_actions=[],
                    reasoning_summary="基于项目状态、CI 和 PR 工具结果生成状态说明。",
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
                "message": "介绍当前状态",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "project_status.read",
        "ci_checks.read",
        "pull_request.read",
    ]
    assert body["evidence_refs"] == [
        "event_check-run-123",
        "event_pull-request-18",
    ]
    assert [
        step["tool_call"]["name"]
        for step in body["reasoning_trace"]
        if step["stage"] == "tool_call"
    ] == [
        "project_status.read",
        "ci_checks.read",
        "pull_request.read",
    ]


def test_agent_session_turn_creates_pending_action_suggestion_draft() -> None:
    from dev_time_agent.schemas import (
        AgentDraftResponse,
        AgentPlan,
        ResponseVerification,
    )
    from fake_agent_llm import FakeConversationLLM

    with fake_dev_time_server() as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(
            FakeConversationLLM(
                expected_user_message="生成 PR 评论草稿",
                plan=AgentPlan(
                    intent="draft_pr_comment",
                    confidence=0.91,
                    needs_evidence=False,
                    needs_tools=False,
                    tool_names=[],
                    answer_strategy="draft_pr_comment",
                    reasoning_summary="用户要求生成 PR 评论草稿。",
                    safety_notes=["write_action_requires_approval"],
                ),
                draft=AgentDraftResponse(
                    answer="已生成 PR 评论草稿，请确认后发布。",
                    evidence_refs=["event_check-run-123"],
                    suggested_actions=[
                        {
                            "action_type": "pr_comment",
                            "target_ref": "pull_request:18",
                            "draft_body": "go test 失败阻塞交付，请先修复后再继续合并。",
                            "evidence_refs": ["event_check-run-123"],
                            "required_permission": "pull_request:write",
                        }
                    ],
                    reasoning_summary="生成待确认 PR 评论草稿。",
                    confidence=0.89,
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
                "message": "生成 PR 评论草稿",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_request"]["status"] == "pending"
    assert body["approval_request"]["actions"][0]["action_suggestion_id"] == (
        "action_tool_123"
    )
    assert body["tool_calls"][-1]["name"] == "action_suggestion.create"
    assert body["tool_calls"][-1]["status"] == "succeeded"
    assert body["tool_calls"][-1]["evidence_refs"] == ["event_check-run-123"]
    assert any(
        step["stage"] == "tool_call"
        and step["tool_call"]["name"] == "action_suggestion.create"
        for step in body["reasoning_trace"]
    )


def test_agent_session_turn_normalizes_incomplete_action_draft() -> None:
    from dev_time_agent.schemas import (
        AgentDraftResponse,
        AgentPlan,
        ResponseVerification,
    )
    from fake_agent_llm import FakeConversationLLM

    with fake_dev_time_server() as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(
            FakeConversationLLM(
                expected_user_message="生成 PR 评论草稿",
                plan=AgentPlan(
                    intent="draft_pr_comment",
                    confidence=0.91,
                    needs_evidence=False,
                    needs_tools=False,
                    tool_names=[],
                    answer_strategy="draft_pr_comment",
                    reasoning_summary="用户要求生成 PR 评论草稿。",
                    safety_notes=["write_action_requires_approval"],
                ),
                draft=AgentDraftResponse(
                    answer="PR #18 的 go test 失败，阻塞进度，请修复。",
                    evidence_refs=["event_check-run-123"],
                    suggested_actions=[
                        {
                            "target_ref": "pull_request:18",
                            "draft_body": "PR #18 的 go test 失败，阻塞进度，请修复。",
                            "evidence_refs": ["event_check-run-123"],
                        }
                    ],
                    reasoning_summary="生成待确认 PR 评论草稿。",
                    confidence=0.89,
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
                "message": "生成 PR 评论草稿",
            },
        )

    assert response.status_code == 200
    body = response.json()
    action = body["approval_request"]["actions"][0]
    assert action["action_type"] == "pr_comment"
    assert action["required_permission"] == "pull_request:write"
    assert action["action_suggestion_id"] == "action_tool_123"


def test_agent_session_turn_lists_github_repositories_through_fallback_tools() -> None:
    from fake_agent_llm import fake_dev_time_server as fake_github_server

    with fake_github_server(github_connected=True) as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1001/turns",
            json={
                "conversation_id": "conversation_project_repo_1001",
                "project_id": "project_repo_1001",
                "risk_assessment_id": "risk_project_repo_1001",
                "message": "查看我的 github 所有项目",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "github_repository_list"
    assert body["current_node"] == "github_repository_reporter"
    assert "henry-insomniac/dev-time-server" in body["agent_response"]
    assert "henry-insomniac/dev-time-agent" in body["agent_response"]
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "github.auth.status",
        "github.repos.list",
    ]
    assert "评估当前风险" not in body["agent_response"]


def test_agent_session_turn_lists_repository_pull_requests_through_fallback_tools() -> (
    None
):
    from fake_agent_llm import fake_dev_time_server as fake_github_server

    with fake_github_server(github_connected=True) as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1001/turns",
            json={
                "conversation_id": "conversation_project_repo_1001",
                "project_id": "project_repo_1001",
                "risk_assessment_id": "risk_project_repo_1001",
                "message": "查看 dev-time-agent 的 PR",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "github_pull_requests_list"
    assert body["current_node"] == "github_pull_request_reporter"
    assert "PR #18" in body["agent_response"]
    assert "Add GitHub tool layer" in body["agent_response"]
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "github.repos.list",
        "github.pull_requests.list",
    ]
    assert "评估当前风险" not in body["agent_response"]


def test_agent_session_turn_lists_repository_issues_through_fallback_tools() -> None:
    from fake_agent_llm import fake_dev_time_server as fake_github_server

    with fake_github_server(github_connected=True) as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1001/turns",
            json={
                "conversation_id": "conversation_project_repo_1001",
                "project_id": "project_repo_1001",
                "risk_assessment_id": "risk_project_repo_1001",
                "message": "查看 dev-time-agent 的 issue",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "github_issues_list"
    assert body["current_node"] == "github_issue_reporter"
    assert "Issue #42" in body["agent_response"]
    assert "Add issue reader" in body["agent_response"]
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "github.repos.list",
        "github.issues.list",
    ]
    assert "评估当前风险" not in body["agent_response"]


def test_agent_session_turn_lists_repository_checks_through_fallback_tools() -> None:
    from fake_agent_llm import fake_dev_time_server as fake_github_server

    with fake_github_server(github_connected=True) as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1001/turns",
            json={
                "conversation_id": "conversation_project_repo_1001",
                "project_id": "project_repo_1001",
                "risk_assessment_id": "risk_project_repo_1001",
                "message": "查看 dev-time-agent 的 CI",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "github_checks_list"
    assert body["current_node"] == "github_check_reporter"
    assert "test" in body["agent_response"]
    assert "failure" in body["agent_response"]
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "github.repos.list",
        "github.checks.list",
    ]
    assert "评估当前风险" not in body["agent_response"]


@contextmanager
def fake_dev_time_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path == "/internal/action-suggestions":
                self.send_json(
                    {
                        "id": "action_tool_123",
                        "project_id": "project_repo_1001",
                        "action_type": "pr_comment",
                        "status": "pending_user_confirmation",
                        "target_ref": "pull_request:18",
                        "draft_body": "go test 失败阻塞交付，请先修复后再继续合并。",
                        "evidence_refs": ["event_check-run-123"],
                    }
                )
                return

            self.send_response(404)
            self.end_headers()

        def do_GET(self) -> None:
            if self.path == "/internal/risk-assessments/risk_123/project-status":
                self.send_json(
                    {
                        "project": {
                            "id": "project_repo_1001",
                            "name": "dev-time-server",
                            "risk_score": 76,
                            "risk_level": "high",
                        },
                        "assessment": {
                            "id": "risk_123",
                            "project_id": "project_repo_1001",
                            "score": 76,
                            "level": "high",
                            "trend": "up",
                        },
                        "top_risk_reason": "go test failed",
                        "evidence_refs": ["event_check-run-123"],
                    }
                )
                return

            if self.path == "/internal/risk-assessments/risk_123/ci-checks":
                self.send_json(
                    {
                        "checks": [
                            {
                                "evidence_ref": "event_check-run-123",
                                "name": "test",
                                "status": "completed",
                                "conclusion": "failure",
                                "url": "https://github.test/actions/runs/421",
                            }
                        ]
                    }
                )
                return

            if self.path == "/internal/risk-assessments/risk_123/pull-requests":
                self.send_json(
                    {
                        "pull_requests": [
                            {
                                "evidence_ref": "event_pull-request-18",
                                "number": 18,
                                "title": "Add agent tool layer",
                                "state": "open",
                                "url": "https://github.test/pull/18",
                            }
                        ]
                    }
                )
                return

            if self.path == "/internal/risk-assessments/risk_123/evidence-bundle":
                self.send_json(
                    {
                        "project": {
                            "id": "project_repo_1001",
                            "name": "dev-time-server",
                            "risk_score": 76,
                            "risk_level": "high",
                        },
                        "assessment": {
                            "id": "risk_123",
                            "project_id": "project_repo_1001",
                            "score": 76,
                            "level": "high",
                            "trend": "up",
                        },
                        "signals": [
                            {
                                "id": "signal_123",
                                "project_id": "project_repo_1001",
                                "category": "ci",
                                "severity": 80,
                                "reason": "go test failed",
                                "evidence_refs": ["event_check-run-123"],
                            }
                        ],
                        "events": [],
                        "allowed_actions": ["pr_comment"],
                    }
                )
                return

            self.send_response(404)
            self.end_headers()

        def send_json(self, payload: dict[str, Any]) -> None:
            import json

            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
