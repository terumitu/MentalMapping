"""entry_mode.py 単体テスト (§4.3 realtime_window 窓判定 / 26:00 wrap 対応)。"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict

import pytest

from modules.entry_mode import (
    determine_entry_mode,
    is_in_window,
    parse_time_boundary,
)


_USERS_CONFIG: Dict[str, Any] = {
    "masuda": {
        "morning_realtime_window": ["06:00", "16:00"],
        "evening_realtime_window": ["17:00", "26:00"],
    },
    "nishide": {
        "morning_realtime_window": ["10:00", "14:00"],
        "evening_realtime_window": ["17:00", "26:00"],
    },
}


def _dt(year: int, month: int, day: int, hh: int, mm: int) -> datetime:
    return datetime(year, month, day, hh, mm, 0)


# ---- parse_time_boundary ---------------------------------------------------


def test_parse_time_boundary_basic() -> None:
    assert parse_time_boundary("06:00", "x") == (6, 0)
    assert parse_time_boundary("15:59", "x") == (15, 59)


def test_parse_time_boundary_accepts_26_hour() -> None:
    assert parse_time_boundary("26:00", "x") == (26, 0)


@pytest.mark.parametrize("bad", ["", "6", "abc", "06-00", None, 6])
def test_parse_time_boundary_rejects_invalid(bad: Any) -> None:
    with pytest.raises(ValueError):
        parse_time_boundary(bad, "x")


def test_parse_time_boundary_rejects_hour_over_26() -> None:
    with pytest.raises(ValueError, match="hour"):
        parse_time_boundary("27:00", "x")


def test_parse_time_boundary_rejects_minute_out_of_range() -> None:
    with pytest.raises(ValueError, match="minute"):
        parse_time_boundary("10:60", "x")


# ---- is_in_window ----------------------------------------------------------


def test_is_in_window_non_wrap_start_inclusive() -> None:
    assert is_in_window(time(6, 0), ["06:00", "16:00"]) is True


def test_is_in_window_non_wrap_end_exclusive() -> None:
    assert is_in_window(time(16, 0), ["06:00", "16:00"]) is False
    assert is_in_window(time(15, 59), ["06:00", "16:00"]) is True


def test_is_in_window_non_wrap_before_start() -> None:
    assert is_in_window(time(5, 59), ["06:00", "16:00"]) is False


def test_is_in_window_wrap_evening_at_17() -> None:
    # evening window [17:00, 26:00) = [17:00, 24:00) ∪ [00:00, 02:00)
    assert is_in_window(time(17, 0), ["17:00", "26:00"]) is True


def test_is_in_window_wrap_evening_at_23_59() -> None:
    assert is_in_window(time(23, 59), ["17:00", "26:00"]) is True


def test_is_in_window_wrap_evening_at_midnight() -> None:
    assert is_in_window(time(0, 0), ["17:00", "26:00"]) is True


def test_is_in_window_wrap_evening_at_01_59() -> None:
    assert is_in_window(time(1, 59), ["17:00", "26:00"]) is True


def test_is_in_window_wrap_evening_at_02_00_exclusive() -> None:
    # 02:00 ちょうどは retroactive (end exclusive)
    assert is_in_window(time(2, 0), ["17:00", "26:00"]) is False


def test_is_in_window_wrap_evening_at_16_59_outside() -> None:
    assert is_in_window(time(16, 59), ["17:00", "26:00"]) is False


def test_is_in_window_rejects_bad_window_shape() -> None:
    with pytest.raises(ValueError):
        is_in_window(time(10, 0), ["06:00"])


# ---- determine_entry_mode --------------------------------------------------


def test_determine_entry_mode_morning_realtime() -> None:
    # 2026-04-17 07:45 masuda morning → realtime (06:00-16:00 窓内)
    assert determine_entry_mode(
        "masuda", "morning", _dt(2026, 4, 17, 7, 45), _USERS_CONFIG
    ) == "realtime"


def test_determine_entry_mode_morning_retroactive() -> None:
    # 2026-04-17 17:00 masuda morning → retroactive (16:00 超)
    assert determine_entry_mode(
        "masuda", "morning", _dt(2026, 4, 17, 17, 0), _USERS_CONFIG
    ) == "retroactive"


def test_determine_entry_mode_evening_realtime() -> None:
    # 2026-04-16 20:45 masuda evening → realtime
    assert determine_entry_mode(
        "masuda", "evening", _dt(2026, 4, 16, 20, 45), _USERS_CONFIG
    ) == "realtime"


def test_determine_entry_mode_evening_retroactive_before_17() -> None:
    # 2026-04-16 16:59 masuda evening → retroactive (17:00 前)
    assert determine_entry_mode(
        "masuda", "evening", _dt(2026, 4, 16, 16, 59), _USERS_CONFIG
    ) == "retroactive"


def test_determine_entry_mode_evening_boundary_26_00_is_retroactive() -> None:
    # evening_realtime_window 上限 26:00 = 翌 02:00 JST。02:00 ちょうどは retroactive。
    assert determine_entry_mode(
        "masuda", "evening", _dt(2026, 4, 17, 2, 0), _USERS_CONFIG
    ) == "retroactive"


def test_determine_entry_mode_evening_boundary_01_59_is_realtime() -> None:
    assert determine_entry_mode(
        "masuda", "evening", _dt(2026, 4, 17, 1, 59), _USERS_CONFIG
    ) == "realtime"


def test_determine_entry_mode_respects_user_specific_window() -> None:
    # nishide morning window [10:00, 14:00)。masuda と違い 06:00 は retroactive。
    assert determine_entry_mode(
        "nishide", "morning", _dt(2026, 4, 17, 6, 0), _USERS_CONFIG
    ) == "retroactive"
    assert determine_entry_mode(
        "nishide", "morning", _dt(2026, 4, 17, 10, 0), _USERS_CONFIG
    ) == "realtime"


def test_determine_entry_mode_rejects_unknown_user() -> None:
    with pytest.raises(ValueError, match="unknown input_user"):
        determine_entry_mode(
            "ghost", "morning", _dt(2026, 4, 17, 10, 0), _USERS_CONFIG
        )


def test_determine_entry_mode_returns_pending_when_window_missing() -> None:
    """v1.2.1 §4.3.4: 該当 realtime_window キー未定義 → 'pending'。"""
    cfg = {"masuda": {"morning_realtime_window": ["06:00", "16:00"]}}
    # evening_realtime_window が未定義 → pending
    assert determine_entry_mode(
        "masuda", "evening", _dt(2026, 4, 17, 20, 0), cfg
    ) == "pending"


def test_determine_entry_mode_returns_pending_when_window_empty() -> None:
    cfg = {"masuda": {
        "morning_realtime_window": ["06:00", "16:00"],
        "evening_realtime_window": [],  # 明示的な空 = 未定義扱い
    }}
    assert determine_entry_mode(
        "masuda", "evening", _dt(2026, 4, 17, 20, 0), cfg
    ) == "pending"


def test_determine_entry_mode_pending_does_not_mask_valid_window() -> None:
    """同ユーザーで morning は定義済み / evening は未定義のケース混在確認。"""
    cfg = {"masuda": {"morning_realtime_window": ["06:00", "16:00"]}}
    # morning は通常判定
    assert determine_entry_mode(
        "masuda", "morning", _dt(2026, 4, 17, 7, 45), cfg
    ) == "realtime"
    # evening のみ pending
    assert determine_entry_mode(
        "masuda", "evening", _dt(2026, 4, 17, 20, 0), cfg
    ) == "pending"


def test_determine_entry_mode_rejects_invalid_time_of_day() -> None:
    with pytest.raises(ValueError, match="time_of_day"):
        determine_entry_mode(
            "masuda", "night", _dt(2026, 4, 17, 10, 0), _USERS_CONFIG
        )
