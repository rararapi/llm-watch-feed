#!/usr/bin/env bash
#
# サイトデプロイ（ニュース更新とは分離）— 方式A
#
# サイトの画面（index.html などの静的ファイル）を Firebase Hosting へデプロイする。
# 独自ドメイン/HTTPS を無料で付けられる Firebase Hosting が「画面」だけを配信し、
# データ（data/models.json）とRSSフィード（feeds/*.xml）は公開GCSバケットが配信する。
#
# サイトの見た目・文言・JS を変更したときだけ実行すればよい。
# 毎日のニュース更新（run_job.sh）はGCSへの書き込みのみで、ここには触れない。
#
# 任意環境変数:
#   FIREBASE_PROJECT  デプロイ先プロジェクトID（既定は .firebaserc の default）
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

echo "[deploy_site] firebase deploy --only hosting"
firebase deploy --only hosting --non-interactive "${PROJECT_ARGS[@]}"

echo "[deploy_site] done"
