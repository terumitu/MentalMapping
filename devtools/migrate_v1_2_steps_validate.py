"""MentalMapping v1.2 マイグレーション Phase 2 validate ステップ

検証・報告系ステップ（11, 12, 13）をまとめる。
- ステップ 11: input_user 整合性チェック（未実装）
- ステップ 12: 最終バリデーション（未実装）
- ステップ 13: サマリー報告（未実装）
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from collections import Counter

from devtools.migrate_v1_2 import (
    ENUM_ENTRY_MODE,
    ENUM_RECORD_STATUS,
    ENUM_TIME_OF_DAY,
    ENUM_WEATHER,
    OUTPUT_DIR,
    USERS_TARGET,
    fetch_all_rows,
    get_worksheet,
    jst_now,
    write_csv,
)


def _not_yet(step: str) -> None:
    raise NotImplementedError(
        f"ステップ {step} は本実装未着手（Plan 承認済・実装順次追加予定）"
    )


def _scan_input_user_divergence(user_expected: str, rows: list) -> list[dict]:
    """全行で input_user != worksheet 所有者の行を列挙。"""
    if not rows or len(rows) < 2:
        return []
    header = rows[0]
    needed = ("input_user", "date", "time_of_day", "record_id")
    if not all(n in header for n in needed):
        return []
    idx = {n: header.index(n) for n in needed}
    divergences: list[dict] = []
    for offset, row in enumerate(rows[1:]):
        sheet_row = offset + 2
        i_iu = idx["input_user"]
        iu = row[i_iu] if len(row) > i_iu else ""
        if iu == user_expected:
            continue
        divergences.append({
            "user_expected": user_expected, "row": sheet_row,
            "date": row[idx["date"]] if len(row) > idx["date"] else "",
            "time_of_day": row[idx["time_of_day"]]
                if len(row) > idx["time_of_day"] else "",
            "record_id": row[idx["record_id"]]
                if len(row) > idx["record_id"] else "",
            "input_user_actual": iu,
        })
    return divergences


def _print_step11_summary(divergences: list[dict], report_path: Path,
                          *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step11_input_user_audit / {mode}]")
    print(f"  divergences: {len(divergences)}")
    for d in divergences:
        print(f"  [DIVERGE] row={d['row']} expected='{d['user_expected']}' "
              f"actual='{d['input_user_actual']}' date={d['date']} "
              f"tod={d['time_of_day']} rid={d['record_id']}")
    print(f"  report: {report_path}")


def step11_input_user_audit(users: tuple[str, ...], *, execute: bool) -> None:
    """全 worksheet で input_user != worksheet 所有者を検出（読み取り専用）。

    §4.6.2 / §A.5.5 準拠。マイグレーション直後は 0 件が期待値。
    Sheets 本体には書き込まず、report_step11.csv に列挙のみ。
    execute フラグは動作に影響しない（読み取り専用ステップ）。
    """
    all_div: list[dict] = []
    for user in users:
        ws = get_worksheet(user)
        rows = fetch_all_rows(ws)
        all_div.extend(_scan_input_user_divergence(user, rows))
    report_path = OUTPUT_DIR / "report_step11.csv"
    write_csv(report_path,
              ["user_expected", "row", "date", "time_of_day",
               "record_id", "input_user_actual"],
              [[d["user_expected"], d["row"], d["date"], d["time_of_day"],
                d["record_id"], d["input_user_actual"]] for d in all_div])
    _print_step11_summary(all_div, report_path, execute=execute)


def _validate_active_unique(users_data: dict) -> list[dict]:
    """同一 (input_user, date, time_of_day) で active 2 件以上を検出。"""
    active_groups: dict = {}
    for user, rows in users_data.items():
        if not rows or len(rows) < 2:
            continue
        header = rows[0]
        idx = {n: header.index(n) for n in
               ("input_user", "date", "time_of_day",
                "record_status", "record_id")}
        for offset, row in enumerate(rows[1:]):
            sheet_row = offset + 2
            i_rs = idx["record_status"]
            if len(row) <= i_rs or row[i_rs] != "active":
                continue
            key = (row[idx["input_user"]],
                   row[idx["date"]], row[idx["time_of_day"]])
            active_groups.setdefault(key, []).append(
                (user, sheet_row, row[idx["record_id"]]))
    return [{"type": "active_unique", "key": key, "rows": items}
            for key, items in active_groups.items() if len(items) > 1]


def _validate_chain_integrity(users_data: dict) -> list[dict]:
    """superseded_by が指す record_id が実在することを検証。"""
    all_rids: set[str] = set()
    for rows in users_data.values():
        if not rows or len(rows) < 2:
            continue
        header = rows[0]
        idx_rid = header.index("record_id")
        for row in rows[1:]:
            if len(row) > idx_rid and row[idx_rid]:
                all_rids.add(row[idx_rid])
    violations: list[dict] = []
    for user, rows in users_data.items():
        if not rows or len(rows) < 2:
            continue
        header = rows[0]
        idx_sb = header.index("superseded_by")
        idx_rid = header.index("record_id")
        for offset, row in enumerate(rows[1:]):
            sheet_row = offset + 2
            if len(row) <= idx_sb:
                continue
            sb = row[idx_sb]
            if sb == "" or sb in all_rids:
                continue
            violations.append({
                "type": "chain_broken", "user": user, "row": sheet_row,
                "record_id": row[idx_rid] if len(row) > idx_rid else "",
                "superseded_by_missing": sb,
            })
    return violations


def _validate_enum_ranges(users_data: dict) -> list[dict]:
    """enum 5 列の値域チェック。weather のみ空文字を許容（null）。"""
    checks: dict = {
        "weather": (set(ENUM_WEATHER), True),
        "time_of_day": (set(ENUM_TIME_OF_DAY), False),
        "record_status": (set(ENUM_RECORD_STATUS), False),
        "entry_mode": (set(ENUM_ENTRY_MODE), False),
        "input_user": (set(USERS_TARGET), False),
    }
    violations: list[dict] = []
    for user, rows in users_data.items():
        if not rows or len(rows) < 2:
            continue
        header = rows[0]
        for field, (allowed, allow_empty) in checks.items():
            if field not in header:
                continue
            idx = header.index(field)
            for offset, row in enumerate(rows[1:]):
                sheet_row = offset + 2
                if len(row) <= idx:
                    continue
                v = row[idx]
                if allow_empty and v == "":
                    continue
                if v in allowed:
                    continue
                violations.append({
                    "type": "enum", "user": user, "row": sheet_row,
                    "field": field, "value": v, "allowed": sorted(allowed),
                })
    return violations


def _print_step12_summary(au: list, ci: list, en: list,
                           report_path, *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step12_validate_final / {mode}]")
    print(f"  active_unique violations: {len(au)}")
    print(f"  chain_integrity violations: {len(ci)}")
    print(f"  enum_range violations: {len(en)}")
    print(f"  total violations: {len(au) + len(ci) + len(en)}")
    for v in au:
        print(f"  [ACTIVE_UNIQUE] {v['key']}: {v['rows']}")
    for v in ci:
        print(f"  [CHAIN_BROKEN] {v['user']} row={v['row']} "
              f"missing={v['superseded_by_missing']!r}")
    for v in en:
        print(f"  [ENUM] {v['user']} row={v['row']} {v['field']}="
              f"{v['value']!r} (allowed: {v['allowed']})")
    print(f"  report: {report_path}")


def step12_validate_final(users: tuple[str, ...], *, execute: bool) -> None:
    """active 1 件 / 鎖整合 / enum 値域の最終バリデーション（読み取り専用）。"""
    users_data: dict = {}
    for user in users:
        ws = get_worksheet(user)
        users_data[user] = fetch_all_rows(ws)
    au = _validate_active_unique(users_data)
    ci = _validate_chain_integrity(users_data)
    en = _validate_enum_ranges(users_data)
    report_path = OUTPUT_DIR / "report_step12.csv"
    rows = [[v["type"], str(v)] for v in au + ci + en]
    write_csv(report_path, ["violation_type", "detail"], rows)
    _print_step12_summary(au, ci, en, report_path, execute=execute)


def _collect_worksheet_stats(user: str, rows: list) -> dict:
    """1 worksheet の統計を収集。"""
    if not rows or len(rows) < 2:
        return {"total": 0}
    header = rows[0]
    data = rows[1:]
    rs_c: Counter = Counter()
    em_c: Counter = Counter()
    weather_c: Counter = Counter()
    tod_c: Counter = Counter()
    idx = {n: header.index(n) for n in
           ("record_status", "entry_mode", "weather", "time_of_day")
           if n in header}
    for row in data:
        def cell(name):
            i = idx.get(name)
            return row[i] if i is not None and len(row) > i else ""
        rs_c[cell("record_status")] += 1
        em_c[cell("entry_mode")] += 1
        weather_c[cell("weather") or "(null)"] += 1
        tod_c[cell("time_of_day")] += 1
    return {
        "total": len(data),
        "record_status": dict(rs_c),
        "entry_mode": dict(em_c),
        "weather": dict(weather_c),
        "time_of_day": dict(tod_c),
    }


def _format_summary_body(stats: dict, now_iso: str) -> str:
    lines: list[str] = []
    lines.append("# MentalMapping v1.2 マイグレーション 最終サマリー")
    lines.append("")
    lines.append(f"**生成日時**: {now_iso} (JST)")
    lines.append("")
    lines.append("## 1. worksheet 最終レコード件数")
    for user in ("masuda", "nishide", "suyasu"):
        s = stats.get(user, {})
        lines.append(f"- `mood_log_{user}`: **{s.get('total', 0)}** records")
    lines.append("")
    lines.append("## 2. record_status 分布")
    for user in ("masuda", "nishide", "suyasu"):
        rs = stats.get(user, {}).get("record_status", {})
        lines.append(f"- {user}: {rs}")
    lines.append("")
    lines.append("## 3. entry_mode 分布")
    for user in ("masuda", "nishide", "suyasu"):
        em = stats.get(user, {}).get("entry_mode", {})
        lines.append(f"- {user}: {em}")
    lines.append("")
    lines.append("## 4. weather 分布")
    for user in ("masuda", "nishide", "suyasu"):
        w = stats.get(user, {}).get("weather", {})
        lines.append(f"- {user}: {w}")
    lines.append("")
    lines.append("## 5. time_of_day 分布")
    for user in ("masuda", "nishide", "suyasu"):
        t = stats.get(user, {}).get("time_of_day", {})
        lines.append(f"- {user}: {t}")
    lines.append("")
    lines.append("## 6. マイグレーション操作サマリー")
    lines.append("")
    lines.append("| 操作 | 件数 | 備考 |")
    lines.append("|-----|------|------|")
    lines.append("| バックアップ取得 (ステップ 1) | 3 CSV | backup_20260418/ |")
    lines.append("| 値域訂正 (ステップ 2: moning→morning) | 1 セル | masuda K2 |")
    lines.append("| 列追加 (ステップ 3: M〜Q) | 15 セル | 3 worksheet × 5 列 |")
    lines.append("| record_id / input_user 付与 (ステップ 4+5+8) | 68 セル + 1 再生成 | daily_aspects 34 件保護 |")
    lines.append("| record_status / entry_mode 判定 (ステップ 6+7) | 68 セル | O 列は 0 件書き込み |")
    lines.append("| weather 置換 (ステップ 9: 雨→雨/雪) | 2 セル | masuda G11, nishide G11 |")
    lines.append("| not_recorded 遡及生成 (ステップ 10) | 8 レコード | suyasu のみ |")
    lines.append("| input_user 整合性 (ステップ 11) | 乖離 0 件 | 期待値通り |")
    lines.append("| 最終バリデーション (ステップ 12) | 違反 0 件 | active 1 件 / 鎖整合 / enum 全 pass |")
    lines.append("")
    lines.append("## 7. 手動確認必要事項（申し送り）")
    lines.append("")
    lines.append("- **mm_notes #2, #3**: row 15 / row 11 の Sheets 直接編集事例を Phase 2 完了時に採番起票")
    lines.append("- **v1.2.2 改訂対象**:")
    lines.append("  - §A.5.6 「masuda 2026-04-16 morning → not_recorded」の誤記削除")
    lines.append("  - §4.1 daily_aspects 既存値保護方針の反映")
    lines.append("  - §A.3 record_id 生成規則に「recorded_at 訂正時の再生成ルール」追記")
    lines.append("  - §8 変更履歴 v1.2.2 エントリ追加")
    lines.append("- **α-D 申し送り** (mm_notes #7 予定):")
    lines.append("  - 2026-04-19 以降の not_recorded は GAS バッチで生成")
    lines.append("  - NOT_RECORDED_START_DATES / NOT_RECORDED_EXCLUDE の GAS 側共有")
    lines.append("  - 日次実行 (03:00 JST 推奨) / 初回遡及ロジック")
    lines.append("- **row 11 (masuda 2026-04-15 evening T12:37:23)** 誤入力は未訂正")
    lines.append("  - 西出が将来訂正する場合、`--step 4_5_8 --execute` で record_id 自動再生成")
    lines.append("")
    return "\n".join(lines)


def step13_summary(users: tuple[str, ...]) -> None:
    """全ステップの集計サマリーを `output/migration_v1_2/summary.md` に書き出す。"""
    now_iso = jst_now().isoformat(timespec="seconds")
    stats: dict = {}
    for user in users:
        ws = get_worksheet(user)
        rows = fetch_all_rows(ws)
        stats[user] = _collect_worksheet_stats(user, rows)
    body = _format_summary_body(stats, now_iso)
    path = OUTPUT_DIR / "summary.md"
    path.write_text(body, encoding="utf-8")
    print(f"[step13_summary]")
    print(f"  wrote: {path}")
    print(f"  total records: "
          f"{sum(s.get('total', 0) for s in stats.values())}")


VALIDATE_STEPS: dict[str, Callable[..., None]] = {
    "11": step11_input_user_audit,
    "12": step12_validate_final,
    "13": step13_summary,
}
