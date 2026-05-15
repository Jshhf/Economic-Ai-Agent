from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.services.analytics import AnalyticsService
from app.services.data_loader import load_employment_data


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


def test_api_job_flow(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    with DATA_FILE.open("rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("employment.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    deadline = time.time() + 20
    payload = {}
    while time.time() < deadline:
        status_response = client.get(f"/api/jobs/{job_id}")
        assert status_response.status_code == 200
        payload = status_response.json()
        if payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert payload["status"] == "completed", payload

    report_response = client.get(f"/api/jobs/{job_id}/report")
    trace_response = client.get(f"/api/jobs/{job_id}/trace")
    assert report_response.status_code == 200
    assert trace_response.status_code == 200
    report_payload = report_response.json()
    trace_payload = trace_response.json()
    assert "经济分析报告" in report_payload["report_markdown"]
    assert len(report_payload["chart_payloads"]) == 3
    assert len(trace_payload["agent_runs"]) >= 2
