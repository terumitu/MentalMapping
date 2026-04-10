"""MentalMapping Phase 1 — Streamlit エントリーポイント.

スマホ縦画面・30秒以内入力を設計原則とする気分記録 UI.
2タブ構成: 「記録する」/「見る」.
保存先は Google Sheets (mood_log) — sheet_client 経由で Worksheet を取得し,
LogWriter / LogReader に注入して使用する.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from modules import chart_builder
from modules.log_reader import LogReader
from modules.log_writer import LogWriter, MoodLogEntry
from modules.sheet_client import connect_worksheet


@st.cache_resource(show_spinner=False)
def _get_worksheet() -> Any:
    """mood_log Worksheet をセッション寿命でキャッシュして返す."""
    return connect_worksheet()


def _get_writer() -> LogWriter:
    return LogWriter(_get_worksheet())


def _get_reader() -> LogReader:
    return LogReader(_get_worksheet())


def render_record_tab() -> None:
    """「記録する」タブ: 30 秒以内入力を目指したフォーム."""
    st.subheader("今日の記録")
    with st.form("record_form", clear_on_submit=True):
        mood_score = st.slider(
            "気分スコア",
            min_value=0,
            max_value=10,
            value=5,
            step=1,
            help="0 = 最悪 / 10 = 最高",
        )
        sleep_hours = st.number_input(
            "睡眠時間 (任意)",
            min_value=0.0,
            max_value=24.0,
            value=7.0,
            step=0.5,
        )
        went_outside = st.checkbox("外出した", value=False)
        memo = st.text_area(
            "メモ (任意, 200字以内)",
            max_chars=200,
            height=80,
        )
        submitted = st.form_submit_button(
            "記録する", use_container_width=True
        )
    if not submitted:
        return
    try:
        entry = MoodLogEntry.create(
            date=datetime.now().strftime("%Y-%m-%d"),
            mood_score=int(mood_score),
            sleep_hours=float(sleep_hours),
            went_outside=bool(went_outside),
            memo=memo or "",
        )
        _get_writer().append(entry)
    except ValueError as e:
        st.error(f"入力値が不正です: {e}")
        return
    except Exception as e:  # gspread/認証エラー等
        st.error(f"Google Sheets への書き込みに失敗しました: {e}")
        return
    st.success("記録しました")


def render_view_tab() -> None:
    """「見る」タブ: 折れ線グラフ / カレンダービュー切替."""
    st.subheader("記録を見る")
    view_mode = st.radio(
        "表示モード",
        ["折れ線グラフ", "カレンダー"],
        horizontal=True,
        key="view_mode",
    )
    try:
        reader = _get_reader()
    except Exception as e:
        st.error(f"Google Sheets への接続に失敗しました: {e}")
        return
    if view_mode == "折れ線グラフ":
        period_label = st.radio(
            "期間", ["週", "月"], horizontal=True, key="period"
        )
        period = "week" if period_label == "週" else "month"
        fig = chart_builder.build_line_chart(reader, period=period)
        st.plotly_chart(fig, use_container_width=True)
    else:
        fig = chart_builder.build_calendar_chart(reader)
        st.plotly_chart(fig, use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="MentalMapping",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.title("MentalMapping")
    tab_record, tab_view = st.tabs(["記録する", "見る"])
    with tab_record:
        render_record_tab()
    with tab_view:
        render_view_tab()


if __name__ == "__main__":
    main()
