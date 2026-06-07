"""既存記事に image_url(og:image) を後付けするバックフィル。

collect.py は新着にしか image_url を付けないため、既存の models.json を一度だけ補完する用途。
1記事の取得失敗で全体が落ちないようにし、取得できなかった記事は image_url=None を明示する
（画面側はプレースホルダにフォールバックする）。

使い方（ローカル: docs/data/models.json を更新）:
  python scripts/backfill_images.py
本番データ（GCS）に反映する場合は download → backfill → upload:
  GCS_BUCKET=<bucket> python scripts/gcs_sync.py download
  GCS_BUCKET=<bucket> python scripts/backfill_images.py
  GCS_BUCKET=<bucket> python scripts/gcs_sync.py upload
"""

import logging

# collect.py の取得関数とI/Oを再利用（単一情報源）
from collect import fetch_og_image, load_existing, save_articles

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


def main() -> None:
    articles = load_existing()
    logger.info(f"Loaded {len(articles)} articles")

    updated = 0
    for a in articles:
        if a.get("image_url"):
            continue  # 既に画像あり
        img = fetch_og_image(a.get("url", ""))
        a["image_url"] = img  # 取れなければ None を明示
        if img:
            updated += 1
            logger.info(f"  + {a.get('source', '')}: {img[:80]}")

    save_articles(articles)
    logger.info(f"Backfill complete. image_url newly set: {updated}/{len(articles)}")


if __name__ == "__main__":
    main()
