"""log_reader.py 単体テスト。"""
from __future__ import annotations

from typing import Any, Dict, List

from modules.log_reader import LogReader


class FakeWorksheet:
    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self._records = records

    def get_all_records(self) -> List[Dict[str, Any]]:
        return list(self._records)


def _row(
    date: str,
    mood_score: Any,
    sleep_hours: Any,
    went_outside: Any,
    memo: str,
    recorded_at: str,
) -> Dict[str, Any]:
    return {
        "date": date,
        "mood_score": mood_score,
        "sleep_hours": sleep_hours,
        "went_outside": went_outside,
        "memo": memo,
        "recorded_at": recorded_at,
    }


# ---- fetch_all --------------------------------------------------------------


def test_fetch_all_returns_records_as_list() -> None:
    ws = FakeWorksheet([
        _row("2026-04-09", 6, 7.0, "TRUE", "", "2026-04-09T09:00:00"),
        _row("2026-04-10", 7, 6.5, "FALSE", "x", "2026-04-10T09:00:00"),
    ])
    reader = LogReader(ws)
    records = reader.fetch_all()
    assert len(records) == 2
    assert records[0]["date"] == "2026-04-09"


def test_fetch_all_empty() -> None:
    reader = LogReader(FakeWorksheet([]))
    assert reader.fetch_all() == []


# ---- fetch_latest_per_day ---------------------------------------------------


def test_fetch_latest_per_day_keeps_only_latest_for_same_date() -> None:
    ws = FakeWorksheet([
        _row("2026-04-09", 4, 7.0, "FALSE", "morning", "2026-04-09T08:00:00"),
        _row("2026-04-09", 7, 7.0, "TRUE", "evening", "2026-04-09T20:00:00"),
        _row("2026-04-10", 5, 6.5, "TRUE", "", "2026-04-10T09:00:00"),
    ])
    reader = LogReader(ws)
    latest = reader.fetch_latest_per_day()
    assert len(latest) == 2

    by_date = {r["date"]: r for r in latest}
    assert by_date["2026-04-09"]["memo"] == "evening"
    assert by_date["2026-04-09"]["mood_score"] == 7
    assert by_date["2026-04-10"]["mood_score"] == 5


def test_fetch_latest_per_day_sorts_dates_ascending() -> None:
    ws = FakeWorksheet([
        _row("2026-04-10", 5, 7.0, "TRUE", "", "2026-04-10T09:00:00"),
        _row("2026-04-08", 3, 5.0, "FALSE", "", "2026-04-08T09:00:00"),
        _row("2026-04-09", 7, 8.0, "TRUE", "", "2026-04-09T09:00:00"),
    ])
    reader = LogReader(ws)
    dates = [r["date"] for r in reader.fetch_latest_per_day()]
    assert dates == ["2026-04-08", "2026-04-09", "2026-04-10"]


def test_fetch_latest_per_day_skips_blank_date() -> None:
    ws = FakeWorksheet([
        _row("", 5, 7.0, "TRUE", "garbage", "2026-04-10T09:00:00"),
        _row("2026-04-10", 6, 7.0, "TRUE", "ok", "2026-04-10T10:00:00"),
    ])
    reader = LogReader(ws)
    latest = reader.fetch_latest_per_day()
    assert len(latest) == 1
    assert latest[0]["memo"] == "ok"


def test_fetch_latest_per_day_empty() -> None:
    reader = LogReader(FakeWorksheet([]))
    assert reader.fetch_latest_per_day() == []


# ---- aggregate_mood ---------------------------------------------------------


def test_aggregate_mood_basic() -> None:
    ws = FakeWorksheet([
        _row("2026-04-08", 4, 7.0, "FALSE", "", "2026-04-08T09:00:00"),
        _row("2026-04-09", 8, 7.0, "TRUE", "", "2026-04-09T09:00:00"),
    ])
    reader = LogReader(ws)
    agg = reader.aggregate_mood()
    assert agg == {"count": 2, "mean": 6.0, "min": 4.0, "max": 8.0}


def test_aggregate_mood_uses_latest_per_day() -> None:
    ws = FakeWorksheet([
        _row("2026-04-09", 2, 7.0, "FALSE", "morning", "2026-04-09T08:00:00"),
        _row("2026-04-09", 8, 7.0, "TRUE", "evening", "2026-04-09T20:00:00"),
    ])
    agg = LogReader(ws).aggregate_mood()
    # 同日: 最新の 8 のみ採用され、2 は集計に含まれない
    assert agg == {"count": 1, "mean": 8.0, "min": 8.0, "max": 8.0}


def test_aggregate_mood_empty_returns_none_fields() -> None:
    agg = LogReader(FakeWorksheet([])).aggregate_mood()
    assert agg == {"count": 0, "mean": None, "min": None, "max": None}


def test_aggregate_mood_ignores_non_numeric() -> None:
    ws = FakeWorksheet([
        _row("2026-04-08", "", 7.0, "FALSE", "", "2026-04-08T09:00:00"),
        _row("2026-04-09", "n/a", 7.0, "TRUE", "", "2026-04-09T09:00:00"),
        _row("2026-04-10", 6, 7.0, "TRUE", "", "2026-04-10T09:00:00"),
    ])
    agg = LogReader(ws).aggregate_mood()
    assert agg == {"count": 1, "mean": 6.0, "min": 6.0, "max": 6.0}


# ---- aggregate_sleep --------------------------------------------------------


def test_aggregate_sleep_basic() -> None:
    ws = FakeWorksheet([
        _row("2026-04-08", 5, 6.0, "FALSE", "", "2026-04-08T09:00:00"),
        _row("2026-04-09", 6, 8.0, "TRUE", "", "2026-04-09T09:00:00"),
    ])
    agg = LogReader(ws).aggregate_sleep()
    assert agg == {"count": 2, "mean": 7.0, "min": 6.0, "max": 8.0}


# ---- outside_ratio ----------------------------------------------------------


def test_outside_ratio_counts_true_values() -> None:
    ws = FakeWorksheet([
        _row("2026-04-08", 5, 7.0, "TRUE", "", "2026-04-08T09:00:00"),
        _row("2026-04-09", 5, 7.0, "FALSE", "", "2026-04-09T09:00:00"),
        _row("2026-04-10", 5, 7.0, "TRUE", "", "2026-04-10T09:00:00"),
        _row("2026-04-11", 5, 7.0, "FALSE", "", "2026-04-11T09:00:00"),
    ])
    assert LogReader(ws).outside_ratio() == 0.5


def test_outside_ratio_empty_returns_none() -> None:
    assert LogReader(FakeWorksheet([])).outside_ratio() is None


def test_outside_ratio_respects_latest_per_day() -> None:
    # 同日で FALSE → TRUE に上書きされるケース
    ws = FakeWorksheet([
        _row("2026-04-10", 5, 7.0, "FALSE", "morning", "2026-04-10T08:00:00"),
        _row("2026-04-10", 5, 7.0, "TRUE", "evening", "2026-04-10T20:00:00"),
    ])
    assert LogReader(ws).outside_ratio() == 1.0
