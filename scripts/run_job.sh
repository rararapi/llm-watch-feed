#!/usr/bin/env bash
#
# Cloud Run Job entrypoint: ニュース更新ジョブ（毎日）
#
#   1. GCS から models.json(状態) を取得（無ければ初回として空開始）
#   2. collect.py で収集・分析
#   3. generate_feeds.py でフィード生成
#   4. 更新後 models.json を GCS へ保存（＝公開配信データ data/models.json）
#   5. RSS フィードを GCS の feeds/ へ配信
#
# このジョブは「ニュース更新」だけを行う。サイト(index.html 等)のデプロイは
# scripts/deploy_site.sh に分離してあり、ここでは触らない。
# 配信は公開GCSバケットが直接担うため firebase deploy は不要。
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
# 配信レイアウトに合わせた出力先（data/ と feeds/）
export MODELS_JSON_PATH="${MODELS_JSON_PATH:-$PUBLIC_DIR/data/models.json}"
export FEEDS_DIR="${FEEDS_DIR:-$PUBLIC_DIR/feeds}"

mkdir -p "$(dirname "$MODELS_JSON_PATH")" "$FEEDS_DIR"

echo "[run_job] 1/5 download state from GCS"
python scripts/gcs_sync.py download

echo "[run_job] 2/5 collect"
python scripts/collect.py

echo "[run_job] 3/5 generate feeds"
python scripts/generate_feeds.py

echo "[run_job] 4/5 upload state (= published data) to GCS"
python scripts/gcs_sync.py upload

echo "[run_job] 5/5 publish feeds to GCS"
python scripts/gcs_sync.py publish-feeds

echo "[run_job] done"
