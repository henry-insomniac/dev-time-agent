import os

from fastapi.testclient import TestClient

from dev_time_agent.app import app
from dev_time_agent.client import HTTPServerClient
from dev_time_agent.graph_runtime import (
    configure_conversation_llm_for_tests,
    configure_session_memory_store_for_tests,
    configure_tool_registry_for_tests,
)
from dev_time_agent.memory import InMemorySessionMemoryStore
from dev_time_agent.schemas import (
    AgentDraftResponse,
    AgentPlan,
    AgentProgram,
    ResponseVerification,
)
from dev_time_agent.tools import build_default_tool_registry
from fake_agent_llm import FakeConversationLLM, fake_dev_time_server


def setup_function() -> None:
    os.environ.pop("DEV_TIME_SERVER_INTERNAL_BASE_URL", None)
    configure_session_memory_store_for_tests(InMemorySessionMemoryStore())
    configure_tool_registry_for_tests(None)
    configure_conversation_llm_for_tests(None)


def test_pr_ci_diagnosis_executes_agent_program_before_generating_response() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "diagnose failing PR CI",
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
                {
                    "id": "list_checks",
                    "kind": "tool",
                    "tool": "github.checks.list",
                    "arguments": {"repository_id": {"$var": "repository_id"}},
                },
                {
                    "id": "select_failed_run",
                    "kind": "select",
                    "from_step": "list_checks",
                    "selector": "$.checks[0].run_id",
                    "output_key": "run_id",
                },
                {
                    "id": "read_logs",
                    "kind": "tool",
                    "tool": "github.checks.logs",
                    "arguments": {
                        "repository_id": {"$var": "repository_id"},
                        "run_id": {"$var": "run_id"},
                    },
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
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(
            FakeConversationLLM(
                expected_user_message="诊断当前 PR 的 CI 失败",
                plan=AgentPlan(
                    intent="pr_ci_diagnosis",
                    domain="github",
                    capabilities=[
                        "github.repos.list",
                        "github.pull_requests.list",
                        "github.checks.list",
                        "github.checks.logs",
                    ],
                    confidence=0.92,
                    needs_evidence=False,
                    needs_tools=True,
                    tool_names=[],
                    program=program,
                    answer_strategy="execute_agent_program_for_pr_ci_diagnosis",
                    reasoning_summary="需要用 AgentProgram 逐步读取仓库、PR、Checks 和失败日志。",
                    safety_notes=[],
                ),
                draft=AgentDraftResponse(
                    answer="CI 失败来自 eslint，日志显示多个 no-unused-vars 错误。",
                    evidence_refs=["github_live_check_run_812_logs"],
                    suggested_actions=[],
                    reasoning_summary="基于 AgentProgram 工具输出生成诊断。",
                    confidence=0.9,
                ),
                verification=ResponseVerification(
                    passed=True,
                    issues=[],
                    rewrite_instruction="",
                ),
            )
        )
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1002/turns",
            json={
                "conversation_id": "conversation_project_repo_1002",
                "project_id": "project_repo_1002",
                "risk_assessment_id": "risk_project_repo_1002",
                "message": "诊断当前 PR 的 CI 失败",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "pr_ci_diagnosis"
    assert "eslint" in body["agent_response"]
    assert [tool_call["name"] for tool_call in body["tool_calls"]] == [
        "github.repos.list",
        "program.select",
        "github.pull_requests.list",
        "github.checks.list",
        "program.select",
        "github.checks.logs",
    ]
    assert body["tool_calls"][-1]["input"] == {
        "repository_id": "repo_1002",
        "run_id": 812,
    }
    assert "github_live_check_run_812_logs" in body["evidence_refs"]


def test_pr_ci_diagnosis_receives_program_partial_result_for_missing_repository() -> None:
    program = AgentProgram.model_validate(
        {
            "version": "agent_program.v1",
            "goal": "diagnose failing PR CI",
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
                {
                    "id": "list_checks",
                    "kind": "tool",
                    "tool": "github.checks.list",
                    "arguments": {"repository_id": {"$var": "repository_id"}},
                },
            ],
            "answer_contract": {"format": "text"},
        }
    )

    class MissingRepositoryLLM:
        def plan_turn(self, context: dict) -> AgentPlan:
            return AgentPlan(
                intent="pr_ci_diagnosis",
                domain="github",
                capabilities=["github.repos.list", "github.checks.list"],
                confidence=0.89,
                needs_evidence=False,
                needs_tools=True,
                tool_names=[],
                program=program,
                answer_strategy="fallback_when_repository_missing",
                reasoning_summary="需要先解析仓库；解析不到时停止。",
                safety_notes=[],
            )

        def generate_response(
            self,
            context: dict,
            plan: AgentPlan,
        ) -> AgentDraftResponse:
            agent_program = context["tool_results"]["agent_program"]
            assert agent_program["status"] == "partial"
            assert agent_program["error"] == "selector_value_missing"
            assert agent_program["step_outputs"]["list_repos"] == {"repositories": []}
            return AgentDraftResponse(
                answer="我没有找到已授权仓库，因此不能继续诊断 PR/CI。",
                evidence_refs=[],
                suggested_actions=[],
                reasoning_summary="仓库解析失败，按 fallback 回复。",
                confidence=0.86,
            )

        def verify_response(
            self,
            context: dict,
            plan: AgentPlan,
            draft: AgentDraftResponse,
        ) -> ResponseVerification:
            return ResponseVerification(passed=True, issues=[], rewrite_instruction="")

    with fake_dev_time_server(github_connected=False) as base_url:
        configure_tool_registry_for_tests(
            build_default_tool_registry(HTTPServerClient(base_url))
        )
        configure_conversation_llm_for_tests(MissingRepositoryLLM())
        client = TestClient(app)

        response = client.post(
            "/agent/sessions/session_project_repo_1002/turns",
            json={
                "conversation_id": "conversation_project_repo_1002",
                "project_id": "project_repo_1002",
                "risk_assessment_id": "risk_project_repo_1002",
                "message": "诊断当前 PR 的 CI 失败",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert "没有找到已授权仓库" in body["agent_response"]
    assert [tool_call["status"] for tool_call in body["tool_calls"]] == [
        "succeeded",
        "failed",
    ]
    assert body["tool_calls"][1]["error"] == "selector_value_missing"
