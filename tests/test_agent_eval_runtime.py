import json
from pathlib import Path

from fastapi.testclient import TestClient

from dev_time_agent.app import app
from dev_time_agent.client import HTTPServerClient
from dev_time_agent.conversation_llm import OpenAICompatibleConversationLLM
from dev_time_agent.graph_runtime import (
    configure_conversation_llm_for_tests,
    configure_session_memory_store_for_tests,
    configure_tool_registry_for_tests,
)
from dev_time_agent.memory import InMemorySessionMemoryStore
from dev_time_agent.schemas import LLMProviderConfig
from dev_time_agent.tools import build_default_tool_registry
from fake_agent_llm import fake_dev_time_server


def test_executable_agent_eval_cases_satisfy_runtime_contracts() -> None:
    cases = json.loads(Path("tests/fixtures/agent_eval_cases.json").read_text())
    executable_cases = [case for case in cases if case.get("executable_runtime")]
    assert {case["id"] for case in executable_cases} == {
        "self_intro_effective_model",
        "trusted_context_current_project",
        "trusted_context_current_project_issues",
        "pr_ci_agent_program_happy_path",
    }

    configure_session_memory_store_for_tests(InMemorySessionMemoryStore())
    configure_conversation_llm_for_tests(
        OpenAICompatibleConversationLLM(
            LLMProviderConfig(
                provider="openai-compatible",
                base_url="http://127.0.0.1:1/v1",
                model="qwen3-coder-plus",
                api_key="eval-key",
            )
        )
    )
    try:
        with fake_dev_time_server(github_connected=True) as base_url:
            configure_tool_registry_for_tests(
                build_default_tool_registry(HTTPServerClient(base_url))
            )
            client = TestClient(app)
            for case in executable_cases:
                payload = {
                    "conversation_id": "eval_" + case["id"],
                    "project_id": "project_repo_1002",
                    "risk_assessment_id": "risk_project_repo_1002",
                    "message": case["user_message"],
                }
                if case.get("trusted_context"):
                    payload["trusted_context"] = case["trusted_context"]
                response = client.post(
                    "/agent/sessions/eval_" + case["id"] + "/turns",
                    json=payload,
                )
                assert response.status_code == 200, case["id"]
                body = response.json()
                assert body["intent"] == case["expected_intent"], case["id"]
                for expected in case.get("expected_response_contains", []):
                    assert expected in body["agent_response"], case["id"]
                assert [call["name"] for call in body["tool_calls"]] == case.get(
                    "expected_tool_names", []
                ), case["id"]
                for evidence_ref in case.get("expected_evidence_refs", []):
                    assert evidence_ref in body["evidence_refs"], case["id"]
                for forbidden in case.get("forbidden_fabrications", []):
                    assert forbidden not in body["agent_response"], case["id"]
    finally:
        configure_conversation_llm_for_tests(None)
        configure_tool_registry_for_tests(None)
