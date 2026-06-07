# site-publishing Specification

## Purpose

サイト・RSSフィード・データを公開GCSバケットから HTTPS 直接配信し、独自ドメイン移行を見据えつつ、公開物に機密を一切含めない。ニュース更新（毎日）とサイトデプロイ（変更時のみ）を分離する。

## Requirements

### Requirement: 公開GCSバケットからの直接配信

システムはサイト（`index.html`）・RSSフィード（`feeds/*.xml`）・データ（`data/models.json`）を公開GCSバケットから直接配信 SHALL する。ニュース更新ジョブはフィード生成後に `data/models.json` と `feeds/*.xml` を当該バケットへ書き込み SHALL し、サイトの再デプロイを要求 SHALL NOT する。

#### Scenario: 更新後に最新成果物が公開される

- **WHEN** ニュース更新ジョブが収集・フィード生成を完了する
- **THEN** `data/models.json` と `feeds/*.xml` が公開GCSバケットへ書き込まれ、公開URLで最新版が閲覧・購読できる

#### Scenario: フロントが配信元からデータを取得する

- **WHEN** ブラウザが公開サイトを開く
- **THEN** `index.html` は相対パスで `data/models.json` を取得し、最新の収集結果を表示する

### Requirement: ニュース更新とサイトデプロイの分離

システムはニュース更新（データ・フィードの書き込み）とサイトデプロイ（`index.html` 等の配信）を分離 SHALL する。毎日のニュース更新はサイト静的ファイルを変更 SHALL NOT し、サイト静的ファイルの配信は専用の手順（`scripts/deploy_site.sh`）で行う。

#### Scenario: 毎日の更新はサイトを再デプロイしない

- **WHEN** ニュース更新ジョブが実行される
- **THEN** `data/models.json` と `feeds/*.xml` のみが更新され、`index.html` 等は再配信されない

#### Scenario: サイト変更時のみサイトを配信する

- **WHEN** サイトの見た目・JS を変更し `deploy_site.sh` を実行する
- **THEN** `index.html` 等のサイト静的ファイルが公開GCSバケットへ配信される

### Requirement: HTTPS 配信と独自ドメイン対応

システムは公開時点から HTTPS で配信 SHALL し、RSSフィードは安定した公開URLで購読可能 SHALL とする。独自ドメインは取得後に追加対応可能 SHALL とし、その移行で配信パイプライン（収集・生成・書き込み）を変更 SHALL NOT する。

#### Scenario: バケットURLの HTTPS でアクセスできる

- **WHEN** 利用者が公開サイトURL・フィードURL（`https://storage.googleapis.com/<bucket>/...`）にアクセスする
- **THEN** 有効な証明書による HTTPS で配信される

#### Scenario: 独自ドメインを後から追加する

- **WHEN** 公開GCSバケットの前段に HTTPS ロードバランサ + Cloud CDN + マネージドSSL を置き独自ドメインを設定する
- **THEN** 収集・生成・書き込みのパイプラインは無変更のまま、独自ドメイン上で HTTPS 配信される

### Requirement: 公開物に機密を含めない

システムは公開される配信物（HTML・JS・フィード・JSON）に API キー等の機密を含め SHALL NOT する。

#### Scenario: 配信物にAPIキーが存在しない

- **WHEN** 配信される公開ファイル一式を検査する
- **THEN** API キー・認証情報その他の機密情報は一切含まれていない
