"""record_chain — record_id 生成 / 鎖構造運用 (§4.4 / §A.3 / §A.4)。

鎖のスコープは (input_user, date, time_of_day)。
同一スコープ内 record_status=active は常に 1 件以内。鎖は線形リスト。

関数:
    generate_record_id       {input_user}_{date}_{time_of_day}_{unix_ts}
    find_active_record       スコープ内 active を (row_index, record) で返す
    supersede_active         既存 active を superseded に書き換え、superseded_by 設定
    get_revision_chain       スコープ内全レコードを recorded_at 昇順で返す

訂正書き込み順序 (§A.4):
    1. 新レコード R_new を active, superseded_by=null で append
    2. 旧 active を UPDATE: status=superseded, superseded_by=R_new.record_id

採用されなかった訂正試行は「新レコードを record_status=superseded,
superseded_by=null で append する」操作であり、本モジュールには専用関数を
置かない (呼び出し側が MoodLogEntry で直接生成する)。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple

# Sheets の列番号 (1-based)
# 列順: A=date … N=record_status, O=superseded_by
COL_RECORD_STATUS = 14  # N
COL_SUPERSEDED_BY = 15  # O


class Worksheet(Protocol):
    """gspread.Worksheet が満たすべき最小インタフェース (更新用)。"""

    def get_all_records(self) -> List[Dict[str, Any]]: ...
    def update_cell(self, row: int, col: int, value: Any) -> Any: ...


def generate_record_id(
    input_user: str, date: str, time_of_day: str, recorded_at: datetime
) -> str:
    """record_id を '{input_user}_{date}_{time_of_day}_{unix_ts}' 形式で生成する。

    unix_ts は recorded_at の UNIX 秒 (int)。recorded_at は tz-aware datetime を
    推奨 (naive の場合はローカルタイム扱いの timestamp() になる)。
    """
    if not input_user:
        raise ValueError("input_user must not be empty")
    if not date:
        raise ValueError("date must not be empty")
    if time_of_day not in ("morning", "evening"):
        raise ValueError(
            f"time_of_day must be 'morning' or 'evening', got {time_of_day!r}"
        )
    if not isinstance(recorded_at, datetime):
        raise ValueError(
            f"recorded_at must be datetime, got {type(recorded_at).__name__}"
        )
    unix_ts = int(recorded_at.timestamp())
    return f"{input_user}_{date}_{time_of_day}_{unix_ts}"


def _scope_matches(rec: Dict[str, Any], input_user: str, date: str, tod: str) -> bool:
    return (
        str(rec.get("input_user", "")) == input_user
        and str(rec.get("date", "")) == date
        and str(rec.get("time_of_day", "")) == tod
    )


def find_active_record(
    worksheet: Worksheet,
    input_user: str,
    date: str,
    time_of_day: str,
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """スコープ内 active レコードを (row_index, record_dict) で返す。

    row_index は Sheets 上の 1-based 行番号 (ヘッダ行 = 1、データ 1 件目 = 2)。
    get_all_records はヘッダを除くため enumerate(start=2) とする。
    不在時は None。不変条件上 active は 1 件以内のため、最初に見つけた 1 件を返す。
    """
    if time_of_day not in ("morning", "evening"):
        raise ValueError(
            f"time_of_day must be 'morning' or 'evening', got {time_of_day!r}"
        )
    for idx, rec in enumerate(worksheet.get_all_records(), start=2):
        if (
            _scope_matches(rec, input_user, date, time_of_day)
            and str(rec.get("record_status", "")) == "active"
        ):
            return idx, rec
    return None


def supersede_active(
    worksheet: Worksheet, row_index: int, new_record_id: str
) -> None:
    """既存 active 行を superseded に更新し、superseded_by を新 record_id に設定する。

    UPDATE 対象は N (record_status) / O (superseded_by) の 2 列のみ (§4.4)。
    """
    if not new_record_id:
        raise ValueError("new_record_id must not be empty")
    if row_index < 2:
        raise ValueError(f"row_index must be >= 2, got {row_index!r}")
    worksheet.update_cell(row_index, COL_RECORD_STATUS, "superseded")
    worksheet.update_cell(row_index, COL_SUPERSEDED_BY, new_record_id)


def get_revision_chain(
    worksheet: Worksheet,
    input_user: str,
    date: str,
    time_of_day: str,
) -> List[Dict[str, Any]]:
    """スコープ内 全レコード (active + superseded) を recorded_at 昇順で返す。

    (§A.5 参考: 訂正履歴閲覧用)。
    """
    if time_of_day not in ("morning", "evening"):
        raise ValueError(
            f"time_of_day must be 'morning' or 'evening', got {time_of_day!r}"
        )
    records = [
        rec
        for rec in worksheet.get_all_records()
        if _scope_matches(rec, input_user, date, time_of_day)
    ]
    records.sort(key=lambda r: str(r.get("recorded_at", "")))
    return records


def is_not_recorded_overwrite(existing_record: Dict[str, Any]) -> bool:
    """既存 active レコードが not_recorded か判定する (v1.2.3 §A.6.3 分岐用)。

    True の場合、訂正ダイアログは「上書き / キャンセル」の 2 択に縮退し、
    「試行として残す」を非表示にする。理由: not_recorded への「訂正試行」
    (superseded_by=null 末端) は意味不成立 (自動生成 vs ユーザー入力の関係)。

    上書き時のチェーン操作 (find_active_record + supersede_active) は両
    ケースで同一実装を使用するため、本関数は UI 分岐判定のみに用いる。
    """
    return str(existing_record.get("entry_mode", "")) == "not_recorded"
