"""Generate the static site (index + per-article OGP pages + subscribe) from models.json.

トップ/購読ページに加え、SNS共有用の「OGPを焼き込んだ個別記事ページ」を事前生成する。
出力は PAGES_DIR 以下で、firebase_hosting_deploy.py が Firebase Hosting へ日次デプロイする。
公開URL は SITE_URL（https://ai-watch-feed.web.app）基準。
"""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

# 購読ページのフィード一覧は generate_feeds.py の FEED_CONFIGS を単一情報源にする
from generate_feeds import FEED_CONFIGS

try:  # ローカル実行時は .env を読み込む（本番はジョブの環境変数を使うため no-op）
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv 未導入でも標準ライブラリのみで動作させる
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# OGP/canonical/asset の絶対URL基準。Firebase Hosting の公開URL（SITE_URL）
SITE_URL = os.environ.get(
    "SITE_URL", "https://storage.googleapis.com/your-bucket"
).rstrip("/")
# フィードファイルの配信元URL（GCS）。SITE_URL（Firebase）とは別に保持する。
FEEDS_BASE_URL = os.environ.get("FEEDS_BASE_URL", SITE_URL).rstrip("/")
SITE_NAME = os.environ.get("SITE_NAME", "AI News Watch")
SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "AIニュースを自動収集・要約してお届け")

MODELS_JSON_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))
PAGES_DIR = Path(os.environ.get("PAGES_DIR", "docs"))
TEMPLATES_DIR = Path(os.environ.get("TEMPLATES_DIR", "templates"))
ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", "assets/site"))
STATIC_PAGES_DIR = Path(os.environ.get("STATIC_PAGES_DIR", "docs"))
STATIC_PAGE_FILES = ["power-automate.html"]

# Web(SSG)とモバイルアプリが同じ表示定数を参照するための共有メタ出力先。
# サイト生成物(PAGES_DIR)とは別のリポ内パスに置く（公開バケットへは載せない）。
SHARED_META_PATH = Path(os.environ.get("SHARED_META_PATH", "shared/meta.json"))

# 重要度ラベル/説明（AGENTS.md のテーブルが単一情報源。UIの絞り込み表示にも使う）
IMPORTANCE_META = {
    "A": {"label": "重要度A", "description": "モデル選定・API利用・コスト・性能・PoC優先度に直接影響する重要なアップデート"},
    "B": {"label": "B", "description": "今すぐ対応不要だが、ウォッチまたは今後のPoC候補として有用な情報"},
    "C": {"label": "C", "description": "関連はあるが低優先度（通常フィードには含めない）"},
}

# モデル種別ラベル（AGENTS.md のテーブルが単一情報源）
MODEL_TYPE_META = {
    "Frontier": "GPT/Claude/Geminiなどの主要フロンティアモデル",
    "Reasoning": "推論能力・長考性能を主な売りにするモデル",
    "Coding": "コード生成・SWE-bench等を主な売りにするモデル",
    "Multimodal": "画像・音声・動画・画面理解を扱うモデル",
    "Open": "オープンウェイト・OSS・公開モデル",
    "Small": "小型・オンデバイス・低コストモデル",
    "Embedding": "埋め込み・検索・RAG用モデル",
    "Audio": "音声認識・音声生成・会話モデル",
    "Video": "動画生成・動画理解モデル",
    "Other": "上記に分類しづらいモデル",
}

# content のある言語だけ出力する。collect.py が en を出すようになったら "en" を足す
LANGUAGES = ["ja"]

OG_DESC_MAX = 200
RELATED_MAX = 4

# 購読ページ用フィード一覧（FEED_CONFIGS から名前・説明を導出）
FEEDS = [
    {
        "name": cfg["title"].split(" - ")[-1],
        "file": filename,
        "description": cfg["description"],
    }
    for filename, cfg in FEED_CONFIGS.items()
]


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # テンプレートはオリジンをまたいでも解決できるよう絶対URLを使う（相対パス禁止）
    env.globals["asset"] = lambda path: f"{SITE_URL}/assets/{path}"
    env.globals["article_url"] = lambda a: f"{SITE_URL}/articles/{a['id']}.html"
    env.globals["page_url"] = lambda name: f"{SITE_URL}/{name}"
    env.globals["lang_home_url"] = lambda l: f"{SITE_URL}/index.html"
    env.globals["site_name"] = SITE_NAME
    env.globals["site_tagline"] = SITE_TAGLINE
    env.globals["site_url"] = SITE_URL
    env.globals["feeds_base_url"] = FEEDS_BASE_URL
    return env


