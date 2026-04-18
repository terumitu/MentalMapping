# MentalMapping アーキテクチャ設計書 v1.2.1

**作成日**: 2026-04-18
**前版**: arch_mentalmap_v1_1.md（2026-04-18 同日付・実装未追従の暫定版）
**ステータス**: Phase 1 実装実態追従版（α-A 先行調査を経て確定）

---

## 1. プロジェクト基本情報

| 項目 | 値 |
|------|-----|
| プロジェクト名 | MentalMapping |
| 配置 | `C:\Python\MentalMapping\`（独立リポジトリ） |
| 対象ユーザー | 増田舞 / 西出朋起 / 須安麗子（3名・非公開・商用化予定なし。須安は**休眠ユーザー**扱い） |
| 目的 | 気分/状態記録 × Transit オーバーレイによる個人傾向把握 |
| AstroEngine との関係 | Phase 2 以降で出力データを参照（コード依存なし・JSON参照のみ） |

---

## 2. 技術スタック

| 項目 | 値 |
|------|-----|
| 実行環境 | Streamlit Cloud |
| バックエンド | Python 3.12 |
| データ保存 | Google Sheets（gspread） |
| グラフ描画 | Plotly |
| AstroEngine 連携 | JSON ファイル参照（Phase 2〜） |
| バッチ実行 | GAS（Google Apps Script）: not_recorded 自動生成の日次バッチ（§4.3 / §A.7） |

---

## 3. ディレクトリ構造

```
C:\Python\MentalMapping\
  app.py
  modules/
    log_writer.py
    log_reader.py
    chart_builder.py
    sheet_client.py
    discord_notifier.py
    transit_loader.py       # Phase 2
    overlay_builder.py      # Phase 2
    correlation_engine.py   # Phase 3
  config/
    settings.yaml
    credentials.json        # gitignore
  requirements.txt
  .streamlit/
    secrets.toml
```

---

## 4. ログ仕様（v1.2 確定版）

### 4.1 入力項目（全17フィールド / Sheets 列 A〜Q）

| # | フィールド | 型 | 必須 | 列 | 備考 |
|---|-----------|-----|------|----|------|
| 1 | date | date | ✅ | A | 記録対象日（デフォルト: 今日） |
| 2 | mood | int 1-5 | ✅ | B | 気分 |
| 3 | energy | int 1-5 | ✅ | C | エネルギー |
| 4 | thinking | int 1-5 | ✅ | D | 思考の働き |
| 5 | focus | int 1-5 | ✅ | E | 集中度 |
| 6 | sleep_hours | float | — | F | 任意。0.5刻み。0-24 |
| 7 | weather | enum | — | G | 内部 enum 値を日本語リテラルで `晴` / `曇` / `雨/雪` の 3 値に確定（§4.1.1 備考）|
| 8 | medication | bool or null | — | H | 服薬有無 |
| 9 | period | bool or null | — | I | 生理有無（該当者のみ） |
| 10 | recorded_at | datetime | 自動 | J | 記録タイムスタンプ（JST `YYYY-MM-DDTHH:MM:SS`） |
| 11 | time_of_day | enum | ✅ | K | morning / evening（**ラジオボタン主観申告**） |
| 12 | daily_aspects | str | 自動 | L | Phase 2 で自動生成。Phase 1 は空文字 |
| 13 | record_id | str | 自動 | M | `{input_user}_{date}_{time_of_day}_{unix_ts}` |
| 14 | record_status | enum | 自動 | N | active / superseded |
| 15 | superseded_by | str or null | — | O | 訂正時のみ次レコードの record_id（採用されなかった訂正試行は null） |
| 16 | entry_mode | enum | 自動 | P | realtime / retroactive / not_recorded / pending（§4.3） |
| 17 | input_user | enum | ✅ | Q | masuda / nishide / suyasu（**毎回ユーザー選択必須**） |

> v1.1 との差分: input_user 列を Q に新設（17列化）。entry_mode 判定ロジックを wake_time ベース → realtime_window 窓判定に全面変更。weather の内部 enum 値を `雨` → `雨/雪` に変更（実装値は 3 値のまま、日本語リテラル運用維持）。time_of_day を selectbox/自動判定 → ラジオボタン主観申告に変更。

#### 4.1.1 weather の意図（備考）

- 内部 enum 値は日本語リテラル `晴` / `曇` / `雨/雪` とする。英字化は v1.2 スコープ外
- `雨/雪` は気象カテゴリと**ユーザー主観状態（低気圧への反応）**の折衷表現
  - 大阪市での降雪頻度は低く、対象ユーザーは低気圧全般に主観状態が影響されるため、雨と雪を同カテゴリで扱う
- 将来「低気圧」等の**抽象カテゴリへのリネーム余地**あり（Phase 3 以降の検討事項）

### 4.2 time_of_day の定義（ラジオボタン主観申告）

**time_of_day は主観状態ラベルである。物理時刻からの自動判定は行わない。**

| UI ラベル（ユーザー表示） | DB 保存値 |
|--------------------------|----------|
| 起き抜け | morning |
| 夜落ち着いた時 | evening |

UI 仕様:

- **ラジオボタン**による 2 択
- **デフォルト選択なし**（ユーザーが明示的に選ぶまで「記録する」ボタンを無効化）
- ユーザーが「いま自分はどちらを記録するか」を意識的に申告する設計

参考運用ガイド（判定ロジックの一部としては使わない）:

- 推奨: morning は起床後落ち着いた最初のタイミングで早めに記録
- ただし「記録時刻が起床後 40 分超なら自動的に retroactive」という旧 v1.1 ロジックは**廃止**
- entry_mode は realtime_window 判定に分離（§4.3）

### 4.3 entry_mode 判定ロジック（v1.2 全面書き換え）

`entry_mode` は 4 値の enum: `realtime` / `retroactive` / `not_recorded` / `pending`。

**判定ベース**: wake_time（起床時刻）は使用しない。`recorded_at` がユーザー毎に設定された
`morning_realtime_window` / `evening_realtime_window` の範囲内に収まるかで判定する。
さらに「該当時間帯に active レコードが存在しない」状態を `not_recorded` として明示的に
データ化する（§6.5 未入力もデータである原則）。

#### 4.3.1 ユーザー入力レコードの判定（realtime / retroactive）

```
if time_of_day == "morning" and recorded_at.time() ∈ users[input_user].morning_realtime_window:
    entry_mode = "realtime"
