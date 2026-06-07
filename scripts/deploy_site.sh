#!/usr/bin/env bash
#
# サイトデプロイ（ニュース更新とは分離）
#
# index.html などのサイト静的ファイルを公開GCSバケットへ配信する。
# サイトの見た目・文言・JS を変更したときだけ実行すればよい。
# 毎日のニュース更新（run_job.sh）はデータとフィードのみ更新し、ここには触れない。
#
# 必須環境変数:
#   GCS_BUCKET   配信バケット名
# 任意:
#   SITE_DIR     サイト静的ファイルのディレクトリ（既定 docs）
#
# 使い方:
#   GCS_BUCKET=<bucket> ./scripts/deploy_site.sh
set -euo pipefail

if [ -z "${GCS_BUCKET:-}" ]; then
  echo "ERROR: GCS_BUCKET is not set" >&2
  exit 2
fi

export SITE_DIR="${SITE_DIR:-docs}"

echo "[deploy_site] publish site files from $SITE_DIR to gs://$GCS_BUCKET/"
python scripts/gcs_sync.py publish-site

echo "[deploy_site] done"
