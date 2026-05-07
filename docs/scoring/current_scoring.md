# Current Scoring

## 概要

今の長期記憶MVPは、会話文を高度に理解しているわけではありません。  
ただし初期版とは違って、`text_analyzer.py` では GiNZA を使って日本語文を分解した上で、手書きルールを適用しています。

入力文に対して、主に次を推定しています。

- どんな種類の記憶か
- どんな感情が含まれていそうか
- 長期記憶としてどれくらい強く残すか
- 後でどういう文脈なら思い出してよさそうか
- センシティブな記憶として慎重に扱うべきか

現状は、学習や統計モデルではなく **GiNZA + ルールベース** の簡易判定です。

## 入力から保存までの流れ

1. 入力文の前後空白を除去する
2. GiNZA で token, lemma, pos, entity を取る
3. 名詞・固有名詞中心に `topics` を生成する
4. 原形ベースで `keywords` を生成する
5. `memory_types` を文字列一致 + lemma 一致で推定する
6. `emotion` を文字列一致 + lemma 一致で推定する
7. 否定表現がある場合は感情シグナルを少し抑える
8. `scores` をルール加点で計算する
9. `reason_codes` を組み立てる
10. `save_strength` と `memory_priority` を計算する
11. `recall_policy`, `safety`, `facets` を組み立てる
12. SQLite に JSON として保存する

## 現在使っている判定材料

今の判定材料は次の2層です。

### 解析の土台

- GiNZA の token
- lemma
- pos
- named entity
- negation の有無

### ルール辞書

- `TEXT_EMOTION_RULES`
- `LEMMA_EMOTION_RULES`
- `TEXT_MEMORY_TYPE_RULES`
- `LEMMA_MEMORY_TYPE_RULES`
- `FUTURE_TERMS`
- `SENSITIVE_TERMS`
- `TECHNICAL_MARKERS`
- `SHORT_ACK_TERMS`

つまり現状は、「GiNZA で文を分解し、その結果に手書きルールを当てる」構成です。  
embedding や学習済み分類器はまだ使っていません。

## 解析結果として保存している主な項目

現在の記憶レコードには、少なくとも次の解析結果を保存しています。

- `summary`
- `topics`
- `keywords`
- `entities`
- `memory_types`
- `facets`
- `scores`
- `emotion`
- `recall_policy`
- `safety`
- `save_strength`
- `memory_priority`
- `reason_codes`

このうち、`topics`, `keywords`, `entities` は GiNZA 導入の恩恵を最も受けている部分です。

## Topics / Keywords / Entities

### `topics`

GiNZA の token から、主に `NOUN` と `PROPN` を topic 候補として拾います。  
固有表現がある場合は、それを先に入れてから通常の名詞を追加します。  
現在は最大6件まで保存します。

topic は、後の検索や会話想起で「この記憶は何の話だったか」を雑に表すための値です。

### `keywords`

GiNZA の token から、`NOUN`, `PROPN`, `VERB`, `ADJ` を keyword 候補として拾います。  
固有名詞は表層形を優先し、それ以外は原形を優先して保存します。  
現在は最大10件まで保存します。

keyword は、topic より少し広く、「話題を支える語彙」まで含めるための値です。

### `entities`

GiNZA が `doc.ents` として返した固有表現をそのまま保存します。  
今は entity label を保存しておらず、text だけを保存しています。

entity は、人名、場所名、作品名、組織名などを拾えたときに、検索性と保存強度の両方へ影響します。

## Memory Types

### `preference`

`好き`, `嫌い`, `苦手`, `避けたい` のような表現、または lemma として `好む`, `避ける` などが取れたときに付きます。  
ユーザーの継続的な好みや嫌悪を示している可能性がある、とみなします。

### `desire`

`したい`, `ほしい`, `欲しい` のような表現、または lemma として `望む` が取れたときに付きます。  
希望や欲求を表す発話として扱います。

### `worry`

`不安`, `心配`, `困る`, `怖い` のような表現、または関連 lemma が取れたときに付きます。  
継続的な悩みや気がかりの候補として扱います。

