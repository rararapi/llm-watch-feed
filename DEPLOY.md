# GCP デプロイ手順（方式A: Firebase Hosting + 公開GCSデータ）

構成は **方式A**:

- **画面全体（index/subscribe/articles/assets）** … Firebase Hosting が配信（無料HTTPS、`*.web.app`、独自ドメイン可）。Cloud Run Job が日次デプロイ（`firebase_hosting_deploy.py` 経由）
- **データ(`data/models.json`)・RSS(`feeds/*.xml`)・AI画像(`images/*.webp`)** … 公開GCSバケットが配信（Storage はデータのみ）
- **ニュース更新** … Cloud Run Job が GCS（data/feeds/images）＋ Firebase Hosting（画面）へ書き込む

```
Cloud Scheduler ─毎日─▶ Cloud Run Job (run_job.sh)
   1.GCS→models.json取得  2.collect.py  3.generate_images.py  4.generate_feeds.py  5.generate_pages.py
   6.data/models.json をGCSへ保存  7.feeds/ をGCSへ配信  8.サイト(index/articles/assets)をFirebase Hostingへデプロイ
        └─ 公開GCSバケット（data/ + feeds/ + images/ をHTTPS配信, CORS有効）
           AI画像は generate_images.py が images/<id>.webp へ直接アップロード（不変キャッシュ・重要度A）

Firebase Hosting（firebase_hosting_deploy.py が日次デプロイ）
   ├─ index.html / subscribe.html / articles/<id>.html / assets / power-automate.html
   └─ 公開URL: https://ai-watch-feed.web.app （独自ドメインは無料で接続可）
```

> 記事ページのOGP/共有URL: SNSクローラはJSを実行しないため、個別記事ページは generate_pages.py が
> OGP/Twitter Card/JSON-LD を焼き込んだ**静的HTML**として事前生成し、Firebase Hosting へ日次デプロイする。
> 共有URL・`og:url`・canonical は Firebase Hosting の URL（`https://ai-watch-feed.web.app/articles/<id>.html`）。
>
> 実クローラ検証（X Card Validator / Slack unfurl 等）は**デプロイ後の Firebase 公開URL**に対して行うこと。

## 前提

- `gcloud` CLI 認証済み・課金有効な GCP プロジェクト
- `firebase` CLI 認証済み（`firebase login`。Firebase Hosting デプロイ用）
- リポジトリ直下で作業

## 0. 変数

```bash
export PROJECT_ID="ai-watch-feed"
export REGION="asia-northeast1"          # 東京
export BUCKET="${PROJECT_ID}-llm-watch-public"   # データ/フィード配信バケット
export REPO="llm-watch"                   # Artifact Registry リポジトリ
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/collector:latest"
export JOB="llm-watch-collector"
export SA="llm-watch-job"
export SA_EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"
# フィードの自己リンク用。フィードはGCSにあるのでバケットURLを指す
export SITE_URL="https://ai-watch-feed.web.app"
export FIREBASE_SITE_ID="ai-watch-feed"

gcloud config set project "$PROJECT_ID"
```

## 3.1 API 有効化

```bash
gcloud services enable \
  run.googleapis.com cloudscheduler.googleapis.com \
  aiplatform.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com storage.googleapis.com \
  firebasehosting.googleapis.com
```

## 3.2 公開GCSバケット作成 + 公開読み取り + CORS + 初期データ投入

```bash
gcloud storage buckets create "gs://${BUCKET}" \
  --location="$REGION" --uniform-bucket-level-access

# 公開読み取り（データ/フィードを配信する）
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="allUsers" --role="roles/storage.objectViewer"

# CORS: Firebase配信のJSがクロスオリジンで data/feeds を fetch できるようにする
cat > /tmp/cors.json <<'JSON'
[{"origin":["*"],"method":["GET","HEAD"],"responseHeader":["Content-Type"],"maxAgeSeconds":3600}]
JSON
gcloud storage buckets update "gs://${BUCKET}" --cors-file=/tmp/cors.json

# 既存の収集済みデータを初期状態として引き継ぐ（任意）
[ -f docs/data/models.json ] && \
  gcloud storage cp docs/data/models.json "gs://${BUCKET}/data/models.json"
```

> data/feeds に機密は含まれない（配信前提のデータ）。

## 3.3 LLM（Vertex AI）の利用方針

記事の分析・要約は Vertex AI（Gemini）で行う。**API キーは使わず**、実行サービスアカウントの
ADC で認証する。権限は次節 3.4 で `roles/aiplatform.user` を付与する。
`GCP_PROJECT` 未設定や権限不足のままでもジョブはダミーモードで完走する。

