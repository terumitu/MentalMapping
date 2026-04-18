"""MentalMapping v1.2 マイグレーション Phase 2 populate ステップ

値付与系ステップ（4+5+8, 6+7, 9, 10）をまとめる。
- ステップ 4+5+8: record_id / input_user / daily_aspects 機械的付与
- ステップ 6+7: record_status / entry_mode 判定（未実装）
- ステップ 9: weather 雨 → 雨/雪 置換（未実装）
- ステップ 10: not_recorded 遡及生成（未実装）
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Callable

from devtools.migrate_v1_2 import (
    OUTPUT_DIR,
    col_letter,
    fetch_all_rows,
    get_worksheet,
    jst_now,
    make_record_id,
    parse_iso_jst,
    unix_ts_of,
    within_realtime_window,
    write_csv,
)
from modules.sheet_client import load_settings

# BLOCKER-4 関連: not_recorded 遡及生成の起点日（§A.5.6）。
# pending とは独立。realtime_window 未定義ユーザー (suyasu) も not_recorded 対象。
NOT_RECORDED_START_DATES: dict[str, date] = {
    "masuda": date(2026, 4, 11),
    "nishide": date(2026, 4, 11),
    "suyasu": date(2026, 4, 14),
}

# §A.5.6 誤記訂正 (v1.2.2 対象): masuda 2026-04-16 morning は実データに存在するため
# not_recorded 対象から除外する。ステップ 10 実装時にハードコード除外。
NOT_RECORDED_EXCLUDE: set[tuple[str, str, str]] = {
    ("masuda", "2026-04-16", "morning"),
}

# α-C スコープ外の本日分は α-D GAS バッチに委譲するため、"本日" を固定。
# 2026-04-19 は end_exclusive（= 04-18 までを遡及対象とする）。
# 再実行時も挙動を保持（時刻依存なし）。
MIGRATION_TODAY: date = date(2026, 4, 19)


def _not_yet(step: str) -> None:
    raise NotImplementedError(
        f"ステップ {step} は本実装未着手（Plan 承認済・実装順次追加予定）"
    )


# ============================================================================
# ステップ 4+5+8: record_id / input_user / daily_aspects 付与
# ============================================================================

def _plan_bulk_row(user: str, row: list, sheet_row: int, ci: dict) -> tuple[list, list]:
    """1 行分の (updates, actions) を返す。

    - M (record_id):
        - 空 → 書き込み（write）
        - 非空かつ現 recorded_at 由来値と一致 → skip
        - 非空かつ不一致（recorded_at 訂正後など）→ regenerate（再生成・更新）
    - Q (input_user): 空なら worksheet 所有者、非空なら skip
    - L (daily_aspects): BLOCKER-1 により既存値は保護、空は no-op
    """
    updates: list = []
    actions: list = []
    m = ci["record_id"]
    uts = unix_ts_of(row[ci["recorded_at"]])
    expected_rid = make_record_id(
        user, row[ci["date"]], row[ci["time_of_day"]], uts)
    current_rid = row[m] if len(row) > m else ""
    if current_rid == "":
        updates.append({"range": f"M{sheet_row}", "values": [[expected_rid]]})
        actions.append(("record_id", "write"))
    elif current_rid != expected_rid:
        updates.append({"range": f"M{sheet_row}", "values": [[expected_rid]]})
        actions.append(("record_id", "regenerate"))
    else:
        actions.append(("record_id", "skip"))
    q = ci["input_user"]
    if len(row) <= q or row[q] == "":
        updates.append({"range": f"Q{sheet_row}", "values": [[user]]})
        actions.append(("input_user", "write"))
    else:
        actions.append(("input_user", "skip"))
    la = ci["daily_aspects"]
    if len(row) > la and row[la] != "":
        actions.append(("daily_aspects", "preserve_existing"))
    else:
        actions.append(("daily_aspects", "empty_no_write"))
    return updates, actions


def _plan_step04_05_08(user: str, rows: list) -> tuple[list, list]:
    if not rows:
        return [], []
    header = rows[0]
    ci = {n: header.index(n) for n in
          ("date", "recorded_at", "time_of_day",
           "daily_aspects", "record_id", "input_user")}
    all_updates: list = []
    all_actions: list = []
    for offset, row in enumerate(rows[1:]):
        u, a = _plan_bulk_row(user, row, offset + 2, ci)
        all_updates.extend(u)
        all_actions.extend([(user, col, st) for col, st in a])
    return all_updates, all_actions


def _print_step04_05_08_summary(actions: list, updates_by_user: dict,
                                 *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step04_05_08_bulk / {mode}]")
    c = Counter(actions)
    for (u, col, st), n in sorted(c.items()):
        print(f"  {u}/{col}/{st}: {n}")
    total = sum(len(v) for v in updates_by_user.values())
    print(f"  total write cells: {total}")


def step04_05_08_bulk(users: tuple[str, ...], *, execute: bool) -> None:
    """record_id / input_user / daily_aspects の機械的付与（束）。"""
    all_updates: dict = {}
    all_actions: list = []
    ws_cache: dict = {}
    for user in users:
        ws = get_worksheet(user)
        ws_cache[user] = ws
        rows = fetch_all_rows(ws)
        ups, acts = _plan_step04_05_08(user, rows)
        all_updates[user] = ups
        all_actions.extend(acts)
    _print_step04_05_08_summary(all_actions, all_updates, execute=execute)
    if not execute:
        return
    for user, updates in all_updates.items():
        if updates:
            ws_cache[user].batch_update(updates)
            print(f"  [APPLIED] {user}: {len(updates)} cells")


# ============================================================================
# ステップ 6+7 / 9 / 10: 未実装スタブ
# ============================================================================

def _build_groups(rows: list[list[str]]) -> dict[tuple[str, str], list[tuple]]:
    """(date, time_of_day) ごとにグループ化。戻り値は各グループ内が
    recorded_at 昇順でソート済みのタプル列 (sheet_row, rec_dt, record_id)。"""
    if not rows:
        return {}
    header = rows[0]
    idx_d = header.index("date")
    idx_t = header.index("time_of_day")
    idx_r = header.index("recorded_at")
    idx_id = header.index("record_id")
    groups: dict[tuple[str, str], list[tuple]] = {}
    for offset, row in enumerate(rows[1:]):
        sheet_row = offset + 2
        key = (row[idx_d], row[idx_t])
        rec_dt = parse_iso_jst(row[idx_r])
        rid = row[idx_id] if len(row) > idx_id else ""
        groups.setdefault(key, []).append((sheet_row, rec_dt, rid))
    for key in groups:
        groups[key].sort(key=lambda x: x[1])
    return groups


def _assign_record_status(groups: dict) -> dict[int, tuple[str, str]]:
    """sheet_row -> (record_status, superseded_by) を返す。

    §A.5.4 準拠: グループ内 recorded_at 最新を active、
    それ以外を superseded（鎖構築: 古いレコードの superseded_by = 次レコードの record_id）。
    """
    assignments: dict[int, tuple[str, str]] = {}
    for key, members in groups.items():
        if len(members) == 1:
            sheet_row, _, _ = members[0]
            assignments[sheet_row] = ("active", "")
            continue
        for i, (sheet_row, _, _) in enumerate(members):
            if i == len(members) - 1:
                assignments[sheet_row] = ("active", "")
            else:
                next_rid = members[i + 1][2]
                assignments[sheet_row] = ("superseded", next_rid)
    return assignments


def _resolve_entry_mode(user: str, tod: str, rec_dt, settings: dict) -> str:
    """1 行分の entry_mode を決定。

    - users[user].{morning,evening}_realtime_window 未定義 → 'pending' (BLOCKER-4)
    - 定義済: [start, end) 半開区間内なら 'realtime'、外なら 'retroactive'
    """
    user_cfg = settings.get("users", {}).get(user, {})
    win_key = f"{tod}_realtime_window"
    win = user_cfg.get(win_key)
    if not win:
        return "pending"
    if within_realtime_window(rec_dt.time(), tuple(win)):
        return "realtime"
    return "retroactive"


def _assign_entry_mode(user: str, rows: list, settings: dict) -> dict[int, str]:
    """sheet_row -> entry_mode の辞書を返す。"""
    if not rows:
        return {}
    header = rows[0]
    idx_t = header.index("time_of_day")
    idx_r = header.index("recorded_at")
    result: dict[int, str] = {}
    for offset, row in enumerate(rows[1:]):
        sheet_row = offset + 2
        tod = row[idx_t]
        rec_dt = parse_iso_jst(row[idx_r])
        result[sheet_row] = _resolve_entry_mode(user, tod, rec_dt, settings)
    return result


def _build_step06_07_updates(rows: list, rs_map: dict,
                              em_map: dict) -> list[dict]:
    """N/O/P 列について現在値と判定値が異なる場合のみ update を出力（冪等）。"""
    if not rows:
        return []
    header = rows[0]
    idx_rs = header.index("record_status")
    idx_sb = header.index("superseded_by")
    idx_em = header.index("entry_mode")
    updates: list[dict] = []
    for offset, row in enumerate(rows[1:]):
        sheet_row = offset + 2
        cur_rs = row[idx_rs] if len(row) > idx_rs else ""
        cur_sb = row[idx_sb] if len(row) > idx_sb else ""
        cur_em = row[idx_em] if len(row) > idx_em else ""
        new_rs, new_sb = rs_map[sheet_row]
        new_em = em_map[sheet_row]
        if cur_rs != new_rs:
            updates.append({"range": f"N{sheet_row}", "values": [[new_rs]]})
        if cur_sb != new_sb:
            updates.append({"range": f"O{sheet_row}", "values": [[new_sb]]})
        if cur_em != new_em:
            updates.append({"range": f"P{sheet_row}", "values": [[new_em]]})
    return updates


def _collect_step06_07_detail(user: str, rows: list, rs_map: dict,
                               em_map: dict, groups: dict) -> list[list]:
    """report_step06_07.csv 用の詳細行を構築。"""
    if not rows:
        return []
    header = rows[0]
    idx_d = header.index("date")
    idx_t = header.index("time_of_day")
    idx_r = header.index("recorded_at")
    gsize = {k: len(v) for k, v in groups.items()}
    out: list[list] = []
    for offset, row in enumerate(rows[1:]):
        sheet_row = offset + 2
        d, t = row[idx_d], row[idx_t]
        rec = row[idx_r]
        rs, sb = rs_map[sheet_row]
        em = em_map[sheet_row]
        out.append([user, sheet_row, d, t, rec, rs, sb, em, gsize.get((d, t), 1)])
    return out


def _print_step06_07_summary(results_by_user: dict, settings: dict,
                              *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step06_07_judge / {mode}]")
    print("(A) record_status:")
    for user, d in results_by_user.items():
        rs_c = Counter(rs for rs, _ in d["rs_map"].values())
        chains = sum(1 for rs, _ in d["rs_map"].values() if rs == "superseded")
        print(f"  {user}: active={rs_c.get('active',0)} "
              f"superseded={rs_c.get('superseded',0)} (chain nodes: {chains})")
    print("(C) entry_mode:")
    for user, d in results_by_user.items():
        em_c = Counter(d["em_map"].values())
        print(f"  {user}: realtime={em_c.get('realtime',0)} "
              f"retroactive={em_c.get('retroactive',0)} "
              f"pending={em_c.get('pending',0)}")
    _print_step06_07_nishide_note(settings)
    _print_step06_07_suyasu_detail(results_by_user.get("suyasu"))


def _print_step06_07_nishide_note(settings: dict) -> None:
    has_nishide_win = "morning_realtime_window" in settings.get(
        "users", {}).get("nishide", {})
    print("(B) nishide time_of_day 遡及確認（§A.5.4-4）:")
    if has_nishide_win:
        print("  全件 '自動判定結果として遡及付与' 扱い（手動変更の履歴確認不可・保守的処理）")
    else:
        print("  nishide realtime_window 未定義のためスキップ")


def _print_step06_07_suyasu_detail(suyasu_data) -> None:
    print("(D) suyasu pending 付与詳細:")
    if not suyasu_data:
        print("  suyasu 対象なし")
        return
    for sheet_row, em in sorted(suyasu_data["em_map"].items()):
        print(f"  row {sheet_row}: entry_mode={em}")


def step06_07_judge(users: tuple[str, ...], *, execute: bool) -> None:
    """ステップ 6+7: record_status + entry_mode 判定（§A.5.4 / BLOCKER-4）。"""
    settings = load_settings()
    results_by_user: dict[str, dict] = {}
    detail_rows: list[list] = []
    ws_cache: dict = {}
    for user in users:
        ws = get_worksheet(user)
        ws_cache[user] = ws
        rows = fetch_all_rows(ws)
        groups = _build_groups(rows)
        rs_map = _assign_record_status(groups)
        em_map = _assign_entry_mode(user, rows, settings)
        updates = _build_step06_07_updates(rows, rs_map, em_map)
        detail_rows.extend(
            _collect_step06_07_detail(user, rows, rs_map, em_map, groups))
        results_by_user[user] = {"rs_map": rs_map, "em_map": em_map,
                                  "updates": updates, "rows": rows}
    report_path = OUTPUT_DIR / "report_step06_07.csv"
    write_csv(report_path,
              ["user", "row", "date", "time_of_day", "recorded_at",
               "record_status", "superseded_by", "entry_mode", "group_size"],
              detail_rows)
    _print_step06_07_summary(results_by_user, settings, execute=execute)
    print(f"  report: {report_path}")
    if not execute:
        return
    for user, d in results_by_user.items():
        if d["updates"]:
            ws_cache[user].batch_update(d["updates"])
            print(f"  [APPLIED] {user}: {len(d['updates'])} cells")


def _scan_rain_targets(user: str, rows: list) -> list[dict]:
    """weather == "雨" (厳密一致) のセルを列挙。"""
    if not rows:
        return []
    header = rows[0]
    idx_w = header.index("weather")
    idx_d = header.index("date")
    idx_t = header.index("time_of_day")
    col = col_letter(idx_w)
    targets: list[dict] = []
    for offset, row in enumerate(rows[1:]):
        sheet_row = offset + 2
        if len(row) <= idx_w:
            continue
        if row[idx_w] == "雨":
            targets.append({
                "user": user, "row": sheet_row,
                "date": row[idx_d], "time_of_day": row[idx_t],
                "col_letter": col,
                "value_before": "雨", "value_after": "雨/雪",
            })
    return targets


def _print_step09_summary(targets: list[dict], *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step09_weather_rain / {mode}]")
    print(f"  targets (weather == '雨'): {len(targets)}")
    for t in targets:
        print(f"  - {t['user']} row={t['row']} ({t['date']} {t['time_of_day']}): "
              f"'{t['value_before']}' -> '{t['value_after']}'")


def step09_weather_rain(users: tuple[str, ...], *, execute: bool) -> None:
    """ステップ 9: weather == '雨' を '雨/雪' に冪等置換（§A.5.1）。"""
    all_targets: list[dict] = []
    ws_cache: dict = {}
    for user in users:
        ws = get_worksheet(user)
        ws_cache[user] = ws
        rows = fetch_all_rows(ws)
        all_targets.extend(_scan_rain_targets(user, rows))
    _print_step09_summary(all_targets, execute=execute)
    if not execute:
        return
    for user in users:
        user_targets = [t for t in all_targets if t["user"] == user]
        if not user_targets:
            continue
        updates = [
            {"range": f"{t['col_letter']}{t['row']}",
             "values": [[t["value_after"]]]}
            for t in user_targets
        ]
        ws_cache[user].batch_update(updates)
        print(f"  [APPLIED] {user}: {len(updates)} cells")


def _scan_not_recorded_gaps(user: str, ws) -> list[tuple[str, str, str]]:
    """start_date〜MIGRATION_TODAY-1 で既存なし・除外外の (user, date, tod) 組を列挙。"""
    start = NOT_RECORDED_START_DATES.get(user)
    if not start:
        return []
    rows = fetch_all_rows(ws)
    existing: set[tuple[str, str]] = set()
    if rows and len(rows) > 1:
        header = rows[0]
        idx_d = header.index("date")
        idx_t = header.index("time_of_day")
        for row in rows[1:]:
            if len(row) > max(idx_d, idx_t):
                existing.add((row[idx_d], row[idx_t]))
    gaps: list[tuple[str, str, str]] = []
    d = start
    while d < MIGRATION_TODAY:
        for tod in ("morning", "evening"):
            dstr = d.isoformat()
            if (dstr, tod) in existing:
                continue
            if (user, dstr, tod) in NOT_RECORDED_EXCLUDE:
                continue
            gaps.append((user, dstr, tod))
        d += timedelta(days=1)
    return gaps


def _build_not_recorded_row(user: str, date_str: str, tod: str,
                             recorded_at_iso: str, unix_ts: int) -> list:
    """§4.3.2 表に従い 17 列 v1.2 行を構築。null 値は空文字列。"""
    rid = make_record_id(user, date_str, tod, unix_ts)
    return [
        date_str, "", "", "", "", "", "", "", "",
        recorded_at_iso, tod, "", rid, "active", "", "not_recorded", user,
    ]


def _print_step10_summary(gaps: list, now_iso: str, *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[step10_not_recorded / {mode}]")
    print(f"  MIGRATION_TODAY (exclusive): {MIGRATION_TODAY.isoformat()}")
    print(f"  recorded_at (batch): {now_iso}")
    print(f"  gaps to generate: {len(gaps)}")
    by_user: dict[str, list] = {}
    for u, d, t in gaps:
        by_user.setdefault(u, []).append((d, t))
    for u in ("masuda", "nishide", "suyasu"):
        ug = by_user.get(u, [])
        print(f"  {u}: {len(ug)} gaps")
        for d, t in ug:
            print(f"    - {d} {t}")
    print(f"  §A.5.6 exclude applied: {sorted(NOT_RECORDED_EXCLUDE)}")


def step10_not_recorded(users: tuple[str, ...], *, execute: bool) -> None:
    """欠損 (user, date, tod) に not_recorded を遡及生成（§A.5.6 / BLOCKER-4）。"""
    now = jst_now()
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
    unix_ts = int(now.timestamp())
    all_gaps: list[tuple[str, str, str]] = []
    ws_cache: dict = {}
    for user in users:
        ws = get_worksheet(user)
        ws_cache[user] = ws
        all_gaps.extend(_scan_not_recorded_gaps(user, ws))
    _print_step10_summary(all_gaps, now_iso, execute=execute)
    if not execute:
        return
    for user in users:
        user_gaps = [g for g in all_gaps if g[0] == user]
        if not user_gaps:
            continue
        new_rows = [
            _build_not_recorded_row(u, d, t, now_iso, unix_ts)
            for (u, d, t) in user_gaps
        ]
        ws_cache[user].append_rows(new_rows, value_input_option="RAW")
        print(f"  [APPLIED] {user}: {len(new_rows)} rows appended")


# ============================================================================
# ディスパッチ（populate ステップ）
# ============================================================================

POPULATE_STEPS: dict[str, Callable[..., None]] = {
    "4_5_8": step04_05_08_bulk,
    "6_7": step06_07_judge,
    "9": step09_weather_rain,
    "10": step10_not_recorded,
}
