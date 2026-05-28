from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.schemas import AgentRunRecord, GoalSummary, GoalSummaryResponse, JobStatusResponse, SourceReference, ToolCallRecord


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def summarize_payload(payload: Any, limit: int = 600) -> str:
    if payload is None:
        return ""
    if hasattr(payload, "model_dump_json"):
        text = payload.model_dump_json()
    elif isinstance(payload, (dict, list)):
        text = json.dumps(payload, ensure_ascii=False)
    else:
        text = str(payload)
    return text[:limit]


@dataclass(slots=True)
class Storage:
    database_path: Path

    def __post_init__(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    skill_id TEXT NOT NULL DEFAULT 'economic_report',
                    status TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    error_message TEXT,
                    failure_category TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_key TEXT NOT NULL,
                    content_json TEXT,
                    content_text TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    model_name TEXT,
                    status TEXT NOT NULL,
                    handoff_to TEXT,
                    input_summary TEXT,
                    output_summary TEXT,
                    skill_id TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );

                CREATE TABLE IF NOT EXISTS tool_call_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    call_id TEXT NOT NULL UNIQUE,
                    phase TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT,
                    result_summary TEXT,
                    success INTEGER,
                    call_kind TEXT NOT NULL DEFAULT 'tool',
                    provider TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_ms INTEGER
                );

                CREATE TABLE IF NOT EXISTS source_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    excerpt TEXT,
                    url TEXT,
                    score REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metrics_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    labels_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS goal_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "analysis_jobs", "skill_id", "TEXT NOT NULL DEFAULT 'economic_report'")
            self._ensure_column(conn, "analysis_jobs", "failure_category", "TEXT")
            self._ensure_column(conn, "agent_runs", "skill_id", "TEXT")
            self._ensure_column(conn, "tool_call_logs", "call_kind", "TEXT NOT NULL DEFAULT 'tool'")
            self._ensure_column(conn, "tool_call_logs", "provider", "TEXT")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_job(self, job_id: str, source_path: str, original_filename: str, *, skill_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_jobs (
                    job_id, source_path, original_filename, skill_id, status, current_stage, created_at
                ) VALUES (?, ?, ?, ?, 'queued', 'queued', ?)
                """,
                (job_id, source_path, original_filename, skill_id, iso_now()),
            )

    def update_job_status(
        self,
        job_id: str,
        *,
        status: str,
        current_stage: str,
        error_message: str | None = None,
        failure_category: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        fields = ["status = ?", "current_stage = ?", "error_message = ?", "failure_category = ?"]
        values: list[Any] = [status, current_stage, error_message, failure_category]
        if started:
            fields.append("started_at = ?")
            values.append(iso_now())
        if finished:
            fields.append("finished_at = ?")
            values.append(iso_now())
        values.append(job_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE analysis_jobs SET {', '.join(fields)} WHERE job_id = ?",
                values,
            )

    def get_job(self, job_id: str) -> JobStatusResponse:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return JobStatusResponse(
            job_id=row["job_id"],
            status=row["status"],
            current_stage=row["current_stage"],
            skill_id=row["skill_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            error_message=row["error_message"],
            failure_category=row["failure_category"],
        )

    def get_job_source_path(self, job_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT source_path FROM analysis_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return str(row["source_path"])

    def get_job_skill_id(self, job_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT skill_id FROM analysis_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return str(row["skill_id"])

    def add_artifact(
        self,
        job_id: str,
        artifact_type: str,
        artifact_key: str,
        *,
        content_json: Any | None = None,
        content_text: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    job_id, artifact_type, artifact_key, content_json, content_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    artifact_type,
                    artifact_key,
                    json.dumps(content_json, ensure_ascii=False) if content_json is not None else None,
                    content_text,
                    iso_now(),
                ),
            )

    def get_latest_artifact(self, job_id: str, artifact_key: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT content_json, content_text
                FROM artifacts
                WHERE job_id = ? AND artifact_key = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (job_id, artifact_key),
            ).fetchone()
        if row is None:
            raise KeyError((job_id, artifact_key))
        payload: dict[str, Any] = {}
        if row["content_json"] is not None:
            payload["content_json"] = json.loads(row["content_json"])
        if row["content_text"] is not None:
            payload["content_text"] = row["content_text"]
        return payload

    def log_agent_result(
        self,
        job_id: str,
        *,
        phase: str,
        agent_name: str,
        model_name: str | None,
        status: str,
        input_summary: str | None = None,
        output_summary: str | None = None,
        handoff_to: str | None = None,
        skill_id: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_runs (
                    job_id, phase, agent_name, model_name, status, handoff_to,
                    input_summary, output_summary, skill_id, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    phase,
                    agent_name,
                    model_name,
                    status,
                    handoff_to,
                    input_summary,
                    output_summary,
                    skill_id,
                    iso_now(),
                    iso_now(),
                ),
            )

    def log_tool_start(
        self,
        job_id: str,
        *,
        call_id: str,
        phase: str,
        agent_name: str,
        tool_name: str,
        arguments_json: str | None,
        call_kind: str = "tool",
        provider: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tool_call_logs (
                    job_id, call_id, phase, agent_name, tool_name, arguments_json, call_kind, provider, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, call_id, phase, agent_name, tool_name, arguments_json, call_kind, provider, iso_now()),
            )

    def log_tool_end(
        self,
        job_id: str,
        *,
        call_id: str,
        result_summary: str,
        success: bool,
    ) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT started_at FROM tool_call_logs WHERE job_id = ? AND call_id = ?",
                (job_id, call_id),
            ).fetchone()
            started_at = datetime.fromisoformat(row["started_at"]) if row else utcnow()
            duration_ms = int((utcnow() - started_at).total_seconds() * 1000)
            conn.execute(
                """
                UPDATE tool_call_logs
                SET result_summary = ?, success = ?, finished_at = ?, duration_ms = ?
                WHERE job_id = ? AND call_id = ?
                """,
                (result_summary, int(success), iso_now(), duration_ms, job_id, call_id),
            )

    def add_source_reference(self, job_id: str, source: SourceReference) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_references (
                    job_id, source_id, source_type, provider, title, summary, excerpt, url, score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    source.source_id,
                    source.source_type,
                    source.provider,
                    source.title,
                    source.summary,
                    source.excerpt,
                    source.url,
                    source.score,
                    iso_now(),
                ),
            )

    def list_sources(self, job_id: str) -> list[SourceReference]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT source_id, source_type, provider, title, summary, excerpt, url, score
                FROM source_references
                WHERE job_id = ?
                ORDER BY score DESC, id ASC
                """,
                (job_id,),
            ).fetchall()
        return [
            SourceReference(
                source_id=row["source_id"],
                source_type=row["source_type"],
                provider=row["provider"],
                title=row["title"],
                summary=row["summary"],
                excerpt=row["excerpt"],
                url=row["url"],
                score=float(row["score"]),
            )
            for row in rows
        ]

    def create_goal_summary(self, job_id: str, skill_id: str, summary: GoalSummary) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO goal_summaries (job_id, skill_id, version, summary_json, created_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (job_id, skill_id, summary.model_dump_json(), iso_now()),
            )

    def append_goal_summary(self, job_id: str, skill_id: str, summary: GoalSummary) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS latest_version FROM goal_summaries WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            next_version = int(row["latest_version"]) + 1 if row is not None else 1
            conn.execute(
                """
                INSERT INTO goal_summaries (job_id, skill_id, version, summary_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, skill_id, next_version, summary.model_dump_json(), iso_now()),
            )

    def get_latest_goal_summary(self, job_id: str) -> GoalSummaryResponse:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT job_id, skill_id, version, summary_json, created_at
                FROM goal_summaries
                WHERE job_id = ?
                ORDER BY version DESC, id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError((job_id, "goal_summary"))
        return GoalSummaryResponse(
            job_id=row["job_id"],
            skill_id=row["skill_id"],
            version=int(row["version"]),
            summary=GoalSummary.model_validate_json(row["summary_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def list_goal_summaries(self, job_id: str) -> list[GoalSummaryResponse]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id, skill_id, version, summary_json, created_at
                FROM goal_summaries
                WHERE job_id = ?
                ORDER BY version ASC, id ASC
                """,
                (job_id,),
            ).fetchall()
        return [
            GoalSummaryResponse(
                job_id=row["job_id"],
                skill_id=row["skill_id"],
                version=int(row["version"]),
                summary=GoalSummary.model_validate_json(row["summary_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def log_metric(self, metric_name: str, metric_value: float, *, job_id: str | None = None, labels: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO metrics_log (job_id, metric_name, metric_value, labels_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    metric_name,
                    metric_value,
                    json.dumps(labels, ensure_ascii=False) if labels else None,
                    iso_now(),
                ),
            )

    def list_metrics(self, job_id: str | None = None) -> dict[str, Any]:
        query = "SELECT metric_name, metric_value, labels_json FROM metrics_log"
        params: tuple[Any, ...] = ()
        if job_id is not None:
            query += " WHERE job_id = ?"
            params = (job_id,)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        metrics: dict[str, Any] = {}
        for row in rows:
            metrics.setdefault(row["metric_name"], []).append(
                {
                    "value": row["metric_value"],
                    "labels": json.loads(row["labels_json"]) if row["labels_json"] else {},
                }
            )
        return metrics

    def list_agent_runs(self, job_id: str) -> list[AgentRunRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_runs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
        return [
            AgentRunRecord(
                id=row["id"],
                phase=row["phase"],
                agent_name=row["agent_name"],
                model_name=row["model_name"],
                status=row["status"],
                handoff_to=row["handoff_to"],
                input_summary=row["input_summary"],
                output_summary=row["output_summary"],
                skill_id=row["skill_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            )
            for row in rows
        ]

    def list_tool_calls(self, job_id: str) -> list[ToolCallRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_call_logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
        return [
            ToolCallRecord(
                id=row["id"],
                phase=row["phase"],
                agent_name=row["agent_name"],
                tool_name=row["tool_name"],
                arguments_json=row["arguments_json"],
                result_summary=row["result_summary"],
                success=bool(row["success"]) if row["success"] is not None else None,
                started_at=datetime.fromisoformat(row["started_at"]),
                finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
                duration_ms=row["duration_ms"],
                call_kind=row["call_kind"] or "tool",
                provider=row["provider"],
            )
            for row in rows
        ]
