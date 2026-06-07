"""Collect LLM model news from RSS sources and analyze with Vertex AI (Gemini).

GCP_PROJECT が設定され ADC（Application Default Credentials）で認証できれば
Vertex AI で要約・分析し、利用できなければダミー文章を埋め込む（ダミーモード）。
認証情報が無くてもパイプライン全体が動くようにするため。

ローカルからも実行できる:
  gcloud auth application-default login   # 一度だけ
  export GCP_PROJECT=<your-project-id>    # .env でも可
  python scripts/collect.py
"""

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
import vertexai
from dotenv import load_dotenv
from vertexai.generative_models import GenerationConfig, GenerativeModel

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

MODELS_JSON_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))
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


DUMMY_NOTICE = "（Vertex AI未設定のため自動生成されたダミー文章です）"


def dummy_analysis(article: dict) -> dict:
    """Vertex AI を利用できないときに埋め込むダミー分析結果。

    要約はLLMを使わないため、記事の概要(excerpt)またはタイトルを流用しつつ、
    ダミーである旨を明示する。全件を取り込めるよう is_model_related は True とする。
    """
    base = (article.get("excerpt") or article.get("title") or "").strip()
    summary = f"{DUMMY_NOTICE} {base[:120]}".strip()
    return {
        "is_model_related": True,
        "model_relevance_reason": DUMMY_NOTICE,
        "model_name": "Unknown",
        "provider": article.get("source", ""),
        "model_type": "Other",
        "summary": summary,
        "impact": DUMMY_NOTICE,
        "action": DUMMY_NOTICE,
        "importance": "B",
        "tags": ["dummy"],
    }


def _strip_json_fence(text: str) -> str:
    """まれに ```json ... ``` で包んで返ってくる場合に備えて中身だけ取り出す。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def analyze(model: GenerativeModel, article: dict) -> Optional[dict]:
    user_content = (
        f"タイトル: {article['title']}\n"
        f"ソース: {article['source']}\n"
        f"URL: {article['url']}\n"
        f"概要: {article['excerpt'] or '(なし)'}"
    )
    try:
        resp = model.generate_content(user_content)
        return json.loads(_strip_json_fence(resp.text))
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed for '{article['title']}': {e}")
        return None
    except Exception as e:
        logger.warning(f"LLM error for '{article['title']}': {e}")
        return None


def build_model(system_prompt: str = SYSTEM_PROMPT) -> Optional[GenerativeModel]:
    """Vertex AI モデルを ADC で初期化する。

    GCP_PROJECT 未設定や認証不可なら None を返し、呼び出し側でダミーモードへ
    フォールバックさせる（認証情報が無くてもパイプライン全体を完走させるため）。
    system_prompt を差し替えれば、収集以外の用途（要約の再生成など）でも再利用できる。
    """
    project = os.environ.get("GCP_PROJECT")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    model_name = os.environ.get("VERTEX_MODEL", "gemini-2.5-flash")

    if not project:
        logger.warning(
            "GCP_PROJECT is not set. Running in DUMMY mode (placeholder summaries)."
        )
        return None
    try:
        vertexai.init(project=project, location=location)
        model = GenerativeModel(
            model_name,
            system_instruction=system_prompt,
            generation_config=GenerationConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        logger.info(f"Using Vertex AI model: {model_name} ({project}/{location})")
        return model
    except Exception as e:
        logger.warning(f"Vertex AI init failed ({e}). Falling back to DUMMY mode.")
        return None


def main() -> None:
    model = build_model()
    use_llm = model is not None

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
        result = analyze(model, article) if use_llm else dummy_analysis(article)
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
    mode = "LLM" if use_llm else "DUMMY"
    logger.info(f"Done ({mode} mode). Added: {added}, Total: {len(existing)}")


if __name__ == "__main__":
    main()
