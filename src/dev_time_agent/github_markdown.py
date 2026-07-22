import re
from collections.abc import Callable


def format_repository_list(repository_names: list[str]) -> str:
    items = "\n".join(f"- `{escape_markdown(name)}`" for name in repository_names)
    return f"**{len(repository_names)} 个 GitHub 仓库**\n\n{items}"


def format_pull_request_list(repository_name: str, pull_requests: list[dict]) -> str:
    return format_numbered_collection(
        repository_name,
        "PR",
        pull_requests,
        format_pull_request,
    )


def format_issue_list(repository_name: str, issues: list[dict]) -> str:
    return format_numbered_collection(
        repository_name,
        "Issue",
        issues,
        format_issue,
    )


def format_check_list(repository_name: str, checks: list[dict]) -> str:
    return format_numbered_collection(
        repository_name,
        "Check",
        checks,
        format_check,
    )


def format_numbered_collection(
    repository_name: str,
    label: str,
    items: list[dict],
    formatter: Callable[[dict], str],
) -> str:
    rows = "\n".join(
        f"{index}. {formatter(item)}" for index, item in enumerate(items, start=1)
    )
    return (
        f"**{escape_markdown(repository_name)}** · {len(items)} 条 {label}\n\n{rows}"
    )


def format_pull_request(pull_request: dict) -> str:
    number = pull_request.get("number", "?")
    title = escape_markdown(pull_request.get("title") or "Untitled")
    state = status_label(pull_request.get("state"))
    label = f"**PR #{number}** · {title}"
    return f"{markdown_link(label, pull_request.get('url'))}  \n   `{state}`"


def format_issue(issue: dict) -> str:
    number = issue.get("number", "?")
    title = escape_markdown(issue.get("title") or "Untitled")
    state = status_label(issue.get("state"))
    label = f"**Issue #{number}** · {title}"
    return f"{markdown_link(label, issue.get('url'))}  \n   `{state}`"


def format_check(check: dict) -> str:
    name = escape_markdown(check.get("name") or "Unknown check")
    status = status_label(check.get("status"))
    conclusion = status_label(check.get("conclusion") or "pending")
    label = f"**{name}**"
    return f"{markdown_link(label, check.get('url'))}  \n   `{status} · {conclusion}`"


def markdown_link(label: str, url: object) -> str:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return label
    return f"[{label}](<{normalized_url}>)"


def status_label(value: object) -> str:
    return str(value or "unknown").strip().lower()


def escape_markdown(value: object) -> str:
    normalized = " ".join(str(value).split())
    return re.sub(r"([\\`*_[\]<>])", r"\\\1", normalized)
