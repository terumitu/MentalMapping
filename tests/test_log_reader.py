"""log_reader.py 単体テスト (v1.2 仕様 / 17 列・fetch_active_records)。"""
from __future__ import annotations

from typing import Any, Dict, List

from modules.log_reader import LogReader


class FakeWorksheet:
    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self._records = records

    def get_all_records(self) -> List[Dict[str, Any]]:
        return list(self._records)


def _row(
    *,
    date: str,
    mood: Any = 3,
    energy: Any = 3,
    thinking: Any = 3,
    focus: Any = 3,
    sleep_hours: Any = 7.0,
    weather: Any = "晴",
    medication: Any = "FALSE",
    period: Any = "FALSE",
    recorded_at: str = "",
    time_of_day: str = "morning",
    daily_aspects: str = "",
    record_id: str = "",
    record_status: str = "active",
    superseded_by: str = "",
    entry_mode: str = "realtime",
    input_user: str = "masuda",
) -> Dict[str, Any]:
    return {
        "date": date, "mood": mood, "energy": energy,
        "thinking": thinking, "focus": focus,
        "sleep_hours": sleep_hours, "weather": weather,
        "medication": medication, "period": period,
        "recorded_at": recorded_at or f"{date}T09:00:00",
        "time_of_day": time_of_day, "daily_aspects": daily_aspects,
        "record_id": record_id or f"{input_user}_{date}_{time_of_day}_1",
        "record_status": record_status, "superseded_by": superseded_by,
        "entry_mode": entry_mode, "input_user": input_user,
    }


# ---- fetch_all --------------------------------------------------------------


def test_fetch_all_returns_records_as_list() -> None:
    ws = FakeWorksheet(
        [_row(date="2026-04-10"), _row(date="2026-04-11", mood=4)]
    )
    records = LogReader(ws).fetch_all()
    assert len(records) == 2
    assert records[1]["mood"] == 4


def test_fetch_all_empty() -> None:
    assert LogReader(FakeWorksheet([])).fetch_all() == []


# ---- fetch_active_records ---------------------------------------------------


def test_fetch_active_records_filters_superseded() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-16", time_of_day="evening", mood=3,
             recorded_at="2026-04-16T20:34:00", record_status="superseded",
             superseded_by="masuda_2026-04-16_evening_xyz",
             record_id="masuda_2026-04-16_evening_old"),
        _row(date="2026-04-16", time_of_day="evening", mood=4,
             recorded_at="2026-04-16T20:45:00", record_status="active",
             record_id="masuda_2026-04-16_evening_xyz"),
    ])
    active = LogReader(ws).fetch_active_records()
    assert len(active) == 1
    assert active[0]["mood"] == 4
    assert active[0]["record_status"] == "active"


def test_fetch_active_records_includes_not_recorded() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-16", time_of_day="morning",
             mood="", energy="", thinking="", focus="",
             entry_mode="not_recorded", record_status="active"),
    ])
    active = LogReader(ws).fetch_active_records()
    assert len(active) == 1
    assert active[0]["entry_mode"] == "not_recorded"


def test_fetch_active_records_sorts_by_date_and_time_of_day() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-11", time_of_day="evening"),
        _row(date="2026-04-11", time_of_day="morning"),
        _row(date="2026-04-10", time_of_day="evening"),
    ])
    active = LogReader(ws).fetch_active_records()
    keys = [(r["date"], r["time_of_day"]) for r in active]
    assert keys == [
        ("2026-04-10", "evening"),
        ("2026-04-11", "evening"),
        ("2026-04-11", "morning"),
    ]


def test_fetch_active_records_empty() -> None:
    assert LogReader(FakeWorksheet([])).fetch_active_records() == []


# ---- get_revision_chain ----------------------------------------------------


def test_get_revision_chain_returns_chronological() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-17", time_of_day="morning", mood=3,
             recorded_at="2026-04-17T11:18:00", record_status="superseded",
             superseded_by="",
             record_id="masuda_2026-04-17_morning_rejected"),
        _row(date="2026-04-17", time_of_day="morning", mood=4,
             recorded_at="2026-04-17T07:45:00", record_status="active",
             record_id="masuda_2026-04-17_morning_active"),
    ])
    chain = LogReader(ws).get_revision_chain("masuda", "2026-04-17", "morning")
    assert len(chain) == 2
    # recorded_at 昇順 (07:45 が先)
    assert chain[0]["recorded_at"] == "2026-04-17T07:45:00"
    assert chain[1]["recorded_at"] == "2026-04-17T11:18:00"


def test_get_revision_chain_filters_by_scope() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-17", time_of_day="morning", input_user="masuda"),
        _row(date="2026-04-17", time_of_day="evening", input_user="masuda"),
        _row(date="2026-04-17", time_of_day="morning", input_user="nishide"),
    ])
    chain = LogReader(ws).get_revision_chain("masuda", "2026-04-17", "morning")
    assert len(chain) == 1
    assert chain[0]["input_user"] == "masuda"
    assert chain[0]["time_of_day"] == "morning"


