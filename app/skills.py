from __future__ import annotations

from dataclasses import dataclass

from app.schemas import SkillDefinition


@dataclass(frozen=True, slots=True)
class SkillRuntimeConfig:
    skill_id: str
    review_requires_follow_up: bool
    include_external_context: bool
    report_style: str


SKILLS: dict[str, SkillDefinition] = {
    "economic_report": SkillDefinition(
        skill_id="economic_report",
        name="Economic Report",
        description="Generate a complete economic analysis report with charts, evidence review, and references.",
        scenarios=["default analysis", "resume demo", "full report generation"],
        available_tools=[
            "inspect_dataset",
            "latest_snapshot",
            "city_rankings",
            "city_trend",
            "income_group_comparison",
            "detect_anomalies",
            "build_chart_payload",
        ],
        rag_enabled=True,
        mcp_sources=["economic-data", "research"],
    ),
    "anomaly_investigation": SkillDefinition(
        skill_id="anomaly_investigation",
        name="Anomaly Investigation",
        description="Focus on abnormal cities and metrics, with deeper diagnostics and external context.",
        scenarios=["anomaly review", "follow-up diagnostics", "root-cause exploration"],
        available_tools=[
            "inspect_dataset",
            "latest_snapshot",
            "city_rankings",
            "city_trend",
            "detect_anomalies",
            "build_chart_payload",
        ],
        rag_enabled=True,
        mcp_sources=["economic-data", "research"],
    ),
    "policy_briefing": SkillDefinition(
        skill_id="policy_briefing",
        name="Policy Briefing",
        description="Blend local analysis with external research context to produce a short policy-oriented briefing.",
        scenarios=["policy summary", "interview briefing", "macro context augmentation"],
        available_tools=[
            "inspect_dataset",
            "latest_snapshot",
            "city_rankings",
            "build_chart_payload",
        ],
        rag_enabled=True,
        mcp_sources=["research", "economic-data"],
    ),
}


SKILL_RUNTIME_CONFIGS: dict[str, SkillRuntimeConfig] = {
    "economic_report": SkillRuntimeConfig(
        skill_id="economic_report",
        review_requires_follow_up=True,
        include_external_context=True,
        report_style="full_report",
    ),
    "anomaly_investigation": SkillRuntimeConfig(
        skill_id="anomaly_investigation",
        review_requires_follow_up=True,
        include_external_context=True,
        report_style="anomaly_first",
    ),
    "policy_briefing": SkillRuntimeConfig(
        skill_id="policy_briefing",
        review_requires_follow_up=False,
        include_external_context=True,
        report_style="briefing",
    ),
}


def get_skill(skill_id: str) -> SkillDefinition:
    if skill_id not in SKILLS:
        raise KeyError(f"Unknown skill: {skill_id}")
    return SKILLS[skill_id]


def get_skill_runtime(skill_id: str) -> SkillRuntimeConfig:
    if skill_id not in SKILL_RUNTIME_CONFIGS:
        raise KeyError(f"Unknown skill runtime config: {skill_id}")
    return SKILL_RUNTIME_CONFIGS[skill_id]


def list_skills() -> list[SkillDefinition]:
    return [SKILLS[key] for key in sorted(SKILLS)]
