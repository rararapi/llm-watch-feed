#!/usr/bin/env bash
#
# ローカルでUIを確認する（デプロイ不要）。
#
# アセット/内部リンクは SITE_URL 基準の絶対URLで出力されるため、ローカル確認では
# SITE_URL をこのローカルサーバへ向けて生成し直してから docs/ を配信する。
# OGP/canonical も localhost を指すが、見た目の確認には問題ない
# （実際のSNS unfurl 検証だけは公開URL=GCS publish後に対して行う）。
#
# 使い方:
#   ./scripts/preview.sh            # http://localhost:8000
#   ./scripts/preview.sh 8011       # ポート指定
set -euo pipefail

PORT="${1:-8000}"
export SITE_URL="http://localhost:${PORT}"
export PAGES_DIR="docs"
export MODELS_JSON_PATH="${MODELS_JSON_PATH:-docs/data/models.json}"

# データが無ければ公開バケット（読み取り公開）から取得して確認できるようにする
if [ ! -f "$MODELS_JSON_PATH" ]; then
  echo "[preview] $MODELS_JSON_PATH が無いので公開バケットから取得します"
  mkdir -p "$(dirname "$MODELS_JSON_PATH")"
  curl -fsS "https://storage.googleapis.com/ai-watch-feed-llm-watch-public/data/models.json" \
    -o "$MODELS_JSON_PATH"
fi

echo "[preview] サイト生成 (SITE_URL=$SITE_URL)"
python scripts/generate_pages.py

echo "[preview] http://localhost:${PORT}/ で配信中（停止は Ctrl+C）"
cd docs && exec python -m http.server "$PORT"
