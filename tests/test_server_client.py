from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

from dev_time_agent.client import HTTPServerClient
from dev_time_agent.schemas import ActionSuggestion, AgentArtifact


def test_http_server_client_claims_fetches_evidence_and_completes_job() -> None:
    state: dict[str, Any] = {"complete_payload": None}

    with fake_dev_time_server(state) as base_url:
        client = HTTPServerClient(base_url)

        job = client.claim_next_agent_job()
        assert job is not None
        assert job.job_id == "job_123"

        evidence_bundle = client.get_evidence_bundle(job.risk_assessment_id)
        assert evidence_bundle.project.name == "dev-time-server"
        assert evidence_bundle.signals[0].evidence_refs == ["event_check-run-123"]

        llm_provider = client.get_llm_provider_config()
        assert llm_provider.provider == "openai"
        assert llm_provider.base_url == "http://127.0.0.1:11434/v1"
        assert llm_provider.model == "gpt-4.1"
        assert llm_provider.api_key == "sk-test"

        client.complete_agent_job(
            AgentArtifact(
                job_id=job.job_id,
                project_id=job.project_id,
                risk_assessment_id=job.risk_assessment_id,
                agent_type=job.agent_type,
                status="succeeded",
                summary="PR #18 is blocked by a failing go test check.",
                evidence_refs=["event_check-run-123"],
                action_suggestions=[
                    ActionSuggestion(
                        action_type="pr_comment",
                        target_ref="pull_request:18",
                        draft_body="Please fix go test before review.",
                        reason="CI is failing.",
                        evidence_refs=["event_check-run-123"],
                        required_permission="pull_request:write",
                    )
                ],
            )
        )

    assert state["complete_payload"] == {
        "summary": "PR #18 is blocked by a failing go test check.",
        "evidence_refs": ["event_check-run-123"],
        "model": "deterministic",
        "prompt_version": "dev-time-agent@v1",
        "action_suggestions": [
            {
                "action_type": "pr_comment",
                "target_ref": "pull_request:18",
                "draft_body": "Please fix go test before review.",
                "evidence_refs": ["event_check-run-123"],
            }
        ],
    }


@contextmanager
def fake_dev_time_server(state: dict[str, Any]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path == "/internal/agent-jobs/claim":
                self.send_json(
                    {
                        "job_id": "job_123",
                        "project_id": "project_123",
                        "risk_assessment_id": "risk_123",
                        "agent_type": "pr_doctor",
                        "trigger": "manual_refresh",
                    }
                )
                return

            if self.path == "/internal/agent-jobs/job_123/complete":
                state["complete_payload"] = self.read_json()
                self.send_json({"status": "succeeded"})
                return

            self.send_response(404)
            self.end_headers()

        def do_GET(self) -> None:
            if self.path == "/internal/risk-assessments/risk_123/evidence-bundle":
                self.send_json(
                    {
                        "project": {
                            "id": "project_123",
                            "name": "dev-time-server",
                            "risk_score": 76,
                            "risk_level": "high",
                        },
                        "assessment": {
                            "id": "risk_123",
                            "project_id": "project_123",
                            "score": 76,
                            "level": "high",
                            "trend": "up",
                        },
                        "signals": [
                            {
                                "id": "signal_123",
                                "project_id": "project_123",
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

            if self.path == "/internal/llm-provider-config":
                self.send_json(
                    {
                        "provider": "openai",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "model": "gpt-4.1",
                        "api_key": "sk-test",
                    }
                )
                return

            self.send_response(404)
            self.end_headers()

        def read_json(self) -> Any:
            import json

            content_length = int(self.headers["Content-Length"])
            return json.loads(self.rfile.read(content_length))

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