### `reflection`

`思う`, `感じる`, `おかしくないか`, `違和感` のような表現、または活用後でも lemma として `思う`, `感じる` が取れたときに付きます。  
価値観や自己理解につながる内省として扱います。

### `relationship`

`友達`, `家族`, `母`, `父`, `恋人`, `先輩`, `後輩` が含まれる、または関連 token が topic に出ると付きます。  
人間関係に関わる記憶かもしれないとみなします。

### `decision_support`

`決めてほしい`, `選んでほしい`, `どれ`, `迷う` のような表現、または lemma として `決める`, `選ぶ`, `迷う` が取れたときに付きます。  
ユーザーが選択支援や判断補助を求めている可能性がある、とみなします。

### `task`

`やる`, `作る`, `確認`, `調べる`, `直す` のような表現、または lemma として同等の動詞が取れたときに付きます。  
タスクやフォローアップ対象として扱います。

### `context`

どのルールにも当たらなかった場合に付くデフォルト値です。  
「意味がない」という意味ではなく、今のルールでは型を付けられなかった、という意味です。

## Emotion

### `joy`

`嬉しい`, `楽しい`, `最高`, `安心`, `よかった` のような表現、または関連 lemma で判定します。  
前向きな感情として扱います。

### `sadness`

`悲しい`, `寂しい`, `つらい`, `しんどい` のような表現、または関連 lemma で判定します。  
落ち込みや喪失感に近い感情として扱います。

### `frustration`

`面倒`, `困る`, `嫌`, `詰まった`, `わからない`, `おかしくないか` のような表現、または関連 lemma で判定します。  
苛立ちや摩擦がある発話として扱います。

### `anxiety`

`不安`, `怖い`, `心配`, `気になる` のような表現、または関連 lemma で判定します。  
気がかりや警戒のある発話として扱います。

### `curiosity`

`気になる`, `知りたい`, `興味`, `試したい` のような表現、または関連 lemma で判定します。  
探索意欲や関心の高さとして扱います。

### `neutral`

上のどれにも当たらなければ `neutral` です。  
感情がないというより、「今の簡易ルールでは強い感情シグナルを見つけられなかった」という意味です。

なお、否定表現が検出された場合は、感情シグナルをそのまま強い感情として扱わないように少し抑制します。  
例えば「不安はない」は、単語だけ見れば `anxiety` に見えますが、今は `neutral` に寄せるようにしています。

## Scores

各スコアは 0.0 から 1.0 の範囲に丸められます。  
今の値は学習済みではなく、初期の手書きルールです。

### `persistence_value`

長期記憶として残しておく価値を表します。  
好み、欲求、内省、関係性、感情を含むと上がります。

### `retrieval_value`

後で思い出す価値を表します。  
未来表現や選択支援の文脈があると上がります。

### `affective_value`

感情的な意味の強さを表します。  
感情が `neutral` でないと上がりますが、否定表現があれば少し抑制します。

### `identity_value`

その人らしさや価値観につながる度合いを表します。  
好み、欲求、内省があると上がります。

### `relationship_value`

人間関係に関する重要度を表します。  
関係語があると大きく上がります。

### `practical_value`

日常の判断や支援に使える度合いを表します。  
選択支援、タスク、技術語、固有表現などがあると上がります。

### `task_value`

未完了タスクとして扱うべき度合いを表します。  
タスク語や未来語があると上がります。

### `decision_value`

選択や判断の材料として重要かを表します。  
今は主に `decision_support` に反応して上がります。

### `indexability_value`

検索や分類のしやすさを表します。  
topic 数が多い、技術語がある、固有表現が取れた、という条件で上がります。

## Scores の具体的な加点条件

今の `scores` は、次のような条件で増減します。

### `persistence_value`

初期値は `0.35` です。  
次の条件で上がります。

- `preference` または `desire` がある
- `reflection` がある
- `relationship` がある
- `emotion.primary` が `neutral` 以外

長く残しておく価値があるかを、好み・内省・関係性・感情から見ています。

### `retrieval_value`

初期値は `0.25` です。  
次の条件で上がります。

