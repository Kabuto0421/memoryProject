# Evaluation Loop

## 目的

この文書は、`memory_project` のルールや想起ロジックを変更したあとに、毎回どの順番で評価し、何を見ればよいかを固定するための運用メモです。  
雰囲気でスコアをいじらず、最低限同じ観点で before / after を比較できる状態を維持します。

## 前提

- 本体リポジトリ: `/Users/kabuto/Documents/Codex/memory_project`
- scratch リポジトリ: `/Users/kabuto/Documents/Codex/memory_project_eval_scratch`

評価スクリプトは scratch 側に置き、本体から analyzer を import して動かします。

## 標準評価セット

標準で毎回回すのは次の 3 種類です。

1. `rule_challenge_set`
   - 目的: `negation`, `decision_support`, `reflection` などの誤爆確認
2. `natural_conversation_set`
   - 目的: 日常会話に近い入力で priority 分布が不自然でないか確認
3. `long_term_memory_gold_set`
   - 目的: 人間が想定した long-term importance と priority のズレ確認

必要に応じて以下を追加します。

- `generated_300`
- `chatgpt_daily_memory_examples_300.csv`

ただし、日常の改善ループではまず 3 種類の curated set を優先します。

## 実行コマンド

本体リポジトリから実行します。

```bash
cd /Users/kabuto/Documents/Codex/memory_project
uv run --with matplotlib python /Users/kabuto/Documents/Codex/memory_project_eval_scratch/run_evaluation_cycle.py
```

この 1 コマンドで以下が更新されます。

- `eval_report_rule_challenge_set.md`
- `eval_report_natural_conversation_set.md`
- `eval_report_long_term_memory_gold_set.md`
- `eval_metrics_*.json`
- `eval_histogram_*.png`
- `eval_reason_code_frequency_*.png`
- `eval_cycle_summary.md`

## 最低限見るべきもの

### 1. `eval_cycle_summary.md`

まず最初に全体を見る場所です。

確認点:

- `priority_counts`
- 上位 `reason_codes`
- gold `exact_match`
- gold `near_match`

### 2. `rule_challenge_set`

確認点:

- `has_negation` が異常に増えていないか
- `has_decision_support` が広がりすぎていないか
- `has_reflection` が消えていないか

### 3. `natural_conversation_set`

確認点:

- `medium` に極端に寄りすぎていないか
- `high` / `critical` がゼロに近づいていないか
- 上位 `reason_codes` が直感とズレていないか

### 4. `long_term_memory_gold_set`

確認点:

- `exact_match`
- `near_match`
- `critical` を `low` に落としていないか
- `low` を `high` に上げすぎていないか

## 変更ごとのチェックルール

### ルール辞書を変えた時

- `rule_challenge_set`
- `long_term_memory_gold_set`

を必ず見る。

### `save_strength` や `memory_priority` 閾値を変えた時

- 3 種類全部見る
- 特に `natural_conversation_set` の分布を見る

### 想起ロジックを変えた時

- 3 種類全部に加えて、review UI で `想起プレビュー` も確認する

## 目安の gate

厳密な CI gate ではないが、最低限これを崩した変更は要再検討にします。

- gold `near_match` が前回より悪化しない
- `rule_challenge_set` で既知誤爆が増えない
- `natural_conversation_set` で `high/critical` が消滅しない
- `reason_codes` の上位が明らかにおかしくならない

## 実務上の運用

- ルールやスコアを変えたら `current_scoring.md` を更新する
- 変更前後で `eval_cycle_summary.md` の差を見る
- 気になるズレがあれば、そのズレを再現する文を `rule_challenge_set` か `gold_set` に追加する

## 次にやると強いこと

- `eval_cycle_summary.md` の過去比較を残す
- gold mismatch 上位の一覧を別ファイルに出す
- review UI から summary を参照できるようにする
