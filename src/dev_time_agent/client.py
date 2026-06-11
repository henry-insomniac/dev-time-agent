import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dev_time_agent.schemas import AgentArtifact, AgentJob, EvidenceBundle


class HTTPServerClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def claim_next_agent_job(self) -> AgentJob | None:
        try:
            payload = self._request_json("POST", "/internal/agent-jobs/claim")
        except HTTPError as error:
            if error.code == 204:
                return None
            raise
        if payload is None:
            return None
        return AgentJob.model_validate(payload)

    def get_evidence_bundle(self, risk_assessment_id: str) -> EvidenceBundle:
        payload = self._request_json(
            "GET",
            f"/internal/risk-assessments/{risk_assessment_id}/evidence-bundle",
        )
        return EvidenceBundle.model_validate(payload)

    def complete_agent_job(self, artifact: AgentArtifact) -> None:
        payload = {
            "summary": artifact.summary,
            "evidence_refs": artifact.evidence_refs,
            "model": "deterministic",
            "prompt_version": "dev-time-agent@v1",
            "action_suggestions": [
                {
                    "action_type": suggestion.action_type,
                    "target_ref": suggestion.target_ref,
                    "draft_body": suggestion.draft_body,
                    "evidence_refs": suggestion.evidence_refs,
                }
                for suggestion in artifact.action_suggestions
            ],
        }
        self._request_json(
            "POST",
            f"/internal/agent-jobs/{artifact.job_id}/complete",
            payload,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        with urlopen(request, timeout=10) as response:
            if response.status == 204:
                return None
            return json.loads(response.read())
