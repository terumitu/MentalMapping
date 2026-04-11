"""log_writer.py 単体テスト (v2 仕様 / 5段階 8項目 + time_of_day)。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pytest

from modules.log_writer import LogWriter, MoodLogEntry, determine_time_of_day


class FakeWorksheet:
    def __init__(self) -> None:
        self.rows: List[List[Any]] = []

    def append_row(self, row: List[Any]) -> None:
        self.rows.append(row)


def _valid_kwargs(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(
        date="2026-04-11",
        mood=3,
        energy=3,
        thinking=3,
        focus=3,
        time_of_day="morning",
        sleep_hours=7.0,
        weather="晴",
        medication=False,
        period=False,
    )
    base.update(overrides)
    return base


_TIME_SETTINGS: Dict[str, Any] = {
    "time_of_day": {"morning_start": "05:30", "evening_start": "15:31"},
}


# ---- MoodLogEntry.create : happy path --------------------------------------


def test_create_populates_recorded_at_when_omitted() -> None:
    entry = MoodLogEntry.create(**_valid_kwargs())
    assert entry.recorded_at  # 非空
    assert entry.date == "2026-04-11"
    assert entry.mood == 3
    assert entry.energy == 3
    assert entry.thinking == 3
    assert entry.focus == 3
    assert entry.sleep_hours == 7.0
    assert entry.weather == "晴"
    assert entry.medication is False
    assert entry.period is False


def test_create_uses_explicit_recorded_at() -> None:
    entry = MoodLogEntry.create(
        **_valid_kwargs(recorded_at="2026-04-11T10:30:00")
    )
    assert entry.recorded_at == "2026-04-11T10:30:00"


def test_create_allows_none_for_optional_fields() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-11",
        mood=1,
        energy=2,
        thinking=3,
        focus=4,
        time_of_day="evening",
        sleep_hours=None,
        weather=None,
        medication=None,
        period=None,
    )
    assert entry.sleep_hours is None
    assert entry.weather is None
    assert entry.medication is None
    assert entry.period is None
    assert entry.time_of_day == "evening"


# ---- MoodLogEntry.create : score validation --------------------------------


@pytest.mark.parametrize("field", ["mood", "energy", "thinking", "focus"])
@pytest.mark.parametrize("bad", [0, 6, -1, 100])
def test_create_rejects_out_of_range_score(field: str, bad: int) -> None:
    with pytest.raises(ValueError, match=field):
        MoodLogEntry.create(**_valid_kwargs(**{field: bad}))


@pytest.mark.parametrize("field", ["mood", "energy", "thinking", "focus"])
def test_create_rejects_float_score(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        MoodLogEntry.create(**_valid_kwargs(**{field: 3.5}))


@pytest.mark.parametrize("field", ["mood", "energy", "thinking", "focus"])
def test_create_rejects_bool_score(field: str) -> None:
    # bool は int サブクラスだが、スコアとしては弾く
    with pytest.raises(ValueError, match=field):
        MoodLogEntry.create(**_valid_kwargs(**{field: True}))


# ---- MoodLogEntry.create : optional field validation -----------------------


@pytest.mark.parametrize("bad_hours", [-0.5, 25.0])
def test_create_rejects_out_of_range_sleep_hours(bad_hours: float) -> None:
    with pytest.raises(ValueError, match="sleep_hours"):
        MoodLogEntry.create(**_valid_kwargs(sleep_hours=bad_hours))


def test_create_accepts_zero_sleep_hours() -> None:
    entry = MoodLogEntry.create(**_valid_kwargs(sleep_hours=0.0))
    assert entry.sleep_hours == 0.0


def test_create_rejects_invalid_weather() -> None:
    with pytest.raises(ValueError, match="weather"):
        MoodLogEntry.create(**_valid_kwargs(weather="雪"))


def test_create_rejects_empty_date() -> None:
    with pytest.raises(ValueError, match="date"):
        MoodLogEntry.create(**_valid_kwargs(date=""))


# ---- to_row ----------------------------------------------------------------


def test_to_row_full_fields() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-11",
        mood=5,
        energy=4,
        thinking=4,
        focus=3,
        time_of_day="morning",
        sleep_hours=7.5,
        weather="晴",
        medication=True,
        period=False,
        recorded_at="2026-04-11T10:00:00",
    )
    # A〜K 順: date mood energy thinking focus sleep_hours
    #          weather medication period recorded_at time_of_day
    assert entry.to_row() == [
        "2026-04-11",           # A: date
        5,                      # B: mood
        4,                      # C: energy
        4,                      # D: thinking
        3,                      # E: focus
        7.5,                    # F: sleep_hours
        "晴",                   # G: weather
        "TRUE",                 # H: medication
        "FALSE",                # I: period
        "2026-04-11T10:00:00",  # J: recorded_at
        "morning",              # K: time_of_day
    ]


def test_to_row_none_optionals_become_empty_string() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-11",
        mood=3,
        energy=3,
        thinking=3,
        focus=3,
        time_of_day="evening",
        sleep_hours=None,
        weather=None,
        medication=None,
        period=None,
        recorded_at="2026-04-11T10:00:00",
    )
    row = entry.to_row()
    assert row[0] == "2026-04-11"            # A: date
    assert row[5] == ""                      # F: sleep_hours
    assert row[6] == ""                      # G: weather
    assert row[7] == ""                      # H: medication
    assert row[8] == ""                      # I: period
    assert row[9] == "2026-04-11T10:00:00"   # J: recorded_at
    assert row[10] == "evening"              # K: time_of_day


def test_to_row_medication_period_both_true() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-11",
        mood=2,
        energy=2,
        thinking=3,
        focus=2,
        time_of_day="evening",
        sleep_hours=5.0,
        weather="雨",
        medication=True,
        period=True,
        recorded_at="2026-04-11T22:00:00",
    )
    row = entry.to_row()
    assert row[6] == "雨"     # G: weather
    assert row[7] == "TRUE"   # H: medication
    assert row[8] == "TRUE"   # I: period
    assert row[10] == "evening"  # K: time_of_day


# ---- LogWriter -------------------------------------------------------------


def test_writer_append_delegates_to_worksheet() -> None:
    ws = FakeWorksheet()
    writer = LogWriter(ws)
    entry = MoodLogEntry.create(
        date="2026-04-11",
        mood=5,
        energy=4,
        thinking=4,
        focus=3,
        time_of_day="morning",
        sleep_hours=7.5,
        weather="晴",
        medication=True,
        period=False,
        recorded_at="2026-04-11T10:00:00",
    )
    writer.append(entry)
    assert ws.rows == [
        [
            "2026-04-11", 5, 4, 4, 3, 7.5, "晴", "TRUE", "FALSE",
            "2026-04-11T10:00:00", "morning",
        ],
    ]


def test_writer_append_multiple_rows() -> None:
    ws = FakeWorksheet()
    writer = LogWriter(ws)
    for i, date in enumerate(("2026-04-10", "2026-04-11")):
        writer.append(
            MoodLogEntry.create(
                date=date,
                mood=3 + i,
                energy=3,
                thinking=3,
                focus=3,
                time_of_day="morning",
                sleep_hours=7.0,
                weather="晴",
                medication=False,
                period=False,
                recorded_at=f"{date}T09:00:00",
            )
        )
    assert len(ws.rows) == 2
    assert ws.rows[0][0] == "2026-04-10"
    assert ws.rows[1][0] == "2026-04-11"
    assert ws.rows[0][1] == 3
    assert ws.rows[1][1] == 4


# ---- determine_time_of_day : 境界4ケース + 設定可変性 -----------------------


def _at(hh: int, mm: int) -> datetime:
    return datetime(2026, 4, 11, hh, mm, 0)


@pytest.mark.parametrize(
    "now, expected",
    [
        (_at(5, 29), "evening"),   # 境界直前
        (_at(5, 30), "morning"),   # morning_start 丁度
        (_at(15, 30), "morning"),  # evening_start 直前
        (_at(15, 31), "evening"),  # evening_start 丁度
    ],
)
def test_determine_time_of_day_boundaries(now: datetime, expected: str) -> None:
    assert determine_time_of_day(now, _TIME_SETTINGS) == expected


def test_determine_time_of_day_respects_settings_override() -> None:
    custom = {"time_of_day": {"morning_start": "08:00", "evening_start": "20:00"}}
    assert determine_time_of_day(_at(7, 59), custom) == "evening"
    assert determine_time_of_day(_at(8, 0), custom) == "morning"
    assert determine_time_of_day(_at(19, 59), custom) == "morning"
    assert determine_time_of_day(_at(20, 0), custom) == "evening"


def test_determine_time_of_day_rejects_missing_config() -> None:
    with pytest.raises(ValueError, match="morning_start"):
        determine_time_of_day(_at(10, 0), {})


# ---- time_of_day validation -------------------------------------------------


def test_create_rejects_invalid_time_of_day() -> None:
    with pytest.raises(ValueError, match="time_of_day"):
        MoodLogEntry.create(**_valid_kwargs(time_of_day="night"))
