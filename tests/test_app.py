from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.services.analytics import AnalyticsService
from app.services.data_loader import load_employment_data
from app.services.rag import RagService
from app.skills import get_stage_disclosure, list_skills


DATA_FILE = PROJECT_ROOT / "data" / "Employment - City - Weekly.csv"


def build_test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        database_path=tmp_path / "analysis.db",
        upload_dir=tmp_path / "uploads",
        output_dir=tmp_path / "output",
        knowledge_dir=PROJECT_ROOT / "knowledge",
    )
    settings.ensure_directories(PROJECT_ROOT)
    return settings


def wait_for_completion(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.time() + 20
    payload: dict[str, object] = {}
    while time.time() < deadline:
        status_response = client.get(f"/api/jobs/{job_id}")
        assert status_response.status_code == 200
        payload = status_response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.2)
    raise AssertionError("Job did not complete within the deadline.")


def test_load_employment_data() -> None:
    dataset = load_employment_data(DATA_FILE)
    assert len(dataset) > 10000
    assert dataset[0].cityid >= 1
    assert dataset[0].period_end.isoformat() >= "2020-01-01"


def test_analytics_service_contract() -> None:
    service = AnalyticsService(DATA_FILE)
    overview = service.dataset_overview()
    snapshot = service.latest_snapshot()
    rankings = service.city_rankings()
    charts = service.build_chart_payloads()

    assert overview.city_count == 53
    assert snapshot["latest_period"]
    assert len(rankings["top"]) == 5
    assert len(rankings["bottom"]) == 5
    assert len(charts) == 3


def test_skill_registry_contract() -> None:
    skills = list_skills()
    assert len(skills) == 3
    assert {skill.skill_id for skill in skills} == {
        "economic_report",
        "anomaly_investigation",
        "policy_briefing",
    }
    economic_report = next(skill for skill in skills if skill.skill_id == "economic_report")
    assert "data_analysis" in economic_report.stage_disclosures
    assert "economist_writer" in economic_report.stage_disclosures


def test_progressive_skill_disclosure_contract() -> None:
    data_stage = get_stage_disclosure("economic_report", "data_analysis")
    review_stage = get_stage_disclosure("economic_report", "economist_review")
    follow_up_stage = get_stage_disclosure("economic_report", "economist_follow_up")
    writer_stage = get_stage_disclosure("economic_report", "economist_writer")

    assert "inspect_dataset" in data_stage.allowed_tools
    assert not data_stage.rag_enabled
    assert review_stage.rag_enabled
    assert review_stage.mcp_sources == ["economic-data"]
    assert "city_trend" in follow_up_stage.allowed_tools
    assert writer_stage.allowed_tools == []
    assert writer_stage.rag_enabled


def test_rag_service_returns_local_knowledge() -> None:
    rag = RagService(PROJECT_ROOT / "knowledge")
    results = rag.search("indicator methodology employment", limit=3)
    assert results
    assert all(item.source_type == "local_knowledge" for item in results)


def test_api_job_flow_with_default_skill(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    with DATA_FILE.open("rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("employment.csv", handle, "text/csv")},
            data={"skill_id": "economic_report"},
        )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    payload = wait_for_completion(client, job_id)
    assert payload["status"] == "completed", payload
    assert payload["skill_id"] == "economic_report"

    report_response = client.get(f"/api/jobs/{job_id}/report")
    trace_response = client.get(f"/api/jobs/{job_id}/trace")
    sources_response = client.get(f"/api/jobs/{job_id}/sources")
    goal_summary_response = client.get(f"/api/jobs/{job_id}/goal-summary")
    assert report_response.status_code == 200
    assert trace_response.status_code == 200
    assert sources_response.status_code == 200
    assert goal_summary_response.status_code == 200
    report_payload = report_response.json()
    trace_payload = trace_response.json()
    sources_payload = sources_response.json()
    goal_summary_payload = goal_summary_response.json()
    assert "Economic Analysis Report" in report_payload["report_markdown"]
    assert report_payload["skill_id"] == "economic_report"
    assert len(report_payload["chart_payloads"]) == 3
    assert len(trace_payload["agent_runs"]) >= 2
    assert any(row["call_kind"] == "rag" for row in trace_payload["tool_calls"])
    assert any(row["call_kind"] == "mcp" for row in trace_payload["tool_calls"])
    assert sources_payload["sources"]
    assert goal_summary_payload["summary"]["current_stage"] == "completed"
    assert goal_summary_payload["summary"]["next_action"] == "Task completed"
    assert "data_analysis" in goal_summary_payload["summary"]["completed_steps"]
    assert goal_summary_payload["version"] >= 5


def test_policy_briefing_skill_path(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    with DATA_FILE.open("rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("employment.csv", handle, "text/csv")},
            data={"skill_id": "policy_briefing"},
        )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    payload = wait_for_completion(client, job_id)
    assert payload["status"] == "completed", payload
    assert payload["skill_id"] == "policy_briefing"

    report_response = client.get(f"/api/jobs/{job_id}/report")
    report_payload = report_response.json()
    assert report_payload["skill_id"] == "policy_briefing"
    assert "policy_briefing" in report_payload["report_markdown"]


def test_goal_summary_created_on_job_creation(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    with DATA_FILE.open("rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("employment.csv", handle, "text/csv")},
            data={"skill_id": "economic_report"},
        )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    summary_response = client.get(f"/api/jobs/{job_id}/goal-summary")
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["summary"]["overall_goal"]
    assert payload["summary"]["next_action"]


def test_anomaly_investigation_goal_summary_follow_up_path(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    with DATA_FILE.open("rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("employment.csv", handle, "text/csv")},
            data={"skill_id": "anomaly_investigation"},
        )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    payload = wait_for_completion(client, job_id)
    assert payload["status"] == "completed", payload

    summary_response = client.get(f"/api/jobs/{job_id}/goal-summary")
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["summary"]["current_stage"] == "completed"
    assert summary_payload["summary"]["next_action"] == "Task completed"
    assert summary_payload["version"] >= 6
    assert any(
        step in summary_payload["summary"]["completed_steps"]
        for step in ["economist_follow_up", "economist_writer"]
    )


def test_goal_summary_api_not_found(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/jobs/missing-job/goal-summary")
    assert response.status_code == 404


def test_knowledge_search_endpoint(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/knowledge/search", params={"q": "employment methodology"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "employment methodology"
    assert payload["results"]
    assert any(item["source_type"] == "local_knowledge" for item in payload["results"])
