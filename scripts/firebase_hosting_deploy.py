"""Deploy the generated static site to Firebase Hosting via REST API.

Cloud Run Job から Node.js / firebase-tools なしで Firebase Hosting へデプロイする。
google-cloud-storage が依存する google-auth を利用するため追加の pip 依存不要。

環境変数:
  FIREBASE_SITE_ID  Firebase Hosting サイト ID（既定: ai-watch-feed）
  FIREBASE_PROJECT  FIREBASE_SITE_ID の別名（後方互換）
  PAGES_DIR         デプロイするサイトのローカルディレクトリ（既定: docs）
"""

import gzip
import hashlib
import logging
import os
import sys
from pathlib import Path

import google.auth
import google.auth.transport.requests
import requests

try:
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

SITE_ID = os.environ.get("FIREBASE_SITE_ID") or os.environ.get("FIREBASE_PROJECT", "ai-watch-feed")
PAGES_DIR = Path(os.environ.get("PAGES_DIR", "docs"))
_API = "https://firebasehosting.googleapis.com/v1beta1"
_SCOPES = ["https://www.googleapis.com/auth/firebase"]


def _token() -> str:
    creds, _ = google.auth.default(scopes=_SCOPES)
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _json_headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _collect_files(pages_dir: Path) -> tuple[dict, dict]:
    """ファイルを gzip 圧縮して SHA-256 を算出する。

    Returns:
        files:   {server_path: sha256}  — populateFiles API に渡す
        content: {sha256: gzip_bytes}   — 実際のアップロード用
    """
    files: dict[str, str] = {}
    content: dict[str, bytes] = {}
    for local in sorted(pages_dir.rglob("*")):
        if not local.is_file():
            continue
        compressed = gzip.compress(local.read_bytes(), compresslevel=9)
        sha = hashlib.sha256(compressed).hexdigest()
        server_path = "/" + local.relative_to(pages_dir).as_posix()
        files[server_path] = sha
        content[sha] = compressed
    return files, content


def deploy(pages_dir: Path = PAGES_DIR, site_id: str = SITE_ID) -> None:
    if not pages_dir.is_dir():
        logger.error(f"{pages_dir} does not exist — run generate_pages.py first")
        sys.exit(1)

    files, content = _collect_files(pages_dir)
    logger.info(f"Deploying {len(files)} files from {pages_dir} to Firebase Hosting: {site_id}")

    # 1. バージョン作成
    version_resp = requests.post(
        f"{_API}/sites/{site_id}/versions",
        headers=_json_headers(),
        json={
            "config": {
                "headers": [
                    {
                        "glob": "**/*.html",
                        "headers": {"Cache-Control": "public, max-age=300"},
                    }
                ]
            }
        },
    )
    version_resp.raise_for_status()
    version_name = version_resp.json()["name"]
    logger.info(f"Created version: {version_name.split('/')[-1]}")

    # 2. ファイル一覧を送信（キャッシュ済みはスキップ、新規分の uploadUrl を受け取る）
    populate_resp = requests.post(
        f"{_API}/{version_name}:populateFiles",
        headers=_json_headers(),
        json={"files": files},
    )
    populate_resp.raise_for_status()
    populate = populate_resp.json()
    upload_url = populate.get("uploadUrl")
    required_hashes: set[str] = set(populate.get("uploadRequiredHashes", []))
    logger.info(f"{len(required_hashes)}/{len(files)} files need uploading (rest cached)")

    # 3. 新規ファイルのアップロード
    if required_hashes and upload_url:
        upload_token = _token()
        upload_headers = {
            "Authorization": f"Bearer {upload_token}",
            "Content-Type": "application/octet-stream",
        }
        for sha, data in content.items():
            if sha not in required_hashes:
                continue
            up = requests.post(f"{upload_url}/{sha}", headers=upload_headers, data=data)
            up.raise_for_status()
        logger.info(f"Uploaded {len(required_hashes)} file(s)")

    # 4. バージョンを確定（FINALIZED）
    finalize_resp = requests.patch(
        f"{_API}/{version_name}",
        headers=_json_headers(),
        params={"updateMask": "status"},
        json={"status": "FINALIZED"},
    )
    finalize_resp.raise_for_status()

    # 5. リリース（ライブに切り替え）
    release_resp = requests.post(
        f"{_API}/sites/{site_id}/releases",
        headers=_json_headers(),
        params={"versionName": version_name},
    )
    release_resp.raise_for_status()
    logger.info(f"Released to https://{site_id}.web.app")


if __name__ == "__main__":
    deploy()
