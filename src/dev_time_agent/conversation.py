import re

from dev_time_agent.schemas import (
    ConversationTurnRequest,
    ConversationTurnResponse,
    EvidenceBundle,
    IntentClassification,
)


def answer_conversation_turn(
    request: ConversationTurnRequest,
    bundle: EvidenceBundle | None,
) -> ConversationTurnResponse:
    classification = classify_intent(request.message)
    if classification.intent == "smalltalk":
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
    if classification.intent == "self_intro":
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
    if classification.intent == "clarify":
        return ConversationTurnResponse(
            conversation_id=request.conversation_id,
            user_message=request.message,
            agent_response=classification.clarifying_question,
            evidence_refs=[],
            intent="clarify",
        )

    if bundle is None:
        return ConversationTurnResponse(
            conversation_id=request.conversation_id,
            user_message=request.message,
            agent_response="我需要先看到当前项目证据，才能继续处理这个请求。",
            evidence_refs=[],
            intent="clarify",
        )

    evidence_refs = evidence_refs_from_bundle(bundle)
    if classification.intent == "action_plan":
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


def classify_intent(message: str) -> IntentClassification:
    normalized = message.strip().lower()
    if normalized in {"你好", "您好", "hi", "hello", "hey"}:
        return IntentClassification(
            intent="smalltalk",
            confidence=1,
            requires_evidence=False,
        )
    if is_current_context_question(normalized):
        return IntentClassification(
            intent="current_context",
            confidence=1,
            requires_evidence=False,
        )
    if any(
        keyword in normalized
        for keyword in {"当前状态", "项目状态", "现在状态", "现在怎么样"}
    ):
        return IntentClassification(
            intent="project_status",
            confidence=0.9,
            requires_evidence=True,
        )
    if is_github_auth_status_question(normalized):
        return IntentClassification(
            intent="github_auth_status",
            confidence=0.9,
            requires_evidence=False,
            requires_tool=True,
        )
    if is_github_pr_ci_diagnosis_question(normalized):
        return IntentClassification(
            intent="github_pr_ci_diagnosis",
            confidence=0.92,
            requires_evidence=False,
            requires_tool=True,
        )
    if is_github_repository_detail_question(normalized):
        return IntentClassification(
            intent="github_repository_detail",
            confidence=0.9,
            requires_evidence=False,
            requires_tool=True,
        )
    if is_github_repository_access_question(normalized):
        return IntentClassification(
            intent="github_repository_list",
            confidence=0.9,
            requires_evidence=False,
            requires_tool=True,
        )
    if is_github_pull_request_list_question(normalized):
        return IntentClassification(
            intent="github_pull_requests_list",
            confidence=0.9,
            requires_evidence=False,
            requires_tool=True,
        )
    if is_github_issue_list_question(normalized):
        return IntentClassification(
            intent="github_issues_list",
            confidence=0.9,
            requires_evidence=False,
            requires_tool=True,
        )
    if is_github_check_list_question(normalized):
        return IntentClassification(
            intent="github_checks_list",
            confidence=0.9,
            requires_evidence=False,
            requires_tool=True,
        )
    if any(
        keyword in normalized
        for keyword in {
            "介绍你自己",
            "介绍自己",
            "你是谁",
            "你能做什么",
            "自我介绍",
            "认识你",
            "了解你",
            "怎么用你",
        }
    ):
        return IntentClassification(
            intent="self_intro",
            confidence=0.95,
            requires_evidence=False,
        )
    if any(keyword in normalized for keyword in {"行动", "计划", "下一步", "怎么做"}):
        return IntentClassification(
            intent="action_plan",
            confidence=0.9,
            requires_evidence=True,
        )
    if any(
        keyword in normalized
        for keyword in {"风险", "证据", "为什么", "高风险", "阻塞", "测试", "ci", "pr"}
    ):
        return IntentClassification(
            intent="risk_explain",
            confidence=0.9,
            requires_evidence=True,
        )
    return IntentClassification(
        intent="clarify",
        confidence=0.35,
        requires_evidence=False,
        clarifying_question="你想让我评估当前风险、解释证据，还是生成下一步行动计划？",
    )


