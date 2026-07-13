# Personalized Newsletter

A daily email newsletter, tailored to my own interests, that lands in my inbox every morning at 7:45 AM — no manual curation required.

Each morning it pulls fresh headlines from news APIs and RSS feeds, filters and tags them against a configurable list of interests, selects a balanced mix (~80% personalized / ~20% general news), adds a market summary with a personal stock watchlist, and emails the result. The watchlist can be updated just by replying to the email in plain English (e.g. "add SHOP.TO and AAPL").

## How it works

The pipeline is a two-stage design: a deterministic script handles data fetching (fast, cheap, reliable), and an LLM agent handles the parts that actually need judgment (selection, summarization, and reading freeform email replies).

```
┌────────────────────────────┐   ┌──────────────────────────────┐
│ scripts/fetch_headlines.py │    │ Scheduled agent              │
│ (deterministic)            │    │ (runs daily, 7:45am)         │
│                            │    │                              │
│ - News API (general news)  │ ─▶ │ 1. Check Gmail for ticker    │
│ - RSS feeds (configurable  │    │    update replies            │
│   per-interest sources)    │    │ 2. Run fetch_headlines.py    │
│ - Market data APIs         │    │ 3. Select headlines per the  │
│   (indices + watchlist)    │    │    rules in                  │
│                            │    │    agent_instructions.md     │
│ -> output/latest.json      │    │ 4. Compose + send via        │
│                            │    │    send_email.py (Gmail API) │
└────────────────────────────┘   └──────────────────────────────┘
```

**Why split it this way?** Fetching and tagging headlines doesn't need judgment — it needs to be fast, cheap, and not depend on an LLM correctly reconstructing API calls every morning. Selecting which headlines are actually interesting, writing concise summaries, preserving important context (e.g. "Summer League" vs. a real NBA game), and reading a freeform reply like "add SHOP.TO and AAPL" — those genuinely benefit from an LLM's judgment. So the script does the former, the agent does the latter.

## Data sources

| Purpose | Source type | Notes |
|---|---|---|
| General news | News aggregation API | Free tier, commercial use allowed |
| Niche/personalized interests | Configurable RSS feeds | Set per-category in `config/sources.yaml` — swap in whatever's relevant to you |
| Market indices + watchlist | Market data APIs (split across two providers) | One provider's free tier only covers US-listed symbols, so non-US symbols route through a second, key-free provider |
| Email delivery | [Gmail API](https://developers.google.com/gmail/api) (OAuth2, HTTPS) | Not SMTP — see Deployment notes below for why |
| Reading replies | Gmail MCP connector (read-only) | Can't send; drafts/read only, by design |

## Selection rules

The full policy the daily agent follows lives in [`agent_instructions.md`](./agent_instructions.md) — it's written as a standing policy (volume targets, a hard cap of 2 items per interest category, a recency window, rumor/speculation filtering, context-preservation rules) rather than being re-tuned by hand each morning, so it stays consistent regardless of what any given day's headlines look like.

## Deployment

Runs as a [Claude Code](https://claude.com/claude-code) scheduled cloud agent — a daily cron-triggered session that clones this repo into an isolated sandbox and runs the pipeline. Two things about that sandbox shaped the design:

- **Outbound network is HTTPS-only.** Raw SMTP (ports 465/587) is blocked by the sandbox's proxy, which only permits port 443. That's why email delivery goes through the Gmail API (plain HTTPS + OAuth2) instead of `smtplib`.
- **No local filesystem.** Credentials are injected as real environment variables by the cloud environment rather than read from a committed `.env` file — `python-dotenv` falls back to the process environment automatically when no `.env` is present, so the same code works locally and in the cloud without changes. Nothing sensitive is ever committed to this repo (see `.env.example` for the shape of what's needed, with no real values).

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in:
   - `CURRENTS_API_KEY` — free key from [currentsapi.services](https://currentsapi.services/)
   - `TWELVEDATA_API_KEY` — free key from [twelvedata.com](https://twelvedata.com/)
   - `GMAIL_ADDRESS` — the sending/receiving Gmail address
   - `GMAIL_OAUTH_CLIENT_ID` / `GMAIL_OAUTH_CLIENT_SECRET` — from a Google Cloud OAuth client (Desktop app type) with the Gmail API enabled and `gmail.send` scope added on the consent screen
   - `GMAIL_OAUTH_REFRESH_TOKEN` — run `python scripts/gmail_oauth_setup.py` once locally (after the two values above are in `.env`) to get this via a one-time browser authorization; it's written straight into `.env`, never printed
3. Edit `config/interests.yaml` with your own interest keywords, and `config/sources.yaml` if you want different RSS sources.
4. Test the fetch step: `python scripts/fetch_headlines.py` (writes `output/latest.json`).
5. Test sending: `python scripts/send_email.py --subject "Test" --html-file path/to/body.html`.

## Project structure

```
config/
  interests.yaml       # personalized interest keywords, grouped by category
  sources.yaml          # RSS feeds + API config per category
  tickers.json           # stock watchlist, updated via email replies
scripts/
  fetch_headlines.py     # deterministic fetch + filter + tag
  send_email.py            # Gmail API send utility
  gmail_oauth_setup.py      # one-time local OAuth setup (not run by the daily pipeline)
agent_instructions.md  # the daily selection/composition policy the scheduled agent follows
```
