"""MentalMapping Phase 2 — チャート描画モジュール (5段階 8項目仕様)。

log_reader.LogReader.fetch_latest_per_day() が返すレコード辞書列
(list[dict[str, Any]]) を受け取り, DataFrame に変換した上で
Plotly の折れ線グラフ (mood/energy/thinking/focus の 4 線重ね表示) と
カレンダービュー (mood 主軸で 5 段階色分け) を構築する.

想定レコード辞書キー:
    date / mood / energy / thinking / focus /
    sleep_hours / weather / medication / period / recorded_at
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go

from modules.log_reader import LogReader

METRIC_FIELDS = ("mood", "energy", "thinking", "focus")

COLUMNS = [
    "date",
    "mood",
    "energy",
    "thinking",
    "focus",
    "sleep_hours",
    "weather",
    "medication",
    "period",
]

# mood 5段階カラー (1=赤 / 2=橙 / 3=黄 / 4=黄緑 / 5=緑)
MOOD_COLOR_MAP: Dict[int, str] = {
    1: "#E74C3C",
    2: "#E67E22",
    3: "#F1C40F",
    4: "#9ACD32",
    5: "#2ECC71",
}

# 折れ線グラフの各指標カラー
METRIC_LINE_COLOR: Dict[str, str] = {
    "mood": "#E74C3C",
    "energy": "#3498DB",
    "thinking": "#9B59B6",
    "focus": "#16A085",
}

METRIC_LABEL_JA: Dict[str, str] = {
    "mood": "気分",
    "energy": "エネルギー",
    "thinking": "思考",
    "focus": "集中",
}


def _records_to_frame(records: List[Dict[str, Any]]) -> pd.DataFrame:
    """fetch_latest_per_day() の返値 (list[dict]) を DataFrame 化する。"""
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(records)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    for field in METRIC_FIELDS:
        df[field] = pd.to_numeric(df[field], errors="coerce")
    if "sleep_hours" in df.columns:
        df["sleep_hours"] = pd.to_numeric(df["sleep_hours"], errors="coerce")
    return df


def load_logs(reader: LogReader) -> pd.DataFrame:
    """LogReader 経由で mood_log を取得し DataFrame 化する。

    同日複数記録は LogReader.fetch_latest_per_day() 側で最新 1 件に集約済み。
    """
    records = reader.fetch_latest_per_day()
    return _records_to_frame(records)


def _filter_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """期間 (week / month) でフィルタ。"""
    if df.empty:
        return df
    now = pd.Timestamp.now().normalize()
    days = 7 if period == "week" else 30
    start = now - pd.Timedelta(days=days - 1)
    return df[df["date"] >= start].sort_values("date")


def _empty_line_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        xaxis_title="日付",
        yaxis_title="スコア (1-5)",
        yaxis=dict(range=[0.5, 5.5], dtick=1),
    )
    return fig


def build_line_chart(reader: LogReader, period: str = "week") -> go.Figure:
    """折れ線グラフ: mood/energy/thinking/focus の 4 線を重ねて描画する。"""
    df = _filter_period(load_logs(reader), period)
    if df.empty:
        return _empty_line_figure("記録がまだありません")
    fig = go.Figure()
    for field in METRIC_FIELDS:
        if field not in df.columns:
            continue
        sub = df[["date", field]].dropna(subset=[field])
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["date"],
                y=sub[field],
                mode="lines+markers",
                name=METRIC_LABEL_JA[field],
                line=dict(color=METRIC_LINE_COLOR[field], width=2),
                marker=dict(size=8),
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>"
                    + METRIC_LABEL_JA[field]
                    + ": %{y}<extra></extra>"
                ),
            )
        )
    title = "過去7日間" if period == "week" else "過去30日間"
    fig.update_layout(
        title=title,
        xaxis_title="日付",
        yaxis_title="スコア (1-5)",
        yaxis=dict(range=[0.5, 5.5], dtick=1),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )
    return fig


def _month_grid(year: int, month: int) -> list[list[datetime | None]]:
    """月のカレンダーグリッド (週 × 曜日, 日曜始まり) を生成する。"""
    first = datetime(year, month, 1)
    if month == 12:
        next_first = datetime(year + 1, 1, 1)
    else:
        next_first = datetime(year, month + 1, 1)
    last_day = (next_first - timedelta(days=1)).day
    # Python: 月=0..日=6 → 日=0..土=6 に変換
    start_weekday = (first.weekday() + 1) % 7
    weeks: list[list[datetime | None]] = []
    current: list[datetime | None] = [None] * start_weekday
    for day in range(1, last_day + 1):
        current.append(datetime(year, month, day))
        if len(current) == 7:
            weeks.append(current)
            current = []
    if current:
        while len(current) < 7:
            current.append(None)
        weeks.append(current)
    return weeks


def _build_mood_map(df: pd.DataFrame, year: int, month: int) -> dict[str, int]:
    """当月の日付 -> mood (1-5) マップを構築する。"""
    if df.empty or "mood" not in df.columns:
        return {}
    mask = (df["date"].dt.year == year) & (df["date"].dt.month == month)
    month_df = df[mask].dropna(subset=["mood"])
    return {
        row["date"].strftime("%Y-%m-%d"): int(row["mood"])
        for _, row in month_df.iterrows()
    }


def build_calendar_chart(reader: LogReader) -> go.Figure:
    """当月カレンダービュー (mood 1-5 で 5 段階色分け)。"""
    df = load_logs(reader)
    now = datetime.now(tz=ZoneInfo("Asia/Tokyo"))
    weeks = _month_grid(now.year, now.month)
    mood_map = _build_mood_map(df, now.year, now.month)
    day_labels = ["日", "月", "火", "水", "木", "金", "土"]

    n_rows = len(weeks)
    z: list[list[float | None]] = [[None] * 7 for _ in range(n_rows)]
    text: list[list[str]] = [[""] * 7 for _ in range(n_rows)]
    for r, week in enumerate(weeks):
        for c, dt in enumerate(week):
            if dt is None:
                continue
            text[r][c] = str(dt.day)
            mood = mood_map.get(dt.strftime("%Y-%m-%d"))
            if mood is not None:
                z[r][c] = float(mood)

    # 5 段階離散カラースケール (zmin=1, zmax=5)
    colorscale = [
        [0.0, MOOD_COLOR_MAP[1]], [0.2, MOOD_COLOR_MAP[1]],
        [0.2, MOOD_COLOR_MAP[2]], [0.4, MOOD_COLOR_MAP[2]],
        [0.4, MOOD_COLOR_MAP[3]], [0.6, MOOD_COLOR_MAP[3]],
        [0.6, MOOD_COLOR_MAP[4]], [0.8, MOOD_COLOR_MAP[4]],
        [0.8, MOOD_COLOR_MAP[5]], [1.0, MOOD_COLOR_MAP[5]],
    ]
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=day_labels,
            y=[f"W{i + 1}" for i in range(n_rows)],
            colorscale=colorscale,
            zmin=1,
            zmax=5,
            showscale=True,
            hoverongaps=False,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=14, color="#222"),
            colorbar=dict(title="mood", tickvals=[1, 2, 3, 4, 5]),
        )
    )
    fig.update_layout(
        title=f"{now.year}年 {now.month}月 (気分)",
        xaxis=dict(side="top"),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig
