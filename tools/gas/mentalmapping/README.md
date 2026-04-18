# MentalMapping GAS バッチ (α-D)

`not_recorded` 日次自動生成 GAS バッチ。standalone Apps Script + clasp 管理。

## セットアップ手順

### 1. Apps Script プロジェクト作成 (ブラウザ作業)

1. [script.new](https://script.new) で standalone プロジェクト新規作成
2. プロジェクト名: `MentalMapping not_recorded batch`
3. URL から scriptId を取得 (`/projects/<scriptId>/edit` の `<scriptId>` 部分)

### 2. Script Properties 設定 (ブラウザ作業)

GAS エディタ → 左側メニュー「プロジェクトの設定」→「スクリプト プロパティ」:

| キー | 値 |
|-----|-----|
| `SPREADSHEET_ID` | `1S0cWK_0WIrxit8Yi0eK7Ocb-JHF99AsfxDCGPd0Hqao` |
| `DISCORD_WEBHOOK_URL` | Streamlit secrets.toml の `DISCORD_WEBHOOK_URL` と同値 |

### 3. Sheets 新設シート作成 (ブラウザ作業)

mood_log spreadsheet 内に以下 3 シートを新設する:

#### config_users (ヘッダ + 3 行)

| input_user | display_name | sheet_name | morning_start | morning_end | evening_start | evening_end | start_date |
|-----------|--------------|------------|---------------|-------------|---------------|-------------|------------|
| masuda | 増田舞 | mood_log_masuda | 06:00 | 16:00 | 17:00 | 26:00 | 2026-04-19 |
| nishide | 西出朋起 | mood_log_nishide | 10:00 | 14:00 | 17:00 | 26:00 | 2026-04-19 |
| suyasu | 須安麗子 | mood_log_suyasu | *(空)* | *(空)* | *(空)* | *(空)* | *(空)* |

`start_date` は α-D が遡及開始する日 (= GAS バッチの起点)。Python 側の
`NOT_RECORDED_START_DATES` (α-C マイグレーションの起点) とは別概念。

任意の window セルが空のユーザーは **pending** 扱いで not_recorded 生成対象外。

#### config_exclude (ヘッダ + 1 行)

| input_user | date | time_of_day | reason |
|-----------|------|-------------|--------|
| masuda | 2026-04-16 | morning | row 12 manual add (mm_notes #1) |

Python 側 `devtools/migrate_v1_2_steps_populate.NOT_RECORDED_EXCLUDE` と
内容一致必須。変更時は両方同時更新 + mm_notes 起票。

#### gas_batch_log (ヘッダのみ)

| execution_at | mode | target_date_range | users_scanned | gaps_generated | errors | elapsed_ms |
|-------------|------|--------------------|---------------|----------------|--------|------------|

### 4. clasp セットアップ

```powershell
cd C:\Python\MentalMapping\tools\gas\mentalmapping
copy .clasp.json.example .clasp.json
```

`.clasp.json` を編集して `scriptId` に手順 1 で取得した ID を設定:

```json
{
  "scriptId": "<取得した scriptId>",
  "rootDir": "",
  "scriptExtensions": [".gs"],
  "jsonExtensions": [".json"]
}
```

```powershell
clasp push
```

`.clasp.json` は `.gitignore` 対象 (scriptId の個別管理のため)。

### 5. 動作確認

GAS エディタで関数を選択して「実行」:

| 順番 | 関数 | 期待 |
|------|------|-----|
| 1 | `testConfigRead` | 実行ログに config_users/config_exclude の内容 |
| 2 | `testNotifyDiscord` | Discord に疎通テスト通知 |
| 3 | `testScanGapsMasuda` | masuda の gap 一覧 |
| 4 | `testScanGapsNishide` | nishide の gap 一覧 |
| 5 | `testScanGapsSuyasu` | `suyasu: pending (skipped)` が 1 行 |
| 6 | `runInitialBackfillDry` | gas_batch_log に `initial_backfill_dry` 追記 / Discord サマリ |
| 7 | `runInitialBackfill` | 実 append / gas_batch_log に `initial_backfill_exec` 追記 |
| 8 | (再実行) `runInitialBackfill` | 冪等性確認 (total=0) |
| 9 | `runDailyBatch` | 前日分 gap 生成 / gas_batch_log に `daily` 追記 |

### 6. time-driven trigger 登録

GAS エディタ →「トリガー」→「トリガーを追加」:

- 実行する関数: `runDailyBatch`
- デプロイ時に実行: `Head`
- イベントのソース: 時間主導型
- 時間ベースのトリガー: 日タイマー
- 時刻: 午前 3 時〜午前 4 時 (内部で 03:00 JST 付近になる)

## ファイル構成

| ファイル | 責務 |
|---------|------|
| `appsscript.json` | manifest (Asia/Tokyo / V8 / STACKDRIVER) |
| `main.gs` | エントリーポイント / Lock / テスト関数 |
| `config_reader.gs` | config_users / config_exclude 読込 |
| `not_recorded_generator.gs` | gap 検出 / 冪等性二段確認 / 生成 |
| `sheet_writer.gs` | 17 列行構築 / append / 既存スロット検出 |
| `notifier.gs` | Discord Webhook / gas_batch_log 追記 |
| `util.gs` | JST 時刻 / ISO lenient / record_id / Spreadsheet open |

## 関連ドキュメント

- 設計書: `docs/arch_mentalmap_v1_2.md` v1.2.2 §4.3.2 / §6.5 / §A.7
- 運用記録: `docs/mm_notes_001-100.md` #7 (α-D 起動時の仕様申し送り)
- Python 側定数: `devtools/migrate_v1_2_steps_populate.py`
  - `NOT_RECORDED_START_DATES` (α-C の起点 / 別概念)
  - `NOT_RECORDED_EXCLUDE` (config_exclude シートと内容一致必須)
