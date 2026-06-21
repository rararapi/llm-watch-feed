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

scripts/generate_images.py
  - models.json の重要度A・image_generated_url未設定の記事に概念的AIアイキャッチ画像を生成
  - Vertex AI（Gemini 2.5 Flash Image）を ADC で利用。2段階（テキスト→視覚プロンプト→画像）
  - 公開GCSバケットの images/<id>.webp へ不変キャッシュ付きでアップロードし image_generated_url 等を書き戻す
  - image_url(OG画像)とは別フィールド。GCP_PROJECT/GCS_BUCKET未設定・生成失敗でも画像なしで完走
    （冪等＝blob.exists()で既存はバックフィル・IMAGE_MAX_PER_RUNで枚数制限）

scripts/generate_feeds.py
  - models.json（MODELS_JSON_PATH）を読み込む
  - 6種類のRSS XMLを生成（出力先は環境変数 FEEDS_DIR、既定 docs/feeds/）
  - BASE_URLは環境変数SITE_URLで設定

scripts/generate_pages.py
  - models.json から Jinja2 でサイトを静的生成（SSG）: index.html / subscribe.html /
    articles/<id>.html（SNS共有用にOGP・Twitter Card・JSON-LDを焼き込んだ個別記事ページ）/ assets
  - 出力先は環境変数 PAGES_DIR（既定 docs、ジョブでは public）。firebase_hosting_deploy.py が
    PAGES_DIR の内容を Firebase Hosting へデプロイする（{SITE_URL}/<key> でアクセス可能）
  - テンプレートは templates/、サイト静的物は assets/site/。OGP/canonical/内部リンクは SITE_URL 基準の絶対URL
  - 表示対象は重要度A/B。1記事の描画失敗で全体が落ちない（try/except）
  - 一覧の絞り込み（重要度/ソース/キーワード）はサーバ生成カードを vanilla JS で表示切替
  - 併せて表示定数を `shared/meta.json`（SHARED_META_PATH）へ出力する。ソース色相(hue)・
    重要度ラベル・モデル種別ラベルの単一情報源で、Web(SSG)とモバイルアプリ(app/)が参照する。
    既存サイト生成物には非干渉（純粋な追加出力・失敗してもサイト生成は完走）。生成物のため gitignore

scripts/gcs_sync.py / scripts/run_job.sh / scripts/deploy_site.sh / scripts/firebase_hosting_deploy.py
  - run_job.sh が Cloud Run Job のエントリポイント（ニュース更新ジョブ）
    GCSからmodels.json取得 → collect → generate_images → generate_feeds → generate_pages →
    GCSへ data/models.json・feeds/ を書き込み（画像は images/ へ直接）→ Firebase Hosting へ画面デプロイ
  - gcs_sync.py のコマンド: download / upload(=配信データ) / publish-feeds /
    publish-pages(手動バックアップ用) /（publish-site はGCS配信時の予備）
  - firebase_hosting_deploy.py は生成済みサイト(index/subscribe/articles/assets)を
    Firebase Hosting REST API で日次デプロイ（Node.js 不要・追加pip依存なし）
  - deploy_site.sh はローカル手動デプロイ用（firebase CLI 経由）

docs/（サイト出力。templates/ + assets/site/ がソース。生成物はgitignore）
  - index.html / subscribe.html / articles/<id>.html / assets を generate_pages.py が生成
  - 記事ページ(articles/)とデータ/フィードは公開GCSバケットが日次配信（OGPクローラはJSを実行しないため
    記事ページは事前生成の静的HTML）。画面(index/subscribe)は Firebase Hosting にも載せて綺麗なURLで入口提供
  - docs/power-automate.html は手書き（Teams連携手順。subscribe から参照）

GCP 実行基盤（手順は DEPLOY.md）
  - Cloud Scheduler が毎日 Cloud Run Job をトリガー → data/models.json・feeds/・サイト(index/articles/assets) をGCSへ書き込み（デプロイ不要）
  - 画面は Firebase Hosting（無料HTTPS・`*.web.app`・独自ドメインも無料で接続可）。データ/フィードは公開GCSバケット
  - 記事分析は Vertex AI（Gemini）を ADC（実行サービスアカウント）で利用。APIキー不要
    （GCP_PROJECT 未設定/権限不足ならダミーモード）
