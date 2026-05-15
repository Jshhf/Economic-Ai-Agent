from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents import Agent, ModelSettings, RunContextWrapper, RunHooks, Runner, function_tool, handoff

from app.config import PROJECT_ROOT, Settings
from app.schemas import CityMetric, EvidencePack, FinalReport, FollowUpRequest, SupplementalEvidence
from app.services.analytics import AnalyticsService
from app.services.knowledge_base import KnowledgeBase
from app.storage import Storage, summarize_payload


@dataclass(slots=True)
class AgentRuntime:
    job_id: str
    storage: Storage
    settings: Settings
    analytics: AnalyticsService
    knowledge_base: KnowledgeBase
    phase: str
    evidence_pack: EvidencePack | None = None
    follow_up_request: FollowUpRequest | None = None
    supplemental_evidence: SupplementalEvidence | None = None
    local_trace: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def use_openai(self) -> bool:
        return bool(self.settings.openai_api_key)


def _tool_call_id(tool_name: str) -> str:
    return f"{tool_name}-{uuid.uuid4().hex}"


def _log_tool_start(
    runtime: AgentRuntime,
    *,
    agent_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    call_id = _tool_call_id(tool_name)
    runtime.storage.log_tool_start(
        runtime.job_id,
        call_id=call_id,
        phase=runtime.phase,
        agent_name=agent_name,
        tool_name=tool_name,
        arguments_json=json.dumps(arguments, ensure_ascii=False),
    )
    return call_id


def _log_tool_end(runtime: AgentRuntime, *, call_id: str, result: Any, success: bool) -> None:
    runtime.storage.log_tool_end(
        runtime.job_id,
        call_id=call_id,
        result_summary=summarize_payload(result),
        success=success,
    )


def _tool_wrapper(ctx: RunContextWrapper[AgentRuntime]) -> AgentRuntime:
    return ctx.context


def build_data_tools(agent_name: str) -> list[Any]:
    @function_tool
    def inspect_dataset(ctx: RunContextWrapper[AgentRuntime]) -> dict[str, Any]:
        """Inspect dataset shape, columns, dates, and missing values."""
        runtime = _tool_wrapper(ctx)
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="inspect_dataset", arguments={})
        try:
            result = runtime.analytics.dataset_overview().model_dump()
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def latest_snapshot(ctx: RunContextWrapper[AgentRuntime]) -> dict[str, Any]:
        """Get the latest period snapshot of overall employment change."""
        runtime = _tool_wrapper(ctx)
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="latest_snapshot", arguments={})
        try:
            result = runtime.analytics.latest_snapshot()
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def city_rankings(
        ctx: RunContextWrapper[AgentRuntime],
        metric: str = "emp",
        top_n: int = 5,
    ) -> dict[str, list[dict[str, Any]]]:
        """Rank cities for a metric in the latest available period."""
        runtime = _tool_wrapper(ctx)
        args = {"metric": metric, "top_n": top_n}
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="city_rankings", arguments=args)
        try:
            result = runtime.analytics.city_rankings(metric=metric, top_n=top_n)
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def city_trend(
        ctx: RunContextWrapper[AgentRuntime],
        city_ids: list[int],
        metric: str = "emp",
        weeks: int = 6,
    ) -> list[dict[str, Any]]:
        """Return recent city-level trend points for selected cities."""
        runtime = _tool_wrapper(ctx)
        args = {"city_ids": city_ids, "metric": metric, "weeks": weeks}
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="city_trend", arguments=args)
        try:
            result = [item.model_dump() for item in runtime.analytics.city_trend(city_ids=city_ids, metric=metric, weeks=weeks)]
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def income_group_comparison(
        ctx: RunContextWrapper[AgentRuntime],
        lookback_weeks: int = 4,
    ) -> list[dict[str, Any]]:
        """Compare employment changes across income groups."""
        runtime = _tool_wrapper(ctx)
        args = {"lookback_weeks": lookback_weeks}
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="income_group_comparison", arguments=args)
        try:
            result = [item.model_dump() for item in runtime.analytics.income_group_comparison(lookback_weeks=lookback_weeks)]
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def detect_anomalies(
        ctx: RunContextWrapper[AgentRuntime],
        metric: str = "emp",
        lookback_weeks: int = 8,
        z_threshold: float = 1.8,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        """Detect recent anomalies relative to the recent history."""
        runtime = _tool_wrapper(ctx)
        args = {
            "metric": metric,
            "lookback_weeks": lookback_weeks,
            "z_threshold": z_threshold,
            "limit": limit,
        }
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="detect_anomalies", arguments=args)
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
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def build_chart_payload(ctx: RunContextWrapper[AgentRuntime]) -> list[dict[str, Any]]:
        """Build chart payloads for trend, city rankings, and income groups."""
        runtime = _tool_wrapper(ctx)
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="build_chart_payload", arguments={})
        try:
            result = [chart.model_dump() for chart in runtime.analytics.build_chart_payloads()]
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
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
    def read_indicator_definitions(ctx: RunContextWrapper[AgentRuntime]) -> str:
        """Read the local indicator definitions document."""
        runtime = _tool_wrapper(ctx)
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="read_indicator_definitions", arguments={})
        try:
            result = runtime.knowledge_base.read_indicator_definitions()
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def read_methodology_notes(ctx: RunContextWrapper[AgentRuntime]) -> str:
        """Read the local methodology notes document."""
        runtime = _tool_wrapper(ctx)
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="read_methodology_notes", arguments={})
        try:
            result = runtime.knowledge_base.read_methodology_notes()
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    @function_tool
    def read_report_rubric(ctx: RunContextWrapper[AgentRuntime]) -> str:
        """Read the local report writing rubric."""
        runtime = _tool_wrapper(ctx)
        call_id = _log_tool_start(runtime, agent_name=agent_name, tool_name="read_report_rubric", arguments={})
        try:
            result = runtime.knowledge_base.read_report_rubric()
            _log_tool_end(runtime, call_id=call_id, result=result, success=True)
            return result
        except Exception as exc:
            _log_tool_end(runtime, call_id=call_id, result={"error": str(exc)}, success=False)
            raise

    return [read_indicator_definitions, read_methodology_notes, read_report_rubric]


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
        )


