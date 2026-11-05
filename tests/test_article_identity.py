import hashlib
import unittest

from scripts.article_identity import article_key, new_candidates, unique_articles


class ArticleIdentityTests(unittest.TestCase):
    def test_tracking_and_anchors_share_identity_but_article_parameters_and_routes_do_not(self):
        url = "https://example.org/read?id=7"
        variant = "https://EXAMPLE.org:443/read?utm_source=rss&id=7&fbclid=x#summary"
        self.assertEqual(article_key(url), article_key(variant))
        for other in (
            "https://example.org/read?id=8",
            "https://example.org/read?id=7&lang=en",
            url + "#/story/2",
            url + "#!story/3",
            "https://example.org:8443/read?id=7",
        ):
            with self.subTest(other=other):
                self.assertNotEqual(article_key(url), article_key(other))
        self.assertNotEqual(article_key(url + "#/story/1"), article_key(url + "#/story/2"))

    def test_technology_review_article_id_survives_date_and_slug_changes(self):
        base = "https://www.technologyreview.com"
        old = "/2026/10/08/1146224/roundtables-a-conversation-with-the-creator-of-ai-designed-viruses/"
        new = "/2026/10/16/1146224/updated-story-slug/"
        self.assertEqual(article_key(base + old), article_key(base + new))
        self.assertNotEqual(article_key(base + old), article_key(base + new.replace("1146224", "1146225")))
        self.assertNotEqual(article_key("https://other.org" + old), article_key("https://other.org" + new))

    def test_malformed_url_does_not_break_the_batch(self):
        bad = "https://example.org:bad/story"
        records = [{"url": bad}, {"url": bad}, {"url": "https://[bad/"}, {"url": "https://ok.org"}]
        self.assertEqual(new_candidates([records], set(), 10), [records[0], records[2], records[3]])

    def test_migration_preserves_visible_id_order_and_existing_image_data(self):
        hidden = {
            "id": "hidden", "url": "https://a.org/story", "importance": "C",
            "image_generated_url": "https://images.org/hidden.webp", "image_generated_alt": "画像",
        }
        independent = {"id": "independent", "url": "https://b.org", "importance": "A", "title": "Same title"}
        visible = {
            "id": "published", "url": "https://a.org/story?utm_source=feed", "importance": "B",
            "image_url": "https://a.org/og.jpg", "title": "Same title",
        }
        # Legacy copies can match one another by URL or by a pre-existing public ID.
        last = dict(visible, url="https://a.org/alternate", importance="A")
        rows = [hidden, independent, visible, last]
        cleaned = unique_articles(rows)
        self.assertEqual([a["id"] for a in cleaned], ["published", "independent"])
        self.assertEqual(cleaned[0]["url"], visible["url"])
        self.assertEqual(cleaned[0]["image_url"], visible["image_url"])
        self.assertEqual(cleaned[0]["image_generated_alt"], "画像")
        self.assertEqual(unique_articles(cleaned), cleaned)
        self.assertNotIn("image_generated_url", visible)

    def test_round_robin_skips_seen_and_within_batch_duplicates_before_budget(self):
        seen_url = "https://a.org/seen"
        seen = {article_key(seen_url)}
        shared = {"url": "https://news.org/1"}
        repeat = {"url": shared["url"] + "?utm_campaign=rss"}
        first = [{"url": seen_url}, shared, repeat, {"url": "https://news.org/3"}]
        second = [repeat, {"url": "https://news.org/2"}]
        self.assertEqual(new_candidates([first, second], seen, 2), [shared, second[1]])
        self.assertEqual(new_candidates([first, second], seen, 10), [shared, second[1], first[-1]])
        self.assertEqual(new_candidates([first], seen, 0), [])
        self.assertEqual(seen, {article_key(seen_url)})

    def test_migration_keeps_unique_related_reports(self):
        url = "https://a.org/article"
        report = {"source": "B", "title": "Second report", "url": "https://b.org/news"}
        newer = {"source": "C", "title": "Third report", "url": "https://c.org/news"}
        first = {"id": "original", "url": url, "other_reports": [report]}
        second = {
            "id": "updated", "url": url + "?utm_campaign=t",
            "other_reports": [dict(report, url=report["url"] + "#section"), {"url": url}, newer],
        }
        self.assertEqual(unique_articles([first, second])[0]["other_reports"], [report, newer])

    def test_shared_legacy_id_keeps_distinct_report_out_of_future_runs(self):
        first = {"id": "legacy", "url": "https://a.org/news", "importance": "B"}
        second = {
            "id": "legacy", "url": "https://b.org/story", "source": "B",
            "title": "A second report", "importance": "A", "model_type": "Coding", "tags": ["API"],
            "published_at": "2026-10-17T00:00:00Z",
        }
        tracking = dict(second, url=second["url"] + "?utm_source=rss")
        record, = unique_articles([first, second, tracking])
        self.assertEqual(record["other_reports"], [{k: v for k, v in second.items() if k != "id"}])
        self.assertEqual(record["previous_article_ids"], [hashlib.sha256(tracking["url"].encode()).hexdigest()])
        seen = {article_key(report["url"]) for report in [record, *record["other_reports"]]}
        self.assertEqual(new_candidates([[second, tracking]], seen, 10), [])
        self.assertEqual(unique_articles([record]), [record])


if __name__ == "__main__":
    unittest.main()
