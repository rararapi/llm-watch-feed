"""Collect LLM model news from RSS sources and analyze with OpenAI."""

import calendar
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RSS_SOURCES = [
    {
        "name": "OpenAI",
        "url": "https://openai.com/news/rss.xml",
    },
    {
        "name": "Google DeepMind",
        "url": "https://deepmind.google/blog/rss.xml",
    },
    {
        "name": "Google Developers Blog",
        "url": "https://developers.googleblog.com/feeds/posts/default/?alt=rss",
    },
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
    },
    {
        "name": "Microsoft AI Blog",
        "url": "https://blogs.microsoft.com/ai/feed/",
    },
]

MODELS_JSON_PATH = Path("docs/data/models.json")
MAX_NEW_ARTICLES = 10
MAX_TOTAL_ARTICLES = 500

SYSTEM_PROMPT = """あなたはAIアプリ開発者向けのLLMモデル情報アナリストです。
以下の記事が、LLMモデル情報として重要かを判定してください。

対象にするもの:
- 新モデル発表
- モデルアップデート
- モデル性能改善
- 価格変更
- コンテキスト長変更
- マルチモーダル対応
- コーディング性能
- 推論モデル
- オープンウェイトモデル
- API提供開始・終了

対象外:
- 一般的なAIニュース
- 企業導入事例
- 資金調達
- 法規制
- RAG実装（ただし主題が新モデルや性能なら対象にする）
- Agentフレームワーク（ただし主題が新モデルや性能なら対象にする）
- セキュリティ
- 論文全般

モデル種別は以下のみ使用（1つ選択）:
Frontier, Reasoning, Coding, Multimodal, Open, Small, Embedding, Audio, Video, Other

重要度の基準:
A: AIアプリのモデル選定・API利用・コスト・性能・PoC優先度に直接影響する重要なモデルアップデート
B: 今すぐ対応不要だが、ウォッチまたは今後のPoC候補として有用なモデル情報
C: モデル関連ではあるが、低優先度

出力はJSONのみ。説明文は一切不要。必ず以下のJSON形式のみで回答すること:

{
  "is_model_related": true,
  "model_relevance_reason": "新しいフロンティアモデルの発表であるため",
  "model_name": "GPT-5.1",
  "provider": "OpenAI",
  "model_type": "Frontier",
  "summary": "日本語で3行以内の要約",
  "impact": "AIアプリ開発への影響",
  "action": "推奨アクション",
  "importance": "A",
  "tags": ["Frontier", "API"]
}

model_nameが不明な場合は "Unknown" を使用。
is_model_related が false の場合、他フィールドは空文字列と空配列でよい。"""


def url_to_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def load_existing() -> list[dict]:
    if MODELS_JSON_PATH.exists():
        with open(MODELS_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_articles(articles: list[dict]) -> None:
    MODELS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODELS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(articles)} articles to {MODELS_JSON_PATH}")


def get_published_at(entry) -> str:
    if getattr(entry, "published_parsed", None):
        try:
            ts = calendar.timegm(entry.published_parsed)
            return datetime.utcfromtimestamp(ts).replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    raw = getattr(entry, "published", None)
    if raw:
        return raw
    return datetime.now(timezone.utc).isoformat()


def fetch_source(source: dict) -> list[dict]:
    name = source["name"]
    url = source["url"]
    try:
        logger.info(f"Fetching: {name}")
        resp = requests.get(
            url, timeout=30, headers={"User-Agent": "LLMWatchFeed/1.0 (+https://github.com)"}
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        articles = []
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue
            articles.append(
                {
                    "title": entry.get("title", ""),
                    "url": link,
                    "source": name,
                    "published_at": get_published_at(entry),
                    "excerpt": (entry.get("summary") or "")[:500],
                }
            )
        logger.info(f"  {name}: {len(articles)} entries")
        return articles
    except Exception as e:
        logger.warning(f"Failed to fetch {name}: {e}")
        return []


def analyze(client: OpenAI, model: str, article: dict) -> Optional[dict]:
    user_content = (
        f"タイトル: {article['title']}\n"
        f"ソース: {article['source']}\n"
        f"URL: {article['url']}\n"
        f"概要: {article['excerpt'] or '(なし)'}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed for '{article['title']}': {e}")
        return None
    except Exception as e:
        logger.warning(f"LLM error for '{article['title']}': {e}")
        return None


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not set")
        raise SystemExit(1)

    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    logger.info(f"Using model: {model}")

    client = OpenAI(api_key=api_key)
    existing = load_existing()
    seen_urls = {a["url"] for a in existing}
    logger.info(f"Existing articles: {len(existing)}")

    raw: list[dict] = []
    for source in RSS_SOURCES:
        raw.extend(fetch_source(source))

    new_articles = [a for a in raw if a["url"] not in seen_urls]
    logger.info(
        f"New articles: {len(new_articles)} (processing up to {MAX_NEW_ARTICLES})"
    )
    new_articles = new_articles[:MAX_NEW_ARTICLES]

    added = 0
    for article in new_articles:
        logger.info(f"Analyzing: {article['title'][:70]}")
        result = analyze(client, model, article)
        if not result:
            logger.warning("  -> Skipped (analysis failed)")
            continue
        if not result.get("is_model_related"):
            logger.info(f"  -> Not model-related: {result.get('model_relevance_reason', '')}")
            continue

        record = {
            "id": url_to_id(article["url"]),
            "title": article["title"],
            "url": article["url"],
            "source": article["source"],
            "published_at": article["published_at"],
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "is_model_related": True,
            "model_relevance_reason": result.get("model_relevance_reason", ""),
            "model_name": result.get("model_name") or "Unknown",
            "provider": result.get("provider", ""),
            "model_type": result.get("model_type", "Other"),
            "summary": result.get("summary", ""),
            "impact": result.get("impact", ""),
            "action": result.get("action", ""),
            "importance": result.get("importance", "C"),
            "tags": result.get("tags") or [],
            "language": "ja",
        }
        existing.append(record)
        added += 1
        logger.info(
            f"  -> Added [{record['importance']}][{record['model_type']}] {record['model_name']}"
        )

    if len(existing) > MAX_TOTAL_ARTICLES:
        existing = existing[-MAX_TOTAL_ARTICLES:]
        logger.info(f"Trimmed to latest {MAX_TOTAL_ARTICLES} articles")

    save_articles(existing)
    logger.info(f"Done. Added: {added}, Total: {len(existing)}")


if __name__ == "__main__":
    main()
