"""MentalMapping v1.2 マイグレーションバッチ

現行 11 列スキーマ → v1.2 17 列スキーマへの遡及適用（§docs/arch_mentalmap_v1_2.md §A.5.7）。

構成:
- Phase 1: 読み取り専用調査（`phase1_investigation`）
- Phase 2: 13 ステップ（ステップ関数・本ファイル内実装）

CLI 例:
    python devtools/migrate_v1_2.py --phase 1
    python devtools/migrate_v1_2.py --phase 2 --step 1
    python devtools/migrate_v1_2.py --phase 2 --step 4_5_8 --execute

注意:
- `--phase 1` は書き込み系 API を物理的にガード（`--execute` 指定時も読み取りのみ）。
- Phase 2 は `--dry-run` をデフォルトとし、`--execute` 指定時のみ Sheets を更新する。
- バックアップ（ステップ 1 本実行）完了まで、ステップ 2 以降の本実行を行わない運用とする。
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.sheet_client import connect_worksheet, load_settings  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")

HEADERS_V11 = [
    "date", "mood", "energy", "thinking", "focus",
    "sleep_hours", "weather", "medication", "period",
    "recorded_at", "time_of_day",
]

HEADERS_V12_ADDITION = [
    "daily_aspects", "record_id", "record_status",
    "superseded_by", "entry_mode", "input_user",
]

HEADERS_V12 = HEADERS_V11 + HEADERS_V12_ADDITION

USERS_TARGET = ("masuda", "nishide", "suyasu")

# Phase 2 ステップ ID（`migrate_v1_2_steps.STEP_DISPATCHER` のキーと一致）。
# CLI --step の choices 用。ここで保持することで parse_args が _steps モジュールを
# import せずに済み、--phase 1 実行時の循環 import を回避する。
STEP_CHOICES = ("1", "2", "3", "4_5_8", "6_7", "9", "10", "11", "12", "13")

# Phase 2 enum 定数（複数 steps ファイルから参照するため共通基盤に配置）。
# v1.2.1 で entry_mode に "pending" 追加（settings.yaml で realtime_window 未定義のユーザー向け）。
ENUM_TIME_OF_DAY = ("morning", "evening")
ENUM_WEATHER = ("晴", "曇", "雨", "雨/雪")
ENUM_RECORD_STATUS = ("active", "superseded")
ENUM_ENTRY_MODE = ("realtime", "retroactive", "not_recorded", "pending")

# §A.5.3 増田確定済み 5 件。
# superseded_by_ref はステップ 6 で他レコードの record_id に解決する。
# 書式: (date, recorded_at_time_hhmm, time_of_day, record_status,
#         superseded_by_ref, entry_mode)
# superseded_by_ref が辞書キー文字列 → ステップ 6 で解決 / None → null
MASUDA_FIXED_RECORDS = [
    ("2026-04-14", "12:12", "morning", "active", None, "realtime"),
    ("2026-04-16", "20:34", "evening", "superseded",
     "masuda@2026-04-16@evening@20:45", "realtime"),
    ("2026-04-16", "20:45", "evening", "active", None, "realtime"),
    ("2026-04-17", "07:45", "morning", "active", None, "realtime"),
    ("2026-04-17", "11:18", "morning", "superseded", None, "realtime"),
]

OUTPUT_DIR = _PROJECT_ROOT / "output" / "migration_v1_2"


# ============================================================================
# ヘルパ
# ============================================================================

def jst_now() -> datetime:
    return datetime.now(JST)


_ISO_LENIENT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{1,2}):(\d{1,2}):(\d{1,2})$")


def _normalize_iso_jst(ts: str) -> str:
    """単桁 H/M/S をゼロパディングして ISO 8601 準拠形式にする（lenient 化）。

    設計書 §4.1 は ISO 8601 指定だが、実データに一部非準拠（例: "2026-04-16T9:34:37"）
    があるため、パース直前に正規化する。表示値は変更しない（内部処理のみ）。
    """
    m = _ISO_LENIENT_RE.match(ts)
    if not m:
        return ts
    date_part, h, mi, s = m.groups()
    return f"{date_part}T{h.zfill(2)}:{mi.zfill(2)}:{s.zfill(2)}"


def parse_iso_jst(ts: str) -> datetime:
    """recorded_at (ISO 8601 "YYYY-MM-DDTHH:MM:SS") を JST tz-aware に変換。

    設計書 §4.1 で TZ 無しの ISO 8601 と確定済。naive 値は JST とみなす。
    単桁 H/M/S は `_normalize_iso_jst` で自動ゼロパディング。
    """
    dt = datetime.fromisoformat(_normalize_iso_jst(ts))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(JST)


def unix_ts_of(ts: str) -> int:
    return int(parse_iso_jst(ts).timestamp())


def make_record_id(user: str, date_str: str, tod: str, unix_ts: int) -> str:
    return f"{user}_{date_str}_{tod}_{unix_ts}"


def _hhmm_to_minutes(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def within_realtime_window(t: time, window: tuple[str, str]) -> bool:
    """[start, end) 半開区間で time() を判定。

    end が "26:00" 等 24 時超の場合は翌日 02:00 JST を意味するため、
    [start, 24:00) ∪ [00:00, end-24:00) として扱う。
    """
    start_m = _hhmm_to_minutes(window[0])
    end_m = _hhmm_to_minutes(window[1])
    t_m = t.hour * 60 + t.minute
    if end_m <= 24 * 60:
        return start_m <= t_m < end_m
    wrapped_end = end_m - 24 * 60
    return (t_m >= start_m) or (t_m < wrapped_end)


def ensure_output_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_worksheet(user_key: str) -> Any:
    """指定ユーザーの worksheet を開く。

    suyasu は settings.yaml でコメントアウト済のため resolve_sheet_name では
    解決できない。worksheet 名を `mood_log_{user_key}` 直指定で開く。
    """
    sheet_name = f"mood_log_{user_key}"
    return connect_worksheet(sheet_name=sheet_name)


def fetch_all_rows(ws: Any) -> list[list[Any]]:
    return ws.get_all_values()


def write_csv(path: Path, headers: Iterable[str], rows: Iterable[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(headers))
        w.writerows(rows)


def col_letter(idx_0based: int) -> str:
    """0-based 列インデックス → A1 表記の列記号（A, B, ..., Z, AA, ...）。"""
    result = ""
    n = idx_0based + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


# ============================================================================
# Phase 1: 先行調査（読み取り専用）
# ============================================================================

def _inspect_worksheet(user: str) -> dict[str, Any]:
    try:
        ws = get_worksheet(user)
        rows = fetch_all_rows(ws)
    except Exception as e:
        return {"exists": False, "error": f"{type(e).__name__}: {e}"}
    header = rows[0] if rows else []
    data = rows[1:] if len(rows) > 1 else []
    return {
        "exists": True,
        "record_count": len(data),
        "header": header,
        "header_matches_v11": header == HEADERS_V11,
        "first_5": data[:5],
        "last_5": data[-5:],
        "all_rows": rows,
    }


def _check_masuda_fixed(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    if not rows:
        return {}
    header = rows[0]
    data = rows[1:]
    try:
        idx_date = header.index("date")
        idx_rec = header.index("recorded_at")
        idx_tod = header.index("time_of_day")
    except ValueError:
        return {"_schema_error": {"found": False, "count": 0}}
    result: dict[str, dict[str, Any]] = {}
    for date_str, hhmm, tod, *_ in MASUDA_FIXED_RECORDS:
        count = 0
        for row in data:
            if len(row) <= max(idx_date, idx_rec, idx_tod):
                continue
            if row[idx_date] != date_str or row[idx_tod] != tod:
                continue
            try:
                rec_dt = parse_iso_jst(row[idx_rec])
            except Exception:
                continue
            if rec_dt.strftime("%H:%M") == hhmm:
                count += 1
        result[f"{date_str} {hhmm} {tod}"] = {"found": count > 0, "count": count}
    return result


def _list_rain_records(user: str, rows: list[list[Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    header = rows[0]
    data = rows[1:]
    if "weather" not in header:
        return []
    idx_w = header.index("weather")
    idx_d = header.index("date")
    idx_t = header.index("time_of_day")
    out: list[dict[str, Any]] = []
    for row in data:
        if len(row) <= idx_w:
            continue
        if row[idx_w].strip() == "雨":
            out.append({
                "user": user,
                "date": row[idx_d] if len(row) > idx_d else None,
                "time_of_day": row[idx_t] if len(row) > idx_t else None,
            })
    return out


def _list_unexpected_duplicates(user: str, rows: list[list[Any]]) -> list[dict[str, Any]]:
    """同一 (date, time_of_day) に複数レコードがある組を列挙。

    §A.5.3 で確定済みのグループ（増田 04-16 evening / 04-17 morning）は除外。
    """
    if not rows or len(rows) < 2:
        return []
    header = rows[0]
    data = rows[1:]
    try:
        idx_d = header.index("date")
        idx_t = header.index("time_of_day")
    except ValueError:
        return []
    fixed_groups = {(d, tod) for d, _, tod, *_ in MASUDA_FIXED_RECORDS}
    counts: dict[tuple[str, str], int] = {}
    for row in data:
        if len(row) <= max(idx_d, idx_t):
            continue
        key = (row[idx_d], row[idx_t])
        counts[key] = counts.get(key, 0) + 1
    out: list[dict[str, Any]] = []
    for (d, tod), c in sorted(counts.items()):
        if c < 2:
            continue
        if user == "masuda" and (d, tod) in fixed_groups:
            continue
        out.append({"user": user, "date": d, "time_of_day": tod, "count": c})
    return out


def phase1_investigation(users: tuple[str, ...]) -> dict[str, Any]:
    """Phase 1: 書き込みを一切発生させない読み取り専用調査。"""
    report: dict[str, Any] = {
        "generated_at": jst_now().isoformat(timespec="seconds"),
        "worksheets": {},
        "masuda_fixed_check": {},
        "weather_rain_records": [],
        "unexpected_duplicates": [],
        "environment": {},
    }
    for user in users:
        info = _inspect_worksheet(user)
        # all_rows は後続検査で使うのみ。レポートには含めない。
        rows = info.pop("all_rows", None) if info.get("exists") else None
        report["worksheets"][user] = info
        if not info.get("exists"):
            continue
        if user == "masuda":
            report["masuda_fixed_check"] = _check_masuda_fixed(rows or [])
        report["weather_rain_records"].extend(_list_rain_records(user, rows or []))
        report["unexpected_duplicates"].extend(_list_unexpected_duplicates(user, rows or []))
    report["environment"] = {
        "gspread_auth": "OK",
        "backup_method": "ws.get_all_values() → CSV (output/migration_v1_2/backup_YYYYMMDD/)",
        "dry_run_method": "読み取り + output/migration_v1_2/report_step{N}.csv 出力",
        "output_dir_exists": OUTPUT_DIR.exists(),
    }
    return report


def format_phase1_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# MentalMapping v1.2 マイグレーション Phase 1 調査結果")
    lines.append("")
    lines.append(f"**実行日時**: {report['generated_at']} (JST)")
    lines.append("")
    lines.append("## worksheet 状態")
    for user, info in report["worksheets"].items():
        if info.get("exists"):
            lines.append(
                f"- `mood_log_{user}`: **{info['record_count']} 件** "
                f"(header_matches_v11={info['header_matches_v11']})"
            )
        else:
            lines.append(f"- `mood_log_{user}`: **取得失敗** {info.get('error')}")
    lines.append("")
    lines.append("## 既存列構造（11 列）")
    for user, info in report["worksheets"].items():
        if not info.get("exists"):
            continue
        status = "合致" if info["header_matches_v11"] else "**乖離**"
        lines.append(f"- `mood_log_{user}`: {status}")
        if not info["header_matches_v11"]:
            lines.append(f"    - 実際: {info['header']}")
            lines.append(f"    - 期待: {HEADERS_V11}")
    lines.append("")
    lines.append("## 増田 確定済みレコード実在チェック（§A.5.3）")
    mfc = report["masuda_fixed_check"]
    if not mfc:
        lines.append("- masuda worksheet 未取得のためスキップ")
    else:
        for key, status in mfc.items():
            mark = "存在" if status["found"] else "**不在**"
            lines.append(f"- 増田 {key}: {mark} (count={status['count']})")
    lines.append("")
    lines.append('## weather "雨" レコード')
    if not report["weather_rain_records"]:
        lines.append("- 該当なし")
    else:
        for rec in report["weather_rain_records"]:
            lines.append(
                f"- `mood_log_{rec['user']}` {rec['date']} {rec['time_of_day']}"
            )
    lines.append("")
    lines.append("## 想定外の複数レコード（§A.5.3 外）")
    if not report["unexpected_duplicates"]:
        lines.append("- 該当なし")
    else:
        for d in report["unexpected_duplicates"]:
            lines.append(
                f"- `mood_log_{d['user']}` {d['date']} {d['time_of_day']}: "
                f"{d['count']} 件"
            )
    lines.append("")
    lines.append("## 環境")
    env = report["environment"]
    lines.append(f"- gspread 認証: {env['gspread_auth']}")
    lines.append(f"- バックアップ方式: {env['backup_method']}")
    lines.append(f"- ドライラン方式: {env['dry_run_method']}")
    created = "作成済" if env["output_dir_exists"] else "未作成"
    lines.append(f"- output/migration_v1_2/: {created}")
    lines.append("")
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MentalMapping v1.2 マイグレーション（13 ステップ）",
    )
    p.add_argument("--phase", type=int, choices=[1, 2], required=True)
    p.add_argument(
        "--step",
        choices=list(STEP_CHOICES),
        help="Phase 2 のみ必須",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    mode.add_argument("--execute", dest="dry_run", action="store_false")
    p.add_argument(
        "--user",
        choices=["masuda", "nishide", "suyasu", "all"],
        default="all",
    )
    return p.parse_args(argv)


def _resolve_users(user_arg: str) -> tuple[str, ...]:
    if user_arg == "all":
        return USERS_TARGET
    return (user_arg,)


def _run_phase1(users: tuple[str, ...], *, dry_run: bool) -> int:
    # 西出要望 (c): --phase 1 では --execute 指定時も書き込み系 API を呼ばない。
    # phase1_investigation は読み取り専用関数のため物理的にガードされる。
    if not dry_run:
        print(
            "[NOTE] --phase 1 は常に読み取り専用。--execute は無視されました。",
            file=sys.stderr,
        )
    report = phase1_investigation(users)
    body = format_phase1_report(report)
    dest = OUTPUT_DIR / "phase1_report.md"
    dest.write_text(body, encoding="utf-8")
    print(body)
    print(f"\n[OK] Phase 1 完了 → {dest}")
    return 0


def _run_phase2(args: argparse.Namespace, users: tuple[str, ...]) -> int:
    if not args.step:
        print("--phase 2 では --step 必須", file=sys.stderr)
        return 2
    # 遅延 import: Phase 1 実行時は _steps モジュールを一切ロードしない。
    from devtools.migrate_v1_2_steps import STEP_DISPATCHER
    fn = STEP_DISPATCHER[args.step]
    try:
        if args.step == "13":
            fn(users)
        else:
            fn(users, execute=not args.dry_run)
    except NotImplementedError as e:
        print(f"[PENDING] {e}", file=sys.stderr)
        return 3
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    ensure_output_dirs()
    users = _resolve_users(args.user)
    if args.phase == 1:
        return _run_phase1(users, dry_run=args.dry_run)
    if args.phase == 2:
        return _run_phase2(args, users)
    return 2


if __name__ == "__main__":
    sys.exit(main())