```

---

## ホスティング方針（GCP・実装済み）

GitHub Pages から **GCP** へ移行済み。構築手順は `DEPLOY.md`。

- 構成: 方式A（画面=Firebase Hosting、データ/フィード/AI画像=公開GCSバケット）
- 実行: Cloud Run Job（`scripts/run_job.sh`）＋ Cloud Scheduler（毎日）
- 状態: 公開GCSバケットの `data/models.json` を正本に download-run-upload。これがそのまま配信される
- データ/フィード/AI画像配信: 公開GCSバケット（HTTPS・CORS設定済み）。Storage はデータのみに使用
- 画面配信: Firebase Hosting（無料HTTPS）。`scripts/firebase_hosting_deploy.py`（REST API）が日次で自動デプロイ
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
- フロントエンドフレームワーク不使用（クライアントは Vanilla HTML/JS/CSS）。
  サイトはサーバ側で Jinja2 による静的生成（SSG）を行う。Jinja2 はテンプレートエンジンであり
  クライアントフレームワークではない。OGP付き個別記事ページをSNS共有用に事前生成するための意図的な採用。
- 外部依存は最小限（標準ライブラリ優先）。サイト生成のための Jinja2 追加が唯一の例外。
  クライアント側に追加ライブラリ・ビルドツール・FEフレームワークは持ち込まない。

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
  "image_url": "https://example.com/og-image.jpg",
  "image_generated_url": "https://storage.googleapis.com/ai-watch-feed-llm-watch-public/images/<id>.webp",
  "image_generated_alt": "画像内容を説明する日本語の代替テキスト",
  "image_generated_prompt": "（任意・デバッグ用）画像生成に使った英語の視覚プロンプト",

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

`model_name` が不明な場合は `"Unknown"`。`image_url` はサムネ用に元記事の og:image を
取得したもの（`collect.py` が新着収集時に付与。既存分は `backfill_images.py` で補完）。
取得できなければ `null`。

`image_generated_url` / `image_generated_alt` / `image_generated_prompt` は **AI生成アイキャッチ画像**
（`generate_images.py` が重要度Aの記事に付与。Vertex AI の Gemini 2.5 Flash Image）。画像は公開GCSバケットの
`images/<id>.webp`（不変キャッシュ）に保存。サムネは **AI画像(`image_generated_url`) → 元記事OG画像(`image_url`)
→ ソース名由来の色のプレースホルダ** の優先順で表示する（`generate_pages.py` の `_thumb` と `macros.html`）。

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

# AI画像生成（重要度Aの記事。GCP_PROJECT・GCS_BUCKET・ADCが必要。無ければ画像なしで完走）
python scripts/generate_images.py

# フィード生成
python scripts/generate_feeds.py

# サイト生成（index/subscribe/articles/assets を PAGES_DIR=docs に出力）
python scripts/generate_pages.py

# ローカルでUI確認（デプロイ不要）。SITE_URL をローカルへ向けて生成し直し docs/ を配信。
#   トップ http://localhost:8000/ ・記事 /articles/<id>.html。停止は Ctrl+C
#   データが無ければ公開バケットから自動取得する
./scripts/preview.sh          # ポート変更は ./scripts/preview.sh 8011

# （手動でやる場合）file:// は不可。アセットは絶対URLなので SITE_URL をローカルに合わせる
SITE_URL=http://localhost:8000 python scripts/generate_pages.py
cd docs && python -m http.server 8000
```

GCP へのデプロイ・自動実行の手順は `DEPLOY.md` を参照。

環境変数:
- `GCP_PROJECT` — Vertex AI のプロジェクトID（未設定ならダミー要約で動作）。認証はADCで行いAPIキーは不要
- `VERTEX_LOCATION` — Vertex AI のリージョン（デフォルト: `us-central1`）
- `VERTEX_MODEL` — Gemini モデル名（デフォルト: `gemini-2.5-flash`。視覚プロンプト生成にも利用）
- `VERTEX_IMAGE_MODEL` — AI画像生成モデル名（デフォルト: `gemini-2.5-flash-image`）
- `IMAGE_MIN_IMPORTANCE` — AI画像生成の対象重要度（デフォルト: `A`）
- `IMAGE_MAX_PER_RUN` — 1回の実行で生成する最大枚数（デフォルト: `5`）
- `IMAGE_BASE_URL` — AI画像URLのベース（デフォルト: `https://storage.googleapis.com/<GCS_BUCKET>`）
- `SITE_URL` — サイトの絶対URL基準（generate_pages.py の OGP/canonical/asset/内部リンク、
  generate_feeds.py の `<channel><link>`。Firebase Hosting URL: `https://ai-watch-feed.web.app`）
- `FEEDS_BASE_URL` — フィードファイルの配信元URL（generate_feeds.py の `atom:link rel="self"`）。
  フィードは GCS に置くため SITE_URL とは別に設定する（`https://storage.googleapis.com/<bucket>`）
- `SITE_NAME` / `SITE_TAGLINE` — サイトのブランド表記（generate_pages.py。既定 `AI News Watch` / タグライン）
- `MODELS_JSON_PATH` / `FEEDS_DIR` / `PAGES_DIR` — 入出力先（既定 `docs/data/models.json` / `docs/feeds/` /
  `docs`。ジョブでは `public/` 配下。PAGES_DIR はサイト生成先＝バケット直下のミラー）
- `SHARED_META_PATH` — 表示定数の共有メタ出力先（既定 `shared/meta.json`）。Web/モバイルアプリ共通の
  ソース色・ラベル定義。generate_pages.py が出力（生成物・gitignore）
