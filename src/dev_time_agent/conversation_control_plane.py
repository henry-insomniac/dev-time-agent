from dataclasses import dataclass
from enum import StrEnum

from dev_time_agent.conversation import classify_intent


class TurnExecutionPath(StrEnum):
    DIRECT = "direct"
    MODEL = "model"


@dataclass(frozen=True)
class ConversationControlDecision:
    intent: str
    execution_path: TurnExecutionPath


_DIRECT_INTENTS = {
    "current_context",
    "smalltalk",
}

_TRUSTED_CONTEXT_DIRECT_INTENTS = {
    "github_checks_list",
    "github_issues_list",
    "github_pr_ci_diagnosis",
    "github_pull_requests_list",
}


def decide_conversation_execution(
    message: str,
    *,
    has_trusted_context: bool,
) -> ConversationControlDecision:
    """Choose the cheapest trustworthy execution path for one turn.

    Direct turns must be answerable from deterministic rules and trusted context.
    All other turns cross the model Adapter seam only after context assembly.
    """
    intent = classify_intent(message).intent
    is_direct = intent in _DIRECT_INTENTS or (
        has_trusted_context and intent in _TRUSTED_CONTEXT_DIRECT_INTENTS
    )
    return ConversationControlDecision(
        intent=intent,
        execution_path=(
            TurnExecutionPath.DIRECT if is_direct else TurnExecutionPath.MODEL
        ),
    )
