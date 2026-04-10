"""MentalMapping Phase 1 — チャート描画モジュール.

log_reader.LogReader.fetch_latest_per_day() が返すレコード辞書列
(list[dict[str, Any]]) を受け取り, DataFrame に変換した上で
Plotly の折れ線グラフ / カレンダービューを構築する.

想定レコード辞書キー:
    date / mood_score / sleep_hours / went_outside / memo / recorded_at
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go

from modules.log_reader import LogReader

COLUMNS = ["date", "mood_score", "sleep_hours", "went_outside", "memo"]

# 気分スコア色分け (0-3 赤 / 4-6 黄 / 7-10 緑)
COLOR_LOW = "#E74C3C"
COLOR_MID = "#F1C40F"
COLOR_HIGH = "#2ECC71"
COLOR_LINE = "#3498DB"


def _records_to_frame(records: List[Dict[str, Any]]) -> pd.DataFrame:
    """fetch_latest_per_day() の返値 (list[dict]) を DataFrame に変換."""
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(records)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["mood_score"] = pd.to_numeric(df["mood_score"], errors="coerce")
    df = df.dropna(subset=["mood_score"])
    return df


def load_logs(reader: LogReader) -> pd.DataFrame:
    """LogReader 経由で mood_log を取得し DataFrame 化する.

    同日複数記録は LogReader.fetch_latest_per_day() 側で最新 1 件に集約済み.
    """
    records = reader.fetch_latest_per_day()
    return _records_to_frame(records)


def _mood_color(score: float) -> str:
    """気分スコア -> 色文字列."""
    if score <= 3:
        return COLOR_LOW
    if score <= 6:
        return COLOR_MID
    return COLOR_HIGH


def _filter_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """期間 (week / month) でフィルタ."""
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
        yaxis_title="気分スコア",
        yaxis=dict(range=[0, 10], dtick=1),
    )
    return fig


def build_line_chart(reader: LogReader, period: str = "week") -> go.Figure:
    """折れ線グラフ (週/月). mood_score をマーカー色で強調."""
    df = _filter_period(load_logs(reader), period)
    if df.empty:
        return _empty_line_figure("記録がまだありません")
    marker_colors = [_mood_color(float(s)) for s in df["mood_score"]]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["mood_score"],
            mode="lines+markers",
            line=dict(color=COLOR_LINE, width=2),
            marker=dict(size=12, color=marker_colors, line=dict(width=1, color="#333")),
            name="気分スコア",
            hovertemplate="%{x|%Y-%m-%d}<br>スコア: %{y}<extra></extra>",
        )
    )
    title = "過去7日間" if period == "week" else "過去30日間"
    fig.update_layout(
        title=title,
        xaxis_title="日付",
        yaxis_title="気分スコア",
        yaxis=dict(range=[0, 10], dtick=1),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def _month_grid(year: int, month: int) -> list[list[datetime | None]]:
    """月のカレンダーグリッド (週 × 曜日, 日曜始まり) を生成."""
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


def _build_score_map(df: pd.DataFrame, year: int, month: int) -> dict[str, float]:
    """当月の日付 -> mood_score マップを構築."""
    if df.empty:
        return {}
    mask = (df["date"].dt.year == year) & (df["date"].dt.month == month)
    month_df = df[mask]
    return {
        row["date"].strftime("%Y-%m-%d"): float(row["mood_score"])
        for _, row in month_df.iterrows()
    }


def build_calendar_chart(reader: LogReader) -> go.Figure:
    """当月カレンダービュー (mood_score で色分け)."""
    df = load_logs(reader)
    now = datetime.now()
    weeks = _month_grid(now.year, now.month)
    score_map = _build_score_map(df, now.year, now.month)
    day_labels = ["日", "月", "火", "水", "木", "金", "土"]

    n_rows = len(weeks)
    z: list[list[float | None]] = [[None] * 7 for _ in range(n_rows)]
    text: list[list[str]] = [[""] * 7 for _ in range(n_rows)]
    for r, week in enumerate(weeks):
        for c, dt in enumerate(week):
            if dt is None:
                continue
            text[r][c] = str(dt.day)
            score = score_map.get(dt.strftime("%Y-%m-%d"))
            if score is not None:
                z[r][c] = score

    # 0-3 赤 / 4-6 黄 / 7-10 緑 の離散カラースケール
    colorscale = [
        [0.0, COLOR_LOW], [0.3, COLOR_LOW],
        [0.3, COLOR_MID], [0.6, COLOR_MID],
        [0.6, COLOR_HIGH], [1.0, COLOR_HIGH],
    ]
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=day_labels,
            y=[f"W{i + 1}" for i in range(n_rows)],
            colorscale=colorscale,
            zmin=0,
            zmax=10,
            showscale=True,
            hoverongaps=False,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=14, color="#222"),
            colorbar=dict(title="mood", tickvals=[1, 5, 9]),
        )
    )
    fig.update_layout(
        title=f"{now.year}年 {now.month}月",
        xaxis=dict(side="top"),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig
