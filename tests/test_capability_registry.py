from dev_time_agent.capability_registry import build_default_capability_registry


def test_default_capability_registry_describes_github_pull_request_capability() -> None:
    registry = build_default_capability_registry()

    capability = registry.get("github.pull_requests.list")

    assert capability.name == "github.pull_requests.list"
    assert capability.domain == "github"
    assert capability.required_entities == ["repository"]
    assert capability.permissions == ["pull_requests:read"]
    assert "查看 dev-time-agent 的 PR" in capability.examples