def is_current_context_question(normalized_message: str) -> bool:
    if any(
        keyword in normalized_message
        for keyword in {"状态", "风险", "进度", "怎么样", "健康"}
    ):
        return False
    has_context_anchor = any(
        keyword in normalized_message
        for keyword in {"当前", "现在", "这个", "本项目", "本仓库", "这里"}
    )
    has_project_subject = any(
        keyword in normalized_message
        for keyword in {"项目", "仓库", "repository", "repo"}
    )
    asks_identity = any(
        keyword in normalized_message
        for keyword in {"是什么", "是哪个", "是哪一个", "叫什么", "哪个项目", "哪个仓库"}
    )
    return has_context_anchor and has_project_subject and asks_identity


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


def is_github_repository_access_question(normalized_message: str) -> bool:
    mentions_github = "github" in normalized_message or "git hub" in normalized_message
    mentions_repository = any(
        keyword in normalized_message
        for keyword in {"项目", "仓库", "repo", "repository", "代码库"}
    )
    asks_visibility = any(
        keyword in normalized_message
        for keyword in {
            "查看",
            "看到",
            "访问",
            "有哪些",
            "什么",
            "列表",
            "能看",
            "可见",
        }
    )
    return mentions_github and mentions_repository and asks_visibility


def is_github_repository_detail_question(normalized_message: str) -> bool:
    mentions_github = "github" in normalized_message or "git hub" in normalized_message
    mentions_repository = any(
        keyword in normalized_message
        for keyword in {"项目", "仓库", "repo", "repository", "代码库"}
    )
    asks_visibility = any(
        keyword in normalized_message
        for keyword in {"查看", "打开", "访问", "看下", "看一下"}
    )
    asks_all = any(
        keyword in normalized_message
        for keyword in {"我的", "所有", "全部", "有哪些", "列表", "能看到", "可见", "什么"}
    )
    return (
        (mentions_github or has_repository_like_token(normalized_message))
        and mentions_repository
        and asks_visibility
        and not asks_all
    )


def is_github_auth_status_question(normalized_message: str) -> bool:
    mentions_github = "github" in normalized_message or "git hub" in normalized_message
    if not mentions_github:
        return False
    return any(
        keyword in normalized_message
        for keyword in {"授权", "连接", "配置", "安装", "权限", "状态", "可访问", "能访问"}
    )


def has_repository_like_token(normalized_message: str) -> bool:
    return re.search(r"[a-z0-9][a-z0-9._-]*[-/][a-z0-9._-]+", normalized_message) is not None


def is_github_pr_ci_diagnosis_question(normalized_message: str) -> bool:
    mentions_pull_request = (
        "pr" in normalized_message or "pull request" in normalized_message
    )
    mentions_pr_number = re.search(
        r"(?:#\s*\d+\s*pr\b|\bpr\s*#?\s*\d+)",
        normalized_message,
    )
    asks_failure_reason = any(
        keyword in normalized_message
        for keyword in {"为什么", "红了", "失败", "挂了", "failed", "failure", "broken"}
    )
    return (mentions_pull_request or mentions_pr_number is not None) and asks_failure_reason


def is_github_pull_request_list_question(normalized_message: str) -> bool:
    mentions_pull_request = (
        "pr" in normalized_message or "pull request" in normalized_message
    )
    asks_visibility = any(
        keyword in normalized_message
        for keyword in {"查看", "看到", "有哪些", "列表", "列出", "打开", "open"}
    )
    mentions_risk = any(
        keyword in normalized_message for keyword in {"风险", "为什么", "阻塞"}
    )
    return mentions_pull_request and asks_visibility and not mentions_risk


def is_github_issue_list_question(normalized_message: str) -> bool:
    mentions_issue = "issue" in normalized_message or "issues" in normalized_message
    asks_visibility = any(
        keyword in normalized_message
        for keyword in {"查看", "看到", "有哪些", "列表", "列出", "打开", "open"}
    )
    mentions_risk = any(
        keyword in normalized_message for keyword in {"风险", "为什么", "阻塞"}
    )
    return mentions_issue and asks_visibility and not mentions_risk


def is_github_check_list_question(normalized_message: str) -> bool:
    mentions_check = any(
        keyword in normalized_message
        for keyword in {"ci", "check", "checks", "检查", "测试"}
    )
    asks_visibility = any(
        keyword in normalized_message
        for keyword in {"查看", "看到", "有哪些", "列表", "列出", "打开", "open"}
    )
    mentions_risk = any(
        keyword in normalized_message for keyword in {"风险", "为什么", "阻塞"}
    )
    return mentions_check and asks_visibility and not mentions_risk
