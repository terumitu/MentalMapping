"""MentalMapping Phase 1 v1.2 — Streamlit エントリーポイント (17 列・ラジオ申告仕様)。

スマホ縦画面・30 秒以内入力を設計原則とする気分記録 UI。2 タブ構成
「記録する」/「見る」。記録時は time_of_day をラジオで主観申告し
(§4.2)、input_user を毎回明示選択する (§A.6.2)。

同一 (input_user, date, time_of_day) に既存 active がある場合は
@st.dialog の 3 択モーダルで: 上書き / 試行として残す / キャンセル。

保存先 Worksheet は sheet_client.resolve_sheet_name(input_user) で解決し、
entry_mode は modules.entry_mode.determine_entry_mode で realtime_window
判定する。鎖更新は modules.record_chain 経由。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

import streamlit as st

from modules import chart_builder, discord_notifier
from modules.entry_mode import determine_entry_mode
from modules.log_reader import LogReader
from modules.log_writer import LogWriter, MoodLogEntry
from modules.record_chain import (
    find_active_record,
    generate_record_id,
    supersede_active,
)
from modules.sheet_client import connect_worksheet, load_settings, resolve_sheet_name

MOOD_LEGEND = "1=消えたい　2=辛い　3=普通　4=良い　5=最高"
ENERGY_LEGEND = "1=起き上がれない　2=重い　3=やればできる　4=動ける　5=やる気がある"
THINKING_LEGEND = "1=頭が動かない　2=遅い・詰まる　3=考えられる　4=クリア　5=冴えている"
FOCUS_LEGEND = "1=何も手につかない　2=すぐ散漫　3=短時間なら可　4=集中できる　5=没頭できた"

WEATHER_OPTIONS = ("晴", "曇", "雨/雪")
TOD_LABEL_MORNING = "起き抜け"
TOD_LABEL_EVENING = "夜落ち着いた時"
TOD_LABEL_TO_DB = {TOD_LABEL_MORNING: "morning", TOD_LABEL_EVENING: "evening"}

JST = ZoneInfo("Asia/Tokyo")


@st.cache_resource(show_spinner=False)
def _get_worksheet(sheet_name: str) -> Any:
    return connect_worksheet(sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def _get_settings() -> Dict[str, Any]:
    return load_settings()


def _get_writer(sheet_name: str) -> LogWriter:
    return LogWriter(_get_worksheet(sheet_name))


def _get_reader(sheet_name: str) -> LogReader:
    return LogReader(_get_worksheet(sheet_name))


def _render_user_sidebar() -> str | None:
    """サイドバーで input_user を毎回明示選択させる (§A.6.2)。

    default_user を初期候補として使うが、選択された user を強調表示する。
    users が未定義の場合は None を返し、resolve_sheet_name の legacy
    フォールバックに処理を委ねる。
    """
    settings = _get_settings()
    users = settings.get("users") or {}
    if not users:
        return None
    st.sidebar.markdown("### 記録者を選択")
    st.sidebar.caption("⚠️ 毎回明示的に選択してください")
    keys = list(users.keys())
    labels = [str(users[k].get("display_name", k)) for k in keys]
    default_key = settings.get("default_user") or keys[0]
    default_idx = keys.index(default_key) if default_key in keys else 0
    selected_label = st.sidebar.selectbox(
        "記録者",
        options=labels,
        index=default_idx,
        key="user_selector",
    )
    user_key = keys[labels.index(selected_label)]
    st.sidebar.success(f"✅ 現在の記録者: **{selected_label}** ({user_key})")
    return user_key


def _score_radio(title: str, legend: str, key: str) -> int:
    """1-5 スコア選択 UI (タイトル + ラベル凡例 + 横並びラジオ)。"""
    st.markdown(f"**{title}**")
    st.caption(legend)
    return int(
        st.radio(
            title,
            options=[1, 2, 3, 4, 5],
            index=2,
            horizontal=True,
            key=key,
            label_visibility="collapsed",
        )
    )


def _time_of_day_radio() -> str | None:
    """time_of_day ラジオ (§A.6.1): index=None / DB 値を返す。"""
    label = st.radio(
        "いつの状態を記録しますか？",
        options=[TOD_LABEL_MORNING, TOD_LABEL_EVENING],
        index=None,
        horizontal=True,
        key="time_of_day_label",
        help="選択するまで「記録する」ボタンは無効です。",
    )
    return TOD_LABEL_TO_DB.get(label) if label else None


def _build_entry_context(
    *,
    input_user: str,
    sheet_name: str,
    time_of_day: str,
    mood: int,
    energy: int,
    thinking: int,
    focus: int,
    sleep_hours: float,
    weather: str,
    medication: bool,
    period: bool,
) -> Dict[str, Any]:
    """記録値を dict にまとめる (pending_entry / 再処理用)。"""
    recorded_at_dt = datetime.now(tz=JST)
    settings = _get_settings()
    record_id = generate_record_id(input_user, recorded_at_dt.strftime("%Y-%m-%d"),
                                   time_of_day, recorded_at_dt)
    entry_mode = determine_entry_mode(
        input_user, time_of_day, recorded_at_dt, settings.get("users") or {}
    )
    return {
        "input_user": input_user,
        "sheet_name": sheet_name,
        "date": recorded_at_dt.strftime("%Y-%m-%d"),
        "recorded_at": recorded_at_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "record_id": record_id,
        "entry_mode": entry_mode,
        "time_of_day": time_of_day,
        "mood": mood, "energy": energy, "thinking": thinking, "focus": focus,
        "sleep_hours": sleep_hours,
        "weather": weather,
        "medication": medication,
        "period": period,
    }


def _build_entry(ctx: Dict[str, Any], *, record_status: str,
                 superseded_by: str | None) -> MoodLogEntry:
    return MoodLogEntry.create(
        date=ctx["date"],
        mood=ctx["mood"], energy=ctx["energy"],
        thinking=ctx["thinking"], focus=ctx["focus"],
        time_of_day=ctx["time_of_day"],
        input_user=ctx["input_user"],
        record_id=ctx["record_id"],
        entry_mode=ctx["entry_mode"],
        sleep_hours=ctx["sleep_hours"],
        weather=ctx["weather"],
        medication=ctx["medication"],
        period=ctx["period"],
        recorded_at=ctx["recorded_at"],
        record_status=record_status,
        superseded_by=superseded_by,
    )


def _write_new_active(ctx: Dict[str, Any]) -> None:
    entry = _build_entry(ctx, record_status="active", superseded_by=None)
    _get_writer(ctx["sheet_name"]).append(entry)


def _overwrite_with_chain(ctx: Dict[str, Any], old_row: int) -> None:
    """R_new を active で append → 旧 active を superseded 化 (§A.4 順序)。"""
    _write_new_active(ctx)
    supersede_active(_get_worksheet(ctx["sheet_name"]), old_row, ctx["record_id"])


def _append_as_rejected(ctx: Dict[str, Any]) -> None:
    """新レコードを superseded, superseded_by=null で追記 (§A.6.3 維持オプション)。"""
    entry = _build_entry(ctx, record_status="superseded", superseded_by=None)
    _get_writer(ctx["sheet_name"]).append(entry)


@st.dialog("既存記録の訂正")
def _correction_dialog() -> None:
    pending = st.session_state.get("pending_entry")
    if pending is None:
        st.error("pending_entry が存在しません。")
        return
    tod_ja = "起き抜け" if pending["time_of_day"] == "morning" else "夜落ち着いた時"
    st.write(f"既に **{pending['date']} {tod_ja}** の記録があります。どうしますか?")
    st.caption("• 上書き: 既存を superseded にして新しい記録を active にします。")
    st.caption("• 試行として残す: 既存は維持し、新しい記録を superseded_by=null で保存します。")
    st.caption("• キャンセル: 何もしません。入力値は次の記録ボタン押下まで保持されます。")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("上書き", use_container_width=True, type="primary",
                     key="dlg_overwrite"):
            st.session_state["correction_action"] = "overwrite"
            st.rerun()
    with col2:
        if st.button("試行として残す", use_container_width=True, key="dlg_reject"):
            st.session_state["correction_action"] = "reject"
            st.rerun()
    with col3:
        if st.button("キャンセル", use_container_width=True, key="dlg_cancel"):
            st.session_state["correction_action"] = "cancel"
            st.rerun()


def _consume_correction_action(sheet_name: str) -> None:
    """直前の dialog 選択を消費して鎖更新 / 維持追記 / キャンセル処理。"""
    action = st.session_state.pop("correction_action", None)
    if action is None:
        return
    ctx = st.session_state.get("pending_entry")
    old_row = st.session_state.get("pending_existing_row")
    if action == "overwrite":
        if ctx is None or old_row is None:
            st.error("pending 情報が欠落しています。再度入力してください。")
        else:
            try:
                _overwrite_with_chain(ctx, old_row)
                st.success("訂正を反映しました (既存を superseded 化)")
                discord_notifier.send(sheet_name)
            except Exception as e:  # noqa: BLE001
                st.error(f"訂正に失敗しました: {type(e).__name__}: {e}")
        st.session_state.pop("pending_entry", None)
        st.session_state.pop("pending_existing_row", None)
    elif action == "reject":
        if ctx is None:
            st.error("pending 情報が欠落しています。")
        else:
            try:
                _append_as_rejected(ctx)
                st.success("訂正試行として追記しました (既存は維持)")
            except Exception as e:  # noqa: BLE001
                st.error(f"追記に失敗しました: {type(e).__name__}: {e}")
        st.session_state.pop("pending_entry", None)
        st.session_state.pop("pending_existing_row", None)
    elif action == "cancel":
        st.info("キャンセルしました。入力値は保持しています。")


def _handle_integrity_ack(sheet_name: str) -> None:
    """input_user 不一致警告の続行 / キャンセル処理 (§4.6.2 A)。"""
    if not st.session_state.get("needs_integrity_ack"):
        return
    pending = st.session_state.get("pending_entry", {})
    settings = _get_settings()
    try:
        expected_sheet = resolve_sheet_name(settings, pending.get("input_user"))
    except ValueError:
        expected_sheet = "(未解決)"
    st.error(
        f"⚠️ 整合性警告: input_user=**{pending.get('input_user')}** に期待される "
        f"worksheet は **{expected_sheet}** ですが、現在 "
        f"**{sheet_name}** に書き込もうとしています。"
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("続行して記録する", use_container_width=True, type="primary",
                     key="integrity_continue"):
            st.session_state["needs_integrity_ack"] = False
            _proceed_after_integrity(sheet_name)
            st.rerun()
    with col2:
        if st.button("キャンセル", use_container_width=True, key="integrity_cancel"):
            st.session_state["needs_integrity_ack"] = False
            st.session_state.pop("pending_entry", None)
            st.rerun()


def _proceed_after_integrity(sheet_name: str) -> None:
    """整合性チェック通過後: 既存 active 有無で write or dialog 分岐。"""
    ctx = st.session_state.get("pending_entry")
    if ctx is None:
        return
    ws = _get_worksheet(sheet_name)
    existing = find_active_record(
        ws, ctx["input_user"], ctx["date"], ctx["time_of_day"]
    )
    if existing is None:
        try:
            _write_new_active(ctx)
            st.success("記録しました")
            discord_notifier.send(sheet_name)
        except Exception as e:  # noqa: BLE001
            st.error(f"記録に失敗しました: {type(e).__name__}: {e}")
        st.session_state.pop("pending_entry", None)
    else:
        st.session_state["pending_existing_row"] = existing[0]
        _correction_dialog()


def render_record_tab(sheet_name: str, input_user: str) -> None:
    """「記録する」タブ。

    - time_of_day ラジオ (index=None) + 送信ボタン disabled (§A.6.1)
    - 整合性チェック警告 (§4.6.2 A)
    - 訂正ダイアログ (§A.6.3)
    """
    _consume_correction_action(sheet_name)
    _handle_integrity_ack(sheet_name)
    if st.session_state.get("needs_integrity_ack"):
        return
    st.subheader("今日の記録")
    time_of_day = _time_of_day_radio()
    mood = _score_radio("気分", MOOD_LEGEND, key="mood")
    energy = _score_radio("エネルギー", ENERGY_LEGEND, key="energy")
    thinking = _score_radio("思考", THINKING_LEGEND, key="thinking")
    focus = _score_radio("集中", FOCUS_LEGEND, key="focus")
    st.divider()
    st.caption("任意項目")
    sleep_hours = st.number_input(
        "睡眠時間", min_value=0.0, max_value=24.0, value=7.0, step=0.5,
        key="sleep_hours",
    )
    weather = st.radio(
        "天気", options=list(WEATHER_OPTIONS), index=0,
        horizontal=True, key="weather",
    )
    medication = st.checkbox("服薬した", value=False, key="medication")
    period = st.checkbox("生理中", value=False, key="period")
    submit = st.button(
        "記録する",
        use_container_width=True,
        disabled=(time_of_day is None or input_user is None),
        key="submit_record",
    )
    if not submit:
        return
    try:
        ctx = _build_entry_context(
            input_user=input_user, sheet_name=sheet_name,
            time_of_day=time_of_day,
            mood=mood, energy=energy, thinking=thinking, focus=focus,
            sleep_hours=float(sleep_hours), weather=weather,
            medication=bool(medication), period=bool(period),
        )
    except ValueError as e:
        st.error(f"入力値が不正です: {e}")
        return
    st.session_state["pending_entry"] = ctx
    settings = _get_settings()
    try:
        expected_sheet = resolve_sheet_name(settings, input_user)
    except ValueError as e:
        st.error(f"シート名解決に失敗しました: {e}")
        return
    if expected_sheet != sheet_name:
        st.session_state["needs_integrity_ack"] = True
        st.rerun()
    else:
        _proceed_after_integrity(sheet_name)


def render_view_tab(sheet_name: str) -> None:
    """「見る」タブ: 折れ線グラフ (4 線 + not_recorded ×) / カレンダー切替。"""
    st.subheader("記録を見る")
    view_mode = st.radio(
        "表示モード", ["折れ線グラフ", "カレンダー"],
        horizontal=True, key="view_mode",
    )
    period: str = "week"
    if view_mode == "折れ線グラフ":
        period_label = st.radio(
            "期間", ["週", "月"], horizontal=True, key="period_range"
        )
        period = "week" if period_label == "週" else "month"
    try:
        reader = _get_reader(sheet_name)
        if view_mode == "折れ線グラフ":
            fig = chart_builder.build_line_chart(reader, period=period)
        else:
            fig = chart_builder.build_calendar_chart(reader)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:  # noqa: BLE001
        st.error(
            "Google Sheets からの読み込みに失敗しました "
            f"({type(e).__name__}): {e}"
        )
        return


def main() -> None:
    st.set_page_config(
        page_title="MentalMapping",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    st.title("MentalMapping")
    user_key = _render_user_sidebar()
    try:
        sheet_name = resolve_sheet_name(_get_settings(), user_key)
    except ValueError as e:
        st.error(f"シート名の解決に失敗しました: {e}")
        return
    st.session_state["sheet_name"] = sheet_name
    st.sidebar.caption(f"書き込み先シート: `{sheet_name}`")
    tab_record, tab_view = st.tabs(["記録する", "見る"])
    with tab_record:
        render_record_tab(sheet_name, user_key or "")
    with tab_view:
        render_view_tab(sheet_name)


if __name__ == "__main__":
    main()