- `FUTURE_TERMS` がある
- `decision_support` がある

つまり、「あとで思い出す文脈が発生しやすいか」を未来参照と判断支援から見ています。

### `affective_value`

初期値は `0.2` です。  
次の条件で上がります。

- `emotion.primary` が `neutral` 以外

次の条件で少し下がります。

- negation がある

これは、「感情語が見えても否定されているなら、そのまま強い感情として扱わない」ためです。

### `identity_value`

初期値は `0.2` です。  
次の条件で上がります。

- `preference` または `desire` がある
- `reflection` がある

価値観や自己理解への寄与を、主に好み・欲求・内省から見ています。

### `relationship_value`

初期値は `0.05` です。  
`relationship` があると大きく上がります。

### `practical_value`

初期値は `0.15` です。  
次の条件で上がります。

- `decision_support` がある
- `task` がある
- `entities` がある
- `TECHNICAL_MARKERS` がある

日常の判断支援や実務的な再利用に効きそうかを見ています。

### `task_value`

初期値は `0.05` です。  
次の条件で上がります。

- `task` がある
- `FUTURE_TERMS` がある

### `decision_value`

初期値は `0.05` です。  
`decision_support` があると上がります。

### `indexability_value`

初期値は `0.2` です。  
次の条件で上がります。

- topic が3件以上ある
- `entities` がある
- `TECHNICAL_MARKERS` がある

検索や分類に使える手がかりがどれくらいあるかを見ています。

## Save Strength

今の設計では、会話は原則としてすべて保存します。  
その代わりに、記憶ごとに「どれくらい強い長期記憶として扱うか」を `save_strength` で表します。

`save_strength` は次の既存スコアから合成しています。

- `persistence_value`
- `affective_value`
- `identity_value`
- `relationship_value`
- `practical_value`
- `task_value`
- `retrieval_value`

現在の重みづけは次の通りです。

- persistence: 0.30
- affective: 0.20
- identity: 0.15
- relationship: 0.10
- practical: 0.10
- task: 0.10
- retrieval: 0.05

さらに、理由コードに応じて微調整をします。

- `has_sensitive_topic` があると少し上げる
- `has_decision_support` があると少し上げる
- `has_future_reference` があると少し上げる
- `has_named_entity` があると少し上げる
- `is_short_ack` があると下げる
- `is_low_information` があると下げる
- `is_context_only` しかないと少し下げる

ここで重要なのは、「低いから保存しない」ではないことです。  
低い記憶も保存し、あとで検索や再評価の対象に残します。

## Memory Priority

`save_strength` から、さらに扱いやすい4段階の `memory_priority` を決めています。

- `low`: 0.00 - 0.29
- `medium`: 0.30 - 0.54
- `high`: 0.55 - 0.79
- `critical`: 0.80 - 1.00

意味は次の通りです。

- `low`
  保存はするが、普段の自動想起では前に出しにくい
- `medium`
  文脈が合えば使う候補
- `high`
  長期記憶としてかなり重要
- `critical`
  強く覚えておくべき記憶

## Recall Policy

`recall_policy` は、記憶をどう出し直すかの簡易ルールです。

### `mode`

- `normal`
  通常の記憶として扱う
- `gentle`
  感情価値が高いので、やや丁寧に持ち出す
- `explicit_only`
  センシティブ語が含まれるので、明示的な文脈でのみ扱う

### `allowed_contexts`

思い出してよい文脈です。  
今は `related_topic` を基本に、`decision_support`, `follow_up`, `emotional_support` を追加します。

追加条件は次の通りです。

- `practical_value >= 0.35` なら `decision_support`
- `task_value >= 0.3` なら `follow_up`
- `affective_value >= 0.45` なら `emotional_support`

### `avoid_contexts`

不用意に思い出さない方がよい文脈です。  
感情価値が高いと `unrelated_smalltalk`、センシティブなら `casual_joking` も避けます。

### `suggested_phrasing`

今は単純に、元の文の先頭40文字を使って「以前、〜という話があったけど」と返すだけです。  
まだ自然な想起文生成ではありません。

