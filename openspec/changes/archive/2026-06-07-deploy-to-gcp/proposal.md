## Why

最優先目的は「**まずサイトをクラウド上で稼働させ、更新時にRSSで通知を受け取れる状態にする**」こと。
ホスティング先は GCP に確定したため、GitHub Pages 前提・収集結果を git にコミットして保存する現構成を、
GCP 上の最小構成へ載せ替える。実体は「常駐サーバの無い静的生成パイプライン」なので、
**保存先・実行場所・配信先の3点を差し替えるだけ**で GCP に移せる。凝った機能は足さず「GCP で動いて届く」ことだけを狙う。

## What Changes

- **実行**: GitHub Actions cron を **Cloud Run Job** に置き換える。`collect.py` → `generate_feeds.py` を1回の実行で回す。
- **トリガー**: **Cloud Scheduler** で **毎日** cron 発火する（現行の火・金から毎日へ変更）。
- **状態保存**: `docs/data/models.json` を git にコミットする方式をやめ、**GCS バケット上の `models.json`** に永続化する。
  ジョブは起動時に GCS から取得 → 更新 → 保存する（**download-run-upload**）。DBは導入しない。
- **配信**: GitHub Pages を **Firebase Hosting** に置き換える。HTTPS・CDN を無料で得る。
  まず Firebase 既定ドメイン（`*.web.app`）の HTTPS で稼働開始し、独自ドメインは取得後に同一構成のまま後追いで追加する（任意）。
  ジョブ末尾で `index.html` + `feeds/*.xml` + `models.json` をデプロイする。
- **配信経路の一本化**: 状態保存用 GCS バケットは**非公開**とし、一般配信は Firebase に一本化する（直URL配信は併用しない）。
- **シークレット**: `OPENAI_API_KEY` を **Secret Manager** からジョブへ注入する。フロント・公開物には一切出さない。
- **コード変更は最小**: `models.json`/`feeds` の入出力パスを環境変数化するのみ。分析・生成ロジックは無改造。
- **撤去**: `.github/workflows/collect.yml` を削除（または手動実行用に縮小）。
- **BREAKING**: 公開 URL が GitHub Pages から独自ドメインへ変わる。既存購読者向けにフィード URL 変更の周知が必要。

採用しなかった案②「Cloud Load Balancer + GCS バックエンドバケット」は、ジョブが Python のまま済む利点はあるが
LB 固定費が月約 $18 かかる。軽量・低コスト優先で **案①（Firebase Hosting）** を採用。代償はジョブに
Firebase デプロイ工程が1つ増えること。月額は実質 OpenAI API 代のみ。

## Capabilities

### New Capabilities
- `cloud-execution`: 収集・フィード生成を GCP 上でスケジュール実行する（Cloud Run Job + Cloud Scheduler + Secret Manager によるキー注入）。
- `state-storage`: 収集状態 `models.json` を GCS バケットに永続化し、実行ごとに取得・更新・保存する（DB不使用）。
- `site-publishing`: サイトとRSSフィードを Firebase Hosting 経由で独自ドメイン・HTTPS で配信する。

### Modified Capabilities
<!-- 既存 specs は無し（openspec/specs/ は空）。要件変更のある既存 capability は無い。 -->

## Impact

- **変更コード**: `scripts/collect.py` / `scripts/generate_feeds.py`（入出力パスの環境変数化のみ）、`requirements.txt`。
- **新規**: `Dockerfile` とジョブ用エントリポイント（DL→collect→generate→UL→deploy）、Firebase 設定、デプロイ手順ドキュメント。
- **撤去/縮小**: `.github/workflows/collect.yml`。
- **不変**: `docs/index.html` のデータ取得（`./data/models.json` 相対 fetch のまま、配信元が変わるだけ）。
- **依存追加**: GCS 入出力手段（`google-cloud-storage` もしくは entrypoint での `gsutil`）と Firebase デプロイ手段。design で確定。
- **外部前提**: 独自ドメインの保有・DNS 設定、GCP プロジェクト・課金有効化。

## Non-goals（今回やらないこと）

- **DBの導入はしない**（GCS上のJSON 1ファイルで十分。Firestore等は将来のAPI化・検索時に検討）。
- **対象スコープの拡大（AIニュース全般化）はしない**（`is_model_related`・`models.json`命名・分類の一般化は別変更）。
- **収集・分析プロンプト・フィード仕様は変更しない**（保存先・実行・配信のみ差し替え）。
- **IaC（Terraform等）での完全自動化は必須としない**（まず動かす。手順化に留めてよい）。
- `OPENAI_API_KEY` 未設定でもダミーモードで動く現挙動は維持する。
