from dev_time_agent.agent_program_executor import execute_agent_program
from dev_time_agent.capability_registry import build_default_capability_registry
from dev_time_agent.client import HTTPServerClient
from dev_time_agent.schemas import (
    AgentProgram,
    AgentProgramAnswerContract,
    AgentProgramStep,
)
from dev_time_agent.tools import build_default_tool_registry
from fake_agent_llm import fake_dev_time_server


def test_agent_program_executor_runs_tool_selector_and_variable_steps() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "inspect pull requests for the selected repository",
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
                    "selector": "$.repositories[1].id",
                    "output_key": "repository_id",
                },
                {
                    "id": "list_prs",
                    "kind": "tool",
                    "tool": "github.pull_requests.list",
                    "arguments": {"repository_id": {"$var": "repository_id"}},
                },
            ],
            "answer_contract": {
                "format": "text",
                "required_sections": ["summary", "evidence"],
                "must_cite_evidence": True,
            },
        }
    )

    with fake_dev_time_server(github_connected=True) as base_url:
        result = execute_agent_program(
            program,
            build_default_tool_registry(HTTPServerClient(base_url)),
            build_default_capability_registry(),
        )

    assert result.status == "succeeded"
    assert result.variables["repository_id"] == "repo_1002"
    assert [tool_call["name"] for tool_call in result.tool_calls] == [
        "github.repos.list",
        "program.select",
        "github.pull_requests.list",
    ]
    assert result.tool_calls[2]["input"] == {"repository_id": "repo_1002"}
    assert result.evidence_refs == ["event_pull-request-12", "event_pull-request-18"]


def test_agent_program_executor_short_circuits_when_selector_data_is_missing() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "inspect missing repository",
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
                    "selector": "$.repositories[99].id",
                    "output_key": "repository_id",
                },
                {
                    "id": "list_prs",
                    "kind": "tool",
                    "tool": "github.pull_requests.list",
                    "arguments": {"repository_id": {"$var": "repository_id"}},
                },
            ],
            "answer_contract": {"format": "text"},
        }
    )

    with fake_dev_time_server(github_connected=True) as base_url:
        result = execute_agent_program(
            program,
            build_default_tool_registry(HTTPServerClient(base_url)),
            build_default_capability_registry(),
        )

    assert result.status == "partial"
    assert result.error == "selector_value_missing"
    assert [tool_call["name"] for tool_call in result.tool_calls] == [
        "github.repos.list",
        "program.select",
    ]
    assert result.tool_calls[1]["status"] == "failed"


def test_agent_program_executor_blocks_approval_required_tools() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "create a PR comment",
            "steps": [
                {
                    "id": "create_comment",
                    "kind": "tool",
                    "tool": "action_suggestion.create",
                    "arguments": {
                        "project_id": "project_repo_1002",
                        "action_type": "pr_comment",
                        "target_ref": "pull_request:18",
                        "draft_body": "Please fix the failing CI check.",
                    },
                }
            ],
            "answer_contract": {"format": "text"},
        }
    )

    with fake_dev_time_server(github_connected=True) as base_url:
        result = execute_agent_program(
            program,
            build_default_tool_registry(HTTPServerClient(base_url)),
            build_default_capability_registry(),
        )

    assert result.status == "partial"
    assert result.error == "approval_required"
    assert result.tool_calls == [
        {
            "step_id": "create_comment",
            "name": "action_suggestion.create",
            "status": "blocked",
            "input": {
                "project_id": "project_repo_1002",
                "action_type": "pr_comment",
                "target_ref": "pull_request:18",
                "draft_body": "Please fix the failing CI check.",
            },
            "error": "approval_required",
            "evidence_refs": [],
        }
    ]


def test_agent_program_executor_validates_arguments_after_variable_resolution() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "read failed check logs",
            "steps": [
                {
                    "id": "list_checks",
                    "kind": "tool",
                    "tool": "github.checks.list",
                    "arguments": {"repository_id": "repo_1002"},
                },
                {
                    "id": "select_check_name",
                    "kind": "select",
                    "from_step": "list_checks",
                    "selector": "$.checks[0].name",
                    "output_key": "run_id",
                },
                {
                    "id": "read_logs",
                    "kind": "tool",
                    "tool": "github.checks.logs",
                    "arguments": {
                        "repository_id": "repo_1002",
                        "run_id": {"$var": "run_id"},
                    },
                },
            ],
            "answer_contract": {"format": "text"},
        }
    )

    with fake_dev_time_server(github_connected=True) as base_url:
        result = execute_agent_program(
            program,
            build_default_tool_registry(HTTPServerClient(base_url)),
            build_default_capability_registry(),
        )

    assert result.status == "partial"
    assert result.error == "invalid_arguments"
    assert [tool_call["name"] for tool_call in result.tool_calls] == [
        "github.checks.list",
        "program.select",
        "github.checks.logs",
    ]
    assert result.tool_calls[2]["status"] == "failed"
    assert result.tool_calls[2]["error"] == "invalid_arguments"


def test_agent_program_executor_handles_missing_variables_without_crashing() -> None:
    program = AgentProgram.model_construct(
        version="agent_program.v1",
        goal="list pull requests",
        steps=[
            AgentProgramStep.model_construct(
                id="list_prs",
                kind="tool",
                tool="github.pull_requests.list",
                arguments={"repository_id": {"$var": "repository_id"}},
                from_step="",
                selector="",
                output_key="",
            )
        ],
        answer_contract=AgentProgramAnswerContract(format="text"),
    )

    with fake_dev_time_server(github_connected=True) as base_url:
        result = execute_agent_program(
            program,
            build_default_tool_registry(HTTPServerClient(base_url)),
            build_default_capability_registry(),
        )

    assert result.status == "partial"
    assert result.error == "missing_variable"
    assert result.tool_calls[0]["status"] == "failed"
    assert result.tool_calls[0]["error"] == "missing_variable"


def test_agent_program_executor_enforces_step_limit() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "too many steps for this execution",
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
                    "selector": "$.repositories[0].id",
                    "output_key": "repository_id",
                },
            ],
            "answer_contract": {"format": "text"},
        }
    )

    with fake_dev_time_server(github_connected=True) as base_url:
        result = execute_agent_program(
            program,
            build_default_tool_registry(HTTPServerClient(base_url)),
            build_default_capability_registry(),
            max_steps=1,
        )

    assert result.status == "failed"
    assert result.error == "max_steps_exceeded"
    assert result.tool_calls == []


def test_agent_program_executor_bounds_tool_output_items() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "list repositories",
            "steps": [
                {
                    "id": "list_repos",
                    "kind": "tool",
                    "tool": "github.repos.list",
                    "arguments": {},
                }
            ],
            "answer_contract": {"format": "text"},
        }
    )

    with fake_dev_time_server(github_connected=True) as base_url:
        result = execute_agent_program(
            program,
            build_default_tool_registry(HTTPServerClient(base_url)),
            build_default_capability_registry(),
            max_output_items=1,
        )

    assert result.status == "succeeded"
    assert len(result.step_outputs["list_repos"]["repositories"]) == 1
