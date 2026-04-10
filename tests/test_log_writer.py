"""log_writer.py 単体テスト。"""
from __future__ import annotations

from typing import Any, List

import pytest

from modules.log_writer import LogWriter, MoodLogEntry


class FakeWorksheet:
    def __init__(self) -> None:
        self.rows: List[List[Any]] = []

    def append_row(self, row: List[Any]) -> None:
        self.rows.append(row)


# ---- MoodLogEntry.create ----------------------------------------------------


def test_create_populates_recorded_at_when_omitted() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-10",
        mood_score=7,
        sleep_hours=6.5,
        went_outside=True,
        memo="ok",
    )
    assert entry.recorded_at  # 非空
    assert entry.date == "2026-04-10"
    assert entry.mood_score == 7
    assert entry.sleep_hours == 6.5
    assert entry.went_outside is True
    assert entry.memo == "ok"


def test_create_uses_explicit_recorded_at() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-10",
        mood_score=5,
        sleep_hours=7.0,
        went_outside=False,
        recorded_at="2026-04-10T10:30:00",
    )
    assert entry.recorded_at == "2026-04-10T10:30:00"


@pytest.mark.parametrize("bad_score", [11, -1, 100])
def test_create_rejects_out_of_range_mood_score(bad_score: int) -> None:
    with pytest.raises(ValueError, match="mood_score"):
        MoodLogEntry.create(
            date="2026-04-10",
            mood_score=bad_score,
            sleep_hours=7.0,
            went_outside=False,
        )


@pytest.mark.parametrize("bad_hours", [-0.5, 25.0])
def test_create_rejects_out_of_range_sleep_hours(bad_hours: float) -> None:
    with pytest.raises(ValueError, match="sleep_hours"):
        MoodLogEntry.create(
            date="2026-04-10",
            mood_score=5,
            sleep_hours=bad_hours,
            went_outside=False,
        )


def test_create_rejects_empty_date() -> None:
    with pytest.raises(ValueError, match="date"):
        MoodLogEntry.create(
            date="",
            mood_score=5,
            sleep_hours=7.0,
            went_outside=False,
        )


# ---- to_row -----------------------------------------------------------------


def test_to_row_formats_bool_as_text() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-10",
        mood_score=8,
        sleep_hours=7.5,
        went_outside=True,
        memo="good",
        recorded_at="2026-04-10T10:00:00",
    )
    assert entry.to_row() == [
        "2026-04-10",
        8,
        7.5,
        "TRUE",
        "good",
        "2026-04-10T10:00:00",
    ]


def test_to_row_false_bool() -> None:
    entry = MoodLogEntry.create(
        date="2026-04-10",
        mood_score=3,
        sleep_hours=5.0,
        went_outside=False,
        memo="",
        recorded_at="2026-04-10T22:00:00",
    )
    row = entry.to_row()
    assert row[3] == "FALSE"
    assert row[4] == ""


# ---- LogWriter --------------------------------------------------------------


def test_writer_append_delegates_to_worksheet() -> None:
    ws = FakeWorksheet()
    writer = LogWriter(ws)
    entry = MoodLogEntry.create(
        date="2026-04-10",
        mood_score=8,
        sleep_hours=7.5,
        went_outside=True,
        memo="good",
        recorded_at="2026-04-10T10:00:00",
    )
    writer.append(entry)
    assert ws.rows == [
        ["2026-04-10", 8, 7.5, "TRUE", "good", "2026-04-10T10:00:00"],
    ]


def test_writer_append_raw_builds_and_appends() -> None:
    ws = FakeWorksheet()
    writer = LogWriter(ws)
    entry = writer.append_raw(
        date="2026-04-10",
        mood_score=6,
        sleep_hours=7.0,
        went_outside=False,
        memo="hello",
        recorded_at="2026-04-10T08:00:00",
    )
    assert isinstance(entry, MoodLogEntry)
    assert ws.rows == [
        ["2026-04-10", 6, 7.0, "FALSE", "hello", "2026-04-10T08:00:00"],
    ]


def test_writer_append_multiple_rows() -> None:
    ws = FakeWorksheet()
    writer = LogWriter(ws)
    writer.append_raw(
        date="2026-04-09",
        mood_score=5,
        sleep_hours=6.0,
        went_outside=True,
        recorded_at="2026-04-09T20:00:00",
    )
    writer.append_raw(
        date="2026-04-10",
        mood_score=7,
        sleep_hours=7.5,
        went_outside=False,
        recorded_at="2026-04-10T09:00:00",
    )
    assert len(ws.rows) == 2
    assert ws.rows[0][0] == "2026-04-09"
    assert ws.rows[1][0] == "2026-04-10"
