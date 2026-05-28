from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


JobStatus = Literal["queued", "running", "reviewing", "completed", "failed"]
FailureCategory = Literal[
    "model_error",
    "tool_error",
    "rag_error",
    "mcp_error",
    "schema_validation_error",
]
CallKind = Literal["tool", "rag", "mcp"]
SourceType = Literal["local_knowledge", "mcp_economic_data", "mcp_research", "dataset"]


class SourceReference(BaseModel):
    source_id: str
    title: str
    source_type: SourceType
    provider: str
    summary: str
    excerpt: str | None = None
    url: str | None = None
    score: float = 0.0


class DatasetOverview(BaseModel):
    row_count: int
    city_count: int
    columns: list[str]
    start_date: str
    end_date: str
    missing_values: dict[str, int]


class CityMetric(BaseModel):
    cityid: int
    value: float


class TrendPoint(BaseModel):
    period: str
    value: float


class CityTrend(BaseModel):
    cityid: int
    points: list[TrendPoint]


class IncomeSignal(BaseModel):
    segment: str
    latest_value: float | None = None
    recent_average: float | None = None
    gap_vs_overall: float | None = None


class AnomalyRecord(BaseModel):
    cityid: int
    metric: str
    latest_value: float
    zscore: float | None = None
    reason: str


class EvidencePack(BaseModel):
    dataset_overview: DatasetOverview
    latest_period: str
    overall_emp_change: float
    top_cities: list[CityMetric]
    bottom_cities: list[CityMetric]
    income_group_signals: list[IncomeSignal]
    recent_trends: list[TrendPoint]
    anomalies: list[AnomalyRecord]
    data_quality_notes: list[str]
    key_findings: list[str]


class FollowUpRequest(BaseModel):
    reason: str
    required_tools: list[str]
    focus_cities: list[int] = Field(default_factory=list)
    focus_income_groups: list[str] = Field(default_factory=list)


class SupplementalEvidence(BaseModel):
    reason: str
    findings: list[str]
    city_trends: list[CityTrend] = Field(default_factory=list)
    income_group_details: list[IncomeSignal] = Field(default_factory=list)
    anomalies: list[AnomalyRecord] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)


class FinalReport(BaseModel):
    overview: str
    city_changes: str
    income_signals: str
    risks: str
    conclusion: str
    next_observation_points: list[str]
    skill_id: str = "economic_report"
    skill_name: str = "Economic Report"
    sources: list[SourceReference] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        observation_lines = "\n".join(f"- {item}" for item in self.next_observation_points)
        source_lines = "\n".join(
            f"- **{item.title}** ({item.provider})"
            + (f": {item.summary}" if item.summary else "")
            + (f" [{item.url}]({item.url})" if item.url else "")
            for item in self.sources
        )
        source_block = f"\n## References\n{source_lines}\n" if source_lines else ""
        return (
            f"# Economic Analysis Report\n\n"
            f"> Skill: `{self.skill_id}` ({self.skill_name})\n\n"
            f"## Overview\n{self.overview}\n\n"
            f"## City Changes\n{self.city_changes}\n\n"
            f"## Income Signals\n{self.income_signals}\n\n"
            f"## Risks\n{self.risks}\n\n"
            f"## Conclusion\n{self.conclusion}\n\n"
            f"## Next Observation Points\n{observation_lines}\n"
            f"{source_block}"
        )


class EconomistDecisionEnvelope(BaseModel):
    decision_type: Literal["follow_up", "final_report"]
    follow_up_request: FollowUpRequest | None = None
    final_report: FinalReport | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "EconomistDecisionEnvelope":
        if self.decision_type == "follow_up" and self.follow_up_request is None:
            raise ValueError("follow_up_request is required when decision_type is follow_up")
        if self.decision_type == "final_report" and self.final_report is None:
            raise ValueError("final_report is required when decision_type is final_report")
        return self


class ChartPayload(BaseModel):
    chart_type: str
    title: str
    labels: list[str]
    datasets: list[dict[str, Any]]


class SkillDefinition(BaseModel):
    skill_id: str
    name: str
    description: str
    scenarios: list[str]
    available_tools: list[str]
    rag_enabled: bool
    mcp_sources: list[str]
    output_type: str = "FinalReport"
    stage_disclosures: dict[str, "SkillStageDisclosure"] = Field(default_factory=dict)


class SkillStageDisclosure(BaseModel):
    stage: str
    stage_goal: str
    allowed_tools: list[str] = Field(default_factory=list)
    rag_enabled: bool = False
    mcp_sources: list[str] = Field(default_factory=list)
    output_type: str | None = None
    disclosure_rationale: str | None = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[SourceReference]


class JobSourcesResponse(BaseModel):
    job_id: str
    skill_id: str
    sources: list[SourceReference]


class GoalSummary(BaseModel):
    overall_goal: str
    user_constraints: list[str] = Field(default_factory=list)
    output_requirements: list[str] = Field(default_factory=list)
    current_stage: str
    completed_steps: list[str] = Field(default_factory=list)
    resolved_questions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    next_action: str | None = None


class GoalSummaryResponse(BaseModel):
    job_id: str
    skill_id: str
    version: int
    summary: GoalSummary
    created_at: datetime


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    skill_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    current_stage: str
    skill_id: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    failure_category: FailureCategory | None = None


class ReportResponse(BaseModel):
    report_markdown: str
    chart_payloads: list[ChartPayload]
    evidence_summary: EvidencePack
    skill_id: str
    sources: list[SourceReference] = Field(default_factory=list)


class AgentRunRecord(BaseModel):
    id: int
    phase: str
    agent_name: str
    model_name: str | None = None
    status: str
    handoff_to: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    skill_id: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ToolCallRecord(BaseModel):
    id: int
    phase: str
    agent_name: str
    tool_name: str
    arguments_json: str | None = None
    result_summary: str | None = None
    success: bool | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    call_kind: CallKind = "tool"
    provider: str | None = None


class TraceResponse(BaseModel):
    agent_runs: list[AgentRunRecord]
    tool_calls: list[ToolCallRecord]
    metrics: dict[str, Any] = Field(default_factory=dict)
