## ADDED Requirements

### Requirement: AI画像の公開GCSバケット配信

システムは生成したAIアイキャッチ画像を公開GCSバケットの `images/` 配下（キー `images/<記事id>.webp`、`id` は記事URLの SHA-256）に保存し、公開URLで直接 HTTPS 配信 SHALL する。画像は記事ごとに不変であるため、長期の不変キャッシュ（`Cache-Control: public, max-age=31536000, immutable`）を付与 SHALL する。書き込みはサービスアカウント経由に限定 SHALL し、配信画像に機密を含め SHALL NOT する。

#### Scenario: 生成画像が公開URLで取得できる

- **WHEN** 画像生成ステップが記事の画像を保存する
- **THEN** その画像は `https://storage.googleapis.com/<bucket>/images/<記事id>.webp` で認証なしに取得でき、記事レコードの `image_generated_url` がこのURLを指す

#### Scenario: 画像は不変キャッシュで配信される

- **WHEN** ブラウザ／CDN が生成画像を取得する
- **THEN** 画像には長期の不変キャッシュ（`max-age` 長期・`immutable`）が設定されており、再取得が抑制される

### Requirement: SSGサムネイルのAI画像優先

システムは SSG が生成するサムネイル（一覧カード・記事ヘッダー）の画像ソースを優先順位で決定 SHALL する。優先順位は **AI画像(`image_generated_url`) → 記事元OG画像(`image_url`) → プレースホルダ** SHALL とする。SNS共有用の `og:image` は外部スクレイパ互換のため従来どおり OG画像または既定画像 SHALL とする。

#### Scenario: サムネはAI画像を優先する

- **WHEN** SSG が `image_generated_url` を持つ記事のページを生成する
- **THEN** カード・記事ヘッダーのサムネイルは `image_generated_url` を参照する

#### Scenario: og:image は従来どおり

- **WHEN** SSG が記事ページの OGP メタを生成する
- **THEN** `og:image` は `image_url`（OG画像）または既定画像を指し、AI画像で置き換えられない
