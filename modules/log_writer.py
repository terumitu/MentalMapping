"""mood-log シートへの書き込みレイヤ (Google Sheets 実スキーマ A〜K 準拠)。

カラム順 (A〜K):
    A:date B:mood C:energy D:thinking E:focus F:sleep_hours
    G:weather H:medication I:period J:recorded_at K:time_of_day

本モジュールはシート名を保持せず、呼び出し側が解決した Worksheet を
Worksheet Protocol 経由で注入する。マルチユーザー運用では
ユーザーごとに別シートの Worksheet を差し替えて使う。
単体テストでは FakeWorksheet を差し込める。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Protocol
from zoneinfo import ZoneInfo

SCORE_FIELDS = ("mood", "energy", "thinking", "focus")
WEATHER_VALUES = ("晴", "曇", "雨")
TIME_OF_DAY_VALUES = ("morning", "evening")


def _parse_hhmm(value: Any, field: str) -> time:
    if not isinstance(value, str):
        raise ValueError(f"time_of_day.{field} must be 'HH:MM' string, got {value!r}")
    try:
        hh, mm = value.split(":")
        return time(hour=int(hh), minute=int(mm))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"time_of_day.{field} must be 'HH:MM' string, got {value!r}"
        ) from exc


def determine_time_of_day(now: datetime, settings: Dict[str, Any]) -> str:
    """settings['time_of_day'] の境界に従い 'morning' / 'evening' を返す。

    morning_start <= now.time() < evening_start のとき 'morning'、
    それ以外は 'evening' を返す。境界時刻を跨ぐ設定（深夜境界）には未対応。
    """
    cfg = (settings or {}).get("time_of_day") or {}
    morning_start = _parse_hhmm(cfg.get("morning_start"), "morning_start")
    evening_start = _parse_hhmm(cfg.get("evening_start"), "evening_start")
    current = now.time().replace(microsecond=0)
    if morning_start <= current < evening_start:
        return "morning"
    return "evening"


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
    """mood_log の 1 レコード (Google Sheets 実スキーマ A〜K 準拠)。

    必須スコア (1-5): mood / energy / thinking / focus
    必須分類:        time_of_day ("morning" | "evening")
    任意項目:
        sleep_hours: float | None (0-24)
        weather:     "晴" | "曇" | "雨" | None
        medication:  bool | None
        period:      bool | None

    フィールド宣言順は Sheets の列順 A〜K と一致させている
    （time_of_day は K 列のため末尾）。
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
    time_of_day: str

    @classmethod
    def create(
        cls,
        date: str,
        mood: int,
        energy: int,
        thinking: int,
        focus: int,
        time_of_day: str,
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
        if time_of_day not in TIME_OF_DAY_VALUES:
            raise ValueError(
                f"time_of_day must be one of {TIME_OF_DAY_VALUES}, got {time_of_day!r}"
            )
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
            recorded_at = datetime.now(tz=ZoneInfo("Asia/Tokyo")).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
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
            time_of_day=time_of_day,
        )

    def to_row(self) -> List[Any]:
        """Sheets に append する行表現。列順 A〜K。None/bool は Sheets 互換の文字列化。"""
        return [
            self.date,                      # A
            self.mood,                      # B
            self.energy,                    # C
            self.thinking,                  # D
            self.focus,                     # E
            _float_cell(self.sleep_hours),  # F
            _str_cell(self.weather),        # G
            _bool_cell(self.medication),    # H
            _bool_cell(self.period),        # I
            self.recorded_at,               # J
            self.time_of_day,               # K
        ]


class LogWriter:
    """注入された Worksheet に 1 レコードを append する。"""

    def __init__(self, worksheet: Worksheet) -> None:
        self._worksheet = worksheet

    def append(self, entry: MoodLogEntry) -> None:
        self._worksheet.append_row(entry.to_row())
