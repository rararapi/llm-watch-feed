#!/usr/bin/env bash
#
# サイトデプロイ（ニュース更新とは分離）— 方式A
#
# サイトの画面（index.html などの静的ファイル）を Firebase Hosting へデプロイする。
# 独自ドメイン/HTTPS を無料で付けられる Firebase Hosting が「画面」だけを配信し、
# データ（data/models.json）とRSSフィード（feeds/*.xml）は公開GCSバケットが配信する。
#
# テンプレート/CSS/JS を変更したときだけ実行すればよい。デプロイ前に generate_pages.py で
# 画面(index/subscribe/assets)を docs/ に再生成し、最新テンプレートと一致させる。
# 毎日のニュース更新（run_job.sh）はGCSへの書き込みのみで、ここには触れない。
# 記事ページ(articles/*.html)はGCSが日次配信するため、Firebaseへは載せない。
#
# 任意環境変数:
#   FIREBASE_PROJECT  デプロイ先プロジェクトID（既定は .firebaserc の default）
#   GCS_BUCKET        セットすると最新の models.json をGCSから取得してから生成する
#
# 前提: firebase CLI が認証済みであること（firebase login 済み、または CI トークン）。
#
# 使い方:
#   ./scripts/deploy_site.sh
set -euo pipefail

PROJECT_ARGS=()
if [ -n "${FIREBASE_PROJECT:-}" ]; then
  PROJECT_ARGS=(--project "$FIREBASE_PROJECT")
fi

# firebase.json の hosting public は docs/。画面を docs/ に再生成してからデプロイする。
export PAGES_DIR="${PAGES_DIR:-docs}"
export MODELS_JSON_PATH="${MODELS_JSON_PATH:-docs/data/models.json}"

if [ -n "${GCS_BUCKET:-}" ]; then
  echo "[deploy_site] download latest models.json from GCS"
  python scripts/gcs_sync.py download || true
fi

echo "[deploy_site] generate pages into $PAGES_DIR"
python scripts/generate_pages.py

echo "[deploy_site] firebase deploy --only hosting"
firebase deploy --only hosting --non-interactive "${PROJECT_ARGS[@]}"

echo "[deploy_site] done"
