from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.schemas import SourceReference


def _tokenize(text: str) -> set[str]:
    normalized = (
        text.lower()
        .replace("\n", " ")
        .replace("`", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("/", " ")
    )
    return {token for token in normalized.split() if token}


@dataclass(slots=True)
class KnowledgeChunk:
    source_id: str
    title: str
    excerpt: str
    source_type: str
    provider: str
    url: str | None = None


@dataclass(slots=True)
class RagService:
    knowledge_dir: Path
    _chunks: list[KnowledgeChunk] | None = None

    def _load_chunks(self) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for path in sorted(self.knowledge_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            parts = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
            for index, part in enumerate(parts):
                chunks.append(
                    KnowledgeChunk(
                        source_id=f"{path.stem}-{index}",
                        title=path.stem.replace("_", " ").title(),
                        excerpt=part[:500],
                        source_type="local_knowledge",
                        provider="knowledge-base",
                    )
                )
        return chunks

    @property
    def chunks(self) -> list[KnowledgeChunk]:
        if self._chunks is None:
            self._chunks = self._load_chunks()
        return self._chunks

    def search(self, query: str, *, limit: int = 5) -> list[SourceReference]:
        query_tokens = _tokenize(query)
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self.chunks:
            excerpt_tokens = _tokenize(f"{chunk.title} {chunk.excerpt}")
            overlap = len(query_tokens.intersection(excerpt_tokens))
            if overlap <= 0:
                # Fallback to a tiny baseline score so local knowledge can still be surfaced
                # even when the query language differs from the document language.
                score = 0.05
            else:
                score = overlap / max(len(query_tokens), 1)
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SourceReference(
                source_id=chunk.source_id,
                title=chunk.title,
                source_type="local_knowledge",
                provider=chunk.provider,
                summary=chunk.excerpt[:200],
                excerpt=chunk.excerpt,
                score=round(score, 4),
            )
            for score, chunk in scored[:limit]
        ]
