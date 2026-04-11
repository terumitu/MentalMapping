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

保存先は Google Sheets — sheet_client 経由で Worksheet を取得し、
LogWriter / LogReader に注入して使用する。マルチユーザー対応のため
サイドバーで選択したユーザーに応じて書き込み先シートを切り替える。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

import streamlit as st

from modules import chart_builder
from modules.log_reader import LogReader
from modules.log_writer import LogWriter, MoodLogEntry, determine_time_of_day
from modules.sheet_client import connect_worksheet, load_settings, resolve_sheet_name

MOOD_LEGEND = "1=消えたい　2=辛い　3=普通　4=良い　5=最高"
ENERGY_LEGEND = "1=起き上がれない　2=重い　3=やればできる　4=動ける　5=やる気がある"
THINKING_LEGEND = "1=頭が動かない　2=遅い・詰まる　3=考えられる　4=クリア　5=冴えている"
FOCUS_LEGEND = "1=何も手につかない　2=すぐ散漫　3=短時間なら可　4=集中できる　5=没頭できた"

WEATHER_OPTIONS = ("晴", "曇", "雨")
TIME_OF_DAY_OPTIONS = ("morning", "evening")
TIME_OF_DAY_LABELS = {"morning": "朝 (morning)", "evening": "夜 (evening)"}
JST = ZoneInfo("Asia/Tokyo")


@st.cache_resource(show_spinner=False)
def _get_worksheet(sheet_name: str) -> Any:
    """sheet_name をキーに Worksheet をキャッシュして返す。"""
    return connect_worksheet(sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def _get_settings() -> Dict[str, Any]:
    """settings.yaml をセッション寿命でキャッシュして返す。"""
    return load_settings()


def _default_time_of_day() -> str:
    """現在時刻 (JST) と settings.yaml から時間帯を自動判定する。"""
    return determine_time_of_day(datetime.now(tz=JST), _get_settings())


def _get_writer(sheet_name: str) -> LogWriter:
    return LogWriter(_get_worksheet(sheet_name))


def _get_reader(sheet_name: str) -> LogReader:
    return LogReader(_get_worksheet(sheet_name))


def _render_user_sidebar() -> str | None:
    """サイドバーにユーザー選択 UI を描画し、選択された user_key を返す。

    ``users`` が未定義 (None / 空) の場合は ``None`` を返し、
    resolve_sheet_name 側の legacy フォールバック経路に処理を委ねる。
    ``users`` が非空のときは必ず users に存在するキーを返す。
    """
    settings = _get_settings()
    users = settings.get("users") or {}
    if not users:
        return None
    keys = list(users.keys())
    labels = [str(users[k].get("display_name", k)) for k in keys]
    default_key = settings.get("default_user") or keys[0]
    default_idx = keys.index(default_key) if default_key in keys else 0
    selected_label = st.sidebar.selectbox(
        "ユーザー",
        options=labels,
        index=default_idx,
        key="user_selector",
    )
    return keys[labels.index(selected_label)]


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


def render_record_tab(sheet_name: str) -> None:
    """「記録する」タブ: 5段階4項目 + 任意4項目のフォーム。"""
    st.subheader("今日の記録")
    default_tod = _default_time_of_day()
    with st.form("record_form", clear_on_submit=True):
        mood = _score_radio("気分", MOOD_LEGEND, key="mood")
        time_of_day = st.selectbox(
            "時間帯",
            options=list(TIME_OF_DAY_OPTIONS),
            index=list(TIME_OF_DAY_OPTIONS).index(default_tod),
            format_func=lambda v: TIME_OF_DAY_LABELS[v],
            key="time_of_day",
            help="現在時刻から自動判定されます。必要なら手動で変更してください。",
        )
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
            date=datetime.now(tz=JST).strftime("%Y-%m-%d"),
            mood=mood,
            energy=energy,
            thinking=thinking,
            focus=focus,
            time_of_day=time_of_day,
            sleep_hours=float(sleep_hours),
            weather=weather,
            medication=bool(medication),
            period=bool(period),
        )
        _get_writer(sheet_name).append(entry)
    except ValueError as e:
        st.error(f"入力値が不正です: {e}")
        return
    except Exception as e:  # gspread/認証エラー等
        st.error(f"Google Sheets への書き込みに失敗しました: {e}")
        return
    st.success("記録しました")


def render_view_tab(sheet_name: str) -> None:
    """「見る」タブ: 折れ線グラフ (4線) / カレンダービュー (mood) 切替。

    reader 取得から chart 構築・描画までを単一 try/except で保護する。
    build_line_chart / build_calendar_chart は内部で get_all_records を
    叩くため、APIError やシート構造起因の例外もここで捕捉する必要がある。
    """
    st.subheader("記録を見る")
    view_mode = st.radio(
        "表示モード",
        ["折れ線グラフ", "カレンダー"],
        horizontal=True,
        key="view_mode",
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
    except Exception as e:
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
    st.sidebar.caption(f"書き込み先シート: `{sheet_name}`")
    tab_record, tab_view = st.tabs(["記録する", "見る"])
    with tab_record:
        render_record_tab(sheet_name)
    with tab_view:
        render_view_tab(sheet_name)


if __name__ == "__main__":
    main()
