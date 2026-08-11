import unittest

from scripts.compose_newsletter import NewsletterValidationError, render_newsletter, validate_newsletter


ARTICLES = {
    "h1": {
        "article_id": "h1",
        "title": "Safe title",
        "source": "Example",
        "url": "https://example.com/story",
        "matched_interests": ["sports"],
    },
    "h2": {
        "article_id": "h2",
        "title": "Another title",
        "source": "Example",
        "url": "javascript:alert(1)",
        "matched_interests": ["sports"],
    },
}


def draft(**overrides):
    value = {
        "subject": "Morning briefing",
        "for_you": [{"article_id": "h1", "category": "sports", "summary": "A <summary>."}],
        "general": [{"article_id": "h2", "summary": "General news."}],
        "market_summary": "Markets were mixed.",
        "footer": "Sports was the only active category today.",
    }
    value.update(overrides)
    return value


class NewsletterValidationTests(unittest.TestCase):
    def test_accepts_valid_source_bound_selection(self):
        newsletter = validate_newsletter(draft(), ARTICLES)
        html = render_newsletter(newsletter)
        self.assertIn('href="https://example.com/story"', html)
        self.assertIn("A &lt;summary&gt;.", html)
        self.assertNotIn("javascript:", html)

    def test_rejects_unknown_or_duplicate_articles(self):
        unknown = draft(for_you=[{"article_id": "missing", "category": "sports", "summary": "x"}])
        with self.assertRaises(NewsletterValidationError):
            validate_newsletter(unknown, ARTICLES)
        duplicate = draft(general=[{"article_id": "h1", "summary": "x"}])
        with self.assertRaises(NewsletterValidationError):
            validate_newsletter(duplicate, ARTICLES)

    def test_rejects_category_cap_violation(self):
        articles = {**ARTICLES, "h3": {**ARTICLES["h2"], "article_id": "h3"}, "h4": {**ARTICLES["h2"], "article_id": "h4"}}
        for_you = [
            {"article_id": article_id, "category": "sports", "summary": "x"}
            for article_id in ("h1", "h3", "h4")
        ]
        with self.assertRaises(NewsletterValidationError):
            validate_newsletter(draft(for_you=for_you, general=[]), articles)


if __name__ == "__main__":
    unittest.main()
