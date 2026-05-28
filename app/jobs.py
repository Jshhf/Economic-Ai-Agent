from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.agents.orchestrator import (
    build_runtime,
    run_data_analyst_agent,
    run_economist_agent,
    run_economist_writer_agent,
    run_follow_up_fallback,
)
from app.config import PROJECT_ROOT, Settings
from app.schemas import EvidencePack, FinalReport, FollowUpRequest, GoalSummary, GoalSummaryResponse, JobSourcesResponse, ReportResponse, SupplementalEvidence, TraceResponse
from app.skills import get_skill
from app.storage import Storage


def classify_failure(exc: Exception) -> str:
    message = str(exc).lower()
    if "schema" in message or "validate" in message:
        return "schema_validation_error"
    if "mcp" in message:
        return "mcp_error"
    if "rag" in message or "knowledge" in message:
        return "rag_error"
    if "tool" in message:
        return "tool_error"
    return "model_error"


def build_goal_summary(
    *,
    skill_id: str,
    original_filename: str,
    current_stage: str,
    completed_steps: list[str] | None = None,
    resolved_questions: list[str] | None = None,
    open_questions: list[str] | None = None,
    key_findings: list[str] | None = None,
    next_action: str | None = None,
) -> GoalSummary:
    skill = get_skill(skill_id)
    return GoalSummary(
        overall_goal=(
            f"Analyze dataset `{original_filename}` with skill `{skill.skill_id}` ({skill.name}) "
            "and produce a structured analysis output."
        ),
        user_constraints=[
            "The runtime should prefer structured intermediate artifacts over free-form reasoning output.",
            "The final output must remain consistent with the configured skill and report schema.",
            "This summary tracks task mainline state rather than storing full conversation history.",
        ],
        output_requirements=[
            f"Generate the final output for skill `{skill.skill_id}`.",
            "Persist evidence, trace, metrics, and source references for later inspection.",
        ],
        current_stage=current_stage,
        completed_steps=completed_steps or [],
        resolved_questions=resolved_questions or [],
        open_questions=open_questions or [],
        key_findings=key_findings or [],
        next_action=next_action,
    )


def merge_key_findings(
    evidence: EvidencePack | None,
    supplemental: SupplementalEvidence | None = None,
) -> list[str]:
    findings: list[str] = []
    if evidence is not None:
        findings.extend(evidence.key_findings[:5])
    if supplemental is not None:
        findings.extend(supplemental.findings[:3])
    return findings


