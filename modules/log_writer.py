"""mood_log シートへの書き込みレイヤ。

Google Sheets への I/O は Worksheet Protocol 経由で受け取るため、
単体テストでは FakeWorksheet を差し込める。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Protocol


class Worksheet(Protocol):
    """gspread.Worksheet が満たすべき最小インタフェース。"""

    def append_row(self, row: List[Any]) -> Any: ...


@dataclass(frozen=True)
class MoodLogEntry:
    """mood_log の 1 レコード。

    Columns: date / mood_score / sleep_hours / went_outside / memo / recorded_at
    """

    date: str
    mood_score: int
    sleep_hours: float
    went_outside: bool
    memo: str
    recorded_at: str

    @classmethod
    def create(
        cls,
        date: str,
        mood_score: int,
        sleep_hours: float,
        went_outside: bool,
        memo: str = "",
        recorded_at: Optional[str] = None,
    ) -> "MoodLogEntry":
        if not date:
            raise ValueError("date must not be empty")
        if not isinstance(mood_score, int) or not (0 <= mood_score <= 10):
            raise ValueError(f"mood_score must be int in [0, 10], got {mood_score!r}")
        if sleep_hours < 0 or sleep_hours > 24:
            raise ValueError(f"sleep_hours must be in [0, 24], got {sleep_hours!r}")
        if recorded_at is None:
            recorded_at = datetime.now().isoformat(timespec="seconds")
        return cls(
            date=date,
            mood_score=mood_score,
            sleep_hours=float(sleep_hours),
            went_outside=bool(went_outside),
            memo=memo,
            recorded_at=recorded_at,
        )

    def to_row(self) -> List[Any]:
        """Sheets に append する行表現。bool は TRUE/FALSE 文字列化。"""
        return [
            self.date,
            self.mood_score,
            self.sleep_hours,
            "TRUE" if self.went_outside else "FALSE",
            self.memo,
            self.recorded_at,
        ]


class LogWriter:
    """mood_log Worksheet に 1 レコードを append する。"""

    def __init__(self, worksheet: Worksheet) -> None:
        self._worksheet = worksheet

    def append(self, entry: MoodLogEntry) -> None:
        self._worksheet.append_row(entry.to_row())

    def append_raw(
        self,
        date: str,
        mood_score: int,
        sleep_hours: float,
        went_outside: bool,
        memo: str = "",
        recorded_at: Optional[str] = None,
    ) -> MoodLogEntry:
        entry = MoodLogEntry.create(
            date=date,
            mood_score=mood_score,
            sleep_hours=sleep_hours,
            went_outside=went_outside,
            memo=memo,
            recorded_at=recorded_at,
        )
        self.append(entry)
        return entry
