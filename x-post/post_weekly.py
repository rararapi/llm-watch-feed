"""importance=A の記事を X にスレッド投稿する（週次・金曜 20:00 実行）。

使い方:
    python x-post/post_weekly.py            # 実際に投稿
    python x-post/post_weekly.py --dry-run  # 投稿内容をコンソールに出力のみ

前提:
    - x-post/save_session.py で playwright_session.json を生成済みであること
    - .env に SITE_URL=https://your-project.web.app が設定されていること
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SESSION_PATH = Path(__file__).parent / "playwright_session.json"
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
DAYS_BACK = 7


def fetch_articles() -> list[dict]:
    """Firebase Hosting から models.json を取得し importance=A・過去7日の記事を返す。"""
    url = f"{SITE_URL}/data/models.json"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        articles = resp.json()
    except Exception as e:
        logger.error("models.json の取得に失敗しました: %s", e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    result = []
    for a in articles:
        if a.get("importance") != "A":
            continue
        try:
            pub = datetime.fromisoformat(a["published_at"])
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if pub >= cutoff:
            result.append(a)

    result.sort(key=lambda a: a["published_at"], reverse=True)
    return result


def build_tweets(articles: list[dict]) -> list[str]:
    """投稿するツイート文のリストを組み立てる。"""
    now = datetime.now(timezone.utc).astimezone()
    week_start = (now - timedelta(days=6)).strftime("%-m/%-d")
    week_end = now.strftime("%-m/%-d")

    header = (
        f"🤖 今週のAIニュース（{week_start}〜{week_end}）\n"
        f"重要アップデート {len(articles)}件 👇"
    )
    tweets = [header]

    for a in articles:
        title = a.get("title", "")
        summary = a.get("summary", "")
        url = a.get("url", "")
        body = f"📌 {title}\n\n{summary}\n\n{url}"
        # 280字超えた場合は summary を末尾カット
        if len(body) > 280:
            overflow = len(body) - 280 + 1
            summary = summary[: len(summary) - overflow] + "…"
            body = f"📌 {title}\n\n{summary}\n\n{url}"
        tweets.append(body)

    return tweets


def post_thread(tweets: list[str]) -> None:
    """Playwright でブラウザを操作し X にスレッド投稿する。"""
    if not SESSION_PATH.exists():
        logger.error(
            "セッションファイルが見つかりません。先に save_session.py を実行してください: %s",
            SESSION_PATH,
        )
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(SESSION_PATH))
        page = context.new_page()

        page.goto("https://x.com/compose/post")
        page.wait_for_load_state("networkidle")

        editor = page.locator('[data-testid="tweetTextarea_0"]')
        editor.wait_for(state="visible", timeout=15000)
        editor.fill(tweets[0])
        logger.info("ヘッダツイートを入力しました")

        for i, tweet in enumerate(tweets[1:], start=1):
            add_btn = page.locator('[data-testid="addButton"]')
            add_btn.wait_for(state="visible", timeout=10000)
            add_btn.click()

            next_editor = page.locator(f'[data-testid="tweetTextarea_{i}"]')
            next_editor.wait_for(state="visible", timeout=10000)
            next_editor.fill(tweet)
            logger.info("記事ツイート %d/%d を入力しました", i, len(tweets) - 1)

        submit_btn = page.locator('[data-testid="tweetButton"]')
        submit_btn.wait_for(state="visible", timeout=10000)
        submit_btn.click()
        page.wait_for_timeout(3000)
        logger.info("スレッドを投稿しました（%d件）", len(tweets))

        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="投稿せずに内容を出力するだけ")
    args = parser.parse_args()

    if not SITE_URL:
        logger.error("SITE_URL が設定されていません。.env を確認してください。")
        sys.exit(1)

    articles = fetch_articles()
    if not articles:
        logger.info("投稿対象の記事がありません（importance=A・過去%d日）。", DAYS_BACK)
        return

    tweets = build_tweets(articles)

    if args.dry_run:
        print(f"\n=== ドライラン: {len(tweets)}ツイート ===\n")
        for i, t in enumerate(tweets):
            print(f"--- [{i + 1}] ({len(t)}字) ---")
            print(t)
            print()
        return

    try:
        post_thread(tweets)
    except Exception as e:
        logger.error("投稿中にエラーが発生しました: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
