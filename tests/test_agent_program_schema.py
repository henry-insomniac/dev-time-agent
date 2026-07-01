import pytest
from pydantic import ValidationError

from dev_time_agent.capability_registry import build_default_capability_registry
from dev_time_agent.schemas import AgentProgram


def test_agent_program_validates_tool_selector_and_variable_references() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "diagnose failing PR CI",
            "steps": [
                {
                    "id": "list_prs",
                    "kind": "tool",
                    "tool": "github.pull_requests.list",
                    "arguments": {"repository_id": "repo_1001"},
                },
                {
                    "id": "select_pr",
                    "kind": "select",
                    "from_step": "list_prs",
                    "selector": "$.pull_requests[0].number",
                    "output_key": "pr_number",
                },
                {
                    "id": "list_checks",
                    "kind": "tool",
                    "tool": "github.checks.list",
                    "arguments": {"repository_id": {"$var": "pr_number"}},
                },
            ],
            "answer_contract": {
                "format": "text",
                "required_sections": ["summary", "evidence"],
                "must_cite_evidence": True,
            },
        }
    )

    assert program.validate_against_tool_specs(build_default_capability_registry()) is program


def test_agent_program_rejects_unknown_variable_references() -> None:
    with pytest.raises(ValidationError, match="unknown variable missing_repo_id"):
        AgentProgram.model_validate(
            {
                "version": "agent_program.v1",
                "goal": "list checks",
                "steps": [
                    {
                        "id": "list_checks",
                        "kind": "tool",
                        "tool": "github.checks.list",
                        "arguments": {"repository_id": {"$var": "missing_repo_id"}},
                    }
                ],
                "answer_contract": {"format": "text"},
            }
        )


def test_agent_program_rejects_invalid_selectors() -> None:
    with pytest.raises(ValidationError, match="valid selector"):
        AgentProgram.model_validate(
            {
                "version": "agent_program.v1",
                "goal": "select repository",
                "steps": [
                    {
                        "id": "list_repos",
                        "kind": "tool",
                        "tool": "github.repos.list",
                        "arguments": {},
                    },
                    {
                        "id": "select_repo",
                        "kind": "select",
                        "from_step": "list_repos",
                        "selector": "repositories[0].id",
                        "output_key": "repository_id",
                    },
                ],
                "answer_contract": {"format": "text"},
            }
        )


def test_agent_program_rejects_unregistered_tools_before_execution() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "delete repository",
            "steps": [
                {
                    "id": "delete_repo",
                    "kind": "tool",
                    "tool": "github.repository.delete",
                    "arguments": {"repository_id": "repo_1001"},
                }
            ],
            "answer_contract": {"format": "text"},
        }
    )

    with pytest.raises(ValueError, match="tool is not registered"):
        program.validate_against_tool_specs(build_default_capability_registry())


def test_agent_program_rejects_invalid_tool_arguments_before_execution() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "read failed check logs",
            "steps": [
                {
                    "id": "read_logs",
                    "kind": "tool",
                    "tool": "github.checks.logs",
                    "arguments": {"repository_id": "repo_1001", "run_id": "123"},
                }
            ],
            "answer_contract": {"format": "text"},
        }
    )

    with pytest.raises(ValueError, match="argument run_id must be integer"):
        program.validate_against_tool_specs(build_default_capability_registry())