### `auto_recall_threshold`

自動想起の強さの目安です。  
`gentle` のときは高め、通常時はやや低めです。

今は具体的に、

- `gentle` なら `0.75`
- それ以外は `0.65`

です。

## Safety

### `sensitivity`

`病気`, `トラウマ`, `家族`, `お金`, `秘密`, `恋人` があると `sensitive`、なければ `normal` です。  
これは保存可否ではなく、扱いの慎重さを示します。

### `privacy_level`

今はすべて `personal` 固定です。  
将来的に `public`, `private` などへ分ける余地があります。

### `stability`

今はすべて `medium` 固定です。  
将来的には「一時的な気分」か「長期的な価値観」かで分けたいです。

### `source_confidence`

今は `0.9` 固定です。  
本人の直接発話をそのまま保存する前提だからです。

### `needs_confirmation`

今は `False` 固定です。  
推測保存や曖昧抽出を後で導入したら意味が出ます。

## Facets

`facets` は、1つの記憶を用途別に見やすくするための整理用フィールドです。  
今は次の6種類を保存しています。

### `practical`

- `goal`
- `constraints`

現時点では固定値に近く、解析器の方針をメモしているだけです。  
まだ高精度に文から抽出しているわけではありません。

### `emotional`

- `need`
- `friction`

`emotion.primary` が `neutral` 以外なら、「感情を伴う記憶として扱う」という `need` を入れます。  
`frustration` または `anxiety` のときは、元文の先頭60文字を `friction` に入れます。

### `identity`

- `values`
- `self_view`

`values` には `preference`, `desire`, `reflection` のような自己理解寄りの `memory_type` を入れます。  
`self_view` には先頭2件の topic を入れます。

### `relationship`

- `people`
- `relation_context`

`people` には、entity と topic のうち `友達`, `家族`, `母`, `父`, `恋人` に当たるものを入れます。  
`relationship` 型の記憶であれば `relation_context` を `personal` にします。

### `task`

- `open_tasks`
- `deadlines`

`task` 型なら、元文の先頭80文字を `open_tasks` に入れます。  
`deadlines` には `FUTURE_TERMS` に当たった語を入れます。

### `decision`

- `decisions`
- `rejected_options`

`decision_support` 型なら、元文の先頭80文字を `decisions` に入れます。  
`rejected_options` は今は常に空です。

## Reason Codes

`reason_codes` は、なぜその記憶強度になったかを人間が追いやすくするための理由ラベルです。  
今は次のようなコードを使っています。

- `has_preference`
- `has_desire`
- `has_worry`
- `has_reflection`
- `has_relationship`
- `has_decision_support`
- `has_task_signal`
- `has_future_reference`
- `has_emotion_signal`
- `has_sensitive_topic`
- `has_technical_marker`
- `has_rich_topics`
- `has_named_entity`
- `has_negation`
- `is_short_ack`
- `is_low_information`
- `is_context_only`

### `has_preference`

好み・嫌悪・苦手意識の表現が含まれていることを示します。  
長期的な嗜好や避けたいものは、あとで会話支援に効くため、保存強度を上げる理由になります。

### `has_desire`

「したい」「ほしい」のような希望や欲求が含まれていることを示します。  
将来の行動や選択支援につながるため、保存価値があるとみなします。

### `has_worry`

不安や心配、困りごとを示す表現が含まれていることを示します。  
継続的な悩みやケア対象になりうるため、感情面と保存強度の両方に効きます。

### `has_reflection`

内省や違和感、自分なりの考えが含まれていることを示します。  
価値観や自己理解に関わる発話として扱うため、長期記憶寄りに評価します。

### `has_relationship`

家族、恋人、友人など、人間関係に関わる語が含まれていることを示します。  
関係性の記憶は後の会話で重要になりやすいため、優先度を上げる理由になります。

### `has_decision_support`

「どれを選ぶか」「決めてほしい」のように、判断支援の要求が含まれていることを示します。  
実用的な会話支援につながるため、`practical_value` と `save_strength` を上げる方向に使います。

### `has_task_signal`