def _source_hue(source: str) -> int:
    """ソース名から決定的にプレースホルダ色相(0-359)を導く。
    Web(macros.html の --ph-hue / styles.css)とアプリで同じ色を出すための単一ロジック。"""
    return int(hashlib.md5(source.encode("utf-8")).hexdigest()[:6], 16) % 360


def _parse_dt(iso_str: str):
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _recency_group(published_at: str, now: datetime) -> str:
    dt = _parse_dt(published_at)
    if dt is None:
        return "earlier"
    days = (now.date() - dt.date()).days
    if days <= 0:
        return "today"
    if days <= 7:
        return "week"
    return "earlier"


def prepare(a: dict, now: datetime) -> dict:
    """テンプレートが使う派生フィールドを補う（元データは壊さない）。"""
    title = a.get("title") or "(無題)"
    summary = a.get("summary") or ""
    summary_oneline = " ".join(summary.split())
    impact_oneline = " ".join((a.get("impact") or "").split())
    desc = summary_oneline or impact_oneline or title
    if len(desc) > OG_DESC_MAX:
        desc = desc[: OG_DESC_MAX - 1] + "…"
    tags = a.get("tags") or []

    a["_title"] = title
    a["_summary_oneline"] = summary_oneline
    a["_og_description"] = desc
    a["_date"] = (a.get("published_at") or "")[:10]
    a["_group"] = _recency_group(a.get("published_at", ""), now)
    a["_tags_attr"] = " ".join(str(t) for t in tags).lower()
    a["_share_text"] = quote(title)
    # 一覧サムネ(_thumb): 取得元サイト(RSS)のサムネ image_url のみ。
    # 記事詳細の最初のサムネ(_hero): AI生成画像(image_generated_url) → image_url の順。
    # og:image(SNS共有) は外部スクレイパ互換を優先し従来どおり OG画像 or 既定画像のまま。
    a["image_url"] = a.get("image_url") or None
    a["_thumb"] = a["image_url"] or None
    a["_hero"] = a.get("image_generated_url") or a["image_url"] or None
    a["_og_image"] = a["image_url"] or f"{SITE_URL}/assets/img/og-default.png"
    source = a.get("source") or a.get("provider") or "AI"
    a["_hue"] = _source_hue(source)
    return a


def _related(target: dict, articles: list[dict]) -> list[dict]:
    """同じタグ/提供元/種別を共有する記事を最大 RELATED_MAX 件（新しい順）。"""
    tags = set(target.get("tags") or [])
    out = []
    for a in articles:
        if a["id"] == target["id"]:
            continue
        if (
            (tags and tags.intersection(a.get("tags") or []))
            or (target.get("provider") and a.get("provider") == target.get("provider"))
            or (target.get("model_type") and a.get("model_type") == target.get("model_type"))
        ):
            out.append(a)
        if len(out) >= RELATED_MAX:
            break
    return out


def _group_articles(articles: list[dict]) -> list[dict]:
    labels = [("today", "今日"), ("week", "今週"), ("earlier", "それ以前")]
    groups = []
    for key, label in labels:
        items = [a for a in articles if a["_group"] == key]
        if items:
            groups.append({"key": key, "label": label, "articles": items})
    return groups


def render_index(env: Environment, articles: list[dict]) -> None:
    groups = _group_articles(articles)
    sources = sorted({a.get("source") for a in articles if a.get("source")})
    html = env.get_template("index.html").render(
        lang="ja",
        languages=LANGUAGES,
        groups=groups,
        sources=sources,
        total=len(articles),
        feeds=FEEDS,
    )
    (PAGES_DIR / "index.html").write_text(html, encoding="utf-8")


