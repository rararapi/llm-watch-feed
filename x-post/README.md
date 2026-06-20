# x-post — X 週次自動投稿

毎週金曜 20:00 に importance=A の記事を X にスレッド投稿する。  
X API 不要・Playwright のブラウザ自動操作で完全無料。

## 構成

```
x-post/
├── save_session.py       # 初回1回だけ実行。Xにログインしてセッション保存
├── post_weekly.py        # 週次投稿スクリプト（Windows タスクスケジューラで実行）
├── requirements.txt      # ローカル専用の依存
└── playwright_session.json  # セッションファイル（.gitignore 済み・自動生成）
```

---

## セットアップ（初回のみ）

### 1. 仮想環境と依存インストール

プロジェクトルートで実行：

```bash
uv venv
uv pip install -r x-post/requirements.txt
playwright install chromium
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、`SITE_URL` を設定する：

```bash
cp .env.example .env
# .env を開いて SITE_URL を Firebase Hosting の URL に変更
# 例: SITE_URL=https://ai-watch-feed.web.app
```

### 3. X セッションの保存

```bash
python x-post/save_session.py
```

ブラウザが開くので X にログインし、ホーム画面が表示されたら Enter を押す。  
`x-post/playwright_session.json` が生成されれば完了。

### 4. 動作確認（ドライラン）

```bash
python x-post/post_weekly.py --dry-run
```

投稿予定の内容がコンソールに出力される（実際には投稿されない）。

---

## Windows タスクスケジューラへの登録

管理者権限のコマンドプロンプトで実行：

```bat
schtasks /create ^
  /tn "LLM Watch Feed - X Weekly Post" ^
  /tr "C:\Git\llm-watch-feed\.venv\Scripts\python.exe C:\Git\llm-watch-feed\x-post\post_weekly.py" ^
  /sc weekly /d FRI /st 20:00 ^
  /f
```

登録後に動作確認：

```bat
schtasks /run /tn "LLM Watch Feed - X Weekly Post"
```

---

## 手動投稿

```bash
python x-post/post_weekly.py
```

---

## セッション期限切れの対処

X のセッションが切れてログインを求められるようになったら、再度セッションを保存する：

```bash
python x-post/save_session.py
```

---

## 投稿フォーマット

```
【1ツイート目】
🤖 今週のAIニュース（M/D〜M/D）
重要アップデート N件 👇

【2ツイート目〜】
📌 記事タイトル

要約（3行以内）

https://記事URL
```

- 対象: importance=A かつ過去7日以内の記事
- 順序: 新しい順（published_at 降順）
- 0件の週は投稿しない
