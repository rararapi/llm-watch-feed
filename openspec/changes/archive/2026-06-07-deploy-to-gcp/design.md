## Context

現構成は「常駐サーバの無い静的生成パイプライン」である。`collect.py` が RSS を取得して OpenAI で分析し
`docs/data/models.json` に追記、`generate_feeds.py` がそこから `docs/feeds/*.xml` を生成、GitHub Actions が
結果を git に commit/push し、GitHub Pages が `docs/` を配信している。状態は `models.json` 1ファイル
（単一ライター・上限500件・数十KB）に集約されている。

ホスティング先は GCP に確定。最優先目的は「GCP で動かし、更新を RSS で届ける」こと。本設計は
**保存先・実行場所・配信先の3点の差し替え**に範囲を限定し、収集・分析・フィード生成のロジックは温存する。

制約（プロジェクト方針）:
- LLM API 呼び出しはバックエンドのみ。APIキーをフロント・公開物（`docs/`相当）に出さない。
- 外部依存は安易に増やさない。Python はシンプル優先、フロントは Vanilla。
- 1ソース・1記事の失敗で全体が落ちない。

## Goals / Non-Goals

**Goals:**
- 収集→生成→配信を GCP 上で定時実行し、独自ドメイン・HTTPS で公開する。
- 状態 `models.json` を GCS に永続化し、git への commit を廃する。
- スクリプト本体はほぼ無改造（入出力パスの環境変数化のみ）でローカル/クラウド両対応にする。
- ランニングコストを実質 OpenAI API 代のみに抑える。

**Non-Goals:**
- DB（Firestore 等）の導入。
- 対象スコープの一般化（`is_model_related`・命名・分類の見直し）。
- 収集ロジック・分析プロンプト・フィード仕様の変更。
- Terraform 等による完全 IaC 化（手順化に留めてよい）。

## Decisions

### 1. 実行基盤は Cloud Run Job + Cloud Scheduler

バッチ処理（数秒・毎日1回）であり常駐不要。Cloud Run Job はゼロスケールで従量課金、無料枠内に収まる。
Cloud Scheduler が cron 発火を担う。

- 代替案: GitHub Actions 継続（保存先のみ GCS へ）。最小手数だが「GCP 上で動かす」要件を実行面で満たさない。
- 代替案: Cloud Functions（gen2）。実体は Cloud Run と同等だがバッチ用途では Job の方が素直。
- 代替案: GCE 常駐 VM。週2回の処理に対し過剰でコスト増。

### 2. 状態は GCS 上の JSON（DBなし）

データは単一ライター・上限500件・数十KB。read-modify-write の競合も無い。よって JSON 1ファイルで十分。

- 代替案: Firestore。将来 API 化・サーバサイド検索が要るなら有力だが、現時点では過剰。
  アップグレードパスとして「`models.json` を読み書きしている箇所」を1モジュールに閉じ込めておけば移行は容易。

### 3. GCS 入出力は download-run-upload（コード変更最小）

ジョブのエントリポイントで「GCS → `/tmp` へ取得 → `collect.py`/`generate_feeds.py` 実行 → `/tmp` → GCS へ保存」を行う。
スクリプトは入出力パスを環境変数（例: `MODELS_JSON_PATH`, `FEEDS_DIR`）で受け取るようにするだけで、本体は無改造。

- 代替案: スクリプト内で `google-cloud-storage` を直接叩く。ストレージ依存がロジックに混ざり、
  ローカル実行との分岐が増える。download-run-upload なら本体はファイル I/O のまま保てる。
- 取得手段: コンテナに `gsutil`/`gcloud` を含めるか、エントリポイントを薄い Python にして `google-cloud-storage` で
  入出力する。**後者（薄い Python ラッパー）を推奨**（イメージが軽く、認証は Workload Identity/ADC で完結）。

### 4. 配信は Firebase Hosting（独自ドメイン HTTPS を無料で）

GCS 単体では独自ドメイン HTTPS を出せない。Firebase Hosting は独自ドメイン・自動証明書・CDN を無料枠で提供する。

- 代替案: Cloud Load Balancer + GCS バックエンドバケット。ジョブは GCS へ書くだけで済み構成は単純だが、
  LB 転送ルールの固定費が月約 $18。軽量・低コスト優先で不採用。
- 代償: ジョブ末尾に Firebase へのデプロイ工程が増える。デプロイ手段は次の2案で、design 段階の推奨は後者。
  - **(a) firebase-tools(Node) をコンテナ同梱**し `firebase deploy --only hosting`。実績豊富だが Node ランタイムが乗りイメージが太る。
  - **(b) Firebase Hosting REST API をサービスアカウントで叩く**。Python のみで完結しイメージが軽い。実装はやや手間。
  - 推奨: まず確実性重視で (a) で動かし、軽量化が必要になったら (b) へ。← Open Questions 参照。

