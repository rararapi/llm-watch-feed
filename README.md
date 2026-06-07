# LLM Model Watch Feed

![LLM Model Watch Feed overview](assets/readme/overview.png)

LLM Model Watch Feed は、LLM モデルに関する重要な更新だけを集めて RSS とサイトで配信する小さなウォッチサービスです。
収集・要約・フィード生成・配信は **GCP 上で毎日自動実行** され、公開は Firebase Hosting（HTTPS）で行います。

新モデルの発表、性能改善、価格変更、API 提供開始、オープンウェイトモデル公開など、AI アプリ開発者が追うべき情報を RSS ソースから収集し、OpenAI API で分類・要約します。

## できること

| 機能 | 内容 |
| --- | --- |
| RSS 収集 | OpenAI、Google DeepMind、Hugging Face などの RSS を取得 |
| LLM 判定 | モデル関連ニュースかどうかを OpenAI API で判定（キー未設定時はダミー要約で動作） |
| 重要度分類 | A / B / C の重要度、モデル種別、タグを付与 |
| RSS 配信 | 用途別の RSS フィードを生成し Firebase Hosting で公開 |
| サイト公開 | `index.html` でフィード URL と最新記事を公開 |
| Teams 通知 | Power Automate の RSS トリガーから Teams へ通知可能 |

## 仕組み（GCP 構成）

```mermaid
flowchart LR
    S[Cloud Scheduler<br/>毎日 09:00 JST] --> J[Cloud Run Job]
    G[(GCS バケット<br/>models.json/正本)] -->|1. 取得| J
    J -->|2. collect.py| K[OpenAI API で<br/>判定・分類・要約]
    K -->|3. generate_feeds.py| F[feeds/*.xml 生成]
    J -->|4. 保存| G
    J -->|5. deploy| H[Firebase Hosting<br/>HTTPS 公開]
    H --> P[Power Automate / Teams]
```

- 状態 `models.json` の正本は **GCS**（DB は使いません）。実行ごとに「取得 → 更新 → 保存」します。
- 収集・生成・配信は **Cloud Run Job** が 1 回で実行し、**Cloud Scheduler** が毎日トリガーします。
- 一般配信は **Firebase Hosting に一本化**（GCS バケットは非公開）。
- API キーは **Secret Manager**（クラウド）またはローカル `.env` のみに置き、公開ファイルには含めません。

## 対象にする情報

このプロジェクトは、AI アプリ開発や PoC の判断に直接影響するモデル情報を優先します。

- 新しい LLM / マルチモーダル / reasoning / coding モデルの発表
- 既存モデルの性能改善、コンテキスト長拡張、API 仕様変更
- 価格、レート制限、提供リージョン、提供開始・終了の変更
- オープンウェイトモデルの公開
- 推論モデル、埋め込み、音声、動画モデルなどの重要な更新

> ※ スコープは AI ニュース全般への拡大方針です。現行コードはモデル関連判定が残っており、段階的に一般化します。

## ローカル実行

スクリプトはローカルでもそのまま動きます（入出力先は環境変数で切替可能。既定は `docs/` 配下）。

```bash
git clone https://github.com/rararapi/llm-watch-feed
cd llm-watch-feed
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # OPENAI_API_KEY を設定（未設定ならダミー要約で動作）
```

```bash
# 収集・分類（OPENAI_API_KEY は任意）
python scripts/collect.py
# RSS 生成
python scripts/generate_feeds.py
# サイト確認（file:// 不可）
cd docs && python -m http.server 8000   # http://localhost:8000
```

入出力先を変える場合（クラウド実行と同じ挙動の確認）:

```bash
MODELS_JSON_PATH=/tmp/out/models.json FEEDS_DIR=/tmp/out/feeds \
  python scripts/collect.py && \
MODELS_JSON_PATH=/tmp/out/models.json FEEDS_DIR=/tmp/out/feeds \
  SITE_URL=https://ai-watch-feed.web.app python scripts/generate_feeds.py
```

## GCP へのデプロイ

構築手順（Cloud Run Job / Scheduler / GCS / Firebase Hosting / Secret Manager）は **[DEPLOY.md](DEPLOY.md)** を参照してください。
コンテナ実行のエントリポイントは `scripts/run_job.sh`（取得 → collect → generate → 保存 → deploy）です。

環境変数（ジョブ）:

| 名前 | 説明 |
| --- | --- |
| `GCS_BUCKET` | 状態 `models.json` を保存する非公開バケット名（必須） |
| `FIREBASE_PROJECT` | デプロイ先 Firebase/GCP プロジェクト ID（必須） |
| `SITE_URL` | 公開サイト URL（フィードの自己リンク用） |
| `OPENAI_API_KEY` | OpenAI API キー（Secret Manager 経由。未設定ならダミーモード） |
| `OPENAI_MODEL` | 分類モデル名（既定 `gpt-4.1-mini`） |
| `MODELS_JSON_PATH` / `FEEDS_DIR` | 入出力先（ジョブ内で `public/` 配下に設定） |

## 公開 RSS フィード

| フィード | パス | 内容 |
| --- | --- | --- |
| All | `/feeds/all.xml` | 重要度 A または B のすべてのモデル情報 |
| Major Models | `/feeds/major-models.xml` | 重要度 A の主要モデル情報 |
| Pricing | `/feeds/pricing.xml` | 価格・コスト関連 |
| Open Models | `/feeds/open-models.xml` | オープンウェイトモデル関連 |
| Coding | `/feeds/coding.xml` | コーディング性能・コード生成モデル関連 |
| Multimodal | `/feeds/multimodal.xml` | マルチモーダル、音声、動画モデル関連 |

公開サイトが `https://ai-watch-feed.web.app` の場合、All フィードは次の URL です。

```text
https://ai-watch-feed.web.app/feeds/all.xml
```

## Power Automate で Teams に通知する

1. Power Automate で新しい自動化クラウドフローを作成
2. トリガーに **RSS フィードに新しいフィード項目が発行されたとき** を選択
3. RSS フィード URL に `/feeds/all.xml` などの絶対 URL を入力
4. アクションに **Microsoft Teams - メッセージを投稿する** を追加
5. メッセージ本文にフィードのタイトル、リンク、概要を配置
6. フローを保存して有効化

## 注意

- `.env` と API キーは絶対にコミットしないでください。クラウドでは Secret Manager を使います。
- `models.json` と `feeds/*.xml` は生成物です。クラウドでは GCS / Firebase に出力され、リポジトリにはコミットしません。
- ローカル確認では `file://` ではなく HTTP サーバーを使ってください。

## 主要ファイル

```text
.
├── scripts/
│   ├── collect.py          # RSS 収集、LLM 判定、models.json 更新
│   ├── generate_feeds.py   # models.json から RSS XML を生成
│   ├── gcs_sync.py         # GCS との状態 download/upload
│   └── run_job.sh          # Cloud Run Job エントリポイント
├── docs/
│   ├── index.html          # 公開画面（Firebase Hosting で配信）
│   └── power-automate.html  # Power Automate 設定ガイド
├── Dockerfile              # Cloud Run Job 用イメージ
├── firebase.json           # Firebase Hosting 設定
├── requirements.txt        # ベース依存
├── requirements-job.txt    # ジョブ追加依存（GCS クライアント）
├── DEPLOY.md               # GCP デプロイ手順
└── README.md
```
