from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.storage import Storage


@dataclass(slots=True)
class ObservabilityService:
    storage: Storage
    provider_status: dict[str, bool] = field(
        default_factory=lambda: {
            "opentelemetry": True,
            "langfuse": False,
            "prometheus": True,
            "grafana": False,
        }
    )

    def emit_metric(self, metric_name: str, metric_value: float, *, job_id: str | None = None, labels: dict[str, Any] | None = None) -> None:
        self.storage.log_metric(metric_name, metric_value, job_id=job_id, labels=labels)

    def collect_summary(self, job_id: str | None = None) -> dict[str, Any]:
        metrics = self.storage.list_metrics(job_id)
        return {
            "providers": self.provider_status,
            "metrics": metrics,
        }
