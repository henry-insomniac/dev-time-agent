from datetime import UTC, datetime
from pathlib import Path
import re

from pydantic import BaseModel


class RetrievedDocChunk(BaseModel):
    id: str
    source_title: str
    source_path: str
    freshness: str
    citation_ref: str
    content: str


def retrieve_docs(
    query: str,
    *,
    docs_root: Path | None = None,
    limit: int = 3,
) -> list[RetrievedDocChunk]:
    root = docs_root or default_docs_root()
    if not root.exists():
        return []
    query_text = query.strip().lower()
    if query_text == "":
        return []

    matches: list[tuple[int, RetrievedDocChunk]] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = doc_title(text, path)
        score = score_doc(query_text, text) + score_doc(query_text, title) * 5
        if score <= 0:
            continue
        source_path = stable_source_path(root, path)
        citation_ref = f"doc:{source_path}"
        matches.append(
            (
                score,
                RetrievedDocChunk(
                    id=citation_ref,
                    source_title=title,
                    source_path=source_path,
                    freshness=doc_freshness(path),
                    citation_ref=citation_ref,
                    content=text[:1600],
                ),
            )
        )

    matches.sort(key=lambda item: (-item[0], item[1].source_path))
    return [chunk for _, chunk in matches[:limit]]


def default_docs_root() -> Path:
    return Path(__file__).resolve().parents[2] / ".claude"


def score_doc(query: str, text: str) -> int:
    haystack = text.lower()
    if query in haystack:
        return len(query) * 10
    normalized_query = re.sub(r"[^\w\u4e00-\u9fff]+", " ", query)
    return sum(len(token) for token in normalized_query.split() if token in haystack)


def stable_source_path(root: Path, path: Path) -> str:
    root_label = root.name
    return f"{root_label}/{path.relative_to(root).as_posix()}"


def doc_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return path.stem


def doc_freshness(path: Path) -> str:
    modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return modified.date().isoformat()
