from __future__ import annotations

import json
from pathlib import Path

import markdown as markdown_lib
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT, Settings, get_settings
from app.jobs import JobRunner
from app.schemas import CreateJobResponse, JobStatusResponse
from app.storage import Storage


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    storage = Storage(PROJECT_ROOT / resolved_settings.database_path)
    storage.init_db()
    runner = JobRunner(settings=resolved_settings, storage=storage)

    app = FastAPI(title=resolved_settings.app_name)
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
    app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")

    app.state.settings = resolved_settings
    app.state.storage = storage
    app.state.runner = runner
    app.state.templates = templates

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": resolved_settings.app_name,
                "sample_path": str(PROJECT_ROOT / "data" / "Employment - City - Weekly.csv"),
                "openai_enabled": bool(resolved_settings.openai_api_key),
            },
        )

    @app.post("/jobs", response_class=HTMLResponse)
    async def create_job_page(request: Request, file: UploadFile = File(...)) -> RedirectResponse:
        payload = await file.read()
        job_id = runner.create_job_from_upload(payload, file.filename or "uploaded.csv")
        runner.enqueue(job_id)
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_detail(request: Request, job_id: str) -> HTMLResponse:
        try:
            storage.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        return templates.TemplateResponse(
            request,
            "job_detail.html",
            {"job_id": job_id, "title": f"Job {job_id}"},
        )

    @app.get("/jobs/{job_id}/panel", response_class=HTMLResponse)
    async def job_panel(request: Request, job_id: str) -> HTMLResponse:
        try:
            job = storage.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

        report = None
        trace = None
        report_html = None
        chart_json = "[]"
        if job.status == "completed":
            report = runner.get_report_response(job_id)
            trace = runner.get_trace_response(job_id)
            report_html = markdown_lib.markdown(report.report_markdown)
            chart_json = json.dumps([chart.model_dump() for chart in report.chart_payloads], ensure_ascii=False)
        elif job.status == "failed":
            trace = runner.get_trace_response(job_id)

        return templates.TemplateResponse(
            request,
            "partials/job_panel.html",
            {
                "job": job,
                "job_id": job_id,
                "report": report,
                "report_html": report_html,
                "trace": trace,
                "chart_json": chart_json,
            },
        )

    @app.get("/jobs/{job_id}/report", response_class=HTMLResponse)
    async def report_page(request: Request, job_id: str) -> HTMLResponse:
        try:
            report = runner.get_report_response(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc
        return templates.TemplateResponse(
            request,
            "report.html",
            {
                "job_id": job_id,
                "report_html": markdown_lib.markdown(report.report_markdown),
                "chart_json": json.dumps([chart.model_dump() for chart in report.chart_payloads], ensure_ascii=False),
            },
        )

    @app.post("/api/jobs", response_model=CreateJobResponse)
    async def create_job_api(file: UploadFile = File(...)) -> CreateJobResponse:
        payload = await file.read()
        job_id = runner.create_job_from_upload(payload, file.filename or "uploaded.csv")
        runner.enqueue(job_id)
        return CreateJobResponse(job_id=job_id, status="queued")

    @app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
    async def get_job_status(job_id: str) -> JobStatusResponse:
        try:
            return storage.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.get("/api/jobs/{job_id}/report")
    async def get_report_api(job_id: str) -> dict[str, object]:
        try:
            report = runner.get_report_response(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc
        return report.model_dump()

    @app.get("/api/jobs/{job_id}/trace")
    async def get_trace_api(job_id: str) -> dict[str, object]:
        return runner.get_trace_response(job_id).model_dump()

    return app


app = create_app()
