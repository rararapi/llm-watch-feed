## Context

本番は SSG 構成（`scripts/generate_pages.py` + Jinja `templates/`）で、`index.html`/`articles/<id>.html`/`assets/` を公開GCSバケットへ配信する。サムネは `templates/partials/macros.html` の `thumb` マクロが記事元OG画像 `image_url` を描画し、無ければソース名プレースホルダを表示する。`image_url` は `collect.py`(`fetch_og_image`) と `backfill_images.py` が設定（どちらも既存値を保持）。分析・要約は Vertex AI（Gemini）を ADC で利用。

本変更は、要約から生成したAIアイキャッチを既存基盤（同一プロジェクト・同一ADC・同一バケット）に1ステップ追加して付与し、SSGサムネで優先表示する。`image_url`(OG) の意味を壊さないよう **別フィールド** `image_generated_url` を使う。

## Goals / Non-Goals

**Goals:**
- 要約からAIアイキャッチを自動生成し、公開GCSへ保存、SSGサムネで AI画像→OG画像→プレースホルダ の順に表示。
- 既存SSGパイプラインへの最小侵襲な追加（新規 `generate_images.py` を1ステップ挿入＋テンプレ1行＋派生フィールド1つ）。
- 冪等・コスト制御・フォールバックを備え、画像生成が失敗してもジョブは正常終了する。

**Non-Goals:**
- importance B/C への定常生成、`og:image` のAI画像化、Imagen 等別モデル、孤児画像GC、画像内文字・ロゴ再現。

## Decisions

### D1. 別フィールド `image_generated_url`（`image_url` を上書きしない）
- **理由**: `image_url` は既に「記事元OG画像」として `collect.py`/`backfill_images.py`/テンプレで使われている。AI画像を同じ枠に入れると意味が衝突し、収集側の上書き競合や運用混乱を招く。別フィールドにすれば両者を独立に保持でき、テンプレ側で優先順位を制御できる。
- **代替**: `image_url` を上書き（最小だが意味衝突・競合リスク）→ 不採用。

### D2. 生成モデルは Vertex AI の Gemini 2.5 Flash Image
- **理由**: 既存の Gemini 利用と同一の Vertex AI / ADC / `GCP_PROJECT` でそのまま動く。約 $0.039/枚と安価。`VERTEX_IMAGE_MODEL` で差し替え可能。
- **代替**: Imagen（高精細だが過剰・コスト高）、外部API（APIキー管理増で方針違反）→ 不採用。

### D3. 独立スクリプト `scripts/generate_images.py`＋2段階プロンプト
- 単一責務。`run_job.sh` で `collect` の後・`generate_pages` の前に挿入。
- Gemini(テキスト)で英語の抽象視覚プロンプト＋日本語altを生成 → 画像化。構図安定・安全制御のため2段階。

### D4. 保存・命名・キャッシュ・形式
- 公開バケット `images/<記事id>.webp`（`id`=URL-SHA256）。`-state` には置かない。
- 不変キャッシュ `public, max-age=31536000, immutable`。
- Gemini出力(PNG)を Pillow で WebP 変換（配信軽量）。`google-genai` と `Pillow` はジョブ専用 `requirements-job.txt` に追加（ベースは軽量維持。Dockerfile は requirements-job.txt 導入済みで変更不要）。

### D5. SSG表示は派生フィールド `_thumb` で優先順位を集約
- `generate_pages.py:prepare()` で `a["_thumb"] = image_generated_url or image_url or None` を計算し、`macros.html` の `thumb` は `_thumb` を描画。既存CSS（`.thumb` 16:9・`.thumb__img` object-fit:cover・`onerror` でプレースホルダ）をそのまま活用。
- `og:image` は `image_url`/既定のまま（外部スクレイパのwebp/比率互換リスク回避）。

### D6. 冪等性・コスト制御・障害分離
- 対象＝`importance==IMAGE_MIN_IMPORTANCE` かつ `image_generated_url` 未設定。
- 生成前に GCS `blob.exists()` で既存チェック→あれば参照のみ補完（枠を消費しない）。
- 1実行 `IMAGE_MAX_PER_RUN` 枚で打ち切り・残数ログ。1記事失敗は try/except＋`__main__` でも握り潰し後続継続。

## Risks / Trade-offs

- [権利・誤情報：実在ロゴ/人物の混入] → プロンプトで禁止し抽象構図に限定。画像内文字も描かせない。
- [画像モデルの分間クォータ(429)] → 1記事失敗扱いでスキップ→冪等再実行で補完。Cloud Run Job の `task-timeout` を延長。一括バックフィルは再試行ループで実施。
- [コスト増（2段階＝画像1+テキスト1/記事）] → A記事のみ＋上限＋冪等で再生成なし。月数百円規模。
- [WebP変換の追加依存(Pillow)・google-genai] → ジョブ専用 requirements に隔離。ベースは軽量のまま。
- [`image_url` 運用との将来差異] → 新規記事は collect が OG画像、generate_images が A記事にAI画像。テンプレが優先制御するので一覧は破綻しない。

## Migration Plan

1. SAの `roles/aiplatform.user` ＋バケット `storage.objectAdmin`、`us-central1` の画像モデル利用可を確認（既存で充足見込み）。
2. ローカルでSSGをビルドし、AI画像→OG→プレースホルダの優先表示を目視確認（3ケース）。
3. ブランチをマージ → ジョブイメージを更新（`requirements-job.txt` 反映）→ Cloud Run Job の env（`VERTEX_IMAGE_MODEL`/`IMAGE_*`）と `task-timeout` を更新。
4. 一度限りの一括バックフィル（既存記事の A／必要なら B）：download → generate_images（A／B）→ upload → generate_pages → publish-pages。`blob.exists()` により既生成画像は無料で参照補完。
5. **ロールバック**: `run_job.sh` から画像生成ステップを外す＋テンプレの `_thumb` を `image_url` に戻せば従来表示へ。`image_generated_url` は残っても OG優先に戻すだけで害なし。

## Open Questions

- `og:image` もAI画像にするか（SNS共有の見栄え向上 vs 外部互換・比率）。当面は見送り。
- 一括バックフィルで B記事まで含めるか（運用判断。既に36件分の画像はバケットに生成済み）。