## 3.4 最小権限のサービスアカウント

```bash
gcloud iam service-accounts create "$SA" --display-name="LLM Watch Job"

# GCS: 対象バケットの read/write のみ
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin"

# Vertex AI: 推論呼び出しに必要な最小ロール
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/aiplatform.user"

# Firebase Hosting: 日次デプロイ（firebase_hosting_deploy.py）に必要
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/firebasehosting.admin"
```

## 4.1 イメージのビルド & push

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION"

gcloud builds submit --tag "$IMAGE"
```

## 4.2 Cloud Run Job 作成

```bash
gcloud run jobs create "$JOB" \
  --image="$IMAGE" --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="GCS_BUCKET=${BUCKET},SITE_URL=${SITE_URL},FEEDS_BASE_URL=https://storage.googleapis.com/${BUCKET},FIREBASE_SITE_ID=${FIREBASE_SITE_ID},GCP_PROJECT=${PROJECT_ID},VERTEX_LOCATION=us-central1,VERTEX_MODEL=gemini-2.5-flash,VERTEX_IMAGE_MODEL=gemini-2.5-flash-image,IMAGE_MIN_IMPORTANCE=A,IMAGE_MAX_PER_RUN=5" \
  --max-retries=1 --task-timeout=1800
# 既存更新時は `gcloud run jobs update "$JOB" ...`（FIREBASE_PROJECT は使わない）
# AI画像生成は GCS_BUCKET（公開バケット）と roles/aiplatform.user で動作。images/<id>.webp に
# 不変キャッシュ付きで配信され、image_generated_url 経由でサムネ表示される（AI画像→OG画像→プレースホルダ）。
# 画像モデルは分間クォータ(429)で律速されることがあるため task-timeout は余裕を持たせる。
# VERTEX_IMAGE_MODEL が使えない/未設定なら画像なしで完走する。
```

## 4.3 手動実行で疎通確認

```bash
gcloud run jobs execute "$JOB" --region="$REGION" --wait
gcloud storage cat "gs://${BUCKET}/data/models.json" | head
curl -s "${SITE_URL}/feeds/all.xml" | head
```

## 4.4 Cloud Scheduler（毎日）

```bash
gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/run.invoker"

gcloud scheduler jobs create http "${JOB}-daily" \
  --location="$REGION" \
  --schedule="0 9 * * *" --time-zone="Asia/Tokyo" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB}:run" \
  --http-method=POST \
  --oauth-service-account-email="${SA_EMAIL}"
```

## 5. サイト（画面）デプロイ — Firebase Hosting（初回・変更時のみ）

画面（`docs/index.html` / `docs/subscribe.html` / `docs/assets/` と手書きの `docs/power-automate.html`）を
Firebase Hosting へデプロイする。`deploy_site.sh` は **`generate_pages.py` で画面を `docs/` に再生成してから**
`firebase deploy` する（テンプレ/CSS/JS を最新化）。ニュース更新とは独立で、**テンプレ/デザインを変更したときだけ**実行する。

```bash
firebase login        # 初回のみ（ブラウザ認証）
firebase hosting:sites:list --project "$PROJECT_ID"   # サイト確認
GCS_BUCKET="$BUCKET" ./scripts/deploy_site.sh         # 最新 models.json を取得→画面再生成→firebase deploy
```

公開URL: `https://ai-watch-feed.web.app`（HTTPS）。
Cloud Run Job が日次で `firebase_hosting_deploy.py` を呼び出し、index.html・articles・assets を Firebase へデプロイするため、
手動デプロイは初回確認または緊急時のみ。バケット名やドメインを変えた場合は `SITE_URL` を更新して再生成・再デプロイする。

## 6. 独自ドメイン（任意・無料）

Firebase Hosting に独自ドメインを**無料で接続**できる（HTTPS証明書も自動・無料）。
ただしドメイン自体の取得（レジストラでの登録・年額）は別途必要。

1. ドメインを取得し DNS を管理下に置く。
2. Firebase コンソール → Hosting → 「カスタムドメインを追加」、または
   `firebase hosting:channel` 系/コンソールで対象ドメインを追加。
3. 提示される TXT/A レコードを DNS に設定 → 証明書自動発行を待つ。

> これで**画面のURL**が独自ドメインになる。**フィードURLは GCS のまま**（`storage.googleapis.com/...`）。
> フィードURLも独自ドメインにしたい場合は有料の方式B（外部HTTPSロードバランサ+Cloud CDN で
> 公開バケットを前段配信、または Cloud Run/Functions で rewrite）が必要。

