"""entry_mode 判定 (§4.3 / §4.3.4 realtime_window 窓判定 + pending 分岐)。

time_of_day (morning/evening) と recorded_at 時刻が、
settings.yaml の users[input_user].{morning,evening}_realtime_window の
[start, end) 半開区間に入るかで realtime / retroactive を判定する。

evening_realtime_window の end が "26:00" 等 24:00 を超える場合、
[start, 24:00) ∪ [00:00, end-24:00) の 2 レンジとして扱う。

v1.2.1 追加 (§4.3.4): users[input_user] に該当 realtime_window キーが
未定義 (None / 空) の場合、realtime/retroactive の判定を保留し
entry_mode='pending' を返す。
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List, Tuple

TOD_VALUES = ("morning", "evening")


def parse_time_boundary(value: Any, field: str) -> Tuple[int, int]:
    """'HH:MM' を (hour, minute) に。hour は 0-26 を許容（26:00 は翌 02:00）。

    >24:00 の wrap は呼び出し側 (is_in_window) で処理する。
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be 'HH:MM' str, got {value!r}")
    try:
        hh_str, mm_str = value.split(":")
        hh, mm = int(hh_str), int(mm_str)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be 'HH:MM', got {value!r}") from exc
    if not (0 <= mm < 60):
        raise ValueError(f"{field} minute out of range: {value!r}")
    if not (0 <= hh <= 26):
        raise ValueError(f"{field} hour out of range [0, 26]: {value!r}")
    return hh, mm


def _to_minutes(hhmm: Tuple[int, int]) -> int:
    return hhmm[0] * 60 + hhmm[1]


def is_in_window(now_time: time, window: List[str]) -> bool:
    """window = [start, end] の [start, end) 半開区間内か判定。

    end が 24:00 を超える場合 (e.g. "26:00") は
    [start, 24:00) ∪ [00:00, end-24:00) の 2 レンジ和集合として扱う。
    """
    if not isinstance(window, (list, tuple)) or len(window) != 2:
        raise ValueError(f"window must be [start, end], got {window!r}")
    start = parse_time_boundary(window[0], "window.start")
    end = parse_time_boundary(window[1], "window.end")
    now_min = now_time.hour * 60 + now_time.minute
    start_min = _to_minutes(start)
    end_min = _to_minutes(end)
    if end_min <= start_min:
        raise ValueError(
            f"window.end must be after start: {window!r}"
        )
    day_minutes = 24 * 60
    if end_min <= day_minutes:
        return start_min <= now_min < end_min
    wrapped_end = end_min - day_minutes
    return now_min >= start_min or now_min < wrapped_end


def determine_entry_mode(
    input_user: str,
    time_of_day: str,
    recorded_at: datetime,
    users_config: Dict[str, Any],
) -> str:
    """realtime_window 判定で 'realtime' / 'retroactive' / 'pending' を返す。

    - 該当 realtime_window キーが未定義: 'pending' (§4.3.4 判定保留)
    - 窓内: 'realtime' (§4.3.1)
    - 窓外: 'retroactive' (§4.3.1)

    wake_time は使用しない。同日 2 件目の自動 retroactive 化も行わない
    (§4.3.3 責務分離)。user が users_config 自体に存在しない場合は
    (設定誤り / 不整合) ValueError を送出する。
    """
    if time_of_day not in TOD_VALUES:
        raise ValueError(
            f"time_of_day must be one of {TOD_VALUES}, got {time_of_day!r}"
        )
    if not users_config or input_user not in users_config:
        raise ValueError(f"unknown input_user: {input_user!r}")
    window_key = f"{time_of_day}_realtime_window"
    window = (users_config[input_user] or {}).get(window_key)
    if not window:
        # 該当窓キーが未定義 = 判定保留 (§4.3.4)
        return "pending"
    now_t = recorded_at.time().replace(microsecond=0)
    return "realtime" if is_in_window(now_t, list(window)) else "retroactive"