def _data_agent_instructions(_: RunContextWrapper[AgentRuntime], __: Agent[AgentRuntime]) -> str:
    return (
        "You are the Data Analyst Agent. Use the available tools to inspect the dataset, "
        "measure latest employment changes, rank cities, compare income groups, identify anomalies, "
        "and inspect chart payloads. You must call tools before returning. "
        "Return a strict EvidencePack JSON object with concise key findings and data quality notes."
    )


def _follow_up_instructions(ctx: RunContextWrapper[AgentRuntime], _: Agent[AgentRuntime]) -> str:
    request = ctx.context.follow_up_request
    request_json = request.model_dump_json(indent=2) if request else "{}"
    return (
        "You are the Data Follow-up Agent. A senior economist requested supplemental analysis. "
        "Use the available data tools and return a strict SupplementalEvidence object. "
        f"The requested follow-up payload is:\n{request_json}"
    )


def _economist_writer_instructions(ctx: RunContextWrapper[AgentRuntime], _: Agent[AgentRuntime]) -> str:
    evidence = ctx.context.evidence_pack.model_dump_json(indent=2) if ctx.context.evidence_pack else "{}"
    supplemental = (
        ctx.context.supplemental_evidence.model_dump_json(indent=2)
        if ctx.context.supplemental_evidence
        else "{}"
    )
    return (
        "You are the Economist Agent. Use the knowledge tools before returning. "
        "Generate a Chinese FinalReport with five sections: overview, city changes, income signals, "
        "risks, conclusion, plus next observation points. Reference numbers from the evidence. "
        f"Evidence pack:\n{evidence}\n\nSupplemental evidence:\n{supplemental}"
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
            "FollowUpRequest that names the required tools and any focus cities or income groups."
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
        quality_notes.append(f"缺失值出现在 {', '.join(missing_columns)}，分析按缺失而非零处理。")
    quality_notes.append("城市名称映射表未提供，报告暂以 cityid 展示。")
    quality_notes.append("第一版仅做横截面比较与近 6 周趋势观察，未做季节调整。")

    top = rankings["top"]
    bottom = rankings["bottom"]
    findings = [
        f"最新一期总体就业变化为 {snapshot['overall_emp_change']:.4f}。",
        f"表现最强的城市是 City {top[0]['cityid']}，就业变化 {top[0]['value']:.4f}。",
        f"表现最弱的城市是 City {bottom[0]['cityid']}，就业变化 {bottom[0]['value']:.4f}。",
    ]
    weakest_income = min(
        [item for item in income if item.latest_value is not None],
        key=lambda item: item.latest_value or 0.0,
        default=None,
    )
    if weakest_income:
        findings.append(
            f"{weakest_income.segment} 是最新一期最弱的收入组，就业变化为 {weakest_income.latest_value:.4f}。"
        )
    if anomalies:
        findings.append(f"检测到 {len(anomalies)} 个显著异常城市，需补充解释。")

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
    )
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
    )
    evidence = runtime.evidence_pack
    assert evidence is not None
    top_city = evidence.top_cities[0].cityid if evidence.top_cities else 1
    bottom_city = evidence.bottom_cities[0].cityid if evidence.bottom_cities else 1
    needs_follow_up = bool(evidence.anomalies) or abs(evidence.top_cities[0].value - evidence.bottom_cities[0].value) > 0.08
    if needs_follow_up:
        request = FollowUpRequest(
            reason="城市间分化或异常波动较强，需要补充城市趋势和收入分层证据。",
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
        )
        return request
    return _build_local_report(runtime)


