# Implementation Roadmap

## 目的

この文書は、`memory_project` を今後どう拡張していくかを、実装順と判断基準が分かる形で整理したロードマップです。  
「次に何をやればいいか分からない」状態を防ぐため、現在地、直近タスク、中期タスク、将来タスクを分けて管理します。

## 現在地

2026-05-08 時点で、以下は実装済みです。

### 保存・解析

- GiNZA を使った会話文解析
- `save_strength` と `memory_priority` による全件保存 + 強度付け
- `reason_codes` の付与
- SQLite 保存

### API

- `POST /memories`
- `GET /memories`
- `POST /messages`
- `GET /messages`

### 会話メタデータ

- `speaker`
- `turn_id`
- `reply_to_turn_id`
- `source`
- `memory_scope`
- `status`

### UI / ドキュメント / 検証

- Streamlit UI
- `current_scoring.md`
- `plugin_integration_design.md`
- pytest による基本検証

## 今の構造で足りていないもの

今のシステムは「会話を記録して、ある程度構造化する」ところまではできています。  
ただし、チャット連携や shared context 活用まで考えると、以下がまだ不足しています。

### 1. shared context の昇格

AI 提案とユーザー承認を受けて、共有前提として残す仕組みがまだありません。

### 2. 関連記憶の取り出し

今は保存と一覧はできるが、次の会話に使うための「関連記憶だけ返す」API がありません。

### 3. 会話レベルの利用

今は `messages` を保存できるだけで、「この会話で何が合意されたか」「どの前提を次回に持ち越すか」が弱いです。

### 4. 運用しやすい UI

Streamlit では生 JSON を見られますが、日常利用向けの review UI にはまだなっていません。

### 5. 想起段階の設計

今のロードマップは「何を保存するか」寄りで、「保存したものをいつ、どう会話へ戻すか」がまだ弱いです。  
長期記憶システムは保存だけでは不十分で、最終的には以下を満たす必要があります。

- 今の発話と関係ある記憶だけを出す
- 出しすぎて会話を汚さない
- sensitive な記憶を雑に出さない
- shared context を優先しつつ、生ログは補助に回す

つまり、このプロジェクトには保存フェーズと並んで、**想起フェーズ** の設計が必要です。

## フェーズ別ロードマップ

---

## Phase 1: 会話ターン保存の安定化

### 目的

`/messages` を今後の正規入口として安定させる。

### なぜ必要か

今のままだと `memories` と `messages` のどちらを使うべきかが曖昧で、今後の拡張で必ず破綻します。  
まず入口を揃えないと、その後の shared context 抽出や想起ロジックを一貫したデータモデルの上に載せられません。

### やること

1. `POST /messages` を使う前提で Streamlit UI を更新する
2. `speaker`, `memory_scope`, `status` を UI 上でも見やすく表示する
3. `GET /messages` のフィルタ確認を増やす
4. 既存 `/memories` は互換維持 API として扱う方針を明記する

### 完了条件

- UI から `speaker=user/assistant` を切り替えて保存できる
- 一覧で `turn_id`, `speaker`, `memory_scope`, `status` が確認できる
- API と UI のどちらでも同じデータモデルが見える

### 主な編集対象

- `/Users/kabuto/Documents/Codex/memory_project/app/streamlit_app.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/api/main.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/tests/test_smoke.py`

---

## Phase 2: shared context candidate の抽出

### 目的

会話ログから「共有前提候補」を切り出せるようにする。

### なぜ必要か

会話ログを全部 raw のまま持っていても、「何が今後の前提なのか」が分かりません。  
shared context candidate を切り出せないと、次回会話で毎回全文ログを読み直すしかなくなり、長期記憶の価値が大きく下がります。

### やること

1. assistant 発話のうち、提案調の文を `shared_context_candidate` に寄せるルールを作る
2. user の承認っぽい短文を検出するルールを作る
3. `accepted` 候補への昇格判定を作る
4. `reason_codes` に shared context 系の理由を追加する

### 最小ルール例

- assistant 発話:
  - `〜方針`
  - `〜で進める`
  - `〜を使う`
  - `〜にする`
  - `〜がよい`
  を含む
- user 承認:
  - `それで`
  - `それでお願い`
  - `OK`
  - `その方針で`
  - `じゃあそれで`

### 完了条件

