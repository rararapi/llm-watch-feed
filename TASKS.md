# TASKS — LLM Model Watch Feed

リポジトリの目的「AI（LLMモデル）ニュースを収集し GitHub Pages で公開、GitHub Actions で定時収集」を達成するためのタスク一覧。
済み / 未済を整理する内部向けドキュメント（`docs/` は全公開のため、ここはリポジトリ直下に置く）。

- 最終更新: 2026-06-07
- スコープ前提: CLAUDE.md に従い、対象は **「LLMモデル情報のみ」**（AIニュース全般ではない）。この範囲を広げるかは [D9](#d-スコープの意思決定) 参照。

---

## ✅ 済み（コード上で確認済み）

| 項目 | 実体 |
|---|---|
| ニュース収集スクリプト | `scripts/collect.py` … RSS取得 → OpenAIでモデル関連判定 → `models.json`追記、SHA-256で重複排除、1回最大10件・上限500件 |
| RSSフィード生成 | `scripts/generate_feeds.py` … 6種XML（all / major-models / coding / multimodal / open-models / pricing） |
| 公開サイト | `docs/index.html`（Vanilla JS）＋ `docs/data/models.json` ＋ `docs/feeds/*.xml` ＋ `.nojekyll` |
| 定時収集ワークフロー | `.github/workflows/collect.yml` … 火・金 09:00 JST cron＋手動実行、変更時のみcommit/push、`SITE_URL`自動注入 |
| 依存・環境定義 | `requirements.txt` / `.env.example` |
| ドキュメント | `README.md` / `docs/power-automate.html` |
| 初期データ | `models.json` にシード4件 |

---

## ❌ 未済 / 要対応

### A. GitHub 側の設定（リポジトリ Settings 上の作業・要確認）
- [ ] **A1. GitHub Pages 有効化** — Settings → Pages → Source を `main / docs`。デプロイ専用workflowが無いため**この手動設定が必須**。
- [ ] **A2. Secrets 登録** — `OPENAI_API_KEY` をリポジトリ Secrets に登録。未登録だと定時収集が毎回失敗。
- [ ] **A3.（任意）`OPENAI_MODEL`** を Variables に設定（未設定なら `gpt-4.1-mini`）。
- [ ] **A4. 初回手動実行** — workflow_dispatch で「収集 → 公開」までスモークテスト。

### B. ドキュメントと実装の不整合
- [ ] **B5. CLAUDE.md の RSS_SOURCES を実装に合わせる** — CLAUDE.md は Anthropic / HF Papers を記載するが、実装(`collect.py`)は Anthropic 無し・Google Developers Blog / Microsoft AI Blog を追加（コミット `48eddf2` で差し替え済）。
- [ ] **B6. `SITE_URL` のプレースホルダ** (`your-username.github.io/...`) の扱いを明記。Actions経由は自動注入で実害低、ローカル生成時のみ注意。

### C. 品質・運用（任意・今後）
- [ ] **C7. テスト/CI** — Lint・`models.json`スキーマ検証の自動化（現状は try/except 保護のみ）。
- [ ] **C8. 拡張候補**（CLAUDE.md 由来）— Slack通知 / 週次サマリー / 英語フィード / 類似記事マージ / タグ正規化 / 実行頻度変更 等。

### D. スコープの意思決定
- [ ] **D9. 対象範囲の確定** — 実装は「LLMモデル情報のみ」。AIニュース全般へ広げるか現状維持かを決定。広げる場合は SYSTEM_PROMPT の判定基準と `model_type`/`importance` 設計の見直しが必要。

---

## 🆕 E. ニュース収集対象の調査・選定（今回追加）

収集ソース（RSS_SOURCES）の品質がフィード全体の価値を直接左右する。コミット履歴（`48eddf2 fix: replace broken RSS sources`）が示すとおり、**ソースは壊れる・古くなる前提で定期的な調査と入れ替えが必要**。これを単発でなく運用タスクとして定義する。

### E1. 選定基準の明文化
- [ ] 採否を判断する基準を定義し、CLAUDE.md または本書に記載する。最低限の評価軸:
  - **RSSの有無/形式** … 公式RSS/Atomがあるか、`feedparser` で解析可能か
  - **更新頻度・活性** … 直近の投稿日、死んでいないか
  - **シグナル/ノイズ比** … モデル情報の割合（採用/募集・イベント告知中心は不適）
  - **一次情報性** … モデル提供者の公式か、二次まとめか
  - **言語** … 日英中心（要約はja前提）
  - **重複** … 既存ソースと内容が大きく被らないか
  - **安定性** … URLが変わりやすくないか（過去の破損実績）

### E2. 候補ソースの洗い出しと現状監査
- [ ] 現行5ソースの稼働状況を再確認（OpenAI / Google DeepMind / Google Developers Blog / Hugging Face Blog / Microsoft AI Blog）。
- [ ] 主要モデル提供者で未収録の候補を調査。優先度高:
  - **Anthropic**（`https://www.anthropic.com/news/rss.xml` — 過去に不調、要再検証）
  - **Meta AI** / **Mistral** / **xAI** / **Cohere** / **AI21**
  - **Alibaba Qwen** / **DeepSeek** / **Stability AI** 等のオープン/海外勢
  - **Hugging Face Papers**（`https://huggingface.co/papers/rss` — CLAUDE.md記載だが実装から外れている、要再検証）
- [ ] 各候補を E1 の基準でスコアリングし、採否を表で記録。

### E3. 技術検証（追加前の動作確認）
- [ ] 候補URLを `feedparser` で実際に取得し、`entries` が取れるか・日付/本文フィールドが揃うかを確認。
- [ ] レート制限/User-Agent/リダイレクトの挙動を確認（`collect.py` は1ソース失敗で全体が落ちない設計だが、無駄な失敗は減らす）。

### E4. 反映と整合
- [ ] 採用ソースを `scripts/collect.py` の `RSS_SOURCES` に追加。
- [ ] **CLAUDE.md の RSS_SOURCES 節を必ず同期**（[B5](#b-ドキュメントと実装の不整合) と連動。実装とドキュメントの乖離を再発させない）。
- [ ] 1記事の取り込み件数上限（`MAX_NEW_ARTICLES`）やコストへの影響を確認。

### E5. 定期レビューの仕組み化
- [ ] ソースの死活・ノイズ比を定期点検する運用を決める（例: 四半期ごとに本書のソース監査表を更新）。
- [ ] 破損ソース検知のため、収集時に「entries 0件が継続するソース」をログ/警告する仕組みを検討（C7と連動可）。

---

## 進め方メモ

最優先は **A（Pages有効化 → Secrets登録 → 手動実行）**。これで「収集→公開→定時運用」が実際に回り始める。
ソース品質を上げる **E** はその後の継続タスク。**B5/E4** はドキュメント同期を伴うため必ずセットで対応する。
