from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.agents.orchestrator import build_runtime, run_data_analyst_agent, run_economist_agent, run_economist_writer_agent, run_follow_up_fallback
from app.config import PROJECT_ROOT, Settings
from app.schemas import EvidencePack, FinalReport, FollowUpRequest, ReportResponse, SupplementalEvidence, TraceResponse
from app.storage import Storage


@dataclass(slots=True)
class JobRunner:
    settings: Settings
    storage: Storage

    def create_job_from_upload(self, upload_bytes: bytes, original_filename: str) -> str:
        job_id = uuid.uuid4().hex
        suffix = Path(original_filename).suffix or ".csv"
        filename = f"{job_id}{suffix}"
        upload_path = PROJECT_ROOT / self.settings.upload_dir / filename
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(upload_bytes)
        self.storage.create_job(job_id, str(upload_path), original_filename)
        return job_id

    def create_job_from_file(self, source_path: str) -> str:
        job_id = uuid.uuid4().hex
        path = Path(source_path)
        self.storage.create_job(job_id, str(path), path.name)
        return job_id

    def enqueue(self, job_id: str) -> None:
        worker = threading.Thread(target=self.run_analysis_job, args=(job_id,), daemon=True)
        worker.start()

    def run_analysis_job(self, job_id: str) -> None:
        try:
            source_path = self.storage.get_job_source_path(job_id)
            runtime = build_runtime(job_id, source_path, self.storage, self.settings)
            self.storage.update_job_status(job_id, status="running", current_stage="data_analysis", started=True)

            evidence = run_data_analyst_agent(runtime)
            self.storage.add_artifact(job_id, "json", "evidence_pack", content_json=evidence.model_dump())
            chart_payloads = runtime.analytics.build_chart_payloads()
            self.storage.add_artifact(
                job_id,
                "json",
                "chart_payloads",
                content_json=[item.model_dump() for item in chart_payloads],
            )

            self.storage.update_job_status(job_id, status="reviewing", current_stage="economist_review")
            economist_result = run_economist_agent(runtime)

            final_report: FinalReport
            if isinstance(economist_result, FollowUpRequest):
                self.storage.add_artifact(
                    job_id,
                    "json",
                    "follow_up_request",
                    content_json=economist_result.model_dump(),
                )
                self.storage.update_job_status(job_id, status="reviewing", current_stage="economist_follow_up")
                if runtime.use_openai:
                    self.storage.add_artifact(
                        job_id,
                        "json",
                        "supplemental_evidence",
                        content_json=runtime.supplemental_evidence.model_dump() if runtime.supplemental_evidence else {},
                    )
                else:
                    supplemental = run_follow_up_fallback(runtime)
                    self.storage.add_artifact(
                        job_id,
                        "json",
                        "supplemental_evidence",
                        content_json=supplemental.model_dump(),
                    )
                self.storage.update_job_status(job_id, status="reviewing", current_stage="economist_writer")
                final_report = run_economist_writer_agent(runtime)
            else:
                final_report = economist_result

            markdown_report = final_report.to_markdown()
            output_path = PROJECT_ROOT / self.settings.output_dir / f"{job_id}_report.md"
            output_path.write_text(markdown_report, encoding="utf-8")

            self.storage.add_artifact(job_id, "json", "final_report", content_json=final_report.model_dump())
            self.storage.add_artifact(job_id, "text", "report_markdown", content_text=markdown_report)
            self.storage.add_artifact(job_id, "text", "report_path", content_text=str(output_path))

            self.storage.update_job_status(job_id, status="completed", current_stage="completed", finished=True)
        except Exception as exc:
            self.storage.update_job_status(
                job_id,
                status="failed",
                current_stage="failed",
                error_message=str(exc),
                finished=True,
            )

    def get_report_response(self, job_id: str) -> ReportResponse:
        report_markdown = self.storage.get_latest_artifact(job_id, "report_markdown")["content_text"]
        evidence = EvidencePack.model_validate(self.storage.get_latest_artifact(job_id, "evidence_pack")["content_json"])
        charts = self.storage.get_latest_artifact(job_id, "chart_payloads")["content_json"]
        return ReportResponse(
            report_markdown=report_markdown,
            chart_payloads=charts,
            evidence_summary=evidence,
        )

    def get_trace_response(self, job_id: str) -> TraceResponse:
        return TraceResponse(
            agent_runs=self.storage.list_agent_runs(job_id),
            tool_calls=self.storage.list_tool_calls(job_id),
        )
