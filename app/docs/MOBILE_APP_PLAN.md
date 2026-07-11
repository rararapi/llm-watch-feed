# モバイルアプリ化 計画（React Native / Expo）

> 作成: 2026-06-20 ／ ステータス: 方針確定（実装未着手）
> 本計画は内部ドキュメント。公開サイト出力の `docs/`（`generate_pages.py` の生成物）とは無関係で、リポジトリのトップレベルに置く。

## 0. 背景と前提（重要）

現行の「Webアプリ」の実体は **Python製のSSG（静的サイトジェネレータ）**。

- フロントは **Vanilla HTML/JS/CSS**（フレームワーク不使用が設計ルール／AGENTS.md）。
- UIは `templates/`（Jinja2）+ `assets/site/`（CSS・`app.js`）を Python が生成。
- データ `models.json`（配列）は **公開GCSバケットからHTTPS配信**（CORS設定済み）。RSSフィードも同様。
- 日次の Cloud Run Job が「収集→分析→AI画像→フィード→サイト生成→GCS書き込み」を実行。

→ **UIコードの再利用は不可能**（Web側にReact資産が存在しない）。
→ ただし **データ層がすでに理想的な「読み取り専用API」**になっており、RNアプリは `models.json` を直接fetchするだけで成立する。再利用すべきは「コンポーネント」ではなく **データ契約・定数・画像リソース・小さなビジネスロジック**。

### 再利用できる資産

| 資産 | 再利用方法 |
|---|---|
| `models.json`（公開JSON） | RNが直接fetch。バックエンド改修ゼロでv1成立 |
| RSSフィード / AI生成画像（GCS） | そのまま参照 |
| スキーマ（Article型） | TSの型として一度だけ定義し単一の真実に |
| 定数（ソース→色、importance/model_type ラベル、タグ） | Python側から `shared/meta.json` で吐き出し両者が読む |
| 絞り込みロジック（`assets/site/js/app.js`） | TSへ移植（importanceセグメント/ソース/キーワード、日付グルーピング、サムネ優先順） |

## 1. 確定方針（ユーザー承認済み）

- **リポジトリ**: モノレポ／main管理。`app/` を追加、CIはパスフィルタで日次ジョブと分離。**Webは無改修で稼働継続**。
- **記事詳細**: ネイティブ表示（要約/impact/action をRN描画、元記事はアプリ内ブラウザで開く）。
- **Push通知**: Phase 2 で追加（Expo Push + Firestore トークン保管 + 日次ジョブからの送信）。
- **スタック**: Expo (managed) + expo-router + TanStack Query + MMKV + expo-web-browser。

### リポジトリ戦略の根拠

- 最も同期させたいデータスキーマを、それを生み出す Python（`collect.py`/`generate_pages.py`）の隣に置ける。スキーマ変更とアプリ追従を1コミットで原子的に行える。
- Push用バックエンド改修も同一リポで完結。
- 小規模・単一プロダクトのため、マルチリポの整合コストが見合わない。
- ブランチ分離は却下（長命ブランチはドリフトしmain追従が苦痛）。
- 将来モバイルが独立チーム／独立リリースになれば `git filter-repo` で履歴ごと分離可能。**まずモノレポ、必要時に割る**。

## 2. ディレクトリ構成（提案）

```
llm-watch-feed/
  scripts/ templates/ assets/   # 既存（変更なし）
  shared/meta.json              # NEW: Pythonが吐く定数（ソース/色/ラベル）
  app/                          # NEW: Expo (React Native) アプリ一式
    app/                        #   expo-router 画面
    src/{api,components,lib,types}
    package.json
```

※ Web側がTSを消費できない以上 `pnpm workspace + packages/core` はオーバーエンジニアリング。型・定数は `app/` 内に持ち、Python由来の定数だけ `shared/meta.json` で共有する。

## 3. 実装フェーズ

