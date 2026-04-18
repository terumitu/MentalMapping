"""not_recorded 既存時の訂正ダイアログ動作確認 (v1.2.3 §A.6.3 分岐)。

検証対象:
  - is_not_recorded_overwrite() 純関数 predicate (entry_mode 文字列で分岐判定)
  - find_active_record() が not_recorded を発見対象に含む (現行仕様維持確認)
  - 上書きフロー: 既存 not_recorded の supersede + 新 active の append
    (両ケース同一実装で動作することの保証)

ダイアログ UI 自体 (@st.dialog) は本ユニットテストの対象外
(Streamlit セッション必須のため。手動ブラウザ検証で代替)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

from modules.log_writer import LogWriter, MoodLogEntry
from modules.record_chain import (
    COL_RECORD_STATUS,
    COL_SUPERSEDED_BY,
    find_active_record,
    is_not_recorded_overwrite,
    supersede_active,
)


class FakeWorksheet:
    """get_all_records / append_row / update_cell を追跡する最小実装。"""

    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self._records = [dict(r) for r in records]
        self.appends: List[List[Any]] = []
        self.updates: List[Tuple[int, int, Any]] = []

    def get_all_records(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._records]

    def append_row(self, row: List[Any]) -> None:
        self.appends.append(row)

    def update_cell(self, row: int, col: int, value: Any) -> None:
        self.updates.append((row, col, value))


def _not_recorded_record(
    *,
    date: str = "2026-04-19",
    time_of_day: str = "morning",
    input_user: str = "masuda",
    record_id: str = "",
) -> Dict[str, Any]:
    """not_recorded active レコードのフィクスチャ (17 列)。"""
    return {
        "date": date, "mood": "", "energy": "", "thinking": "", "focus": "",
        "sleep_hours": "", "weather": "", "medication": "", "period": "",
        "recorded_at": f"{date}T18:00:00", "time_of_day": time_of_day,
        "daily_aspects": "",
        "record_id": record_id or f"{input_user}_{date}_{time_of_day}_nr",
        "record_status": "active", "superseded_by": "",
        "entry_mode": "not_recorded", "input_user": input_user,
    }


# ---- is_not_recorded_overwrite predicate -----------------------------------


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("not_recorded", True),
        ("realtime", False),
        ("retroactive", False),
        ("pending", False),
        ("", False),
    ],
)
def test_is_not_recorded_overwrite_branches_by_entry_mode(
    mode: str, expected: bool
) -> None:
    assert is_not_recorded_overwrite({"entry_mode": mode}) is expected


def test_is_not_recorded_overwrite_handles_missing_key() -> None:
    """entry_mode キー欠落は False (通常 3 択ダイアログを発動)。"""
    assert is_not_recorded_overwrite({}) is False


def test_is_not_recorded_overwrite_handles_non_string_value() -> None:
    """非文字列値も str() 経由で安全に判定する。"""
    assert is_not_recorded_overwrite({"entry_mode": None}) is False
    assert is_not_recorded_overwrite({"entry_mode": 0}) is False


# ---- find_active_record が not_recorded を対象に含む確認 -------------------


def test_find_active_record_finds_not_recorded() -> None:
    """not_recorded は active の一形態としてダイアログ発動対象になる (§4.3.2)。"""
    ws = FakeWorksheet([_not_recorded_record()])
    result = find_active_record(ws, "masuda", "2026-04-19", "morning")
    assert result is not None
    row_idx, rec = result
    assert row_idx == 2
    assert rec["entry_mode"] == "not_recorded"
    # 分岐 predicate も True を返す
    assert is_not_recorded_overwrite(rec) is True


# ---- end-to-end: not_recorded を上書きする昇格フロー (§4.4.1) --------------


def test_overwrite_not_recorded_supersedes_existing_and_appends_new_active() -> None:
    """既存 not_recorded の supersede + 新 active の append が 1 連で成立。

    検証ポイント:
      - LogWriter.append() で新レコード (active / retroactive) が追記
      - supersede_active() で旧 not_recorded 行の N/O 列が更新
      - 両者が呼ばれる順序 (§A.4: append → supersede) は呼び出し側責務
    """
    ws = FakeWorksheet([_not_recorded_record(
        record_id="masuda_2026-04-19_morning_nr"
    )])

    # Step 1: 既存 active を find (not_recorded を含む)
    existing = find_active_record(ws, "masuda", "2026-04-19", "morning")
    assert existing is not None
    row_idx, existing_rec = existing
    assert is_not_recorded_overwrite(existing_rec) is True

    # Step 2: 新 active を append (§A.4 順序: 先に新を書く)
    new_id = "masuda_2026-04-19_morning_real"
    new_entry = MoodLogEntry.create(
        date="2026-04-19", mood=4, energy=4, thinking=4, focus=4,
        time_of_day="morning", input_user="masuda",
        record_id=new_id, entry_mode="retroactive",
        recorded_at="2026-04-19T20:00:00",
        sleep_hours=7.0, weather="晴", medication=False, period=False,
    )
    LogWriter(ws).append(new_entry)
    # 新レコードが active で追記されている
    assert len(ws.appends) == 1
    appended = ws.appends[0]
    assert appended[12] == new_id          # M: record_id
    assert appended[13] == "active"        # N: record_status
    assert appended[14] == ""              # O: superseded_by (null = "")
    assert appended[15] == "retroactive"   # P: entry_mode (§4.4.1 昇格)

    # Step 3: 既存 not_recorded を superseded 化
    supersede_active(ws, row_idx, new_id)
    assert ws.updates == [
        (row_idx, COL_RECORD_STATUS, "superseded"),
        (row_idx, COL_SUPERSEDED_BY, new_id),
    ]


def test_overwrite_not_recorded_chain_uses_same_implementation_as_normal() -> None:
    """not_recorded ケースと realtime ケースで record_chain 実装が共通であることの保証。

    分岐は app.py 側のダイアログ UI のみであり、modules/record_chain.py に
    not_recorded 専用コードを置かない設計判断 (v1.2.3 §A.6.3 実装責務分離) を
    回帰防止する。
    """
    # Case 1: existing realtime
    ws_a = FakeWorksheet([{
        **_not_recorded_record(record_id="masuda_2026-04-19_morning_rt"),
        "entry_mode": "realtime", "mood": 3, "energy": 3, "thinking": 3, "focus": 3,
    }])
    found_a = find_active_record(ws_a, "masuda", "2026-04-19", "morning")
    assert found_a is not None
    supersede_active(ws_a, found_a[0], "masuda_2026-04-19_morning_new")

    # Case 2: existing not_recorded
    ws_b = FakeWorksheet([_not_recorded_record(
        record_id="masuda_2026-04-19_morning_nr"
    )])
    found_b = find_active_record(ws_b, "masuda", "2026-04-19", "morning")
    assert found_b is not None
    supersede_active(ws_b, found_b[0], "masuda_2026-04-19_morning_new")

    # 両ケースで同じ row index に同じ列が更新される (現行実装の共有を確認)
    assert ws_a.updates == ws_b.updates
