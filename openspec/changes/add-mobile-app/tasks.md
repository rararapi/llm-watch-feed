## 1. バックエンド: 表示定数の共有出力（Phase 0）

- [x] 1.1 `generate_pages.py` に、ソース一覧・ソース色・重要度ラベル・モデル種別ラベルを `shared/meta.json` として出力する処理を追加（既存サイト出力に非干渉、try/exceptで保護）
- [x] 1.2 `shared/meta.json` に機密・APIキーが含まれないことを確認（公開前提の表示定数のみ）
- [x] 1.3 検証: `python scripts/generate_pages.py` 実行 → `shared/meta.json` 生成と、既存 `docs/index.html`/`docs/articles/`/`docs/feeds/` が従来どおり生成されることを確認（`./scripts/preview.sh` でサイト表示確認）
- [x] 1.4 `.gitignore` で `shared/meta.json` の追跡方針を決定（生成物としてignore or コミット）。`AGENTS.md` に出力を追記

## 2. モバイル: プロジェクト基盤（Phase 1）

- [x] 2.1 `app/` に Expo (managed) プロジェクトを作成（expo-router 構成、TypeScript）
- [x] 2.2 ルートの `.gitignore` に `app/node_modules` 等を追加。CIワークフローを `app/**` パスフィルタで新設（既存 `deploy.yml` と非干渉）
- [x] 2.3 `TanStack Query` / `MMKV`（or AsyncStorage）/ `expo-web-browser` を導入
- [x] 2.4 検証: `app/` で `npx expo start` が起動し、空画面がiOS/Androidシミュレータ（またはExpo Go）で表示される

## 3. モバイル: データ層

- [x] 3.1 `models.json` のスキーマをミラーした `Article` TS型を `app/src/types` に定義
- [x] 3.2 公開GCSの `data/models.json` を取得するAPIクライアントを実装（TanStack Query、失敗時の再試行）
- [x] 3.3 取得データをローカルキャッシュし、オフライン時に利用する永続化を実装
- [x] 3.4 `shared/meta.json` をアプリへ取り込み、ソース色・ラベルを解決するユーティリティを実装（アプリ内ハードコードを避ける）
- [x] 3.5 検証: 機内モード（オフライン）でも直近取得データの一覧が表示されることを確認

## 4. モバイル: フィード一覧（Phase 1）

- [x] 4.1 記事を `published_at` 降順・日付グループで表示する一覧画面を実装
- [x] 4.2 サムネ優先順（`image_generated_url` → `image_url` → プレースホルダ）を実装
- [x] 4.3 絞り込み（重要度セグメント / ソース / キーワード、AND結合、件数表示、該当なし表示）を `assets/site/js/app.js` と同等挙動で実装
- [x] 4.4 検証: Web版（`./scripts/preview.sh`）と同じデータで、絞り込み結果・件数が一致することを確認

## 5. モバイル: 記事詳細（Phase 1）

- [x] 5.1 要約 / impact / action / タグ / ソース / 重要度をネイティブ描画する詳細画面を実装
- [x] 5.2 「元記事を開く」を `expo-web-browser`（アプリ内ブラウザ）で実装
- [x] 5.3 記事URL（とタイトル）のOS標準共有を実装
- [x] 5.4 検証: 一覧→詳細→元記事→共有の一連の操作がiOS/Androidで動作することを確認

## 6. モバイル: 購読画面とMVP仕上げ（Phase 1）

- [x] 6.1 RSSフィードURL一覧の表示とコピー機能を実装（Push通知はスコープ外と明記）
- [x] 6.2 アプリアイコン・スプラッシュ・基本テーマを設定
- [ ] 6.3 検証: EAS Build で内部配布ビルドを作成し、TestFlight / Play内部テストで実機確認

## 7. ドキュメント

- [x] 7.1 `MOBILE_APP_PLAN.md` / `AGENTS.md` を実装結果に合わせて更新（`app/` 構成・起動手順・CI）
- [x] 7.2 `app/README.md` に開発・ビルド・配布手順（`expo start` / EAS Build / EAS Update）を記載
