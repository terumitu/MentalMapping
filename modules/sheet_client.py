"""Google Sheets 接続ヘルパ（log_writer / log_reader から分離）。

このモジュールのみが gspread / yaml に依存する。
log_writer.py と log_reader.py は Worksheet Protocol しか要求しないため、
gspread 未インストール環境でも単体テストが通る。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

PathLike = Union[str, Path]
DEFAULT_FALLBACK_SHEET = "mood_log"

# プロジェクトルート基準の絶対パス。
# Streamlit を任意の CWD から起動しても同じファイルを読み込めるようにする。
# （相対パスだと `streamlit run` の起動ディレクトリに依存し、
#  古い/別プロジェクトの config を掴むリスクがあった。）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = _PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_CREDENTIALS_PATH = _PROJECT_ROOT / "config" / "credentials.json"

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def load_settings(path: PathLike = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    """settings.yaml を辞書で返す。"""
    import yaml  # 遅延 import: yaml 未導入環境でも log_writer/log_reader は使える

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_sheet_name(
    settings: Dict[str, Any], user_key: Optional[str] = None
) -> str:
    """user_key に紐づく sheet_name を返す。

    解決順:
      1. users[user_key].sheet_name
      2. users[settings.default_user].sheet_name（user_key=None のとき）
      3. users が未定義のときのみ google_sheets.sheet_name にフォールバック
      4. DEFAULT_FALLBACK_SHEET

    未知の user_key を渡した場合は ValueError。
    users が定義されているにも関わらず user_key / default_user で
    解決できない場合も ValueError。黙って google_sheets.sheet_name に
    フォールバックすると「全員同じシートに書き込む」事故が起きるため。
    """
    users = settings.get("users") or {}
    if users:
        key = user_key if user_key is not None else settings.get("default_user")
        if key is None:
            raise ValueError(
                "users is defined but neither user_key nor default_user is set"
            )
        if key not in users:
            raise ValueError(f"unknown user_key: {key!r}")
        sheet = users[key].get("sheet_name")
        if not sheet:
            raise ValueError(f"users[{key!r}].sheet_name is not set")
        return str(sheet)
    gs_cfg = settings.get("google_sheets") or {}
    return str(gs_cfg.get("sheet_name") or DEFAULT_FALLBACK_SHEET)


def connect_worksheet(
    settings_path: PathLike = DEFAULT_SETTINGS_PATH,
    sheet_name: Optional[str] = None,
) -> Any:
    """settings.yaml に従い、指定された Worksheet を開いて返す。

    sheet_name が None のときは ``google_sheets.sheet_name`` にフォールバックする。
    マルチユーザー呼び出し側は :func:`resolve_sheet_name` で解決した値を渡す想定。

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
    effective_sheet = sheet_name or gs_cfg.get("sheet_name") or DEFAULT_FALLBACK_SHEET

    if not spreadsheet_id:
        raise ValueError("google_sheets.spreadsheet_id is not set in settings.yaml")

    creds = _load_credentials(gs_cfg.get("credentials_path"))

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet.worksheet(effective_sheet)


def _load_credentials(credentials_path: Any) -> Any:
    """Streamlit secrets 優先でサービスアカウント Credentials を返す。

    非 Streamlit 環境 (pytest 等) では ImportError を静かに握って
    ローカル JSON にフォールバックする。Streamlit は import できるが
    secrets アクセスや Credentials 構築に失敗した場合は st.warning で
    可視化した上でローカル JSON にフォールバックする (旧: bare except 握りつぶし)。
    """
    from google.oauth2.service_account import Credentials

    try:
        import streamlit as st  # 遅延 import
    except ImportError:
        st = None  # type: ignore[assignment]

    if st is not None:
        try:
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                return Credentials.from_service_account_info(
                    dict(st.secrets["gcp_service_account"]),
                    scopes=SCOPES,
                )
        except Exception as e:
            # secrets 形式不正 / Credentials 構築失敗等。握りつぶさず可視化。
            try:
                st.warning(
                    "st.secrets からの認証情報取得に失敗しました "
                    f"({type(e).__name__}: {e})。"
                    "ローカル credentials.json へフォールバックします。"
                )
            except Exception:
                pass

    # ローカル環境: credentials.json ファイルから取得
    local_path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS_PATH
    if not local_path.exists():
        raise FileNotFoundError(
            f"Service account credentials not found: {local_path}. "
            "Set Streamlit secrets 'gcp_service_account' or place credentials.json."
        )
    return Credentials.from_service_account_file(str(local_path), scopes=SCOPES)
