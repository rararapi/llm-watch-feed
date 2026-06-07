#!/usr/bin/env bash
#
# Cloud Run Job entrypoint: download-run-upload-deploy
#
#   1. GCS から models.json(状態) を取得（無ければ初回として空開始）
#   2. collect.py で収集・分析
#   3. generate_feeds.py でフィード生成
#   4. 更新後 models.json を GCS(正本) へ保存
#   5. 公開物(index.html + feeds + models.json)を Firebase Hosting へデプロイ
#
# 必須環境変数:
#   GCS_BUCKET        状態保存バケット名
#   FIREBASE_PROJECT  Firebase/GCP プロジェクト ID
#   SITE_URL          公開サイトURL（generate_feeds.py のフィード自己リンク用）
#   GCP_PROJECT       Vertex AI のプロジェクト ID（未設定ならダミーモードで完走）
# 任意:
#   VERTEX_LOCATION   Vertex AI リージョン（既定 us-central1）
#   VERTEX_MODEL      Gemini モデル名（既定 gemini-2.5-flash）
#   GCS_OBJECT        既定 models.json
#   PUBLIC_DIR        既定 public
#
# 認証: API キーは使わず ADC（実行サービスアカウント）で Vertex AI を呼ぶ。
#       サービスアカウントに roles/aiplatform.user を付与しておくこと。
set -euo pipefail

PUBLIC_DIR="${PUBLIC_DIR:-public}"
# 公開ディレクトリを正本の出力先にして余計なコピーを避ける
export MODELS_JSON_PATH="${MODELS_JSON_PATH:-$PUBLIC_DIR/data/models.json}"
export FEEDS_DIR="${FEEDS_DIR:-$PUBLIC_DIR/feeds}"

mkdir -p "$(dirname "$MODELS_JSON_PATH")" "$FEEDS_DIR"

echo "[run_job] 1/5 download state from GCS"
python scripts/gcs_sync.py download

echo "[run_job] 2/5 collect"
python scripts/collect.py

echo "[run_job] 3/5 generate feeds"
python scripts/generate_feeds.py

echo "[run_job] 4/5 upload state to GCS"
python scripts/gcs_sync.py upload

echo "[run_job] 5/5 assemble public dir and deploy to Firebase Hosting"
cp docs/index.html "$PUBLIC_DIR/"
[ -f docs/power-automate.html ] && cp docs/power-automate.html "$PUBLIC_DIR/" || true
firebase deploy --only hosting --project "$FIREBASE_PROJECT" --non-interactive

echo "[run_job] done"
