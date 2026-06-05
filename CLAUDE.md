# CLAUDE.md — LLM Model Watch Feed

## プロジェクト概要

AIアプリ開発者向けに、**LLMモデル情報だけ**をキャッチアップできる静的RSSフィードサービス。

- サーバなし・DBなし・GitHub Actions + GitHub Pages + JSON のみで構築
- LLM API呼び出しはGitHub Actionsのみ（APIキーはフロントに出ない）
- `docs/` をGitHub Pagesのソースとして配信

---

## MVP の制約（重要）

このMVPは **LLMモデル情報だけ** を対象にしている。

以下は**対象外**:
- 一般的なAIニュース・資金調達・企業導入事例
- 法規制・セキュリティ・RAG実装記事
- Agentフレームワーク記事・論文全般・プロンプトエンジニアリング

AgentやRAGの記事であっても、主題が「新モデル」「モデル性能」「モデルAPI」なら対象。

---

## アーキテクチャ

```
scripts/collect.py
  - RSS_SOURCESからフィードを取得（feedparser + requests）
  - 新着記事をOpenAI APIで分析（is_model_related判定）
  - モデル関連記事のみdocs/data/models.jsonに追記
  - URLのSHA-256ハッシュで重複排除
  - 1回の実行で最大MAX_NEW_ARTICLES=10件を処理
  - models.jsonは最大MAX_TOTAL_ARTICLES=500件に制限

scripts/generate_feeds.py
  - docs/data/models.jsonを読み込む
  - 6種類のRSS XMLを生成してdocs/feeds/に書き出す
  - BASE_URLは環境変数SITE_URLで設定（デフォルト: プレースホルダー）

docs/index.html
  - 静的HTML + Vanilla JS
  - window.locationからフィードURLを動的生成
  - ./data/models.jsonをfetchして最新モデル情報を表示

.github/workflows/collect.yml
  - 火・金 09:00 JST (UTC 00:00) にcron実行
  - workflow_dispatchで手動実行可
  - 変更がない場合はcommitしない
```

---

## 開発ルール

- Pythonはシンプル・読みやすさ優先
- 1記事・1ソースの失敗で全体が落ちないようにtry/exceptで保護
- APIキーをHTML・JSに絶対に書かない
- `docs/`以下はすべて公開されるため機密情報を置かない
- コメントはWHYが非自明な場合のみ記述
- フロントエンドフレームワーク不使用（Vanilla HTML/JS/CSS）
- 外部依存は増やさない（標準ライブラリ優先）

---

## models.json スキーマ

`docs/data/models.json` は配列形式。各要素:

```json
{
  "id": "sha256-hash-of-url",
  "title": "記事タイトル",
  "url": "https://example.com/article",
  "source": "OpenAI",
  "published_at": "2026-06-04T09:00:00+00:00",
  "collected_at": "2026-06-04T09:05:00+00:00",

  "is_model_related": true,
  "model_relevance_reason": "新しいLLMモデルの発表であるため",

  "model_name": "GPT-5.1",
  "provider": "OpenAI",
  "model_type": "Frontier",
  "summary": "日本語で3行以内の要約",
  "impact": "AIアプリ開発への影響",
  "action": "推奨アクション",
  "importance": "A",
  "tags": ["Frontier", "API", "Pricing"],
  "language": "ja"
}
```

`model_name` が不明な場合は `"Unknown"`。

---

## モデル種別 (model_type)

| 値 | 説明 |
|----|------|
| `Frontier` | GPT、Claude、Geminiなどの主要フロンティアモデル |
| `Reasoning` | 推論能力・長考性能を主な売りにするモデル |
| `Coding` | コード生成・SWE-bench等を主な売りにするモデル |
| `Multimodal` | 画像・音声・動画・画面理解を扱うモデル |
| `Open` | オープンウェイト・OSS・公開モデル |
| `Small` | 小型・オンデバイス・低コストモデル |
| `Embedding` | 埋め込みモデル・検索・RAG用モデル |
| `Audio` | 音声認識・音声生成・会話モデル |
| `Video` | 動画生成・動画理解モデル |
| `Other` | 上記に分類しづらいモデル |

---

## 重要度 (importance)

| 値 | 説明 |
|----|------|
| `A` | AIアプリのモデル選定・API利用・コスト・性能・PoC優先度に直接影響する重要なアップデート |
| `B` | 今すぐ対応不要だが、ウォッチまたは今後のPoC候補として有用なモデル情報 |
| `C` | モデル関連ではあるが低優先度（通常フィードには含めない） |

`all.xml` は重要度AとBを含む。`major-models.xml` は重要度Aのみ。

---

## 実行コマンド

```bash
# 依存インストール
pip install -r requirements.txt

# 記事収集（OPENAI_API_KEY必須）
python scripts/collect.py

# フィード生成
python scripts/generate_feeds.py

# サイト確認（file://不可）
cd docs && python -m http.server 8000
```

環境変数:
- `OPENAI_API_KEY` — OpenAI APIキー（必須）
- `OPENAI_MODEL` — モデル名（デフォルト: `gpt-4.1-mini`）
- `SITE_URL` — GitHub PagesのURL（generate_feeds.py用）

---

## RSSソース

```python
RSS_SOURCES = [
    {"name": "OpenAI",              "url": "https://openai.com/news/rss.xml"},
    {"name": "Anthropic",           "url": "https://www.anthropic.com/news/rss.xml"},
    {"name": "Google DeepMind",     "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Hugging Face Blog",   "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Hugging Face Papers", "url": "https://huggingface.co/papers/rss"},
]
```

---

## 今後の拡張候補

- RSSソースの追加（Mistral、Meta、Microsoft、xAI等）
- 記事本文の全文取得と深い分析
- 重複・類似記事のマージ
- Slack Webhook通知
- タグの自動正規化
- 週次サマリーフィード
- 英語フィード（`language: en`）の追加
- GitHub Actions の実行頻度変更（毎日等）
- モデルリリース履歴の可視化
