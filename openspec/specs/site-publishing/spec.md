# site-publishing Specification

## Purpose

画面（HTML/JS）は Firebase Hosting で HTTPS 配信し、データ（`data/models.json`）とRSSフィード（`feeds/*.xml`）は公開GCSバケットで配信する（方式A）。ニュース更新（GCS書き込み）とサイトデプロイ（画面のFirebaseデプロイ）を分離し、公開物に機密を一切含めない。

## Requirements

### Requirement: データ／フィードの公開GCSバケット配信

システムはデータ（`data/models.json`）とRSSフィード（`feeds/*.xml`）を公開GCSバケットから直接配信 SHALL する。ニュース更新ジョブはフィード生成後にこれらをバケットへ書き込み SHALL し、配信のためのサイト再デプロイを要求 SHALL NOT する。

#### Scenario: 更新後に最新データ／フィードが公開される

- **WHEN** ニュース更新ジョブが収集・フィード生成を完了する
- **THEN** `data/models.json` と `feeds/*.xml` が公開GCSバケットへ書き込まれ、公開URLで最新版が取得・購読できる

### Requirement: 画面の Firebase Hosting 配信

システムは画面（`index.html` 等の静的ファイル）を Firebase Hosting で HTTPS 配信 SHALL する。画面のデプロイはニュース更新から独立 SHALL し、画面の静的ファイルを変更したときにのみ行う（`scripts/deploy_site.sh` = `firebase deploy`）。

#### Scenario: 毎日のニュース更新は画面を再デプロイしない

- **WHEN** ニュース更新ジョブが実行される
- **THEN** `data/models.json` と `feeds/*.xml` のみが更新され、Firebase Hosting の画面は再デプロイされない

#### Scenario: 画面変更時のみデプロイする

- **WHEN** 画面の見た目・JS を変更し `deploy_site.sh` を実行する
- **THEN** 画面の静的ファイルが Firebase Hosting へデプロイされる

### Requirement: 画面はGCSからクロスオリジンでデータ取得

システムは Firebase Hosting で配信される画面のJSが、公開GCSバケットの絶対URL（`DATA_ORIGIN`）から `data/models.json` と `feeds/*.xml` を取得 SHALL できるよう、バケットに CORS（GET 許可）を設定 SHALL する。

#### Scenario: ブラウザがクロスオリジンでデータを表示する

- **WHEN** ブラウザが Firebase Hosting の画面を開く
- **THEN** 画面のJSは GCS の絶対URLから `data/models.json` を取得し（CORS許可）、最新の収集結果を表示する

### Requirement: HTTPS 配信と独自ドメイン対応

システムは画面を公開時点から HTTPS で配信 SHALL し、RSSフィードは安定した公開URLで購読可能 SHALL とする。画面の独自ドメインは Firebase Hosting に無料で接続可能 SHALL とする。

#### Scenario: 既定ドメインの HTTPS でアクセスできる

- **WHEN** 利用者が画面URL（`https://<project>.web.app`）にアクセスする
- **THEN** 有効な証明書による HTTPS で配信される

#### Scenario: 独自ドメインを後から追加する

- **WHEN** 取得済みドメインを Firebase Hosting にカスタムドメインとして追加する
- **THEN** 配信パイプラインを変更せず、画面が独自ドメイン上で HTTPS 配信される（フィードURLは公開GCSバケットのまま）

### Requirement: 公開物に機密を含めない

システムは公開される配信物（HTML・JS・フィード・JSON）に API キー等の機密を含め SHALL NOT する。

#### Scenario: 配信物にAPIキーが存在しない

- **WHEN** 配信される公開ファイル一式を検査する
- **THEN** API キー・認証情報その他の機密情報は一切含まれていない
