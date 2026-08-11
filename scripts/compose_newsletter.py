"""Compose and safely render a newsletter with the OpenAI Responses API."""
import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
MODEL = "gpt-5.6-terra"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "for_you", "general", "market_summary", "footer"],
    "properties": {
        "subject": {"type": "string"},
        "for_you": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["article_id", "summary"], "properties": {"article_id": {"type": "string"}, "summary": {"type": "string"}}}},
        "general": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["article_id", "summary"], "properties": {"article_id": {"type": "string"}, "summary": {"type": "string"}}}},
        "market_summary": {"type": "string"},
        "footer": {"type": "string"},
    },
}


class NewsletterValidationError(ValueError):
    pass


def load_candidates(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    articles = {f"h{index}": {**article, "article_id": f"h{index}"} for index, article in enumerate(payload.get("headlines", []), 1)}
    return payload, articles


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise NewsletterValidationError(f"{name} must be a non-empty string.")


def validate_newsletter(draft, articles):
    if not isinstance(draft, dict):
        raise NewsletterValidationError("Response must be an object.")
    for key in ("subject", "market_summary", "footer"):
        _text(draft.get(key), key)
    for_you, general = draft.get("for_you"), draft.get("general")
    if not isinstance(for_you, list) or not isinstance(general, list):
        raise NewsletterValidationError("for_you and general must be lists.")
    if len(for_you) > 12 or len(general) > 5:
        raise NewsletterValidationError("Selection exceeds volume limits.")

    selected, category_counts, chosen_for_you = set(), {}, []
    for item in for_you:
        if not isinstance(item, dict):
            raise NewsletterValidationError("For-you entries must be objects.")
        article_id = item.get("article_id")
        _text(article_id, "for_you.article_id")
        _text(item.get("summary"), "for_you.summary")
        article = articles.get(article_id)
        if not article or article_id in selected:
            raise NewsletterValidationError(f"Invalid or duplicate article ID: {article_id}")
        eligible_categories = article.get("matched_interests", [])
        if not eligible_categories:
            raise NewsletterValidationError(f"{article_id} is not eligible for For You.")
        category = min(eligible_categories, key=lambda value: (category_counts.get(value, 0), value))
        category_counts[category] = category_counts.get(category, 0) + 1
        if category_counts[category] > 2:
            raise NewsletterValidationError(f"More than two items selected for {category}.")
        selected.add(article_id)
        chosen_for_you.append({**item, "category": category, "article": article})

    chosen_general = []
    for item in general:
        if not isinstance(item, dict):
            raise NewsletterValidationError("General entries must be objects.")
        article_id = item.get("article_id")
        _text(article_id, "general.article_id")
        _text(item.get("summary"), "general.summary")
        article = articles.get(article_id)
        if not article or article_id in selected:
            raise NewsletterValidationError(f"Invalid or duplicate article ID: {article_id}")
        selected.add(article_id)
        chosen_general.append({**item, "article": article})
    return {**draft, "for_you": chosen_for_you, "general": chosen_general}


def _safe_url(value):
    parsed = urlparse(value) if isinstance(value, str) else None
    return value if parsed and parsed.scheme in {"http", "https"} and parsed.netloc else None


def _render_item(item):
    article = item["article"]
    title = html.escape(str(article.get("title", "Untitled")))
    source = html.escape(str(article.get("source", "Source")))
    summary = html.escape(item["summary"]).replace("\n", "<br>")
    url = _safe_url(article.get("url"))
    heading = f'<a href="{html.escape(url, quote=True)}">{title}</a>' if url else title
    return f"<article><h3>{heading}</h3><p><em>{source}</em></p><p>{summary}</p></article>"


def render_newsletter(newsletter):
    for_you = "".join(_render_item(item) for item in newsletter["for_you"]) or "<p>No personalized items met today's criteria.</p>"
    general = "".join(_render_item(item) for item in newsletter["general"]) or "<p>No general-news items were selected today.</p>"
    market = html.escape(newsletter["market_summary"]).replace("\n", "<br>")
    footer = html.escape(newsletter["footer"])
    return f"""<!doctype html>
<html><body><h1>Your Morning Briefing</h1><h2>For You</h2>{for_you}
<h2>General News</h2>{general}<h2>Markets</h2><p>{market}</p>
<footer><p>{footer}</p></footer></body></html>"""


def _prompt(payload, articles, policy):
    candidates = [
        {key: article.get(key) for key in ("article_id", "title", "description", "source", "url", "matched_interests", "published_at")}
        for article in articles.values()
    ]
    for_you_candidates = [candidate for candidate in candidates if candidate["matched_interests"]]
    return json.dumps(
        {
            "editorial_policy": policy,
            "for_you_candidates": for_you_candidates,
            "general_candidates": candidates,
            "market": payload.get("market", {}),
        },
        ensure_ascii=False,
    )


def _request(client, prompt, correction=None, previous_draft=None):
    inputs = [
        {"role": "system", "content": "Compose a concise personal morning newsletter. For for_you, select article IDs only from for_you_candidates; for general, select only from general_candidates. Ground summaries strictly in the supplied title and description. Return the requested JSON only."},
        {"role": "user", "content": prompt},
    ]
    if correction:
        inputs.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "previous_draft": previous_draft,
                        "validation_error": correction,
                        "instruction": "Return a corrected replacement draft. Do not reuse invalid selections.",
                    }
                ),
            }
        )
    response = client.responses.create(
        model=MODEL,
        input=inputs,
        reasoning={"effort": "low"},
        store=False,
        text={"format": {"type": "json_schema", "name": "newsletter", "strict": True, "schema": SCHEMA}},
    )
    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise NewsletterValidationError("Response was not valid JSON.") from exc


def compose(input_path, html_path, metadata_path, *, client=None, policy_path=ROOT / "agent_instructions.md"):
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Missing required environment variable: OPENAI_API_KEY")
    payload, articles = load_candidates(input_path)
    policy_text = policy_path.read_text(encoding="utf-8")
    policy = policy_text.split("## Selection rules", maxsplit=1)[-1]
    prompt = _prompt(payload, articles, policy)
    client = client or OpenAI()
    error = None
    previous_draft = None
    for _ in range(2):
        try:
            previous_draft = _request(client, prompt, error, previous_draft)
            newsletter = validate_newsletter(previous_draft, articles)
            break
        except NewsletterValidationError as exc:
            error = str(exc)
    else:
        raise NewsletterValidationError(error or "Unable to validate newsletter.")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_newsletter(newsletter), encoding="utf-8")
    metadata_path.write_text(json.dumps({"subject": newsletter["subject"]}, indent=2) + "\n", encoding="utf-8")
    return newsletter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=OUTPUT_DIR / "latest.json")
    parser.add_argument("--html-output", type=Path, default=OUTPUT_DIR / "newsletter.html")
    parser.add_argument("--metadata-output", type=Path, default=OUTPUT_DIR / "newsletter.json")
    args = parser.parse_args()
    newsletter = compose(args.input, args.html_output, args.metadata_output)
    print(json.dumps({"subject": newsletter["subject"], "for_you": len(newsletter["for_you"]), "general": len(newsletter["general"])}, indent=2))


if __name__ == "__main__":
    main()
