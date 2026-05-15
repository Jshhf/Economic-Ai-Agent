from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    app_name: str = "Economic Agent Platform"
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8000"))
    database_path: Path = Path(os.getenv("DATABASE_PATH", "runtime/analysis.db"))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "runtime/uploads"))
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", "output"))
    knowledge_dir: Path = Path(os.getenv("KNOWLEDGE_DIR", "knowledge"))
    data_agent_model: str = os.getenv("DATA_AGENT_MODEL", "gpt-5.4-mini")
    economist_agent_model: str = os.getenv("ECONOMIST_AGENT_MODEL", "gpt-5.5")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

    def ensure_directories(self, project_root: Path) -> None:
        for relative_path in (
            self.database_path.parent,
            self.upload_dir,
            self.output_dir,
            self.knowledge_dir,
        ):
            (project_root / relative_path).mkdir(parents=True, exist_ok=True)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories(PROJECT_ROOT)
    return settings

