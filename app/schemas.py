from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


JobStatus = Literal["queued", "running", "reviewing", "completed", "failed"]


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

    def to_markdown(self) -> str:
        observation_lines = "\n".join(f"- {item}" for item in self.next_observation_points)
        return (
            "# 经济分析报告\n\n"
            f"## 本期概览\n{self.overview}\n\n"
            f"## 主要城市变化\n{self.city_changes}\n\n"
            f"## 收入分层信号\n{self.income_signals}\n\n"
            f"## 趋势与风险\n{self.risks}\n\n"
            f"## 结论\n{self.conclusion}\n\n"
            f"## 后续观察点\n{observation_lines}\n"
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


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    current_stage: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class ReportResponse(BaseModel):
    report_markdown: str
    chart_payloads: list[ChartPayload]
    evidence_summary: EvidencePack


class AgentRunRecord(BaseModel):
    id: int
    phase: str
    agent_name: str
    model_name: str | None = None
    status: str
    handoff_to: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
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


class TraceResponse(BaseModel):
    agent_runs: list[AgentRunRecord]
    tool_calls: list[ToolCallRecord]
