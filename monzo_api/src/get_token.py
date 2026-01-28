#!/usr/bin/env python3
"""Monzo OAuth Token Generator.

Prerequisites:
1. Create a client at https://developers.monzo.com
2. Set redirect URI to: http://localhost:8080/callback
3. Create .env.secrets in project root with:
   MONZO_CLIENT_ID=oauth2client_xxx
   MONZO_CLIENT_SECRET=mnzconf.xxx

Usage:
    python src/get_token.py
"""

import http.server
import os
import secrets
import urllib.parse
import webbrowser
from typing import Any

import httpx

from monzo_api.src.config import API_URL, AUTH_URL, TOKEN_FILE
from monzo_api.src.utils import load_env_secrets, load_token_data, save_token

load_env_secrets()

# Configuration - from .env.secrets or environment variables
CLIENT_ID = os.environ.get("MONZO_CLIENT_ID", "YOUR_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MONZO_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback"


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler for OAuth callback requests."""

    auth_code: str | None = None
    state_token: str | None = None

    def do_GET(self) -> None:
        """Handle GET request for OAuth callback."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            CallbackHandler.auth_code = params.get("code", [None])[0]
            received_state = params.get("state", [None])[0]

            if received_state != CallbackHandler.state_token:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch - possible CSRF attack!")
                return

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                <h1>Authorization successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                <p>Don't forget to <strong>approve access in the Monzo app</strong>!</p>
                </body></html>
            """)

    def log_message(self, fmt: str, *args: Any) -> None:
        """Suppress HTTP request logging."""


def get_auth_code() -> str:
    """Open browser for auth and capture the callback."""
    state = secrets.token_urlsafe(32)
    CallbackHandler.state_token = state

    auth_params = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
    )
    auth_url = f"{AUTH_URL}/?{auth_params}"

    print("Opening browser for Monzo authentication...")
    webbrowser.open(auth_url)

    # Start local server to receive callback
    server = http.server.HTTPServer(("localhost", 8080), CallbackHandler)
    print("Waiting for callback on http://localhost:8080/callback ...")

    while CallbackHandler.auth_code is None:
        server.handle_request()

    server.server_close()
    return CallbackHandler.auth_code


def exchange_code_for_token(auth_code: str) -> dict:
    """Exchange authorization code for access token."""
    with httpx.Client() as client:
        resp = client.post(
            f"{API_URL}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "code": auth_code,
            },
        )
        if resp.status_code != 200:
            print(f"Error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
        return resp.json()


def refresh_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    with httpx.Client() as client:
        resp = client.post(
            f"{API_URL}/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        return resp.json()


def test_token(access_token: str) -> bool:
    """Test if token is valid."""
    with httpx.Client() as client:
        resp = client.get(
            f"{API_URL}/ping/whoami",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"Token valid - User: {data.get('user_id')}, Client: {data.get('client_id')}")
            return True
        return False


def main() -> None:
    """Run the OAuth token flow."""
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":  # noqa: S105
        print("ERROR: Set your MONZO_CLIENT_ID and MONZO_CLIENT_SECRET")
        print("  1. Create a client at https://developers.monzo.com")
        print("  2. Set redirect URI to: http://localhost:8080/callback")
        print("  3. Export env vars or edit this script")
        print()
        print("  export MONZO_CLIENT_ID='oauth2client_xxx'")
        print("  export MONZO_CLIENT_SECRET='mnzconf.xxx'")
        return

    # Try loading existing token
    existing = load_token_data()
    if existing:
        print("Found existing token, testing...")
        if test_token(existing["access_token"]):
            print(f"\nAccess token: {existing['access_token'][:20]}...")
            return

        # Try refresh if we have a refresh token
        if existing.get("refresh_token"):
            print("Token expired, trying refresh...")
            try:
                token_data = refresh_token(existing["refresh_token"])
                save_token(token_data)
                print(f"Token saved to {TOKEN_FILE}")

                print("\nToken refreshed!")
                print(f"Access token: {token_data['access_token'][:20]}...")
                return
            except httpx.HTTPStatusError:
                print("Refresh failed, need new auth...")

    # Full OAuth flow
    auth_code = get_auth_code()
    print(f"Got authorization code: {auth_code[:10]}...")

    print("Exchanging for access token...")
    token_data = exchange_code_for_token(auth_code)
    save_token(token_data)
    print(f"Token saved to {TOKEN_FILE}")

    print()
    print("=" * 50)
    print("IMPORTANT: Open Monzo app and approve the access request!")
    print("=" * 50)
    print()
    print(f"Access token: {token_data['access_token']}")
    print(
        f"Expires in: {token_data['expires_in']} seconds (~{token_data['expires_in'] // 3600} hours)"
    )
    if token_data.get("refresh_token"):
        print(f"Refresh token: {token_data['refresh_token'][:20]}...")
    else:
        print("No refresh token (non-confidential client)")


if __name__ == "__main__":
    main()
