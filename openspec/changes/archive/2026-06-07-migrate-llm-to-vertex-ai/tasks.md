## 1. 依存の差し替え

- [x] 1.1 `requirements.txt` から `openai` を除去し、`google-cloud-aiplatform` を追加する
- [x] 1.2 `pip install -r requirements.txt` でインストールが通ることを確認する

## 2. collect.py の LLM クライアント実装

- [x] 2.1 `from openai import OpenAI` を Vertex AI SDK（`vertexai` / `google-cloud-aiplatform`）の import に置き換える
- [x] 2.2 `main()` の LLM 初期化を ADC ベースに変更する（`vertexai.init(project=GCP_PROJECT, location=VERTEX_LOCATION)`）。環境変数 `GCP_PROJECT` / `VERTEX_LOCATION` / `VERTEX_MODEL`（既定 `gemini-2.5-flash`）を読む
- [x] 2.3 利用可否判定を「`OPENAI_API_KEY` の有無」から「`GCP_PROJECT` 設定済み かつ ADC 初期化成功」に変更し、欠ける/失敗時は従来どおり `dummy_analysis()` にフォールバックする
- [x] 2.4 起動ログに LLM モード/ダミーモードのどちらで動くかを出力する

## 3. analyze() の置き換え

- [x] 3.1 `analyze()` を Gemini 呼び出し（`GenerativeModel(...).generate_content(...)`）に置き換え、`SYSTEM_PROMPT` を system 指示として渡す
- [x] 3.2 構造化出力を `response_mime_type="application/json"`（GenerationConfig）で指定し、現行の JSON 出力と等価にする
- [x] 3.3 既存の例外処理（`json.JSONDecodeError` / 一般例外で `None` を返しスキップ）を維持し、1 記事の失敗で全体が落ちないことを保つ。必要なら ```json フェンス除去の軽い後処理を入れる
- [x] 3.4 出力 JSON スキーマ（`is_model_related`/`model_type`/`importance`/`tags` 等）と `dummy_analysis()` は変更しない

## 4. 設定・ドキュメント更新

- [x] 4.1 `scripts/run_job.sh` とジョブ定義の env を `OPENAI_*` から `GCP_PROJECT`/`VERTEX_LOCATION`/`VERTEX_MODEL` に置き換える
- [x] 4.2 `CLAUDE.md` の環境変数表・RSSソース近辺の記述を更新（`OPENAI_API_KEY`/`OPENAI_MODEL` の記述を Vertex 系に差し替え）
- [x] 4.3 `DEPLOY.md` を更新（サービスアカウントへの `roles/aiplatform.user` 付与、Secret Manager の `OPENAI_API_KEY` 紐付け解除、ローカルでの `gcloud auth application-default login` 手順）

## 5. 動作確認

- [x] 5.1 ダミーモード確認: `GCP_PROJECT` 未設定で `python scripts/collect.py` を実行し、ダミー要約で完走・`models.json` に追記されることを確認する
- [x] 5.2 LLM モード確認: ローカルで ADC（`gcloud auth application-default login`）・`GCP_PROJECT=ai-watch-feed` の上で `python scripts/collect.py` を実行し、Gemini が model-related 判定・日本語要約・`model_type`/`importance` を返すことを確認済み（`aiplatform.googleapis.com` 有効化後）。
- [x] 5.3 `python scripts/generate_feeds.py` を実行し、RSS XML が `FEEDS_DIR` に生成されることを確認する
- [x] 5.4 ローカルのサイト（`docs/index.html`）が配信されることを確認する（`data/`・`feeds/` は実行時/デプロイ時に生成される成果物）
