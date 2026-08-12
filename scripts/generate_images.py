"""Generate eyecatch images for high-importance articles via Vertex AI (Gemini 2.5 Flash Image).

AI生成画像は記事元のOG画像(`image_url`)とは別フィールド `image_generated_url` に保存する
（テンプレートは AI画像 → OG画像 → プレースホルダ の順で表示する）。

models.json を読み、対象（既定 重要度 B 以上 = A・B、A>B>C のしきい値）かつ image_generated_url 未設定の記事に対して:
  1) Gemini(テキスト)で「英語の抽象的な視覚プロンプト」と「日本語の代替テキスト(alt)」を生成
  2) Gemini 2.5 Flash Image で画像を生成
  3) 公開GCSバケットの images/<記事id>.webp へ不変キャッシュ付きでアップロード
  4) image_generated_url / image_generated_alt / image_generated_prompt を models.json に書き戻す

設計方針（既存パイプラインに合わせる）:
- GCP_PROJECT 未設定・認証不可・GCS_BUCKET 未設定・1記事の生成失敗のいずれでも
  ジョブをエラー終了させず、画像なしのまま完走する（フォールバック）。
- 既に画像を持つ記事（image_generated_url 設定済み or GCS に同一IDの画像が存在）は再生成しない（冪等）。
- 画像内に文字は描かせず、実在ロゴ・人物・商標を避けた抽象的アイキャッチにする。
- 1回の実行は IMAGE_MAX_PER_RUN 枚で打ち切り、残りは次回実行へ持ち越す（コスト制御）。

ローカルでの試験実行例:
  gcloud auth application-default login
  export GCP_PROJECT=ai-watch-feed
  export GCS_BUCKET=ai-watch-feed-llm-watch-public
  python scripts/generate_images.py
"""

import io
import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 重い/任意の依存はインポート失敗でもジョブ全体を落とさないよう防御的に読み込む。
try:
    from google import genai
    from google.genai import types as genai_types
except Exception as e:  # pragma: no cover - 環境依存
    genai = None
    genai_types = None
    _GENAI_IMPORT_ERROR = e
else:
    _GENAI_IMPORT_ERROR = None

try:
    from google.cloud import storage
except Exception as e:  # pragma: no cover - 環境依存
    storage = None
    _STORAGE_IMPORT_ERROR = e
else:
    _STORAGE_IMPORT_ERROR = None

try:
    from PIL import Image
except Exception as e:  # pragma: no cover - 環境依存
    Image = None
    _PIL_IMPORT_ERROR = e
else:
    _PIL_IMPORT_ERROR = None


MODELS_JSON_PATH = Path(os.environ.get("MODELS_JSON_PATH", "docs/data/models.json"))
# 生成対象の重要度しきい値（高い順 A > B > C）。IMAGE_MIN_IMPORTANCE「以上」を対象にする。
# 既定 "B" = 重要度 A・B を生成し、C は対象外。
_IMPORTANCE_ORDER = {"A": 3, "B": 2, "C": 1}
IMAGE_MIN_IMPORTANCE = os.environ.get("IMAGE_MIN_IMPORTANCE", "B")
IMAGE_MAX_PER_RUN = int(os.environ.get("IMAGE_MAX_PER_RUN", "5"))


def meets_importance(importance: Optional[str]) -> bool:
    """記事の重要度が IMAGE_MIN_IMPORTANCE 以上か（A > B > C）。未知/欠落は対象外。"""
    threshold = _IMPORTANCE_ORDER.get(IMAGE_MIN_IMPORTANCE, _IMPORTANCE_ORDER["A"])
    return _IMPORTANCE_ORDER.get(importance or "", 0) >= threshold

GCS_BUCKET = os.environ.get("GCS_BUCKET")
IMAGE_BASE_URL = os.environ.get(
    "IMAGE_BASE_URL",
    f"https://storage.googleapis.com/{GCS_BUCKET}" if GCS_BUCKET else "",
)

TEXT_MODEL = os.environ.get("VERTEX_MODEL", "gemini-3.1-flash-lite")
IMAGE_MODEL = os.environ.get("VERTEX_IMAGE_MODEL", "gemini-2.5-flash-image")

# 不変な配信物として長期キャッシュさせる（記事ごとに画像は変わらない）。
IMAGE_CACHE_CONTROL = "public, max-age=31536000, immutable"

# 視覚プロンプト生成のシステム指示。記事内容を概念的なアイキャッチに落とし込む。
PROMPT_SYSTEM = """あなたはAIニュース記事のアイキャッチ画像のアートディレクターです。
記事のタイトル・要約・タグから、内容が直感的に伝わる「抽象的・概念的」なビジュアルの
英語プロンプトを作成してください。

必須の制約:
- 画像内に文字・ロゴ・UI・透かしを一切入れない（no text, no letters, no logos, no watermark, no UI）。
- 実在企業のロゴ・商標・実在人物・著名人を描かない。
- 抽象的・概念的・象徴的な構図にする（モダンでクリーン、テック系のトーン）。
- 横長16:9で1枚絵として成立する明確な主題を持たせる。

出力はJSONのみ。必ず次の形式で回答すること:
{
  "prompt": "英語の画像生成プロンプト（80語以内、視覚的・具体的な描写）",
  "alt": "日本語の代替テキスト（1文・画像内容の説明）"
}"""


def load_articles() -> list[dict]:
    if MODELS_JSON_PATH.exists():
        with open(MODELS_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_articles(articles: list[dict]) -> None:
    MODELS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODELS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(articles)} articles to {MODELS_JSON_PATH}")


