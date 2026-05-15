from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import fmean, median, stdev

from app.schemas import AnomalyRecord, ChartPayload, CityMetric, CityTrend, DatasetOverview, IncomeSignal, TrendPoint
from app.services.data_loader import EmploymentDataset, EmploymentRecord, METRIC_COLUMNS, build_dataset_context, load_employment_data


INCOME_COLUMNS = [
    "emp_incq1",
    "emp_incq2",
    "emp_incq3",
    "emp_incq4",
    "emp_incmiddle",
    "emp_incbelowmed",
    "emp_incabovemed",
]


def _mean(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    return float(fmean(filtered)) if filtered else None


def _median(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    return float(median(filtered)) if filtered else None


def _stddev(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if len(filtered) < 2:
        return None
    return float(stdev(filtered))


@dataclass(slots=True)
class AnalyticsService:
    dataset_path: Path
    _dataset: EmploymentDataset | None = None

    def __post_init__(self) -> None:
        pass

    @property
    def dataset(self) -> EmploymentDataset:
        if self._dataset is None:
            self._dataset = load_employment_data(self.dataset_path)
        return self._dataset

    def dataset_overview(self) -> DatasetOverview:
        return DatasetOverview(**build_dataset_context(self.dataset))

    def periods(self) -> list[date]:
        return sorted({record.period_end for record in self.dataset})

    def latest_period_records(self) -> tuple[date, list[EmploymentRecord]]:
        latest_period = self.periods()[-1]
        records = [record for record in self.dataset if record.period_end == latest_period]
        return latest_period, records

    def latest_snapshot(self) -> dict[str, object]:
        latest_period, records = self.latest_period_records()
        values = [record.emp for record in records]
        overall = _mean(values)
        return {
            "latest_period": latest_period.isoformat(),
            "city_count": len({record.cityid for record in records}),
            "overall_emp_change": overall if overall is not None else 0.0,
            "median_emp_change": _median(values) or 0.0,
            "dispersion_std": _stddev(values) or 0.0,
        }

    def city_rankings(self, metric: str = "emp", top_n: int = 5) -> dict[str, list[dict[str, float | int]]]:
        _, records = self.latest_period_records()
        ranked = sorted(
            (
                CityMetric(cityid=record.cityid, value=value)
                for record in records
                if (value := record.get_metric(metric)) is not None
            ),
            key=lambda item: item.value,
            reverse=True,
        )
        return {
            "top": [item.model_dump() for item in ranked[:top_n]],
            "bottom": [item.model_dump() for item in sorted(ranked[-top_n:], key=lambda item: item.value)],
        }

    def recent_trend(self, metric: str = "emp", weeks: int = 6) -> list[TrendPoint]:
        grouped: dict[date, list[float | None]] = defaultdict(list)
        for record in self.dataset:
            grouped[record.period_end].append(record.get_metric(metric))
        periods = sorted(grouped)[-weeks:]
        return [
            TrendPoint(period=period.isoformat(), value=_mean(grouped[period]) or 0.0)
            for period in periods
        ]

    def city_trend(self, city_ids: list[int], metric: str = "emp", weeks: int = 6) -> list[CityTrend]:
        output: list[CityTrend] = []
        for city_id in sorted(set(city_ids)):
            points = [
                TrendPoint(period=record.period_end.isoformat(), value=value)
                for record in self.dataset
                if record.cityid == city_id and (value := record.get_metric(metric)) is not None
            ][-weeks:]
            if points:
                output.append(CityTrend(cityid=city_id, points=points))
        return output

    def income_group_comparison(self, lookback_weeks: int = 4) -> list[IncomeSignal]:
        latest_period, latest_records = self.latest_period_records()
        recent_periods = set(self.periods()[-max(lookback_weeks, 1) :])
        recent_records = [record for record in self.dataset if record.period_end in recent_periods]
        overall_latest = _mean([record.emp for record in latest_records]) or 0.0
        signals: list[IncomeSignal] = []
        for column in INCOME_COLUMNS:
            latest_value = _mean([record.get_metric(column) for record in latest_records])
            recent_average = _mean([record.get_metric(column) for record in recent_records])
            signals.append(
                IncomeSignal(
                    segment=column,
                    latest_value=latest_value,
                    recent_average=recent_average,
                    gap_vs_overall=None if latest_value is None else latest_value - overall_latest,
                )
            )
        return signals

    def detect_anomalies(
        self,
        metric: str = "emp",
        lookback_weeks: int = 8,
        z_threshold: float = 1.8,
        limit: int = 6,
    ) -> list[AnomalyRecord]:
        latest_period, latest_records = self.latest_period_records()
        history_periods = [period for period in self.periods() if period < latest_period][-lookback_weeks:]
        anomalies: list[AnomalyRecord] = []
        for latest_record in latest_records:
            latest_value = latest_record.get_metric(metric)
            if latest_value is None:
                continue
            baseline = [
                record.get_metric(metric)
                for record in self.dataset
                if record.cityid == latest_record.cityid and record.period_end in history_periods
            ]
            avg = _mean(baseline)
            deviation = _stddev(baseline)
            if avg is None or deviation in {None, 0.0}:
                continue
            zscore = (latest_value - avg) / deviation
            if abs(zscore) >= z_threshold:
                anomalies.append(
                    AnomalyRecord(
                        cityid=latest_record.cityid,
                        metric=metric,
                        latest_value=latest_value,
                        zscore=zscore,
                        reason=f"Latest {metric} deviates from the recent {lookback_weeks}-week mean.",
                    )
                )
        anomalies.sort(key=lambda item: abs(item.zscore or 0.0), reverse=True)
        return anomalies[:limit]

    def build_chart_payloads(self, top_n: int = 5) -> list[ChartPayload]:
        latest = self.latest_snapshot()
        rankings = self.city_rankings(top_n=top_n)
        trend = self.recent_trend(weeks=8)
        income = self.income_group_comparison()
        return [
            ChartPayload(
                chart_type="overall_trend",
                title="Overall Employment Trend",
                labels=[point.period for point in trend],
                datasets=[{"label": "emp", "data": [point.value for point in trend]}],
            ),
            ChartPayload(
                chart_type="city_rankings",
                title=f"Top and Bottom Cities ({latest['latest_period']})",
                labels=[f"City {item['cityid']}" for item in rankings["top"] + rankings["bottom"]],
                datasets=[
                    {
                        "label": "emp",
                        "data": [float(item["value"]) for item in rankings["top"] + rankings["bottom"]],
                    }
                ],
            ),
            ChartPayload(
                chart_type="income_groups",
                title="Income Group Snapshot",
                labels=[signal.segment for signal in income],
                datasets=[{"label": "latest", "data": [signal.latest_value for signal in income]}],
            ),
        ]
