"""MentalMapping Phase 1 — チャート描画モジュール (v1.2 / 17 列・not_recorded 対応)。

log_reader.LogReader.fetch_active_records() が返すレコード辞書列
(list[dict[str, Any]]) を受け取り, DataFrame に変換した上で
Plotly の折れ線グラフ (mood/energy/thinking/focus の 4 線重ね + not_recorded ×)
とカレンダービュー (mood 主軸 5 段階色分け + not_recorded グレー) を構築する.

想定レコード辞書キー (v1.2 / 17 列):
    date / mood / energy / thinking / focus / sleep_hours /
    weather / medication / period / recorded_at / time_of_day /
    daily_aspects / record_id / record_status / superseded_by /
    entry_mode / input_user
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
    "date", "mood", "energy", "thinking", "focus",
    "sleep_hours", "weather", "medication", "period",
    "recorded_at", "time_of_day", "daily_aspects",
    "record_id", "record_status", "superseded_by",
    "entry_mode", "input_user",
]

MOOD_COLOR_MAP: Dict[int, str] = {
    1: "#E74C3C",
    2: "#E67E22",
    3: "#F1C40F",
    4: "#9ACD32",
    5: "#2ECC71",
}

NOT_RECORDED_COLOR = "#BDC3C7"  # §A.6.5 カレンダーのグレー塗り用
PENDING_COLOR = "#FFE89E"        # §4.3.4 カレンダーの薄黄色塗り用 (v1.2.1)
PENDING_MARKER_COLOR = "#D4AC0D" # 折れ線グラフ pending マーカー縁色

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
    """fetch_active_records() の返値 (list[dict]) を DataFrame 化する。"""
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
    """LogReader.fetch_active_records() 経由で active 全レコードを DataFrame 化。

    同一 (date, time_of_day) 内 active は 1 件以内 (§4.4 不変条件)。
    not_recorded 行も含まれる (entry_mode 列で判別可能)。
    """
    records = reader.fetch_active_records()
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


def _split_recorded_not_recorded(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """entry_mode で recorded (pending 含む) / not_recorded に分割する。

    pending は値を持つため折れ線グラフにプロットする (§4.3.4 / v1.2.1)。
    """
    if df.empty:
        return df, df
    is_not_rec = df["entry_mode"].astype(str) == "not_recorded"
    return df[~is_not_rec], df[is_not_rec]


def _extract_pending(df: pd.DataFrame) -> pd.DataFrame:
    """entry_mode=pending のレコードを抽出する (v1.2.1)。"""
    if df.empty or "entry_mode" not in df.columns:
        return df.iloc[0:0] if not df.empty else df
    return df[df["entry_mode"].astype(str) == "pending"]


def _add_metric_traces(fig: go.Figure, recorded_df: pd.DataFrame) -> None:
    """mood/energy/thinking/focus の 4 線を追加する。"""
    for field in METRIC_FIELDS:
        if field not in recorded_df.columns:
            continue
        sub = recorded_df[["date", field]].dropna(subset=[field])
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["date"], y=sub[field],
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


def _add_not_recorded_trace(fig: go.Figure, not_rec_df: pd.DataFrame) -> None:
    """not_recorded 日を × マーカーで明示する (§A.6.5)。"""
    if not_rec_df.empty:
        return
    fig.add_trace(
        go.Scatter(
            x=not_rec_df["date"],
            y=[0.5] * len(not_rec_df),
            mode="markers",
            name="未記録 (not_recorded)",
            marker=dict(symbol="x", size=12, color=NOT_RECORDED_COLOR),
            hovertemplate="%{x|%Y-%m-%d}<br>未記録<extra></extra>",
        )
    )


def _add_pending_overlay_trace(fig: go.Figure, pending_df: pd.DataFrame) -> None:
    """entry_mode=pending の日を diamond マーカーで重ね、判定保留を明示する。

    mood 値を Y 座標に使い、pending 日が分析レビュー対象であることを示す (v1.2.1)。
    """
    if pending_df.empty:
        return
    sub = pending_df[["date", "mood"]].dropna(subset=["mood"])
    if sub.empty:
        return
    fig.add_trace(
        go.Scatter(
            x=sub["date"], y=sub["mood"],
            mode="markers",
            name="判定保留 (pending)",
            marker=dict(
                symbol="diamond-open",
                size=16,
                color=PENDING_COLOR,
                line=dict(width=2, color=PENDING_MARKER_COLOR),
            ),
            hovertemplate="%{x|%Y-%m-%d}<br>判定保留 (realtime/retroactive 未確定)<extra></extra>",
        )
    )


def build_line_chart(reader: LogReader, period: str = "week") -> go.Figure:
    """折れ線グラフ: 4 指標 + not_recorded × + pending diamond オーバーレイ。"""
    df = _filter_period(load_logs(reader), period)
    if df.empty:
        return _empty_line_figure("記録がまだありません")
    recorded_df, not_rec_df = _split_recorded_not_recorded(df)
    fig = go.Figure()
    _add_metric_traces(fig, recorded_df)
    _add_not_recorded_trace(fig, not_rec_df)
    _add_pending_overlay_trace(fig, _extract_pending(recorded_df))
    title = "過去7日間" if period == "week" else "過去30日間"
    fig.update_layout(
        title=title,
        xaxis_title="日付",
        yaxis_title="スコア (1-5)",
        yaxis=dict(range=[0, 5.5], dtick=1),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _month_grid(year: int, month: int) -> list[list[datetime | None]]:
    """月のカレンダーグリッド (週 × 曜日, 日曜始まり)。"""
    first = datetime(year, month, 1)
    if month == 12:
        next_first = datetime(year + 1, 1, 1)
    else:
        next_first = datetime(year, month + 1, 1)
    last_day = (next_first - timedelta(days=1)).day
    start_weekday = (first.weekday() + 1) % 7  # Python: 月=0..日=6 → 日=0..土=6
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


def _build_day_value_map(df: pd.DataFrame, year: int, month: int) -> Dict[str, int]:
    """当月の日付 -> z 値マップを構築する (-1=pending / 0=not_recorded / 1-5=mood)。

    優先順位 (低→高、後から上書き): not_recorded(0) → mood(1-5) → pending(-1)。
    pending 日は値を持つが realtime/retroactive 判定保留のため、セルを
    薄黄色で独立表示する (v1.2.1 §4.3.4 可視化方針)。
    """
    if df.empty:
        return {}
    mask = (df["date"].dt.year == year) & (df["date"].dt.month == month)
    month_df = df[mask]
    out: Dict[str, int] = {}
    # not_recorded = 0
    not_rec = month_df[month_df["entry_mode"].astype(str) == "not_recorded"]
    for _, row in not_rec.iterrows():
        out[row["date"].strftime("%Y-%m-%d")] = 0
    # 通常記録 (realtime / retroactive) = 1-5
    is_regular = ~month_df["entry_mode"].astype(str).isin(["not_recorded", "pending"])
    regular = month_df[is_regular].dropna(subset=["mood"])
    for _, row in regular.iterrows():
        out[row["date"].strftime("%Y-%m-%d")] = int(row["mood"])
    # pending = -1 (他を上書き。判定保留の可視性を最優先)
    pending = month_df[month_df["entry_mode"].astype(str) == "pending"]
    for _, row in pending.iterrows():
        out[row["date"].strftime("%Y-%m-%d")] = -1
    return out


def _calendar_colorscale() -> list:
    """7 段階 (-1=pending / 0=not_recorded / 1-5=mood) の離散カラースケール。

    zmin=-1, zmax=5 で 7 バケット × 1/7 幅。
    """
    step = 1 / 7
    return [
        [0 * step, PENDING_COLOR], [1 * step, PENDING_COLOR],
        [1 * step, NOT_RECORDED_COLOR], [2 * step, NOT_RECORDED_COLOR],
        [2 * step, MOOD_COLOR_MAP[1]], [3 * step, MOOD_COLOR_MAP[1]],
        [3 * step, MOOD_COLOR_MAP[2]], [4 * step, MOOD_COLOR_MAP[2]],
        [4 * step, MOOD_COLOR_MAP[3]], [5 * step, MOOD_COLOR_MAP[3]],
        [5 * step, MOOD_COLOR_MAP[4]], [6 * step, MOOD_COLOR_MAP[4]],
        [6 * step, MOOD_COLOR_MAP[5]], [1.0, MOOD_COLOR_MAP[5]],
    ]


def build_calendar_chart(reader: LogReader) -> go.Figure:
    """当月カレンダー: mood 1-5 で 5 段階色分け + not_recorded はグレー。"""
    df = load_logs(reader)
    now = datetime.now(tz=ZoneInfo("Asia/Tokyo"))
    weeks = _month_grid(now.year, now.month)
    day_map = _build_day_value_map(df, now.year, now.month)
    day_labels = ["日", "月", "火", "水", "木", "金", "土"]

    n_rows = len(weeks)
    z: list[list[float | None]] = [[None] * 7 for _ in range(n_rows)]
    text: list[list[str]] = [[""] * 7 for _ in range(n_rows)]
    for r, week in enumerate(weeks):
        for c, dt in enumerate(week):
            if dt is None:
                continue
            text[r][c] = str(dt.day)
            v = day_map.get(dt.strftime("%Y-%m-%d"))
            if v is not None:
                z[r][c] = float(v)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=day_labels,
            y=[f"W{i + 1}" for i in range(n_rows)],
            colorscale=_calendar_colorscale(),
            zmin=-1,
            zmax=5,
            showscale=True,
            hoverongaps=False,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=14, color="#222"),
            colorbar=dict(
                title="mood",
                tickvals=[-1, 0, 1, 2, 3, 4, 5],
                ticktext=["保留", "未記録", "1", "2", "3", "4", "5"],
            ),
        )
    )
    fig.update_layout(
        title=f"{now.year}年 {now.month}月 (気分・未記録グレー・保留薄黄)",
        xaxis=dict(side="top"),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig
