from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas import SourceReference


class MCPAdapter(Protocol):
    name: str

    def search(self, query: str, *, limit: int = 3) -> list[SourceReference]:
        ...


@dataclass(slots=True)
class EconomicDataMCPAdapter:
    name: str = "economic-data"

    def search(self, query: str, *, limit: int = 3) -> list[SourceReference]:
        query_lower = query.lower()
        presets = [
            SourceReference(
                source_id="econ-open-data-employment",
                title="Open Employment Trend Reference",
                source_type="mcp_economic_data",
                provider="economic-data-mcp",
                summary="Synthetic public macro reference for employment change interpretation and time-series comparison.",
                excerpt="Public macro data indicates employment trend interpretation should account for dispersion and income-group asymmetry.",
                url="https://example.com/economic-data/employment-trend",
                score=0.77,
            ),
            SourceReference(
                source_id="econ-open-data-dispersion",
                title="Regional Dispersion Reference",
                source_type="mcp_economic_data",
                provider="economic-data-mcp",
                summary="Synthetic reference on regional divergence and anomaly interpretation in labor data.",
                excerpt="Regional divergence can persist even when aggregate employment improves, especially across income segments.",
                url="https://example.com/economic-data/regional-dispersion",
                score=0.68,
            ),
        ]
        if "policy" in query_lower or "brief" in query_lower:
            presets.reverse()
        return presets[:limit]


@dataclass(slots=True)
class ResearchMCPAdapter:
    name: str = "research"

    def search(self, query: str, *, limit: int = 3) -> list[SourceReference]:
        return [
            SourceReference(
                source_id="research-labor-brief",
                title="Labor Market Background Brief",
                source_type="mcp_research",
                provider="research-mcp",
                summary="Synthetic public research brief describing labor market volatility, low-income sensitivity, and policy framing.",
                excerpt="Low-income cohorts tend to react more sharply to short-term demand shocks, which can widen divergence during recoveries.",
                url="https://example.com/research/labor-market-brief",
                score=0.73,
            ),
            SourceReference(
                source_id="research-methodology-note",
                title="Interpretation Methodology Note",
                source_type="mcp_research",
                provider="research-mcp",
                summary="Synthetic note on interpreting anomalies in weekly employment data without overclaiming causality.",
                excerpt="Anomalies should be triangulated against recent history and structural context instead of treated as isolated signals.",
                url="https://example.com/research/methodology-note",
                score=0.61,
            ),
        ][:limit]


@dataclass(slots=True)
class MCPRegistry:
    adapters: dict[str, MCPAdapter]

    def search(self, source_name: str, query: str, *, limit: int = 3) -> list[SourceReference]:
        adapter = self.adapters.get(source_name)
        if adapter is None:
            return []
        return adapter.search(query, limit=limit)

    def list_sources(self) -> list[str]:
        return sorted(self.adapters)


def build_default_mcp_registry() -> MCPRegistry:
    return MCPRegistry(
        adapters={
            "economic-data": EconomicDataMCPAdapter(),
            "research": ResearchMCPAdapter(),
        }
    )
