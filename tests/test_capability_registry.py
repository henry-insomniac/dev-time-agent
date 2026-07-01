from dev_time_agent.capability_registry import build_default_capability_registry


def test_default_capability_registry_describes_github_pull_request_capability() -> None:
    registry = build_default_capability_registry()

    capability = registry.get("github.pull_requests.list")

    assert capability.name == "github.pull_requests.list"
    assert capability.domain == "github"
    assert capability.required_entities == ["repository"]
    assert capability.permissions == ["pull_requests:read"]
    assert "查看 dev-time-agent 的 PR" in capability.examples


def test_default_tool_specs_include_policy_and_schema_metadata() -> None:
    registry = build_default_capability_registry()

    check_logs = registry.get("github.checks.logs")

    assert check_logs.category == "diagnostic"
    assert check_logs.required_permissions == ["checks:read"]
    assert check_logs.input_schema == {
        "type": "object",
        "required": ["repository_id", "run_id"],
        "properties": {
            "repository_id": {"type": "string"},
            "run_id": {"type": "integer"},
        },
    }
    assert check_logs.output_schema == "CheckLogExcerpt"
    assert check_logs.idempotent is True
    assert check_logs.requires_approval is False
    assert check_logs.risk_level == "low"
    assert check_logs.audit_event_type == "github.checks.logs.read"


def test_action_suggestion_tool_spec_requires_approval_boundary() -> None:
    registry = build_default_capability_registry()

    action_draft = registry.get("action_suggestion.create")

    assert action_draft.category == "plan"
    assert action_draft.required_permissions == ["pull_request:write"]
    assert action_draft.requires_approval is True
    assert action_draft.risk_level == "medium"
    assert action_draft.audit_event_type == "action_suggestion.created"
