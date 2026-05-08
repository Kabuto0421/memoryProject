# Plugin Integration Design

## 目的

この文書は、`memory_project` を将来的に日常的なチャット利用と接続するための設計方針を整理したものです。  
最終目標は、会話の流れを壊さずに長期記憶を活用できる、軽量で実用的なローカル記憶バックエンドを作ることです。

ここで重要なのは、最初から「チャットプラグインそのもの」を作ることではありません。  
先に、会話ログの保存・検索・想起候補抽出を担う独立した記憶バックエンドを作り、その上にプラグインや MCP サーバを載せる構成を採ります。

## 中核方針

### 1. 保存は軽くする

毎ターン重い LLM 推論を走らせる設計にはしません。  
保存時には、できるだけ rule-based な処理と軽量な構造化だけを行います。

保存時に最低限行うこと:

- 発話テキストの保存
- `speaker` の記録
- `turn_id` と参照関係の記録
- `save_strength` と `memory_priority` の計算
- `reason_codes` の付与
- `memory_scope` の仮置き

### 2. 想起と統合は必要時だけ重くする

重い処理は、以下のような場面に限定します。

- 会話開始前に関連記憶を数件取り出す
- 長い会話から shared context を要約する
- 類似記憶をまとめ直す
- 曖昧な設計合意を圧縮する

つまり、保存は cheap、想起は selective、圧縮は occasional にする方針です。

### 3. ユーザー発話と AI 発話は同列に扱わない

ユーザー発話も AI 発話も保存対象ですが、同じ意味では保存しません。

- ユーザー発話:
  - 好み
  - 感情
  - 継続的な悩み
  - 人間関係
  - 習慣
  - 方針
- AI 発話:
  - 提案
  - 説明
  - 仮説
  - 合意候補
  - 未解決論点

AI の出力をそのまま「ユーザーの事実」として保存すると、後で誤った既成事実化が起きるため、最低限 `speaker` と `status` の分離が必要です。

## 全体アーキテクチャ

```text
chat input
-> lightweight ingestion
-> local memory store (SQLite)

when needed
-> retrieve relevant memories
-> retrieve shared context
-> inject compact context into chat
```

この構成では、`memory_project` 自体は記憶バックエンドとして独立し、将来的に以下のフロントから再利用できます。

- ChatGPT 連携
- Codex / MCP 連携
- ローカル CLI
- 独自 UI

## 記憶レイヤー

### 1. user_memory

ユーザー自身に関する継続的な記憶です。

例:

- 好み
- 避けたいもの
- 不安
- 関係性
- 習慣
- 価値観

### 2. assistant_trace

AI 側が会話中に出した提案や説明のログです。

例:

- 保存方針の提案
- スコア設計案
- 実装方針
- 仮説
- 調査メモ

### 3. shared_context

会話の中で双方が共有し、今後の前提として扱う情報です。  
この層が、長期チャット利用では最も重要です。

例:

- 「全件保存する」方針
- `save_strength` を使う設計
- `should_save` は現時点では使わない
- 文書変更時は `current_scoring.md` も更新する

## なぜ shared_context が必要か

単に会話ログを蓄積するだけでは、後から「何が合意済みなのか」が分かりません。  
毎回全文ログを再読しないといけない状態は、日常チャットとの統合に向きません。

そこで、shared context は raw turn とは別に管理します。

shared context に昇格しうるもの:

- ユーザーが明示的に採用した提案
- 継続的な開発方針
- 命名方針
- 実装上の制約
- 会話内で確定した用語定義

## 推奨ストレージモデル

最初から複雑に正規化しすぎる必要はありません。  
ただし、将来のプラグイン統合を考えると、今の `memories` テーブルだけでは不足します。

### Table A: `conversation_turns`

会話の生ログを保存するテーブルです。

推奨カラム:

```text
id TEXT PRIMARY KEY
turn_id TEXT NOT NULL
reply_to_turn_id TEXT NULL
speaker TEXT NOT NULL
text TEXT NOT NULL
source TEXT NOT NULL
memory_scope TEXT NOT NULL
status TEXT NOT NULL
summary TEXT NOT NULL
memory_types_json TEXT NOT NULL
topics_json TEXT NOT NULL
keywords_json TEXT NOT NULL
entities_json TEXT NOT NULL
facets_json TEXT NOT NULL
scores_json TEXT NOT NULL
emotion_json TEXT NOT NULL
recall_policy_json TEXT NOT NULL
safety_json TEXT NOT NULL
reason_codes_json TEXT NOT NULL
save_strength REAL NOT NULL
memory_priority TEXT NOT NULL
created_at TEXT NOT NULL
updated_at TEXT NULL
```

### 推奨値

- `speaker`
  - `user`
  - `assistant`
  - 必要なら将来 `system`
- `memory_scope`
  - `user_memory`
  - `assistant_trace`
  - `shared_context_candidate`
- `status`
  - `asserted`
  - `proposed`
  - `accepted`
  - `rejected`
  - `unresolved`

### Table B: `shared_contexts`

会話ログから昇格させた共有前提を保存します。

推奨カラム:

```text
id TEXT PRIMARY KEY
summary TEXT NOT NULL
detail TEXT NOT NULL
status TEXT NOT NULL
source_turn_ids_json TEXT NOT NULL
tags_json TEXT NOT NULL
importance REAL NOT NULL
created_at TEXT NOT NULL
updated_at TEXT NULL
```

