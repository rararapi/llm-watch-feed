# cloud-execution Specification

## Purpose

GCP 上で収集・分析・フィード生成パイプラインをスケジュール実行し、シークレットを安全に注入しつつ、個々のソース・記事の失敗で全体が落ちないよう保護する。

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

### Requirement: シークレットの安全な注入

システムは `OPENAI_API_KEY` を Secret Manager から実行環境にのみ注入 SHALL し、
公開ディレクトリ・フロントエンド・コンテナイメージ・ログのいずれにも平文で出力 SHALL NOT する。

#### Scenario: APIキーが設定されている場合

- **WHEN** Secret Manager に `OPENAI_API_KEY` が登録されジョブに紐付けられている
- **THEN** ジョブ実行時のみ環境変数として参照でき、OpenAI による分析・要約が行われる

#### Scenario: APIキーが未設定の場合（ダミーモード）

- **WHEN** `OPENAI_API_KEY` が注入されていない
- **THEN** ジョブはエラー終了せず、ダミー要約でパイプライン全体を完走する

### Requirement: 障害分離

システムは1ソース・1記事の取得や分析の失敗で実行全体が落ちないよう保護 SHALL し、
処理可能な記事のみを反映してジョブを正常終了 SHALL する。

#### Scenario: 一部ソースが取得失敗する

- **WHEN** RSS ソースの一部が取得・解析に失敗する
- **THEN** 失敗はログに記録され、取得できたソースの記事のみで処理が継続し、ジョブは成功終了する
