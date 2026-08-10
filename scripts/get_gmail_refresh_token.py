# scripts/get_gmail_refresh_token.py
#
# One-time LOCAL script to get a Gmail API OAuth refresh token for
# GmailAPIEmailBackend (web/config/email_backends.py). Run this once on
# your own machine -- it opens your browser for a normal Google login +
# consent screen, then prints the refresh token to paste into Render as
# GMAIL_OAUTH_REFRESH_TOKEN. Never runs in production; no new dependency
# beyond `requests`, which the project already has.
#
# Usage:
#   uv run python scripts/get_gmail_refresh_token.py --client-id ... --client-secret ...
#
# Prerequisites (Google Cloud Console, https://console.cloud.google.com):
#   1. Create a project (or reuse one).
#   2. APIs & Services -> Enabled APIs -> enable "Gmail API".
#   3. APIs & Services -> OAuth consent screen -> External -> fill the
#      required fields (app name, your email) -> Save. Testing mode is
#      fine; add your own Gmail address under "Test users".
#   4. APIs & Services -> Credentials -> Create Credentials -> OAuth
#      client ID -> Application type "Desktop app" -> Create.
#   5. Copy the Client ID and Client Secret it shows you -- pass them to
#      this script.

import argparse
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/gmail.send"

_received_code = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _received_code["code"] = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>Done -- you can close this tab and return to the terminal.</body></html>")

    def log_message(self, *args):
        pass  # keep the console output clean


def main():
    parser = argparse.ArgumentParser(description="Get a Gmail API OAuth refresh token.")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    auth_params = {
        "client_id": args.client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # forces a refresh_token even on repeat runs
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    print("Opening your browser to sign in and grant access...")
    print(f"If it doesn't open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.handle_request()  # blocks until the one redirect arrives

    code = _received_code.get("code")
    if not code:
        print("No authorization code received -- did you cancel the consent screen?")
        return

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=10,
    )
    response.raise_for_status()
    tokens = response.json()

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("Google didn't return a refresh_token. This usually means you've already")
        print("authorized this app before without revoking it. Go to")
        print("https://myaccount.google.com/permissions, remove access for this app,")
        print("then run this script again.")
        return

    print("\nSuccess! Set these on Render:\n")
    print(f"  GMAIL_OAUTH_CLIENT_ID={args.client_id}")
    print(f"  GMAIL_OAUTH_CLIENT_SECRET={args.client_secret}")
    print(f"  GMAIL_OAUTH_REFRESH_TOKEN={refresh_token}")
    print("\n(GMAIL_ADDRESS should already be set to the Gmail address you just signed in with.)")


if __name__ == "__main__":
    main()