ここでは raw text 全文ではなく、共有前提として再利用しやすい要約を保存します。

例:

```json
{
  "summary": "保存は全件保存、強度は save_strength で制御する",
  "status": "accepted",
  "source_turn_ids_json": ["turn_102", "turn_103"]
}
```

### Optional Table C: `memory_links`

必要になった段階で追加すればよい補助テーブルです。

用途:

- `conversation_turns` と `shared_contexts` の関係付け
- どの turn がどの shared context に寄与したかの追跡
- 将来の検索改善

最初の MVP ではなくても構いません。

## 低コストな取り込み戦略

### 基本方針

保存時は LLM なしでも動くようにします。

### 軽量取り込みの流れ

```text
new message
-> assign speaker
-> assign turn_id / reply_to_turn_id
-> run lightweight analyzer
-> assign memory_scope
-> assign status
-> persist to conversation_turns
```

### `memory_scope` の決め方

初期は単純でよいです。

- `speaker == user`
  - まず `user_memory`
- `speaker == assistant`
  - まず `assistant_trace`

ただし AI 発話のうち、shared context 候補になりそうなものは `shared_context_candidate` としても扱えるようにします。

### `status` の決め方

これも最初は cheap rule で十分です。

例:

- user 発話:
  - 基本 `asserted`
- assistant 発話:
  - 提案調なら `proposed`
- 直後の user 発話が
  - `それで`
  - `それでお願い`
  - `OK`
  - `その方針で`
  のような承認なら、直前の `proposed` を `accepted` 候補にする

この方式なら、保存時の追加コストはほぼ増えません。

## 提案 API 形状

最終的にプラグイン化する前提なら、API は「会話保存」と「文脈取得」を分けるべきです。

### 1. Ingestion

```http
POST /messages
```

リクエスト例:

```json
{
  "turn_id": "turn_123",
  "reply_to_turn_id": "turn_122",
  "speaker": "user",
  "text": "本屋では候補を広げるより、一冊に絞ってほしい。"
}
```

レスポンス例:

```json
{
  "id": "mem_abc123",
  "memory_scope": "user_memory",
  "status": "asserted",
  "save_strength": 0.56,
  "memory_priority": "critical",
  "reason_codes": [
    "has_desire",
    "has_reflection",
    "has_rich_topics"
  ]
}
```

### 2. Recent Turns

```http
GET /messages
```

用途:

- 直近会話一覧
- UI 表示
- デバッグ確認

### 3. Raw Memory Search

```http
GET /memories/search
```

用途:

- キーワード検索
- `memory_priority` や `speaker` による絞り込み
- トピック単位での検索

クエリ例:

```text
query=本屋&speaker=user&priority=high
```

### 4. Relevant Context Retrieval

```http
GET /context/relevant
```

用途:

- 次の会話に入れる関連記憶を少数返す
- プラグインがチャット文脈へ注入する候補を作る

レスポンス例:

```json
{
  "shared_contexts": [...],
  "user_memories": [...],
  "assistant_trace": [...]
}
```

ここでは件数を絞ることが重要です。  
raw 全文を大量に返すのではなく、数件の関連記憶と共有前提に圧縮して返します。

### 5. Shared Context Listing

```http
GET /context/shared
```

用途:

- 現在の合意事項一覧
- セッション横断で維持したい前提確認
- UI からのレビュー

## コスト最適化の考え方

日常チャット連携を意識すると、コストを食う場所は明確です。

### 高コスト化しやすいもの

- 毎ターン LLM を呼ぶ保存処理
- 会話全文を毎回再要約する処理
- すべての記憶を毎回再ランキングする処理

### 安く保つべきもの

- 取り込み
- 軽いスコアリング
- 軽いタグ付け
- speaker / status / scope の付与

### LLM を使うなら後回しにする処理

- shared context の高品質な要約
- 曖昧な合意の解消
- 長期ログの圧縮
- 複数記憶の統合説明

つまり、LLM は ingestion path ではなく refinement path で使います。

## 実装フェーズ案

### Phase 1

既存の `memories` 中心構成を維持しつつ、以下を追加します。

- `speaker`
- `turn_id`
- `reply_to_turn_id`
- `memory_scope`
- `status`

### Phase 2

`POST /messages` と `GET /messages` を追加し、会話 turn 単位の保存へ寄せます。

### Phase 3

`shared_contexts` テーブルを追加し、`accepted` な提案や継続方針を昇格保存できるようにします。

### Phase 4

`GET /context/relevant` を作り、チャットプラグインや MCP 側で「次の発話に混ぜる関連記憶」を返せるようにします。

### Phase 5

必要であれば、shared context の圧縮・統合にだけ LLM を導入します。

## 結論

最終目標が「普段のチャットと組み合わせられるプラグイン」であっても、今すぐプラグインを作る必要はありません。  
先にやるべきなのは、以下の条件を満たす記憶バックエンドを作ることです。

- 全件保存できる
- ユーザー発話と AI 発話を区別できる
- 会話の共有前提を別管理できる
- 保存コストが低い
- 必要時だけ関連文脈を返せる

この形にしておけば、将来は ChatGPT 連携、Codex 連携、MCP 化、独自プラグイン化のどれにも拡張しやすくなります。
