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
