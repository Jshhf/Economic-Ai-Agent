from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class KnowledgeBase:
    knowledge_dir: Path

    def read_document(self, filename: str) -> str:
        target = self.knowledge_dir / filename
        if not target.exists():
            raise FileNotFoundError(f"Knowledge document not found: {target}")
        return target.read_text(encoding="utf-8")

    def list_documents(self) -> list[str]:
        return sorted(path.name for path in self.knowledge_dir.glob("*.md"))

    def read_indicator_definitions(self) -> str:
        return self.read_document("indicator_definitions.md")

    def read_methodology_notes(self) -> str:
        return self.read_document("methodology_notes.md")

    def read_report_rubric(self) -> str:
        return self.read_document("report_rubric.md")