### Phase 0 — データをAPIとして固める（バックエンド微修正のみ）
- `models.json` の到達性・CORSを確認。
- TSの `Article` 型をスキーマからミラー定義。
- `generate_pages.py` 等に `shared/meta.json` 出力を追加（ソース一覧・色・ラベル。アプリのハードコード回避）。
- （任意）モバイル向け軽量JSON（必要フィールドのみ／件数制限）。v1は500件の `models.json` をそのまま消費で可。

### Phase 1 — アプリMVP（Web機能パリティ・読み取り専用）
- Expo雛形 + expo-router。
- フィード一覧: `models.json`取得 → 日付グルーピング → importanceセグメント＋ソース絞り込み＋キーワード検索（`app.js`移植）＋サムネ優先順（AI画像→OG→プレースホルダ）。
- 記事詳細: 要約/impact/action をネイティブ表示 ＋「元記事を開く」（expo-web-browser）＋ シェア。
- 購読画面: RSS URLコピー、既存subscribeページへのリンク。
- オフラインキャッシュ（MMKV/AsyncStorage）。
- EAS Build → TestFlight / Play内部テスト。

### Phase 2 — モバイルならではの価値
- **Push通知**: 日次ジョブが新規・重要度Aを検出 → Expo Push API にPOST。トークン登録の保管に Firestore を追加。
- ブックマーク／既読（ローカル）。アイコン・スプラッシュ・ストア素材。

### Phase 3 — リリースと運用
- App Store / Play 提出。EAS UpdateでOTA。クラッシュ計測。

## 4. Webへの影響

**ゼロ。** モバイルは同じ公開データを読むだけの純粋な追加で、既存Webは無改修で稼働継続。バックエンドはPhase 2でPush用ステップが増えるのみ。

## 5. 進め方

このリポは OpenSpec ワークフロー（`openspec/`）で変更管理しているため、推奨順は:

1. **OpenSpec で proposal 起票**（この計画をレビュー可能な形式に）
2. **Phase 0**（データ契約確定）
3. **Phase 1**（Expo雛形 + 一覧画面）

## 6. 実装状況（2026-06-20）

OpenSpec 変更 `add-mobile-app` を起票し、Phase 0 + Phase 1 のコードを実装済み。

- **Phase 0（バックエンド）**: `generate_pages.py` が表示定数を `shared/meta.json` へ出力（既存サイト出力に非干渉・gitignore）。`./scripts/generate_pages.py` で生成と既存サイト36記事の生成を確認済み。
- **Phase 1（アプリ）**: `app/` に Expo (managed) + expo-router で実装。一覧（取得/絞り込み/日付グルーピング/サムネ優先順）・記事詳細（ネイティブ表示 + アプリ内ブラウザ + 共有）・RSS購読（コピー）・オフラインキャッシュ。`npx tsc --noEmit` と iOS Metro バンドル（1152 modules）が成功。
- **CI**: `.github/workflows/app.yml` を `app/**` パスフィルタで新設（型チェック + 任意の EAS ビルド）。既存 `deploy.yml` とは非干渉。
- **データ取得先**: `app/src/lib/config.ts`（公開バケット `models.json`。`EXPO_PUBLIC_DATA_URL` で上書き可）。

### 残作業（実機・アカウントが必要なため未実施）

- 実機/シミュレータでの動作確認（`npm run start`、オフライン挙動、Webとの絞り込み結果一致）
- EAS Build による内部配布（TestFlight / Play内部テスト）— Apple/Google デベロッパー登録と `EXPO_TOKEN` が必要
  - Apple 個人登録の詳細手順は [`apple-developer-enrollment.md`](./apple-developer-enrollment.md)
- アプリアイコン/スプラッシュの本番デザイン差し替え（現状は Expo 既定）

詳細手順は [`app/README.md`](../README.md)。Push通知は Phase 2（別 OpenSpec 提案）。
