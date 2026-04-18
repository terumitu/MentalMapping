"""log_writer.py 単体テスト (v1.2 仕様 / 17 列スキーマ)。"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from modules.log_writer import LogWriter, MoodLogEntry


class FakeWorksheet:
    def __init__(self) -> None:
        self.rows: List[List[Any]] = []

    def append_row(self, row: List[Any]) -> None:
        self.rows.append(row)


def _valid_kwargs(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(
        date="2026-04-17",
        mood=3,
        energy=3,
        thinking=3,
        focus=3,
        time_of_day="morning",
        input_user="masuda",
        record_id="masuda_2026-04-17_morning_1744848000",
        entry_mode="realtime",
        sleep_hours=7.0,
        weather="晴",
        medication=False,
        period=False,
    )
    base.update(overrides)
    return base


# ---- MoodLogEntry.create : happy path --------------------------------------


def test_create_populates_recorded_at_when_omitted() -> None:
    entry = MoodLogEntry.create(**_valid_kwargs())
    assert entry.recorded_at  # 非空
    assert entry.date == "2026-04-17"
    assert entry.mood == 3
    assert entry.input_user == "masuda"
    assert entry.record_id == "masuda_2026-04-17_morning_1744848000"
    assert entry.entry_mode == "realtime"
    assert entry.record_status == "active"
    assert entry.superseded_by is None
    assert entry.daily_aspects == ""


def test_create_uses_explicit_recorded_at() -> None:
    entry = MoodLogEntry.create(
        **_valid_kwargs(recorded_at="2026-04-17T07:45:00")
    )
    assert entry.recorded_at == "2026-04-17T07:45:00"


def test_create_allows_none_for_optional_fields() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-17", mood=1, energy=2, thinking=3, focus=4,
        time_of_day="evening", input_user="nishide",
        record_id="nishide_2026-04-17_evening_1", entry_mode="retroactive",
        sleep_hours=None, weather=None, medication=None, period=None,
    )
    assert entry.sleep_hours is None
    assert entry.weather is None
    assert entry.medication is None
    assert entry.period is None
    assert entry.time_of_day == "evening"


def test_create_accepts_superseded_with_null_superseded_by() -> None:
    """採用されなかった訂正試行 (§4.4 末端解釈)。"""
    entry = MoodLogEntry.create(
        **_valid_kwargs(record_status="superseded", superseded_by=None)
    )
    assert entry.record_status == "superseded"
    assert entry.superseded_by is None


def test_create_accepts_superseded_with_chain_link() -> None:
    entry = MoodLogEntry.create(
        **_valid_kwargs(
            record_status="superseded",
            superseded_by="masuda_2026-04-17_morning_1744900000",
        )
    )
    assert entry.superseded_by == "masuda_2026-04-17_morning_1744900000"


# ---- score validation ------------------------------------------------------


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
    with pytest.raises(ValueError, match=field):
        MoodLogEntry.create(**_valid_kwargs(**{field: True}))


# ---- optional field validation ---------------------------------------------


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


def test_create_accepts_new_weather_enum_literal() -> None:
    """v1.2 で weather 内部値を '雨' → '雨/雪' に変更 (§4.1.1)。"""
    entry = MoodLogEntry.create(**_valid_kwargs(weather="雨/雪"))
    assert entry.weather == "雨/雪"


def test_create_rejects_empty_date() -> None:
    with pytest.raises(ValueError, match="date"):
        MoodLogEntry.create(**_valid_kwargs(date=""))


def test_create_rejects_empty_record_id() -> None:
    with pytest.raises(ValueError, match="record_id"):
        MoodLogEntry.create(**_valid_kwargs(record_id=""))


# ---- enum validation -------------------------------------------------------


def test_create_rejects_invalid_time_of_day() -> None:
    with pytest.raises(ValueError, match="time_of_day"):
        MoodLogEntry.create(**_valid_kwargs(time_of_day="night"))


def test_create_rejects_invalid_record_status() -> None:
    with pytest.raises(ValueError, match="record_status"):
        MoodLogEntry.create(**_valid_kwargs(record_status="archived"))


def test_create_rejects_invalid_entry_mode() -> None:
    with pytest.raises(ValueError, match="entry_mode"):
        MoodLogEntry.create(**_valid_kwargs(entry_mode="delayed"))


def test_create_rejects_invalid_input_user() -> None:
    with pytest.raises(ValueError, match="input_user"):
        MoodLogEntry.create(**_valid_kwargs(input_user="guest"))


# ---- not_recorded semantics ------------------------------------------------


def test_create_allows_null_scores_when_not_recorded() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-16", mood=None, energy=None, thinking=None, focus=None,
        time_of_day="morning", input_user="masuda",
        record_id="masuda_2026-04-16_morning_1", entry_mode="not_recorded",
        sleep_hours=None, weather=None, medication=None, period=None,
    )
    assert entry.mood is None
    assert entry.entry_mode == "not_recorded"


def test_create_rejects_non_null_score_when_not_recorded() -> None:
    with pytest.raises(ValueError, match="mood"):
        MoodLogEntry.create(
            date="2026-04-16", mood=3, energy=None, thinking=None, focus=None,
            time_of_day="morning", input_user="masuda",
            record_id="masuda_2026-04-16_morning_1", entry_mode="not_recorded",
        )


def test_create_accepts_pending_entry_mode_with_full_scores() -> None:
    """v1.2.1 §4.3.4: pending は値を持つため通常スコアが必須。"""
    entry = MoodLogEntry.create(**_valid_kwargs(entry_mode="pending"))
    assert entry.entry_mode == "pending"
    assert entry.mood == 3


def test_create_rejects_pending_with_null_score() -> None:
    """pending は realtime/retroactive と同様スコア 1-5 必須 (null 不許可)。"""
    with pytest.raises(ValueError, match="mood"):
        MoodLogEntry.create(
            date="2026-04-17", mood=None, energy=3, thinking=3, focus=3,
            time_of_day="evening", input_user="masuda",
            record_id="masuda_2026-04-17_evening_1", entry_mode="pending",
        )


# ---- to_row : 17 列 --------------------------------------------------------


def test_to_row_full_17_columns() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-17", mood=5, energy=4, thinking=4, focus=3,
        time_of_day="morning", input_user="masuda",
        record_id="masuda_2026-04-17_morning_1744848000",
        entry_mode="realtime",
        sleep_hours=7.5, weather="晴", medication=True, period=False,
        recorded_at="2026-04-17T07:45:00",
        daily_aspects="", record_status="active", superseded_by=None,
    )
    assert entry.to_row() == [
        "2026-04-17",                                   # A: date
        5, 4, 4, 3,                                     # B-E: mood/energy/thinking/focus
        7.5, "晴", "TRUE", "FALSE",                     # F-I
        "2026-04-17T07:45:00",                          # J: recorded_at
        "morning",                                      # K: time_of_day
        "",                                             # L: daily_aspects
        "masuda_2026-04-17_morning_1744848000",         # M: record_id
        "active",                                       # N: record_status
        "",                                             # O: superseded_by
        "realtime",                                     # P: entry_mode
        "masuda",                                       # Q: input_user
    ]


def test_to_row_not_recorded_row_has_empty_score_cells() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-16", mood=None, energy=None, thinking=None, focus=None,
        time_of_day="morning", input_user="masuda",
        record_id="masuda_2026-04-16_morning_1", entry_mode="not_recorded",
        recorded_at="2026-04-17T00:30:00",
    )
    row = entry.to_row()
    assert row[0] == "2026-04-16"
    assert row[1] == "" and row[2] == "" and row[3] == "" and row[4] == ""
    assert row[15] == "not_recorded"
    assert row[16] == "masuda"


def test_to_row_superseded_with_chain_link() -> None:
    entry = MoodLogEntry.create(
        **_valid_kwargs(
            record_status="superseded",
            superseded_by="masuda_2026-04-16_evening_1744876500",
            recorded_at="2026-04-16T20:34:00",
        )
    )
    row = entry.to_row()
    assert row[13] == "superseded"
    assert row[14] == "masuda_2026-04-16_evening_1744876500"


# ---- LogWriter -------------------------------------------------------------


def test_writer_append_delegates_to_worksheet() -> None:
    ws = FakeWorksheet()
    writer = LogWriter(ws)
    entry = MoodLogEntry.create(
        **_valid_kwargs(recorded_at="2026-04-17T07:45:00")
    )
    writer.append(entry)
    assert len(ws.rows) == 1
    assert ws.rows[0][0] == "2026-04-17"
    assert ws.rows[0][16] == "masuda"  # Q: input_user


def test_writer_append_multiple_rows() -> None:
    ws = FakeWorksheet()
    writer = LogWriter(ws)
    for i, date in enumerate(("2026-04-10", "2026-04-11")):
        writer.append(
            MoodLogEntry.create(
                **_valid_kwargs(
                    date=date, mood=3 + i,
                    record_id=f"masuda_{date}_morning_{i}",
                    recorded_at=f"{date}T09:00:00",
                )
            )
        )
    assert len(ws.rows) == 2
    assert ws.rows[0][0] == "2026-04-10"
    assert ws.rows[1][0] == "2026-04-11"
