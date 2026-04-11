"""mood-log シートからの読み込み・集計レイヤ (Google Sheets 実スキーマ A〜K 準拠)。

カラム順 (A〜K):
    A:date B:mood C:energy D:thinking E:focus F:sleep_hours
    G:weather H:medication I:period J:recorded_at K:time_of_day

本モジュールはシート名を保持せず、呼び出し側が解決した Worksheet を
Worksheet Protocol 経由で注入する。マルチユーザー運用では
ユーザーごとに別シートの Worksheet を差し替えて使う。get_all_records
はヘッダ行キーで dict を返すので、列位置の変更には影響されない。
同日複数レコードは recorded_at が最も新しい 1 件のみを採用する。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

NUMERIC_FIELDS = ("mood", "energy", "thinking", "focus", "sleep_hours")
SCORE_FIELDS = ("mood", "energy", "thinking", "focus")


class Worksheet(Protocol):
    """gspread.Worksheet が満たすべき最小インタフェース。"""

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

    def fetch_latest_per_day(self) -> List[Dict[str, Any]]:
        """同日複数記録時は recorded_at が最新の 1 件を採用。date 昇順で返す。"""
        latest: Dict[str, Dict[str, Any]] = {}
        for rec in self.fetch_all():
            date = rec.get("date")
            if not date:
                continue
            prev = latest.get(date)
            if prev is None:
                latest[date] = rec
                continue
            if str(rec.get("recorded_at", "")) >= str(prev.get("recorded_at", "")):
                latest[date] = rec
        return [latest[d] for d in sorted(latest.keys())]

    # ---- aggregates (numeric) ------------------------------------------

    def _collect_numeric(self, field: str) -> List[float]:
        records = self.fetch_latest_per_day()
        out: List[float] = []
        for rec in records:
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
        records = self.fetch_latest_per_day()
        bools = [_to_bool(r.get(field)) for r in records]
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
        """weather 値の出現回数 (空セルは除外)。"""
        records = self.fetch_latest_per_day()
        dist: Dict[str, int] = {}
        for r in records:
            w = r.get("weather")
            if w is None or w == "":
                continue
            key = str(w)
            dist[key] = dist.get(key, 0) + 1
        return dist
