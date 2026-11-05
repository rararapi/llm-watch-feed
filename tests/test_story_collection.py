import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect
import generate_feeds
from article_identity import article_key
from story_dedup import group_stories


def article(title, url, source="Example", **fields):
    return {
        "id": collect.url_to_id(url), "title": title, "url": url, "source": source,
        "published_at": "2026-10-28T10:00:00+00:00", "importance": "B",
        "excerpt": title, "summary": title, **fields,
    }


RELEASE = article("Google announces Gemini 4 Carbon", "https://google.example/carbon")
REPORT = article("Google、Gemini 4 Carbonを発表", "https://news.example/carbon", "国内紙")
FOLLOWUP = article("Gemini 4 CarbonのAPI料金を改定", "https://news.example/carbon-api", "国内紙")


def model_reply(prompt):
    # Independently check that the collector supplied comparable content from
    # existing records and from multiple publishers in the current batch.
    request = json.loads(prompt)
    titles = {a["title"]: a["n"] for a in request["articles"]}
    decisions = [
        {"n": n, "same_as": titles.get(RELEASE["title"]) if n == titles.get(REPORT["title"]) else None}
        for n in request["check"]
    ]
    return SimpleNamespace(text=json.dumps({"decisions": decisions}))


class StoryCollectionTests(unittest.TestCase):
    def test_multilingual_reports_group_across_batches_and_followup_remains(self):
        model = Mock()
        model.generate_content.side_effect = model_reply
        with patch("story_dedup.BATCH_SIZE", 1):
            records = group_stories([dict(RELEASE), dict(REPORT), dict(FOLLOWUP)], model, set())
        self.assertEqual([r["id"] for r in records], [RELEASE["id"], FOLLOWUP["id"]])
        self.assertEqual(records[0]["other_reports"][0]["url"], REPORT["url"])
        model.reset_mock()
        self.assertEqual(group_stories(records, model, {a["id"] for a in records}), records)
        model.generate_content.assert_not_called()

    def test_invalid_decisions_never_remove_an_article(self):
        model = Mock()
        for invalid in ([{"n": 1, "same_as": True}], [{"n": 1, "same_as": 99}],
                        [{"n": 1, "same_as": 0}, {"n": 1, "same_as": None}], []):
            with self.subTest(invalid=invalid):
                model.generate_content.return_value.text = json.dumps({"decisions": invalid})
                result = group_stories([dict(RELEASE), dict(FOLLOWUP)], model, set())
                self.assertEqual(result, [RELEASE, FOLLOWUP])

    def test_backfill_preserves_existing_visible_guid_and_topic_feed(self):
        hidden = {**REPORT, "importance": "C", "tags": ["Pricing"]}
        visible = dict(RELEASE)
        model = Mock()
        model.generate_content.side_effect = model_reply
        records = group_stories([hidden, visible], model, {hidden["id"], visible["id"]})
        self.assertEqual([r["id"] for r in records], [visible["id"]])
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(generate_feeds, "FEEDS_DIR", Path(tmp)):
                generate_feeds.generate_feed("pricing.xml", generate_feeds.FEED_CONFIGS["pricing.xml"], records)
            self.assertEqual(ElementTree.parse(Path(tmp, "pricing.xml")).findtext(".//item/guid"), visible["id"])

    def test_collect_rss_and_eviction_retry_share_one_identity(self):
        matcher = Mock()
        matcher.generate_content.side_effect = model_reply
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            path = Path(tmp, "models.json")
            stack.enter_context(patch.object(collect, "MODELS_JSON_PATH", path))
            stack.enter_context(patch.object(collect, "MAX_TOTAL_ARTICLES", 2))
            stack.enter_context(patch.object(collect, "RSS_SOURCES", ["official", "media"]))
            feeds = {"official": [RELEASE, RELEASE], "media": [REPORT, FOLLOWUP]}
            stack.enter_context(patch.object(collect, "fetch_source", side_effect=feeds.__getitem__))
            stack.enter_context(patch.object(collect, "build_model", return_value=matcher))
            analyze = stack.enter_context(patch.object(collect, "analyze", side_effect=lambda _, a: {
                "is_model_related": True, "importance": "B", "summary": a["title"],
            }))
            og = stack.enter_context(patch.object(collect, "fetch_og_image", return_value=None))

            collect.main()
            records = collect.load_existing()
            self.assertEqual([r["id"] for r in records], [RELEASE["id"], FOLLOWUP["id"]])
            self.assertEqual(records[0]["other_reports"][0]["source"], REPORT["source"])
            self.assertEqual(analyze.call_count, 3)
            self.assertEqual(og.call_count, 2)
            stack.enter_context(patch.object(generate_feeds, "MODELS_JSON_PATH", path))
            stack.enter_context(patch.object(generate_feeds, "FEEDS_DIR", Path(tmp, "feeds")))
            generate_feeds.main()
            xml = ElementTree.parse(Path(tmp, "feeds/all.xml"))
            self.assertEqual([g.text for g in xml.findall(".//item/guid")], [r["id"] for r in records])

            # The already-published story has left the 500-record window. Both
            # its representative and the other publisher's URL must stay seen.
            feeds["media"].append(article("Independent research", "https://example.org/research"))
            collect.main()
            self.assertEqual(len(collect.load_existing()), 2)
            archive = json.loads(Path(str(path) + ".archive.json").read_text())
            self.assertEqual(set(archive), {article_key(RELEASE["url"]), article_key(REPORT["url"])})
            feeds["media"][0] = {**REPORT, "url": REPORT["url"] + "?utm_source=rss"}
            snapshot = path.read_bytes()
            analyze.reset_mock()
            collect.main()
            analyze.assert_not_called()
            self.assertEqual(path.read_bytes(), snapshot)

    def test_failed_comparison_keeps_published_story_and_retries_new_one(self):
        matcher = Mock()
        matcher.generate_content.side_effect = RuntimeError("timeout")
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            path = Path(tmp, "models.json")
            stack.enter_context(patch.object(collect, "MODELS_JSON_PATH", path))
            stack.enter_context(patch.object(collect, "RSS_SOURCES", ["media"]))
            stack.enter_context(patch.object(collect, "fetch_source", return_value=[REPORT]))
            stack.enter_context(patch.object(collect, "build_model", return_value=matcher))
            stack.enter_context(patch.object(collect, "analyze", return_value={
                "is_model_related": True, "summary": REPORT["title"], "importance": "B",
            }))
            stack.enter_context(patch.object(collect, "fetch_og_image", return_value=None))
            collect.save_articles([dict(RELEASE)])
            collect.main()
            self.assertEqual(collect.load_existing(), [RELEASE])
            matcher.generate_content.side_effect = model_reply
            collect.main()
            records = collect.load_existing()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["other_reports"][0]["url"], REPORT["url"])


if __name__ == "__main__":
    unittest.main()
