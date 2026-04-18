# mm_notes 001-100

MentalMapping プロジェクト運用上の注意事項・決定事項の採番記録。
100 件到達で `mm_notes_101-200.md` に移行する。

MentalMapping 独立連番で #1 から開始（v5.0 側の採番と衝突は気にしない・別プロジェクト体系）。

---

## #1 masuda 2026-04-16 morning レコード手動追加事例（§A.5.6 誤記の契機）

- **採番日**: 2026-04-19
- **採番起票**: α-C
- **実施者（Sheets 編集）**: 西出

### 事実

- `mood_log_masuda` row 12 として以下のレコードが手動追加された。
- α-C Phase 1 実行（2026-04-18 23:04 JST）時点では存在せず、
  Phase 2 着手時点（2026-04-19）で発見された。
- 経緯: 増田本人から「04-16 朝も記録していたつもり」との申告があり、
  西出が Sheets に遡及登録した。

### 追加レコードの内容（ステップ 4+5+8 実行前の snapshot）

| 列 | 値 |
|----|----|
| date | `2026-04-16` |
| mood / energy / thinking / focus | `3 / 3 / 3 / 3` |
| sleep_hours | `7` |
| weather | `晴` |
| medication / period | `TRUE / TRUE` |
| recorded_at | **`2026-04-16T9:34:37`**（単桁時・ISO 8601 非準拠） |
| time_of_day | `morning` |
| daily_aspects | アスペクト情報（既存パイプラインで生成されたと想定） |
| record_id 〜 input_user (M〜Q) | 空（ステップ 4+5+8 で付与済）|

### 設計書への影響

- 設計書 `docs/arch_mentalmap_v1_2.md` §A.5.6 の
  「masuda 2026-04-16 morning → not_recorded 生成」が**誤記となった**。
- 訂正は **v1.2.2 改訂で実施**（α-C Phase 2 完了後・α-B または後継スコープ）。
- Phase 2 ステップ 10 実装側で `NOT_RECORDED_EXCLUDE = {("masuda", "2026-04-16", "morning")}`
  としてハードコード除外済（`devtools/migrate_v1_2_steps_populate.py`）。

### 副次的な発見事項

- `recorded_at` が単桁時刻 `T9:34:37` で登録されており、Python の
  `datetime.fromisoformat()` で拒否される。
- 対応として `migrate_v1_2.parse_iso_jst()` にゼロパディング lenient 化を実装
  （`_normalize_iso_jst`）。表示値は変更せず、内部処理のみ正規化。

### 新ルール「Sheets 直接編集時の同期義務」との関係

- 本件は同ルール制定前の編集のため直接違反ではないが、**ルール制定の契機**
  となった事例。
- 今後同種の Sheets 直接編集を行う場合は以下 3 点を同時実施する:
  1. mm_notes に事実を記録（日時・内容・理由）
  2. 設計書 `arch_mentalmap_v1_X.md` の該当箇所を確認・修正
  3. 進行中 Sprint があれば α-X に通知

### 未確定事項（西出回答待ち）

- [要・西出回答] **正確な追加日時**（Google Sheets のバージョン履歴で特定可能）
- [要・西出回答] **recorded_at 単桁時刻 `T9:34:37` の原因**
  - 入力ミスか、旧 Streamlit 実装の出力不備か、その他か
  - 今後同じパターンの発生を抑止する対策が必要かどうかの判断材料
