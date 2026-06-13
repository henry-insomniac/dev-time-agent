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
    ) -> None:
        self.expected_user_message = expected_user_message
        self.plan = plan
        self.draft = draft
        self.verification = verification

    def plan_turn(self, context: dict) -> AgentPlan:
        assert context["user_message"] == self.expected_user_message
        assert "风险解释" in context["capabilities"]
        assert "不能编造证据" in context["boundaries"]
        return self.plan

    def generate_response(
        self,
        context: dict,
        plan: AgentPlan,
    ) -> AgentDraftResponse:
        if plan.needs_evidence:
            assert context["evidence_summary"]["available"] is True
            assert "event_check-run-123" in context["evidence_summary"][
                "evidence_refs"
            ]
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
def fake_dev_time_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
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
