# AI News Watch — モバイルアプリ (Expo / React Native)

既存Web（SSG）と同じ公開データ（`models.json`）を読む **読み取り専用** の iOS/Android アプリ。
バックエンド・配信構成には依存せず、公開GCSバケットの JSON を直接取得して表示する。

計画・設計の全体像は [`docs/MOBILE_APP_PLAN.md`](docs/MOBILE_APP_PLAN.md) と
リポジトリ直下 `openspec/changes/add-mobile-app/`（proposal / design / specs / tasks）を参照。

## 技術スタック

- Expo (managed) + expo-router（ファイルベースルーティング）
- TanStack Query（取得・キャッシュ・再試行）
- AsyncStorage（オフラインキャッシュ。Expo Go 互換のため MMKV ではなく AsyncStorage を採用）
- expo-web-browser（元記事をアプリ内ブラウザで表示）/ expo-clipboard（RSS URLコピー）

## ディレクトリ

```
app/
  app/                 expo-router の画面
    _layout.tsx        ルート（QueryClientProvider + Stack）
    index.tsx          フィード一覧（取得/絞り込み/日付グルーピング）
    article/[id].tsx   記事詳細（ネイティブ表示 + 元記事/共有）
    subscribe.tsx      RSS購読（フィードURLのコピー）
  src/
    api/               models.json 取得（client）とオフラインキャッシュ（storage）
    components/        ArticleCard / Thumbnail / Badge / Filters
    lib/               filter（絞り込み・グルーピング）/ thumb / meta / format / config
    types/             Article / SharedMeta 型
    generated/meta.json  バックエンド生成 shared/meta.json のビルド時コピー（sync-meta）
  scripts/sync-meta.mjs  ../shared/meta.json を src/generated/meta.json へ複製
```

## 表示定数の単一情報源

ソース色・重要度/モデル種別ラベルは、バックエンドの `scripts/generate_pages.py` が出力する
リポジトリ直下 `shared/meta.json` が単一情報源。`npm run sync-meta` で `src/generated/meta.json`
へ取り込む（アプリ内に同等定数を重複定義しない）。ソース色は Web（`styles.css` の `--ph-hue`）と
同じ hue 計算で一致させている。記事データ取得先（公開バケットURL）は `src/lib/config.ts`
（`EXPO_PUBLIC_DATA_URL` で上書き可）。

## 開発

```bash
cd app
npm install          # .npmrc で legacy-peer-deps=true（Expo の peer 競合回避）
npm run sync-meta    # 任意: shared/meta.json があれば取り込む
npm run start        # Expo Dev Server。iOS/Android シミュレータか Expo Go で開く
npm run typecheck    # tsc --noEmit
```

ローカルで本番以外のデータに向ける場合:

```bash
EXPO_PUBLIC_DATA_URL=http://localhost:8000/data/models.json npm run start
```

## ビルド・配布（EAS）

```bash
npm install -g eas-cli
eas login
eas build --platform all --profile preview   # 内部配布（TestFlight / Play内部テスト）
eas update                                    # JS の OTA 更新
```

CI（`.github/workflows/app.yml`）は `app/**` 変更時のみ型チェックを実行。`EXPO_TOKEN`
シークレットがある場合のみ EAS ビルドを実行する（既存の GCP デプロイとは独立）。

## スコープ外（Phase 2 以降）

Push通知（Expo Push + トークン保管 + 日次ジョブからの送信）、ブックマーク/既読のクラウド同期。
