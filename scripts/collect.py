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
import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import feedparser
import requests
import vertexai
from dotenv import load_dotenv
from vertexai.generative_models import GenerationConfig, GenerativeModel

from article_identity import article_key, new_candidates, unique_articles, url_to_id
from story_dedup import STORY_PROMPT, group_stories

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
A: AI開発者が「今週中に対応・検討が必要」と判断するレベルの重要ニュース。
   具体的には: 新モデルのAPIリリース・廃止、コスト/性能/コンテキスト長の変更、重要な規制・セキュリティ動向。
   研究ブログ・企業技術ブログ・業界動向・将来予測はソース元が大手でもAにしない。
B: 知っておくべきだが今すぐ行動変容は不要なAIニュース（論文・企業事例・業界トレンド・開発者向け実装知見等）。
C: AI関連だが開発者の意思決定にほぼ影響しない低優先度コンテンツ（将来予測・市場規模レポート等）。

以下は判定例（入力と期待する出力JSON）:

---例1 (A: 新モデルのAPIリリース)---
入力:
タイトル: OpenAI、GPT-5を正式リリース — コンテキスト長1Mトークン、APIは$15/1Mトークンから
ソース: OpenAI
URL: https://openai.com/news/gpt-5
概要: OpenAIは次世代フロンティアモデルGPT-5を本日より一般提供開始。GPT-4oと比較してコーディング・推論が大幅向上。既存APIは移行期間3ヶ月で廃止予定。
出力: {"is_model_related": true, "model_relevance_reason": "主要フロンティアモデルの正式リリースでAPI移行を即時検討すべき", "model_name": "GPT-5", "provider": "OpenAI", "model_type": "Frontier", "summary": "OpenAIがGPT-5を正式リリース。コンテキスト1Mトークン、APIは$15/1Mトークンから。既存GPT-4o APIは3ヶ月後廃止予定。", "impact": "現行APIの移行タイムラインを確認し、GPT-5のコスト・性能評価が必要。", "action": "API移行計画を今週中に立案。コスト試算を実施。", "importance": "A", "tags": ["Frontier", "API", "Pricing", "Migration"]}

---例2 (A: 価格変更)---
入力:
タイトル: Anthropic、Claude 3.7 Sonnetの入力コストを50%値下げ — 200Kコンテキストも全プランで無料に
ソース: TechCrunch AI
URL: https://techcrunch.com/2026/03/01/anthropic-claude-price-cut
概要: AnthropicはClaude 3.7 SonnetのAPI価格をMTokあたり$3→$1.5に引き下げ。200Kコンテキストウィンドウは全ティアで追加料金なしに。
出力: {"is_model_related": true, "model_relevance_reason": "API価格の大幅値下げはコスト計画に直接影響", "model_name": "Claude 3.7 Sonnet", "provider": "Anthropic", "model_type": "Frontier", "summary": "Claude 3.7 SonnetのAPI入力コストが50%値下げ（MTokあたり$3→$1.5）。200Kコンテキストも全プランで無料化。", "impact": "Claude利用コストが半減。長文処理ユースケースの再評価機会。", "action": "現行コスト試算を更新。Claude採用検討中のプロジェクトを再評価。", "importance": "A", "tags": ["Frontier", "Pricing", "API"]}

---例3 (A: 重要な規制動向)---
入力:
タイトル: EU AI Act、高リスクAIシステムへの適合義務が8月1日より発効 — 違反には売上高6%の制裁金
ソース: The Verge AI
URL: https://www.theverge.com/2026/07/01/eu-ai-act-enforcement
概要: EU AI法の高リスクAI義務規定が発効。AIを用いた採用・信用スコアリング・重要インフラ制御は適合文書の提出が必須。
出力: {"is_model_related": false, "model_relevance_reason": "EU AI法の施行はAIシステム開発者の法的義務に直接関わる規制動向", "model_name": "Unknown", "provider": "", "model_type": "Other", "summary": "EU AI法の高リスクAI義務が8月1日発効。採用・信用スコアリング・重要インフラ用途は適合文書が必須。違反は売上高6%制裁。", "impact": "EU圏またはEU向けサービスで高リスク分類のAI利用は即時対応が必要。", "action": "自社AIユースケースのリスク分類を確認。法務・コンプライアンス部門と連携。", "importance": "A", "tags": ["Regulation", "EU AI Act", "Compliance"]}

