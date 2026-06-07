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

# AIニュース全般を対象とする。大別して
#   1) モデルプロバイダ／開発元（一次情報）
#   2) AI専門・テック系メディア（資金調達・企業動向・規制・業界ニュース）
#   3) 研究・開発者向け（論文・実践知）
# 追加候補は事前に取得可否（HTTP 200 + RSS実体あり）を検証済み。
# 公開RSSが無い／HTMLしか返さないソース（Anthropic, Meta AI, Mistral,
# Cohere, Stability AI 等）は現時点では含めていない。
RSS_SOURCES = [
    # --- モデルプロバイダ／開発元（一次情報） ---
    {
        "name": "OpenAI",
        "url": "https://openai.com/news/rss.xml",
    },
    {
        "name": "Google DeepMind",
        "url": "https://deepmind.google/blog/rss.xml",
    },
    {
        "name": "Google AI",
        "url": "https://blog.google/technology/ai/rss/",
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
    {
        "name": "AWS Machine Learning Blog",
        "url": "https://aws.amazon.com/blogs/machine-learning/feed/",
    },
    {
        "name": "NVIDIA Blog",
        "url": "https://blogs.nvidia.com/feed/",
    },
    {
        "name": "NVIDIA Developer Blog",
        "url": "https://developer.nvidia.com/blog/feed",
    },
    # --- 研究機関・大学・研究ブログ ---
    {
        "name": "Google Research",
        "url": "https://research.google/blog/rss/",
    },
    {
        "name": "Microsoft Research",
        "url": "https://www.microsoft.com/en-us/research/feed/",
    },
    {
        "name": "MIT News AI",
        "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",
    },
    {
        "name": "BAIR Blog",
        "url": "https://bair.berkeley.edu/blog/feed.xml",
    },
    # --- AI専門・テック系メディア（英語） ---
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    },
    {
        "name": "Ars Technica AI",
        "url": "https://arstechnica.com/ai/feed/",
    },
    {
        "name": "MIT Technology Review AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    },
    {
        "name": "WIRED AI",
        "url": "https://www.wired.com/feed/tag/ai/latest/rss",
    },
    {
        "name": "The Decoder",
        "url": "https://the-decoder.com/feed/",
    },
    # --- 国内：政策・総合媒体 ---
    {
        "name": "デジタル庁",
        "url": "https://www.digital.go.jp/rss/news.xml",
    },
    {
        "name": "ITmedia AI＋",
        "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
    },
    {
        "name": "＠IT Smart & Social",
        "url": "https://rss.itmedia.co.jp/rss/2.0/ait_smart.xml",
    },
    {
        "name": "Publickey",
        "url": "https://www.publickey1.jp/atom.xml",
    },
    # --- 国内：企業技術ブログ（実装知見） ---
    {
        "name": "LINEヤフー Tech Blog",
        "url": "https://techblog.lycorp.co.jp/ja/feed/index.xml",
    },
    {
        "name": "Mercari Engineering",
        "url": "https://engineering.mercari.com/blog/feed.xml",
    },
    {
        "name": "Recruit Tech Blog",
        "url": "https://blog.recruit.co.jp/data/index.xml",
    },
    {
        "name": "BrainPad Blog",
        "url": "https://blog.brainpad.co.jp/rss",
    },
    {
        "name": "DeNA Engineering",
        "url": "https://engineering.dena.com/index.xml",
    },
    {
        "name": "NTT Communications Engineers' Blog",
        "url": "https://engineers.ntt.com/feed",
    },
    # --- 研究・開発者向け（個人） ---
    {
        "name": "Simon Willison's Weblog",
        "url": "https://simonwillison.net/atom/everything/",
    },
]

MODELS_JSON_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))
# ソース数増加に伴い、1回の実行で各ソースの最新まで処理が回るよう上限を引き上げ。
# 新着はソースごとにラウンドロビンで並べる（後述）が、デジタル庁や企業技術ブログ等の
# 一般ソースは非AI記事も混ざり、それらも分析前に上限へ計上され破棄される。
# 上限はその破棄分も見込んだ値。Gemini Flash の1日1回実行なら現実的なコスト。
MAX_NEW_ARTICLES = 40
MAX_TOTAL_ARTICLES = 500

SYSTEM_PROMPT = """あなたはAI開発者・ウォッチャー向けのAIニュースアナリストです。
以下の記事が、AIニュースとして掲載に値するかを判定してください。

対象にするもの（AIニュース全般）:
- 新モデル発表・アップデート・性能改善・価格/コンテキスト長変更・API提供開始/終了
- マルチモーダル・推論・コーディング・オープンウェイトなどモデル系の話題
- AIエージェント／開発ツール／フレームワーク／RAG など開発者向けリリース
- 注目すべき研究・論文・ベンチマーク
- 資金調達・買収・企業動向・人事などの業界ニュース
- AIに関する規制・政策・ガバナンス
- AIのセキュリティ・安全性に関する重要な話題

対象外（掲載しない）:
- AIと実質的に無関係な一般ニュース
- 内容の薄い広告・宣伝・イベント告知のみの記事

種別 (model_type) は以下のみ使用（1つ選択）。特定モデルの話題でなければ Other:
Frontier, Reasoning, Coding, Multimodal, Open, Small, Embedding, Audio, Video, Other

重要度の基準:
A: AI開発者の意思決定（モデル選定・API利用・コスト・採用技術・重要な業界/規制動向）に直接影響する重要ニュース
B: 今すぐ対応不要だが、ウォッチ価値のあるAIニュース
C: AI関連だが低優先度

出力はJSONのみ。説明文は一切不要。必ず以下のJSON形式のみで回答すること:

{
  "is_model_related": true,
  "model_relevance_reason": "AIニュースとして掲載すべき理由を簡潔に",
  "model_name": "GPT-5.1",
  "provider": "OpenAI",
  "model_type": "Frontier",
  "summary": "日本語で3行以内の要約",
  "impact": "AI開発・利用への影響",
  "action": "推奨アクション",
  "importance": "A",
  "tags": ["Frontier", "API"]
}

注: 互換性のため掲載可否のフラグは "is_model_related" という名前のままにしている。
AIニュースとして掲載すべきなら true、対象外なら false を返すこと。
特定モデルの話題でない場合は model_name を "Unknown"、model_type を "Other" とし、
provider には関係する企業・組織名（不明なら空文字列）を入れる。
tags は内容に応じて自由に付与（例: Funding, Regulation, Agent, RAG, Research, Security など）。
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

    # ソースごとに新着を集め、ラウンドロビンで均等に取り込む。
    # 単純連結だと先頭ソースだけで MAX_NEW_ARTICLES に達し、後段ソースが
    # 取り込まれにくくなるため（ソース数が多いほど顕著）。
    per_source_new: list[list[dict]] = []
    for source in RSS_SOURCES:
        fetched = fetch_source(source)
        per_source_new.append([a for a in fetched if a["url"] not in seen_urls])

    new_articles: list[dict] = []
    for i in range(max((len(s) for s in per_source_new), default=0)):
        for src_articles in per_source_new:
            if i < len(src_articles):
                new_articles.append(src_articles[i])

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
