"""GCS sync helper. GCSバケットをデータ/フィード/AI画像の配信元にする構成のI/Oを担う。

画面（HTML/assets）は Firebase Hosting が配信し、GCS はデータのみを保持する。
ニュース更新パイプライン:
  download → collect/generate → upload(状態=配信データ) → publish-feeds → [Firebase deploy は firebase_hosting_deploy.py]

状態 models.json の正本は `gs://<bucket>/<GCS_OBJECT>`（既定 data/models.json）であり、
これがそのまま公開配信される（中身に機密は無い）。publish-pages は手動バックアップ用に残す。
保持上限で配信対象から外れた記事のハッシュは、同じキーに .archive.json を付けて保存する。

環境変数:
- GCS_BUCKET       配信／状態バケット名（必須）
- GCS_OBJECT       状態=配信データのオブジェクトキー（既定: data/models.json）
- MODELS_JSON_PATH ローカルの読み書き先（collect.py / generate_feeds.py と共有）
- FEEDS_DIR        生成済みフィードのローカルディレクトリ（既定: docs/feeds）
- PAGES_DIR        生成済みサイト(index/articles/assets)のローカルディレクトリ（publish-pages 用、既定: docs）
- SITE_DIR         サイト静的ファイルのローカルディレクトリ（publish-site 用、既定: docs）
"""

import hashlib
import json
import logging
import mimetypes
import os
import sys
import tempfile
from pathlib import Path

from google.cloud import storage

try:  # ローカル実行時は .env を読み込む（本番はジョブの環境変数を使うため no-op）
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

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
PAGES_DIR = Path(os.environ.get("PAGES_DIR", "docs"))
SITE_DIR = Path(os.environ.get("SITE_DIR", "docs"))

# publish-site で配信するサイト静的ファイル（SITE_DIR 直下からの相対パス）
SITE_FILES = ["index.html", "subscribe.html", "power-automate.html"]

# 配信物の Content-Type を拡張子から補強する（GCS のレンジ配信/CDN 向け）
_CONTENT_TYPES = {
    ".xml": "application/rss+xml; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
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


def _upload_file(local: Path, object_key: str, generation: int | None = None) -> int:
    blob = _bucket().blob(object_key)
    blob.cache_control = _CACHE_CONTROL
    blob.upload_from_filename(
        str(local), content_type=_content_type(local), if_generation_match=generation
    )
    logger.info(f"Uploaded {local} -> gs://{BUCKET}/{object_key}")
    return blob.generation


def _upload_dir(local_root: Path, key_prefix: str) -> int:
    """local_root 配下のファイルを再帰的にアップロードする。
    オブジェクトキー = key_prefix + (local_root からの相対パス)。"""
    count = 0
    for path in sorted(local_root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(local_root).as_posix()
            _upload_file(path, f"{key_prefix}{rel}")
            count += 1
    return count


def _generation_path() -> Path:
    # download と upload は別プロセス。Firebase に配信されない一時領域で世代を引き継ぐ。
    target = json.dumps([BUCKET, OBJECT, str(LOCAL_PATH.resolve())]).encode()
    name = "llm-watch-generations-" + hashlib.sha256(target).hexdigest()
    return Path(tempfile.gettempdir()) / name


def _archive_path() -> Path:
    return LOCAL_PATH.with_name(LOCAL_PATH.name + ".archive.json")


def download() -> None:
    """公開記事と保持上限を超えた記事の履歴を取得する。"""
    receipt = _generation_path()
    receipt.unlink(missing_ok=True)
    bucket = _bucket()
    generations = {}
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=LOCAL_PATH.parent) as staging:
        for key, local in ((OBJECT, LOCAL_PATH), (OBJECT + ".archive.json", _archive_path())):
            staged = Path(staging, local.name)
            blob = bucket.get_blob(key)
            if blob is None:
                generations[key] = 0
                # 初回は既存のローカルデータからの初期化も許容する。
                # 既存バケットに履歴だけ無い移行時は空の履歴から開始する。
                if generations[OBJECT] or not local.exists():
                    staged.write_text("[]", encoding="utf-8")
            else:
                generations[key] = blob.generation
                blob.download_to_filename(str(staged), if_generation_match=blob.generation)
                logger.info(f"Downloaded gs://{BUCKET}/{key}")
        for staged in Path(staging).iterdir():
            staged.replace(LOCAL_PATH.parent / staged.name)
    receipt.write_text(json.dumps(generations), encoding="utf-8")


def upload() -> None:
    """再掲載を防ぐ履歴を先に確定してから、公開記事を書き戻す。"""
    if not LOCAL_PATH.exists():
        logger.error(f"{LOCAL_PATH} does not exist — nothing to upload")
        sys.exit(1)
    receipt = _generation_path()
    archive_key = OBJECT + ".archive.json"
    archive_path = _archive_path()
    # ダウンロードしていないローカルデータは、新規バケットの初期化に限り許容する。
    generations = {OBJECT: 0, archive_key: 0}
    if receipt.exists():
        generations = json.loads(receipt.read_text(encoding="utf-8"))
    elif _bucket().get_blob(OBJECT) is not None:
        raise RuntimeError("Download the current GCS state before uploading changes")
    if archive_path.exists():
        generations[archive_key] = _upload_file(archive_path, archive_key, generations[archive_key])
        receipt.write_text(json.dumps(generations), encoding="utf-8")
    elif generations[archive_key]:
        raise FileNotFoundError(archive_path)
    generations[OBJECT] = _upload_file(LOCAL_PATH, OBJECT, generations[OBJECT])
    receipt.write_text(json.dumps(generations), encoding="utf-8")


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


def publish_pages() -> None:
    """生成済みサイト(index/subscribe/articles/assets)を GCS バケット直下へ配信する。

    data/ と feeds/ は別コマンド(upload / publish-feeds)が担当するため、ここでは触らない。
    記事ページは feeds と同じ“バッチ生成物”であり、サイトの「デプロイ」ではない。
    """
    index = PAGES_DIR / "index.html"
    if not index.exists():
        logger.error(f"{index} does not exist — run generate_pages.py first")
        sys.exit(1)

    published = 0
    for name in SITE_FILES:
        local = PAGES_DIR / name
        if local.exists():
            _upload_file(local, name)
            published += 1
    for subdir in ("articles", "assets"):
        local_dir = PAGES_DIR / subdir
        if local_dir.is_dir():
            published += _upload_dir(local_dir, f"{subdir}/")
    logger.info(f"Published {published} page file(s) to gs://{BUCKET}/")


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
    "publish-pages": publish_pages,
    "publish-site": publish_site,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        logger.error(f"usage: gcs_sync.py [{'|'.join(COMMANDS)}]")
        sys.exit(2)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
