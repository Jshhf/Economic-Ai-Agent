from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


REQUIRED_COLUMNS = [
    "year",
    "month",
    "day_endofweek",
    "cityid",
    "emp",
    "emp_incq1",
    "emp_incq2",
    "emp_incq3",
    "emp_incq4",
    "emp_incmiddle",
    "emp_incbelowmed",
    "emp_incabovemed",
]

METRIC_COLUMNS = REQUIRED_COLUMNS[4:]


@dataclass(slots=True)
class EmploymentRecord:
    year: int
    month: int
    day_endofweek: int
    cityid: int
    emp: float | None
    emp_incq1: float | None
    emp_incq2: float | None
    emp_incq3: float | None
    emp_incq4: float | None
    emp_incmiddle: float | None
    emp_incbelowmed: float | None
    emp_incabovemed: float | None
    period_end: date

    def get_metric(self, metric: str) -> float | None:
        if not hasattr(self, metric):
            raise KeyError(f"Unknown metric: {metric}")
        return getattr(self, metric)


EmploymentDataset = list[EmploymentRecord]


def _parse_int(value: str | None, column: str) -> int:
    if value is None or value == "":
        raise ValueError(f"Missing required integer value in column {column}")
    return int(value)


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned in {"", "."}:
        return None
    return float(cleaned)


def load_employment_data(path: str | Path) -> EmploymentDataset:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        if reader.fieldnames is None:
            raise ValueError("The dataset does not contain headers.")
        missing = sorted(set(REQUIRED_COLUMNS).difference(reader.fieldnames))
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        records: EmploymentDataset = []
        for row in reader:
            year = _parse_int(row["year"], "year")
            month = _parse_int(row["month"], "month")
            day = _parse_int(row["day_endofweek"], "day_endofweek")
            cityid = _parse_int(row["cityid"], "cityid")
            period_end = date(year, month, day)
            records.append(
                EmploymentRecord(
                    year=year,
                    month=month,
                    day_endofweek=day,
                    cityid=cityid,
                    emp=_parse_float(row["emp"]),
                    emp_incq1=_parse_float(row["emp_incq1"]),
                    emp_incq2=_parse_float(row["emp_incq2"]),
                    emp_incq3=_parse_float(row["emp_incq3"]),
                    emp_incq4=_parse_float(row["emp_incq4"]),
                    emp_incmiddle=_parse_float(row["emp_incmiddle"]),
                    emp_incbelowmed=_parse_float(row["emp_incbelowmed"]),
                    emp_incabovemed=_parse_float(row["emp_incabovemed"]),
                    period_end=period_end,
                )
            )

    if not records:
        raise ValueError("The dataset is empty.")

    records.sort(key=lambda item: (item.period_end, item.cityid))
    return records


def build_dataset_context(dataset: EmploymentDataset) -> dict[str, object]:
    periods = [record.period_end for record in dataset]
    city_ids = {record.cityid for record in dataset}
    missing_values = {
        column: sum(1 for record in dataset if record.get_metric(column) is None)
        for column in METRIC_COLUMNS
    }
    return {
        "row_count": len(dataset),
        "city_count": len(city_ids),
        "columns": [*REQUIRED_COLUMNS, "period_end"],
        "start_date": min(periods).isoformat(),
        "end_date": max(periods).isoformat(),
        "missing_values": missing_values,
    }
