# GCP デプロイ手順（公開GCSバケット配信）

**Cloud Run Job + Cloud Scheduler + 公開GCSバケット** 構成の構築手順。
配信は公開GCSバケットが直接担い、**サイトの「デプロイ」は不要**（ニュース更新＝GCSへの書き込み）。

パイプラインは2系統に分離している:

- **ニュース更新（毎日・自動）**: 収集→生成→GCSへ `data/models.json` と `feeds/*.xml` を書き込むだけ
- **サイトデプロイ（変更時のみ・手動/CI）**: `index.html` 等を GCS へ配信（`scripts/deploy_site.sh`）

```
Cloud Scheduler ─毎日─▶ Cloud Run Job (run_job.sh)
   1.GCS→models.json取得  2.collect.py  3.generate_feeds.py
   4.models.json を GCS へ保存(=公開データ)  5.feeds/ を GCS へ配信
        └─ 公開GCSバケット（Web配信ルート）
              ├─ index.html               ← deploy_site.sh で配信（サイト変更時のみ）
              ├─ data/models.json         ← run_job.sh が毎日更新
              └─ feeds/*.xml              ← run_job.sh が毎日更新

独自ドメイン/きれいなURL（後追い）:
   外部 HTTPS ロードバランサ + Cloud CDN + マネージドSSL を公開バケットの前段に置く
        └─ https://news.example.com/feeds/all.xml の形が可能。上のパイプラインは無変更
```

## 前提

- `gcloud` CLI 認証済み・課金有効な GCP プロジェクト
- リポジトリ直下で作業

## 0. 変数

```bash
export PROJECT_ID="your-project-id"
export REGION="asia-northeast1"          # 東京
export BUCKET="${PROJECT_ID}-llm-watch-public"   # 公開配信バケット
export REPO="llm-watch"                   # Artifact Registry リポジトリ
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/collector:latest"
export JOB="llm-watch-collector"
export SA="llm-watch-job"
export SA_EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"
# 当面の公開URL（独自ドメイン設定後はそのURLに変更）
export SITE_URL="https://storage.googleapis.com/${BUCKET}"

gcloud config set project "$PROJECT_ID"
```

## 3.1 API 有効化

```bash
gcloud services enable \
  run.googleapis.com cloudscheduler.googleapis.com \
  aiplatform.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com storage.googleapis.com
```

## 3.2 公開GCSバケット作成 + Web配信設定 + 初期データ投入

```bash
# uniform bucket-level access = ACL無効（IAMで一元管理）
gcloud storage buckets create "gs://${BUCKET}" \
  --location="$REGION" --uniform-bucket-level-access

# 公開読み取りを付与（配信ルートにするため）
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="allUsers" --role="roles/storage.objectViewer"

# Webサイト設定（/ で index.html を返す。404 ページは任意）
gcloud storage buckets update "gs://${BUCKET}" --web-main-page-suffix=index.html

# 既存の収集済みデータを初期状態として引き継ぐ（任意。無ければ初回空開始でよい）
[ -f docs/data/models.json ] && \
  gcloud storage cp docs/data/models.json "gs://${BUCKET}/data/models.json"
```

> models.json / feeds に機密は含まれない（配信前提のデータ）。バケットは公開で問題ない。

## 3.3 LLM（Vertex AI）の利用方針

記事の分析・要約は Vertex AI（Gemini）で行う。**API キーは使わず**、実行サービスアカウントの
ADC（Application Default Credentials）で認証する。権限は次節 3.4 で `roles/aiplatform.user` を付与する。

> `GCP_PROJECT` 未設定や権限不足のままでもジョブはダミーモードで完走する（段階導入可）。

## 3.4 最小権限のサービスアカウント

```bash
gcloud iam service-accounts create "$SA" --display-name="LLM Watch Job"

# GCS: 対象バケットの read/write のみ
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin"

# Vertex AI: 推論呼び出しに必要な最小ロール
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/aiplatform.user"
```

## 4.1 イメージのビルド & push

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION"

# Cloud Build でビルド（ローカル docker 不要）
gcloud builds submit --tag "$IMAGE"
```

## 4.2 Cloud Run Job 作成

```bash
gcloud run jobs create "$JOB" \
  --image="$IMAGE" --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="GCS_BUCKET=${BUCKET},SITE_URL=${SITE_URL},GCP_PROJECT=${PROJECT_ID},VERTEX_LOCATION=${REGION},VERTEX_MODEL=gemini-2.5-flash" \
  --max-retries=1 --task-timeout=600
# 既存更新時は `gcloud run jobs update "$JOB" ...`
```

## 4.3 手動実行で疎通確認

```bash
gcloud run jobs execute "$JOB" --region="$REGION" --wait
# 確認: GCS のデータ更新
gcloud storage cat "gs://${BUCKET}/data/models.json" | head
curl -s "${SITE_URL}/feeds/all.xml" | head
```

## 4.4 Cloud Scheduler（毎日）

Cloud Run Jobs を Run Admin API 経由で起動する HTTP ジョブを作成する。

```bash
# Scheduler が Job を起動するための実行権限
gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/run.invoker"

