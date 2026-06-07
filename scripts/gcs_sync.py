"""GCS sync helper for the Cloud Run Job (download/upload of models.json).

状態(models.json)の正本は GCS に置く。ジョブ起動時に download し、
collect/generate 後に upload する（download-run-upload 方式）。
本体スクリプト(collect.py / generate_feeds.py)はファイル I/O のまま無改造で動かす。

環境変数:
- GCS_BUCKET       保存先バケット名（必須）
- GCS_OBJECT       オブジェクトキー（既定: models.json）
- MODELS_JSON_PATH ローカルの読み書き先（collect.py / generate_feeds.py と共有）
"""

import logging
import os
import sys
from pathlib import Path

from google.cloud import storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BUCKET = os.environ.get("GCS_BUCKET")
OBJECT = os.environ.get("GCS_OBJECT", "models.json")
LOCAL_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))


def _blob():
    if not BUCKET:
        logger.error("GCS_BUCKET is not set")
        sys.exit(2)
    return storage.Client().bucket(BUCKET).blob(OBJECT)


def download() -> None:
    """GCS の状態をローカルへ取得する。

    オブジェクトが存在しない場合のみ「初回実行＝空から開始」を許容する。
    存在するのに取得に失敗した場合は例外を送出し、状態の取り違え（全件消失）を防ぐ。
    """
    blob = _blob()
    if not blob.exists():
        logger.warning(f"gs://{BUCKET}/{OBJECT} not found — first run, starting empty")
        return
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(LOCAL_PATH))
    logger.info(f"Downloaded gs://{BUCKET}/{OBJECT} -> {LOCAL_PATH}")


def upload() -> None:
    """更新後のローカル状態を GCS（正本）へ書き戻す。"""
    if not LOCAL_PATH.exists():
        logger.error(f"{LOCAL_PATH} does not exist — nothing to upload")
        sys.exit(1)
    blob = _blob()
    blob.upload_from_filename(str(LOCAL_PATH), content_type="application/json")
    logger.info(f"Uploaded {LOCAL_PATH} -> gs://{BUCKET}/{OBJECT}")


COMMANDS = {"download": download, "upload": upload}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        logger.error("usage: gcs_sync.py [download|upload]")
        sys.exit(2)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