やること、作ること、確認することなど、未完了タスクの匂いがあることを示します。  
あとでフォローアップや想起が必要になるかもしれないため、記憶強度を上げる理由になります。

### `has_future_reference`

「明日」「来週」「あとで」など、未来時点への参照があることを示します。  
後の会話で思い出す価値があるため、`retrieval_value` と `save_strength` に加点します。

### `has_emotion_signal`

強い感情ではなくても、`neutral` 以外の感情シグナルが拾えたことを示します。  
その発話が単なる事実ではなく、感情を伴った体験かもしれないため、保存強度を上げます。

### `has_sensitive_topic`

病気、お金、秘密、恋人など、慎重に扱うべき話題が含まれていることを示します。  
重要である一方で、想起の仕方に注意が必要な記憶として扱います。

### `has_technical_marker`

URL、ファイル名、技術名、パス記法など、技術的な手がかりが含まれていることを示します。  
検索しやすく、実務支援にも使いやすい発話として少し加点します。

### `has_rich_topics`

抽出された topic が比較的多く、話題の手がかりが豊富であることを示します。  
検索や再利用のしやすさに寄与するため、情報密度がやや高い記憶として扱います。

### `has_named_entity`

GiNZA によって固有表現が取れたことを示します。  
人名、場所、作品、組織などの手がかりは後の検索や会話想起に効きやすいため、少し保存強度を上げます。

### `has_negation`

否定表現が文に含まれていることを示します。  
これは直接の加点理由ではなく、「単語が含まれているだけで感情や不安と断定しないための注意シグナル」として使います。

### `is_short_ack`

「ありがとう」「了解」「OK」のような短い相槌であることを示します。  
全件保存方針なので削除はしませんが、普段は前に出しにくい低優先度記憶として扱います。

### `is_low_information`

文章が短く、topic も少なく、情報の手がかりが少ないことを示します。  
将来の検索や会話支援に効きにくいため、保存強度を下げる理由になります。

### `is_context_only`

現在のルールでは、好み・感情・タスク・関係性などの明確な型を付けられなかったことを示します。  
無価値という意味ではなく、「今の簡易判定器では文脈情報としてしか扱えていない」状態です。

## `should_save` はあるのか

今の設計では `should_save` は使っていません。  
理由は、会話を原則として全件保存する方針にしているからです。

今のMVPでは、

- 保存するかどうか

ではなく、

- 保存した上で、どれくらい強い記憶として扱うか

を主眼にしています。

## 限界

今のスコアリングには、はっきりした限界があります。

- GiNZA を入れても感情理解そのものが高精度になったわけではない
- 否定や文脈の取り違えは少し改善したが、まだ完全ではない
- `reason_codes` はあるが、まだ粒度が粗く、重みとの対応も単純
- 実データによる評価・調整ループがない

つまり、今は「GiNZA を使った保存ルールの初期たたき台」であって、精度の高い記憶判定器ではありません。

## 何ができるようになったか

GiNZA 導入により、少なくとも次が初期版より改善しました。

- token を日本語として少し自然に分割できる
- 活用形でも lemma ベースで `memory_types` を拾いやすい
- `topics` と `keywords` を名詞・固有名詞・原形ベースで作れる
- 固有表現を `entities` として保存できる
- 否定表現があると感情シグナルを少し抑えられる

## テストで見やすい例

改善を確認しやすい入力例は次です。

1. 活用形の内省
   `AIに相談できると助かると感じた。`
   期待:
   `reflection` が付く、`感じる` が keyword に入る

2. 否定付き不安
   `不安はないので大丈夫。`
   期待:
   `has_negation` が付く、`emotion.primary` は `neutral` に寄る

3. 固有表現付き話題
   `来週、東京で村上春樹の新刊を探したい。`
   期待:
   `entities` や `topics` が前より意味のある形で出る

## 次に更新すべき項目

今後スコアを改善するなら、少なくとも次をこの文書へ追記すべきです。

- `save_strength`
- `memory_priority`
- `reason_codes`
- スコア変更の理由
- 誤判定の具体例
