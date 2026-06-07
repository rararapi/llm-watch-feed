## Why

配信基盤は GCP（Cloud Run Job + GCS + Firebase Hosting）に一本化済みだが、記事の分析・要約だけは外部の OpenAI API に依存しており、`OPENAI_API_KEY` を Secret Manager で運用する必要がある。LLM 呼び出しも GCP 内（Vertex AI / Gemini）で完結させ、Application Default Credentials（ADC）による認証に切り替えることで、外部APIキー依存と障害点を減らし、現フェーズの目的である「サイトが安定して動き、更新がRSSで届く」状態に寄与する。

## What Changes

- `scripts/collect.py` の分析・要約を OpenAI（`openai` SDK / Chat Completions）から **Vertex AI（Gemini, 例: `gemini-2.5-flash`）** に置き換える。
- 認証を **ADC（Cloud Run のサービスアカウント）** ベースにし、`OPENAI_API_KEY` の Secret Manager 注入を廃止する。**BREAKING**: 環境変数 `OPENAI_API_KEY` / `OPENAI_MODEL` は廃止し、`GCP_PROJECT` / `VERTEX_LOCATION` / `VERTEX_MODEL`（仮称）に置き換える。
- 既存のフォールバック挙動（LLM を利用できない場合はダミー要約でパイプライン全体を完走）は維持する。判定条件を「APIキーの有無」から「Vertex 構成・認証の利用可否」に一般化する。
- 依存を `openai` から `google-cloud-aiplatform`（Vertex AI SDK）へ差し替える（`requirements.txt`）。
- JSON 構造化出力（現状 `response_format={"type":"json_object"}`）を Gemini 側の同等機能（`response_mime_type="application/json"` 等）に置き換える。プロンプト本文・出力スキーマ自体は変更しない。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `cloud-execution`: 「シークレットの安全な注入」要件を見直す。OpenAI APIキー前提の注入から、**Vertex AI を ADC で利用する構成**（プロジェクト/リージョン/サービスアカウントのIAM）へ要件を変更し、利用可否に応じてダミーモードへフォールバックする挙動を維持する。

## Impact

- コード: `scripts/collect.py`（`analyze()` と `main()` の LLM 初期化・呼び出し）。
- 依存: `requirements.txt` — `openai` を除去、`google-cloud-aiplatform` を追加。
- 設定・運用: Cloud Run Job のサービスアカウントに Vertex AI 利用権限（`roles/aiplatform.user`）が必要。`DEPLOY.md` と環境変数表（`CLAUDE.md`）の更新。Secret Manager の `OPENAI_API_KEY` は不要になる。
- spec: `openspec/specs/cloud-execution/spec.md` の「シークレットの安全な注入」要件。
- Non-goals（今回やらないこと）:
  - スコープ拡大に伴う一般化（`is_model_related` 判定、`models.json` リネーム、分類・タグの一般化）。
  - プロンプト内容・出力スキーマ（`model_type`/`importance` 等）の変更。
  - Cloud Scheduler / GCS / Firebase Hosting の構成変更。
