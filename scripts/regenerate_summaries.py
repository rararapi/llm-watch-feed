"""既存 models.json の全記事を Vertex AI（Gemini）で再分析し、要約等を作り直す。

collect.py は新着記事しか分析しないため、過去のダミー要約（Vertex/旧OpenAI未設定時の
プレースホルダ）が残り続ける。Vertex が使えるようになったら本スクリプトで一括再生成する。

- 分析フィールド（summary / impact / action / model_* / importance / tags /
  model_relevance_reason / is_model_related）のみ上書きし、
  id / url / source / published_at / collected_at / language は保持する。
- 記事本文は保存していないため、RSS フィードを再取得して excerpt を可能な範囲で復元し、
  フィードに残っていない過去記事はタイトル等のみで分析する。
- Vertex が使えない（ダミーモード）場合は、ダミー要約で上書きしてしまわないよう中断する。
- 1記事の分析失敗は元のレコードを温存し、全体は止めない。

使い方:
  gcloud auth application-default login        # 一度だけ
  export GCP_PROJECT=<your-project-id>         # .env でも可
  python scripts/regenerate_summaries.py
"""

import logging
import os

from collect import (
    MODELS_JSON_PATH,
    RSS_SOURCES,
    analyze,
    build_model,
    fetch_source,
    load_existing,
    save_articles,
)

logger = logging.getLogger(__name__)

# 再生成では「AIニュース全般」を対象スコープとし、モデル関連かどうかに関わらず
# 必ず日本語要約を生成する（collect.py の SYSTEM_PROMPT はモデル非関連だと
# 要約を空で返す仕様のため、ここでは専用プロンプトを使う）。
REGEN_SYSTEM_PROMPT = """あなたはAIアプリ開発者向けのAIニュースアナリストです。
与えられた記事を読み、AI開発者がキャッチアップしやすいように日本語で要約・分析してください。
対象はAIニュース全般（新モデル・API・性能・価格、Agent/ツール、RAG、論文、
開発者向けリリース、資金調達・企業動向・規制・業界ニュース等）です。

すべての記事について summary / impact / action を必ず日本語で埋めてください（空文字禁止）。
情報が乏しい場合でもタイトル等から妥当な要約を生成すること。

is_model_related は「新モデル発表・モデル更新・性能/価格/API等、モデルそのものの情報」なら true、
それ以外（企業導入事例・方針・提携・規制・一般ニュース）は false にしてください。

model_type は以下から1つ選択（モデル非関連なら "Other"）:
Frontier, Reasoning, Coding, Multimodal, Open, Small, Embedding, Audio, Video, Other

importance は必ず A / B / C のいずれかを設定（空禁止）:
A: モデル選定・API利用・コスト・性能・PoC優先度に直接影響する重要な情報
B: 今すぐ対応不要だが、ウォッチ価値のあるAIニュース
C: 参考程度の低優先度ニュース

出力はJSONのみ。説明文は一切不要。必ず以下のJSON形式のみで回答すること:

{
  "is_model_related": true,
  "model_relevance_reason": "判定理由",
  "model_name": "GPT-5.1",
  "provider": "OpenAI",
  "model_type": "Frontier",
  "summary": "日本語で3行以内の要約",
  "impact": "AIアプリ開発への影響",
  "action": "推奨アクション",
  "importance": "A",
  "tags": ["Frontier", "API"]
}

model_name が不明、またはモデル非関連の場合は "Unknown" を使用。"""

# 上書きする分析由来フィールドと、欠損時のデフォルト
ANALYSIS_FIELDS = {
    "is_model_related": True,
    "model_relevance_reason": "",
    "model_name": "Unknown",
    "provider": "",
    "model_type": "Other",
    "summary": "",
    "impact": "",
    "action": "",
    "importance": "C",
    "tags": [],
}


def build_excerpt_map() -> dict[str, str]:
    """現在の RSS フィードを再取得し、URL -> excerpt の対応を作る（ベストエフォート）。"""
    excerpts: dict[str, str] = {}
    for source in RSS_SOURCES:
        for article in fetch_source(source):
            if article["url"] and article.get("excerpt"):
                excerpts[article["url"]] = article["excerpt"]
    logger.info(f"Recovered excerpts for {len(excerpts)} URL(s) from current feeds")
    return excerpts


def main() -> None:
    model = build_model(REGEN_SYSTEM_PROMPT)
    if model is None:
        logger.error(
            "Vertex AI is unavailable (DUMMY mode). Aborting so that real "
            "summaries are not overwritten with placeholders. "
            "Set GCP_PROJECT and ensure ADC is configured."
        )
        raise SystemExit(2)

    records = load_existing()
    if not records:
        logger.warning(f"No records found at {MODELS_JSON_PATH}. Nothing to do.")
        return
    logger.info(f"Regenerating summaries for {len(records)} article(s)")

    excerpt_map = build_excerpt_map()

    regenerated = 0
    failed = 0
    for record in records:
        article = {
            "title": record.get("title", ""),
            "source": record.get("source", ""),
            "url": record.get("url", ""),
            "excerpt": excerpt_map.get(record.get("url", ""), ""),
        }
        logger.info(f"Analyzing: {article['title'][:70]}")
        result = analyze(model, article)
        if not result:
            failed += 1
            logger.warning("  -> Kept original (analysis failed)")
            continue

        # 空文字/空配列で返ってきたフィールドはデフォルトへ寄せる
        # （特に importance/model_type が空だとフィードの絞り込みが壊れるため）。
        for field, default in ANALYSIS_FIELDS.items():
            value = result.get(field, default)
            if isinstance(default, str) and not str(value).strip():
                value = default
            elif isinstance(default, list) and not value:
                value = default
            record[field] = value
        regenerated += 1
        logger.info(
            f"  -> Updated [{record['importance']}][{record['model_type']}] "
            f"{record['model_name']}"
        )

    save_articles(records)
    logger.info(
        f"Done. Regenerated: {regenerated}, Failed (kept original): {failed}, "
        f"Total: {len(records)}"
    )


if __name__ == "__main__":
    main()
