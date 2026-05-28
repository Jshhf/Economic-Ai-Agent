from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents import Agent, ModelSettings, RunContextWrapper, RunHooks, Runner, function_tool, handoff

from app.config import PROJECT_ROOT, Settings
from app.schemas import (
    CityMetric,
    EvidencePack,
    FinalReport,
    FollowUpRequest,
    SourceReference,
    SupplementalEvidence,
)
from app.services.analytics import AnalyticsService
from app.services.knowledge_base import KnowledgeBase
from app.services.mcp import MCPRegistry, build_default_mcp_registry
from app.services.observability import ObservabilityService
from app.services.rag import RagService
from app.skills import SkillRuntimeConfig, get_skill, get_skill_runtime
from app.storage import Storage, summarize_payload


@dataclass(slots=True)
class AgentRuntime:
    job_id: str
    skill_id: str
    storage: Storage
    settings: Settings
    analytics: AnalyticsService
    knowledge_base: KnowledgeBase
    rag: RagService
    mcp_registry: MCPRegistry
    observability: ObservabilityService
    phase: str
    evidence_pack: EvidencePack | None = None
    follow_up_request: FollowUpRequest | None = None
    supplemental_evidence: SupplementalEvidence | None = None
    source_references: list[SourceReference] = field(default_factory=list)
    local_trace: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def use_openai(self) -> bool:
        return bool(self.settings.openai_api_key)

    @property
    def skill(self) -> SkillRuntimeConfig:
        return get_skill_runtime(self.skill_id)


def build_goal_summary_block(runtime: AgentRuntime) -> str:
    try:
        goal_summary = runtime.storage.get_latest_goal_summary(runtime.job_id).summary
    except KeyError:
        return "Goal Summary:\n- unavailable"
    return (
        "Goal Summary:\n"
        f"- overall_goal: {goal_summary.overall_goal}\n"
        f"- current_stage: {goal_summary.current_stage}\n"
        f"- completed_steps: {goal_summary.completed_steps}\n"
        f"- resolved_questions: {goal_summary.resolved_questions}\n"
        f"- open_questions: {goal_summary.open_questions}\n"
        f"- key_findings: {goal_summary.key_findings}\n"
        f"- next_action: {goal_summary.next_action or 'none'}"
    )


def _call_id(name: str) -> str:
    return f"{name}-{uuid.uuid4().hex}"


def _log_call_start(
    runtime: AgentRuntime,
    *,
    agent_name: str,
    tool_name: str,
    arguments: dict[str, Any],
    call_kind: str = "tool",
    provider: str | None = None,
) -> str:
    call_id = _call_id(tool_name)
    runtime.storage.log_tool_start(
        runtime.job_id,
        call_id=call_id,
        phase=runtime.phase,
        agent_name=agent_name,
        tool_name=tool_name,
        arguments_json=json.dumps(arguments, ensure_ascii=False),
        call_kind=call_kind,
        provider=provider,
    )
    return call_id


def _log_call_end(runtime: AgentRuntime, *, call_id: str, result: Any, success: bool) -> None:
    runtime.storage.log_tool_end(
        runtime.job_id,
        call_id=call_id,
        result_summary=summarize_payload(result),
        success=success,
    )


def _tool_wrapper(ctx: RunContextWrapper[AgentRuntime]) -> AgentRuntime:
    return ctx.context


def _register_sources(runtime: AgentRuntime, sources: list[SourceReference]) -> list[SourceReference]:
    existing = {item.source_id for item in runtime.source_references}
    for source in sources:
        if source.source_id in existing:
            continue
        runtime.source_references.append(source)
        runtime.storage.add_source_reference(runtime.job_id, source)
        existing.add(source.source_id)
    return sources


