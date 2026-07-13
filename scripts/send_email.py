"""
Sends an email via the Gmail API (HTTPS), authenticated with a long-lived
OAuth refresh token.

This exists because two earlier approaches didn't work in the cloud sandbox
that runs the daily scheduled agent: the connected Gmail MCP tool can only
create drafts, not send; and raw SMTP (ports 465/587) is blocked by the
sandbox's network proxy, which only permits outbound HTTPS on port 443. The
Gmail API send endpoint is plain HTTPS, so it goes through fine. Run
gmail_oauth_setup.py once (locally, where a browser exists) to obtain the
refresh token this script depends on.

Usage: python send_email.py --subject "..." --html-file path/to/body.html
"""
import argparse
import base64
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
CLIENT_ID = os.environ.get("GMAIL_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GMAIL_OAUTH_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GMAIL_OAUTH_REFRESH_TOKEN")


def _get_access_token():
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def send_email(subject, html_body, to_address=None):
    to_address = to_address or GMAIL_ADDRESS
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    access_token = _get_access_token()

    resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"raw": raw},
        timeout=15,
    )
    resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True)
    parser.add_argument("--html-file", required=True)
    parser.add_argument("--to", default=None)
    args = parser.parse_args()

    if not all([GMAIL_ADDRESS, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        raise SystemExit(
            "GMAIL_ADDRESS / GMAIL_OAUTH_CLIENT_ID / GMAIL_OAUTH_CLIENT_SECRET / "
            "GMAIL_OAUTH_REFRESH_TOKEN not set in .env — run gmail_oauth_setup.py first."
        )

    html_body = Path(args.html_file).read_text(encoding="utf-8")
    send_email(args.subject, html_body, args.to)
    print(f"Sent to {args.to or GMAIL_ADDRESS}")


if __name__ == "__main__":
    main()
