"""mood-log シートへの書き込みレイヤ (Google Sheets 実スキーマ A〜Q / 17 列)。

カラム順 (v1.2):
    A:date B:mood C:energy D:thinking E:focus F:sleep_hours
    G:weather H:medication I:period J:recorded_at K:time_of_day
    L:daily_aspects M:record_id N:record_status O:superseded_by
    P:entry_mode Q:input_user

本モジュールは Worksheet Protocol のみ要求し、呼び出し側が
Worksheet を注入する。単体テストでは FakeWorksheet を差し替える。

entry_mode 判定は ``modules.entry_mode`` 側、鎖構造操作は
``modules.record_chain`` 側の責務。本モジュールは MoodLogEntry の
バリデーションと LogWriter.append のみを持つ。

v1.1 で提供していた ``determine_time_of_day`` (時刻ベース自動判定) は
v1.2 のラジオボタン主観申告仕様化に伴い削除 (§4.2)。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Protocol
from zoneinfo import ZoneInfo

SCORE_FIELDS = ("mood", "energy", "thinking", "focus")
WEATHER_VALUES = ("晴", "曇", "雨/雪")
TIME_OF_DAY_VALUES = ("morning", "evening")
RECORD_STATUS_VALUES = ("active", "superseded")
ENTRY_MODE_VALUES = ("realtime", "retroactive", "not_recorded", "pending")
INPUT_USER_VALUES = ("masuda", "nishide", "suyasu")


class Worksheet(Protocol):
    """gspread.Worksheet が満たすべき最小インタフェース (append 用)。"""

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


def _score_cell(value: Optional[int]) -> Any:
    return "" if value is None else value


def _validate_score(name: str, value: Any) -> None:
    # bool は int サブクラスなので明示的に弾く
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 5):
        raise ValueError(f"{name} must be int in [1, 5], got {value!r}")


def _validate_optional_sleep(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"sleep_hours must be float or None, got {value!r}")
    if value < 0 or value > 24:
        raise ValueError(f"sleep_hours must be in [0, 24], got {value!r}")


def _validate_enums(
    time_of_day: str,
    record_status: str,
    entry_mode: str,
    input_user: str,
) -> None:
    if time_of_day not in TIME_OF_DAY_VALUES:
        raise ValueError(
            f"time_of_day must be one of {TIME_OF_DAY_VALUES}, got {time_of_day!r}"
        )
    if record_status not in RECORD_STATUS_VALUES:
        raise ValueError(
            f"record_status must be one of {RECORD_STATUS_VALUES}, got {record_status!r}"
        )
    if entry_mode not in ENTRY_MODE_VALUES:
        raise ValueError(
            f"entry_mode must be one of {ENTRY_MODE_VALUES}, got {entry_mode!r}"
        )
    if input_user not in INPUT_USER_VALUES:
        raise ValueError(
            f"input_user must be one of {INPUT_USER_VALUES}, got {input_user!r}"
        )


@dataclass(frozen=True)
class MoodLogEntry:
    """mood_log の 1 レコード (Google Sheets 実スキーマ A〜Q / 17 列準拠)。

    必須スコア (1-5): mood / energy / thinking / focus
        ただし entry_mode='not_recorded' のときは全て None が必須。
    必須分類: time_of_day / record_status / entry_mode / input_user / record_id
    任意項目: sleep_hours / weather / medication / period / superseded_by
    自動付与: recorded_at (未指定なら JST 現在時刻) / daily_aspects (既定 "")
    """

    date: str
    mood: Optional[int]
    energy: Optional[int]
    thinking: Optional[int]
    focus: Optional[int]
    sleep_hours: Optional[float]
    weather: Optional[str]
    medication: Optional[bool]
    period: Optional[bool]
    recorded_at: str
    time_of_day: str
    daily_aspects: str
    record_id: str
    record_status: str
    superseded_by: Optional[str]
    entry_mode: str
    input_user: str

    @classmethod
    def create(
        cls,
        date: str,
        mood: Optional[int],
        energy: Optional[int],
        thinking: Optional[int],
        focus: Optional[int],
        time_of_day: str,
        input_user: str,
        record_id: str,
        entry_mode: str,
        sleep_hours: Optional[float] = None,
        weather: Optional[str] = None,
        medication: Optional[bool] = None,
        period: Optional[bool] = None,
        recorded_at: Optional[str] = None,
        daily_aspects: str = "",
        record_status: str = "active",
        superseded_by: Optional[str] = None,
    ) -> "MoodLogEntry":
        if not date:
            raise ValueError("date must not be empty")
        if not record_id:
            raise ValueError("record_id must not be empty")
        _validate_enums(time_of_day, record_status, entry_mode, input_user)
        # not_recorded はスコアを null 必須とする (§4.3.2)
        if entry_mode == "not_recorded":
            for name, v in (
                ("mood", mood), ("energy", energy),
                ("thinking", thinking), ("focus", focus),
            ):
                if v is not None:
                    raise ValueError(
                        f"{name} must be None when entry_mode='not_recorded', got {v!r}"
                    )
        else:
            _validate_score("mood", mood)
            _validate_score("energy", energy)
            _validate_score("thinking", thinking)
            _validate_score("focus", focus)
        _validate_optional_sleep(sleep_hours)
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
            daily_aspects=daily_aspects,
            record_id=record_id,
            record_status=record_status,
            superseded_by=superseded_by,
            entry_mode=entry_mode,
            input_user=input_user,
        )

    def to_row(self) -> List[Any]:
        """Sheets に append する行表現。列順 A〜Q (17 列)。"""
        return [
            self.date,                       # A
            _score_cell(self.mood),          # B
            _score_cell(self.energy),        # C
            _score_cell(self.thinking),      # D
            _score_cell(self.focus),         # E
            _float_cell(self.sleep_hours),   # F
            _str_cell(self.weather),         # G
            _bool_cell(self.medication),     # H
            _bool_cell(self.period),         # I
            self.recorded_at,                # J
            self.time_of_day,                # K
            _str_cell(self.daily_aspects),   # L
            self.record_id,                  # M
            self.record_status,              # N
            _str_cell(self.superseded_by),   # O
            self.entry_mode,                 # P
            self.input_user,                 # Q
        ]


class LogWriter:
    """注入された Worksheet に 1 レコードを append する。"""

    def __init__(self, worksheet: Worksheet) -> None:
        self._worksheet = worksheet

    def append(self, entry: MoodLogEntry) -> None:
        self._worksheet.append_row(entry.to_row())
