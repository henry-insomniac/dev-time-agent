from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

from dev_time_agent.schemas import AgentDraftResponse, AgentPlan, ResponseVerification


class FakeConversationLLM:
    def __init__(
        self,
        *,
        expected_user_message: str,
        plan: AgentPlan,
        draft: AgentDraftResponse,
        verification: ResponseVerification,
        expected_page_context: dict | None = None,
    ) -> None:
        self.expected_user_message = expected_user_message
        self.plan = plan
        self.draft = draft
        self.verification = verification
        self.expected_page_context = expected_page_context

    def plan_turn(self, context: dict) -> AgentPlan:
        assert context["user_message"] == self.expected_user_message
        assert "风险解释" in context["capabilities"]
        assert "不能编造证据" in context["boundaries"]
        if self.expected_page_context is not None:
            assert context["page_context"] == self.expected_page_context
        return self.plan

    def generate_response(
        self,
        context: dict,
        plan: AgentPlan,
    ) -> AgentDraftResponse:
        if plan.needs_evidence:
            assert context["evidence_summary"]["available"] is True
            assert "event_check-run-123" in context["evidence_summary"]["evidence_refs"]
        return self.draft

    def verify_response(
        self,
        context: dict,
        plan: AgentPlan,
        draft: AgentDraftResponse,
    ) -> ResponseVerification:
        assert draft.answer != ""
        return self.verification


@contextmanager
def fake_dev_time_server(github_connected: bool = False) -> Iterator[str]:
    github_repositories = [
        {
            "id": "repo_1001",
            "github_id": 1001,
            "owner": "henry-insomniac",
            "name": "dev-time-server",
            "full_name": "henry-insomniac/dev-time-server",
            "project_id": "project_repo_1001",
        },
        {
            "id": "repo_1002",
            "github_id": 1002,
            "owner": "henry-insomniac",
            "name": "dev-time-agent",
            "full_name": "henry-insomniac/dev-time-agent",
            "project_id": "project_repo_1002",
        },
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/internal/github/auth-status":
                self.send_json(
                    {
                        "connected": github_connected,
                        "provider": "github_app",
                        "repositories": github_repositories if github_connected else [],
                        "permissions": (
                            ["metadata:read", "pull_requests:read", "checks:read"]
                            if github_connected
                            else []
                        ),
                    }
                )
                return

            if self.path == "/internal/github/repositories":
                self.send_json(
                    {"repositories": (github_repositories if github_connected else [])}
                )
                return

            if self.path == "/internal/github/repositories/repo_1002/pull-requests":
                self.send_json(
                    {
                        "pull_requests": [
                            {
                                "evidence_ref": "event_pull-request-12",
                                "number": 12,
                                "title": "Wire CI diagnostics",
                                "state": "open",
                                "url": (
                                    "https://github.test/"
                                    "henry-insomniac/dev-time-agent/pull/12"
                                ),
                            },
                            {
                                "evidence_ref": "event_pull-request-18",
                                "number": 18,
                                "title": "Add GitHub tool layer",
                                "state": "open",
                                "url": (
                                    "https://github.test/"
                                    "henry-insomniac/dev-time-agent/pull/18"
                                ),
                            }
                        ]
                    }
                )
                return

            if self.path == "/internal/github/repositories/repo_1002/issues":
                self.send_json(
                    {
                        "issues": [
                            {
                                "evidence_ref": "event_issue-42",
                                "number": 42,
                                "title": "Add issue reader",
                                "state": "open",
                                "url": (
                                    "https://github.test/"
                                    "henry-insomniac/dev-time-agent/issues/42"
                                ),
                            }
                        ]
                    }
                )
                return

            if self.path == "/internal/github/repositories/repo_1002/checks":
                self.send_json(
                    {
                        "checks": [
                            {
                                "evidence_ref": "event_check-run-12",
                                "run_id": 812,
                                "name": "eslint",
                                "status": "completed",
                                "conclusion": "failure",
                                "url": (
                                    "https://github.test/"
                                    "henry-insomniac/dev-time-agent/actions/runs/812"
                                ),
                            },
                            {
                                "evidence_ref": "event_check-run-421",
                                "run_id": 421,
                                "name": "test",
                                "status": "completed",
                                "conclusion": "failure",
                                "url": (
                                    "https://github.test/"
                                    "henry-insomniac/dev-time-agent/actions/runs/421"
                                ),
                            }
                        ]
                    }
                )
                return

            if (
                self.path
                == "/internal/github/repositories/repo_1002/checks/812/logs"
            ):
                self.send_json(
                    {
                        "run_id": 812,
                        "check_name": "eslint",
                        "conclusion": "failure",
                        "log_excerpt": (
                            "src/planner.ts:45:7 error 'draftPlan' is assigned "
                            "a value but never used no-unused-vars\n"
                            "src/router.ts:18:10 error 'route' is defined but "
                            "never used no-unused-vars\n"
                            "src/client.ts:11:3 error 'debug' is defined but "
                            "never used no-unused-vars"
                        ),
                        "evidence_refs": ["github_live_check_run_812_logs"],
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


@contextmanager
def fake_llm_provider_server(llm_base_url: str) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/internal/llm-provider-config":
                self.send_json(
                    {
                        "provider": "deepseek",
                        "base_url": llm_base_url,
                        "model": "deepseek-chat",
                        "api_key": "sk-deepseek-test",
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


@contextmanager
def fake_openai_compatible_conversation_llm(state: dict[str, Any]) -> Iterator[str]:
    responses = [
        {
            "intent": "capability_explain",
            "confidence": 0.94,
            "needs_evidence": False,
            "needs_tools": False,
            "tool_names": [],
            "answer_strategy": "explain_agent_capabilities_with_examples",
            "reasoning_summary": "用户询问如何测试 Agent 能力。",
            "safety_notes": [],
        },
        {
            "answer": (
                "我是 Dev Time 的项目风险 Agent。你可以这样测试我："
                "问我如何解释风险、追踪证据、生成行动计划。"
            ),
            "evidence_refs": [],
            "suggested_actions": [],
            "reasoning_summary": "按用户问题说明测试方式。",
            "confidence": 0.92,
        },
        {
            "passed": True,
            "issues": [],
            "rewrite_instruction": "",
        },
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/chat/completions":
                self.send_response(404)
                self.end_headers()
                return

            payload = self.read_json()
            index = len(state["requests"])
            state["requests"].append(
                {
                    "authorization": self.headers.get("Authorization"),
                    "payload": payload,
                }
            )
            self.send_json(
                {
                    "choices": [
                        {
                            "message": {
                                "content": self.dumps_json(responses[index]),
                            }
                        }
                    ]
                }
            )

        def read_json(self) -> Any:
            import json

            content_length = int(self.headers["Content-Length"])
            return json.loads(self.rfile.read(content_length))

        def dumps_json(self, payload: dict[str, Any]) -> str:
            import json

            return json.dumps(payload, ensure_ascii=False)

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