---例4 (B: 研究ブログ・論文 — Google発でもB)---
入力:
タイトル: Google Research、Transformerの注意機構を改善する新手法「SparseAttention v2」を発表
ソース: Google Research
URL: https://research.google/blog/sparse-attention-v2
概要: Transformerの注意計算コストをO(n^2)からO(n log n)に削減する新アーキテクチャを提案。ベンチマークでは既存手法より15%高速化を達成。
出力: {"is_model_related": false, "model_relevance_reason": "研究段階の効率化手法でウォッチ価値はあるが即時対応不要", "model_name": "Unknown", "provider": "Google", "model_type": "Other", "summary": "GoogleがTransformerの注意機構を改善するSparseAttention v2を発表。計算量をO(n log n)に削減し15%高速化。", "impact": "将来のモデル効率改善につながる可能性があるが、実用化・製品化はまだ先。", "action": "論文をウォッチリストに追加。製品化の動向を継続観察。", "importance": "B", "tags": ["Research", "Architecture", "Efficiency"]}

---例5 (B: 開発者向けツールのアップデート)---
入力:
タイトル: LangChain v0.3リリース — マルチエージェント対応とメモリ管理が大幅改善
ソース: The Decoder
URL: https://the-decoder.com/langchain-v0-3
概要: LangChainのメジャーアップデート。複数エージェント間での状態共有API、長期メモリの永続化が標準搭載。Python 3.12以降が必須。
出力: {"is_model_related": false, "model_relevance_reason": "主要AIフレームワークのメジャーアップデートはウォッチ価値あり", "model_name": "Unknown", "provider": "LangChain", "model_type": "Other", "summary": "LangChain v0.3がリリース。マルチエージェントの状態共有と長期メモリ永続化が標準搭載。Python 3.12以降が必須。", "impact": "LangChain採用プロジェクトは依存関係・互換性の確認が必要。新機能でエージェント構築が効率化。", "action": "次のスプリントでアップグレード検討。マイグレーションガイドを確認。", "importance": "B", "tags": ["Agent", "Framework", "LangChain"]}

---例6 (B: 企業技術ブログ・実装事例)---
入力:
タイトル: LINEヤフー、社内問い合わせ対応にRAGシステムを導入した事例と知見
ソース: LINEヤフー Tech Blog
URL: https://techblog.lycorp.co.jp/ja/rag-internal-helpdesk
概要: 社内ヘルプデスクにRAGを導入した際のチャンク戦略、再ランキング手法、評価指標の選定について詳述。
出力: {"is_model_related": false, "model_relevance_reason": "RAG実装の実践的知見はウォッチ価値あり", "model_name": "Unknown", "provider": "LINEヤフー", "model_type": "Other", "summary": "LINEヤフーが社内問い合わせ対応RAGの構築知見を公開。チャンク戦略・再ランキング・評価指標を詳述。", "impact": "RAG構築の実践参考になるが、自社システムへの即時変更は不要。", "action": "次のRAG改善フェーズで参照。ブログをブックマーク。", "importance": "B", "tags": ["RAG", "Enterprise", "Implementation"]}

---例7 (B: OpenAI発の研究解説 — 一次情報ソースでも新モデル・API変更でなければB)---
入力:
タイトル: OpenAI、大規模言語モデルにおける幻覚の発生メカニズムを解説するブログを公開
ソース: OpenAI
URL: https://openai.com/research/hallucination-mechanisms
概要: GPT系モデルで幻覚が発生するトークン予測のメカニズムを内部研究として解説。特定の事実ドメインで誤りが多い原因を分析。
出力: {"is_model_related": false, "model_relevance_reason": "OpenAI発の研究解説だが新モデル・API変更を含まないためB判定", "model_name": "Unknown", "provider": "OpenAI", "model_type": "Other", "summary": "OpenAIが幻覚の発生メカニズムを解説するブログを公開。特定事実ドメインでの誤り発生パターンを分析。", "impact": "幻覚対策設計の参考になるが直接的なAPI変更ではない。", "action": "プロンプト設計・検証フローの参考として確認。", "importance": "B", "tags": ["Research", "Hallucination", "Safety"]}

---例8 (C: 将来予測・市場規模レポート)---
入力:
タイトル: 2030年のAI市場は1.8兆ドル規模に — 調査会社が予測レポートを発表
ソース: VentureBeat AI
URL: https://venturebeat.com/ai/ai-market-2030-forecast
概要: 大手調査会社がAI関連市場の成長予測を発表。生成AI分野が最大の成長セグメントとなる見込み。
出力: {"is_model_related": false, "model_relevance_reason": "将来予測レポートは参考情報でAI開発者の意思決定に直接影響しない", "model_name": "Unknown", "provider": "", "model_type": "Other", "summary": "調査会社が2030年のAI市場を1.8兆ドルと予測。生成AIが最大成長セグメント。", "impact": "業界規模感の把握に有用だが技術・製品選定への直接影響はない。", "action": "参考情報として記録のみ。", "importance": "C", "tags": ["Market", "Forecast"]}

