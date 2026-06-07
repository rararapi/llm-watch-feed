# CLAUDE.md — AI News Watch Feed

## プロジェクト概要

AI開発者・ウォッチャー向けに、**AIニュースを自動収集・要約**してキャッチアップできるRSSフィード＋サイトサービス。
RSSフィードに加え、収集ニュースの要約を本サイトでも公開する。

- LLM API呼び出しはバックエンド側のみで行い、APIキーはフロントに出さない
- 収集→分析・要約→JSON→RSS XML / サイトの順に生成
- ホスティングは**GCP で稼働**（後述「ホスティング方針」、手順は `DEPLOY.md`）

> ⚠️ **方針転換中**: 本プロジェクトは当初「LLMモデル情報だけ」を対象とする静的フィード(GitHub Pages配信)としてMVPを作った。
> **配信基盤は GCP へ移行済み**（手順は `DEPLOY.md`）。構成は方式A: **画面(HTML/JS)は Firebase Hosting（無料HTTPS・独自ドメイン可）**、
> **データ(`data/models.json`)とRSSフィード(`feeds/*.xml`)は公開GCSバケット**が配信する。
> ニュース更新は GCS への書き込みのみで完結し、サイトの「デプロイ」は不要。Firebaseデプロイはサイト画面の変更時だけ。
> 一方で **対象をAIニュース全般へ拡大** する方針は進行中で、現行コード（`is_model_related`判定・`models.json`という命名）は
> 旧方針のまま残っており、段階的に見直す必要がある。

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

実行基盤は GCP。方式A構成: 画面(HTML/JS)は Firebase Hosting、データとRSSフィードは公開GCSバケットが配信する。
状態 `models.json` の正本は公開GCSバケットの `data/models.json` で、これがそのまま配信される。
ニュース更新（毎日・GCS書き込みのみ）とサイトデプロイ（HTML変更時のみ・Firebase）は分離している。
収集・分類のコードは旧方針（モデル関連判定）のまま残っており段階的に見直す。

```
scripts/collect.py
  - RSS_SOURCESからフィードを取得（feedparser + requests）
  - 新着記事をVertex AI（Gemini）で分析（is_model_related判定）。Vertex未設定/認証不可時はダミー要約を埋め込む
  - モデル関連記事のみ models.json に追記（出力先は環境変数 MODELS_JSON_PATH、既定 docs/data/models.json）
  - URLのSHA-256ハッシュで重複排除
  - 1回の実行で最大MAX_NEW_ARTICLES=10件を処理
  - models.jsonは最大MAX_TOTAL_ARTICLES=500件に制限

scripts/generate_feeds.py
  - models.json（MODELS_JSON_PATH）を読み込む
  - 6種類のRSS XMLを生成（出力先は環境変数 FEEDS_DIR、既定 docs/feeds/）
  - BASE_URLは環境変数SITE_URLで設定

scripts/gcs_sync.py / scripts/run_job.sh / scripts/deploy_site.sh
  - run_job.sh が Cloud Run Job のエントリポイント（ニュース更新ジョブ）
    GCSからmodels.json取得 → collect → generate → GCSへ data/models.json と feeds/ を書き込み
  - gcs_sync.py のコマンド: download / upload(=配信データ) / publish-feeds /（publish-site はGCS配信時の予備）
  - deploy_site.sh は画面(HTML)を Firebase Hosting へデプロイ（サイト変更時のみ・ニュース更新とは独立）

docs/index.html
  - 静的HTML + Vanilla JS。Firebase Hosting から配信
  - フィードURLと models.json は公開GCSバケットの絶対URL（DATA_ORIGIN）からfetch（CORS設定済み）

GCP 実行基盤（手順は DEPLOY.md）
  - Cloud Scheduler が毎日 Cloud Run Job をトリガー → data/models.json と feeds/ をGCSへ書き込み（デプロイ不要）
  - 画面は Firebase Hosting（無料HTTPS・`*.web.app`・独自ドメインも無料で接続可）。データ/フィードは公開GCSバケット
  - 記事分析は Vertex AI（Gemini）を ADC（実行サービスアカウント）で利用。APIキー不要
    （GCP_PROJECT 未設定/権限不足ならダミーモード）
```

---

## ホスティング方針（GCP・実装済み）

GitHub Pages から **GCP** へ移行済み。構築手順は `DEPLOY.md`。

- 構成: 方式A（画面=Firebase Hosting、データ/フィード=公開GCSバケット）
- 実行: Cloud Run Job（`scripts/run_job.sh`）＋ Cloud Scheduler（毎日）
- 状態: 公開GCSバケットの `data/models.json` を正本に download-run-upload。これがそのまま配信される
- データ/フィード配信: 公開GCSバケット（HTTPS・CORS設定済み）。ニュース更新はGCS書き込みのみで「デプロイ」不要
- 画面配信: Firebase Hosting（無料HTTPS）。`scripts/deploy_site.sh`（= `firebase deploy`）でサイト変更時のみデプロイ
- 公開URL: 画面 `https://ai-watch-feed.web.app`、フィード `https://storage.googleapis.com/ai-watch-feed-llm-watch-public/feeds/*.xml`
- 独自ドメイン: Firebase Hosting に無料で接続可（ドメイン自体の取得は別途）。フィードURLはGCSのまま（綺麗にするには有料の方式B=LB/CDN or rewrite が必要）
- LLM: Vertex AI（Gemini）。認証は ADC（実行サービスアカウントに `roles/aiplatform.user`）。APIキー不要。未設定/権限不足ならダミーモードで完走

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

# 記事収集（GCP_PROJECTとADCがあればVertex AIで分析。無ければダミー要約で動作）
#   ローカルで実際にVertexを使う場合は事前に:
#     gcloud auth application-default login
#     export GCP_PROJECT=<your-project-id>   # .env でも可
python scripts/collect.py

# フィード生成
python scripts/generate_feeds.py

# サイト確認（file://不可）
cd docs && python -m http.server 8000
```

GCP へのデプロイ・自動実行の手順は `DEPLOY.md` を参照。

環境変数（ローカルは `.env` に集約。`collect.py` / `generate_feeds.py` / `gcs_sync.py` が起動時に `load_dotenv` で読み込む。本番はジョブのenvを使い `.env` は無いのでno-op。一覧は `.env.example` 参照。認証(ADC)は `.env` に入れない）:
- `GCP_PROJECT` — Vertex AI のプロジェクトID（未設定ならダミー要約で動作）。認証はADCで行いAPIキーは不要
- `VERTEX_LOCATION` — Vertex AI のリージョン（デフォルト: `us-central1`）
- `VERTEX_MODEL` — Gemini モデル名（デフォルト: `gemini-2.5-flash`）
- `SITE_URL` — 公開サイトのURL（generate_feeds.py用。当面はバケットURL、独自ドメイン設定後はそのURL）
- `MODELS_JSON_PATH` / `FEEDS_DIR` — 入出力先（既定 `docs/data/models.json` / `docs/feeds/`。ジョブでは `public/` 配下）
- `GCS_BUCKET` — 公開配信／状態バケット名（`scripts/gcs_sync.py` 用、クラウド実行時）
- `GCS_OBJECT` — 状態＝配信データのキー（既定 `data/models.json`）
- `SITE_DIR` — `gcs_sync.py publish-site`（GCS配信する場合の予備手段）が読むディレクトリ（既定 `docs`）。通常の画面デプロイは Firebase（`deploy_site.sh`）
- `FIREBASE_PROJECT` — `deploy_site.sh`（Firebaseデプロイ）の対象プロジェクト（任意。未設定なら `.firebaserc` の default）

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
