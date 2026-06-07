## Context

記事の収集・分析・配信パイプラインは GCP（Cloud Run Job + Cloud Scheduler + GCS + Firebase Hosting）へ移行済みだが、分析・要約だけは外部の OpenAI API（`openai` SDK / Chat Completions、`OPENAI_API_KEY` を Secret Manager 注入）に依存している。現行実装は `scripts/collect.py` の `analyze()` で `client.chat.completions.create(..., response_format={"type":"json_object"})` を呼び、`OPENAI_API_KEY` 未設定時は `dummy_analysis()` にフォールバックする。

本変更は、この LLM 呼び出しを GCP 内の Vertex AI（Gemini）へ寄せ、認証を Application Default Credentials（ADC）に切り替える。出力スキーマ（`is_model_related`/`model_type`/`importance` 等）と `SYSTEM_PROMPT` は据え置き、差し替えは LLM クライアントの初期化・呼び出し・依存・環境変数に限定する。

## Goals / Non-Goals

**Goals:**
- 分析・要約を Vertex AI（Gemini, 既定 `gemini-2.5-flash`）で実行する。
- 認証を ADC（Cloud Run のサービスアカウント）に統一し、LLM 用の API キー／シークレットを廃止する。
- 「LLM を使えない場合はダミー要約で完走」というフォールバックを維持する（判定軸を「キーの有無」から「Vertex 構成・認証の利用可否」へ一般化）。
- 外部依存の差し替えを最小限（`openai` 除去、`google-cloud-aiplatform` 追加）にする。

**Non-Goals:**
- スコープ拡大に伴う一般化（`is_model_related`、`models.json` リネーム、分類・タグの一般化）。
- プロンプト本文・出力 JSON スキーマの変更。
- Cloud Scheduler / GCS / Firebase Hosting の構成変更。
- ローカル開発での `gcloud auth application-default login` 手順の自動化（手順は DEPLOY.md に記載するに留める）。

## Decisions

### 決定1: Vertex AI + ADC を採用（Gemini API キー方式は不採用）

- **採用**: Vertex AI SDK（`google-cloud-aiplatform`）+ ADC。Cloud Run のサービスアカウントに `roles/aiplatform.user` を付与し、鍵を持たない。
- **理由**: 配信基盤が GCP に一本化済みで、サービスアカウント認証なら Secret Manager の鍵運用・ローテーション・漏洩リスクが消える。IAM で権限を一元管理できる。
- **代替案 (Gemini API / AI Studio + `GEMINI_API_KEY`)**: 現行のキー注入パターンを流用でき差分は小さいが、結局シークレット運用が残り GCP の IAM に乗らない。本変更の主目的（外部キー依存の排除）に反するため不採用。

### 決定2: 依存は `google-cloud-aiplatform` のみ追加、`openai` は除去

- **理由**: 「外部依存を安易に増やさない」方針に沿い、SDK 差し替えで純増を避ける。Vertex AI 公式 SDK は構造化出力（`response_mime_type="application/json"`）に対応し、現行の JSON 強制と等価に置換できる。
- **トレードオフ**: `google-cloud-aiplatform` は比較的重い依存だが、GCP 上での実行が前提のため許容する（design ルールに従い明記）。

### 決定3: 利用可否の判定とフォールバック

- `GCP_PROJECT`（必須）と `VERTEX_LOCATION`（既定 `us-central1` 等）が設定され、ADC が取得できれば LLM モード。いずれか欠ける／初期化・呼び出しが例外なら `dummy_analysis()` にフォールバック。
- `analyze()` 内の `try/except` は現状どおり維持し、1 記事の失敗で全体を落とさない（障害分離要件）。
- **理由**: ダミーモードを維持することで、認証未整備のローカル環境や権限未付与時でもパイプラインが完走し、「動いて届く」現フェーズ目的を守る。

### 決定4: 環境変数の置き換え

| 旧 | 新 | 備考 |
|----|----|------|
| `OPENAI_API_KEY` | （廃止） | ADC 認証に置換 |
| `OPENAI_MODEL`（既定 `gpt-4.1-mini`） | `VERTEX_MODEL`（既定 `gemini-2.5-flash`） | モデル名 |
| — | `GCP_PROJECT` | Vertex 初期化に必須 |
| — | `VERTEX_LOCATION`（既定例 `us-central1`） | リージョン |

`CLAUDE.md` の環境変数表・`DEPLOY.md`・`run_job.sh`／ジョブ定義の env を更新する。

## Risks / Trade-offs

- [サービスアカウントに Vertex 権限が無く本番で全件ダミー化] → デプロイ手順に `roles/aiplatform.user` 付与を明記し、初回実行ログでモード（LLM/ダミー）を出力して気づけるようにする。
- [Gemini の JSON 構造化出力が OpenAI と微妙に異なり parse 失敗] → `response_mime_type="application/json"` を指定し、既存の `json.JSONDecodeError` ハンドリングでスキップ（落とさない）。必要なら出力から ```json フェンス等を除去する軽い後処理を入れる。
- [モデル名・リージョンの非対応値で初期化失敗] → 既定値を用意し、例外時はダミーモードへフォールバック。
- [ローカル開発で ADC 未設定だと常にダミー] → DEPLOY.md にローカルでの `gcloud auth application-default login` と `GCP_PROJECT` 設定手順を記載。
- [依存差し替えによる requirements の肥大化] → `openai` を除去して純増を抑える。

## Migration Plan

1. `requirements.txt` を更新（`openai` 除去、`google-cloud-aiplatform` 追加）。
2. `scripts/collect.py` の LLM 初期化・`analyze()` を Vertex AI 実装へ置換。`dummy_analysis()`・出力スキーマ・`SYSTEM_PROMPT` は不変。
3. 環境変数を `GCP_PROJECT`/`VERTEX_LOCATION`/`VERTEX_MODEL` に置換し、`run_job.sh`・ジョブ定義・`CLAUDE.md`・`DEPLOY.md` を更新。
4. Cloud Run Job のサービスアカウントに `roles/aiplatform.user` を付与。Secret Manager の `OPENAI_API_KEY` 紐付けを外す。
5. ローカルでダミーモード（ADC 無し）と LLM モード（ADC 有り）の両方を確認 → デプロイ。
- **ロールバック**: 本変更を revert し `requirements.txt`・`collect.py`・env を戻す。`OPENAI_API_KEY` を Secret Manager に再注入すれば旧構成に復帰可能（状態 `models.json` のスキーマは不変のため互換）。

## Open Questions

- 既定リージョン（`VERTEX_LOCATION`）をどこにするか（コスト・モデル提供状況で決定。`us-central1` を仮置き）。
- 既定モデルを `gemini-2.5-flash` とするか、より安価/上位のモデルにするか（コストと要約品質のバランス）。
