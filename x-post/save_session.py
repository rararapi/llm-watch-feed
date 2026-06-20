"""X のブラウザセッションを保存する（初回1回だけ手動実行）。

実行方法:
    python x-post/save_session.py

ブラウザが開くので X にログインし、ホーム画面が表示されたら Enter を押す。
playwright_session.json にセッションが保存される。
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

SESSION_PATH = Path(__file__).parent / "playwright_session.json"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://x.com/login")

        print("ブラウザで X にログインしてください。")
        print("ホーム画面が表示されたら Enter を押してください...")
        input()

        context.storage_state(path=str(SESSION_PATH))
        browser.close()

    print(f"セッションを保存しました: {SESSION_PATH}")


if __name__ == "__main__":
    main()