- `GCS_BUCKET` — 公開配信／状態バケット名（`scripts/gcs_sync.py` 用、クラウド実行時）
- `GCS_OBJECT` — 状態＝配信データのキー（既定 `data/models.json`）
- `SITE_DIR` — `gcs_sync.py publish-site`（GCS配信する場合の予備手段）が読むディレクトリ（既定 `docs`）。通常の画面デプロイは Firebase（`deploy_site.sh`）
- `FIREBASE_PROJECT` — `deploy_site.sh`（Firebaseデプロイ）の対象プロジェクト（任意。未設定なら `.firebaserc` の default）

---

## RSSソース

AIニュース全般を対象に、(1) モデルプロバイダ／開発元、(2) AI専門・テック系メディア、
(3) 研究・開発者向け の3カテゴリで構成する。追加時は事前に取得可否（HTTP 200＋RSS実体あり）を検証する。
公開RSSが無い／HTMLしか返さないソース（Anthropic, Meta AI, Mistral, Cohere, Stability AI 等）は含めていない。

```python
RSS_SOURCES = [
    # モデルプロバイダ／開発元（一次情報）
    {"name": "OpenAI",                   "url": "https://openai.com/news/rss.xml"},
    {"name": "Google DeepMind",          "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Google AI",                "url": "https://blog.google/technology/ai/rss/"},
    {"name": "Google Developers Blog",   "url": "https://developers.googleblog.com/feeds/posts/default/?alt=rss"},
    {"name": "Hugging Face Blog",        "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Microsoft AI Blog",        "url": "https://blogs.microsoft.com/ai/feed/"},
    {"name": "AWS Machine Learning Blog","url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    {"name": "NVIDIA Blog",              "url": "https://blogs.nvidia.com/feed/"},
    {"name": "NVIDIA Developer Blog",    "url": "https://developer.nvidia.com/blog/feed"},
    # 研究機関・大学・研究ブログ
    {"name": "Google Research",          "url": "https://research.google/blog/rss/"},
    {"name": "Microsoft Research",       "url": "https://www.microsoft.com/en-us/research/feed/"},
    {"name": "MIT News AI",              "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml"},
    {"name": "BAIR Blog",                "url": "https://bair.berkeley.edu/blog/feed.xml"},
    # AI専門・テック系メディア（英語）
    {"name": "TechCrunch AI",            "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat AI",           "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "The Verge AI",             "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "Ars Technica AI",          "url": "https://arstechnica.com/ai/feed/"},
    {"name": "MIT Technology Review AI",  "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
    {"name": "WIRED AI",                 "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"name": "The Decoder",              "url": "https://the-decoder.com/feed/"},
    # 国内：政策・総合媒体
    {"name": "デジタル庁",                "url": "https://www.digital.go.jp/rss/news.xml"},
    {"name": "ITmedia AI＋",             "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"},
    {"name": "＠IT Smart & Social",      "url": "https://rss.itmedia.co.jp/rss/2.0/ait_smart.xml"},
    {"name": "Publickey",                "url": "https://www.publickey1.jp/atom.xml"},
    # 国内：企業技術ブログ（実装知見）
    {"name": "LINEヤフー Tech Blog",     "url": "https://techblog.lycorp.co.jp/ja/feed/index.xml"},
    {"name": "Mercari Engineering",      "url": "https://engineering.mercari.com/blog/feed.xml"},
    {"name": "Recruit Tech Blog",        "url": "https://blog.recruit.co.jp/data/index.xml"},
    {"name": "BrainPad Blog",            "url": "https://blog.brainpad.co.jp/rss"},
    {"name": "DeNA Engineering",         "url": "https://engineering.dena.com/index.xml"},
    {"name": "NTT Communications Engineers' Blog", "url": "https://engineers.ntt.com/feed"},
    # 研究・開発者向け（個人）
    {"name": "Simon Willison's Weblog",  "url": "https://simonwillison.net/atom/everything/"},
]
```

国内総合媒体（デジタル庁・＠IT 等）や企業技術ブログは非AI記事も混ざるため、`SYSTEM_PROMPT`
のAIニュース判定（`is_model_related`）でフィルタする前提。要約アグリゲータ（MarkTechPost 等）や
高ノイズの総合媒体（ASCII/CNET/GIGAZINE）、コミュニティ系（Zenn/Qiita/note）は、URLベースの
重複排除しか無い現状では重複・ノイズが増えるため未採用。産総研(AIST)はRSSのフィードURLを
公式ページから確定できず（JSレンダリング）、確証が取れるまで未採用とした。

新着は全ソースをまとめてからソース順に処理するのではなく、**ソースごとにラウンドロビン**で
取り込む（先頭ソースだけで `MAX_NEW_ARTICLES` を使い切らないため）。
`SYSTEM_PROMPT` のフィルタは「モデル関連のみ」から **AIニュース全般** に一般化済み。
互換性のため掲載可否フラグは `is_model_related` という名前のまま（true=掲載、false=対象外）で、
特定モデルの話題でなければ `model_type="Other"` / `model_name="Unknown"` とする。

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