def render_subscribe(env: Environment) -> None:
    html = env.get_template("subscribe.html").render(
        lang="ja", languages=LANGUAGES, feeds=FEEDS
    )
    (PAGES_DIR / "subscribe.html").write_text(html, encoding="utf-8")


def render_article(env: Environment, a: dict, articles: list[dict]) -> bool:
    """1記事ページを生成。1件の失敗で全体を落とさない（CLAUDE.mdルール）。"""
    try:
        html = env.get_template("article.html").render(
            lang=a.get("language") or "ja",
            languages=LANGUAGES,
            a=a,
            related=_related(a, articles),
        )
        (PAGES_DIR / "articles" / f"{a['id']}.html").write_text(html, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"Failed to render article {a.get('id', '?')}: {e}")
        return False


def copy_assets() -> None:
    if not ASSETS_DIR.is_dir():
        logger.warning(f"{ASSETS_DIR} not found — skipping asset copy")
        return
    shutil.copytree(ASSETS_DIR, PAGES_DIR / "assets", dirs_exist_ok=True)
    logger.info(f"Copied assets {ASSETS_DIR} -> {PAGES_DIR / 'assets'}")


def render_meta(articles: list[dict]) -> None:
    """表示定数(ソース色/重要度/モデル種別)を shared/meta.json に出力。
    モバイルアプリとWebが同じ定義を参照するための単一情報源。既存サイト生成物には
    一切干渉せず、失敗してもサイト生成を落とさない（純粋な追加出力）。
    機密は含めない（公開前提の表示定数のみ）。"""
    try:
        sources = sorted({a.get("source") for a in articles if a.get("source")})
        meta = {
            "schema_version": 1,
            "site_url": SITE_URL,
            "site_name": SITE_NAME,
            # アプリが記事データを取得する公開URL（= 配信されている models.json）
            "data_url": f"{SITE_URL}/data/models.json",
            # プレースホルダ色: HSL の color-1/color-2 を hue から導く（Webの styles.css と同等）
            "placeholder": {
                "formula": "hue = int(md5(source).hexdigest()[:6], 16) % 360",
                "saturation": 55,
                "lightness": 30,
            },
            "sources": [{"name": s, "hue": _source_hue(s)} for s in sources],
            "importance": IMPORTANCE_META,
            "model_types": MODEL_TYPE_META,
        }
        SHARED_META_PATH.parent.mkdir(parents=True, exist_ok=True)
        SHARED_META_PATH.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        logger.info(f"Wrote shared meta -> {SHARED_META_PATH} ({len(sources)} sources)")
    except Exception as e:  # 既存サイト生成を巻き込まない
        logger.warning(f"Failed to write shared meta {SHARED_META_PATH}: {e}")


def copy_static_pages() -> None:
    for name in STATIC_PAGE_FILES:
        src = STATIC_PAGES_DIR / name
        dst = PAGES_DIR / name
        if not src.exists():
            logger.warning(f"{src} not found — skipping static page copy")
            continue
        if src.resolve() == dst.resolve():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        logger.info(f"Copied static page {src} -> {dst}")


def main() -> None:
    if not MODELS_JSON_PATH.exists():
        logger.warning("models.json not found — generating empty site")
        articles: list[dict] = []
    else:
        with open(MODELS_JSON_PATH, encoding="utf-8") as f:
            articles = json.load(f)
    logger.info(f"Loaded {len(articles)} articles")

    now = datetime.now(timezone.utc)
    # 表示対象は重要度 A/B（C は通常フィードと同様に一覧から除外）。新しい順。
    visible = [a for a in articles if a.get("importance") in ("A", "B")]
    visible.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    for a in visible:
        prepare(a, now)

    (PAGES_DIR / "articles").mkdir(parents=True, exist_ok=True)
    env = _build_env()

    copy_assets()
    copy_static_pages()
    render_meta(visible)
    render_index(env, visible)
    render_subscribe(env)

    rendered = sum(render_article(env, a, visible) for a in visible)
    logger.info(
        f"Site generation complete: index + subscribe + {rendered}/{len(visible)} article pages -> {PAGES_DIR}"
    )


if __name__ == "__main__":
    main()
