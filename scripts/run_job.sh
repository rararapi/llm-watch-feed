#!/usr/bin/env bash
#
# Cloud Run Job entrypoint: ニュース更新ジョブ（毎日）
#
#   1. GCS から models.json(状態) を取得（無ければ初回として空開始）
#   2. collect.py で収集・分析
#   3. generate_feeds.py でフィード生成
#   4. generate_pages.py でサイト(index/articles/assets)生成
#   5. 更新後 models.json を GCS へ保存（＝公開配信データ data/models.json）
#   6. RSS フィードを GCS の feeds/ へ配信
#   7. 生成サイト(index/articles/assets)を GCS へ配信
#
# このジョブは「ニュース更新」だけを行う。記事ページHTMLは feeds と同じ“バッチ生成物”として
# GCSへ書き込むだけで、サイトの「デプロイ」ではない（firebase deploy は走らない）。
# 画面テンプレ/デザイン変更時のデプロイは scripts/deploy_site.sh に分離してある。
#
# 必須環境変数:
#   GCS_BUCKET        配信／状態バケット名
#   SITE_URL          公開サイトURL（generate_feeds.py のフィード自己リンク用。独自ドメイン or バケットURL）
#   GCP_PROJECT       Vertex AI のプロジェクト ID（未設定ならダミーモードで完走）
# 任意:
#   VERTEX_LOCATION   Vertex AI リージョン（既定 us-central1）
#   VERTEX_MODEL      Gemini モデル名（既定 gemini-2.5-flash）
#   GCS_OBJECT        状態=配信データのキー（既定 data/models.json）
#   PUBLIC_DIR        既定 public
#
# 認証: API キーは使わず ADC（実行サービスアカウント）で Vertex AI / GCS を呼ぶ。
#       サービスアカウントに roles/aiplatform.user と対象バケットの read/write を付与しておくこと。
set -euo pipefail

PUBLIC_DIR="${PUBLIC_DIR:-public}"
# 配信レイアウトに合わせた出力先。PAGES_DIR は GCS バケット直下のミラー（data/ と feeds/ はその配下）
export MODELS_JSON_PATH="${MODELS_JSON_PATH:-$PUBLIC_DIR/data/models.json}"
export FEEDS_DIR="${FEEDS_DIR:-$PUBLIC_DIR/feeds}"
export PAGES_DIR="${PAGES_DIR:-$PUBLIC_DIR}"

mkdir -p "$(dirname "$MODELS_JSON_PATH")" "$FEEDS_DIR" "$PAGES_DIR/articles"

echo "[run_job] 1/7 download state from GCS"
python scripts/gcs_sync.py download

echo "[run_job] 2/7 collect"
python scripts/collect.py

echo "[run_job] 3/7 generate feeds"
python scripts/generate_feeds.py

echo "[run_job] 4/7 generate site pages"
python scripts/generate_pages.py

echo "[run_job] 5/7 upload state (= published data) to GCS"
python scripts/gcs_sync.py upload

echo "[run_job] 6/7 publish feeds to GCS"
python scripts/gcs_sync.py publish-feeds

echo "[run_job] 7/7 publish site pages to GCS"
python scripts/gcs_sync.py publish-pages

echo "[run_job] done"
