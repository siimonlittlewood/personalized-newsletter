"""
One-time interactive setup: runs the OAuth2 flow for the Gmail API
(gmail.send scope only) and writes a refresh token into .env.

Not part of the daily pipeline — run this once locally, and
scripts/send_email.py uses the resulting refresh token from then on.

Despite "Desktop app" OAuth clients being public clients per the OAuth
spec (and Google Cloud Console not surfacing a secret by default), Google's
token endpoint rejected our first attempt at a pure-PKCE, secret-less
exchange with "client_secret is missing" — so a secret had to be generated
explicitly in the console and is included here too, alongside PKCE.

Reads GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET from .env.
"""
import base64
import hashlib
import http.server
import os
import secrets
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
SCOPE = "https://www.googleapis.com/auth/gmail.send"

_auth_code = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _auth_code["code"] = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Done, you can close this tab and return to the terminal.")

    def log_message(self, *args):
        pass


def main():
    client_id = os.environ.get("GMAIL_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("Set GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET in .env first.")

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
    )

    print(f"Opening browser to authorize... if it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.handle_request()

    code = _auth_code.get("code")
    if not code:
        raise SystemExit("No authorization code received.")

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    if not resp.ok:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        resp.raise_for_status()
    tokens = resp.json()

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise SystemExit("No refresh_token in response (token exchange failed).")

    existing = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    lines = [l for l in existing.splitlines() if not l.startswith(("GMAIL_OAUTH_CLIENT_ID=", "GMAIL_OAUTH_REFRESH_TOKEN="))]
    lines.append(f"GMAIL_OAUTH_CLIENT_ID={client_id}")
    lines.append(f"GMAIL_OAUTH_REFRESH_TOKEN={refresh_token}")
    ENV_PATH.write_text("\n".join(lines) + "\n")

    print("\nSuccess — GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_REFRESH_TOKEN written to .env directly (not printed).")


if __name__ == "__main__":
    main()
