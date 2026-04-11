"""sheet_client.resolve_sheet_name のユーザー→シート名マッピングテスト。

gspread / google-auth 非依存の純粋ロジックのみをテストする
（connect_worksheet 本体は外部接続が必要なため対象外）。
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from modules.sheet_client import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_FALLBACK_SHEET,
    DEFAULT_SETTINGS_PATH,
    resolve_sheet_name,
)


def _settings() -> Dict[str, Any]:
    return {
        "google_sheets": {"sheet_name": "mood_log"},
        "users": {
            "masuda": {
                "display_name": "増田舞",
                "sheet_name": "mood_log_masuda",
            },
            "nishide": {
                "display_name": "西出朋起",
                "sheet_name": "mood_log_nishide",
            },
        },
        "default_user": "masuda",
    }


# ---- 基本マッピング --------------------------------------------------------


def test_resolve_masuda_to_mood_log_masuda() -> None:
    assert resolve_sheet_name(_settings(), "masuda") == "mood_log_masuda"


def test_resolve_nishide_to_mood_log_nishide() -> None:
    assert resolve_sheet_name(_settings(), "nishide") == "mood_log_nishide"


def test_resolve_none_uses_default_user() -> None:
    # user_key を省略すると default_user の値が選ばれる
    assert resolve_sheet_name(_settings(), None) == "mood_log_masuda"


def test_resolve_default_can_be_overridden() -> None:
    settings = _settings()
    settings["default_user"] = "nishide"
    assert resolve_sheet_name(settings, None) == "mood_log_nishide"


# ---- フォールバック / エラー ----------------------------------------------


def test_resolve_unknown_user_raises() -> None:
    with pytest.raises(ValueError, match="unknown user_key"):
        resolve_sheet_name(_settings(), "unknown")


def test_resolve_without_users_falls_back_to_google_sheets_sheet_name() -> None:
    settings: Dict[str, Any] = {"google_sheets": {"sheet_name": "legacy_sheet"}}
    assert resolve_sheet_name(settings, None) == "legacy_sheet"


def test_resolve_empty_settings_returns_default_fallback() -> None:
    assert resolve_sheet_name({}, None) == DEFAULT_FALLBACK_SHEET


# ---- strict モード: users 定義ありで解決不能な場合は raise ----------------


def test_resolve_users_defined_no_default_no_user_key_raises() -> None:
    """users 定義ありで user_key/default_user どちらも無いとき黙って
    google_sheets.sheet_name にフォールバックしない（全員同じシートに
    書き込む事故を防ぐ）。"""
    settings = _settings()
    del settings["default_user"]
    with pytest.raises(ValueError, match="neither user_key nor default_user"):
        resolve_sheet_name(settings, None)


def test_resolve_users_defined_but_user_sheet_missing_raises() -> None:
    settings = _settings()
    settings["users"]["masuda"] = {"display_name": "増田舞"}  # sheet_name 無し
    with pytest.raises(ValueError, match="sheet_name is not set"):
        resolve_sheet_name(settings, "masuda")


# ---- デフォルトパス: モジュール基準で絶対化されている --------------------


def test_default_paths_are_absolute() -> None:
    """Streamlit の起動 CWD に依存せず同じファイルを読むために
    デフォルトパスはプロジェクト基準の絶対パスでなければならない。"""
    assert DEFAULT_SETTINGS_PATH.is_absolute()
    assert DEFAULT_CREDENTIALS_PATH.is_absolute()
    assert DEFAULT_SETTINGS_PATH.name == "settings.yaml"
    assert DEFAULT_CREDENTIALS_PATH.name == "credentials.json"