elif time_of_day == "evening" and recorded_at.time() ∈ users[input_user].evening_realtime_window:
    entry_mode = "realtime"
else:
    entry_mode = "retroactive"
```

境界解釈は `[start, end)`（start 含む / end 含まない）。詳細は §4.7。

#### 4.3.2 未入力時の自動生成（not_recorded）

該当時間帯に active レコードが不在のまま窓終端を過ぎた場合、GAS バッチが
`entry_mode=not_recorded` の active レコードを自動追記する。

**生成トリガー**:
- morning: `morning_realtime_window.end` を過ぎた時刻で、対象 `(input_user, date, morning)`
  に active レコードが存在しない場合
- evening: `evening_realtime_window.end`（翌日深夜）を過ぎた時刻で、対象
  `(input_user, date, evening)` に active レコードが存在しない場合

**not_recorded レコードの構造**:

| 列 | 値 |
|----|-----|
| A: date | 対象日 |
| B〜E: mood/energy/thinking/focus | null |
| F: sleep_hours | null |
| G: weather | null |
| H: medication | null |
| I: period | null |
| J: recorded_at | バッチ実行時刻（JST） |
| K: time_of_day | `morning` または `evening` |
| L: daily_aspects | 空文字（Phase 2 で埋める） |
| M: record_id | `{input_user}_{date}_{time_of_day}_{unix_ts_of_generation}` |
| N: record_status | `active` |
| O: superseded_by | null |
| P: entry_mode | `not_recorded` |
| Q: input_user | 対象ユーザー |

**冪等性**: 同一 `(input_user, date, time_of_day)` で既に任意の record_status
（active / superseded いずれも）のレコードが存在する場合、not_recorded は**生成しない**。

#### 4.3.3 責務分離（重要）

- 同日 2 件目記録による自動 retroactive 判定は**行わない**
- 訂正の表現は `record_status` の責務（§4.4）であり、`entry_mode` とは責務分離する
- `realtime` / `retroactive` は「その記録が realtime 窓内で行われたか」のメタデータ
- `not_recorded` は「ユーザーが記録しなかったこと」を表すメタデータかつ観察対象（§6.5）

#### 4.3.4 realtime_window 未定義時の判定（pending）

ユーザーの morning_realtime_window / evening_realtime_window が settings.yaml
に未定義の場合、entry_mode は `pending` を付与する。

`pending` の意味:
- 「realtime_window 未定義のため判定保留」を表す
- 将来 realtime_window が確定した時点で、recorded_at と照合して
  realtime / retroactive に再判定する

`pending` 再判定の運用ルール:
- realtime_window 確定時、該当ユーザーの pending レコードを全件抽出
- 各レコードの recorded_at と新 realtime_window で判定
- pending → realtime または pending → retroactive へ更新
- この更新は entry_mode 列のみの書き換えであり、record_status 鎖構造には
  影響しない（例外的な既存値書き換え操作）
- 更新履歴は mm_notes に記録する
- 再判定バッチは devtools/rebalance_pending.py として将来実装
  （suyasu realtime_window 確定時に着手）

### 4.4 record_status と訂正機能（鎖構造）

**正規化ルール**: 同一 `(input_user, date, time_of_day)` において `record_status=active` は常に1件以内。

**訂正フロー（鎖構造）**:

1. 既存 active レコード R1 がある状態で、同一 `(input_user, date, time_of_day)` に訂正レコード R2 を追記
2. R1.record_status = `superseded`
3. R1.superseded_by = R2.record_id
4. R2.record_status = `active`
5. さらに R2 を R3 で訂正する場合、R2 も superseded に遷移し、R2.superseded_by = R3.record_id（複数回訂正可）

**鎖の解釈規則**:

- `superseded` かつ `superseded_by != null` → 鎖の中間ノード（次レコードに引き継がれた）
- **`superseded` かつ `superseded_by == null` → 鎖の末端で「採用されなかった訂正試行」を表す**
  - ユーザーが訂正レコードを書こうとして直後に判断を翻し、元の active を維持したケースを保存する用途
  - 例: 増田 04-17 11:18 morning（後述 §A.5.2 参照）
- `active` かつ `superseded_by == null` → 現行採用レコード（常に 1 件以内）

**スコープと input_user の関係**:

- 訂正の同一性判定は `(input_user, date, time_of_day)` で行う（physical_worksheet ではなく **input_user**）
- 理由: 誤入力修正時に input_user 値そのものを変更した場合も、同じユーザー主体内で鎖の一貫性を保つため

**データ保全**: superseded レコードは**物理削除しない**。

#### 4.4.1 not_recorded → retroactive 昇格

ユーザーが `not_recorded` レコード生成後に遡って記録を行った場合、鎖構造による昇格が発生する。

1. 既存 `not_recorded` レコード N1（active）が存在する状態で、ユーザーが同一
   `(input_user, date, time_of_day)` にレコード R2 を追記する
2. R2 は realtime 窓外からの入力のため `entry_mode=retroactive` になる（§4.3.1）
3. N1.record_status: `active` → `superseded`
4. N1.superseded_by: `null` → `R2.record_id`
5. R2.record_status: `active`, R2.superseded_by: null

**鎖の解釈**: not_recorded は active の一形態として鎖に乗る。昇格後も not_recorded の
事実は superseded レコードとして保持されるため、「記録しなかった期間が後日補完された」
履歴が失われない。

### 4.5 Google Sheets 構造（17列）

| A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| date | mood | energy | thinking | focus | sleep_hours | weather | medication | period | recorded_at | time_of_day | daily_aspects | record_id | record_status | superseded_by | entry_mode | input_user |

- 1行1レコード・追記のみ（UPDATE は record_status / superseded_by の 2 列のみに限定）
- 同一 `(input_user, date, time_of_day)` の active は最大 1 件、superseded を含めれば任意件数

### 4.6 マルチユーザー運用

#### 4.6.1 worksheet 分離（同一 spreadsheet 内）

実装実態に合わせて以下を確定する（v1.1 の「別スプレッドシート」記述は誤り）:

- spreadsheet_id は**全ユーザー共通**（1 個）
- worksheet（タブ）名で分離:

| input_user | worksheet 名 |
|-----------|--------------|
| masuda | mood_log_masuda |
| nishide | mood_log_nishide |
| suyasu | mood_log_suyasu（休眠ユーザー・運用未開始） |

- 物理分離: worksheet 単位
- 論理分離: `input_user` 列（§4.6.2）

**suyasu 運用注記**: suyasu は実装対象だが、Phase 1 時点で記録行動が定着していない。
settings.yaml への realtime_window 設定追加は**入力再開時に判断**する（§4.7 参照）。

#### 4.6.2 input_user と physical_worksheet の整合性チェック

**期待値**: `input_user == physical_worksheet_owner`（worksheet 名に対応するユーザー）

**乖離時の二段防衛**:

(A) リアルタイムチェック（Streamlit UI）:
- 記録ボタン押下時に Streamlit が `input_user` と現在開いている worksheet を照合
- 不一致なら **警告表示**（赤バッジ・モーダル等）
- ブロックはせず、ユーザー判断で続行可能（誤入力修正の意図的入力もありうるため）
- 実装責務: app.py / log_writer.py（α-B 担当）

(B) 遡及チェック（バッチ）:
- α-C のマイグレーション処理が既存データを全スキャン
- input_user 値と worksheet 所有者が乖離するレコードを列挙
- 西出が手動で訂正判断（input_user 修正 / レコードの superseded 化 等）
- 実装責務: devtools 配下スクリプト（α-C 担当）

### 4.7 settings.yaml スキーマ（v1.2 確定版）

旧 `time_of_day.morning_start / evening_start`（自動判定境界）は**廃止**し、ユーザー毎の
realtime_window 設定に統合する。

```yaml
google_sheets:
  spreadsheet_id: "<single shared id>"
  credentials_path: "config/credentials.json"