@dataclass(slots=True)
class JobRunner:
    settings: Settings
    storage: Storage

    def create_job_from_upload(self, upload_bytes: bytes, original_filename: str, *, skill_id: str) -> str:
        job_id = uuid.uuid4().hex
        suffix = Path(original_filename).suffix or ".csv"
        filename = f"{job_id}{suffix}"
        upload_path = PROJECT_ROOT / self.settings.upload_dir / filename
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(upload_bytes)
        self.storage.create_job(job_id, str(upload_path), original_filename, skill_id=skill_id)
        self.storage.create_goal_summary(
            job_id,
            skill_id,
            build_goal_summary(
                skill_id=skill_id,
                original_filename=original_filename,
                current_stage="queued",
                next_action="Start data analysis",
            ),
        )
        return job_id

    def create_job_from_file(self, source_path: str, *, skill_id: str) -> str:
        job_id = uuid.uuid4().hex
        path = Path(source_path)
        self.storage.create_job(job_id, str(path), path.name, skill_id=skill_id)
        self.storage.create_goal_summary(
            job_id,
            skill_id,
            build_goal_summary(
                skill_id=skill_id,
                original_filename=path.name,
                current_stage="queued",
                next_action="Start data analysis",
            ),
        )
        return job_id

    def enqueue(self, job_id: str) -> None:
        worker = threading.Thread(target=self.run_analysis_job, args=(job_id,), daemon=True)
        worker.start()

    def run_analysis_job(self, job_id: str) -> None:
        skill_id = self.storage.get_job_skill_id(job_id)
        source_path = self.storage.get_job_source_path(job_id)
        original_filename = Path(source_path).name
        try:
            runtime = build_runtime(job_id, source_path, self.storage, self.settings, skill_id=skill_id)
            self.storage.update_job_status(job_id, status="running", current_stage="data_analysis", started=True)
            self.storage.append_goal_summary(
                job_id,
                skill_id,
                build_goal_summary(
                    skill_id=skill_id,
                    original_filename=original_filename,
                    current_stage="data_analysis",
                    completed_steps=[],
                    next_action="Generate evidence pack from dataset tools",
                ),
            )
            runtime.observability.emit_metric("job_start_count", 1.0, job_id=job_id, labels={"skill_id": skill_id})
            runtime.observability.emit_metric("skill_selection_count", 1.0, job_id=job_id, labels={"skill_id": skill_id})

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
            self.storage.append_goal_summary(
                job_id,
                skill_id,
                build_goal_summary(
                    skill_id=skill_id,
                    original_filename=original_filename,
                    current_stage="economist_review",
                    completed_steps=["data_analysis"],
                    key_findings=merge_key_findings(evidence),
                    next_action="Review evidence and decide whether follow-up is needed",
                ),
            )
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
                self.storage.append_goal_summary(
                    job_id,
                    skill_id,
                    build_goal_summary(
                        skill_id=skill_id,
                        original_filename=original_filename,
                        current_stage="economist_follow_up",
                        completed_steps=["data_analysis", "economist_review"],
                        open_questions=[economist_result.reason],
                        key_findings=merge_key_findings(evidence),
                        next_action="Run targeted follow-up analysis",
                    ),
                )
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
                supplemental_artifact = self.storage.get_latest_artifact(job_id, "supplemental_evidence")
                supplemental_evidence = SupplementalEvidence.model_validate(supplemental_artifact["content_json"])
                self.storage.update_job_status(job_id, status="reviewing", current_stage="economist_writer")
                self.storage.append_goal_summary(
                    job_id,
                    skill_id,
                    build_goal_summary(
                        skill_id=skill_id,
                        original_filename=original_filename,
                        current_stage="economist_writer",
                        completed_steps=["data_analysis", "economist_review", "economist_follow_up"],
                        resolved_questions=[economist_result.reason],
                        key_findings=merge_key_findings(evidence, supplemental_evidence),
                        next_action="Draft final report",
                    ),
                )
                final_report = run_economist_writer_agent(runtime)
            else:
                final_report = economist_result
                self.storage.append_goal_summary(
                    job_id,
                    skill_id,
                    build_goal_summary(
                        skill_id=skill_id,
                        original_filename=original_filename,
                        current_stage="economist_writer",
                        completed_steps=["data_analysis", "economist_review"],
                        key_findings=merge_key_findings(evidence),
                        next_action="Finalize report output",
                    ),
                )

            markdown_report = final_report.to_markdown()
            output_path = PROJECT_ROOT / self.settings.output_dir / f"{job_id}_report.md"
            output_path.write_text(markdown_report, encoding="utf-8")

            self.storage.add_artifact(job_id, "json", "final_report", content_json=final_report.model_dump())
            self.storage.add_artifact(job_id, "text", "report_markdown", content_text=markdown_report)
            self.storage.add_artifact(job_id, "text", "report_path", content_text=str(output_path))
            self.storage.add_artifact(job_id, "json", "sources", content_json=[item.model_dump() for item in final_report.sources])

            self.storage.update_job_status(job_id, status="completed", current_stage="completed", finished=True)
            self.storage.append_goal_summary(
                job_id,
                skill_id,
                build_goal_summary(
                    skill_id=skill_id,
                    original_filename=original_filename,
                    current_stage="completed",
                    completed_steps=[
                        "data_analysis",
                        "economist_review",
                        "economist_writer",
                    ]
                    + (["economist_follow_up"] if isinstance(economist_result, FollowUpRequest) else []),
                    key_findings=merge_key_findings(evidence, runtime.supplemental_evidence),
                    next_action="Task completed",
                ),
            )
            runtime.observability.emit_metric("job_success_rate", 1.0, job_id=job_id, labels={"skill_id": skill_id})
        except Exception as exc:
            failure_category = classify_failure(exc)
            self.storage.update_job_status(
                job_id,
                status="failed",
                current_stage="failed",
                error_message=str(exc),
                failure_category=failure_category,
                finished=True,
            )
            latest_summary: GoalSummary | None = None
            try:
                latest_summary = self.storage.get_latest_goal_summary(job_id).summary
            except KeyError:
                latest_summary = None
            self.storage.append_goal_summary(
                job_id,
                skill_id,
                build_goal_summary(
                    skill_id=skill_id,
                    original_filename=original_filename,
                    current_stage="failed",
                    completed_steps=latest_summary.completed_steps if latest_summary else [],
                    resolved_questions=latest_summary.resolved_questions if latest_summary else [],
                    open_questions=latest_summary.open_questions if latest_summary else [],
                    key_findings=latest_summary.key_findings if latest_summary else [],
                    next_action="Investigate failure",
                ),
            )
            self.storage.log_metric("job_failure_count", 1.0, job_id=job_id, labels={"skill_id": skill_id, "failure_category": failure_category})

    def get_report_response(self, job_id: str) -> ReportResponse:
        report_markdown = self.storage.get_latest_artifact(job_id, "report_markdown")["content_text"]
        evidence = EvidencePack.model_validate(self.storage.get_latest_artifact(job_id, "evidence_pack")["content_json"])
        charts = self.storage.get_latest_artifact(job_id, "chart_payloads")["content_json"]
        sources_artifact = self.storage.get_latest_artifact(job_id, "sources")
        return ReportResponse(
            report_markdown=report_markdown,
            chart_payloads=charts,
            evidence_summary=evidence,
            skill_id=self.storage.get_job_skill_id(job_id),
            sources=sources_artifact.get("content_json", []),
        )

    def get_trace_response(self, job_id: str) -> TraceResponse:
        return TraceResponse(
            agent_runs=self.storage.list_agent_runs(job_id),
            tool_calls=self.storage.list_tool_calls(job_id),
            metrics=self.storage.list_metrics(job_id),
        )

    def get_sources_response(self, job_id: str) -> JobSourcesResponse:
        return JobSourcesResponse(
            job_id=job_id,
            skill_id=self.storage.get_job_skill_id(job_id),
            sources=self.storage.list_sources(job_id),
        )

    def get_goal_summary_response(self, job_id: str) -> GoalSummaryResponse:
        return self.storage.get_latest_goal_summary(job_id)

    def validate_skill(self, skill_id: str) -> str:
        get_skill(skill_id)
        return skill_id
