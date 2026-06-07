"""GCS sync helper. 公開GCSバケットを唯一の配信元にする構成のI/Oを担う。

バケットは Web 配信ルートを兼ねる（独自ドメインは後段の HTTPS ロードバランサ + Cloud CDN で付与）。
パイプラインは2系統に分離している:

- ニュース更新（毎日）: download → collect/generate → upload(状態=配信データ) → publish-feeds
- サイトデプロイ（変更時のみ）: publish-site

状態 models.json の正本は `gs://<bucket>/<GCS_OBJECT>`（既定 data/models.json）であり、
これがそのまま公開配信される（中身に機密は無い）。

環境変数:
- GCS_BUCKET       配信／状態バケット名（必須）
- GCS_OBJECT       状態=配信データのオブジェクトキー（既定: data/models.json）
- MODELS_JSON_PATH ローカルの読み書き先（collect.py / generate_feeds.py と共有）
- FEEDS_DIR        生成済みフィードのローカルディレクトリ（既定: docs/feeds）
- SITE_DIR         サイト静的ファイルのローカルディレクトリ（publish-site 用、既定: docs）
"""

import logging
import mimetypes
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
OBJECT = os.environ.get("GCS_OBJECT", "data/models.json")
LOCAL_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))
FEEDS_DIR = Path(os.environ.get("FEEDS_DIR", "docs/feeds"))
SITE_DIR = Path(os.environ.get("SITE_DIR", "docs"))

# publish-site で配信するサイト静的ファイル（SITE_DIR 直下からの相対パス）
SITE_FILES = ["index.html", "power-automate.html"]

# 配信物の Content-Type を拡張子から補強する（GCS のレンジ配信/CDN 向け）
_CONTENT_TYPES = {
    ".xml": "application/rss+xml; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}
# 毎回更新される配信物は短めにキャッシュし、ドメイン/CDN 追加後も更新が伝播するようにする
_CACHE_CONTROL = "public, max-age=300"


def _bucket():
    if not BUCKET:
        logger.error("GCS_BUCKET is not set")
        sys.exit(2)
    return storage.Client().bucket(BUCKET)


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower()) or (
        mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    )


def _upload_file(local: Path, object_key: str) -> None:
    blob = _bucket().blob(object_key)
    blob.cache_control = _CACHE_CONTROL
    blob.upload_from_filename(str(local), content_type=_content_type(local))
    logger.info(f"Uploaded {local} -> gs://{BUCKET}/{object_key}")


def download() -> None:
    """状態(models.json)をローカルへ取得する。

    オブジェクトが存在しない場合のみ「初回実行＝空から開始」を許容する。
    存在するのに取得に失敗した場合は例外を送出し、状態の取り違え（全件消失）を防ぐ。
    """
    blob = _bucket().blob(OBJECT)
    if not blob.exists():
        logger.warning(f"gs://{BUCKET}/{OBJECT} not found — first run, starting empty")
        return
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(LOCAL_PATH))
    logger.info(f"Downloaded gs://{BUCKET}/{OBJECT} -> {LOCAL_PATH}")


def upload() -> None:
    """更新後の状態(models.json)を GCS へ書き戻す。これがそのまま公開配信される。"""
    if not LOCAL_PATH.exists():
        logger.error(f"{LOCAL_PATH} does not exist — nothing to upload")
        sys.exit(1)
    _upload_file(LOCAL_PATH, OBJECT)


def publish_feeds() -> None:
    """生成済み RSS フィードを gs://<bucket>/feeds/ へ配信する。"""
    if not FEEDS_DIR.is_dir():
        logger.error(f"{FEEDS_DIR} does not exist — run generate_feeds.py first")
        sys.exit(1)
    count = 0
    for xml in sorted(FEEDS_DIR.glob("*.xml")):
        _upload_file(xml, f"feeds/{xml.name}")
        count += 1
    logger.info(f"Published {count} feed(s) to gs://{BUCKET}/feeds/")


def publish_site() -> None:
    """サイト静的ファイル(index.html 等)をバケット直下へ配信する（サイトデプロイ）。"""
    published = 0
    for name in SITE_FILES:
        local = SITE_DIR / name
        if not local.exists():
            logger.warning(f"{local} not found — skip")
            continue
        _upload_file(local, name)
        published += 1
    if published == 0:
        logger.error(f"no site files found under {SITE_DIR}")
        sys.exit(1)
    logger.info(f"Published {published} site file(s) to gs://{BUCKET}/")


COMMANDS = {
    "download": download,
    "upload": upload,
    "publish-feeds": publish_feeds,
    "publish-site": publish_site,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        logger.error(f"usage: gcs_sync.py [{'|'.join(COMMANDS)}]")
        sys.exit(2)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
