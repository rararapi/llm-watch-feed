# GCP デプロイ手順（deploy-to-gcp）

案①: **Cloud Run Job + Cloud Scheduler + GCS(非公開) + Firebase Hosting** 構成の構築手順。
収集→生成→GCS保存→Firebase配信を毎日自動実行する。状態 `models.json` の正本は GCS、一般配信は Firebase に一本化する。

```
Cloud Scheduler ─毎日─▶ Cloud Run Job (このリポジトリのコンテナ)
   1.GCS→models.json取得  2.collect.py  3.generate_feeds.py
   4.GCS→models.json保存(正本)  5.Firebase Hosting へデプロイ
        └─ 公開: https://<project>.web.app （独自ドメインは後追いで追加可）
```

## 前提

- `gcloud` CLI 認証済み・課金有効な GCP プロジェクト
- `firebase-tools`（ローカル初期化用。ジョブ内ではコンテナに同梱済み）
- リポジトリ直下で作業

## 0. 変数

```bash
export PROJECT_ID="your-project-id"
export REGION="asia-northeast1"          # 東京
export BUCKET="${PROJECT_ID}-llm-watch-state"
export REPO="llm-watch"                   # Artifact Registry リポジトリ
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/collector:latest"
export JOB="llm-watch-collector"
export SA="llm-watch-job"
export SA_EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"
export SITE_URL="https://${PROJECT_ID}.web.app"   # 独自ドメイン取得後はそのURLに変更

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

## 3.2 GCS バケット（非公開）作成 + 初期状態アップロード

```bash
# uniform bucket-level access = ACL無効。公開アクセスは付与しない（非公開）。
gcloud storage buckets create "gs://${BUCKET}" \
  --location="$REGION" --uniform-bucket-level-access \
  --public-access-prevention

# 既存の収集済みデータを初期状態として引き継ぐ（任意。無ければ初回空開始でよい）
gcloud storage cp docs/data/models.json "gs://${BUCKET}/models.json"
```

## 3.3 LLM（Vertex AI）の利用方針

記事の分析・要約は Vertex AI（Gemini）で行う。**API キーは使わず**、実行サービスアカウントの
ADC（Application Default Credentials）で認証する。よってここで登録するシークレットは無い。
権限は次節 3.4 でサービスアカウントに `roles/aiplatform.user` を付与して与える。

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

# Firebase Hosting デプロイ権限（ジョブ内 firebase deploy が ADC で使用）
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/firebasehosting.admin"
# firebase-tools が ADC でプロジェクトを解決するために必要
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/serviceusage.serviceUsageConsumer"
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
  --set-env-vars="GCS_BUCKET=${BUCKET},FIREBASE_PROJECT=${PROJECT_ID},SITE_URL=${SITE_URL},GCP_PROJECT=${PROJECT_ID},VERTEX_LOCATION=${REGION},VERTEX_MODEL=gemini-2.5-flash" \
  --max-retries=1 --task-timeout=600
# 既存更新時は `gcloud run jobs update "$JOB" ...`
```

## 4.3 手動実行で疎通確認

```bash
gcloud run jobs execute "$JOB" --region="$REGION" --wait
# 確認: GCS の models.json 更新、Firebase 公開
gcloud storage cat "gs://${BUCKET}/models.json" | head
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
> cron `0 0 * * *` (Asia/Tokyo) = 毎日 09:00 JST 相当に揃える場合は `--schedule="0 9 * * *"` に調整。

## 5. Firebase Hosting（既定ドメインで稼働開始）

初回のみローカルで Hosting サイトを有効化する（`firebase.json` は本リポジトリに同梱済み）。

```bash
firebase login
firebase projects:addfirebase "$PROJECT_ID"   # 既にFirebase化済みなら不要
firebase hosting:sites:list --project "$PROJECT_ID"
```
以降の通常デプロイはジョブ(`run_job.sh` の step5)が自動実行する。
公開URL: `https://${PROJECT_ID}.web.app`（HTTPS）。サイト・各フィードURLにアクセスして確認する。

### 5.5/5.6 独自ドメイン（任意・後追い）

1. ドメインを取得し DNS を管理下に置く。
2. `firebase hosting:sites` のサイトに対し Firebase コンソール / CLI でカスタムドメインを追加し、提示される
   DNS レコードを設定 → 証明書自動発行を待つ。
3. `SITE_URL` を独自ドメインに更新し、`gcloud run jobs update "$JOB" --set-env-vars=SITE_URL=...` で反映。

## 5.9 ローカルから Vertex AI を呼ぶ（開発時）

ローカル実行でも本番と同じ ADC で Gemini を叩ける。初回のみ認証し、`GCP_PROJECT` を渡す。

```bash
gcloud auth application-default login          # 一度だけ。ブラウザで認証
export GCP_PROJECT="$PROJECT_ID"               # .env に GCP_PROJECT=... でも可
# 任意: export VERTEX_LOCATION=us-central1  VERTEX_MODEL=gemini-2.5-flash
python scripts/collect.py                      # ログに "Using Vertex AI model: ..." が出れば成功
```
> `GCP_PROJECT` を渡さなければダミーモードで動く（認証不要）。ログイン中のアカウントにも
> プロジェクトでの `roles/aiplatform.user` 相当の権限が必要。`aiplatform.googleapis.com` が
> 未有効だと呼び出しが弾かれるため、3.1 の API 有効化を先に済ませておく。

## 6. セキュリティ検収

```bash
# 公開物にキーが無いこと（デプロイ済み公開ファイルを取得して確認）
curl -s "${SITE_URL}/data/models.json" | grep -i "sk-" || echo "no key in models.json ✓"
# Run ログにキー平文が出ていないこと
gcloud logging read "resource.type=cloud_run_job AND textPayload:sk-" --limit=5 --project "$PROJECT_ID"
```

## 7. 旧構成の撤去（数サイクル並行運用で安定確認後）

- `.github/workflows/collect.yml` を撤去（または手動実行用に縮小）
- GitHub Pages を停止（必要なら旧URLに新フィードURLの案内を残す）
- `README.md` / `CLAUDE.md` の実行・配信手順を GCP 構成へ更新

## ロールバック

移行完了までは GitHub Actions + Pages を残す。問題時は `gcloud scheduler jobs pause "${JOB}-daily" --location="$REGION"` で停止し旧構成へ戻す。
GCS の `models.json` が正本のため、旧構成へ戻す場合はその時点の JSON を `docs/data/models.json` に戻して commit する。
