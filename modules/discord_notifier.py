"""Discord Webhook 通知 — 当日の natal x transit アスペクトデータを投稿する。

記録送信後に呼び出し、対応する transit_grid シートから当日分の
アスペクトデータを取得して Discord に投稿する。
投稿失敗時はログ出力のみで呼び出し元の処理を妨げない。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")

# mood_log シート名 -> transit_grid シート名の対応
_TRANSIT_GRID_MAP: Dict[str, str] = {
    "mood_log_masuda": "transit_grid",
    "mood_log_nishide": "transit_grid_nishide",
    "mood_log_suyasu": "transit_grid_suyasu",
}


def _resolve_transit_sheet(mood_sheet: str) -> Optional[str]:
    """mood_log シート名から対応する transit_grid シート名を返す。"""
    return _TRANSIT_GRID_MAP.get(mood_sheet)


def _get_webhook_url() -> Optional[str]:
    """Streamlit secrets から DISCORD_WEBHOOK_URL を取得する。"""
    try:
        import streamlit as st

        return str(st.secrets["DISCORD_WEBHOOK_URL"])
    except KeyError:
        logger.warning("DISCORD_WEBHOOK_URL is not set in Streamlit secrets")
    except Exception as e:
        logger.warning("Failed to read DISCORD_WEBHOOK_URL: %s: %s", type(e).__name__, e)
    return None


def _fetch_today_aspects(worksheet: Any, today: str) -> List[Dict[str, Any]]:
    """transit_grid シートから当日日付の行を全件取得する。"""
    records = worksheet.get_all_records()
    return [r for r in records if str(r.get("date", "")) == today]


def _format_message(aspects: List[Dict[str, Any]], now: datetime) -> str:
    """Discord 投稿用メッセージを整形する。"""
    lines: List[str] = [
        f"【今日の星の動き - {now.year}年{now.month}月{now.day}日】",
        "",
        "📋 そのままClaudeにコピペしてね",
        "",
        "---",
    ]
    for a in aspects:
        transit = a.get("transit_body", "")
        natal = a.get("natal_point", "")
        aspect = a.get("aspect_type", "")
        orb = a.get("orb", "")
        nature = a.get("nature", "")
        lines.append(f"{transit} → {natal} {aspect} ({orb}°) [{nature}]")
    lines.append("---")
    lines.append("")
    lines.append(
        "💬 Claudeへの貼り方例：\n"
        "「今日のトランジットアスペクトです。"
        "それぞれが今日の私にどう影響するか教えてください。」"
    )
    return "\n".join(lines)


def _post_discord(webhook_url: str, content: str) -> None:
    """Discord Webhook へ POST する。"""
    payload = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MentalMapping/1.0",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


def send(sheet_name: str) -> None:
    """記録送信後のエントリーポイント。

    sheet_name に対応する transit_grid シートから当日アスペクトを取得し
    Discord に投稿する。未設定・データなし・通信エラーはログのみ。
    """
    transit_sheet = _resolve_transit_sheet(sheet_name)
    if transit_sheet is None:
        logger.info("No transit_grid mapping for sheet: %s", sheet_name)
        return

    webhook_url = _get_webhook_url()
    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL is not configured in secrets")
        return

    try:
        from modules.sheet_client import connect_worksheet

        now = datetime.now(tz=JST)
        today = now.strftime("%Y-%m-%d")
        ws = connect_worksheet(sheet_name=transit_sheet)
        aspects = _fetch_today_aspects(ws, today)
        if not aspects:
            logger.info("No transit aspects for %s in %s", today, transit_sheet)
            return
        message = _format_message(aspects, now)
        _post_discord(webhook_url, message)
    except Exception:
        logger.exception("Discord notification failed (sheet: %s)", sheet_name)
