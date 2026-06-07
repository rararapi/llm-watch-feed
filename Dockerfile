# Cloud Run Job 用イメージ。
# Python(収集・生成・GCS同期) + Node/firebase-tools(Hosting デプロイ) を同梱する。
FROM python:3.12-slim

# Node.js と firebase-tools（Hosting デプロイ手段: design Decision 4 案a）
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g firebase-tools \
 && apt-get purge -y gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-job.txt ./
RUN pip install --no-cache-dir -r requirements-job.txt

COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY firebase.json ./
RUN chmod +x scripts/run_job.sh

ENTRYPOINT ["scripts/run_job.sh"]
