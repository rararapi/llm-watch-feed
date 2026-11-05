import unittest

from scripts.exact_story import same_content


def article(title, date="2026-10-17T00:00:00Z", **fields):
    return {"title": title, "published_at": date, **fields}


class ExactStoryTests(unittest.TestCase):
    def test_same_detailed_title_after_markup_case_and_width_cleanup(self):
        title = "Meta removes language that raised scraping & AI training concerns"
        self.assertTrue(same_content(
            article(title, source="Publisher A"),
            article("<b>META</b> removes language that raised scraping &amp; ＡＩ training concerns",
                    source="Publisher B"),
        ))

    def test_verbatim_syndicated_body_can_have_a_different_headline(self):
        text = "The Grid Protectors Program will supply emergency power from a Georgia data center to the local electrical grid."
        original = article("Introducing the Grid Protectors Program", excerpt=f"<p>{text}</p>")
        translated = article("電力会社とOpenAIが新たなプログラムを発表",
                             summary=f"（Vertex AI未設定のため自動生成されたダミー文章です） {text}")
        self.assertTrue(same_content(original, translated))
        self.assertTrue(same_content(translated, original))

    def test_shared_headline_with_conflicting_specific_details_needs_review(self):
        title = "New AI models are available to developers today"
        a = article(title, summary="Acme has released its first open model for Italian speech recognition.")
        b = article(title, summary="Peak launched its retrieval model aimed at enterprise search workloads.")
        self.assertFalse(same_content(a, b))
        self.assertTrue(same_content(a, article(title)))
        self.assertTrue(same_content(a, article(title, excerpt=a["summary"])))

    def test_same_series_introduction_does_not_merge_parts_or_releases(self):
        intro = "This detailed technical series evaluates approaches to scaling TensorRT performance across multiple build routes."
        for left, right in (("Global Performance Tuner, Part 1", "Global Performance Tuner, Part 2"),
                            ("Introducing Gemini 3.7 Flash", "Introducing Gemini 3.8 Flash"),
                            ("New API price $20", "New API price €20"),
                            ("Benchmark score change of +12%", "Benchmark score change of -12%")):
            with self.subTest(left=left):
                self.assertFalse(same_content(article(left, summary=intro), article(right, summary=intro)))

    def test_short_generic_titles_digest_and_subscription_text(self):
        boilerplate = "Subscribe to our newsletter to get access to exclusive analysis of the most important technology stories this week."
        for title in ("What's new", "Weekly artificial intelligence news roundup",
                      "Subscribe to our newsletter for the latest news", "今週のAI開発者向けニュースまとめ"):
            with self.subTest(title=title):
                self.assertFalse(same_content(article(title, excerpt=boilerplate), article(title, summary=boilerplate)))
        notice = "（Vertex AI未設定のため自動生成されたダミー文章です）"
        self.assertFalse(same_content(article("A", summary=notice), article("B", summary=notice)))

    def test_dates_use_publication_even_when_articles_are_collected_together(self):
        title = "A detailed update to the intelligence index for frontier models"
        a = article(title, "Thu, 01 Oct 2026 12:00:00 +0900", collected_at="2026-11-05")
        self.assertFalse(same_content(a, article(title, "2026-10-15", collected_at="2026-11-05")))
        self.assertTrue(same_content(a, article(title, "invalid", collected_at="2026-10-02")))
        self.assertFalse(same_content(a, article(title, "")))
