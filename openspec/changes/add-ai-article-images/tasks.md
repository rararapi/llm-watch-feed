## 1. 事前確認（GCP）

- [x] 1.1 実行SA `llm-watch-job@` が `roles/aiplatform.user` ＋公開バケット `storage.objectAdmin` を保有することを確認（追加権限不要）
- [x] 1.2 `us-central1` で `gemini-2.5-flash-image` が利用可能か確認（スモークテストで200応答・画像取得を確認）

## 2. 設定・スキーマ・依存

- [x] 2.1 `.env.example` に `VERTEX_IMAGE_MODEL` / `IMAGE_MIN_IMPORTANCE` / `IMAGE_MAX_PER_RUN` / `IMAGE_BASE_URL` を追加
- [x] 2.2 `requirements-job.txt` に `google-genai` / `Pillow` を追加（Dockerfile は requirements-job.txt 導入済みで変更不要）
- [x] 2.3 `models.json` スキーマへ `image_generated_url` / `image_generated_alt` / `image_generated_prompt` を AGENTS.md に反映

## 3. 画像生成スクリプト（scripts/generate_images.py）

- [x] 3.1 `models.json` を読み、`image_generated_url` 未設定かつ `importance == IMAGE_MIN_IMPORTANCE` の対象を抽出
- [x] 3.2 google-genai を Vertex モードで ADC 初期化（`GCP_PROJECT`/依存欠落/失敗なら画像なし完走）
- [x] 3.3 2段階プロンプト：Gemini で英語の抽象視覚プロンプト＋日本語altを生成（画像内文字・実在ロゴ/人物を禁止）
- [x] 3.4 視覚プロンプトから Gemini 2.5 Flash Image で画像を1枚生成
- [x] 3.5 Pillow で WebP 変換し、公開バケット `images/<id>.webp` へ不変キャッシュ＋content-type付きで直接アップロード
- [x] 3.6 `image_generated_url` / `image_generated_alt` / `image_generated_prompt` を書き戻し（`image_url` は触らない）
- [x] 3.7 冪等性：`image_generated_url` 既設、または GCS に同一IDの画像が `blob.exists()` で存在ならスキップ／参照補完
- [x] 3.8 コスト制御：1実行 `IMAGE_MAX_PER_RUN` 枚で打ち切り、残数をログ出力
- [x] 3.9 障害分離：1記事の失敗は try/except でログのみ・`__main__` でも握り潰し後続継続

## 4. パイプライン統合

- [x] 4.1 `scripts/run_job.sh` の `collect` と `generate_feeds`/`generate_pages` の間に `generate_images.py` を挿入し番号/ログを更新

## 5. SSG表示（generate_pages.py + templates）

- [x] 5.1 `generate_pages.py:prepare()` に `_thumb = image_generated_url or image_url or None` を追加（`og:image` は従来どおり）
- [x] 5.2 `templates/partials/macros.html` の `thumb` マクロを `a._thumb` 参照に変更（一覧カード・記事ヘッダー両対応）
- [x] 5.3 既存CSS（16:9・object-fit:cover・onerrorプレースホルダ）で破綻しないことを確認

## 6. 検証（ローカル）

- [x] 6.1 SSGをローカルビルドし、AI画像→OG画像→プレースホルダの優先表示を3ケースで確認（index＋記事ヘッダー）
- [x] 6.2 `generate_images.py` のフォールバック（GCS_BUCKET未設定）で exit 0・データ不変を確認
- [x] 6.3 冪等性：`image_generated_url` 既設はスキップ、対象抽出が正しいことを確認
- [x] 6.4 構文チェック（py / `bash -n run_job.sh`）

## 7. 本番反映（運用者・要GCP／デプロイ判断）

- [ ] 7.1 ブランチをマージし、Cloud Run Job のイメージを再ビルド（`requirements-job.txt` 反映）
- [ ] 7.2 Cloud Run Job の env に `VERTEX_IMAGE_MODEL`/`IMAGE_MIN_IMPORTANCE`/`IMAGE_MAX_PER_RUN` を追加し `task-timeout` を延長
- [ ] 7.3 一括バックフィル：download → generate_images（A／必要ならB）→ upload → generate_pages → publish-pages（既生成36枚は `blob.exists()` で無料補完）
- [ ] 7.4 公開サイトでサムネがAI画像になっていること・画像なし記事が破綻しないことを目視確認
