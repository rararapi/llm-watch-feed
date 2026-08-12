#!/usr/bin/env bash
#
# Cloud Run Job entrypoint: ニュース更新ジョブ（毎日）
#
#   1. GCS から models.json(状態) を取得（無ければ初回として空開始）
#   2. collect.py で収集・分析
#   3. generate_images.py で重要度AのAIアイキャッチ画像を生成（GCSへ・別フィールド）
#   4. generate_feeds.py でフィード生成
#   5. generate_pages.py でサイト(index/articles/assets)生成
#   6. 更新後 models.json を GCS へ保存（＝公開配信データ data/models.json）
#   7. RSS フィードを GCS の feeds/ へ配信
#   8. 生成サイト(index/articles/assets)を Firebase Hosting へデプロイ
#
# Storage はデータ（data/models.json・feeds/・images/）のみ。HTML画面は Firebase Hosting が配信。
# テンプレ/デザイン変更は次回日次実行（最大24時間後）に Firebase へ反映される。
#
# 必須環境変数:
#   GCS_BUCKET        配信／状態バケット名
#   SITE_URL          公開サイトURL（Firebase Hosting URL: https://ai-watch-feed.web.app）
#   GCP_PROJECT       Vertex AI のプロジェクト ID（未設定ならダミーモードで完走）
# Firebase:
#   FIREBASE_SITE_ID  Firebase Hosting サイト ID（既定: ai-watch-feed）
# 任意:
#   VERTEX_LOCATION   Vertex AI リージョン（既定 us-central1）
#   VERTEX_MODEL      Gemini モデル名（既定 gemini-3.1-flash-lite）
#   GCS_OBJECT        状態=配信データのキー（既定 data/models.json）
#   PUBLIC_DIR        既定 public
#
# 認証: API キーは使わず ADC（実行サービスアカウント）で Vertex AI / GCS を呼ぶ。
#       サービスアカウントに roles/aiplatform.user と対象バケットの read/write を付与しておくこと。
set -euo pipefail

PUBLIC_DIR="${PUBLIC_DIR:-public}"
# サイト生成先。firebase_hosting_deploy.py がこのディレクトリを Firebase Hosting へデプロイする。
export MODELS_JSON_PATH="${MODELS_JSON_PATH:-$PUBLIC_DIR/data/models.json}"
export FEEDS_DIR="${FEEDS_DIR:-$PUBLIC_DIR/feeds}"
export PAGES_DIR="${PAGES_DIR:-$PUBLIC_DIR}"

mkdir -p "$(dirname "$MODELS_JSON_PATH")" "$FEEDS_DIR" "$PAGES_DIR/articles"

echo "[run_job] 1/7 download state from GCS"
python scripts/gcs_sync.py download

echo "[run_job] 2/8 collect"
python scripts/collect.py

echo "[run_job] 3/8 generate AI images (importance A; skips gracefully if unavailable)"
python scripts/generate_images.py

echo "[run_job] 4/8 generate feeds"
python scripts/generate_feeds.py

echo "[run_job] 5/8 generate site pages"
python scripts/generate_pages.py

echo "[run_job] 6/8 upload state (= published data) to GCS"
python scripts/gcs_sync.py upload

echo "[run_job] 7/8 publish feeds to GCS"
python scripts/gcs_sync.py publish-feeds

echo "[run_job] 8/8 deploy site pages to Firebase Hosting"
python scripts/firebase_hosting_deploy.py

echo "[run_job] done"
