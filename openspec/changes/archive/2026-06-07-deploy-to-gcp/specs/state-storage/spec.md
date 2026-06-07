## ADDED Requirements

### Requirement: GCS への状態永続化

システムは収集状態 `models.json` を GCS バケットに永続化 SHALL し、git リポジトリには保存 SHALL NOT する。
実行ごとにジョブは GCS から既存の `models.json` を取得し、更新後に GCS へ書き戻す（download-run-upload）。

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

### Requirement: 状態バケットの非公開

システムは状態保存用 GCS バケットを非公開 SHALL とし、アクセスをサービスアカウント経由の読み書きに限定 SHALL する。一般利用者への配信は Firebase Hosting に一本化 SHALL し、GCS の直URL配信は提供 SHALL NOT する。

#### Scenario: バケットへ匿名アクセスできない

- **WHEN** 認証情報なしで GCS バケットのオブジェクトに直接アクセスする
- **THEN** アクセスは拒否され、公開配信は Firebase 経由でのみ提供される

### Requirement: 入出力パスの設定可能化

システムは `models.json` と生成フィードの入出力先を環境変数で設定可能 SHALL とし、
ローカル実行（ファイルパス）とクラウド実行（GCS）の双方で同一スクリプトが動作 SHALL する。

#### Scenario: 環境変数で保存先を切り替える

- **WHEN** 入出力先を指定する環境変数が設定されている
- **THEN** スクリプトはその場所に対して読み書きし、本体ロジックは変更なく動作する
