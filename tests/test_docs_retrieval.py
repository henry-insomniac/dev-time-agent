from pathlib import Path

from dev_time_agent.docs_retrieval import retrieve_docs


def test_docs_retrieval_returns_stable_citation_for_exact_keyword_match() -> None:
    chunks = retrieve_docs(
        "GitHub 能力层",
        docs_root=Path(".claude"),
    )

    assert chunks
    first = chunks[0]
    assert first.id == "doc:.claude/github-capability-layer.md"
    assert first.source_title == "GitHub 能力层架构"
    assert first.source_path == ".claude/github-capability-layer.md"
    assert first.freshness != ""
    assert first.citation_ref == "doc:.claude/github-capability-layer.md"
    assert "GitHub 能力层" in first.content


def test_docs_retrieval_returns_empty_list_when_no_keyword_matches() -> None:
    assert retrieve_docs("totally-unmatched-query-xyz", docs_root=Path(".claude")) == []