def build_client() -> Optional["genai.Client"]:
    """Vertex AI 経由の google-genai クライアントを ADC で初期化する。

    GCP_PROJECT 未設定・依存欠落・初期化失敗時は None を返し、呼び出し側で
    画像なしのまま完走させる（パイプラインを落とさないため）。
    """
    project = os.environ.get("GCP_PROJECT")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    if not project:
        logger.warning("GCP_PROJECT is not set. Skipping image generation.")
        return None
    if genai is None:
        logger.warning(f"google-genai unavailable ({_GENAI_IMPORT_ERROR}). Skipping image generation.")
        return None
    try:
        client = genai.Client(vertexai=True, project=project, location=location)
        logger.info(f"Using Vertex AI image model: {IMAGE_MODEL} ({project}/{location})")
        return client
    except Exception as e:
        logger.warning(f"genai client init failed ({e}). Skipping image generation.")
        return None


def make_visual_prompt(client, article: dict) -> Optional[dict]:
    """記事から英語の視覚プロンプトと日本語altを生成する（2段階目の入力）。"""
    tags = ", ".join(article.get("tags") or [])
    user_content = (
        f"タイトル: {article.get('title', '')}\n"
        f"要約: {article.get('summary', '') or '(なし)'}\n"
        f"タグ: {tags or '(なし)'}"
    )
    try:
        resp = client.models.generate_content(
            model=TEXT_MODEL,
            contents=user_content,
            config=genai_types.GenerateContentConfig(
                system_instruction=PROMPT_SYSTEM,
                temperature=0.7,
                response_mime_type="application/json",
            ),
        )
        data = json.loads(resp.text)
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return None
        return {"prompt": prompt, "alt": (data.get("alt") or "").strip()}
    except Exception as e:
        logger.warning(f"Visual-prompt generation failed for '{article.get('title', '')[:60]}': {e}")
        return None


def _extract_image_bytes(resp) -> Optional[bytes]:
    """genai のレスポンスから最初の inline 画像バイト列を取り出す。"""
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data
    return None


def generate_image_webp(client, prompt: str) -> Optional[bytes]:
    """視覚プロンプトから画像を生成し、WebP バイト列に変換して返す。"""
    try:
        resp = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
    except Exception as e:
        logger.warning(f"Image generation call failed: {e}")
        return None

    raw = _extract_image_bytes(resp)
    if not raw:
        logger.warning("Image generation returned no image data.")
        return None

    if Image is None:
        logger.warning(f"Pillow unavailable ({_PIL_IMPORT_ERROR}); cannot encode WebP.")
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=82, method=6)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"WebP encoding failed: {e}")
        return None


def upload_image(bucket, object_key: str, data: bytes) -> None:
    blob = bucket.blob(object_key)
    blob.cache_control = IMAGE_CACHE_CONTROL
    blob.upload_from_string(data, content_type="image/webp")
    logger.info(f"Uploaded gs://{GCS_BUCKET}/{object_key}")


def main() -> None:
    articles = load_articles()
    if not articles:
        logger.info("No articles found. Nothing to do.")
        return

    if not GCS_BUCKET or storage is None:
        reason = "GCS_BUCKET is not set" if not GCS_BUCKET else f"storage unavailable ({_STORAGE_IMPORT_ERROR})"
        logger.warning(f"{reason}. Skipping image generation (articles unchanged).")
        return

    client = build_client()
    if client is None:
        return  # 画像なしで完走（フォールバック）

    bucket = storage.Client().bucket(GCS_BUCKET)

    # 対象: 重要度が IMAGE_MIN_IMPORTANCE 以上（A>B>C）で、まだ AI生成画像を持たない記事。
    targets = [
        a
        for a in articles
        if meets_importance(a.get("importance")) and not a.get("image_generated_url")
    ]
    logger.info(
        f"Candidates: {len(targets)} (min importance={IMAGE_MIN_IMPORTANCE}, "
        f"max per run={IMAGE_MAX_PER_RUN})"
    )

    generated = 0
    backfilled = 0
    changed = False

    for article in targets:
        if generated >= IMAGE_MAX_PER_RUN:
            break

        article_id = article.get("id")
        if not article_id:
            continue
        object_key = f"images/{article_id}.webp"
        image_url = f"{IMAGE_BASE_URL}/{object_key}"

        # 冪等性: GCS に既存ならアップロードせず参照を補完するだけ（生成枠を消費しない）。
        try:
            if bucket.blob(object_key).exists():
                article["image_generated_url"] = image_url
                backfilled += 1
                changed = True
                logger.info(f"Backfilled existing image: {object_key}")
                continue
        except Exception as e:
            logger.warning(f"Existence check failed for {object_key}: {e}")

        spec = make_visual_prompt(client, article)
        if not spec:
            continue

        webp = generate_image_webp(client, spec["prompt"])
        if not webp:
            continue

        try:
            upload_image(bucket, object_key, webp)
        except Exception as e:
            logger.warning(f"Upload failed for {object_key}: {e}")
            continue

        article["image_generated_url"] = image_url
        article["image_generated_alt"] = spec["alt"]
        article["image_generated_prompt"] = spec["prompt"]
        generated += 1
        changed = True
        logger.info(f"Generated image [{generated}/{IMAGE_MAX_PER_RUN}] for: {article.get('title', '')[:60]}")

    remaining = max(0, len(targets) - generated - backfilled)
    if changed:
        save_articles(articles)
    logger.info(
        f"Done. Generated: {generated}, backfilled: {backfilled}, "
        f"remaining (carry over): {remaining}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 画像生成の失敗でジョブ全体を落とさない（既存パイプラインの方針に合わせる）。
        logger.warning(f"generate_images failed but continuing pipeline: {e}")
