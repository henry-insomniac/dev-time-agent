import os

from fastapi.testclient import TestClient

from dev_time_agent.app import app
from dev_time_agent.graph_runtime import (
    configure_conversation_llm_for_tests,
    configure_session_memory_store_for_tests,
    configure_tool_registry_for_tests,
)
from dev_time_agent.memory import InMemorySessionMemoryStore
from dev_time_agent.schemas import AgentDraftResponse, AgentPlan, ResponseVerification


def setup_function() -> None:
    os.environ.pop("DEV_TIME_SERVER_INTERNAL_BASE_URL", None)
    configure_session_memory_store_for_tests(InMemorySessionMemoryStore())
    configure_tool_registry_for_tests(None)
    configure_conversation_llm_for_tests(None)


def test_docs_answer_propagates_retrieved_chunk_citation_refs() -> None:
    class DocsLLM:
        def plan_turn(self, context: dict) -> AgentPlan:
            assert context["retrieved_docs"]["available"] is True
            assert (
                context["retrieved_docs"]["chunks"][0]["citation_ref"]
                == "doc:.claude/github-capability-layer.md"
            )
            return AgentPlan(
                intent="docs_answer",
                domain="docs",
                confidence=0.9,
                needs_evidence=False,
                needs_tools=False,
                tool_names=[],
                answer_strategy="answer_from_retrieved_docs",
                reasoning_summary="用户询问概念，使用检索文档回答。",
                safety_notes=[],
            )

        def generate_response(
            self,
            context: dict,
            plan: AgentPlan,
        ) -> AgentDraftResponse:
            citation_ref = context["retrieved_docs"]["chunks"][0]["citation_ref"]
            return AgentDraftResponse(
                answer="GitHub 能力层通过 dev-time-server internal API 读取受控事实。",
                evidence_refs=[citation_ref],
                suggested_actions=[],
                reasoning_summary="使用检索到的 GitHub 能力层文档回答。",
                confidence=0.9,
            )

        def verify_response(
            self,
            context: dict,
            plan: AgentPlan,
            draft: AgentDraftResponse,
        ) -> ResponseVerification:
            return ResponseVerification(passed=True, issues=[], rewrite_instruction="")

    configure_conversation_llm_for_tests(DocsLLM())
    client = TestClient(app)

    response = client.post(
        "/agent/sessions/session_docs/turns",
        json={
            "conversation_id": "conversation_docs",
            "project_id": "project_repo_1001",
            "risk_assessment_id": "risk_project_repo_1001",
            "message": "什么是 GitHub 能力层？",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "docs_answer"
    assert body["evidence_refs"] == ["doc:.claude/github-capability-layer.md"]
