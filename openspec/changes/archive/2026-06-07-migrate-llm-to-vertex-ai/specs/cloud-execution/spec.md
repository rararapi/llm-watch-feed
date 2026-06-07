# cloud-execution Specification (delta)

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: シークレットの安全な注入

**Reason**: 記事分析を OpenAI API から Vertex AI（ADC 認証）へ移行し、`OPENAI_API_KEY` を
Secret Manager で注入する運用そのものが不要になったため。

**Migration**: Secret Manager の `OPENAI_API_KEY` および環境変数 `OPENAI_API_KEY` / `OPENAI_MODEL`
を廃止する。代わりに Cloud Run Job のサービスアカウントに `roles/aiplatform.user` を付与し、
環境変数 `GCP_PROJECT` / `VERTEX_LOCATION` / `VERTEX_MODEL` を設定する。ダミーモードへの
フォールバック挙動は新要件「LLM（Vertex AI）の安全な利用」が引き継ぐ。
