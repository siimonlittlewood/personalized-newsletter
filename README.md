# Personalized Newsletter

A daily, AI-curated email newsletter delivered at 7:45 AM America/Edmonton.
It gathers headlines and market data, selects a balanced briefing with OpenAI,
and sends the result through Gmail.

## How it works

1. `scripts/fetch_headlines.py` fetches, filters, and tags news plus market data.
2. `scripts/compose_newsletter.py` uses the OpenAI Responses API to select and
   summarize only the fetched items, then validates the selection and renders
   safe HTML locally.
3. `scripts/send_email.py` sends the rendered newsletter through the Gmail API.

The stock watchlist is deliberately simple: edit `config/tickers.json` directly.
The project does not read email replies or modify Gmail labels.

## Scheduled deployment

GitHub Actions runs [the daily workflow](.github/workflows/daily-newsletter.yml).
It uses two UTC schedule entries plus an Edmonton local-time guard, so it runs
at 7:45 AM across daylight-saving changes. Manual dispatch defaults to a dry
run, which renders the newsletter without sending it.

Add these repository secrets under **Settings → Secrets and variables → Actions**:

- `OPENAI_API_KEY`
- `CURRENTS_API_KEY`
- `TWELVEDATA_API_KEY`
- `GMAIL_ADDRESS`
- `GMAIL_OAUTH_CLIENT_ID`
- `GMAIL_OAUTH_CLIENT_SECRET`
- `GMAIL_OAUTH_REFRESH_TOKEN`

The workflow requires only read access to the repository.

## Local setup

1. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and populate the listed values. Never commit
   the real `.env` file.

3. Enable the Gmail API in your Google Cloud project and create a Desktop OAuth
   client. The included OAuth helper requests only `gmail.send`:

   ```powershell
   python scripts/gmail_oauth_setup.py
   ```

4. Run a local dry run:

   ```powershell
   python scripts/run_newsletter.py --dry-run
   ```

## Configuration

- `config/interests.yaml` controls personalized categories and keywords.
- `config/sources.yaml` controls news, RSS, and market sources.
- `config/tickers.json` controls the stock watchlist.
- `agent_instructions.md` contains the stable editorial selection policy.
