from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capability:
    name: str
    domain: str
    description: str
    required_entities: list[str]
    required_permissions: list[str]
    output_schema: str
    category: str = "read"
    input_schema: dict = field(default_factory=dict)
    idempotent: bool = True
    requires_approval: bool = False
    risk_level: str = "low"
    audit_event_type: str = ""
    examples: list[str] = field(default_factory=list)

    @property
    def permissions(self) -> list[str]:
        return self.required_permissions

    @property
    def result_schema(self) -> str:
        return self.output_schema


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability]) -> None:
        self._capabilities = {capability.name: capability for capability in capabilities}

    def get(self, name: str) -> Capability:
        return self._capabilities[name]

    def names(self) -> list[str]:
        return list(self._capabilities.keys())

    def for_domain(self, domain: str) -> list[Capability]:
        return [
            capability
            for capability in self._capabilities.values()
            if capability.domain == domain
        ]


def build_default_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        [
            Capability(
                name="github.auth.status",
                domain="github",
                description="Check GitHub App authorization status.",
                required_entities=[],
                required_permissions=["metadata:read"],
                output_schema="GitHubAuthStatus",
                category="read",
                input_schema=object_schema(),
                audit_event_type="github.auth.status.read",
                examples=["github 授权状态", "我能访问哪些仓库"],
            ),
            Capability(
                name="github.repos.list",
                domain="github",
                description="List repositories authorized for Dev Time.",
                required_entities=[],
                required_permissions=["metadata:read"],
                output_schema="GitHubRepository[]",
                category="read",
                input_schema=object_schema(),
                audit_event_type="github.repos.list.read",
                examples=["查看我的 github 项目", "我能看到哪些仓库"],
            ),
            Capability(
                name="github.repo.detail",
                domain="github",
                description="Read one authorized repository profile.",
                required_entities=["repository"],
                required_permissions=["metadata:read"],
                output_schema="GitHubRepository",
                category="read",
                input_schema=object_schema(required=["repository_id"]),
                audit_event_type="github.repo.detail.read",
                examples=["查看 dev-time-agent 项目"],
            ),
            Capability(
                name="github.pull_requests.list",
                domain="github",
                description="List pull requests for a repository.",
                required_entities=["repository"],
                required_permissions=["pull_requests:read"],
                output_schema="PullRequest[]",
                category="read",
                input_schema=object_schema(required=["repository_id"]),
                audit_event_type="github.pull_requests.list.read",
                examples=[
                    "查看 dev-time-agent 的 PR",
                    "dev-time-agent 有哪些打开的 PR",
                    "看一下这个仓库最近的 pull request",
                ],
            ),
            Capability(
                name="github.issues.list",
                domain="github",
                description="List issues for a repository.",
                required_entities=["repository"],
                required_permissions=["issues:read"],
                output_schema="Issue[]",
                category="read",
                input_schema=object_schema(required=["repository_id"]),
                audit_event_type="github.issues.list.read",
                examples=["查看 dev-time-agent 的 issue"],
            ),
            Capability(
                name="github.checks.list",
                domain="github",
                description="List CI check runs for a repository.",
                required_entities=["repository"],
                required_permissions=["checks:read"],
                output_schema="CheckRun[]",
                category="read",
                input_schema=object_schema(required=["repository_id"]),
                audit_event_type="github.checks.list.read",
                examples=["查看 dev-time-agent 的 CI"],
            ),
            Capability(
                name="github.checks.logs",
                domain="github",
                description="Read failed CI check logs for diagnosis.",
                required_entities=["repository", "run_id"],
                required_permissions=["checks:read"],
                output_schema="CheckLogExcerpt",
                category="diagnostic",
                input_schema=object_schema(
                    required=["repository_id", "run_id"],
                    properties={
                        "repository_id": {"type": "string"},
                        "run_id": {"type": "integer"},
                    },
                ),
                audit_event_type="github.checks.logs.read",
                examples=["帮我看看 dev-time-agent #12 PR 为什么红了"],
            ),
            Capability(
                name="action_suggestion.create",
                domain="agent_action",
                description="Create a pending action suggestion draft for user approval.",
                required_entities=["project", "target_ref"],
                required_permissions=["pull_request:write"],
                output_schema="ActionSuggestion",
                category="plan",
                input_schema=object_schema(
                    required=[
                        "project_id",
                        "action_type",
                        "target_ref",
                        "draft_body",
                    ],
                    properties={
                        "project_id": {"type": "string"},
                        "action_type": {"type": "string"},
                        "target_ref": {"type": "string"},
                        "draft_body": {"type": "string"},
                        "evidence_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                ),
                idempotent=False,
                requires_approval=True,
                risk_level="medium",
                audit_event_type="action_suggestion.created",
                examples=["生成 PR 评论草稿", "创建待确认行动建议"],
            ),
        ]
    )


def object_schema(
    *,
    required: list[str] | None = None,
    properties: dict | None = None,
) -> dict:
    if properties is None:
        properties = {
            name: {"type": "string"}
            for name in required or []
        }
    return {
        "type": "object",
        "required": required or [],
        "properties": properties,
    }
