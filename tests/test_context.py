from dev_time_agent.context import assemble_agent_context


def test_agent_context_includes_github_capability_metadata() -> None:
    context = assemble_agent_context(
        user_message="查看 dev-time-agent 的 PR",
        project_id="project_repo_1001",
        risk_assessment_id="risk_project_repo_1001",
        memory={},
        evidence_bundle=None,
        available_tools=["github.repos.list", "github.pull_requests.list"],
    )

    github_capabilities = context["capability_registry"]["github"]

    assert "github.pull_requests.list" in github_capabilities
    assert github_capabilities["github.pull_requests.list"]["required_entities"] == [
        "repository"
    ]
    assert github_capabilities["github.pull_requests.list"]["permissions"] == [
        "pull_requests:read"
    ]


def test_agent_context_retrieves_docs_for_concept_questions() -> None:
    context = assemble_agent_context(
        user_message="什么是 GitHub 能力层？",
        project_id="project_repo_1001",
        risk_assessment_id="risk_project_repo_1001",
        memory={},
        evidence_bundle=None,
        available_tools=[],
    )

    assert context["retrieved_docs"]["available"] is True
    first = context["retrieved_docs"]["chunks"][0]
    assert first["citation_ref"] == "doc:.claude/github-capability-layer.md"
    assert first["source_title"] == "GitHub 能力层架构"
