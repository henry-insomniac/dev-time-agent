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
    data: dict[str, Any]


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
            data=evidence_bundle.model_dump(),
        )


class ProjectStatusReadTool:
    name = "project_status.read"

    def __init__(self, server_client: HTTPServerClient) -> None:
        self.server_client = server_client

    def run(self, payload: dict[str, Any]) -> ToolResult:
        data = self.server_client.get_project_status(str(payload["risk_assessment_id"]))
        return ToolResult(
            evidence_bundle=None,
            evidence_refs=list(data.get("evidence_refs", [])),
            data=data,
        )


class CIChecksReadTool:
    name = "ci_checks.read"

    def __init__(self, server_client: HTTPServerClient) -> None:
        self.server_client = server_client

    def run(self, payload: dict[str, Any]) -> ToolResult:
        data = self.server_client.get_ci_checks(str(payload["risk_assessment_id"]))
        return ToolResult(
            evidence_bundle=None,
            evidence_refs=evidence_refs_from_items(data.get("checks", [])),
            data=data,
        )


class PullRequestReadTool:
    name = "pull_request.read"

    def __init__(self, server_client: HTTPServerClient) -> None:
        self.server_client = server_client

    def run(self, payload: dict[str, Any]) -> ToolResult:
        data = self.server_client.get_pull_requests(str(payload["risk_assessment_id"]))
        return ToolResult(
            evidence_bundle=None,
            evidence_refs=evidence_refs_from_items(data.get("pull_requests", [])),
            data=data,
        )


class ActionSuggestionCreateTool:
    name = "action_suggestion.create"

    def __init__(self, server_client: HTTPServerClient) -> None:
        self.server_client = server_client

    def run(self, payload: dict[str, Any]) -> ToolResult:
        data = self.server_client.create_action_suggestion(payload)
        return ToolResult(
            evidence_bundle=None,
            evidence_refs=list(data.get("evidence_refs", [])),
            data=data,
        )


class ToolRegistry:
    def __init__(self, tools: list[AgentTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def run(self, name: str, payload: dict[str, Any]) -> ToolResult:
        return self._tools[name].run(payload)

    def names(self) -> list[str]:
        return list(self._tools.keys())


def build_default_tool_registry(server_client: HTTPServerClient) -> ToolRegistry:
    return ToolRegistry(
        [
            RiskEvidenceReadTool(server_client),
            ProjectStatusReadTool(server_client),
            CIChecksReadTool(server_client),
            PullRequestReadTool(server_client),
            ActionSuggestionCreateTool(server_client),
        ]
    )


def build_tool_registry_from_env(
    environment: Mapping[str, str] | None = None,
) -> ToolRegistry | None:
    loaded_environment = environment or os.environ
    server_internal_base_url = loaded_environment.get("DEV_TIME_SERVER_INTERNAL_BASE_URL")
    if not server_internal_base_url:
        return None
    return build_default_tool_registry(HTTPServerClient(server_internal_base_url))


def evidence_refs_from_items(items: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in items:
        evidence_ref = item.get("evidence_ref")
        if evidence_ref:
            refs.append(str(evidence_ref))
    return refs
