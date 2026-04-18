"""mood-log シートからの読み込み・集計レイヤ (A〜Q 17 列準拠)。

v1.2 仕様:
    - fetch_active_records(): record_status=active のみ抽出 (§4.4)
    - get_revision_chain():   スコープ内 全レコードを時系列で返す (§A.5)
    - aggregate_*:            active かつ entry_mode != not_recorded のみ集計

カラム順 (v1.2 / 17 列): A:date B:mood C:energy D:thinking E:focus
    F:sleep_hours G:weather H:medication I:period J:recorded_at
    K:time_of_day L:daily_aspects M:record_id N:record_status
    O:superseded_by P:entry_mode Q:input_user

本モジュールはシート名を保持せず、呼び出し側が解決した Worksheet を
Worksheet Protocol 経由で注入する。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

NUMERIC_FIELDS = ("mood", "energy", "thinking", "focus", "sleep_hours")
SCORE_FIELDS = ("mood", "energy", "thinking", "focus")


class Worksheet(Protocol):
    """gspread.Worksheet が満たすべき最小インタフェース (読み取り用)。"""

    def get_all_records(self) -> List[Dict[str, Any]]: ...


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> Optional[bool]:
    """True/False/None を返す。空セルは None。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    return None


def _empty_agg() -> Dict[str, Any]:
    return {"count": 0, "mean": None, "min": None, "max": None}


def _agg(values: List[float]) -> Dict[str, Any]:
    if not values:
        return _empty_agg()
    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 4),
        "min": min(values),
        "max": max(values),
    }


class LogReader:
    """注入された Worksheet から読み込み・集計する。"""

    def __init__(self, worksheet: Worksheet) -> None:
        self._worksheet = worksheet

    # ---- fetch ---------------------------------------------------------

    def fetch_all(self) -> List[Dict[str, Any]]:
        """全行を辞書リストで返す (加工なし・順序保持)。"""
        return list(self._worksheet.get_all_records())

    def fetch_active_records(self) -> List[Dict[str, Any]]:
        """record_status=active のレコードを (date, time_of_day) 昇順で返す。

        not_recorded も active の一形態として含まれる (§4.3.2)。
        数値集計側で entry_mode を見て除外する責務を持つ。
        """
        active = [
            rec
            for rec in self.fetch_all()
            if str(rec.get("record_status", "")) == "active"
        ]
        active.sort(
            key=lambda r: (str(r.get("date", "")), str(r.get("time_of_day", "")))
        )
        return active

    def get_revision_chain(
        self, input_user: str, date: str, time_of_day: str
    ) -> List[Dict[str, Any]]:
        """スコープ内全レコード (active + superseded) を recorded_at 昇順で返す。"""
        records = [
            r
            for r in self.fetch_all()
            if str(r.get("input_user", "")) == input_user
            and str(r.get("date", "")) == date
            and str(r.get("time_of_day", "")) == time_of_day
        ]
        records.sort(key=lambda r: str(r.get("recorded_at", "")))
        return records

    # ---- aggregates (numeric, not_recorded を除外) ---------------------

    def _numeric_target_records(self) -> List[Dict[str, Any]]:
        """active かつ entry_mode != not_recorded のレコード (集計対象)。"""
        return [
            r
            for r in self.fetch_active_records()
            if str(r.get("entry_mode", "")) != "not_recorded"
        ]

    def _collect_numeric(self, field: str) -> List[float]:
        out: List[float] = []
        for rec in self._numeric_target_records():
            v = _to_float(rec.get(field))
            if v is not None:
                out.append(v)
        return out

    def aggregate_mood(self) -> Dict[str, Any]:
        return _agg(self._collect_numeric("mood"))

    def aggregate_energy(self) -> Dict[str, Any]:
        return _agg(self._collect_numeric("energy"))

    def aggregate_thinking(self) -> Dict[str, Any]:
        return _agg(self._collect_numeric("thinking"))

    def aggregate_focus(self) -> Dict[str, Any]:
        return _agg(self._collect_numeric("focus"))

    def aggregate_sleep(self) -> Dict[str, Any]:
        return _agg(self._collect_numeric("sleep_hours"))

    # ---- ratios / distribution (optional fields) -----------------------

    def _bool_ratio(self, field: str) -> Optional[float]:
        bools = [_to_bool(r.get(field)) for r in self._numeric_target_records()]
        bools = [b for b in bools if b is not None]
        if not bools:
            return None
        return round(sum(1 for b in bools if b) / len(bools), 4)

    def medication_ratio(self) -> Optional[float]:
        """medication == True の比率 (0.0-1.0)。記録なしは None。"""
        return self._bool_ratio("medication")

    def period_ratio(self) -> Optional[float]:
        """period == True の比率 (0.0-1.0)。記録なしは None。"""
        return self._bool_ratio("period")

    def weather_distribution(self) -> Dict[str, int]:
        """weather 値の出現回数 (空セルと not_recorded は除外)。"""
        dist: Dict[str, int] = {}
        for r in self._numeric_target_records():
            w = r.get("weather")
            if w is None or w == "":
                continue
            key = str(w)
            dist[key] = dist.get(key, 0) + 1
        return dist