---例9 (掲載対象外: AI無関係)---
入力:
タイトル: リクルート、新卒採用の応募締め切りを3月末に変更
ソース: Recruit Tech Blog
URL: https://blog.recruit.co.jp/data/2026-recruitment-schedule
概要: リクルートグループの2027年度新卒採用について、エントリー締め切りを従来より2ヶ月早める方針を発表。
出力: {"is_model_related": false, "model_relevance_reason": "AI・LLM開発と無関係な採用情報", "model_name": "", "provider": "", "model_type": "", "summary": "", "impact": "", "action": "", "importance": "", "tags": []}

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


def load_existing() -> list[dict]:
    if MODELS_JSON_PATH.exists():
        with open(MODELS_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_articles(articles: list[dict]) -> None:
    MODELS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODELS_JSON_PATH.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    temporary.replace(MODELS_JSON_PATH)
    logger.info(f"Saved {len(articles)} articles to {MODELS_JSON_PATH}")


def report_keys(articles: list[dict]) -> set[str]:
    return {
        article_key(report["url"])
        for article in articles
        for report in [article, *article.get("other_reports", [])]
    }


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


# 記事ページから og:image / twitter:image を抜くための軽量パーサ（BeautifulSoup等は増やさない）
_META_IMAGE_RE = re.compile(
    r"<meta[^>]+(?:property|name)\s*=\s*[\"'](?:og:image(?::url)?|twitter:image(?::src)?)[\"'][^>]*>",
    re.I,
)
_CONTENT_RE = re.compile(r"content\s*=\s*[\"']([^\"']+)[\"']", re.I)


def fetch_og_image(page_url: str, timeout: int = 15) -> Optional[str]:
    """記事ページの og:image（無ければ twitter:image）を取得して絶対URLで返す。

    画像はソース元のCDNをそのまま参照する（再ホストしない）。取得失敗は致命的でないため
    None を返し、サムネは画面側でプレースホルダにフォールバックさせる。
    """
    try:
        resp = requests.get(
            page_url,
            timeout=timeout,
            headers={"User-Agent": "LLMWatchFeed/1.0 (+https://github.com)"},
        )
        resp.raise_for_status()
        # メタタグは <head> 上部にあるため全文の先頭側だけ見れば十分
        page_html = resp.text[:200_000]
        for tag in _META_IMAGE_RE.finditer(page_html):
            m = _CONTENT_RE.search(tag.group(0))
            if m and m.group(1).strip():
                # 取得元HTMLで &amp; 等にエンコードされた content をデコードして素のURLに戻す
                return urljoin(page_url, html.unescape(m.group(1).strip()))
    except Exception as e:
        logger.warning(f"og:image fetch failed for {page_url}: {e}")
    return None


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
    model_name = os.environ.get("VERTEX_MODEL", "gemini-3.1-flash-lite")

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

    existing = unique_articles(load_existing())
    existing_ids = {a["id"] for a in existing}
    archive_path = Path(str(MODELS_JSON_PATH) + ".archive.json")
    archived = set(json.loads(archive_path.read_text(encoding="utf-8"))) if archive_path.exists() else set()
    logger.info(f"Existing articles: {len(existing)}")

    # ソースごとに新着を集め、ラウンドロビンで均等に取り込む。
    # 単純連結だと先頭ソースだけで MAX_NEW_ARTICLES に達し、後段ソースが
    # 取り込まれにくくなるため（ソース数が多いほど顕著）。
    new_articles = new_candidates(
        [fetch_source(source) for source in RSS_SOURCES],
        archived | report_keys(existing),
        MAX_NEW_ARTICLES,
    )
    logger.info(f"New articles to analyze: {len(new_articles)}")

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
            "image_url": None,
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

    matcher = None
    if use_llm and any(not a.get("story_checked") for a in existing):
        matcher = build_model(STORY_PROMPT)
    existing = group_stories(existing, matcher, existing_ids)
    if use_llm:
        # A failed comparison is retried from RSS just like a failed analysis.
        # Never retract already published items because the matcher was unavailable.
        before = len(existing)
        existing = [a for a in existing if a["id"] in existing_ids or a.get("story_checked")]
        if len(existing) < before:
            logger.warning("Deferred %d new article(s) pending story comparison", before - len(existing))

    if len(existing) > MAX_TOTAL_ARTICLES:
        archived.update(report_keys(existing[:-MAX_TOTAL_ARTICLES]))
        existing = existing[-MAX_TOTAL_ARTICLES:]
        logger.info(f"Trimmed to latest {MAX_TOTAL_ARTICLES} articles")

    # Persist evicted keys before replacing the public list. A retry after a
    # partial write still recognizes all URLs from the previous publication.
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(sorted(archived)), encoding="utf-8")
    temporary.replace(archive_path)

    added = 0
    for record in existing:
        if record["id"] not in existing_ids:
            record["image_url"] = fetch_og_image(record["url"])
            added += 1
    save_articles(existing)
    mode = "LLM" if use_llm else "DUMMY"
    logger.info(f"Done ({mode} mode). Added: {added}, Total: {len(existing)}")


if __name__ == "__main__":
    main()
