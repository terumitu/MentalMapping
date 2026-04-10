"""MentalMapping Phase 2 — Streamlit エントリーポイント (5段階 8項目仕様)。

スマホ縦画面・30秒以内入力を設計原則とする気分記録 UI.
2タブ構成: 「記録する」/「見る」.

記録項目:
  必須 4 項目 (ラジオボタン 1-5): mood / energy / thinking / focus
  任意 4 項目:
    sleep_hours : 数値入力 (0.5 刻み)
    weather     : ラジオボタン 晴/曇/雨
    medication  : チェックボックス
    period      : チェックボックス

保存先は Google Sheets (mood_log) — sheet_client 経由で Worksheet を取得し、
LogWriter / LogReader に注入して使用する。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from modules import chart_builder
from modules.log_reader import LogReader
from modules.log_writer import LogWriter, MoodLogEntry
from modules.sheet_client import connect_worksheet

MOOD_LEGEND = "1=消えたい　2=辛い　3=普通　4=良い　5=最高"
ENERGY_LEGEND = "1=起き上がれない　2=重い　3=やればできる　4=動ける　5=やる気がある"
THINKING_LEGEND = "1=頭が動かない　2=遅い・詰まる　3=考えられる　4=クリア　5=冴えている"
FOCUS_LEGEND = "1=何も手につかない　2=すぐ散漫　3=短時間なら可　4=集中できる　5=没頭できた"

WEATHER_OPTIONS = ("晴", "曇", "雨")


@st.cache_resource(show_spinner=False)
def _get_worksheet() -> Any:
    """mood_log Worksheet をセッション寿命でキャッシュして返す。"""
    return connect_worksheet()


def _get_writer() -> LogWriter:
    return LogWriter(_get_worksheet())


def _get_reader() -> LogReader:
    return LogReader(_get_worksheet())


def _score_radio(title: str, legend: str, key: str) -> int:
    """1-5 スコア選択 UI (タイトル + ラベル凡例 + 横並びラジオ)。"""
    st.markdown(f"**{title}**")
    st.caption(legend)
    return int(
        st.radio(
            title,
            options=[1, 2, 3, 4, 5],
            index=2,  # default = 3 (普通)
            horizontal=True,
            key=key,
            label_visibility="collapsed",
        )
    )


def render_record_tab() -> None:
    """「記録する」タブ: 5段階4項目 + 任意4項目のフォーム。"""
    st.subheader("今日の記録")
    with st.form("record_form", clear_on_submit=True):
        mood = _score_radio("気分", MOOD_LEGEND, key="mood")
        energy = _score_radio("エネルギー", ENERGY_LEGEND, key="energy")
        thinking = _score_radio("思考", THINKING_LEGEND, key="thinking")
        focus = _score_radio("集中", FOCUS_LEGEND, key="focus")

        st.divider()
        st.caption("任意項目")

        sleep_hours = st.number_input(
            "睡眠時間",
            min_value=0.0,
            max_value=24.0,
            value=7.0,
            step=0.5,
        )
        weather = st.radio(
            "天気",
            options=list(WEATHER_OPTIONS),
            index=0,
            horizontal=True,
            key="weather",
        )
        medication = st.checkbox("服薬した", value=False)
        period = st.checkbox("生理中", value=False)

        submitted = st.form_submit_button(
            "記録する", use_container_width=True
        )
    if not submitted:
        return
    try:
        entry = MoodLogEntry.create(
            date=datetime.now().strftime("%Y-%m-%d"),
            mood=mood,
            energy=energy,
            thinking=thinking,
            focus=focus,
            sleep_hours=float(sleep_hours),
            weather=weather,
            medication=bool(medication),
            period=bool(period),
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
    """「見る」タブ: 折れ線グラフ (4線) / カレンダービュー (mood) 切替。"""
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
            "期間", ["週", "月"], horizontal=True, key="period_range"
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
