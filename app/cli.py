from __future__ import annotations

import argparse

from app.config import get_settings
from app.jobs import JobRunner
from app.storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Economic Agent Platform CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_local = subparsers.add_parser("run-local", help="Run a local analysis job against a CSV file")
    run_local.add_argument("--file", required=True, help="Path to the CSV file")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    storage = Storage(settings.database_path)
    storage.init_db()
    runner = JobRunner(settings=settings, storage=storage)

    if args.command == "run-local":
        job_id = runner.create_job_from_file(args.file)
        runner.run_analysis_job(job_id)
        job = storage.get_job(job_id)
        print(f"job_id={job_id}")
        print(f"status={job.status}")
        if job.status == "completed":
            report = runner.get_report_response(job_id)
            print(report.report_markdown)
        else:
            print(f"error={job.error_message}")


if __name__ == "__main__":
    main()
