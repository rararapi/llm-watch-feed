# CLAUDE.md — AI News Watch Feed

## プロジェクト概要

AI開発者・ウォッチャー向けに、**AIニュースを自動収集・要約**してキャッチアップできるRSSフィード＋サイトサービス。
RSSフィードに加え、収集ニュースの要約を本サイトでも公開する。

- LLM API呼び出しはバックエンド側のみで行い、APIキーはフロントに出さない
- 収集→分析・要約→JSON→RSS XML / サイトの順に生成
- ホスティングは**いずれかのクラウドへ移行予定**（後述「ホスティング方針」）

> ⚠️ **方針転換中**: 本プロジェクトは当初「LLMモデル情報だけ」を対象とする静的フィード(GitHub Pages配信)としてMVPを作った。
> 現在は **対象をAIニュース全般へ拡大** し、**配信先をクラウドへ移行** する方針に変わっている。
> このため現行コード（`is_model_related`判定・`models.json`という命名・GitHub Pages前提など）は
> 旧方針のまま残っており、新方針に合わせて段階的に見直す必要がある。

---

## 現フェーズの目的（最優先）

まずサイトをいずれかのクラウド上で稼働させ、サイトに更新があったときにRSSで通知を
受け取れる状態にすること。凝った機能より「動いて届く」ことを優先する。

---

## 対象スコープ

**AIニュース全般** を対象とする。

- 含む例: モデル発表・性能・API、Agent/ツール、RAG、論文、開発者向けリリース・アップデート、
  資金調達・企業動向・規制・業界ニュース 等
- ※現行コードはまだ「モデル関連だけ」を残す実装（`is_model_related`判定、モデル種別/重要度の分類）になっており、
  スコープ拡大に伴いフィルタ・分類・命名の一般化が必要。

---

## アーキテクチャ（現状）

以下は旧方針のまま残っている現行コードの挙動。新方針に合わせ段階的に見直す。

```
scripts/collect.py
  - RSS_SOURCESからフィードを取得（feedparser + requests）
  - 新着記事をOpenAI APIで分析（is_model_related判定）。APIキー未設定時はダミー要約を埋め込む
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

## ホスティング方針（移行予定）

従来のGitHub Pagesから、**いずれかのクラウド上での稼働へ移行**する想定。
どこかのクラウドで動かすことはほぼ確実だが、クラウド事業者（AWS / GCP / Azure 等）も
具体的なサービス選定も**未定**。収集処理の実行場所（GitHub Actions 継続か、クラウドへ寄せるか）も**未定**。

- 特定クラウドに過度に依存しない選択を基本とする。
- 提案・設計時はこの未確定点を明示し、必要なら選択肢とトレードオフを提示する。

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

## データスキーマ（現状: models.json）

> 現行の保存先は `docs/data/models.json`。モデル前提の命名・フィールド（`is_model_related`、
> `model_name`、`model_type` 等）が残っており、AIニュース全般への拡大に合わせて
> 命名・分類の一般化を検討する。以下は現行スキーマ。

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

# 記事収集（OPENAI_API_KEYは任意。無ければダミー要約で動作）
python scripts/collect.py

# フィード生成
python scripts/generate_feeds.py

# サイト確認（file://不可）
cd docs && python -m http.server 8000
```

環境変数:
- `OPENAI_API_KEY` — OpenAI APIキー（任意。未設定ならダミー要約で動作）
- `OPENAI_MODEL` — モデル名（デフォルト: `gpt-4.1-mini`）
- `SITE_URL` — 公開サイトのURL（generate_feeds.py用。現状GitHub Pages、移行後は稼働クラウドのURL）

---

## RSSソース

現状はモデルプロバイダ中心。スコープ拡大に伴い、AIニュース全般を扱うソースを追加していく。

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

新方針（AIニュース全般 / クラウド移行）に直結する項目を優先する。

- **[優先] クラウドへのデプロイ**（配信構成の選定・構築。事業者/サービスは未定）
- **[優先] 対象スコープの拡大対応**（`is_model_related`フィルタの一般化、AIニュース全般の分類・タグ整備）
- **[優先] 命名の一般化**（`models.json` など旧名のリネーム検討）
- AIニュース全般を扱うRSSソースの追加
- 記事本文の全文取得と深い分析
- 重複・類似記事のマージ
- Slack Webhook通知
- タグの自動正規化
- 週次サマリーフィード
- 英語フィード（`language: en`）の追加
- 収集の実行頻度変更（毎日等）
