from dev_time_agent.entity_resolver import resolve_github_entities


def test_github_entity_resolver_prefers_longest_repository_name_match() -> None:
    repositories = [
        {
            "id": "repo_1001",
            "name": "dev-time",
            "full_name": "henry-insomniac/dev-time",
        },
        {
            "id": "repo_1002",
            "name": "dev-time-agent",
            "full_name": "henry-insomniac/dev-time-agent",
        },
    ]

    entities = resolve_github_entities("查看 dev-time-agent 的 PR", repositories)

    assert entities == {
        "repository": {
            "id": "repo_1002",
            "name": "dev-time-agent",
            "full_name": "henry-insomniac/dev-time-agent",
        }
    }
