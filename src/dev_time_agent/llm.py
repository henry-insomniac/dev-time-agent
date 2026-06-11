import json
from typing import Any
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from dev_time_agent.schemas import (
    ActionSuggestion,
    AgentArtifact,
    AgentJob,
    EvidenceBundle,
    LLMProviderConfig,
)


class LLMArtifactOutput(BaseModel):
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    action_suggestions: list[ActionSuggestion] = Field(default_factory=list)


class OpenAICompatibleLLMClient:
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def generate_agent_artifact(
        self,
        job: AgentJob,
        bundle: EvidenceBundle,
    ) -> AgentArtifact:
        response = self._chat_completion(job, bundle)
        output = LLMArtifactOutput.model_validate_json(response)
        return AgentArtifact(
            job_id=job.job_id,
            project_id=job.project_id,
            risk_assessment_id=job.risk_assessment_id,
            agent_type=job.agent_type,
            status="succeeded",
            summary=output.summary,
            evidence_refs=output.evidence_refs,
            action_suggestions=output.action_suggestions,
            model=f"{self.config.provider}:{self.config.model}",
            prompt_version="dev-time-agent-llm@v1",
        )

    def _chat_completion(self, job: AgentJob, bundle: EvidenceBundle) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 Dev Time 的项目风险 Agent。只基于证据包输出 JSON，"
                        "不要编造不存在的 GitHub 事实。"
                    ),
                },
                {
                    "role": "user",
                    "content": build_agent_prompt(job, bundle),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read())

        content = nested_value(body, "choices", 0, "message", "content")
        if not isinstance(content, str) or content == "":
            raise ValueError("llm response did not include message content")
        return content


def build_agent_prompt(job: AgentJob, bundle: EvidenceBundle) -> str:
    return json.dumps(
        {
            "task": job.agent_type,
            "required_output_schema": {
                "summary": "中文风险结论",
                "evidence_refs": ["必须来自 evidence_bundle.signals/events 的 id"],
                "action_suggestions": [
                    {
                        "action_type": "pr_comment | issue_comment",
                        "target_ref": "pull_request:<number> 或 issue:<number>",
                        "draft_body": "中文行动草稿",
                        "reason": "生成该草稿的原因",
                        "evidence_refs": ["相关 evidence id"],
                        "required_permission": "需要的权限",
                    }
                ],
            },
            "evidence_bundle": bundle.model_dump(),
        },
        ensure_ascii=False,
    )


def nested_value(payload: Any, *path: str | int) -> Any:
    value = payload
    for key in path:
        if isinstance(key, int):
            if not isinstance(value, list) or len(value) <= key:
                return None
            value = value[key]
            continue
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
