## ADDED Requirements

### Requirement: AIアイキャッチ画像の自動生成

システムはニュース更新パイプラインの中で、記事の要約・タイトル・タグから内容を象徴する視覚的アイキャッチ画像を Vertex AI（Gemini 2.5 Flash Image）で生成 SHALL する。認証は実行環境の Application Default Credentials（既存の `GCP_PROJECT` / サービスアカウント）で行い、API キー等のシークレットを保持・注入 SHALL NOT する。生成モデルは `VERTEX_IMAGE_MODEL`（既定 `gemini-2.5-flash-image`）で設定可能 SHALL とする。

#### Scenario: 対象記事の画像を生成する

- **WHEN** 画像生成ステップが、画像未生成かつ生成対象の記事を処理する
- **THEN** Vertex AI で画像が1枚生成され、所定の保存先に保管されたうえで記事レコードから参照できる

#### Scenario: Vertex AI を ADC で利用する

- **WHEN** `GCP_PROJECT` が設定され、サービスアカウントに `roles/aiplatform.user` が付与されている
- **THEN** 画像生成は ADC で認証され、API キーを用いずに実行される

### Requirement: OG画像とは別フィールドへの保存

システムは AI生成画像の参照を、記事元のOG画像 `image_url` とは**別フィールド** `image_generated_url`（および `image_generated_alt` / `image_generated_prompt`）に保存 SHALL する。AI画像生成は `image_url` を書き換え SHALL NOT し、収集処理（OG画像の付与）と相互に上書きし SHALL NOT する。

#### Scenario: image_url を上書きしない

- **WHEN** AI画像が生成され記事レコードに書き戻される
- **THEN** `image_generated_url` が設定され、既存の `image_url`（OG画像）は変更されない

### Requirement: 生成対象の選別とコスト制御

システムは生成対象を重要度で限定 SHALL し、既定では `importance == "A"` の記事のみを生成対象 SHALL とする（`IMAGE_MIN_IMPORTANCE` で変更可）。1回の実行で生成する枚数は上限（`IMAGE_MAX_PER_RUN`）で制限 SHALL する。

#### Scenario: 重要度Aのみ生成する

- **WHEN** `importance` が対象重要度でない記事を処理する
- **THEN** その記事の画像は生成されず、`image_generated_url` も付与されない

#### Scenario: 1実行あたりの生成枚数を上限で制限する

- **WHEN** 画像未生成の対象記事数が `IMAGE_MAX_PER_RUN` を超える
- **THEN** 当該実行では上限枚数までを生成し、残りは後続の実行に持ち越す

### Requirement: 画像生成の冪等性

システムは既に AI画像を保持する記事を再生成 SHALL NOT する。記事レコードに `image_generated_url` が設定済み、または保存先に当該記事の画像オブジェクトが既存である場合は生成をスキップ SHALL し、後者では参照のみ補完 SHALL する。

#### Scenario: 既に画像がある記事はスキップする

- **WHEN** `image_generated_url` が設定済みの記事を処理する
- **THEN** 画像生成は行われず、既存の参照がそのまま保持される

#### Scenario: GCSに既存画像があれば参照のみ補完する

- **WHEN** `image_generated_url` は未設定だが保存先に同一記事IDの画像が存在する記事を処理する
- **THEN** 画像生成は行われず、既存画像を指す `image_generated_url` が補完される（生成枚数の上限を消費しない）

### Requirement: プロンプト設計と安全性

システムは画像を「抽象的・概念的なアイキャッチ」として生成 SHALL し、画像内に文字（タイトル等）を描画 SHALL NOT する。実在企業のロゴ・商標・実在人物の再現はプロンプトで回避 SHALL する。要約・タイトル・タグから視覚プロンプトと代替テキストを生成し、それを基に画像生成する2段階方式 SHALL とする。

#### Scenario: 概念的なアイキャッチを生成する

- **WHEN** 記事の要約・タイトルから画像プロンプトを生成する
- **THEN** プロンプトは抽象的・概念的な構図を指示し、画像内文字・実在ロゴ・実在人物の再現を含めない

### Requirement: 生成失敗時のフォールバック

システムは画像生成（モデル呼び出し・変換・保存）に失敗した場合、ジョブをエラー終了 SHALL NOT し、当該記事の `image_generated_url` を付与せずにパイプライン全体を完走 SHALL する。`GCP_PROJECT` / `GCS_BUCKET` 未設定や依存欠落でも同様に画像なしで完走 SHALL する。1記事の失敗が他記事や後続ステップを止め SHALL NOT する。

#### Scenario: 1記事の生成失敗で全体が落ちない

- **WHEN** ある記事の画像生成または保存が失敗する
- **THEN** 失敗はログに記録され、その記事は `image_generated_url` なしのまま、他記事の処理と後続ステップが継続する

#### Scenario: 構成未設定では画像なしで完走する

- **WHEN** `GCP_PROJECT` または `GCS_BUCKET` が未設定で画像生成ステップが実行される
- **THEN** 画像は生成されず、`image_generated_url` を付与しないままパイプライン全体が正常終了する

### Requirement: サイトでのAI画像優先表示

システムは SSG のサムネイルを **AI画像(`image_generated_url`) → 記事元OG画像(`image_url`) → プレースホルダ** の優先順で表示 SHALL する。画像読み込みに失敗した場合はプレースホルダにフォールバック SHALL し、表示が破綻 SHALL NOT する。

#### Scenario: AI画像があればそれを表示する

- **WHEN** 記事が `image_generated_url` と `image_url` の両方を持つ
- **THEN** サムネイルには `image_generated_url`（AI画像）が用いられる

#### Scenario: AI画像が無くOG画像があればOG画像を表示する

- **WHEN** 記事が `image_generated_url` を持たず `image_url`（OG画像）を持つ
- **THEN** サムネイルには `image_url` が用いられる

#### Scenario: どちらも無ければプレースホルダを表示する

- **WHEN** 記事が `image_generated_url` も `image_url` も持たない
- **THEN** ソース名由来の色のプレースホルダが表示され、レイアウトは破綻しない
