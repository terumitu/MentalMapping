"""log_reader.py 単体テスト (v2 仕様 / 5段階 8項目)。"""
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
    mood: Any,
    energy: Any,
    thinking: Any,
    focus: Any,
    sleep_hours: Any,
    weather: Any,
    medication: Any,
    period: Any,
    recorded_at: str,
) -> Dict[str, Any]:
    return {
        "date": date,
        "mood": mood,
        "energy": energy,
        "thinking": thinking,
        "focus": focus,
        "sleep_hours": sleep_hours,
        "weather": weather,
        "medication": medication,
        "period": period,
        "recorded_at": recorded_at,
    }


# ---- fetch_all --------------------------------------------------------------


def test_fetch_all_returns_records_as_list() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 3, 3, 7.0, "晴", "TRUE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 4, 4, 3, 3, 6.5, "曇", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    records = LogReader(ws).fetch_all()
    assert len(records) == 2
    assert records[0]["date"] == "2026-04-10"
    assert records[1]["mood"] == 4


def test_fetch_all_empty() -> None:
    assert LogReader(FakeWorksheet([])).fetch_all() == []


# ---- fetch_latest_per_day ---------------------------------------------------


def test_fetch_latest_per_day_keeps_only_latest_for_same_date() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 2, 2, 2, 2, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-10T08:00:00"),
            _row("2026-04-10", 4, 4, 4, 4, 7.0, "晴", "TRUE", "FALSE",
                 "2026-04-10T20:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 6.5, "曇", "TRUE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    latest = LogReader(ws).fetch_latest_per_day()
    assert len(latest) == 2
    by_date = {r["date"]: r for r in latest}
    assert by_date["2026-04-10"]["mood"] == 4
    assert by_date["2026-04-10"]["medication"] == "TRUE"
    assert by_date["2026-04-11"]["mood"] == 3


def test_fetch_latest_per_day_sorts_dates_ascending() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
            _row("2026-04-09", 2, 2, 2, 2, 5.0, "雨", "FALSE", "FALSE",
                 "2026-04-09T09:00:00"),
            _row("2026-04-10", 5, 5, 5, 5, 8.0, "晴", "TRUE", "FALSE",
                 "2026-04-10T09:00:00"),
        ]
    )
    dates = [r["date"] for r in LogReader(ws).fetch_latest_per_day()]
    assert dates == ["2026-04-09", "2026-04-10", "2026-04-11"]


def test_fetch_latest_per_day_skips_blank_date() -> None:
    ws = FakeWorksheet(
        [
            _row("", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
            _row("2026-04-11", 4, 4, 4, 4, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T10:00:00"),
        ]
    )
    latest = LogReader(ws).fetch_latest_per_day()
    assert len(latest) == 1
    assert latest[0]["mood"] == 4


def test_fetch_latest_per_day_empty() -> None:
    assert LogReader(FakeWorksheet([])).fetch_latest_per_day() == []


# ---- aggregate_mood / energy / thinking / focus ----------------------------


def test_aggregate_mood_basic() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 2, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 4, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_mood() == {
        "count": 2, "mean": 3.0, "min": 2.0, "max": 4.0,
    }


def test_aggregate_mood_uses_latest_per_day() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-11", 1, 1, 1, 1, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T08:00:00"),
            _row("2026-04-11", 5, 5, 5, 5, 7.0, "晴", "TRUE", "FALSE",
                 "2026-04-11T20:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_mood() == {
        "count": 1, "mean": 5.0, "min": 5.0, "max": 5.0,
    }


def test_aggregate_energy_basic() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 2, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 4, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_energy() == {
        "count": 2, "mean": 3.0, "min": 2.0, "max": 4.0,
    }


def test_aggregate_thinking_basic() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 5, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 1, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_thinking() == {
        "count": 2, "mean": 3.0, "min": 1.0, "max": 5.0,
    }


def test_aggregate_focus_basic() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 3, 2, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 4, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_focus() == {
        "count": 2, "mean": 3.0, "min": 2.0, "max": 4.0,
    }


def test_aggregate_empty_returns_none_fields() -> None:
    reader = LogReader(FakeWorksheet([]))
    expected = {"count": 0, "mean": None, "min": None, "max": None}
    assert reader.aggregate_mood() == expected
    assert reader.aggregate_energy() == expected
    assert reader.aggregate_thinking() == expected
    assert reader.aggregate_focus() == expected


def test_aggregate_ignores_non_numeric() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", "", 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", "n/a", 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
            _row("2026-04-12", 4, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-12T09:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_mood() == {
        "count": 1, "mean": 4.0, "min": 4.0, "max": 4.0,
    }


# ---- aggregate_sleep --------------------------------------------------------


def test_aggregate_sleep_basic() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 3, 3, 6.0, "晴", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 8.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_sleep() == {
        "count": 2, "mean": 7.0, "min": 6.0, "max": 8.0,
    }


def test_aggregate_sleep_skips_empty_cells() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 3, 3, "", "晴", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 7.5, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).aggregate_sleep() == {
        "count": 1, "mean": 7.5, "min": 7.5, "max": 7.5,
    }


# ---- medication_ratio / period_ratio ---------------------------------------


def test_medication_ratio_counts_true_values() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-08", 3, 3, 3, 3, 7.0, "晴", "TRUE", "FALSE",
                 "2026-04-08T09:00:00"),
            _row("2026-04-09", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-09T09:00:00"),
            _row("2026-04-10", 3, 3, 3, 3, 7.0, "晴", "TRUE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).medication_ratio() == 0.5


def test_medication_ratio_empty_returns_none() -> None:
    assert LogReader(FakeWorksheet([])).medication_ratio() is None


def test_medication_ratio_respects_latest_per_day() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T08:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "晴", "TRUE", "FALSE",
                 "2026-04-11T20:00:00"),
        ]
    )
    assert LogReader(ws).medication_ratio() == 1.0


def test_medication_ratio_ignores_empty_cells() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 3, 3, 7.0, "晴", "", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "晴", "TRUE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).medication_ratio() == 1.0


def test_period_ratio_counts_true_values() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 3, 3, 7.0, "晴", "FALSE", "TRUE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).period_ratio() == 0.5


def test_period_ratio_empty_returns_none() -> None:
    assert LogReader(FakeWorksheet([])).period_ratio() is None


# ---- weather_distribution --------------------------------------------------


def test_weather_distribution_counts() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-08", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-08T09:00:00"),
            _row("2026-04-09", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-09T09:00:00"),
            _row("2026-04-10", 3, 3, 3, 3, 7.0, "曇", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "雨", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    dist = LogReader(ws).weather_distribution()
    assert dist == {"晴": 2, "曇": 1, "雨": 1}


def test_weather_distribution_skips_empty() -> None:
    ws = FakeWorksheet(
        [
            _row("2026-04-10", 3, 3, 3, 3, 7.0, "", "FALSE", "FALSE",
                 "2026-04-10T09:00:00"),
            _row("2026-04-11", 3, 3, 3, 3, 7.0, "晴", "FALSE", "FALSE",
                 "2026-04-11T09:00:00"),
        ]
    )
    assert LogReader(ws).weather_distribution() == {"晴": 1}


def test_weather_distribution_empty() -> None:
    assert LogReader(FakeWorksheet([])).weather_distribution() == {}
