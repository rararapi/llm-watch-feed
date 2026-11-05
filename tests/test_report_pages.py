import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReportPagesTests(unittest.TestCase):
    def test_site_displays_sources_and_preserves_shared_article_links(self):
        def article(url, title):
            return {
                "url": url, "id": hashlib.sha256(url.encode()).hexdigest(),
                "source": "News", "importance": "B", "title": title,
            }

        primary = article("https://news.example/item", "<Weekly & News>")
        revised = article(primary["url"] + "?utm_source=rss", "URL variant")
        occupied = article("https://news.example/independent", "Independent article")
        occupied["previous_article_ids"] = ["../unexpected", None, {"unexpected": "object"}]
        secondary = article("https://other.example/report?a=1&b=2", "<Other report>")
        unsafe = article("javascript:alert(1)", "Unsafe")
        primary["other_reports"] = [secondary, unsafe, occupied]

        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            models = work / "models.json"
            models.write_text(json.dumps([primary, revised, occupied]), encoding="utf-8")
            site = "https://site.example"
            env = dict(os.environ, MODELS_JSON_PATH=str(models), PAGES_DIR=str(work / "pages"),
                       SHARED_META_PATH=str(work / "meta.json"), SITE_URL=site)
            subprocess.run([sys.executable, "scripts/generate_pages.py"], cwd=ROOT, env=env,
                           capture_output=True, check=True)
            pages = work / "pages" / "articles"
            primary_html = (pages / f"{primary['id']}.html").read_text(encoding="utf-8")
            self.assertIn("同じニュースを報じた記事", primary_html)
            self.assertIn('href="https://other.example/report?a=1&amp;b=2"', primary_html)
            self.assertIn("&lt;Other report&gt;", primary_html)
            self.assertNotIn(unsafe["url"], primary_html)
            self.assertFalse((pages / f"{unsafe['id']}.html").exists())
            target = f"{site}/articles/{primary['id']}.html"
            for alias in (revised, secondary):
                redirect = (pages / f"{alias['id']}.html").read_text(encoding="utf-8")
                self.assertIn(f'<link rel="canonical" href="{target}">', redirect)
                self.assertIn(f'content="0; url={target}"', redirect)
                self.assertIn("&lt;Weekly &amp; News&gt;", redirect)
            independent_html = (pages / f"{occupied['id']}.html").read_text(encoding="utf-8")
            self.assertIn('class="article__title">Independent article', independent_html)
            self.assertNotIn("同じニュースを報じた記事", independent_html)
            self.assertFalse((work / "pages" / "unexpected.html").exists())
            index = (work / "pages" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn(revised["id"], index)


if __name__ == "__main__":
    unittest.main()
