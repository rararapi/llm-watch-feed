"""Conservatively recognize syndicated copies without calling Vertex AI."""

import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache


_WINDOW = timedelta(days=3)
_TAG = re.compile(r"</?[a-zA-Z][\w:-]*(?:\s+[^<>]*)?\s*/?>")
_DUMMY_NOTICE = "(vertex ai未設定のため自動生成されたダミー文章です)"
_NUMBER = re.compile(r"[$€£¥+−-]?\d+(?:[.,]\d+)*(?:[%$€£¥])?")
_RECURRING = re.compile(
    r"\b(?:daily|weekly|monthly)\b.*\b(?:news|updates?|roundup|digest|briefing|newsletter|recap)\b"
    r"|(?:日刊|週刊|月刊|今週の|今日の|今月の).*(?:まとめ|ニュース|ダイジェスト)"
)
_BOILERPLATE = re.compile(
    r"\b(?:subscribe to|sign in to|read the full article|this post (?:first )?appeared on)\b"
    r"|(?:続きを読む|会員登録して|ログインして)"
)


@lru_cache(maxsize=4096)
def _text(value: str) -> str:
    value = html.unescape(_TAG.sub(" ", value))
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.split()).removeprefix(_DUMMY_NOTICE).strip()


@lru_cache(maxsize=4096)
def parse_timestamp(value: str) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _date(article: dict) -> datetime | None:
    return parse_timestamp(article.get("published_at") or "") or parse_timestamp(
        article.get("collected_at") or ""
    )


@lru_cache(maxsize=4096)
def _substantive(value: str, min_length: int) -> bool:
    letters = [c for c in value if c.isalnum()]
    return len(letters) >= min_length and len(set(letters)) >= 8


@lru_cache(maxsize=4096)
def _usable_body(value: str) -> str:
    text = _text(value)
    return text if _substantive(text, 24) and not _BOILERPLATE.search(text) else ""


def _bodies(article: dict) -> set[str]:
    texts = {_usable_body(article.get(field) or "") for field in ("excerpt", "body", "summary")}
    return texts - {""}


def same_content(a: dict, b: dict) -> bool:
    """Match a recent verbatim headline or sufficiently detailed copy."""
    date_a, date_b = _date(a), _date(b)
    if date_a is None or date_b is None or abs(date_a - date_b) > _WINDOW:
        return False

    title_a, title_b = _text(a.get("title") or ""), _text(b.get("title") or "")
    if title_a == title_b and _substantive(title_a, 18):
        if not _RECURRING.search(title_a) and not _BOILERPLATE.search(title_a):
            bodies_a, bodies_b = _bodies(a), _bodies(b)
            return not bodies_a or not bodies_b or bool(bodies_a & bodies_b)

    # Syndicated series may share an introductory paragraph across numbered parts.
    numbers_a, numbers_b = _NUMBER.findall(title_a), _NUMBER.findall(title_b)
    if numbers_a and numbers_b and numbers_a != numbers_b:
        return False
    return any(_substantive(t, 55) for t in _bodies(a) & _bodies(b))
