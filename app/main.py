from __future__ import annotations

import json

import markdown as markdown_lib
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT, Settings, get_settings
from app.jobs import JobRunner
from app.schemas import CreateJobResponse, JobStatusResponse, KnowledgeSearchResponse
from app.services.knowledge_base import KnowledgeBase
from app.services.mcp import build_default_mcp_registry
from app.services.rag import RagService
from app.skills import DEFAULT_STAGE_ORDER, get_skill, get_stage_disclosure, list_skills
from app.storage import Storage


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    storage = Storage(PROJECT_ROOT / resolved_settings.database_path)
    storage.init_db()
    runner = JobRunner(settings=resolved_settings, storage=storage)
    rag_service = RagService(PROJECT_ROOT / resolved_settings.knowledge_dir)
    mcp_registry = build_default_mcp_registry()
    knowledge_base = KnowledgeBase(PROJECT_ROOT / resolved_settings.knowledge_dir)

    app = FastAPI(title=resolved_settings.app_name)
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
    app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")

    app.state.settings = resolved_settings
    app.state.storage = storage
    app.state.runner = runner
    app.state.templates = templates
    app.state.rag_service = rag_service
    app.state.mcp_registry = mcp_registry
    app.state.knowledge_base = knowledge_base

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": resolved_settings.app_name,
                "sample_path": str(PROJECT_ROOT / "data" / "Employment - City - Weekly.csv"),
                "openai_enabled": bool(resolved_settings.openai_api_key),
                "skills": list_skills(),
                "mcp_sources": mcp_registry.list_sources(),
                "knowledge_docs": knowledge_base.list_documents(),
            },
        )

    @app.post("/jobs", response_class=HTMLResponse)
    async def create_job_page(
        request: Request,
        file: UploadFile = File(...),
        skill_id: str = Form("economic_report"),
    ) -> RedirectResponse:
        payload = await file.read()
        resolved_skill = runner.validate_skill(skill_id)
        job_id = runner.create_job_from_upload(payload, file.filename or "uploaded.csv", skill_id=resolved_skill)
        runner.enqueue(job_id)
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_detail(request: Request, job_id: str) -> HTMLResponse:
        try:
            job = storage.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        return templates.TemplateResponse(
            request,
            "job_detail.html",
            {"job_id": job_id, "title": f"Job {job_id}", "job": job},
        )

    @app.get("/jobs/{job_id}/panel", response_class=HTMLResponse)
    async def job_panel(request: Request, job_id: str) -> HTMLResponse:
        try:
            job = storage.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

        report = None
        trace = runner.get_trace_response(job_id)
        goal_summary = runner.get_goal_summary_response(job_id)
        report_html = None
        chart_json = "[]"
        sources = []
        if job.status == "completed":
            report = runner.get_report_response(job_id)
            sources = runner.get_sources_response(job_id).sources
            report_html = markdown_lib.markdown(report.report_markdown)
            chart_json = json.dumps([chart.model_dump() for chart in report.chart_payloads], ensure_ascii=False)
        elif job.status == "failed":
            sources = runner.get_sources_response(job_id).sources
        disclosure_stage = goal_summary.summary.current_stage if goal_summary else job.current_stage
        stage_disclosure = get_stage_disclosure(job.skill_id, disclosure_stage)
        skill_definition = get_skill(job.skill_id)
        disclosure_plan = [
            skill_definition.stage_disclosures[stage]
            for stage in DEFAULT_STAGE_ORDER
            if stage in skill_definition.stage_disclosures
        ]

        return templates.TemplateResponse(
            request,
            "partials/job_panel.html",
            {
                "job": job,
                "job_id": job_id,
                "report": report,
                "report_html": report_html,
                "trace": trace,
                "goal_summary": goal_summary,
                "stage_disclosure": stage_disclosure,
                "disclosure_plan": disclosure_plan,
                "chart_json": chart_json,
                "sources": sources,
            },
        )

    @app.get("/jobs/{job_id}/report", response_class=HTMLResponse)
    async def report_page(request: Request, job_id: str) -> HTMLResponse:
        try:
            report = runner.get_report_response(job_id)
            sources = runner.get_sources_response(job_id).sources
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc
        return templates.TemplateResponse(
            request,
            "report.html",
            {
                "job_id": job_id,
                "report": report,
                "sources": sources,
                "report_html": markdown_lib.markdown(report.report_markdown),
                "chart_json": json.dumps([chart.model_dump() for chart in report.chart_payloads], ensure_ascii=False),
            },
        )

    @app.post("/api/jobs", response_model=CreateJobResponse)
    async def create_job_api(
        file: UploadFile = File(...),
        skill_id: str = Form("economic_report"),
    ) -> CreateJobResponse:
        payload = await file.read()
        resolved_skill = runner.validate_skill(skill_id)
        job_id = runner.create_job_from_upload(payload, file.filename or "uploaded.csv", skill_id=resolved_skill)
        runner.enqueue(job_id)
        return CreateJobResponse(job_id=job_id, status="queued", skill_id=resolved_skill)

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

    @app.get("/api/jobs/{job_id}/goal-summary")
    async def get_goal_summary_api(job_id: str) -> dict[str, object]:
        try:
            return runner.get_goal_summary_response(job_id).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Goal summary not found") from exc

    @app.get("/api/jobs/{job_id}/sources")
    async def get_job_sources(job_id: str) -> dict[str, object]:
        return runner.get_sources_response(job_id).model_dump()

    @app.get("/api/skills")
    async def get_skills() -> list[dict[str, object]]:
        return [skill.model_dump() for skill in list_skills()]

    @app.get("/api/knowledge/search", response_model=KnowledgeSearchResponse)
    async def search_knowledge(q: str = Query(..., min_length=2)) -> KnowledgeSearchResponse:
        local_results = rag_service.search(q, limit=resolved_settings.rag_top_k)
        external_results = []
        for source_name in mcp_registry.list_sources():
            external_results.extend(mcp_registry.search(source_name, q, limit=1))
        results = local_results + external_results
        return KnowledgeSearchResponse(query=q, results=results)

    return app


app = create_app()
