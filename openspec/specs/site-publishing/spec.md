# site-publishing Specification

## Purpose

サイト・RSSフィード・データを Firebase Hosting 経由で HTTPS 配信し、独自ドメイン移行を見据えつつ、公開物に機密を一切含めない。

## Requirements

### Requirement: Firebase Hosting での配信

システムはサイト（`index.html`）・RSSフィード（`feeds/*.xml`）・データ（`models.json`）を Firebase Hosting 経由で配信 SHALL する。ジョブはフィード生成後に最新成果物を Firebase Hosting へデプロイ SHALL する。

#### Scenario: 更新後に最新成果物が公開される

- **WHEN** ジョブが収集・フィード生成を完了する
- **THEN** `index.html` + `feeds/*.xml` + `models.json` が Firebase Hosting にデプロイされ、公開URLで最新版が閲覧・購読できる

#### Scenario: フロントが配信元からデータを取得する

- **WHEN** ブラウザが公開サイトを開く
- **THEN** `index.html` は相対パスで `models.json` を取得し、最新の収集結果を表示する

### Requirement: HTTPS 配信と独自ドメイン対応

システムは公開時点から HTTPS で配信 SHALL し、RSSフィードは安定した公開URLで購読可能 SHALL とする。独自ドメインは取得後に追加対応可能 SHALL とし、その移行で配信アーキテクチャを変更 SHALL NOT する。

#### Scenario: 既定ドメインの HTTPS でアクセスできる

- **WHEN** 利用者が公開サイトURL・フィードURL（Firebase 既定ドメイン `*.web.app`）にアクセスする
- **THEN** 有効な証明書による HTTPS で配信される

#### Scenario: 独自ドメインを後から追加する

- **WHEN** 独自ドメインを取得し Firebase Hosting に設定する
- **THEN** 同一の配信構成のまま、独自ドメイン上で HTTPS 配信される

### Requirement: 公開物に機密を含めない

システムは公開される配信物（HTML・JS・フィード・JSON）に API キー等の機密を含め SHALL NOT する。

#### Scenario: 配信物にAPIキーが存在しない

- **WHEN** デプロイされた公開ファイル一式を検査する
- **THEN** `OPENAI_API_KEY` その他の機密情報は一切含まれていない