def run_follow_up_fallback(runtime: AgentRuntime) -> SupplementalEvidence:
    runtime.phase = "economist_follow_up"
    request = runtime.follow_up_request or FollowUpRequest(
        reason="默认补充分析。",
        required_tools=["city_trend"],
        focus_cities=[],
        focus_income_groups=[],
    )
    city_trends = runtime.analytics.city_trend(city_ids=request.focus_cities or [item.cityid for item in runtime.evidence_pack.top_cities[:2]])
    income_details = runtime.analytics.income_group_comparison()
    anomalies = runtime.analytics.detect_anomalies(limit=4)
    findings = []
    for city_trend_item in city_trends:
        if city_trend_item.points:
            findings.append(
                f"City {city_trend_item.cityid} 最近 {len(city_trend_item.points)} 周的最新值为 {city_trend_item.points[-1].value:.4f}。"
            )
    if anomalies:
        findings.append(f"补充分析再次确认 {len(anomalies)} 个异常城市。")
    supplemental = SupplementalEvidence(
        reason=request.reason,
        findings=findings or ["补充分析未发现超出主报告的新证据。"],
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
    )
    runtime.supplemental_evidence = supplemental
    return supplemental


def _build_local_report(runtime: AgentRuntime) -> FinalReport:
    evidence = runtime.evidence_pack
    assert evidence is not None
    supplemental = runtime.supplemental_evidence
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
    overview = (
        f"最新一期 {evidence.latest_period} 的总体就业变化为 {evidence.overall_emp_change:.4f}。"
        f"从最近 {len(evidence.recent_trends)} 个观察点看，整体走势仍以短期波动为主。"
    )
    city_changes = (
        f"城市分化较明显，City {best_city.cityid} 以 {best_city.value:.4f} 领跑，"
        f"City {worst_city.cityid} 以 {worst_city.value:.4f} 处于末位。"
        if best_city and worst_city
        else "当前城市层面的排序信息不足。"
    )
    if supplemental and supplemental.city_trends:
        city_changes += " 补充趋势显示重点城市的近期波动仍未完全收敛。"
    income_text = "收入分层信号整体可读。"
    if weakest_income and strongest_income:
        income_text = (
            f"收入组之间存在分化，{strongest_income.segment} 最新值为 {strongest_income.latest_value:.4f}，"
            f"而 {weakest_income.segment} 仅为 {weakest_income.latest_value:.4f}。"
        )
    risks = "主要风险来自区域恢复不均衡、部分收入组偏弱以及缺失值带来的解释不确定性。"
    if evidence.anomalies:
        risks += f" 当前还检测到 {len(evidence.anomalies)} 个异常城市，需要持续跟踪。"
    conclusion = "综合来看，这份数据更像是“恢复中伴随分化”，而不是全面同步改善。"
    observations = [
        "继续跟踪总体就业变化是否延续改善。",
        "观察头部与尾部城市之间的差距是否收敛。",
        "关注低收入相关分组是否继续弱于总体。",
    ]
    if supplemental and supplemental.findings:
        observations.append("复查补充分析涉及的重点城市，确认异常是一次性冲击还是趋势拐点。")
    return FinalReport(
        overview=overview,
        city_changes=city_changes,
        income_signals=income_text,
        risks=risks,
        conclusion=conclusion,
        next_observation_points=observations,
    )


