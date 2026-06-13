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
    }
    assert {case["id"] for case in cases} >= required_ids
    for case in cases:
        assert case["user_message"].strip()
        assert case["expected_intent"].strip()
        assert case["acceptance_criteria"]
        assert case["quality_metrics"]
