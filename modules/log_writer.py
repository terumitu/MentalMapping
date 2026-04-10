"""mood_log シートへの書き込みレイヤ (v2 仕様 / 5段階 8項目)。

カラム順:
    date / mood / energy / thinking / focus /
    sleep_hours / weather / medication / period / recorded_at

Google Sheets への I/O は Worksheet Protocol 経由で受け取るため、
単体テストでは FakeWorksheet を差し込める。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Protocol

SCORE_FIELDS = ("mood", "energy", "thinking", "focus")
WEATHER_VALUES = ("晴", "曇", "雨")


class Worksheet(Protocol):
    """gspread.Worksheet が満たすべき最小インタフェース。"""

    def append_row(self, row: List[Any]) -> Any: ...


def _bool_cell(value: Optional[bool]) -> str:
    if value is None:
        return ""
    return "TRUE" if value else "FALSE"


def _float_cell(value: Optional[float]) -> Any:
    if value is None:
        return ""
    return float(value)


def _str_cell(value: Optional[str]) -> str:
    return "" if value is None else value


def _validate_score(name: str, value: Any) -> None:
    # bool は int サブクラスなので明示的に弾く
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 5):
        raise ValueError(f"{name} must be int in [1, 5], got {value!r}")


@dataclass(frozen=True)
class MoodLogEntry:
    """mood_log の 1 レコード (v2 仕様)。

    必須スコア (1-5): mood / energy / thinking / focus
    任意項目:
        sleep_hours: float | None (0-24)
        weather:     "晴" | "曇" | "雨" | None
        medication:  bool | None
        period:      bool | None
    """

    date: str
    mood: int
    energy: int
    thinking: int
    focus: int
    sleep_hours: Optional[float]
    weather: Optional[str]
    medication: Optional[bool]
    period: Optional[bool]
    recorded_at: str

    @classmethod
    def create(
        cls,
        date: str,
        mood: int,
        energy: int,
        thinking: int,
        focus: int,
        sleep_hours: Optional[float] = None,
        weather: Optional[str] = None,
        medication: Optional[bool] = None,
        period: Optional[bool] = None,
        recorded_at: Optional[str] = None,
    ) -> "MoodLogEntry":
        if not date:
            raise ValueError("date must not be empty")
        _validate_score("mood", mood)
        _validate_score("energy", energy)
        _validate_score("thinking", thinking)
        _validate_score("focus", focus)
        if sleep_hours is not None:
            if isinstance(sleep_hours, bool) or not isinstance(sleep_hours, (int, float)):
                raise ValueError(
                    f"sleep_hours must be float or None, got {sleep_hours!r}"
                )
            if sleep_hours < 0 or sleep_hours > 24:
                raise ValueError(
                    f"sleep_hours must be in [0, 24], got {sleep_hours!r}"
                )
        if weather is not None and weather not in WEATHER_VALUES:
            raise ValueError(
                f"weather must be one of {WEATHER_VALUES} or None, got {weather!r}"
            )
        if medication is not None and not isinstance(medication, bool):
            raise ValueError(f"medication must be bool or None, got {medication!r}")
        if period is not None and not isinstance(period, bool):
            raise ValueError(f"period must be bool or None, got {period!r}")
        if recorded_at is None:
            recorded_at = datetime.now().isoformat(timespec="seconds")
        return cls(
            date=date,
            mood=mood,
            energy=energy,
            thinking=thinking,
            focus=focus,
            sleep_hours=None if sleep_hours is None else float(sleep_hours),
            weather=weather,
            medication=medication,
            period=period,
            recorded_at=recorded_at,
        )

    def to_row(self) -> List[Any]:
        """Sheets に append する行表現。None/bool は Sheets 互換の文字列化。"""
        return [
            self.date,
            self.mood,
            self.energy,
            self.thinking,
            self.focus,
            _float_cell(self.sleep_hours),
            _str_cell(self.weather),
            _bool_cell(self.medication),
            _bool_cell(self.period),
            self.recorded_at,
        ]


class LogWriter:
    """mood_log Worksheet に 1 レコードを append する。"""

    def __init__(self, worksheet: Worksheet) -> None:
        self._worksheet = worksheet

    def append(self, entry: MoodLogEntry) -> None:
        self._worksheet.append_row(entry.to_row())
