# Cloud Run Job 用イメージ（ニュース更新ジョブ）。
# Python(収集・生成・GCS同期) のみ。配信は公開GCSバケットが直接担うため
# Firebase Hosting / firebase-tools / Node は不要。
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-job.txt ./
RUN pip install --no-cache-dir -r requirements-job.txt

COPY scripts/ ./scripts/
COPY docs/ ./docs/
RUN chmod +x scripts/run_job.sh scripts/deploy_site.sh

ENTRYPOINT ["scripts/run_job.sh"]
