"""Generate the static site (index + per-article OGP pages + subscribe) from models.json.

トップ/購読ページに加え、SNS共有用の「OGPを焼き込んだ個別記事ページ」を事前生成する。
出力は PAGES_DIR 以下で、そのディレクトリは公開GCSバケット直下のミラーになる
（= 各ファイルの相対パス = GCSオブジェクトキー = {SITE_URL}/<key>）。RSSと同じく日次バッチで
生成・配信され、サイトの「デプロイ」は不要（feeds と同じ“バッチ生成物”として扱う）。
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

# OGP/canonical/asset の絶対URL基準。記事が実際に配信されるGCSオリジンを指す（SITE_URL を再利用）
SITE_URL = os.environ.get(
    "SITE_URL", "https://storage.googleapis.com/your-bucket"
).rstrip("/")
SITE_NAME = os.environ.get("SITE_NAME", "AI News Watch")
SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "AIニュースを自動収集・要約してお届け")

MODELS_JSON_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))
PAGES_DIR = Path(os.environ.get("PAGES_DIR", "docs"))
TEMPLATES_DIR = Path(os.environ.get("TEMPLATES_DIR", "templates"))
ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", "assets/site"))

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
    return env


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
    a["_hue"] = int(hashlib.md5(source.encode("utf-8")).hexdigest()[:6], 16) % 360
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
    render_index(env, visible)
    render_subscribe(env)

    rendered = sum(render_article(env, a, visible) for a in visible)
    logger.info(
        f"Site generation complete: index + subscribe + {rendered}/{len(visible)} article pages -> {PAGES_DIR}"
    )


if __name__ == "__main__":
    main()
