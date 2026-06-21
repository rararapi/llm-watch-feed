## Why

「サイトが稼働し、更新がRSSで届く」現フェーズの目的は達成済みで、次の到達点は **届け先の拡大** にある。RSS購読のハードルが高い一般のAIウォッチャーに対し、ネイティブのモバイルアプリは最も日常的な接点になる。既存の `models.json` は公開GCSバケットからHTTPS＋CORSで配信済みで、すでに「読み取り専用API」として成立しているため、**バックエンド改修ゼロ** でモバイルクライアントを追加できる。Webアプリ（SSG）はそのまま無改修で稼働を続ける。

## What Changes

- **新規 `app/`（Expoモノレポ）**: React Native (Expo managed) でiOS/Androidアプリを追加。同一リポジトリ・main管理で、CIはパスフィルタにより既存の日次ジョブ／サイトデプロイと分離する。
- **読み取り専用クライアント**: アプリは公開GCSの `data/models.json` を直接fetchし、フィード一覧・絞り込み（重要度/ソース/キーワード）・記事詳細をネイティブ描画する。元記事はアプリ内ブラウザで開く。バックエンド・配信構成は変更しない。
- **定数の共有ソース化**: ソース一覧・色・ラベル等の表示定数を `generate_pages.py` から `shared/meta.json` として出力し、Web（SSG）とアプリ双方が同じ定義を参照できるようにする（アプリ側ハードコード回避）。これがバックエンドへの唯一の追加で、既存サイト生成の挙動は変えない（純粋な追加出力）。
- **オフライン閲覧**: 取得済み `models.json` をローカルキャッシュし、オフラインでも直近データを表示する。
- **段階導入**: MVP（Phase 1）は読み取り専用で配信。**Push通知はPhase 2** とし、本提案のスコープからは外す（下記 Non-goals）。

### Non-goals（今回やらないこと）

- **Push通知**（Phase 2で別提案。Expo Push＋トークン保管＋日次ジョブからの送信が必要なため、バックエンド変更を伴う本格機能として分離）。
- 既存Web/SSG・RSS・収集パイプラインのリプレースや改修（モバイルは純粋な追加。Webは無改修で継続）。
- `models.json` のスキーマ変更や命名一般化（別途進行中の課題。本提案はモバイルからの参照のみ）。
- アプリ専用APIサーバやBFFの新設（v1は公開JSONを直接消費。将来モバイル向け軽量JSONが必要になれば別途検討）。
- ブックマーク/既読のクラウド同期（v1はローカル保存のみ。クラウド同期は将来検討）。
- アプリ内課金・アフィリエイトのストア対応（収益化が必要になった段階で審査ポリシーを含め別途）。

### 未確定の前提（決め打ちしない点）

- **配布アカウント/組織**: Apple Developer Program・Google Play デベロッパーアカウントの取得・名義は未確定。MVPの内部配布（TestFlight/Play内部テスト）までを当面の到達点とし、一般公開は別判断とする。
- **アプリ内ブラウザ vs 外部ブラウザ**: 元記事の開き方は `expo-web-browser`（アプリ内）を推奨（離脱を抑えUXが良い）。OS標準ブラウザで開く案もあり、実装後に比較可能。

## Capabilities

### New Capabilities
- `mobile-app`: 公開GCSの `models.json` を直接消費し、フィード一覧・絞り込み・記事詳細・オフラインキャッシュを提供する React Native (Expo) モバイルクライアント。読み取り専用で、既存Web/バックエンドに非依存。

### Modified Capabilities
- `site-publishing`: サイト生成（`generate_pages.py`）に、表示定数を `shared/meta.json` として出力する **追加挙動** を加える（既存サイト出力の挙動は不変）。モバイルとWebが同一の表示定数を参照できるようにするため。

## Impact

- **新規コード**: `app/`（Expoアプリ一式：expo-router 画面、`src/{api,components,lib,types}`、`package.json` 等）。
- **新規生成物**: `shared/meta.json`（`generate_pages.py` が出力）。
- **変更コード**: `scripts/generate_pages.py`（`shared/meta.json` 出力の追加）。`AGENTS.md` / `README.md`（アプリ構成の追記）。
- **CI/CD**: アプリ用ワークフロー（EAS Build/Update）を `app/**` パスフィルタで追加。既存 `deploy.yml`（日次ジョブ／サイト）は無改修で、相互に干渉しない。
- **依存**: `app/` 配下にのみ Node/Expo ツールチェーン（node_modules, EAS）を導入。Python側の依存は増やさない。
- **配信/データ**: 既存の公開GCSバケット・Firebase Hosting・RSS配信は無改修。アプリは公開 `models.json` を読むのみ。
- **コスト**: EAS（無料枠あり、ビルド超過分は従量）。配布時に Apple/Google のデベロッパー登録費用が別途発生（一般公開を判断した段階）。