def run_economist_writer_fallback(runtime: AgentRuntime) -> FinalReport:
    runtime.phase = "economist_writer"
    # Read knowledge docs through storage-visible fallback calls so the trace still shows knowledge access.
    for tool_name, reader in [
        ("read_indicator_definitions", runtime.knowledge_base.read_indicator_definitions),
        ("read_methodology_notes", runtime.knowledge_base.read_methodology_notes),
        ("read_report_rubric", runtime.knowledge_base.read_report_rubric),
    ]:
        call_id = _log_tool_start(runtime, agent_name="Economist Writer Agent", tool_name=tool_name, arguments={})
        document = reader()
        _log_tool_end(runtime, call_id=call_id, result=document[:300], success=True)

    report = _build_local_report(runtime)
    runtime.storage.log_agent_result(
        runtime.job_id,
        phase=runtime.phase,
        agent_name="Economist Writer Agent",
        model_name="fallback-local",
        status="completed",
        output_summary=summarize_payload(report),
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
            "Analyze the uploaded employment dataset. You must call dataset tools before returning. "
            "Return a strict EvidencePack with key findings and data quality notes."
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
            "Review the evidence pack below. If it is sufficient, return FinalReport in Chinese. "
            "If not, use handoff to request focused follow-up analysis.\n\n"
            f"{evidence_json}"
        ),
        context=runtime,
        hooks=AnalysisRunHooks(),
    )
    if isinstance(result.final_output, FinalReport):
        return result.final_output_as(FinalReport, raise_if_incorrect_type=True)
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
            "Write the final Chinese economic report based on the evidence pack and supplemental evidence.\n\n"
            f"EvidencePack:\n{evidence_json}\n\nSupplementalEvidence:\n{supplemental_json}"
        ),
        context=runtime,
        hooks=AnalysisRunHooks(),
    )
    return result.final_output_as(FinalReport, raise_if_incorrect_type=True)


def build_runtime(job_id: str, source_path: str, storage: Storage, settings: Settings) -> AgentRuntime:
    dataset_path = Path(source_path)
    knowledge_base = KnowledgeBase(PROJECT_ROOT / settings.knowledge_dir)
    analytics = AnalyticsService(dataset_path)
    return AgentRuntime(
        job_id=job_id,
        storage=storage,
        settings=settings,
        analytics=analytics,
        knowledge_base=knowledge_base,
        phase="queued",
    )
