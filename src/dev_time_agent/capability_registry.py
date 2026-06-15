from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capability:
    name: str
    domain: str
    description: str
    required_entities: list[str]
    permissions: list[str]
    result_schema: str
    examples: list[str] = field(default_factory=list)


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
                permissions=["metadata:read"],
                result_schema="GitHubAuthStatus",
                examples=["github 授权状态", "我能访问哪些仓库"],
            ),
            Capability(
                name="github.repos.list",
                domain="github",
                description="List repositories authorized for Dev Time.",
                required_entities=[],
                permissions=["metadata:read"],
                result_schema="GitHubRepository[]",
                examples=["查看我的 github 项目", "我能看到哪些仓库"],
            ),
            Capability(
                name="github.repo.detail",
                domain="github",
                description="Read one authorized repository profile.",
                required_entities=["repository"],
                permissions=["metadata:read"],
                result_schema="GitHubRepository",
                examples=["查看 dev-time-agent 项目"],
            ),
            Capability(
                name="github.pull_requests.list",
                domain="github",
                description="List pull requests for a repository.",
                required_entities=["repository"],
                permissions=["pull_requests:read"],
                result_schema="PullRequest[]",
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
                permissions=["issues:read"],
                result_schema="Issue[]",
                examples=["查看 dev-time-agent 的 issue"],
            ),
            Capability(
                name="github.checks.list",
                domain="github",
                description="List CI check runs for a repository.",
                required_entities=["repository"],
                permissions=["checks:read"],
                result_schema="CheckRun[]",
                examples=["查看 dev-time-agent 的 CI"],
            ),
        ]
    )
