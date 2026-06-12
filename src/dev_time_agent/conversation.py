from dev_time_agent.schemas import (
    ConversationTurnRequest,
    ConversationTurnResponse,
    EvidenceBundle,
)


def answer_conversation_turn(
    request: ConversationTurnRequest,
    bundle: EvidenceBundle,
) -> ConversationTurnResponse:
    intent = classify_intent(request.message)
    if intent == "smalltalk":
        return ConversationTurnResponse(
            conversation_id=request.conversation_id,
            user_message=request.message,
            agent_response=(
                "你好，我是 Dev Time Agent。你可以让我解释当前风险、查看证据，"
                "或生成下一步行动计划。"
            ),
            evidence_refs=[],
            intent="smalltalk",
        )
    if intent == "self_intro":
        return ConversationTurnResponse(
            conversation_id=request.conversation_id,
            user_message=request.message,
            agent_response=(
                "我是 Dev Time Agent，定位是项目风险驱动助手。"
                "我会围绕项目、PR、测试、CI 和交付阻塞来识别风险、解释证据、"
                "生成行动计划，并在需要执行工具前请求确认。"
            ),
            evidence_refs=[],
            intent="self_intro",
        )

    evidence_refs = evidence_refs_from_bundle(bundle)
    if intent == "action_plan":
        first_reason = (
            bundle.signals[0].reason if bundle.signals else "暂无活跃风险信号"
        )
        return ConversationTurnResponse(
            conversation_id=request.conversation_id,
            user_message=request.message,
            agent_response=(
                "行动计划：先确认阻塞证据，再定位失败检查，随后修复并重新运行测试。"
                f"当前依据：{first_reason}"
            ),
            evidence_refs=evidence_refs,
            intent="action_plan",
        )

    return ConversationTurnResponse(
        conversation_id=request.conversation_id,
        user_message=request.message,
        agent_response=f"当前风险原因：{bundle.signals[0].reason}"
        if bundle.signals
        else "暂无活跃风险信号。",
        evidence_refs=evidence_refs,
        intent="risk_explain",
    )


def classify_intent(message: str) -> str:
    normalized = message.strip().lower()
    if normalized in {"你好", "您好", "hi", "hello", "hey"}:
        return "smalltalk"
    if any(
        keyword in normalized
        for keyword in {"介绍", "你是谁", "你能做什么", "自我介绍", "介绍你自己"}
    ):
        return "self_intro"
    if any(keyword in normalized for keyword in {"行动", "计划", "下一步", "怎么做"}):
        return "action_plan"
    return "risk_explain"


def evidence_refs_from_bundle(bundle: EvidenceBundle) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for signal in bundle.signals:
        for evidence_ref in signal.evidence_refs:
            if evidence_ref in seen:
                continue
            seen.add(evidence_ref)
            refs.append(evidence_ref)
    return refs
