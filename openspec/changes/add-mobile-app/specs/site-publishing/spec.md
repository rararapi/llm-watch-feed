## ADDED Requirements

### Requirement: 表示定数を共有メタとして出力

サイト生成（`generate_pages.py`）は、ソース一覧・ソース表示色・重要度ラベル・モデル種別ラベル等の表示定数を、機械可読な共有定義 `shared/meta.json` としてSHALL出力する。これはモバイルアプリとWeb（SSG）が同一の表示定数を参照するための単一の真実とする。本出力の追加は既存のサイト生成物（`index.html` / `articles/` / `assets/` / `feeds/`）の内容・挙動を変更してはMUST NOT（純粋な追加出力）。`shared/meta.json` には機密情報・APIキーを含めてMUST NOT。

#### Scenario: サイト生成時にメタを出力
- **WHEN** `generate_pages.py` が実行される
- **THEN** ソース一覧・色・各種ラベルを含む `shared/meta.json` が生成され、既存のサイト生成物は従来どおり出力される

#### Scenario: 既存サイト出力への非干渉
- **WHEN** `shared/meta.json` 出力処理が失敗、または無効化される
- **THEN** 既存の `index.html` / `articles/` / `feeds/` の生成は影響を受けず完走する
