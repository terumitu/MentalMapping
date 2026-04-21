"""record_chain.py 単体テスト (§4.4 / §A.3 / §A.4)。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple

import pytest

from modules.record_chain import (
    COL_RECORD_STATUS,
    COL_SUPERSEDED_BY,
    find_active_record,
    generate_record_id,
    get_revision_chain,
    supersede_active,
)


JST = timezone(timedelta(hours=9))


class FakeWorksheet:
    """get_all_records / update_cell を追跡する最小実装。

    Hotfix で find_active_record が expected_headers= を渡すようになったため
    シグネチャ互換のために kwarg を受け取り、最後の指定値を保持する。
    既存呼び出し（get_revision_chain 等の無引数呼び出し）とも両立させる。
    """

    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self._records = [dict(r) for r in records]
        self.updates: List[Tuple[int, int, Any]] = []
        self.last_expected_headers: Any = None

    def get_all_records(self, expected_headers: Any = None) -> List[Dict[str, Any]]:
        self.last_expected_headers = expected_headers
        return [dict(r) for r in self._records]

    def update_cell(self, row: int, col: int, value: Any) -> None:
        self.updates.append((row, col, value))


def _row(
    *,
    date: str,
    time_of_day: str = "morning",
    record_status: str = "active",
    superseded_by: str = "",
    record_id: str = "",
    recorded_at: str = "",
    input_user: str = "masuda",
    mood: Any = 3,
) -> Dict[str, Any]:
    return {
        "date": date,
        "mood": mood,
        "energy": 3, "thinking": 3, "focus": 3,
        "sleep_hours": 7.0, "weather": "晴",
        "medication": "FALSE", "period": "FALSE",
        "recorded_at": recorded_at or f"{date}T09:00:00",
        "time_of_day": time_of_day, "daily_aspects": "",
        "record_id": record_id or f"{input_user}_{date}_{time_of_day}_1",
        "record_status": record_status,
        "superseded_by": superseded_by,
        "entry_mode": "realtime",
        "input_user": input_user,
    }


# ---- generate_record_id ----------------------------------------------------


def test_generate_record_id_format() -> None:
    # JST 2026-04-17 07:45:00 → UNIX 秒は tz-aware から計算
    dt = datetime(2026, 4, 17, 7, 45, 0, tzinfo=JST)
    rid = generate_record_id("masuda", "2026-04-17", "morning", dt)
    expected_ts = int(dt.timestamp())
    assert rid == f"masuda_2026-04-17_morning_{expected_ts}"


def test_generate_record_id_uses_unix_ts_as_int() -> None:
    dt = datetime(2026, 4, 14, 12, 12, 0, tzinfo=JST)
    rid = generate_record_id("masuda", "2026-04-14", "morning", dt)
    assert rid.startswith("masuda_2026-04-14_morning_")
    suffix = rid.rsplit("_", 1)[-1]
    assert suffix.isdigit()
    assert int(suffix) == int(dt.timestamp())


def test_generate_record_id_rejects_empty_input_user() -> None:
    dt = datetime(2026, 4, 17, 7, 45, 0, tzinfo=JST)
    with pytest.raises(ValueError, match="input_user"):
        generate_record_id("", "2026-04-17", "morning", dt)


def test_generate_record_id_rejects_invalid_time_of_day() -> None:
    dt = datetime(2026, 4, 17, 7, 45, 0, tzinfo=JST)
    with pytest.raises(ValueError, match="time_of_day"):
        generate_record_id("masuda", "2026-04-17", "night", dt)


def test_generate_record_id_rejects_non_datetime_recorded_at() -> None:
    with pytest.raises(ValueError, match="datetime"):
        generate_record_id("masuda", "2026-04-17", "morning", "2026-04-17T07:45:00")


# ---- find_active_record ----------------------------------------------------


def test_find_active_record_returns_none_when_absent() -> None:
    ws = FakeWorksheet([])
    assert find_active_record(ws, "masuda", "2026-04-17", "morning") is None


def test_find_active_record_returns_match_with_row_index() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-17", time_of_day="morning", record_status="active",
             record_id="masuda_2026-04-17_morning_1"),
    ])
    result = find_active_record(ws, "masuda", "2026-04-17", "morning")
    assert result is not None
    row_idx, rec = result
    # データ 1 件目はヘッダ次行 = row 2
    assert row_idx == 2
    assert rec["record_id"] == "masuda_2026-04-17_morning_1"


def test_find_active_record_skips_superseded() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-17", time_of_day="morning",
             record_status="superseded",
             superseded_by="masuda_2026-04-17_morning_new",
             record_id="masuda_2026-04-17_morning_old"),
    ])
    # active が存在しないケース
    assert find_active_record(ws, "masuda", "2026-04-17", "morning") is None


def test_find_active_record_passes_expected_headers_v12() -> None:
    """Hotfix 回帰テスト: find_active_record が get_all_records に
    expected_headers=list(HEADERS_V12) を明示して渡していることを保証する。

    本番 masuda worksheet の空ヘッダー (col_count=47) 暴露時に gspread 6.x が
    GSpreadException("duplicates: ['']") を raise した事故の再発防止用。
    expected_headers 指定で uniqueness チェックがバイパスされる。
    """
    from devtools.migrate_v1_2 import HEADERS_V12

    ws = FakeWorksheet([
        _row(date="2026-04-19", time_of_day="morning",
             record_id="masuda_2026-04-19_morning_1"),
    ])
    find_active_record(ws, "masuda", "2026-04-19", "morning")
    assert ws.last_expected_headers == list(HEADERS_V12)
    assert len(ws.last_expected_headers) == 17


def test_find_active_record_respects_scope() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-17", time_of_day="morning", input_user="masuda",
             record_id="masuda_row"),
        _row(date="2026-04-17", time_of_day="morning", input_user="nishide",
             record_id="nishide_row"),
        _row(date="2026-04-17", time_of_day="evening", input_user="masuda",
             record_id="masuda_evening_row"),
    ])
    result = find_active_record(ws, "masuda", "2026-04-17", "morning")
    assert result is not None
    _, rec = result
    assert rec["record_id"] == "masuda_row"


# ---- supersede_active ------------------------------------------------------


def test_supersede_active_updates_two_cells() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-16", time_of_day="evening",
             record_id="masuda_2026-04-16_evening_old"),
    ])
    new_id = "masuda_2026-04-16_evening_new"
    supersede_active(ws, row_index=2, new_record_id=new_id)
    assert ws.updates == [
        (2, COL_RECORD_STATUS, "superseded"),
        (2, COL_SUPERSEDED_BY, new_id),
    ]


def test_supersede_active_rejects_empty_new_id() -> None:
    ws = FakeWorksheet([])
    with pytest.raises(ValueError, match="new_record_id"):
        supersede_active(ws, row_index=2, new_record_id="")


def test_supersede_active_rejects_row_index_below_2() -> None:
    ws = FakeWorksheet([])
    with pytest.raises(ValueError, match="row_index"):
        supersede_active(ws, row_index=1, new_record_id="x")


# ---- rejected correction: superseded_by=null 末端ケース (§4.4 末端解釈) ----


def test_rejected_correction_produces_superseded_with_null_link() -> None:
    """採用されなかった訂正試行は superseded + superseded_by=null で追記される。

    本モジュールは dedicated ヘルパーを持たず、呼び出し側が MoodLogEntry を
    record_status='superseded', superseded_by=None で append する設計 (§A.6.3)。
    本テストはそのデータ表現が正しく鎖として読めるかを検証する。
    """
    ws = FakeWorksheet([
        _row(date="2026-04-17", time_of_day="morning", mood=4,
             recorded_at="2026-04-17T07:45:00", record_status="active",
             record_id="masuda_2026-04-17_morning_active"),
        _row(date="2026-04-17", time_of_day="morning", mood=3,
             recorded_at="2026-04-17T11:18:00", record_status="superseded",
             superseded_by="",
             record_id="masuda_2026-04-17_morning_rejected"),
    ])
    # active は 07:45 のまま維持されている
    result = find_active_record(ws, "masuda", "2026-04-17", "morning")
    assert result is not None
    _, active_rec = result
    assert active_rec["record_id"] == "masuda_2026-04-17_morning_active"

    # 鎖取得時は両方見える (recorded_at 昇順)
    chain = get_revision_chain(ws, "masuda", "2026-04-17", "morning")
    assert [r["record_status"] for r in chain] == ["active", "superseded"]
    # 11:18 は superseded_by が null 相当 (空文字)
    assert chain[1]["superseded_by"] == ""
    assert chain[1]["record_id"] == "masuda_2026-04-17_morning_rejected"


# ---- get_revision_chain ----------------------------------------------------


def test_get_revision_chain_sorts_by_recorded_at() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-16", time_of_day="evening", mood=3,
             recorded_at="2026-04-16T20:45:00", record_status="active",
             record_id="new_id"),
        _row(date="2026-04-16", time_of_day="evening", mood=2,
             recorded_at="2026-04-16T20:34:00", record_status="superseded",
             superseded_by="new_id", record_id="old_id"),
    ])
    chain = get_revision_chain(ws, "masuda", "2026-04-16", "evening")
    assert [r["recorded_at"] for r in chain] == [
        "2026-04-16T20:34:00",
        "2026-04-16T20:45:00",
    ]


def test_get_revision_chain_filters_by_scope() -> None:
    ws = FakeWorksheet([
        _row(date="2026-04-16", time_of_day="evening"),
        _row(date="2026-04-16", time_of_day="morning"),
        _row(date="2026-04-17", time_of_day="evening"),
    ])
    chain = get_revision_chain(ws, "masuda", "2026-04-16", "evening")
    assert len(chain) == 1
    assert chain[0]["date"] == "2026-04-16"
    assert chain[0]["time_of_day"] == "evening"
