# cloud-execution Specification

## Purpose

GCP 上で収集・分析・フィード生成パイプラインをスケジュール実行し、分析・要約に Vertex AI（Gemini）を ADC で安全に利用しつつ、個々のソース・記事の失敗で全体が落ちないよう保護する。

## Requirements

### Requirement: スケジュール実行

システムは収集・フィード生成処理を GCP 上でスケジュール実行 SHALL する。
実行は Cloud Run Job 1 回の起動で `collect.py` → `generate_feeds.py` の順に行われ、
Cloud Scheduler が毎日の cron でこれを発火 SHALL する。

#### Scenario: 定時にジョブが起動する

- **WHEN** Cloud Scheduler の毎日の cron 時刻に到達する
- **THEN** Cloud Run Job が1回起動し、収集→分析→フィード生成が順に実行される

#### Scenario: 手動実行できる

- **WHEN** 運用者が Cloud Run Job を手動でトリガーする
- **THEN** スケジュール実行と同じ処理が1回実行される

### Requirement: LLM（Vertex AI）の安全な利用

システムは記事の分析・要約に GCP の Vertex AI（Gemini）を利用 SHALL し、認証は実行環境の
Application Default Credentials（Cloud Run Job のサービスアカウント）で行う。API キー等の
シークレットを保持・注入 SHALL NOT し、公開ディレクトリ・フロントエンド・コンテナイメージ・
ログのいずれにも認証情報や機密を平文で出力 SHALL NOT する。Vertex AI を利用できない場合
（構成未設定・認証不可・呼び出しエラー）は、ジョブをエラー終了させず、ダミー要約で
パイプライン全体を完走 SHALL する。

#### Scenario: Vertex AI が利用可能な場合

- **WHEN** `GCP_PROJECT` / `VERTEX_LOCATION` が設定され、実行環境のサービスアカウントに
  Vertex AI 利用権限（`roles/aiplatform.user`）が付与されている
- **THEN** ジョブ実行時に ADC で認証され、Vertex AI（Gemini）による分析・要約が行われる

#### Scenario: Vertex AI 構成が未設定の場合（ダミーモード）

- **WHEN** `GCP_PROJECT` 等の Vertex AI 構成が設定されていない、または認証情報が取得できない
- **THEN** ジョブはエラー終了せず、ダミー要約でパイプライン全体を完走する

#### Scenario: 認証情報が外部に露出しない

- **WHEN** ジョブが実行され、成果物（`docs/`/`public/` 配下）とログが生成される
- **THEN** 認証情報・サービスアカウント鍵その他の機密は一切含まれない

### Requirement: 障害分離

システムは1ソース・1記事の取得や分析の失敗で実行全体が落ちないよう保護 SHALL し、
処理可能な記事のみを反映してジョブを正常終了 SHALL する。

#### Scenario: 一部ソースが取得失敗する

- **WHEN** RSS ソースの一部が取得・解析に失敗する
- **THEN** 失敗はログに記録され、取得できたソースの記事のみで処理が継続し、ジョブは成功終了する
