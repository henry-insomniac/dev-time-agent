import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from dev_time_agent.client import HTTPServerClient
from dev_time_agent.conversation import evidence_refs_from_bundle
from dev_time_agent.schemas import EvidenceBundle


@dataclass(frozen=True)
class ToolResult:
    evidence_bundle: EvidenceBundle | None
    evidence_refs: list[str]


class AgentTool(Protocol):
    name: str

    def run(self, payload: dict[str, Any]) -> ToolResult:
        ...


class RiskEvidenceReadTool:
    name = "risk_evidence.read"

    def __init__(self, server_client: HTTPServerClient) -> None:
        self.server_client = server_client

    def run(self, payload: dict[str, Any]) -> ToolResult:
        risk_assessment_id = str(payload["risk_assessment_id"])
        evidence_bundle = self.server_client.get_evidence_bundle(risk_assessment_id)
        return ToolResult(
            evidence_bundle=evidence_bundle,
            evidence_refs=evidence_refs_from_bundle(evidence_bundle),
        )


class ToolRegistry:
    def __init__(self, tools: list[AgentTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def run(self, name: str, payload: dict[str, Any]) -> ToolResult:
        return self._tools[name].run(payload)


def build_default_tool_registry(server_client: HTTPServerClient) -> ToolRegistry:
    return ToolRegistry([RiskEvidenceReadTool(server_client)])


def build_tool_registry_from_env(
    environment: Mapping[str, str] | None = None,
) -> ToolRegistry | None:
    loaded_environment = environment or os.environ
    server_internal_base_url = loaded_environment.get("DEV_TIME_SERVER_INTERNAL_BASE_URL")
    if not server_internal_base_url:
        return None
    return build_default_tool_registry(HTTPServerClient(server_internal_base_url))
