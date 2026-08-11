import json
import unittest

from scripts.compose_newsletter import NewsletterValidationError, _request, render_newsletter, validate_newsletter


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
        "for_you": [{"article_id": "h1", "summary": "A <summary>."}],
        "general": [{"article_id": "h2", "summary": "General news."}],
        "footer": "Sports was the only active category today.",
    }
    value.update(overrides)
    return value


class NewsletterValidationTests(unittest.TestCase):
    def test_accepts_valid_source_bound_selection(self):
        newsletter = validate_newsletter(draft(), ARTICLES)
        html = render_newsletter(
            newsletter,
            {"indices": [{"symbol": "SPY", "percent_change": "1.25"}], "tickers": []},
        )
        self.assertIn('href="https://example.com/story"', html)
        self.assertIn("color: #000000", html)
        self.assertIn("A &lt;summary&gt;.", html)
        self.assertNotIn("javascript:", html)
        self.assertIn("SPY</strong> +1.25%", html)
        self.assertIn("<small><em>Sports was the only active category today.", html)

    def test_rejects_unknown_or_duplicate_articles(self):
        unknown = draft(for_you=[{"article_id": "missing", "summary": "x"}])
        with self.assertRaises(NewsletterValidationError):
            validate_newsletter(unknown, ARTICLES)
        duplicate = draft(general=[{"article_id": "h1", "summary": "x"}])
        with self.assertRaises(NewsletterValidationError):
            validate_newsletter(duplicate, ARTICLES)

    def test_rejects_category_cap_violation(self):
        articles = {**ARTICLES, "h3": {**ARTICLES["h2"], "article_id": "h3"}, "h4": {**ARTICLES["h2"], "article_id": "h4"}}
        for_you = [{"article_id": article_id, "summary": "x"} for article_id in ("h1", "h3", "h4")]
        with self.assertRaises(NewsletterValidationError):
            validate_newsletter(draft(for_you=for_you, general=[]), articles)

    def test_rejects_untagged_for_you_article(self):
        articles = {**ARTICLES, "h3": {**ARTICLES["h2"], "article_id": "h3", "matched_interests": []}}
        with self.assertRaises(NewsletterValidationError):
            validate_newsletter(draft(for_you=[{"article_id": "h3", "summary": "x"}], general=[]), articles)

    def test_retry_includes_the_rejected_draft(self):
        captured = {}

        class Responses:
            def create(self, **kwargs):
                captured.update(kwargs)
                return type("Response", (), {"output_text": json.dumps(draft())})()

        client = type("Client", (), {"responses": Responses()})()
        previous = draft(for_you=[{"article_id": "missing", "summary": "x"}])
        _request(client, "candidate input", "Unknown article ID: missing", previous)
        correction = json.loads(captured["input"][-1]["content"])
        self.assertEqual(correction["previous_draft"], previous)


if __name__ == "__main__":
    unittest.main()
