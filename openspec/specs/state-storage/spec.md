# state-storage Specification

## Purpose

収集状態 `models.json` を公開GCSバケットの `data/models.json` に永続化し、重複排除・件数上限を維持しつつ、これをそのまま配信に用い、ローカル/クラウド双方から同一スクリプトが動作できるようにする。

## Requirements

### Requirement: GCS への状態永続化

システムは収集状態を公開GCSバケットの `data/models.json`（既定キー、`GCS_OBJECT` で変更可）に永続化 SHALL し、git リポジトリには保存 SHALL NOT する。
実行ごとにジョブは GCS から既存の状態を取得し、更新後に GCS へ書き戻す（download-run-upload）。書き戻した状態はそのまま公開配信される。

#### Scenario: 既存状態を引き継いで追記する

- **WHEN** ジョブが起動し GCS に前回の `models.json` が存在する
- **THEN** その内容を読み込み、新着記事を追記したうえで GCS に保存する

#### Scenario: 初回実行（状態が存在しない）

- **WHEN** GCS に `models.json` が存在しない状態でジョブが起動する
- **THEN** 空の状態から開始し、収集結果で新規に `models.json` を作成して GCS に保存する

### Requirement: 重複排除と件数上限

システムは URL の SHA-256 ハッシュで記事を重複排除 SHALL し、保持件数を上限（既定 500 件）に制限 SHALL する。

#### Scenario: 既出URLを再収集しない

- **WHEN** すでに `models.json` に存在する URL の記事を再取得する
- **THEN** その記事は重複として追加されない

#### Scenario: 上限を超えたら古い記事を切り詰める

- **WHEN** 追記後の総件数が上限を超える
- **THEN** 最新分のみを残して上限件数に切り詰めて保存する

### Requirement: 状態バケットは公開配信を兼ねる

システムは状態保存用 GCS バケットを公開読み取り可能 SHALL とし、`data/models.json` を含む配信物をバケットから直接 HTTPS 配信 SHALL する。書き込み（状態更新）はサービスアカウント経由に限定 SHALL し、公開する配信物に機密を含め SHALL NOT する。

#### Scenario: 状態が公開URLで取得できる

- **WHEN** 利用者が `https://storage.googleapis.com/<bucket>/data/models.json` にアクセスする
- **THEN** 認証なしで最新の状態（機密を含まない）が取得できる

#### Scenario: 書き込みは認証が必要

- **WHEN** 認証情報なしで GCS バケットのオブジェクトを書き換えようとする
- **THEN** 書き込みは拒否され、更新はサービスアカウント経由でのみ可能である

### Requirement: 入出力パスの設定可能化

システムは `models.json` と生成フィードの入出力先を環境変数で設定可能 SHALL とし、
ローカル実行（ファイルパス）とクラウド実行（GCS）の双方で同一スクリプトが動作 SHALL する。

#### Scenario: 環境変数で保存先を切り替える

- **WHEN** 入出力先を指定する環境変数が設定されている
- **THEN** スクリプトはその場所に対して読み書きし、本体ロジックは変更なく動作する
