"""MentalMapping v1.2 マイグレーション Phase 2 schema ステップ

スキーマ準備系ステップ（1, 2, 3）をまとめる。
- ステップ 1: バックアップ取得
- ステップ 2: 値域バリデーション + BLOCKER-3 `moning→morning` 訂正
- ステップ 3: M〜Q 5 列追加（BLOCKER-1: daily_aspects は既存保護）
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from devtools.migrate_v1_2 import (
    ENUM_TIME_OF_DAY,
    ENUM_WEATHER,
    HEADERS_V11,
    HEADERS_V12,
    HEADERS_V12_ADDITION,
    OUTPUT_DIR,
    col_letter,
    fetch_all_rows,
    get_worksheet,
    jst_now,
    write_csv,
)

INT_1_5_FIELDS = ("mood", "energy", "thinking", "focus")

# BLOCKER-3: time_of_day タイポ自動訂正ルール。冪等に動作。
TIME_OF_DAY_CORRECTIONS: dict[str, str] = {
    "moning": "morning",
}


# ============================================================================
# ステップ 1: バックアップ取得
# ============================================================================

def _resolve_backup_dir() -> Path:
    """本日（JST）の backup_YYYYMMDD/ を返す。既存時は HHMMSS 付きで回避。"""
    now = jst_now()
    today = now.strftime("%Y%m%d")
    primary = OUTPUT_DIR / f"backup_{today}"
    if not primary.exists():
        return primary
    hhmmss = now.strftime("%H%M%S")
    return OUTPUT_DIR / f"backup_{today}_{hhmmss}"


def _print_backup_plan(snapshots: list, backup_dir: Path, *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step01_backup / {mode}]")
    print(f"  backup_dir: {backup_dir}")
    print(f"  backup_dir exists: {backup_dir.exists()}")
    for user, rows, dest in snapshots:
        total = len(rows)
        data_count = max(total - 1, 0)
        print(f"  - {user}: header+{data_count} data rows (total {total}) "
              f"-> {dest.name}")


def step01_backup(users: tuple[str, ...], *, execute: bool) -> None:
    """各 worksheet 全行を CSV バックアップ（UTF-8 BOM-free）。"""
    backup_dir = _resolve_backup_dir()
    snapshots: list[tuple[str, list, Path]] = []
    for user in users:
        ws = get_worksheet(user)
        rows = fetch_all_rows(ws)
        dest = backup_dir / f"mood_log_{user}.csv"
        snapshots.append((user, rows, dest))
    _print_backup_plan(snapshots, backup_dir, execute=execute)
    if not execute:
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    for user, rows, dest in snapshots:
        header = rows[0] if rows else []
        body = rows[1:] if len(rows) > 1 else []
        write_csv(dest, header, body)
        print(f"  [WROTE] {dest}")


# ============================================================================
# ステップ 2: 値域バリデーション + BLOCKER-3 訂正
# ============================================================================

def _violation(user: str, row: int, field: str, v: str, note: str) -> dict:
    return {"user": user, "row": row, "field": field, "value_before": v,
            "value_after": "", "action": "VIOLATION", "note": note}


def _correction(user: str, row: int, field: str, col_idx: int,
                v_before: str, v_after: str) -> dict:
    return {"user": user, "row": row, "field": field, "col_idx": col_idx,
            "value_before": v_before, "value_after": v_after,
            "action": "CORRECTION", "note": ""}


def _check_int_1_5(user: str, sheet_row: int, header: list, row: list, field: str):
    if field not in header:
        return None
    idx = header.index(field)
    if len(row) <= idx or row[idx] == "":
        return None
    v = row[idx]
    try:
        iv = int(v)
        if 1 <= iv <= 5:
            return None
        return _violation(user, sheet_row, field, v, "out of range [1,5]")
    except ValueError:
        return _violation(user, sheet_row, field, v, "not int")


def _check_float_0_24(user: str, sheet_row: int, header: list, row: list, field: str):
    if field not in header:
        return None
    idx = header.index(field)
    if len(row) <= idx or row[idx] == "":
        return None
    v = row[idx]
    try:
        fv = float(v)
        if 0 <= fv <= 24:
            return None
        return _violation(user, sheet_row, field, v, "out of range [0,24]")
    except ValueError:
        return _violation(user, sheet_row, field, v, "not float")


def _check_enum(user: str, sheet_row: int, header: list, row: list,
                field: str, allowed: tuple[str, ...]):
    if field not in header:
        return None
    idx = header.index(field)
    if len(row) <= idx:
        return None
    v = row[idx]
    if v == "" or v in allowed:
        return None
    return _violation(user, sheet_row, field, v, f"not in {allowed}")


def _check_time_of_day(user: str, sheet_row: int, header: list, row: list):
    field = "time_of_day"
    if field not in header:
        return (None, None)
    idx = header.index(field)
    if len(row) <= idx:
        return (None, None)
    v = row[idx]
    if v in TIME_OF_DAY_CORRECTIONS:
        return (_correction(user, sheet_row, field, idx, v,
                            TIME_OF_DAY_CORRECTIONS[v]), None)
    if v != "" and v not in ENUM_TIME_OF_DAY:
        return (None, _violation(user, sheet_row, field, v,
                                 f"not in {ENUM_TIME_OF_DAY}"))
    return (None, None)


def _scan_worksheet_for_step02(user: str, rows: list[list[str]]):
    if not rows:
        return [], []
    header = rows[0]
    data = rows[1:]
    violations: list[dict] = []
    corrections: list[dict] = []
    for offset, row in enumerate(data):
        sheet_row = offset + 2
        for f in INT_1_5_FIELDS:
            r = _check_int_1_5(user, sheet_row, header, row, f)
            if r:
                violations.append(r)
        r = _check_float_0_24(user, sheet_row, header, row, "sleep_hours")
        if r:
            violations.append(r)
        r = _check_enum(user, sheet_row, header, row, "weather", ENUM_WEATHER)
        if r:
            violations.append(r)
        corr, viol = _check_time_of_day(user, sheet_row, header, row)
        if corr:
            corrections.append(corr)
        if viol:
            violations.append(viol)
        for f in ("medication", "period"):
            r = _check_enum(user, sheet_row, header, row, f, ("TRUE", "FALSE"))
            if r:
                violations.append(r)
    return violations, corrections


def _write_step02_report(violations: list[dict], corrections: list[dict]) -> Path:
    headers = ["user", "row", "field", "value_before", "value_after", "action", "note"]
    path = OUTPUT_DIR / "report_step02.csv"
    rows: list[list] = []
    for v in violations:
        rows.append([v["user"], v["row"], v["field"], v["value_before"],
                     v.get("value_after", ""), v["action"], v.get("note", "")])
    for c in corrections:
        rows.append([c["user"], c["row"], c["field"], c["value_before"],
                     c["value_after"], c["action"], c.get("note", "")])
    write_csv(path, headers, rows)
    return path


def _print_step02_summary(violations: list[dict], corrections: list[dict],
                          report_path: Path, *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step02_validate_ranges / {mode}]")
    print(f"  violations: {len(violations)}")
    print(f"  corrections: {len(corrections)}")
    for v in violations:
        print(f"  [VIOLATION] {v['user']} row={v['row']} {v['field']}="
              f"'{v['value_before']}' ({v.get('note','')})")
    for c in corrections:
        print(f"  [CORRECTION] {c['user']} row={c['row']} {c['field']}: "
              f"'{c['value_before']}' -> '{c['value_after']}'")
    print(f"  report: {report_path}")


def _apply_step02_corrections(ws, corrections: list[dict]) -> None:
    if not corrections:
        return
    updates = []
    for c in corrections:
        col = col_letter(c["col_idx"])
        cell = f"{col}{c['row']}"
        updates.append({"range": cell, "values": [[c["value_after"]]]})
        print(f"  [APPLY] {cell}: '{c['value_before']}' -> '{c['value_after']}'")
    ws.batch_update(updates)


def step02_validate_ranges(users: tuple[str, ...], *, execute: bool) -> None:
    """値域バリデーション + BLOCKER-3 time_of_day 訂正。"""
    all_violations: list[dict] = []
    all_corrections: list[dict] = []
    ws_cache: dict[str, object] = {}
    for user in users:
        ws = get_worksheet(user)
        ws_cache[user] = ws
        rows = fetch_all_rows(ws)
        v, c = _scan_worksheet_for_step02(user, rows)
        all_violations.extend(v)
        all_corrections.extend(c)
    report_path = _write_step02_report(all_violations, all_corrections)
    _print_step02_summary(all_violations, all_corrections, report_path, execute=execute)
    if not execute:
        return
    for user in users:
        ws_corrs = [c for c in all_corrections if c["user"] == user]
        if ws_corrs:
            _apply_step02_corrections(ws_cache[user], ws_corrs)


# ============================================================================
# ステップ 3: M〜Q 5 列追加
# ============================================================================

def _check_step03_state(user: str, rows: list[list[str]]) -> dict:
    if not rows:
        return {"user": user, "action": "abort_unexpected", "reason": "empty worksheet"}
    header = rows[0]
    if header == list(HEADERS_V12):
        return {"user": user, "action": "skip", "current_cols": len(header)}
    expected_pre_v12 = list(HEADERS_V11) + ["daily_aspects"]
    if header == expected_pre_v12:
        return {"user": user, "action": "add_mq", "current_cols": len(header)}
    return {"user": user, "action": "abort_unexpected",
            "reason": f"header mismatch: {header!r}"}


def _apply_step03(ws, plan: dict) -> None:
    if plan["action"] != "add_mq":
        return
    new_headers = list(HEADERS_V12_ADDITION[1:])
    assert len(new_headers) == 5, "expected 5 headers M-Q"
    if ws.col_count < 17:
        ws.add_cols(17 - ws.col_count)
    ws.batch_update([{"range": "M1:Q1", "values": [new_headers]}])


def _print_step03_summary(plans: list[dict], *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step03_add_columns / {mode}]")
    for plan in plans:
        u = plan["user"]
        if plan["action"] == "skip":
            print(f"  {u}: SKIP (already v12 header, {plan['current_cols']} cols)")
        elif plan["action"] == "add_mq":
            print(f"  {u}: ADD M-Q (5 cols: {HEADERS_V12_ADDITION[1:]}) "
                  f"-> {plan['current_cols']} cols + 5 = 17 cols")
        else:
            print(f"  {u}: ABORT - {plan['reason']}")


def step03_add_columns(users: tuple[str, ...], *, execute: bool) -> None:
    """BLOCKER-1: daily_aspects は L に既存。M〜Q の 5 列のみ追加。"""
    plans: list[dict] = []
    ws_cache: dict[str, object] = {}
    for user in users:
        ws = get_worksheet(user)
        ws_cache[user] = ws
        rows = fetch_all_rows(ws)
        plans.append(_check_step03_state(user, rows))
    _print_step03_summary(plans, execute=execute)
    aborts = [p for p in plans if p["action"] == "abort_unexpected"]
    if aborts:
        raise RuntimeError(f"step03 aborted (unexpected header state): {aborts}")
    if not execute:
        return
    for plan in plans:
        if plan["action"] == "add_mq":
            _apply_step03(ws_cache[plan["user"]], plan)
            print(f"  [APPLIED] {plan['user']}: M-Q headers written")


# ============================================================================
# ディスパッチ（schema ステップ）
# ============================================================================

SCHEMA_STEPS: dict[str, Callable[..., None]] = {
    "1": step01_backup,
    "2": step02_validate_ranges,
    "3": step03_add_columns,
}