## 7. セキュリティ検収

```bash
# GCS の models.json にキーが含まれていないこと
gcloud storage cat "gs://${BUCKET}/data/models.json" | python -m json.tool | grep -i "sk-" || echo "no key ✓"
gcloud logging read "resource.type=cloud_run_job AND textPayload:sk-" --limit=5 --project "$PROJECT_ID"
# CORS が効いていること（Firebase JS から GCS data/feeds を fetch するため）
curl -s -D - -o /dev/null -H "Origin: ${SITE_URL}" \
  "https://storage.googleapis.com/${BUCKET}/data/models.json" | grep -i "access-control-allow-origin"
# Firebase Hosting にサイトが配信されていること
curl -s "${SITE_URL}/" | grep "<title>"
```

## 9. CI 自動デプロイ（main マージで自動・GitHub Actions + WIF）

`main` にマージ（push）されると `.github/workflows/deploy.yml` が走り、**Cloud Run Job** のイメージを再ビルド・更新する。

- `scripts/**` / `Dockerfile` / `requirements*.txt` / `templates/**` / `assets/**` / `docs/**` の変更 → **Cloud Run Job** のイメージを再ビルドしてジョブを更新

> Firebase Hosting へのデプロイは Cloud Run Job（`firebase_hosting_deploy.py`）が日次で行うため、
> GitHub Actions から Firebase へのデプロイは不要。テンプレート/デザイン変更は次回日次実行（最大24時間後）に反映される。

認証は **Workload Identity Federation（鍵レス）**。SA の JSON キーは保存しない。以下は初回のみの準備。

### 9.1 変数

```bash
export PROJECT_ID="ai-watch-feed"
export GH_REPO="rararapi/llm-watch-feed"      # owner/repo
export POOL="github"
export PROVIDER="github"
export DEPLOY_SA="gha-deployer"
export DEPLOY_SA_EMAIL="${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud config set project "$PROJECT_ID"
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com
```

### 9.2 デプロイ用サービスアカウント + 権限

```bash
gcloud iam service-accounts create "$DEPLOY_SA" --display-name="GitHub Actions Deployer"

# Firebase Hosting デプロイ
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/firebasehosting.admin"
# firebase CLI のプロジェクト解決に必要
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/serviceusage.serviceUsageConsumer"

# Cloud Build でイメージをビルド/プッシュ
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/cloudbuild.builds.editor"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/artifactregistry.writer"
# gcloud builds submit のソースアップロード先（ステージングバケット）
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/storage.admin"

# Cloud Run Job の更新
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/run.developer"
# ジョブが使うランタイム SA を指定できるように（actAs）
gcloud iam service-accounts add-iam-policy-binding \
  "llm-watch-job@${PROJECT_ID}.iam.gserviceaccount.com" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/iam.serviceAccountUser"
```

### 9.3 Workload Identity Pool / Provider（GitHub 連携）

```bash
gcloud iam workload-identity-pools create "$POOL" \
  --location="global" --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location="global" --workload-identity-pool="$POOL" \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GH_REPO}'"

# このリポジトリからのトークンだけが DEPLOY_SA を借用できるよう束縛
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GH_REPO}"
```

### 9.4 GitHub Secrets を設定

```bash
# Provider のリソース名（GCP_WIF_PROVIDER に入れる値）
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"

# gh CLI があればそのまま登録できる
gh secret set GCP_WIF_PROVIDER --repo "$GH_REPO" \
  --body "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"
gh secret set GCP_DEPLOY_SA --repo "$GH_REPO" --body "$DEPLOY_SA_EMAIL"
```

| Secret | 値 |
|--------|----|
| `GCP_WIF_PROVIDER` | `projects/<番号>/locations/global/workloadIdentityPools/github/providers/github` |
| `GCP_DEPLOY_SA` | `gha-deployer@ai-watch-feed.iam.gserviceaccount.com` |

> 設定後、`main` への次回マージから自動デプロイが有効になる。手動デプロイ（`deploy_site.sh` /
> `gcloud builds submit`）も引き続き使える。動作確認は GitHub の Actions タブを見る。

## ロールバック

`gcloud scheduler jobs pause "${JOB}-daily" --location="$REGION"` で毎日更新を停止できる。
状態の正本は `gs://${BUCKET}/data/models.json`。画面は直前の Firebase リリースへロールバック可能
（Firebase コンソール → Hosting → リリース履歴）。
