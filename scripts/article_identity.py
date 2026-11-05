"""Identify already-published RSS articles without changing their public IDs or URLs."""

import hashlib
import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit


_TRACKING_PARAMS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
_MIT_ARTICLE = re.compile(r"^/\d{4}/\d{2}/\d{2}/(\d+)(?:/[^/]+)?/?$")
REPORT_FIELDS = (
    "url", "source", "title", "published_at", "published_at_estimated", "importance", "model_type", "tags",
)


def url_to_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def article_key(url: str) -> str:
    value = url.strip()
    try:
        parts = urlsplit(value)
        if parts.scheme in {"http", "https"} and parts.hostname and "@" not in parts.netloc:
            # Preserve the original query encoding, order, and all non-tracking parameters.
            query = []
            for field in parts.query.split("&"):
                name = unquote_plus(field.partition("=")[0]).lower()
                if not name.startswith("utm_") and name not in _TRACKING_PARAMS:
                    query.append(field)
            host = parts.hostname
            netloc = f"[{host}]" if ":" in host else host
            if parts.port is not None and parts.port != (443 if parts.scheme == "https" else 80):
                netloc += f":{parts.port}"
            path = parts.path or "/"
            # MIT Technology Review retains its numeric story ID after changing the date or slug.
            if host in {"www.technologyreview.com", "technologyreview.com"}:
                match = _MIT_ARTICLE.fullmatch(path)
                if match:
                    netloc = netloc.removeprefix("www.")
                    path = f"/{match[1]}"
            fragment = parts.fragment if parts.fragment.startswith(("/", "!", "?")) else ""
            value = urlunsplit((parts.scheme, netloc, path, "&".join(query), fragment))
    except ValueError:
        # A malformed link should only match another occurrence of that exact link.
        pass
    return url_to_id(value)


def unique_articles(articles: list[dict]) -> list[dict]:
    """Keep the first published copy of each article, even for records predating URL keys."""
    parents = list(range(len(articles)))
    by_identity = {}

    def group(index: int) -> int:
        while index != parents[index]:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    # A legacy ID and a URL variant can independently connect copies to the same group.
    for index, article in enumerate(articles):
        keys = []
        if article.get("id"):
            keys.append(("id", article["id"]))
        if article.get("url"):
            keys.append(("url", article_key(article["url"])))
        for key in keys:
            previous = by_identity.setdefault(key, index)
            parents[group(index)] = group(previous)

    groups = {}
    for index, article in enumerate(articles):
        groups.setdefault(group(index), []).append(article)

    result = []
    for copies in groups.values():
        first_visible = next((a for a in copies if a.get("importance") in ("A", "B")), copies[0])
        kept = first_visible.copy()
        primary_key = article_key(kept["url"]) if kept.get("url") else None
        reports_by_key = {}
        old_ids = set()
        for other in copies:
            old_ids.update(i for i in (other.get("previous_article_ids") or []) if isinstance(i, str))
            if other.get("id"):
                old_ids.add(other["id"])
            for report in [other, *(other.get("other_reports") or [])]:
                if not isinstance(report, dict) or not isinstance(report.get("url"), str) or not report["url"]:
                    continue
                old_ids.add(url_to_id(report["url"]))
                key = article_key(report["url"])
                if key != primary_key:
                    alias = reports_by_key.setdefault(key, {})
                    for field in REPORT_FIELDS:
                        if field in report:
                            alias.setdefault(field, report[field])
            if not kept.get("image_url") and other.get("image_url"):
                kept["image_url"] = other["image_url"]
            generated = other.get("image_generated_url")
            if not generated:
                continue
            if not kept.get("image_generated_url"):
                kept["image_generated_url"] = generated
                for field in ("image_generated_alt", "image_generated_prompt"):
                    kept.pop(field, None)
            if kept["image_generated_url"] == generated:
                for field in ("image_generated_alt", "image_generated_prompt"):
                    if not kept.get(field) and other.get(field):
                        kept[field] = other[field]
        reports = list(reports_by_key.values())
        if reports or "other_reports" in kept:
            kept["other_reports"] = reports
        # A changed URL can have an old public page even when it points to the same report.
        old_ids.discard(kept.get("id"))
        for report in [kept, *reports]:
            if report.get("url"):
                old_ids.discard(url_to_id(report["url"]))
        old_ids = {i for i in old_ids if isinstance(i, str) and re.fullmatch(r"[0-9a-f]{64}", i)}
        if old_ids or "previous_article_ids" in kept:
            kept["previous_article_ids"] = sorted(old_ids)
        result.append(kept)
    return result


def new_candidates(per_source: list[list[dict]], seen: set[str], limit: int) -> list[dict]:
    """Give each source one unseen article per round until the analysis budget is full."""
    used = seen.copy()
    candidates = []
    sources = [iter(articles) for articles in per_source]
    while sources and len(candidates) < limit:
        next_round = []
        for source in sources:
            for article in source:
                if not article.get("url"):
                    continue
                key = article_key(article["url"])
                if key in used:
                    continue
                used.add(key)
                candidates.append(article)
                if len(candidates) == limit:
                    return candidates
                next_round.append(source)
                break
        sources = next_round
    return candidates
