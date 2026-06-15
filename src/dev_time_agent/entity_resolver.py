def resolve_github_entities(
    message: str,
    repositories: list[dict],
) -> dict:
    repository = resolve_repository(message, repositories)
    if repository is None:
        return {}
    return {"repository": repository_entity(repository)}


def resolve_repository(message: str, repositories: list[dict]) -> dict | None:
    normalized_message = message.strip().lower()
    for repository in repositories:
        full_name = str(repository.get("full_name", "")).lower()
        if full_name and full_name in normalized_message:
            return repository

    matches: list[dict] = []
    longest_match_length = 0
    for repository in repositories:
        name = str(repository.get("name", "")).lower()
        if not name or name not in normalized_message:
            continue
        if len(name) > longest_match_length:
            matches = [repository]
            longest_match_length = len(name)
            continue
        if len(name) == longest_match_length:
            matches.append(repository)

    if len(matches) == 1:
        return matches[0]
    if len(repositories) == 1:
        return repositories[0]
    return None


def repository_entity(repository: dict) -> dict:
    return {
        "id": str(repository.get("id", "")),
        "name": str(repository.get("name") or ""),
        "full_name": str(repository.get("full_name") or ""),
    }