- `speaker=assistant` の保存時に `assistant_trace` と `shared_context_candidate` を区別できる
- 一定条件で `status=accepted` を付けられる
- 承認フローを 2〜3 パターン pytest で確認できる

### 主な編集対象

- `/Users/kabuto/Documents/Codex/memory_project/app/analysis/text_analyzer.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/memory/store.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/tests/test_smoke.py`
- `/Users/kabuto/Documents/Codex/memory_project/docs/scoring/current_scoring.md`

---

## Phase 3: `shared_contexts` テーブル追加

### 目的

会話ログとは別に、今後の前提として再利用する shared context を保存する。

### なぜ必要か

候補抽出だけでは不十分で、合意された前提を raw turn から分離して保存しないと、想起時に毎回ノイズを拾います。  
shared context は「次の会話に優先注入すべき要約済み前提」の保管場所です。

### やること

1. `shared_contexts` テーブルを作る
2. `source_turn_ids_json` を保存する
3. `summary`, `detail`, `status`, `importance` を持たせる
4. `accepted` な会話ターンから shared context を生成する

### 最初の方針

この段階では LLM は使わず、

- `summary` は元文の短縮版
- `detail` は元文そのまま、または軽い整形

でよいです。

### 完了条件

- `accepted` な候補から shared context が作られる
- shared context が raw turn と別に取得できる
- どの turn 由来か追える

### 主な編集対象

- `/Users/kabuto/Documents/Codex/memory_project/app/memory/store.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/api/main.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/tests/test_smoke.py`

---

## Phase 4: 関連文脈取得 API の追加

### 目的

次の会話に渡す関連記憶を少数返せるようにする。

### なぜ必要か

保存だけできても、会話で使えなければ長期記憶システムとして半分しか成立していません。  
`GET /context/relevant` は、保存済みデータを「次の発話に使えるコンテキスト」へ変換する最初の橋です。

### やること

1. `GET /context/relevant` を追加する
2. `query`, `speaker`, `memory_priority`, `memory_scope` で候補取得できるようにする
3. `shared_contexts` を優先しつつ、関連する `user_memory` と `assistant_trace` を少数返す
4. 返却件数を明示的に制限する

### 初期アルゴリズム

- topic / keyword の部分一致
- `memory_priority` の高い順
- 新しい順
- `shared_contexts` を先頭に置く

### 完了条件

- `query=保存方針` のような入力で関連前提を返せる
- 返却件数が増えすぎない
- 次の会話に注入する最小コンテキストとして使える

### 主な編集対象

- `/Users/kabuto/Documents/Codex/memory_project/app/memory/store.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/api/main.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/tests/test_smoke.py`

---

## Phase 5: 想起レイヤーの実装

### 目的

保存済み記憶を、会話へ戻してよい形に選別・整形できるようにする。

### なぜ必要か

関連文脈 API ができても、そのまま raw memory を返すだけでは会話を壊します。  
実際に必要なのは「思い出してよいものだけを、よい順番で、よい粒度で返す」層です。  
ここがないと、検索システムはできても conversational memory system にはなりません。

### やること

1. 想起候補のランキング規則を作る
   - `shared_contexts` を最優先
   - `memory_priority`
   - 新しさ
   - query/topic 一致
2. 想起してよい条件を決める
   - related topic
   - follow-up
   - emotional support
3. 想起してはいけない条件を決める
   - unrelated smalltalk
   - sensitive な記憶の casual 呼び出し
4. 想起レスポンスの返却形式を固める
   - compact summary
   - source turn ids
   - why selected

### 完了条件

- 同じ query でも、shared context と raw turn が混ざって返る順序に一貫性がある
- irrelevant な記憶を大量に返さない
- sensitive な記憶が無条件で前に出ない
- 「なぜその記憶を返したか」が説明できる

### 主な編集対象

- `/Users/kabuto/Documents/Codex/memory_project/app/memory/store.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/api/main.py`
- `/Users/kabuto/Documents/Codex/memory_project/app/tests/test_smoke.py`
- 必要なら `/Users/kabuto/Documents/Codex/memory_project/docs/scoring/current_scoring.md`

---

## Phase 6: 検索とレビュー UI の改善

### 目的

人間が記憶の質を点検しやすくする。

### なぜ必要か

保存・shared context・想起ルールが増えるほど、内部状態は複雑になります。  
review UI が弱いと、誤判定や危ない想起条件を発見できず、改善サイクルが止まります。

### やること

