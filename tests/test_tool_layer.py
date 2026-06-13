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