gcloud scheduler jobs create http "${JOB}-daily" \
  --location="$REGION" \
  --schedule="0 0 * * *" --time-zone="Asia/Tokyo" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB}:run" \
  --http-method=POST \
  --oauth-service-account-email="${SA_EMAIL}"
```
> cron `0 9 * * *` (Asia/Tokyo) にすれば毎日 09:00 JST。

## 5. サイトデプロイ（初回・変更時のみ）

サイトの静的ファイル（`index.html` 等）はニュース更新とは独立して配信する。
**初回に一度実行**し、以降は**サイトの見た目・JS を変更したときだけ**実行すればよい。

```bash
# ローカルから（ADC で認証。bucket への objectAdmin 権限が要る）
gcloud auth application-default login   # 初回のみ
pip install -r requirements-job.txt     # google-cloud-storage を含む
GCS_BUCKET="$BUCKET" ./scripts/deploy_site.sh
```

公開URL: `https://storage.googleapis.com/${BUCKET}/index.html`（HTTPS）。
各フィードは `https://storage.googleapis.com/${BUCKET}/feeds/all.xml` 等。
> CI で自動化する場合は、`docs/` 配下の変更時のみ `deploy_site.sh` を走らせるようにする。

## 6. 独自ドメイン・きれいなURL（後追い）

公開バケットの前段に **外部 HTTPS ロードバランサ + Cloud CDN + マネージドSSL** を置くと、
`https://news.example.com/feeds/all.xml` のようなクリーンなURLで配信できる。
**パイプライン（ニュース更新・サイトデプロイ）は一切変更不要**で、バックエンドが同じ公開バケットを指す。

概略手順:

```bash
# 1) バックエンドバケット（CDN 有効）
gcloud compute backend-buckets create llm-watch-bb \
  --gcs-bucket-name="$BUCKET" --enable-cdn

# 2) URL マップ → ターゲット HTTPS プロキシ → グローバル転送ルール（IP 確保）
gcloud compute url-maps create llm-watch-lb --default-backend-bucket=llm-watch-bb
gcloud compute addresses create llm-watch-ip --global

# 3) マネージドSSL証明書（取得済みドメインを指定）
gcloud compute ssl-certificates create llm-watch-cert \
  --domains="news.example.com" --global
gcloud compute target-https-proxies create llm-watch-proxy \
  --url-map=llm-watch-lb --ssl-certificates=llm-watch-cert
gcloud compute forwarding-rules create llm-watch-fr \
  --global --target-https-proxy=llm-watch-proxy \
  --address=llm-watch-ip --ports=443

# 4) 確保した IP を取得し、ドメインの A レコードに設定 → 証明書 PROVISIONING 完了を待つ
gcloud compute addresses describe llm-watch-ip --global --format='value(address)'
```

ドメイン稼働後:

```bash
# フィードの自己リンクを独自ドメインに合わせて更新（次回のニュース更新で反映される）
gcloud run jobs update "$JOB" --region="$REGION" \
  --update-env-vars="SITE_URL=https://news.example.com"
```

> ロードバランサは月額の最低料金が発生する（転送ルール課金）。ドメイン公開が必要になるまでは
> 当面 `storage.googleapis.com/<bucket>/...` の直URLで運用してよい（HTTPSで配信される）。

## 7. セキュリティ検収

```bash
# 公開物にキーが無いこと
curl -s "${SITE_URL}/data/models.json" | grep -i "sk-" || echo "no key in models.json ✓"
# Run ログにキー平文が出ていないこと
gcloud logging read "resource.type=cloud_run_job AND textPayload:sk-" --limit=5 --project "$PROJECT_ID"
```

## 8. 旧 Firebase 構成からの移行

旧構成（Firebase Hosting + 非公開状態バケット）から移る場合:

1. 旧状態バケットの `models.json` を新公開バケットの `data/models.json` へコピー
   （`gcloud storage cp gs://OLD/models.json gs://${BUCKET}/data/models.json`）。
2. 本手順でジョブ・スケジューラを更新（`FIREBASE_PROJECT` 環境変数は不要・削除）。
3. `deploy_site.sh` でサイトを初回配信。
4. 数サイクル安定確認後、旧 Firebase Hosting サイトと旧スケジューラを停止。
   旧URLには新URL（バケット or 独自ドメイン）への案内を残すとよい。

## ロールバック

`gcloud scheduler jobs pause "${JOB}-daily" --location="$REGION"` で毎日更新を停止できる。
状態の正本は `gs://${BUCKET}/data/models.json` なので、必要ならその時点のJSONを差し替える。
