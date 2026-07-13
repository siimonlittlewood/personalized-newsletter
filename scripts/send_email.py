"""
Sends an email via Gmail SMTP using an App Password.

This exists because the connected Gmail MCP tool can only create drafts, not
actually send mail (a deliberate safety restriction on auto-sending). SMTP
with an App Password is the actual delivery mechanism for the daily send;
the Gmail MCP connector is still used read-only, for checking replies.

Usage: python send_email.py --subject "..." --html-file path/to/body.html
"""
import argparse
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")


def send_email(subject, html_body, to_address=None):
    to_address = to_address or GMAIL_ADDRESS
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_address], msg.as_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True)
    parser.add_argument("--html-file", required=True)
    parser.add_argument("--to", default=None)
    args = parser.parse_args()

    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise SystemExit("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env")

    html_body = Path(args.html_file).read_text(encoding="utf-8")
    send_email(args.subject, html_body, args.to)
    print(f"Sent to {args.to or GMAIL_ADDRESS}")


if __name__ == "__main__":
    main()
