## 1. コードの入出力パス環境変数化（ローカルで完結）

- [x] 1.1 `collect.py` の `MODELS_JSON_PATH` を環境変数（既定: `docs/data/models.json`）で上書き可能にする
- [x] 1.2 `generate_feeds.py` の `MODELS_JSON_PATH` / `FEEDS_DIR` を環境変数（既定は現行パス）で上書き可能にする
- [x] 1.3 後方互換確認: 環境変数なしで `python scripts/collect.py` → `python scripts/generate_feeds.py` が従来どおり動く
- [x] 1.4 パス差し替え確認: 環境変数で別ディレクトリを指定し、そこに `models.json` と `feeds/*.xml` が出力される
- [x] 1.5 `OPENAI_API_KEY` 未設定でダミーモード完走、設定時に OpenAI 分析が走ることをローカルで確認

## 2. コンテナ化とエントリポイント（DL→collect→generate→UL→deploy）

- [x] 2.1 `Dockerfile` を作成（Python + requirements、必要なら Firebase デプロイ手段を同梱）
- [x] 2.2 エントリポイントを作成: GCS から `models.json` 取得 →（無ければ初回として空開始）
- [x] 2.3 エントリポイントで `collect.py` → `generate_feeds.py` を順に実行
- [x] 2.4 エントリポイントで更新後 `models.json` を GCS へ保存（状態の正本）
- [x] 2.5 エントリポイントで `index.html` + `feeds/*.xml` + `models.json` を Firebase Hosting へデプロイ
- [x] 2.6 ローカルで `docker run`（GCS/Firebase は認証情報を渡して）し、一連が通ることを確認

## 3. GCP リソース準備

- [x] 3.1 GCP プロジェクト・課金・必要 API（Run / Scheduler / Secret Manager / Firebase / Storage）を有効化
- [x] 3.2 GCS バケットを**非公開**で作成し、既存 `docs/data/models.json` を初期状態としてアップロード（公開ACLは付与しない）
- [ ] 3.3 Secret Manager に `OPENAI_API_KEY` を登録
- [x] 3.4 最小権限のサービスアカウントを作成（GCS read/write・Secret accessor・Firebase デプロイのみ）

## 4. デプロイと定時実行

- [x] 4.1 コンテナイメージをビルドし Artifact Registry へ push
- [x] 4.2 Cloud Run Job を作成し、シークレットと環境変数（`SITE_URL`・GCS バケット名等）を紐付け
- [x] 4.3 Cloud Run Job を手動実行し、GCS 更新と Firebase 公開まで疎通確認
- [x] 4.4 Cloud Scheduler を作成（毎日）し、定時起動を確認

## 5. 配信（Firebase Hosting）

- [x] 5.1 Firebase Hosting を初期化し、既定ドメイン（`*.web.app`）へのデプロイ疎通を確認
- [x] 5.2 既定ドメインの HTTPS でサイト・フィードにアクセスできることを確認（ここまでで「動いて届く」を達成）
- [x] 5.3 公開サイトをブラウザで開き、`models.json` を取得して最新記事が表示されることを確認
- [x] 5.4 各 RSS フィード URL を RSS リーダーで購読し、更新が届くことを確認
- [ ] 5.5 （任意・ユーザ作業）独自ドメインを取得し DNS を設定する
- [ ] 5.6 （任意）取得した独自ドメインを Firebase Hosting に追加し、HTTPS 証明書発行とアクセスを確認

## 6. セキュリティ検収

- [x] 6.1 デプロイ済み公開ファイル一式を grep し、`OPENAI_API_KEY` 等の機密が含まれないことを確認
- [x] 6.2 Cloud Run Job のログに API キーが平文出力されていないことを確認

## 7. 旧構成の撤去

- [ ] 7.1 数サイクル並行運用し、GCP 側で安定して更新・配信されることを確認（ユーザ判断で即時切替を選択したためスキップ）
- [x] 7.2 `.github/workflows/collect.yml` を撤去（旧生成物 docs/data・docs/feeds・.nojekyll も削除）
- [ ] 7.3 GitHub Pages を停止し、必要なら旧 URL に新フィード URL への案内を残す（要 GitHub Web 設定。手動作業）
- [x] 7.4 README / CLAUDE.md の実行・配信手順を GCP 構成に合わせて更新
