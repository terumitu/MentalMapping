# CLAUDE.md — MentalMapping

**対象**: 実装担当 Window
**更新者**: alpha Window のみ

---

## 0. 作業開始時チェック（必須）

```powershell
cd C:\Python\MentalMapping
```

- 作業ディレクトリが `C:\Python\MentalMapping\` であること
- 本プロジェクトは Streamlit Cloud にデプロイされる。ローカル動作確認後に push すること

---

## 1. プロジェクト基本情報

| 項目 | 値 |
|------|-----|
| パス | C:\Python\MentalMapping\ |
| 用途 | 増田用ムードトラッキングアプリ（Streamlit Cloud） |
| Python | 3.12 |
| エンコーディング | BOM-free UTF-8 厳守 |
| テスト | pytest（conftest.py はルート直下、`pytest tests/` で実行） |
| デプロイ | Streamlit Cloud（push で自動反映） |
| タイムゾーン | JST 固定（UTC 変換禁止） |
| データ管理 | Google Sheets（ユーザーごとにシート分離） |

---

## 2. ディレクトリ構成

```
MentalMapping/
  app.py               エントリーポイント（Streamlit）
  conftest.py          pytest 共通フィクスチャ
  requirements.txt
  config/
    settings.yaml
    credentials.json   ← push 禁止（§7 参照）
  modules/             ※ src/ ではなくこのパスが正
    __init__.py
    chart_builder.py   チャート構築
    log_reader.py      ログ読み取り
    log_writer.py      ログ書き込み
    sheet_client.py    Google Sheets 連携
  tests/
    test_log_reader.py
    test_log_writer.py
    test_sheet_client.py
```

---

## 3. 層別責務

| 層 | パス | 責務 | 禁止 |
|----|------|------|------|
| エントリー | app.py | Streamlit UI・画面遷移 | ビジネスロジック直書き |
| チャート | modules/chart_builder.py | 可視化データ構築 | Sheets 操作・UI |
| 読取 | modules/log_reader.py | Sheets からのログ取得 (active フィルタ / revision chain) | 書き込み・UI |
| 書込 | modules/log_writer.py | MoodLogEntry バリデーション + Sheets への append | 読取・UI・鎖更新・窓判定 |
| entry_mode | modules/entry_mode.py | realtime_window 窓判定 (§4.3) | Sheets I/O・UI・鎖更新 |
| 鎖構造 | modules/record_chain.py | record_id 生成 / find_active / supersede_active / get_revision_chain (§4.4 / §A.3 / §A.4) | MoodLogEntry 生成・窓判定・UI |
| 接続 | modules/sheet_client.py | Google Sheets API 接続管理 | ビジネスロジック |

---

## 4. コーディング規約

| 基準 | 値 |
|------|-----|
| ファイル hard_limit | 500行（絶対上限） |
| 関数最大行数 | 50行 |
| 循環的複雑度 | CC <= 10 |

**孤児コードの扱い**:
自分の変更によって不要になった import / 変数 / 関数は削除する。
変更前から存在していた死骸コードには触れない。

**JST 制約**:
- 日時処理は JST 固定。`datetime.utcnow()` 使用禁止
- `Asia/Tokyo` を明示的に指定すること

**マルチユーザー制約**:
- ユーザーごとのシート分離を破壊する変更を行わない
- sheet_client.py のユーザー識別ロジックを変更する場合は西出に確認すること

---

## 5. 絶対禁止事項

- 500行超のファイル生成・編集
- 指示されていないファイルの変更・追加
- `config/credentials.json` の push（§7 参照）
- UTC 基準の日時処理
- ユーザー間のシートデータ混在を招く変更

---

## 6. Plan モード（必須トリガー）

以下のいずれかに該当する場合、実装開始前に必ず `/plan` で計画を立てること:

- ステップ数が 3 以上のタスク
- 複数ファイルへの書き込みを伴うタスク
- Google Sheets スキーマ変更を伴うタスク

計画中に以下が判明した場合は即座に停止し、西出に報告すること:

- 設計の前提が崩れている
- スコープが指示範囲を超える

> 「作りながら考えるな。おかしくなったら即停止・再計画。」

---

## 7. Git 運用ルール

**commit タイミング**:
- タスク完了時に commit + push（Streamlit Cloud に即反映される点に注意）
- 動作未確認のまま push しない

**commit メッセージ形式**:

```
feat: 新機能実装
fix:  バグ修正
chore: ドキュメント・設定・整備
refactor: リファクタリング
```

**push 禁止事項**:
- `config/credentials.json` / `.env` / APIキーを含むファイルを push しない
- force push は Claude Code から行わない（西出の明示許可が必要）

---

## 8. 完了報告フォーマット

完了報告前に自問すること:
- □ テストは実際に通っているか（`pytest tests/` を実行したか）
- □ 変更は指示されたファイル・スコープのみに留まっているか
- □ 500行 hard_limit を超えていないか
- □ JST 固定・マルチユーザー分離を維持しているか

```
【完了報告】
- 完了タスク: （概要）
- 成果物: ファイルパス（実測行数）
- テスト結果: pass N件 / fail 0件
- 変更サマリー: （何をどう変えたか 1〜2行）
- 発見事項: （あれば）
- 未完了: （あれば）
```

---

## 9. Sheets 直接編集時の同期義務

Google Sheets を **アプリを介さずに直接編集**（行追加・行削除・cell 値書き換え等）した場合、
編集者は以下 3 点を**同時に実施する義務**を負う:

1. **mm_notes に事実記録**: 日時・内容・理由・編集者を `docs/mm_notes_001-100.md` に
   採番起票する
2. **設計書の該当箇所確認・修正**: `docs/arch_mentalmap_v1_X.md` の該当セクション
   （§A.5 マイグレーション関連 / §4.x データ仕様 等）を確認し、実態と乖離があれば改訂する
3. **進行中 Sprint の担当 α に通知**: 影響範囲のあるタスクを実施中の α-X に通知し、
   実装側のハードコード除外（NOT_RECORDED_EXCLUDE 等）が必要かを確認する

### 背景

- MentalMapping v1.2 Sprint で以下の Sheets 直接編集事例が発生:
  - パターン 2a: 訂正試行レコードの直接削除（04-16 20:34 evening / 04-17 11:18 morning）
  - パターン 2b: 記録漏れの遡及追加（row 12: 04-16 T9:34:37 morning）
  - パターン 2c: time_of_day 入力ミス（row 11 / row 15）
  - パターン 2d: 入力ミスの事後訂正（row 15）
- いずれも **設計書記述と実データの乖離**を引き起こし、α-C / α-B の作業に手戻りを発生させた
- 詳細は `docs/mm_notes_001-100.md` #1 / #2 / #3 / #5 を参照

### 適用範囲

- Sheets を**意図的に**直接編集する全ケースに適用（バックアップ取得・スナップショットは除く）
- 編集が**緊急対応**の場合でも、対応完了後に遡って 3 点同時実施すること
- 違反時は本ルールに基づきレビュー・修正タスクを起票する