# ---- aggregate : active かつ not_recorded 除外 ------------------------------


def test_aggregate_mood_basic() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", mood=2),
        _row(date="2026-04-11", mood=4),
    ])
    assert LogReader(ws).aggregate_mood() == {
        "count": 2, "mean": 3.0, "min": 2.0, "max": 4.0,
    }


def test_aggregate_mood_excludes_superseded() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-11", mood=1, record_status="superseded",
             superseded_by="masuda_2026-04-11_morning_new"),
        _row(date="2026-04-11", mood=5, record_status="active",
             recorded_at="2026-04-11T20:00:00"),
    ])
    assert LogReader(ws).aggregate_mood() == {
        "count": 1, "mean": 5.0, "min": 5.0, "max": 5.0,
    }


def test_aggregate_mood_excludes_not_recorded() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", mood=2),
        _row(date="2026-04-16", mood="", entry_mode="not_recorded"),
    ])
    # not_recorded は集計対象外
    assert LogReader(ws).aggregate_mood() == {
        "count": 1, "mean": 2.0, "min": 2.0, "max": 2.0,
    }


def test_aggregate_energy_basic() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", energy=2),
        _row(date="2026-04-11", energy=4),
    ])
    assert LogReader(ws).aggregate_energy() == {
        "count": 2, "mean": 3.0, "min": 2.0, "max": 4.0,
    }


def test_aggregate_thinking_basic() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", thinking=5),
        _row(date="2026-04-11", thinking=1),
    ])
    assert LogReader(ws).aggregate_thinking() == {
        "count": 2, "mean": 3.0, "min": 1.0, "max": 5.0,
    }


def test_aggregate_focus_basic() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", focus=2),
        _row(date="2026-04-11", focus=4),
    ])
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
    ws = FakeWorksheet([
        _row(date="2026-04-10", mood=""),
        _row(date="2026-04-11", mood="n/a"),
        _row(date="2026-04-12", mood=4),
    ])
    assert LogReader(ws).aggregate_mood() == {
        "count": 1, "mean": 4.0, "min": 4.0, "max": 4.0,
    }


# ---- aggregate_sleep --------------------------------------------------------


def test_aggregate_sleep_basic() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", sleep_hours=6.0),
        _row(date="2026-04-11", sleep_hours=8.0),
    ])
    assert LogReader(ws).aggregate_sleep() == {
        "count": 2, "mean": 7.0, "min": 6.0, "max": 8.0,
    }


def test_aggregate_sleep_skips_empty_cells() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", sleep_hours=""),
        _row(date="2026-04-11", sleep_hours=7.5),
    ])
    assert LogReader(ws).aggregate_sleep() == {
        "count": 1, "mean": 7.5, "min": 7.5, "max": 7.5,
    }


# ---- medication_ratio / period_ratio ---------------------------------------


def test_medication_ratio_counts_true_values() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-08", medication="TRUE"),
        _row(date="2026-04-09", medication="FALSE"),
        _row(date="2026-04-10", medication="TRUE"),
        _row(date="2026-04-11", medication="FALSE"),
    ])
    assert LogReader(ws).medication_ratio() == 0.5


def test_medication_ratio_empty_returns_none() -> None:
    assert LogReader(FakeWorksheet([])).medication_ratio() is None


def test_medication_ratio_ignores_empty_cells() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", medication=""),
        _row(date="2026-04-11", medication="TRUE"),
    ])
    assert LogReader(ws).medication_ratio() == 1.0


def test_period_ratio_counts_true_values() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", period="TRUE"),
        _row(date="2026-04-11", period="FALSE"),
    ])
    assert LogReader(ws).period_ratio() == 0.5


def test_period_ratio_empty_returns_none() -> None:
    assert LogReader(FakeWorksheet([])).period_ratio() is None


# ---- weather_distribution --------------------------------------------------


def test_weather_distribution_counts() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-08", weather="晴"),
        _row(date="2026-04-09", weather="晴"),
        _row(date="2026-04-10", weather="曇"),
        _row(date="2026-04-11", weather="雨/雪"),
    ])
    dist = LogReader(ws).weather_distribution()
    assert dist == {"晴": 2, "曇": 1, "雨/雪": 1}


def test_weather_distribution_skips_empty() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", weather=""),
        _row(date="2026-04-11", weather="晴"),
    ])
    assert LogReader(ws).weather_distribution() == {"晴": 1}


def test_weather_distribution_empty() -> None:
    assert LogReader(FakeWorksheet([])).weather_distribution() == {}


def test_weather_distribution_excludes_not_recorded() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-10", weather="晴"),
        _row(date="2026-04-16", weather="", entry_mode="not_recorded"),
    ])
    assert LogReader(ws).weather_distribution() == {"晴": 1}
