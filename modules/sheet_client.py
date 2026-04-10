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


def load_settings(path: PathLike = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    """settings.yaml を辞書で返す。"""
    import yaml  # 遅延 import: yaml 未導入環境でも log_writer/log_reader は使える

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def connect_worksheet(settings_path: PathLike = DEFAULT_SETTINGS_PATH) -> Any:
    """settings.yaml に従い、mood_log Worksheet を開いて返す。"""
    import gspread  # 遅延 import

    settings = load_settings(settings_path)
    gs_cfg = settings.get("google_sheets", {})
    credentials_path = gs_cfg.get("credentials_path")
    spreadsheet_id = gs_cfg.get("spreadsheet_id")
    sheet_name = gs_cfg.get("sheet_name", "mood_log")

    if not credentials_path:
        raise ValueError("google_sheets.credentials_path is not set in settings.yaml")
    if not spreadsheet_id:
        raise ValueError("google_sheets.spreadsheet_id is not set in settings.yaml")

    gc = gspread.service_account(filename=credentials_path)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    return spreadsheet.worksheet(sheet_name)
