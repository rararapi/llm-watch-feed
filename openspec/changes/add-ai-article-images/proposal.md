## Why

SSGサイトの記事サムネは現在「記事元のOG画像(`image_url`)→ソース名プレースホルダ」で、OG画像が無い記事が多く視覚的に弱い。記事の要約・内容を象徴するAIアイキャッチ画像を自動生成して付与し、一覧の視認性・訴求力を高める。既に Vertex AI（Gemini）を ADC で利用しているため、画像生成（Gemini 2.5 Flash Image）を同一基盤・同一認証で追加でき、APIキー新規発行も別サービスも不要。

## What Changes

- ニュース更新パイプラインに**AI画像生成ステップ**を追加（新規 `scripts/generate_images.py`）。`run_job.sh` の `collect` の後・`generate_pages` の前に挿入。
- 生成対象は **`importance == "A"` の記事のみ**（コスト制御）。`image_generated_url` 未設定の記事だけを処理する冪等な実装。
- 画像生成モデルは **Vertex AI の Gemini 2.5 Flash Image**。既存の `GCP_PROJECT` / ADC を利用。
- **2段階プロンプト**：要約・タイトル・タグ → Gemini で英語の抽象的視覚プロンプト＋日本語altを生成 → 画像生成。画像内に文字は描かせず、実在ロゴ・人物・商標を避ける。
- AI画像は**記事元OG画像の `image_url` とは別フィールド** `image_generated_url`（+ `image_generated_alt` / `image_generated_prompt`）に保存。公開GCSバケットの `images/<記事id>.webp`（`id` は URL-SHA256）へ不変キャッシュ付きで保存。
- SSGのサムネ表示を **AI画像(`image_generated_url`) → 元記事OG画像(`image_url`) → プレースホルダ** の優先順に変更（`generate_pages.py` の派生フィールド `_thumb` ＋ `templates/partials/macros.html`）。SNS共有用 `og:image` は外部互換のため従来どおり OG画像/既定画像のまま。
- 新規環境変数：`VERTEX_IMAGE_MODEL`（既定 `gemini-2.5-flash-image`）、`IMAGE_MIN_IMPORTANCE`（既定 `A`）、`IMAGE_MAX_PER_RUN`、`IMAGE_BASE_URL`。
- **堅牢性**：`GCP_PROJECT`/`GCS_BUCKET` 未設定や生成失敗時は `image_generated_url` を付けず完走（1記事・1ソースの失敗で全体を落とさない既存方針を踏襲）。

### Non-goals（今回やらないこと）

- importance B / C への定常生成（当面 A のみ。env で将来拡張可能にとどめる）。一括バックフィルは別途運用で実施。
- `og:image`（SNS共有画像）のAI画像化（外部スクレイパ互換・アスペクト比のため見送り。将来検討）。
- Imagen 等の別モデル対応（今回は Gemini 2.5 Flash Image に限定。env で差し替え可能にはする）。
- 孤児画像（`models.json` から消えた記事の `images/`）の自動クリーンアップ。
- 画像内へのタイトル文字描画・ブランドロゴ再現（不安定かつ権利リスクのため意図的に避ける）。

## Capabilities

### New Capabilities
- `ai-article-images`: 記事の要約・タイトルから視覚的アイキャッチを Vertex AI（Gemini 2.5 Flash Image）で生成し、公開GCSバケットへ保存、`image_generated_url` 経由で SSG サイトに優先表示する一連の挙動（対象選別・冪等性・フォールバックを含む）。

### Modified Capabilities
- `state-storage`: `models.json` スキーマに AI画像参照フィールド（`image_generated_url` / `image_generated_alt` / `image_generated_prompt`）を追加（既存の OG画像 `image_url` とは別フィールド）。
- `cloud-execution`: ニュース更新ジョブに AI画像生成ステップ（`collect` と `generate_pages` の間）を追加。
- `site-publishing`: AI画像を公開GCSバケットの `images/` 配下へ不変キャッシュ付きで配信し、SSG サムネを AI画像優先で表示。

## Impact

- **新規コード**: `scripts/generate_images.py`。
- **変更コード**: `scripts/run_job.sh`（ステップ挿入）、`scripts/generate_pages.py`（`_thumb` 派生フィールド）、`templates/partials/macros.html`（サムネ src）、`requirements-job.txt`（`google-genai`/`Pillow`）、`.env.example`、`AGENTS.md` / `DEPLOY.md`。
- **依存**: 画像生成に `google-genai`、WebP変換に `Pillow`（いずれもジョブ専用 `requirements-job.txt`）。Dockerfile は `requirements-job.txt` を導入済みのため変更不要。
- **GCP**: 実行サービスアカウントは既存の `roles/aiplatform.user` ＋バケット `storage.objectAdmin` で充足（追加権限なし）。`us-central1` で画像モデル利用可。Cloud Run Job の `task-timeout` は画像モデルの分間クォータ(429)を考慮し延長。
- **コスト**: 約 $0.039/枚 × A記事のみ。1日数枚規模で月数百円以内。
