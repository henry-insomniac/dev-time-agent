import json
from pathlib import Path


def test_agent_eval_cases_cover_core_conversation_scenarios() -> None:
    fixture_path = Path("tests/fixtures/agent_eval_cases.json")
    cases = json.loads(fixture_path.read_text())

    required_ids = {
        "smalltalk_hello",
        "capability_how_to_test",
        "risk_explain_with_evidence",
        "follow_up_action_plan",
        "write_action_requires_approval",
        "off_topic_guardrail",
        "page_context_repository_resolution",
        "pr_ci_agent_program_happy_path",
        "pr_ci_missing_repository_fallback",
        "pr_ci_missing_checks_fallback",
        "docs_retrieval_with_citation",
        "approval_required_action_suggestion_no_execution",
    }
    assert {case["id"] for case in cases} >= required_ids
    for case in cases:
        assert case["user_message"].strip()
        assert case["expected_intent"].strip()
        assert case["acceptance_criteria"]
        assert case["quality_metrics"]
        if case["id"] in required_ids - {
            "smalltalk_hello",
            "capability_how_to_test",
            "risk_explain_with_evidence",
            "follow_up_action_plan",
            "write_action_requires_approval",
            "off_topic_guardrail",
        }:
            assert case["deterministic_fixture"] is True
            assert case["forbidden_fabrications"]