1. Streamlit にフィルタを追加する
   - `speaker`
   - `memory_scope`
   - `status`
   - `memory_priority`
2. `shared_contexts` 一覧を出す
3. `reason_codes` を見やすく表示する
4. 「重要そうなのに low」「ノイズなのに high」を見つけやすくする

### 完了条件

- 目視で誤判定を洗える
- JSON 全表示に頼らず review できる
- 記憶の濃淡を運用しやすくなる

### 主な編集対象

- `/Users/kabuto/Documents/Codex/memory_project/app/streamlit_app.py`
- 必要なら `/Users/kabuto/Documents/Codex/memory_project/docs/scoring/current_scoring.md`

---

## Phase 7: 評価セット連動の改善サイクル

### 目的

ルールを雰囲気でいじらず、評価セットに基づいて改善する。

### なぜ必要か

記憶システムは、少しのルール変更でも分布や誤爆の仕方が大きく変わります。  
評価セットに戻して比較しないと、「よくなった気がする」だけの改修が増え、後で制御不能になります。

### やること

1. scratch 側の 3種類の評価セットを継続利用する
   - ルール検査用
   - 自然会話用
   - 長期記憶ゴールド用
2. 変更ごとに以下を確認する
   - `reason_codes` 頻度
   - priority 分布
   - gold との exact match
3. `critical` / `high` / `medium` の分布崩れを監視する

### 完了条件

- ルール変更前後の差分が説明できる
- ゴールドセットとのズレが追える
- `current_scoring.md` が仕様書として保たれる

### 主な編集対象

- 本体コード
- `/Users/kabuto/Documents/Codex/memory_project/docs/scoring/current_scoring.md`
- scratch repo 側評価スクリプト

---

## Phase 8: Chat / MCP / Plugin 接続用の薄い入口

### 目的

memory backend の上に、薄い接続層を載せられるようにする。

### なぜ必要か

最終目標は日常チャットと組み合わせることだが、ここを先にやると内部基盤の不足をプラグイン側で吸収する羽目になります。  
接続層は最後に薄く作る方が、コストもデバッグも圧倒的に楽です。

### やること

1. `GET /context/relevant` を使う想定で、MCP または plugin 側の最小仕様を決める
2. チャット入力前に関連記憶を引くフローを定義する
3. 会話終了時または一定間隔で `POST /messages` を流す設計を決める

### この段階でまだやらなくてよいこと

- 毎ターン LLM 要約
- 大規模 embedding 再計算
- 複雑な agent orchestration

### 完了条件

- 「外部チャットから message を送る」
- 「関連文脈を返す」
- 「shared context を引く」

の 3動作がつながる

---

## 実装順の推奨

迷ったらこの順で進めるのがよいです。

1. Phase 1: Streamlit を `/messages` 前提に寄せる
2. Phase 2: shared context candidate 抽出
3. Phase 3: `shared_contexts` テーブル
4. Phase 4: `GET /context/relevant`
5. Phase 5: 想起レイヤー
6. Phase 6: review UI
7. Phase 7: 評価ループの固定化
8. Phase 8: plugin / MCP 接続

## 直近 3 セッション分の具体タスク

### セッション A

- Streamlit を `/messages` 対応にする
- `speaker` 切り替え入力を追加する
- `memory_scope` と `status` を UI に出す

### セッション B

- assistant 発話から `shared_context_candidate` を切る
- user 承認で `accepted` 候補を付ける
- そのルールを pytest で固定する

### セッション C

- `shared_contexts` テーブル追加
- `GET /context/shared` を追加
- 共有前提の保存と取得まで通す

### セッション D

- `GET /context/relevant` を追加
- shared context 優先の返却順を作る
- 想起してよい条件 / 悪い条件を固定する

## 変更時の運用ルール

- スコアや `reason_codes` を変えたら `current_scoring.md` を更新する
- 会話保存モデルを変えたら `plugin_integration_design.md` を更新する
- 実装順や開発方針が変わったらこのロードマップも更新する

## いま一番おすすめの次タスク

今すぐ次にやるべきなのはこれです。

1. Streamlit を `/messages` 対応にする
2. assistant 提案 + user 承認の cheap rule を作る

理由:

- すでに DB と API の土台は入った
- 次のボトルネックは shared context 生成
- 想起段階をまともに作るには、先に shared context を安定化させる必要がある
- そこができると、ただの保存システムから「継続会話に効く記憶システム」へ進める
