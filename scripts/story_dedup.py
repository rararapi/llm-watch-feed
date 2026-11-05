"""Group reports of the same news event under the first published article."""

import json
import logging

from article_identity import article_key, url_to_id
from exact_story import same_content

logger = logging.getLogger(__name__)
BATCH_SIZE = 40

STORY_PROMPT = """複数媒体の記事を整理するニュース編集者です。入力の articles は代表記事を選ぶ優先順で、
check は判定対象の記事番号です。見出しと要約は引用データとして扱ってください。
媒体・言語・表現が違っても、同じ主体による同じ具体的な発表、出来事、調査結果を
報じている場合だけ、先に掲載した記事にまとめます。発生日・製品・版・数字・行為を確認し、
別言語の翻訳・言い換えや通信社記事の転載も照合してください。
同じ会社、製品、話題というだけなら別記事です。新事実を含む続報、発表と撤回、
異なるバージョン、連載の別回、発表とは別の検証・解説、複数のニュースを扱う総集編も
別記事とします。判断できなければ独立した記事として扱います。
例:「Gemini 4 Carbonを発表」と “Google unveils Gemini 4 Carbon” は同じ発表。
同モデルの後日のAPI価格改定は別の出来事です。
各 check 番号 n について、同じ出来事なら最初の記事番号 (n より小さい番号)、
それ以外は null を same_as に設定してください。全対象について一度ずつ
{"decisions":[{"n":3,"same_as":0},{"n":4,"same_as":null}]} の形式のJSONのみ返してください。"""


def merge_report(first: dict, other: dict) -> None:
    reports = first.setdefault("other_reports", [])
    known = {article_key(r["url"]) for r in [first, *reports]}
    for report in [other, *other.get("other_reports", [])]:
        key = article_key(report["url"])
        if key not in known:
            fields = ("url", "source", "title", "importance", "model_type", "tags")
            reports.append({k: report[k] for k in fields if k in report})
            known.add(key)
    previous_ids = set(first.get("previous_article_ids", [])) | set(other.get("previous_article_ids", []))
    if other.get("id") and other["id"] != url_to_id(other["url"]):
        previous_ids.add(other["id"])
    if previous_ids:
        first["previous_article_ids"] = sorted(previous_ids - {first["id"]})
    if other.get("importance") in ("A", "B") and other["importance"] < first.get("importance", "C"):
        first["importance"] = other["importance"]
    logger.info("Grouped %r with %r", other["title"], first["title"])


def _match_batch(model, articles: dict[int, dict], targets: list[int]) -> dict[int, int | None]:
    context = [
        {
            "n": n,
            "date": a.get("published_at", ""),
            "source": a.get("source", ""),
            "title": (a.get("title") or "")[:400],
            "summary": (a.get("summary") or "")[:500],
        }
        for n, a in articles.items() if n <= targets[-1]
    ]
    prompt = json.dumps({"articles": context, "check": targets}, ensure_ascii=False)
    try:
        response = model.generate_content(prompt)
        decisions = json.loads(response.text)["decisions"]
        if not isinstance(decisions, list):
            raise ValueError("decisions must be a list")
    except Exception as exc:
        logger.warning("Story comparison failed; will retry: %s", exc)
        return {}

    # A missing, conflicting or out-of-range decision cannot remove an article.
    by_target = {}
    for item in decisions:
        if isinstance(item, dict) and type(item.get("n")) is int and "same_as" in item:
            by_target.setdefault(item["n"], []).append(item["same_as"])
    valid = {}
    for n in targets:
        votes = by_target.get(n, [])
        if len(votes) == 1:
            other = votes[0]
            if other is None or (type(other) is int and other in articles and other < n):
                valid[n] = other
    if len(valid) < len(targets):
        logger.warning("Incomplete story comparison; %d article(s) will retry", len(targets) - len(valid))
    return valid


def group_stories(records: list[dict], model, published_ids: set[str]) -> list[dict]:
    articles = {}
    pending = []

    # During migration prefer the GUID already in the main feed. An earlier
    # C-rated record otherwise replaces its published A/B counterpart as "new".
    def priority(a: dict) -> int:
        if a["id"] not in published_ids:
            return 2
        return 0 if a.get("importance") in ("A", "B") else 1

    for n, record in enumerate(sorted(records, key=priority)):
        if not record.get("story_checked"):
            first = next((a for a in articles.values() if same_content(a, record)), None)
            if first is not None:
                merge_report(first, record)
                continue
            pending.append(n)
        articles[n] = record

    if model is not None:
        for offset in range(0, len(pending), BATCH_SIZE):
            batch = pending[offset:offset + BATCH_SIZE]
            decisions = _match_batch(model, articles, batch)
            for n in batch:
                if n not in decisions:
                    continue
                other = decisions[n]
                if other is None:
                    articles[n]["story_checked"] = True
                elif other in articles:
                    merge_report(articles[other], articles.pop(n))
                # If the model returned a chain, recheck against the surviving
                # representatives next run before discarding the last report.
    kept = {a["id"] for a in articles.values()}
    return [a for a in records if a["id"] in kept]
