## ADDED Requirements

### Requirement: 記事レコードのAI画像参照フィールド

システムは `models.json` の各記事レコードに、AI生成画像の参照フィールドを保持できる SHALL とする。
AI画像が生成された記事は `image_generated_url`（公開GCSバケット上の画像への絶対URL）を持ち、
任意で `image_generated_alt`（代替テキスト）と `image_generated_prompt`（生成に用いた視覚プロンプト、デバッグ用）を持つ。
これらは記事元OG画像の `image_url` とは別フィールド SHALL とし、相互に上書き SHALL NOT する。
AI画像が未生成・対象外・生成失敗の記事はこれらのフィールドを持たない（または空）でよく、
有無が他フィールドの読み書きや重複排除・件数上限の挙動に影響 SHALL NOT する。

#### Scenario: AI画像のある記事に参照フィールドが含まれる

- **WHEN** AI画像が生成された記事が `models.json` に保存される
- **THEN** その記事レコードは公開GCSバケット上の画像を指す `image_generated_url`（絶対URL）を含み、`image_url` は変更されない

#### Scenario: AI画像のない記事でも状態が成立する

- **WHEN** AI画像が未生成・対象外・生成失敗の記事が `models.json` に保存される
- **THEN** その記事は `image_generated_url` を持たないまま有効なレコードとして保存され、重複排除・件数上限は従来どおり動作する