def build_data_tools(agent_name: str) -> list[Any]:
    @function_tool
    def inspect_dataset(ctx: RunContextWrapper[AgentRuntime]) -> dict[str, Any]:
        runtime = _tool_wrapper(ctx)
        call_id = _log_call_start(runtime, agent_name=agent_name, tool_name="inspect_dataset", arguments={})
        try:
            result = runtime.analytics.dataset_overview().model_dump()
            _log_call_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def latest_snapshot(ctx: RunContextWrapper[AgentRuntime]) -> dict[str, Any]:
        runtime = _tool_wrapper(ctx)
        call_id = _log_call_start(runtime, agent_name=agent_name, tool_name="latest_snapshot", arguments={})
        try:
            result = runtime.analytics.latest_snapshot()
            _log_call_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def city_rankings(
        ctx: RunContextWrapper[AgentRuntime],
        metric: str = "emp",
        top_n: int = 5,
    ) -> dict[str, list[dict[str, Any]]]:
        runtime = _tool_wrapper(ctx)
        args = {"metric": metric, "top_n": top_n}
        call_id = _log_call_start(runtime, agent_name=agent_name, tool_name="city_rankings", arguments=args)
        try:
            result = runtime.analytics.city_rankings(metric=metric, top_n=top_n)
            _log_call_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def city_trend(
        ctx: RunContextWrapper[AgentRuntime],
        city_ids: list[int],
        metric: str = "emp",
        weeks: int = 6,
    ) -> list[dict[str, Any]]:
        runtime = _tool_wrapper(ctx)
        args = {"city_ids": city_ids, "metric": metric, "weeks": weeks}
        call_id = _log_call_start(runtime, agent_name=agent_name, tool_name="city_trend", arguments=args)
        try:
            result = [item.model_dump() for item in runtime.analytics.city_trend(city_ids=city_ids, metric=metric, weeks=weeks)]
            _log_call_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def income_group_comparison(
        ctx: RunContextWrapper[AgentRuntime],
        lookback_weeks: int = 4,
    ) -> list[dict[str, Any]]:
        runtime = _tool_wrapper(ctx)
        args = {"lookback_weeks": lookback_weeks}
        call_id = _log_call_start(runtime, agent_name=agent_name, tool_name="income_group_comparison", arguments=args)
        try:
            result = [item.model_dump() for item in runtime.analytics.income_group_comparison(lookback_weeks=lookback_weeks)]
            _log_call_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def detect_anomalies(
        ctx: RunContextWrapper[AgentRuntime],
        metric: str = "emp",
        lookback_weeks: int = 8,
        z_threshold: float = 1.8,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        runtime = _tool_wrapper(ctx)
        args = {
            "metric": metric,
            "lookback_weeks": lookback_weeks,
            "z_threshold": z_threshold,
            "limit": limit,
        }
        call_id = _log_call_start(runtime, agent_name=agent_name, tool_name="detect_anomalies", arguments=args)
        try:
            result = [
                item.model_dump()
                for item in runtime.analytics.detect_anomalies(
                    metric=metric,
                    lookback_weeks=lookback_weeks,
                    z_threshold=z_threshold,
                    limit=limit,
                )
            ]
            _log_call_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def build_chart_payload(ctx: RunContextWrapper[AgentRuntime]) -> list[dict[str, Any]]:
        runtime = _tool_wrapper(ctx)
        call_id = _log_call_start(runtime, agent_name=agent_name, tool_name="build_chart_payload", arguments={})
        try:
            result = [chart.model_dump() for chart in runtime.analytics.build_chart_payloads()]
            _log_call_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    return [
        inspect_dataset,
        latest_snapshot,
        city_rankings,
        city_trend,
        income_group_comparison,
        detect_anomalies,
        build_chart_payload,
    ]


def build_knowledge_tools(agent_name: str) -> list[Any]:
    @function_tool
    def rag_search(ctx: RunContextWrapper[AgentRuntime], query: str) -> list[dict[str, Any]]:
        runtime = _tool_wrapper(ctx)
        call_id = _log_call_start(
            runtime,
            agent_name=agent_name,
            tool_name="rag_search",
            arguments={"query": query},
            call_kind="rag",
            provider="local-knowledge",
        )
        try:
            result = runtime.rag.search(query, limit=runtime.settings.rag_top_k)
            _register_sources(runtime, result)
            runtime.observability.emit_metric("rag_retrieval_count", float(len(result)), job_id=runtime.job_id, labels={"skill_id": runtime.skill_id})
            _log_call_end(runtime, call_id=call_id, result=[item.model_dump() for item in result], success=True)
            return [item.model_dump() for item in result]
        except Exception as exc:
            runtime.observability.emit_metric("rag_error_count", 1.0, job_id=runtime.job_id, labels={"skill_id": runtime.skill_id})
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def mcp_search(ctx: RunContextWrapper[AgentRuntime], source_name: str, query: str) -> list[dict[str, Any]]:
        runtime = _tool_wrapper(ctx)
        call_id = _log_call_start(
            runtime,
            agent_name=agent_name,
            tool_name=f"mcp_search:{source_name}",
            arguments={"source_name": source_name, "query": query},
            call_kind="mcp",
            provider=source_name,
        )
        try:
            result = runtime.mcp_registry.search(source_name, query, limit=3)
            _register_sources(runtime, result)
            runtime.observability.emit_metric("mcp_call_count", 1.0, job_id=runtime.job_id, labels={"source_name": source_name})
            _log_call_end(runtime, call_id=call_id, result=[item.model_dump() for item in result], success=True)
            return [item.model_dump() for item in result]
        except Exception as exc:
            runtime.observability.emit_metric("mcp_error_count", 1.0, job_id=runtime.job_id, labels={"source_name": source_name})
            _log_call_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    return [rag_search, mcp_search]


class AnalysisRunHooks(RunHooks[AgentRuntime]):
    def on_agent_end(self, context: Any, agent: Agent[AgentRuntime], output: Any) -> None:
        runtime = context.context
        runtime.storage.log_agent_result(
            runtime.job_id,
            phase=runtime.phase,
            agent_name=agent.name,
            model_name=str(agent.model) if agent.model else None,
            status="completed",
            output_summary=summarize_payload(output),
            skill_id=runtime.skill_id,
        )

    def on_handoff(
        self,
        context: RunContextWrapper[AgentRuntime],
        from_agent: Agent[AgentRuntime],
        to_agent: Agent[AgentRuntime],
    ) -> None:
        runtime = context.context
        runtime.storage.log_agent_result(
            runtime.job_id,
            phase=runtime.phase,
            agent_name=from_agent.name,
            model_name=str(from_agent.model) if from_agent.model else None,
            status="handoff",
            handoff_to=to_agent.name,
            output_summary="Handoff triggered.",
            skill_id=runtime.skill_id,
        )


def _data_agent_instructions(ctx: RunContextWrapper[AgentRuntime], _: Agent[AgentRuntime]) -> str:
    skill = get_skill(ctx.context.skill_id)
    goal_summary = build_goal_summary_block(ctx.context)
    return (
        f"You are the Data Analyst Agent for skill `{skill.skill_id}` ({skill.name}). "
        "Use dataset tools to inspect the data, measure latest employment changes, rank cities, "
        "compare income groups, identify anomalies, and inspect chart payloads. "
        "Return a strict EvidencePack JSON object with concise findings.\n\n"
        f"{goal_summary}"
    )


def _follow_up_instructions(ctx: RunContextWrapper[AgentRuntime], _: Agent[AgentRuntime]) -> str:
    request = ctx.context.follow_up_request
    request_json = request.model_dump_json(indent=2) if request else "{}"
    goal_summary = build_goal_summary_block(ctx.context)
    return (
        "You are the Data Follow-up Agent. A senior economist requested supplemental analysis. "
        "Use the available data tools and return a strict SupplementalEvidence object. "
        f"The requested follow-up payload is:\n{request_json}\n\n"
        f"{goal_summary}"
    )


def _economist_writer_instructions(ctx: RunContextWrapper[AgentRuntime], _: Agent[AgentRuntime]) -> str:
    skill = get_skill(ctx.context.skill_id)
    evidence = ctx.context.evidence_pack.model_dump_json(indent=2) if ctx.context.evidence_pack else "{}"
    supplemental = (
        ctx.context.supplemental_evidence.model_dump_json(indent=2)
        if ctx.context.supplemental_evidence
        else "{}"
    )
    source_names = ", ".join(source.title for source in ctx.context.source_references[:6]) or "none"
    goal_summary = build_goal_summary_block(ctx.context)
    return (
        f"You are the Economist Agent for skill `{skill.skill_id}` ({skill.name}). "
        "Use rag_search and mcp_search before returning. "
        "Generate a Chinese FinalReport with overview, city changes, income signals, risks, conclusion, "
        "and next observation points. Reference evidence and sources. "
        f"Known sources: {source_names}\n\n{goal_summary}\n\nEvidence pack:\n{evidence}\n\nSupplemental evidence:\n{supplemental}"
    )


def build_agents(runtime: AgentRuntime) -> tuple[Agent[AgentRuntime], Agent[AgentRuntime], Agent[AgentRuntime]]:
    data_tools = build_data_tools("Data Analyst Agent")
    knowledge_tools = build_knowledge_tools("Economist Agent")
    follow_up_tools = build_data_tools("Data Follow-up Agent")

    follow_up_agent = Agent[AgentRuntime](
        name="Data Follow-up Agent",
        handoff_description="Performs targeted follow-up analysis for cities or income groups.",
        instructions=_follow_up_instructions,
        tools=follow_up_tools,
        model=runtime.settings.data_agent_model,
        model_settings=ModelSettings(tool_choice="required", parallel_tool_calls=False, temperature=0.1),
        output_type=SupplementalEvidence,
    )

    def capture_follow_up(ctx: RunContextWrapper[AgentRuntime], payload: FollowUpRequest) -> None:
        runtime_obj = ctx.context
        runtime_obj.follow_up_request = payload

    economist_review_agent = Agent[AgentRuntime](
        name="Economist Review Agent",
        handoff_description="Reviews the evidence pack and decides whether more data is needed.",
        instructions=(
            "You are the Economist Review Agent. Review the evidence pack carefully. "
            "If the evidence is sufficient, return a Chinese FinalReport directly. "
            "If you need more support, hand off to the Data Follow-up Agent with a structured "
            "FollowUpRequest that names the required tools and focus cities or income groups."
        ),
        tools=knowledge_tools,
        handoffs=[
            handoff(
                follow_up_agent,
                on_handoff=capture_follow_up,
                input_type=FollowUpRequest,
                tool_description_override="Request targeted follow-up analysis from the data specialist.",
            )
        ],
        model=runtime.settings.economist_agent_model,
        model_settings=ModelSettings(tool_choice="required", parallel_tool_calls=False, temperature=0.2),
        output_type=FinalReport,
    )

    economist_writer_agent = Agent[AgentRuntime](
        name="Economist Writer Agent",
        handoff_description="Turns evidence into the final Chinese report.",
        instructions=_economist_writer_instructions,
        tools=knowledge_tools,
        model=runtime.settings.economist_agent_model,
        model_settings=ModelSettings(tool_choice="required", parallel_tool_calls=False, temperature=0.2),
        output_type=FinalReport,
    )

    data_agent = Agent[AgentRuntime](
        name="Data Analyst Agent",
        handoff_description="Produces the structured evidence pack from dataset tools.",
        instructions=_data_agent_instructions,
        tools=data_tools,
        model=runtime.settings.data_agent_model,
        model_settings=ModelSettings(tool_choice="required", parallel_tool_calls=False, temperature=0.1),
        output_type=EvidencePack,
    )

    return data_agent, economist_review_agent, economist_writer_agent


def _build_local_sources(runtime: AgentRuntime) -> list[SourceReference]:
    query = f"{runtime.skill_id} employment trend anomalies methodology policy"
    rag_sources = runtime.rag.search(query, limit=runtime.settings.rag_top_k)
    mcp_sources: list[SourceReference] = []
    for source_name in get_skill(runtime.skill_id).mcp_sources:
        mcp_sources.extend(runtime.mcp_registry.search(source_name, query, limit=2))
    return _register_sources(runtime, rag_sources + mcp_sources)


def run_data_analyst_fallback(runtime: AgentRuntime) -> EvidencePack:
    runtime.phase = "data_analysis"
    overview = runtime.analytics.dataset_overview()
    snapshot = runtime.analytics.latest_snapshot()
    rankings = runtime.analytics.city_rankings()
    income = runtime.analytics.income_group_comparison()
    anomalies = runtime.analytics.detect_anomalies()
    trend = runtime.analytics.recent_trend(weeks=6)

    missing_columns = [name for name, count in overview.missing_values.items() if count > 0]
    quality_notes = []
    if missing_columns:
        quality_notes.append(f"Missing values appear in {', '.join(missing_columns)} and are treated as nulls instead of zeros.")
    quality_notes.append("City names are not provided, so the report continues to display city IDs.")
    quality_notes.append("The MVP focuses on cross-sectional comparison and recent trend review without seasonal adjustment.")

    top = rankings["top"]
    bottom = rankings["bottom"]
    findings = [
        f"Latest overall employment change is {snapshot['overall_emp_change']:.4f}.",
        f"Best-performing city is City {top[0]['cityid']} at {top[0]['value']:.4f}.",
        f"Weakest-performing city is City {bottom[0]['cityid']} at {bottom[0]['value']:.4f}.",
    ]
    weakest_income = min(
        [item for item in income if item.latest_value is not None],
        key=lambda item: item.latest_value or 0.0,
        default=None,
    )
    if weakest_income:
        findings.append(
            f"{weakest_income.segment} is the weakest income cohort in the latest period at {weakest_income.latest_value:.4f}."
        )
    if anomalies:
        findings.append(f"Detected {len(anomalies)} notable anomaly signals that warrant explanation.")

    evidence = EvidencePack(
        dataset_overview=overview,
        latest_period=str(snapshot["latest_period"]),
        overall_emp_change=float(snapshot["overall_emp_change"]),
        top_cities=[CityMetric.model_validate(item) for item in top],
        bottom_cities=[CityMetric.model_validate(item) for item in bottom],
        income_group_signals=income,
        recent_trends=trend,
        anomalies=anomalies,
        data_quality_notes=quality_notes,
        key_findings=findings,
    )
    runtime.storage.log_agent_result(
        runtime.job_id,
        phase=runtime.phase,
        agent_name="Data Analyst Agent",
        model_name="fallback-local",
        status="completed",
        output_summary=summarize_payload(evidence),
        skill_id=runtime.skill_id,
    )
    runtime.observability.emit_metric("tool_success_rate", 1.0, job_id=runtime.job_id, labels={"phase": runtime.phase})
    return evidence


def run_economist_review_fallback(runtime: AgentRuntime) -> FollowUpRequest | FinalReport:
    runtime.phase = "economist_review"
    runtime.storage.log_agent_result(
        runtime.job_id,
        phase=runtime.phase,
        agent_name="Economist Review Agent",
        model_name="fallback-local",
        status="completed",
        input_summary=summarize_payload(runtime.evidence_pack),
        output_summary="Fallback review completed.",
        skill_id=runtime.skill_id,
    )
    evidence = runtime.evidence_pack
    assert evidence is not None
    top_city = evidence.top_cities[0].cityid if evidence.top_cities else 1
    bottom_city = evidence.bottom_cities[0].cityid if evidence.bottom_cities else 1
    needs_follow_up = runtime.skill.review_requires_follow_up and (
        bool(evidence.anomalies) or abs(evidence.top_cities[0].value - evidence.bottom_cities[0].value) > 0.08
    )
    if needs_follow_up:
        request = FollowUpRequest(
            reason="The city-level divergence or anomalies are large enough to justify targeted follow-up.",
            required_tools=["city_trend", "income_group_comparison", "detect_anomalies"],
            focus_cities=[top_city, bottom_city],
            focus_income_groups=["emp_incq1", "emp_incbelowmed", "emp_incmiddle"],
        )
        runtime.follow_up_request = request
        runtime.storage.log_agent_result(
            runtime.job_id,
            phase=runtime.phase,
            agent_name="Economist Review Agent",
            model_name="fallback-local",
            status="handoff",
            handoff_to="Data Follow-up Agent",
            output_summary=summarize_payload(request),
            skill_id=runtime.skill_id,
        )
        return request
    return _build_local_report(runtime)


def run_follow_up_fallback(runtime: AgentRuntime) -> SupplementalEvidence:
    runtime.phase = "economist_follow_up"
    request = runtime.follow_up_request or FollowUpRequest(
        reason="Default follow-up analysis.",
        required_tools=["city_trend"],
        focus_cities=[],
        focus_income_groups=[],
    )
    city_trends = runtime.analytics.city_trend(
        city_ids=request.focus_cities or [item.cityid for item in runtime.evidence_pack.top_cities[:2]]
    )
    income_details = runtime.analytics.income_group_comparison()
    anomalies = runtime.analytics.detect_anomalies(limit=4)
    findings = []
    for city_trend_item in city_trends:
        if city_trend_item.points:
            findings.append(
                f"City {city_trend_item.cityid} recent {len(city_trend_item.points)}-week value ends at {city_trend_item.points[-1].value:.4f}."
            )
    if anomalies:
        findings.append(f"Follow-up analysis confirms {len(anomalies)} anomaly signals.")
    supplemental = SupplementalEvidence(
        reason=request.reason,
        findings=findings or ["Follow-up analysis did not uncover evidence beyond the main report."],
        city_trends=city_trends,
        income_group_details=income_details,
        anomalies=anomalies,
        unresolved_gaps=[],
    )
    runtime.storage.log_agent_result(
        runtime.job_id,
        phase=runtime.phase,
        agent_name="Data Follow-up Agent",
        model_name="fallback-local",
        status="completed",
        output_summary=summarize_payload(supplemental),
        skill_id=runtime.skill_id,
    )
    runtime.supplemental_evidence = supplemental
    return supplemental


def _build_local_report(runtime: AgentRuntime) -> FinalReport:
    evidence = runtime.evidence_pack
    assert evidence is not None
    supplemental = runtime.supplemental_evidence
    skill_definition = get_skill(runtime.skill_id)
    sources = runtime.source_references or _build_local_sources(runtime)

    best_city = evidence.top_cities[0] if evidence.top_cities else None
    worst_city = evidence.bottom_cities[0] if evidence.bottom_cities else None
    weakest_income = min(
        [item for item in evidence.income_group_signals if item.latest_value is not None],
        key=lambda item: item.latest_value or 0.0,
        default=None,
    )
    strongest_income = max(
        [item for item in evidence.income_group_signals if item.latest_value is not None],
        key=lambda item: item.latest_value or 0.0,
        default=None,
    )

    if runtime.skill.report_style == "briefing":
        overview = (
            f"The latest period {evidence.latest_period} shows overall employment change at {evidence.overall_emp_change:.4f}. "
            "This briefing focuses on how the local signal aligns with external macro and policy context."
        )
    else:
        overview = (
            f"The latest observed period {evidence.latest_period} shows overall employment change at {evidence.overall_emp_change:.4f}. "
            f"Across the latest {len(evidence.recent_trends)} observations, the series remains directionally recoverable but uneven."
        )

    city_changes = (
        f"City divergence remains visible: City {best_city.cityid} leads at {best_city.value:.4f}, "
        f"while City {worst_city.cityid} trails at {worst_city.value:.4f}."
        if best_city and worst_city
        else "City-level ranking data is not sufficient for a reliable comparison."
    )
    if supplemental and supplemental.city_trends:
        city_changes += " Follow-up city trends suggest the most extreme cities still show unstable short-term movement."

    if weakest_income and strongest_income:
        income_text = (
            f"Income segmentation is uneven: {strongest_income.segment} is strongest at {strongest_income.latest_value:.4f}, "
            f"while {weakest_income.segment} is weakest at {weakest_income.latest_value:.4f}."
        )
    else:
        income_text = "Income-group signals are readable but do not yet support a strong directional claim."

    risks = "The main risks are regional dispersion, weak lower-income performance, and interpretation uncertainty from missing values."
    if evidence.anomalies:
        risks += f" The latest run also detected {len(evidence.anomalies)} anomalies that require cautious interpretation."
    if runtime.skill.report_style == "briefing":
        risks += " Policy framing should avoid claiming causality from a single weekly snapshot."

    conclusion = (
        "Overall, the dataset looks more like a recovery with divergence than a synchronized improvement."
        if runtime.skill.report_style != "briefing"
        else "Overall, the local data and retrieved background context point to a selective recovery rather than a broad-based stabilization."
    )
    observations = [
        "Track whether overall employment change continues to improve over the next reporting periods.",
        "Watch whether the gap between top and bottom cities narrows or widens further.",
        "Monitor whether lower-income cohorts remain weaker than the aggregate trend.",
    ]
    if supplemental and supplemental.findings:
        observations.append("Revisit follow-up cities to determine whether current anomalies are temporary shocks or trend breaks.")

    return FinalReport(
        overview=overview,
        city_changes=city_changes,
        income_signals=income_text,
        risks=risks,
        conclusion=conclusion,
        next_observation_points=observations,
        skill_id=runtime.skill_id,
        skill_name=skill_definition.name,
        sources=sources,
        cited_source_ids=[item.source_id for item in sources],
    )


def _prime_fallback_sources(runtime: AgentRuntime) -> None:
    if runtime.source_references:
        return
    query = f"{runtime.skill_id} employment anomalies policy methodology"
    rag_call_id = _log_call_start(
        runtime,
        agent_name="Economist Writer Agent",
        tool_name="rag_search",
        arguments={"query": query},
        call_kind="rag",
        provider="local-knowledge",
    )
    rag_result = runtime.rag.search(query, limit=runtime.settings.rag_top_k)
    _register_sources(runtime, rag_result)
    _log_call_end(runtime, call_id=rag_call_id, result=[item.model_dump() for item in rag_result], success=True)

    for source_name in get_skill(runtime.skill_id).mcp_sources:
        call_id = _log_call_start(
            runtime,
            agent_name="Economist Writer Agent",
            tool_name=f"mcp_search:{source_name}",
            arguments={"query": query},
            call_kind="mcp",
            provider=source_name,
        )
        result = runtime.mcp_registry.search(source_name, query, limit=2)
        _register_sources(runtime, result)
        _log_call_end(runtime, call_id=call_id, result=[item.model_dump() for item in result], success=True)


def run_economist_writer_fallback(runtime: AgentRuntime) -> FinalReport:
    runtime.phase = "economist_writer"
    _prime_fallback_sources(runtime)
    report = _build_local_report(runtime)
    runtime.storage.log_agent_result(
        runtime.job_id,
        phase=runtime.phase,
        agent_name="Economist Writer Agent",
        model_name="fallback-local",
        status="completed",
        output_summary=summarize_payload(report),
        skill_id=runtime.skill_id,
    )
    return report


def run_data_analyst_agent(runtime: AgentRuntime) -> EvidencePack:
    runtime.phase = "data_analysis"
    if not runtime.use_openai:
        runtime.evidence_pack = run_data_analyst_fallback(runtime)
        return runtime.evidence_pack

    data_agent, _, _ = build_agents(runtime)
    result = Runner.run_sync(
        data_agent,
        input=(
            f"Analyze the uploaded employment dataset for skill `{runtime.skill_id}`. "
            "You must call dataset tools before returning. "
            "Return a strict EvidencePack with key findings and data quality notes.\n\n"
            f"{build_goal_summary_block(runtime)}"
        ),
        context=runtime,
        hooks=AnalysisRunHooks(),
    )
    runtime.evidence_pack = result.final_output_as(EvidencePack, raise_if_incorrect_type=True)
    return runtime.evidence_pack


def run_economist_agent(runtime: AgentRuntime) -> FollowUpRequest | FinalReport:
    runtime.phase = "economist_review"
    if not runtime.use_openai:
        return run_economist_review_fallback(runtime)

    _, economist_review_agent, _ = build_agents(runtime)
    evidence_json = runtime.evidence_pack.model_dump_json(indent=2) if runtime.evidence_pack else "{}"
    result = Runner.run_sync(
        economist_review_agent,
        input=(
            f"Review the evidence pack for skill `{runtime.skill_id}`. "
            "If it is sufficient, return FinalReport in Chinese. "
            "If not, use handoff to request focused follow-up analysis.\n\n"
            f"{build_goal_summary_block(runtime)}\n\n{evidence_json}"
        ),
        context=runtime,
        hooks=AnalysisRunHooks(),
    )
    if isinstance(result.final_output, FinalReport):
        final_report = result.final_output_as(FinalReport, raise_if_incorrect_type=True)
        final_report.skill_id = runtime.skill_id
        final_report.skill_name = get_skill(runtime.skill_id).name
        final_report.sources = runtime.source_references
        final_report.cited_source_ids = [item.source_id for item in runtime.source_references]
        return final_report
    if isinstance(result.final_output, SupplementalEvidence):
        runtime.supplemental_evidence = result.final_output_as(SupplementalEvidence, raise_if_incorrect_type=True)
        if runtime.follow_up_request is None:
            runtime.follow_up_request = FollowUpRequest(
                reason="Follow-up analysis completed through SDK handoff.",
                required_tools=["city_trend"],
            )
        return runtime.follow_up_request
    raise TypeError(f"Unexpected economist output type: {type(result.final_output)!r}")


def run_economist_writer_agent(runtime: AgentRuntime) -> FinalReport:
    runtime.phase = "economist_writer"
    if not runtime.use_openai:
        return run_economist_writer_fallback(runtime)

    _, _, writer_agent = build_agents(runtime)
    evidence_json = runtime.evidence_pack.model_dump_json(indent=2) if runtime.evidence_pack else "{}"
    supplemental_json = (
        runtime.supplemental_evidence.model_dump_json(indent=2)
        if runtime.supplemental_evidence
        else "{}"
    )
    result = Runner.run_sync(
        writer_agent,
        input=(
            f"Write the final Chinese economic report for skill `{runtime.skill_id}` based on the evidence pack and supplemental evidence.\n\n"
            f"{build_goal_summary_block(runtime)}\n\n"
            f"EvidencePack:\n{evidence_json}\n\nSupplementalEvidence:\n{supplemental_json}"
        ),
        context=runtime,
        hooks=AnalysisRunHooks(),
    )
    final_report = result.final_output_as(FinalReport, raise_if_incorrect_type=True)
    final_report.skill_id = runtime.skill_id
    final_report.skill_name = get_skill(runtime.skill_id).name
    final_report.sources = runtime.source_references
    final_report.cited_source_ids = [item.source_id for item in runtime.source_references]
    return final_report


def build_runtime(job_id: str, source_path: str, storage: Storage, settings: Settings, *, skill_id: str) -> AgentRuntime:
    dataset_path = Path(source_path)
    knowledge_base = KnowledgeBase(PROJECT_ROOT / settings.knowledge_dir)
    analytics = AnalyticsService(dataset_path)
    rag = RagService(PROJECT_ROOT / settings.knowledge_dir)
    observability = ObservabilityService(storage)
    return AgentRuntime(
        job_id=job_id,
        skill_id=skill_id,
        storage=storage,
        settings=settings,
        analytics=analytics,
        knowledge_base=knowledge_base,
        rag=rag,
        mcp_registry=build_default_mcp_registry(),
        observability=observability,
        phase="queued",
    )
