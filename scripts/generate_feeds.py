"""Generate RSS feeds from docs/data/models.json."""

import json
import logging
import os
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_URL = os.environ.get(
    "SITE_URL", "https://your-username.github.io/llm-watch-feed"
).rstrip("/")
MODELS_JSON_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))
FEEDS_DIR = Path(os.environ.get("FEEDS_DIR", "docs/feeds"))
MAX_ITEMS_PER_FEED = 50

FEED_CONFIGS: dict[str, dict] = {
    "all.xml": {
        "title": "LLM Watch Feed - All",
        "description": "重要度AまたはBのLLMモデル情報",
        "filter": lambda a: a.get("importance") in ("A", "B"),
    },
    "major-models.xml": {
        "title": "LLM Watch Feed - Major Models",
        "description": "重要度Aの主要LLMモデル情報",
        "filter": lambda a: a.get("importance") == "A",
    },
    "pricing.xml": {
        "title": "LLM Watch Feed - Pricing",
        "description": "価格・コスト関連のLLMモデル情報",
        "filter": lambda a: any(t in a.get("tags", []) for t in ("Pricing", "Cost")),
    },
    "open-models.xml": {
        "title": "LLM Watch Feed - Open Models",
        "description": "オープンウェイトモデルの情報",
        "filter": lambda a: a.get("model_type") == "Open",
    },
    "coding.xml": {
        "title": "LLM Watch Feed - Coding",
        "description": "コーディング性能に特化したLLMモデル情報",
        "filter": lambda a: a.get("model_type") == "Coding"
        or "Coding" in a.get("tags", []),
    },
    "multimodal.xml": {
        "title": "LLM Watch Feed - Multimodal",
        "description": "マルチモーダル・音声・動画モデルの情報",
        "filter": lambda a: a.get("model_type") in ("Multimodal", "Audio", "Video")
        or "Multimodal" in a.get("tags", []),
    },
}


def to_rfc822(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt)
    except Exception:
        return format_datetime(datetime.now(timezone.utc))


def build_item_title(a: dict) -> str:
    importance = a.get("importance", "?")
    model_type = a.get("model_type", "Other")
    model_name = a.get("model_name", "Unknown")
    title = a.get("title", "")
    return f"[重要度{importance}][{model_type}] {model_name} - {title}"


def build_description(a: dict) -> str:
    rows = [
        ("モデル名", a.get("model_name", "Unknown")),
        ("提供元", a.get("provider", "")),
        ("モデル種別", a.get("model_type", "")),
        ("要約", a.get("summary", "")),
        ("影響", a.get("impact", "")),
        ("推奨アクション", a.get("action", "")),
        ("ソース", a.get("source", "")),
        ("重要度", a.get("importance", "")),
    ]
    parts = [f"<strong>{label}:</strong> {escape(str(value))}" for label, value in rows]
    return "<br/>".join(parts)


def generate_feed(filename: str, config: dict, articles: list[dict]) -> None:
    items = sorted(
        [a for a in articles if config["filter"](a)],
        key=lambda a: a.get("published_at", ""),
        reverse=True,
    )[:MAX_ITEMS_PER_FEED]

    feed_url = f"{BASE_URL}/feeds/{filename}"
    now = format_datetime(datetime.now(timezone.utc))

    item_blocks = []
    for a in items:
        item_blocks.append(
            f"""    <item>
      <title><![CDATA[{build_item_title(a)}]]></title>
      <link>{escape(a.get("url", ""))}</link>
      <guid isPermaLink="false">{escape(a.get("id", a.get("url", "")))}</guid>
      <pubDate>{to_rfc822(a.get("published_at", ""))}</pubDate>
      <description><![CDATA[{build_description(a)}]]></description>
    </item>"""
        )

    items_xml = "\n".join(item_blocks)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(config["title"])}</title>
    <link>{escape(BASE_URL)}</link>
    <description>{escape(config["description"])}</description>
    <language>ja</language>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="{escape(feed_url)}" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>
"""

    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    (FEEDS_DIR / filename).write_text(xml, encoding="utf-8")
    logger.info(f"  {filename}: {len(items)} items")


def main() -> None:
    if not MODELS_JSON_PATH.exists():
        logger.warning("models.json not found — generating empty feeds")
        articles: list[dict] = []
    else:
        with open(MODELS_JSON_PATH, encoding="utf-8") as f:
            articles = json.load(f)
    logger.info(f"Loaded {len(articles)} articles")

    for filename, config in FEED_CONFIGS.items():
        generate_feed(filename, config, articles)

    logger.info("Feed generation complete")


if __name__ == "__main__":
    main()