### 5. GCS の役割は「実行間の状態」、Firebase は「公開配信」

`models.json` の正本は GCS（次回実行が読む状態）。公開物は Firebase にデプロイされたコピー。
`models.json` も Firebase に置くことでフロントの `./data/models.json` 相対 fetch を無改造で維持する。

### 6. シークレットは Secret Manager 経由

`OPENAI_API_KEY` を Secret Manager に格納し、Cloud Run Job のシークレット参照として実行時のみ注入。
イメージ・ログ・公開物に出さない。未注入時はダミーモードで完走する現挙動を維持し、段階導入を可能にする。

### 7. 実行頻度は毎日

現行の火・金（週2回）から毎日 1 回へ変更する。Cloud Scheduler・Cloud Run Job とも無料枠内に収まる。
OpenAI 呼び出しは増えるが 1 回あたり最大 10 件のため増分は小さい。「更新を早く届ける」狙いに合致する。

### 8. 状態用 GCS バケットは非公開、配信は Firebase に一本化

GCS は実行間の状態（`models.json` の正本）置き場に徹し、公開 ACL は付けない。一般配信は Firebase のみとする。

- 代替案: GCS も公開し直URL（`storage.googleapis.com/...`）配信を併用。移行ブリッジになり得るが、
  Firebase は既定ドメイン `*.web.app` で即 HTTPS 配信できるためブリッジは不要。
  また直URLを購読されると正規フィードURLが二系統化し、後で畳む際に購読断絶を招く。よって非公開・一本化を採る。

### 9. 独自ドメインは後追い、まず Firebase 既定ドメインで稼働開始

独自ドメインは未取得。取得・DNS 設定はユーザ作業のため launch ブロッカーにしない。
Firebase 既定ドメイン（`*.web.app`、無料 HTTPS）でまず公開し、ドメイン取得後に Firebase に追加設定する。
配信アーキテクチャは変わらないため、後追い追加のコストは小さい。

- トレードオフ: 既定ドメインで公開した後に独自ドメインへ移すと、フィードURLが再度変わる。
  独自ドメインを早期に確定できるなら先に取得しておくとURL変更を1回で済ませられる（タスク 5 を参照）。

## Risks / Trade-offs

- [Firebase デプロイ工程の追加でジョブが複雑化] → デプロイをエントリポイント内の独立ステップに分離。
  デプロイ失敗時も GCS の状態保存は完了済みにし、次回再デプロイで回復可能にする。
- [サービスアカウント権限の過剰付与] → 役割を最小化（GCS: 対象バケットの read/write、Secret: 当該シークレットの accessor、
  Firebase: Hosting デプロイ権限のみ）。
- [公開物への機密混入] → 配信前提のファイルにキーを書かない設計を維持し、検収時に公開物一式を grep で確認。
- [フィード URL 変更による既存購読の断絶] → 公開時に旧 URL 変更を周知。必要なら旧 Pages に転送案内を残す。
- [download-run-upload の取得失敗] → 取得失敗時は空状態で開始せず明示エラーにし、状態の取り違え（全件消失）を防ぐ。
  初回のみ「存在しない＝空開始」を許容する。

## Migration Plan

1. GCP プロジェクト・課金・必要 API（Run/Scheduler/Secret Manager/Firebase）を有効化。
2. GCS バケット作成。既存 `docs/data/models.json` を初期状態としてアップロード（履歴の引き継ぎ）。
3. スクリプトの入出力パスを環境変数化（ローカルでは従来パスを既定にし後方互換）。
4. `Dockerfile` とエントリポイント（DL→collect→generate→UL→deploy）を作成。ローカルでコンテナ実行を検証。
5. Secret Manager に `OPENAI_API_KEY` 登録。Cloud Run Job 作成・シークレット紐付け。手動実行で疎通確認。
6. Cloud Scheduler 作成（毎日）。
7. Firebase Hosting 初期化・独自ドメイン設定・証明書発行。デプロイ疎通確認。
8. 数サイクル並行運用で安定確認後、`.github/workflows/collect.yml` を撤去（または手動用に縮小）、GitHub Pages を停止。

ロールバック: 移行完了までは GitHub Actions + Pages を残す。問題時は Scheduler を停止し旧構成へ戻す。
GCS の `models.json` を正本としているため、旧構成へ戻す場合はその時点の JSON を `docs/` に戻して commit する。

## Open Questions

- Firebase デプロイ手段は (a) firebase-tools 同梱 か (b) Hosting REST API か。初期は (a)、軽量化要件が出たら (b)。
- 独自ドメインを取得するか／どのドメインにするか（取得・DNS はユーザ作業。未取得でも既定ドメインで稼働可。タスク 5 で任意対応）。

> 解決済み: 実行頻度=毎日（Decision 7）、GCS 非公開・Firebase 一本化（Decision 8）、既定ドメインで稼働開始し独自ドメインは後追い（Decision 9）。
