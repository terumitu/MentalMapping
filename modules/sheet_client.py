"""Google Sheets 接続ヘルパ（log_writer / log_reader から分離）。

このモジュールのみが gspread / yaml に依存する。
log_writer.py と log_reader.py は Worksheet Protocol しか要求しないため、
gspread 未インストール環境でも単体テストが通る。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

PathLike = Union[str, Path]

DEFAULT_SETTINGS_PATH = Path("config") / "settings.yaml"
DEFAULT_CREDENTIALS_PATH = Path("config") / "credentials.json"

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def load_settings(path: PathLike = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    """settings.yaml を辞書で返す。"""
    import yaml  # 遅延 import: yaml 未導入環境でも log_writer/log_reader は使える

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def connect_worksheet(settings_path: PathLike = DEFAULT_SETTINGS_PATH) -> Any:
    """settings.yaml に従い、mood_log Worksheet を開いて返す。

    認証情報の取得優先順位:
      1. Streamlit secrets の ``gcp_service_account``（Streamlit Cloud 環境）
      2. ``settings.yaml`` の ``google_sheets.credentials_path`` が指す JSON ファイル
         （未設定時は ``config/credentials.json``）
    """
    import gspread  # 遅延 import
    from google.oauth2.service_account import Credentials

    settings = load_settings(settings_path)
    gs_cfg = settings.get("google_sheets", {})
    spreadsheet_id = gs_cfg.get("spreadsheet_id")
    sheet_name = gs_cfg.get("sheet_name", "mood_log")

    if not spreadsheet_id:
        raise ValueError("google_sheets.spreadsheet_id is not set in settings.yaml")

    creds = _load_credentials(gs_cfg.get("credentials_path"))

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet.worksheet(sheet_name)


def _load_credentials(credentials_path: Any) -> Any:
    """Streamlit secrets 優先でサービスアカウント Credentials を返す。"""
    from google.oauth2.service_account import Credentials

    # Streamlit Cloud 環境: secrets から取得
    try:
        import streamlit as st  # 遅延 import（非 Streamlit 環境でも import 失敗を握る）

        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            return Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]),
                scopes=SCOPES,
            )
    except Exception:
        # streamlit 未導入 / secrets 未設定時はローカルファイルにフォールバック
        pass

    # ローカル環境: credentials.json ファイルから取得
    local_path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS_PATH
    if not local_path.exists():
        raise FileNotFoundError(
            f"Service account credentials not found: {local_path}. "
            "Set Streamlit secrets 'gcp_service_account' or place credentials.json."
        )
    return Credentials.from_service_account_file(str(local_path), scopes=SCOPES)
