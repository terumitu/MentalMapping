"""mood_log シートからの読み込み・集計レイヤ。

同日複数レコードは recorded_at が最も新しい 1 件のみを採用する。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


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


def _to_int(value: Any) -> Optional[int]:
    f = _to_float(value)
    if f is None:
        return None
    return int(f)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


class LogReader:
    """mood_log Worksheet から読み込み・集計する。"""

    def __init__(self, worksheet: Worksheet) -> None:
        self._worksheet = worksheet

    def fetch_all(self) -> List[Dict[str, Any]]:
        """全行を辞書リストで返す（加工なし・順序保持）。"""
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

    def aggregate_mood(self) -> Dict[str, Any]:
        """mood_score の基本集計（count / mean / min / max）。

        同日複数記録は fetch_latest_per_day 基準で集計する。
        """
        records = self.fetch_latest_per_day()
        scores: List[float] = []
        for rec in records:
            v = _to_float(rec.get("mood_score"))
            if v is not None:
                scores.append(v)
        if not scores:
            return {"count": 0, "mean": None, "min": None, "max": None}
        return {
            "count": len(scores),
            "mean": round(sum(scores) / len(scores), 4),
            "min": min(scores),
            "max": max(scores),
        }

    def aggregate_sleep(self) -> Dict[str, Any]:
        """sleep_hours の基本集計。"""
        records = self.fetch_latest_per_day()
        hours: List[float] = []
        for rec in records:
            v = _to_float(rec.get("sleep_hours"))
            if v is not None:
                hours.append(v)
        if not hours:
            return {"count": 0, "mean": None, "min": None, "max": None}
        return {
            "count": len(hours),
            "mean": round(sum(hours) / len(hours), 4),
            "min": min(hours),
            "max": max(hours),
        }

    def outside_ratio(self) -> Optional[float]:
        """went_outside == True の比率（0.0-1.0）。レコードが無ければ None。"""
        records = self.fetch_latest_per_day()
        if not records:
            return None
        outside = sum(1 for r in records if _to_bool(r.get("went_outside")))
        return round(outside / len(records), 4)