users:
  masuda:
    display_name: "増田舞"
    sheet_name: "mood_log_masuda"
    morning_realtime_window: ["06:00", "16:00"]
    evening_realtime_window: ["17:00", "26:00"]
  nishide:
    display_name: "西出朋起"
    sheet_name: "mood_log_nishide"
    morning_realtime_window: ["10:00", "14:00"]
    evening_realtime_window: ["17:00", "26:00"]
  # suyasu は休眠ユーザー。入力再開時に窓設定を決定する。
  # suyasu:
  #   display_name: "須安麗子"
  #   sheet_name: "mood_log_suyasu"
  #   morning_realtime_window: [TBD]
  #   evening_realtime_window: [TBD]
default_user: "masuda"
```

**境界時刻の解釈規則**: `[start, end)`（start inclusive / end exclusive）

- 例: morning_realtime_window `["06:00", "16:00"]`
  - `06:00:00` ちょうどは realtime
  - `15:59:59` は realtime
  - `16:00:00` ちょうどは retroactive
- evening 上限 `26:00` は **翌日 02:00 JST** を意味する（深夜入力を許容）
  - 実装上は recorded_at の time() を [17:00, 24:00) ∪ [00:00, 02:00) として扱う

**廃止項目**:
- `time_of_day.morning_start` / `time_of_day.evening_start`（v1.1 まで存在した自動判定境界）
- `mood_log_columns`（17 列固定化により廃止可能。α-B 判断）

**依存コード対応**: log_writer.determine_time_of_day() / app.py._default_time_of_day() は α-B が削除/置換する。

---

## 5. Phase 別スコープ

### Phase 1：ログ基盤

**完了条件**:
- 17 フィールド入力 UI（time_of_day はラジオ・デフォルト選択なし・input_user 選択必須）
- Google Sheets 保存（列 A〜Q）
- record_status / superseded_by の自動運用（鎖構造）
- entry_mode の realtime_window 窓判定による自動付与
- input_user 整合性リアルタイムチェック（§4.6.2 (A)）
- カレンダービュー（月表示・色分け）
- 4指標折れ線グラフ（週/月切り替え）

**UI 設計原則**:
- スマホ縦画面で完結
- 入力操作は 30 秒以内
- mood/energy/thinking/focus と time_of_day と input_user 以外はすべてスキップ可能
- 訂正モード（既存 active を上書きに見える UI で内部は鎖構造で追記）

### Phase 2：Transit オーバーレイ

**前提条件**: Phase 1 完了 + 気分記録 30 日以上蓄積

**使用データ（AstroEngine v5.0 出力 JSON）**:

| データ種別 | 用途 | 対象天体 |
|-----------|------|---------|
| Transit to Natal（アスペクト） | 日次の天体圧力 | 土星・木星・冥王星・天王星・海王星 優先 |
| Transit House ingress | 活性化ハウス推移 | 全惑星 |
| Profection（月次） | 静的コンテキスト表示のみ | — |
| Firdaria（期間主星） | 静的コンテキスト表示のみ | — |

**Phase 2 申し送り事項（v1.2 確定 / v1.1 から反転）**:

- Transit 計算時刻は **`recorded_at` を使用する**（**選択肢 1**・v1.1 の選択肢 2 から反転）
- 反転理由:
  > ラジオで「起き抜け」を申告した時点で、ユーザーはその瞬間を朝の基底状態として申告している。
  > 選択肢 2（主観時間帯中心の固定時刻）を採用すると、実際にユーザーが申告した瞬間から数時間
  > ズレた Transit が割り当てられ、主観状態と Transit の対応が歪む。
  > したがって recorded_at を使用する。
- 分析対象は `record_status=active` のレコードのみ
- `entry_mode=retroactive` の扱いは Phase 2 設計着手時に再検討。選択肢:
  - 除外（realtime のみで分析）
  - 重み減（retroactive は寄与度を下げる）
  - 別集計（realtime / retroactive を別系列として並走表示）
- daily_aspects 列は Phase 2 で自動計算し埋める（Phase 1 は空文字）

### Phase 3：相関スコア・傾向サマリー

**前提条件**: 記録 180 日以上

**内容**:
- Transit 種別 × 各指標（mood/energy/thinking/focus）の相関係数算出
- 「この配置の時期に重くなる傾向（n=X件）」サマリー
- 月次レポート自動生成

---

## 6. 設計原則・制約

### 6.1 観測装置原則との整合
AstroEngine は天体状態の時系列を渡すのみ（評価しない）。Transit × 気分の判定は MentalMapping
アプリケーション層の責務。AstroEngine 側への改変は行わない。

### 6.2 n=1 前提
統計的有意性は目的としない。サマリー表示時は必ずサンプル数（n=X）を明示する。

### 6.3 プライバシー
増田・西出・須安専用の非公開運用。Streamlit Cloud は URL 秘匿。
worksheet レベルでユーザー間データを物理分離（§4.6.1）。

### 6.4 主観状態記録の原則（v1.2 改訂）

> 記録の質は次の **2 段** で保証される:
>
> (1) ラジオボタンによる time_of_day の **主観申告**
> (2) realtime 窓判定による entry_mode の **メタデータ化**
>
> 想起バイアスを含む `retroactive` サンプルは `realtime` と**別管理**する。

**含意**:

- `recorded_at` は「いつ入力されたか」を表すメタデータかつ Transit 計算の基準時刻でもある（Phase 2）
- ユーザーが「起き抜け」と申告した瞬間に realtime 窓内であれば、その時刻が朝の基底状態
- entry_mode は分析時の重み付け / フィルタリング判断に使う（Phase 2 で確定）

### 6.5 未入力もデータである原則（v1.2 新設）

> MentalMapping の記録対象は「ユーザーが記録した状態」だけではない。
> **「記録しなかったこと」自体もユーザー状態に関する情報である。**
>
> 特に本プロジェクトの目的（鬱トリガー特定等）においては、**記録できないほど状態が悪化した日
> こそが最も重要な観察対象**となりうる。
>
> したがって、時間帯ごとに active レコードが存在しない場合、システムは `not_recorded`
> レコードを自動生成し、未入力を明示的なデータとして管理する。
> これは観測装置原則の具体的適用である: **観測を評価せず、観測の不在も観測の一形態として
> 記録する**。

**含意**:
- `not_recorded` は欠損ではなく観測値として扱う
- 分析（Phase 3）では `not_recorded` の頻度・クラスタ・Transit 相関も対象になりうる
- ユーザーが後日遡って記録した場合、not_recorded は superseded に昇格し履歴を保持する（§4.4.1）

---

## 7. 開発優先順位

| Priority | タスク | Phase | 担当 |
|---------|--------|-------|------|
| **P0** | **17 列スキーマ拡張（L〜Q 追加）+ record_status 鎖構造実装** | **1** | **α-B** |
| **P0** | **既存 11 列データ → 17 列への遡及付与マイグレーション** | **1** | **α-C** |
| **P0** | **settings.yaml の time_of_day 廃止 → realtime_window 統合** | **1** | **α-B** |
| **P0** | **time_of_day ラジオ化 + デフォルト選択なし化** | **1** | **α-B** |
| **P0** | **not_recorded 自動生成 GAS バッチ + カレンダー/グラフの not_recorded 表示** | **1** | **α-B または α-D（別窓検討）** |
| P1 | input_user 整合性リアルタイムチェック UI | 1 | α-B |
| P1 | カレンダービュー + 4指標折れ線グラフ（既存維持） | 1 | α |
| P2 | Transit JSON 読み込み + オーバーレイ表示 | 2 | α |
| P3 | 相関スコア算出 + サマリー | 3 | α |

---

## 8. 変更履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v1.0 | 2026-04-10 | 初版作成（mood_score 0-10 単一指標 + memo + went_outside の 6 フィールド想定）。実装は別路線で先行し、本設計どおりのデータは実在しなかった。 |
| v1.1 | 2026-04-18 | 16 フィールド設計書として書き直し。しかし当時 α-A は MentalMapping 実装コードを確認せず、想像上の v1.0 スキーマからのマイグレーション指針を記述。実態は: (i) 実装は最初から 11 列で動いていた、(ii) 対象ユーザーは 3 名定義済（v1.1 は 2 名と誤記）、(iii) 物理分離は別 worksheet（v1.1 は別スプレッドシートと誤記）、(iv) entry_mode の wake_time ベース判定は実装も合意もされていなかった。設計書の嘘状態が約 1 週間放置され、付録 A.5 マイグレーション指針は「存在しないデータの破壊変換」を指示する誤った内容となっていた。 |
| v1.2 | 2026-04-18 | **Phase 1 先行調査（R-10 準拠）を経て v1.1 を全面訂正**。主要変更: (1) 対象ユーザーを 3 名（増田・西出・須安）に正記、須安は休眠ユーザー扱い。(2) 入力項目を 16 → 17 フィールドに拡張（input_user 列を Q に新設）。(3) time_of_day をラジオボタン主観申告に変更（自動判定廃止・デフォルト選択なし）。(4) entry_mode 判定を wake_time ベース → realtime_window 窓判定に全面変更（責務分離: 同日 2 件目の自動 retroactive 化を行わない）。(5) Phase 2 Transit 時刻を recorded_at 使用（選択肢 1）に反転。(6) 物理分離を別 worksheet（同一 spreadsheet）に訂正。(7) weather の内部 enum 値を "雨" → "雨/雪" に変更（実装値は 3 値維持・日本語リテラル運用維持・英字化は v1.2 スコープ外）。`雨/雪` は気象カテゴリと主観状態（低気圧反応）の折衷表現であり、将来「低気圧」等の抽象カテゴリへのリネーム余地を申し送る（§4.1.1）。(8) settings.yaml の time_of_day.morning_start/evening_start を廃止し users.{user}.{morning,evening}_realtime_window に統合。(9) 鎖構造仕様に「superseded_by=null の superseded = 採用されなかった訂正試行」解釈を追加。(10) 付録 A.5 マイグレーション指針を「現行 11 列 → v1.2 の 17 列拡張」として全面書き直し。既存 9 フィールドは変換不要、追加 6 列の遡及付与のみ + weather "雨" → "雨/雪" 置換。マイグレーション手順を 13 ステップで確定（§A.5.7）。(11) **§6.5「未入力もデータである原則」を新設**、entry_mode enum に `not_recorded` を追加、GAS バッチによる日次自動生成と遡及生成（選択肢γ・§A.5.6）、not_recorded → retroactive 昇格鎖（§4.4.1）、カレンダー/グラフでの not_recorded 可視化（§A.6.5）、GAS バッチ要件（§A.7）を仕様化。(12) 運用観察として記録継続性の動機構造差異を注意事項 #331 / #332 として登録。教訓（R-10 先行調査ルール）は注意事項 #330 に登録。 |
| v1.2.1 | 2026-04-18 | α-C Phase 1 で suyasu worksheet に 2 件の既存レコード（2026-04-14 09:42 morning / 2026-04-16 11:57 morning）が発見された。当初想定（休眠ユーザー・0 件）との乖離が判明。suyasu の realtime_window が settings.yaml で未定義のため、entry_mode に 4 値目 `pending` を追加（§4.1 / §4.3 / §4.3.4 新設 / §A.2 / §A.5.7 ステップ 7）。pending は realtime_window 未定義ユーザーのレコードに付与され、将来 realtime_window 確定時に realtime / retroactive に再判定される。再判定バッチ `devtools/rebalance_pending.py` は将来実装（suyasu realtime_window 確定時）。α-B Phase 2 実装時点で pending 分岐を先行実装済み（`modules/entry_mode.py` / `tests/test_entry_mode.py`）であり、本改訂は設計書を実装に追従させるもの。mm_notes #1 / #2 / #3 として運用観察を記録予定（α-C Phase 2 完了時採番）。 |

---

## 付録 A: α-B / α-C 受け渡しフォーマット（v1.2 確定版）

### A.1 列名リスト（Sheets 列順 17 列）

```
A: date              J: recorded_at
B: mood              K: time_of_day
C: energy            L: daily_aspects
D: thinking          M: record_id
E: focus             N: record_status
F: sleep_hours       O: superseded_by
G: weather           P: entry_mode
H: medication        Q: input_user
I: period
```

### A.2 enum 値

| フィールド | 許容値 |
|-----------|--------|
| weather | `晴` / `曇` / `雨/雪` |
| time_of_day | `morning` / `evening` |
| record_status | `active` / `superseded` |
| entry_mode | `realtime` / `retroactive` / `not_recorded` / `pending` |
| input_user | `masuda` / `nishide` / `suyasu` |

bool 系（medication / period）は `TRUE` / `FALSE` / `""`（空セル = null）。

### A.3 record_id 生成規則

```
record_id = f"{input_user}_{date}_{time_of_day}_{unix_ts}"
```

- `input_user` トークンは Q 列の値と一致させること（worksheet 所有者ではない）
- `unix_ts` は `recorded_at` の UNIX 秒（int）
- 生成例: `masuda_2026-04-14_morning_1744600320`

### A.4 鎖構造仕様

**スコープ**: `(input_user, date, time_of_day)`

**不変条件**:
- 同一スコープ内 `record_status=active` は常に 1 件以内
- 鎖は線形リスト（分岐禁止・各ノードの `superseded_by` は 0 または 1 本）

**superseded_by の解釈**:

| record_status | superseded_by | 意味 |
|---------------|--------------|------|
| active | null | 現行採用レコード |
| superseded | record_id | 鎖の中間（次レコードに引き継がれた） |
| superseded | null | **採用されなかった訂正試行**（鎖の末端に保存） |

**訂正書き込み手順（アプリ層でアトミック性保証）**:
1. 新レコード R_new を追記（active, superseded_by=null）
2. 既存 active R_old を UPDATE: status `active→superseded`, superseded_by `null→R_new.record_id`

**not_recorded → retroactive 昇格**（§4.4.1 参照）:
- 既存 not_recorded（active）は遡及入力レコードにより superseded に昇格
- 昇格後も not_recorded レコード自体は物理削除せず履歴として保持

### A.5 マイグレーション指針（α-C 担当・全面書き直し）

**前提**: 「v1.0 → v1.x」変換ではなく「**現行 11 列実装データ → v1.2 の 17 列拡張**」。
v1.0 スキーマ（mood_score 0-10 / went_outside / memo）のデータは存在しないため変換不要。

#### A.5.1 既存 11 フィールドの扱い

| 列 | 既存値の扱い |
|----|------------|
| A: date | そのまま |
| B〜E: mood/energy/thinking/focus | そのまま（実装は最初から 1-5 で蓄積） |
| F: sleep_hours | そのまま |
| **G: weather** | **`WHERE weather = "雨"` 条件で `"雨/雪"` へ置換**（晴・曇は変更なし）。冪等性確保: 再実行時の二重置換（例: `"雨/雪"` が既に置換済みの値を再処理して `"雨/雪/雪"` 化するような動作）を防止するため、置換条件は必ず `weather == "雨"` の厳密一致とする |
| H: medication | そのまま |
| I: period | そのまま |
| J: recorded_at | そのまま |
| K: time_of_day | そのまま（既存値が自動判定結果か手動上書きかは A.5.4 で遡及確認） |

#### A.5.2 追加 6 列の遡及付与ルール

| 追加列 | 遡及付与ルール |
|--------|--------------|
| L: daily_aspects | 全レコード空文字 `""`（Phase 2 で後埋め） |
| M: record_id | `{input_user}_{date}_{time_of_day}_{unix_ts}` で recorded_at から生成 |
| N: record_status | §A.5.3 のレコード別判定に従う |
| O: superseded_by | 鎖構築ルール（§A.5.3）に従う |
| P: entry_mode | recorded_at と users[input_user] の realtime_window から再判定 |
| Q: input_user | **遡及付与時は worksheet 所有者**（mood_log_masuda → masuda 等）。誤入力疑いレコードは A.5.5 で別管理 |

#### A.5.3 増田の確定済みレコード（西出と本議論で確定済）

以下は α-C が独自に推定せず、本表のとおり付与する。

| date | recorded_at | time_of_day | record_status | superseded_by | entry_mode | 備考 |
|------|-------------|-------------|---------------|---------------|-----------|------|
| 2026-04-14 | 12:12 | morning | **active** | null | **realtime** | 前回議論で一度 retroactive 扱いしたが、ラジオボタン設計移行に伴い realtime, active で確定 |
| 2026-04-16 | 20:34 | evening | **superseded** | `<04-16 20:45 evening の record_id>` | realtime | 直後の 20:45 で訂正 |
| 2026-04-16 | 20:45 | evening | **active** | null | realtime | 04-16 evening の現行採用 |
| 2026-04-17 | 11:18 | morning | **superseded** | **null** | realtime | 採用されなかった訂正試行（鎖の末端・§4.4 末端解釈） |
| 2026-04-17 | 07:45 | morning | **active** | null | realtime | 04-17 morning の現行採用（同日 11:18 は採用されなかった訂正試行） |

増田の上記以外のレコードは α-C が日付順にスキャンし、同一 `(date, time_of_day)` に複数レコードが
存在する場合のみ recorded_at 時系列と西出確認に基づき active / superseded 判定する。
**本表の特殊事例**: 増田 04-17 は時系列的に古い 07:45 が active、新しい 11:18 が superseded（採用されなかった訂正試行）。この逆転は §4.4「active を決めるのはユーザー判断」に基づく確定事項である。α-C は一般ルールではなく本表を正として適用すること。

**weather 置換確定対象（両ユーザー）**:

以下は `weather` セル単独の置換対象として A.5.1 の冪等性条件で処理する。
他列（record_status / entry_mode 等）は §A.5.3 / §A.5.4 の各判定に従う。

| worksheet | date | time_of_day | 変更前 | 変更後 |
|-----------|------|-------------|--------|--------|
| mood_log_masuda | 2026-04-15 | evening | `雨` | `雨/雪` |
| mood_log_nishide | 2026-04-15 | evening | `雨` | `雨/雪` |

上記以外にも `weather == "雨"` のレコードが存在する場合、同条件で一括置換する
（`WHERE weather = "雨"` による冪等置換）。

#### A.5.4 西出のレコード（遡及スキャン）

西出データは本議論で個別レコードを確定していない。α-C は以下手順で判定する:

1. 全レコードを date 昇順で取得
2. 同一 `(date, time_of_day)` グループを構築
3. 各グループ内で recorded_at 最新を仮 active、それ以外を仮 superseded とする
4. **既存 time_of_day 値が自動判定結果か selectbox 手動変更結果かを遡及確認**:
   - 確認手段がある場合: 西出に確認
   - **確認不可の場合: 「自動判定結果として遡及付与扱い」とする**（保守的処理）
5. 仮判定を西出にレビュー依頼。承認後に本付与
6. entry_mode は recorded_at と nishide の realtime_window から機械的に再判定

#### A.5.5 input_user 整合性の遡及チェック

α-C は遡及付与時に以下を実施:

1. 各 worksheet を全件スキャン
2. 期待値: `input_user == worksheet 所有者`
3. **乖離レコードを別ファイル（CSV / 一時シート等）に列挙**し、Sheets 本体への書き込みは保留
4. 西出が手動レビューし、訂正方針を決定:
   - input_user の値を訂正
   - レコードを superseded 化
   - レコード自体を削除

#### A.5.6 not_recorded の遡及生成（選択肢γ）

**起点日**: 各ユーザーの初回記録日を遡及生成の起点とする。

| input_user | 初回記録日 | 遡及対象 |
|-----------|------------|----------|
| masuda | 2026-04-11 morning | 初回記録日 〜 マイグレーション実行日 |
| nishide | 2026-04-11 morning | 初回記録日 〜 マイグレーション実行日 |
| suyasu | 未発生 | **遡及生成対象ゼロ** |

**確定済み遡及生成対象**（本議論で確定）:

| input_user | date | time_of_day | 生成理由 |
|-----------|------|-------------|----------|
| masuda | 2026-04-16 | morning | 当該 (date, time_of_day) に active レコードなし → not_recorded を生成 |

他の日付については、α-C が起点日 〜 実行日の範囲を走査し、同一 `(input_user, date, time_of_day)`
に任意の record_status のレコードが存在しない場合のみ not_recorded を生成する（§4.3.2 冪等性）。

#### A.5.7 マイグレーション実行順序（13 ステップ）

1. **バックアップ取得**: 全 worksheet のスナップショット（別ファイル / 別シート）
2. **値域バリデーション**: 既存 11 列の値域チェック（mood/energy/thinking/focus が 1-5、
   weather が `晴/曇/雨`、time_of_day が `morning/evening` 等）。逸脱レコードは別ファイル列挙
3. **列追加**: L〜Q の 6 列（daily_aspects / record_id / record_status / superseded_by /
   entry_mode / input_user）を worksheet に物理追加
4. **record_id 付与**: 既存レコードに `{input_user}_{date}_{time_of_day}_{unix_ts}` 形式で生成
5. **input_user 付与**: 既存レコードに `physical_worksheet` 所有者を遡及付与
6. **record_status 付与**: §A.5.3（増田確定）/ §A.5.4（西出スキャン手順）に基づく判定
7. **entry_mode 付与**（realtime / retroactive / pending のみ。not_recorded はステップ 10 で生成）:
   - users[input_user] の realtime_window が **定義済み** の場合:
     - recorded_at と users[input_user] の realtime_window から判定
     - time_of_day==morning かつ recorded_at ∈ morning_realtime_window
       → entry_mode=realtime
     - time_of_day==evening かつ recorded_at ∈ evening_realtime_window
       → entry_mode=realtime
     - それ以外 → entry_mode=retroactive
     - masuda と nishide の realtime_window は settings.yaml v1.2.1 版を使用
     - evening_realtime_window 上限 26:00 の翌日時間帯扱いを正しく実装
   - users[input_user] の realtime_window が **未定義** の場合（suyasu 等）:
     - entry_mode = `pending` を付与（§4.3.4 参照）
8. **daily_aspects 付与**: 全レコード空文字 `""`
9. **weather "雨" → "雨/雪" 置換**: `WHERE weather = "雨"` の冪等条件で置換（§A.5.1 / §A.5.3 末尾）
10. **not_recorded 遡及生成**: §A.5.6 の選択肢γ基準で実施
11. **input_user 整合性チェック**: §A.5.5 の遡及チェックを実施、乖離レコードを西出レビュー用に列挙
12. **バリデーション**: active 1 件ルール、鎖構造整合性（superseded_by の整合）、enum 値域の
    最終チェック
13. **検証結果の西出報告**: 遡及生成件数・置換件数・乖離件数・異常レコード等のサマリー提出

**全体前提**:
- 各ステップは**ドライラン → 西出確認 → 本実行**の 2 段階で行う
- Sheets 本体への書き込みはステップ 3 以降のみ、ステップ 2 までは検証用出力のみ

### A.6 Streamlit UI 要件（v1.2 新設）

#### A.6.1 time_of_day ラジオボタン
- ウィジェット: `st.radio`
- 選択肢: `["起き抜け", "夜落ち着いた時"]`（DB 保存値は `morning` / `evening`）
- **デフォルト選択なし**（`index=None`）
- 「記録する」ボタンは time_of_day 未選択時 disabled

#### A.6.2 input_user 選択 UI
- 毎回必須選択（毎回明示）
- サイドバーで現在の input_user を強調表示
- worksheet 所有者と乖離する選択がされた場合、§4.6.2 (A) のリアルタイム警告を発動

#### A.6.3 訂正ダイアログ
- 同一 `(input_user, date, time_of_day)` に既存 active がある状態で記録ボタン押下時:
  - 確認モーダル: 「既存記録を訂正しますか? それとも記録試行を残しつつ既存を維持しますか?」
  - 訂正: §4.4 の鎖構築フローを実行
  - 維持: 新レコードを `record_status=superseded, superseded_by=null` で追記（採用されなかった訂正試行として保存）

#### A.6.4 同日同 time_of_day 複数レコード時の表示
- 「見る」タブの集計は `record_status=active` のレコードのみを使用
- 訂正履歴の閲覧は別 UI（Phase 1 後半 / Phase 2 で検討）

#### A.6.5 not_recorded 表示
- **カレンダービュー**: `active` かつ `entry_mode=not_recorded` の日は**グレー塗り**等で
  通常記録日（4 指標平均の色分け）と明確に区別する
- **折れ線グラフ**: not_recorded 区間は
  - データ点を置かずに線を欠損表示
  - または not_recorded マーカー（×印等）で明示
- 集計では `not_recorded` は欠損ではなく観測値として件数に含める（§6.5）

### A.7 GAS バッチ要件（v1.2 新設・α-B または α-D 向け）

#### A.7.1 目的
未入力時の `not_recorded` レコードを日次で自動生成し、欠損でなく観測値として Sheets に
明示化する（§4.3.2 / §6.5）。

#### A.7.2 実装環境
- **Google Apps Script（GAS）**
- 理由: Streamlit Cloud は常時起動しないためスケジューラに不向き。GAS は Google Sheets と
  同一エコシステム・トリガー管理・権限モデルで最適
- **BTR コホート GAS とは別トリガー・別スクリプトで独立実装**（相互影響を避ける）

#### A.7.3 実行頻度
- **日次**（毎日深夜想定。正確な時刻は α-B / α-D 決定）
- 手動実行による即時トリガーも許容

#### A.7.4 処理内容
1. settings.yaml から `users` を取得（GAS 側は Sheets 内 config or Properties サービス経由）
2. 各ユーザー worksheet を走査
3. 以下の 2 条件を**両方満たす**時間帯について not_recorded を追記:
   - 判定時刻が `{time_of_day}_realtime_window.end` を過ぎている
   - 同一 `(input_user, date, time_of_day)` に**任意の record_status**のレコードが存在しない
4. not_recorded レコードの構造は §4.3.2 に従う

#### A.7.5 冪等性
- 再実行時は上記 3 の「任意の record_status のレコードが存在しない」条件により
  二重生成を防止
- not_recorded が既に生成された `(user, date, time_of_day)` は再生成しない

#### A.7.6 調査事項（α-B / α-D 着手前に確認）
- BTR コホート GAS との **スクリプトファイル分離方針**（同 spreadsheet か別プロジェクトか）
- **トリガー管理**（time-driven trigger の重複防止）
- **Google Sheets API 権限**（サービスアカウント共有 or GAS の実行アカウント権限）
- **実行時間上限**（GAS は 6 分制限。全ユーザー × 遡及期間の走査が収まるかの見積）
- **エラー通知**（Discord Webhook / メール / Sheets 内ログシート）
