from __future__ import annotations

from dataclasses import dataclass

from app.schemas import SkillDefinition, SkillStageDisclosure


@dataclass(frozen=True, slots=True)
class SkillRuntimeConfig:
    skill_id: str
    review_requires_follow_up: bool
    include_external_context: bool
    report_style: str


DEFAULT_STAGE_ORDER = [
    "queued",
    "data_analysis",
    "economist_review",
    "economist_follow_up",
    "economist_writer",
    "completed",
    "failed",
]


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
        stage_disclosures={
            "queued": SkillStageDisclosure(
                stage="queued",
                stage_goal="Register the job and wait to start the analysis pipeline.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="JobStatusResponse",
                disclosure_rationale="No analysis capabilities are exposed before the job starts.",
            ),
            "data_analysis": SkillStageDisclosure(
                stage="data_analysis",
                stage_goal="Inspect the uploaded dataset and build the first structured evidence pack.",
                allowed_tools=[
                    "inspect_dataset",
                    "latest_snapshot",
                    "city_rankings",
                    "city_trend",
                    "income_group_comparison",
                    "detect_anomalies",
                    "build_chart_payload",
                ],
                rag_enabled=False,
                mcp_sources=[],
                output_type="EvidencePack",
                disclosure_rationale="The first stage should focus on deterministic dataset inspection instead of external context.",
            ),
            "economist_review": SkillStageDisclosure(
                stage="economist_review",
                stage_goal="Review the evidence pack and decide whether more targeted analysis is required.",
                allowed_tools=[],
                rag_enabled=True,
                mcp_sources=["economic-data"],
                output_type="FinalReport|FollowUpRequest",
                disclosure_rationale="Only lightweight retrieval is disclosed first so the reviewer can judge evidence sufficiency without reopening the full tool surface.",
            ),
            "economist_follow_up": SkillStageDisclosure(
                stage="economist_follow_up",
                stage_goal="Run targeted follow-up analysis for the specific gaps identified during review.",
                allowed_tools=[
                    "city_trend",
                    "income_group_comparison",
                    "detect_anomalies",
                ],
                rag_enabled=True,
                mcp_sources=["economic-data", "research"],
                output_type="SupplementalEvidence",
                disclosure_rationale="Deeper tools and broader external sources are only disclosed after the review stage confirms evidence gaps.",
            ),
            "economist_writer": SkillStageDisclosure(
                stage="economist_writer",
                stage_goal="Synthesize the evidence and references into the final Chinese report.",
                allowed_tools=[],
                rag_enabled=True,
                mcp_sources=["economic-data", "research"],
                output_type="FinalReport",
                disclosure_rationale="The writer mainly needs curated evidence and references instead of raw analytical tools.",
            ),
            "completed": SkillStageDisclosure(
                stage="completed",
                stage_goal="Persist the final result and expose the completed task state.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="ReportResponse",
                disclosure_rationale="No extra capabilities are exposed after the job has completed.",
            ),
            "failed": SkillStageDisclosure(
                stage="failed",
                stage_goal="Surface the failure state and preserve the latest task mainline for debugging.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="JobStatusResponse",
                disclosure_rationale="Failure handling should not expose new runtime capabilities.",
            ),
        },
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
        stage_disclosures={
            "queued": SkillStageDisclosure(
                stage="queued",
                stage_goal="Register the anomaly investigation job before analysis starts.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="JobStatusResponse",
                disclosure_rationale="No capability should be used before the task enters analysis.",
            ),
            "data_analysis": SkillStageDisclosure(
                stage="data_analysis",
                stage_goal="Detect the most abnormal cities and build the baseline evidence pack.",
                allowed_tools=[
                    "inspect_dataset",
                    "latest_snapshot",
                    "city_rankings",
                    "city_trend",
                    "detect_anomalies",
                    "build_chart_payload",
                ],
                rag_enabled=False,
                mcp_sources=[],
                output_type="EvidencePack",
                disclosure_rationale="The first pass stays focused on anomaly detection from the dataset itself.",
            ),
            "economist_review": SkillStageDisclosure(
                stage="economist_review",
                stage_goal="Judge whether the anomaly evidence is strong enough or needs targeted follow-up.",
                allowed_tools=[],
                rag_enabled=True,
                mcp_sources=["economic-data"],
                output_type="FinalReport|FollowUpRequest",
                disclosure_rationale="The reviewer gets limited context first to avoid over-expanding the task too early.",
            ),
            "economist_follow_up": SkillStageDisclosure(
                stage="economist_follow_up",
                stage_goal="Investigate focused cities and signals that still need explanation.",
                allowed_tools=[
                    "city_trend",
                    "detect_anomalies",
                    "income_group_comparison",
                ],
                rag_enabled=True,
                mcp_sources=["economic-data", "research"],
                output_type="SupplementalEvidence",
                disclosure_rationale="Additional tools are exposed only after the review explicitly identifies evidence gaps.",
            ),
            "economist_writer": SkillStageDisclosure(
                stage="economist_writer",
                stage_goal="Write the anomaly-oriented final report with supporting references.",
                allowed_tools=[],
                rag_enabled=True,
                mcp_sources=["economic-data", "research"],
                output_type="FinalReport",
                disclosure_rationale="The writer consumes the curated evidence instead of reopening broad analytics.",
            ),
            "completed": SkillStageDisclosure(
                stage="completed",
                stage_goal="Persist the anomaly investigation output and expose the completed state.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="ReportResponse",
                disclosure_rationale="No extra capabilities are needed after completion.",
            ),
            "failed": SkillStageDisclosure(
                stage="failed",
                stage_goal="Persist the failed state for debugging.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="JobStatusResponse",
                disclosure_rationale="Failure state should not disclose extra capabilities.",
            ),
        },
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
        stage_disclosures={
            "queued": SkillStageDisclosure(
                stage="queued",
                stage_goal="Register the policy briefing job before the analysis starts.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="JobStatusResponse",
                disclosure_rationale="No analysis capability is disclosed at queue time.",
            ),
            "data_analysis": SkillStageDisclosure(
                stage="data_analysis",
                stage_goal="Build a concise local evidence pack for the policy briefing.",
                allowed_tools=[
                    "inspect_dataset",
                    "latest_snapshot",
                    "city_rankings",
                    "build_chart_payload",
                ],
                rag_enabled=False,
                mcp_sources=[],
                output_type="EvidencePack",
                disclosure_rationale="The first stage stays lightweight and local before adding policy context.",
            ),
            "economist_review": SkillStageDisclosure(
                stage="economist_review",
                stage_goal="Combine the local evidence with minimal external context to decide whether the briefing is sufficient.",
                allowed_tools=[],
                rag_enabled=True,
                mcp_sources=["research"],
                output_type="FinalReport",
                disclosure_rationale="Policy briefing benefits from research context, but it should still start with a constrained source set.",
            ),
            "economist_writer": SkillStageDisclosure(
                stage="economist_writer",
                stage_goal="Write the short policy-oriented briefing with selected references.",
                allowed_tools=[],
                rag_enabled=True,
                mcp_sources=["research", "economic-data"],
                output_type="FinalReport",
                disclosure_rationale="The writer can access broader context after the concise briefing direction is confirmed.",
            ),
            "completed": SkillStageDisclosure(
                stage="completed",
                stage_goal="Persist the policy briefing output and expose the completed state.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="ReportResponse",
                disclosure_rationale="No post-completion capability exposure is needed.",
            ),
            "failed": SkillStageDisclosure(
                stage="failed",
                stage_goal="Persist the failed policy briefing state for debugging.",
                allowed_tools=[],
                rag_enabled=False,
                mcp_sources=[],
                output_type="JobStatusResponse",
                disclosure_rationale="Failure handling should remain capability-minimal.",
            ),
        },
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


def get_stage_disclosure(skill_id: str, stage: str) -> SkillStageDisclosure:
    skill = get_skill(skill_id)
    disclosure = skill.stage_disclosures.get(stage)
    if disclosure is not None:
        return disclosure
    if stage in {"completed", "failed"} and stage in skill.stage_disclosures:
        return skill.stage_disclosures[stage]
    raise KeyError(f"Unknown disclosure stage `{stage}` for skill `{skill_id}`")
