import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

from dev_time_agent.schemas import (
    AgentArtifact,
    AgentJob,
    EvidenceBundle,
    EvidenceEvent,
    LLMProviderConfig,
    ProjectSummary,
    RiskAssessment,
    RiskSignal,
)
from dev_time_agent.worker import process_next_agent_job


def test_worker_runs_pr_doctor_with_openai_compatible_llm() -> None:
    llm_state: dict[str, Any] = {"request": None}

    with fake_openai_compatible_llm(llm_state) as llm_base_url:
        server = FakeLLMBackedServerClient(
            AgentJob(
                job_id="job_llm_123",
                project_id="project_123",
                risk_assessment_id="risk_123",
                agent_type="pr_doctor",
                trigger="manual_refresh",
            ),
            EvidenceBundle(
                project=ProjectSummary(
                    id="project_123",
                    name="dev-time-server",
                    risk_score=82,
                    risk_level="high",
                ),
                assessment=RiskAssessment(
                    id="risk_123",
                    project_id="project_123",
                    score=82,
                    level="high",
                    trend="up",
                ),
                signals=[
                    RiskSignal(
                        id="signal_123",
                        project_id="project_123",
                        category="ci",
                        severity=82,
                        reason="go test failed",
                        evidence_refs=["event_check-run-123", "event_pr-18"],
                    )
                ],
                events=[
                    EvidenceEvent(
                        id="event_check-run-123",
                        event_type="check_run",
                        payload={"check_run": {"name": "go test", "conclusion": "failure"}},
                    ),
                    EvidenceEvent(
                        id="event_pr-18",
                        event_type="pull_request",
                        payload={
                            "pull_request": {
                                "number": 18,
                                "title": "Add timeline",
                            }
                        },
                    ),
                ],
                allowed_actions=["pr_comment"],
            ),
            LLMProviderConfig(
                provider="deepseek",
                base_url=llm_base_url,
                model="deepseek-chat",
                api_key="sk-deepseek-test",
            ),
        )

        processed = process_next_agent_job(server)

    assert processed is True
    assert llm_state["request"]["path"] == "/chat/completions"
    assert llm_state["request"]["authorization"] == "Bearer sk-deepseek-test"
    assert llm_state["request"]["payload"]["model"] == "deepseek-chat"
    assert "event_check-run-123" in json.dumps(
        llm_state["request"]["payload"],
        ensure_ascii=False,
    )
    assert server.succeeded_artifact is not None
    assert server.succeeded_artifact.summary == "LLM 判断 PR #18 被 go test 阻塞。"
    assert server.succeeded_artifact.model == "deepseek:deepseek-chat"
    assert server.succeeded_artifact.prompt_version == "dev-time-agent-llm@v1"
    assert server.succeeded_artifact.action_suggestions[0].draft_body == (
        "请先修复 go test，再请求下一轮 Review。"
    )


class FakeLLMBackedServerClient:
    def __init__(
        self,
        job: AgentJob,
        evidence_bundle: EvidenceBundle,
        llm_provider: LLMProviderConfig,
    ) -> None:
        self.job = job
        self.evidence_bundle = evidence_bundle
        self.llm_provider = llm_provider
        self.succeeded_artifact: AgentArtifact | None = None

    def claim_next_agent_job(self) -> AgentJob | None:
        return self.job

    def get_evidence_bundle(self, risk_assessment_id: str) -> EvidenceBundle:
        assert risk_assessment_id == self.job.risk_assessment_id
        return self.evidence_bundle

    def get_llm_provider_config(self) -> LLMProviderConfig:
        return self.llm_provider

    def complete_agent_job(self, artifact: AgentArtifact) -> None:
        self.succeeded_artifact = artifact


@contextmanager
def fake_openai_compatible_llm(state: dict[str, Any]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/chat/completions":
                self.send_response(404)
                self.end_headers()
                return

            state["request"] = {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "payload": self.read_json(),
            }
            self.send_json(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "summary": "LLM 判断 PR #18 被 go test 阻塞。",
                                        "evidence_refs": [
                                            "event_check-run-123",
                                            "event_pr-18",
                                        ],
                                        "action_suggestions": [
                                            {
                                                "action_type": "pr_comment",
                                                "target_ref": "pull_request:18",
                                                "draft_body": "请先修复 go test，再请求下一轮 Review。",
                                                "reason": "CI 检查失败正在阻塞 Review。",
                                                "evidence_refs": [
                                                    "event_check-run-123",
                                                    "event_pr-18",
                                                ],
                                                "required_permission": "pull_request:write",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            )

        def read_json(self) -> Any:
            content_length = int(self.headers["Content-Length"])
            return json.loads(self.rfile.read(content_length))

        def send_json(self, payload: dict[str, Any]) -> None:
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
