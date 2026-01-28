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
import logging
import os
import secrets
import threading
import urllib.parse
import webbrowser
from typing import Any

import httpx

from monzo_api.src.config import API_URL, AUTH_URL, TOKEN_FILE
from monzo_api.src.utils import load_env_secrets, load_token_data, save_token

load_env_secrets()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Configuration - from .env.secrets or environment variables
CLIENT_ID = os.environ.get("MONZO_CLIENT_ID", "YOUR_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MONZO_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback"

# Global event for thread synchronization
AUTH_EVENT = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler for OAuth callback requests."""

    auth_code: str | None = None
    state_token: str | None = None
    # using global AUTH_EVENT now

    def do_GET(self) -> None:
        """Handle GET request for OAuth callback."""
        logger.debug(f"Received request: {self.path}")
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            received_code = params.get("code", [None])[0]
            received_state = params.get("state", [None])[0]

            if received_state != CallbackHandler.state_token:
                logger.warning("State mismatch detected!")
                logger.warning("This usually happens if you approved an OLD browser tab from a previous run.")
                logger.warning("Please close all Monzo tabs and try again with the NEW link.")
                logger.warning(f"Expected: {CallbackHandler.state_token}")
                logger.warning(f"Received: {received_state}")
                
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch - used old tab? Close tabs and try again.")
                return

            CallbackHandler.auth_code = received_code
            AUTH_EVENT.set()
            logger.info("Auth code received successfully. Signal sent.")
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
        else:
            logger.debug(f"Ignored request for path: {parsed.path}")
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, fmt: str, *args: Any) -> None:
        """Log arbitrary message to debug logger."""
        logger.debug("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), fmt % args)


def get_auth_code() -> str:
    """Open browser for auth and capture the callback."""
    state = secrets.token_urlsafe(32)
    CallbackHandler.state_token = state
    CallbackHandler.auth_code = None
    AUTH_EVENT.clear()

    auth_params = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
    )
    auth_url = f"{AUTH_URL}/?{auth_params}"

    # Start local server to receive callback
    # Bind to 0.0.0.0 so it's accessible externally/via port forwarding
    logger.info("Starting local server...")
    
    class ReusableTCPServer(http.server.HTTPServer):
        allow_reuse_address = True

    server = ReusableTCPServer(("0.0.0.0", 8080), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    logger.info("Opening browser for Monzo authentication...")
    logger.info(f"If the browser does not open, visit this URL:\n  {auth_url}\n")
    
    # Open browser in a separate thread to prevent blocking
    browser_thread = threading.Thread(target=lambda: webbrowser.open(auth_url))
    browser_thread.daemon = True
    browser_thread.start()
    
    logger.info("Waiting for callback on http://localhost:8080/callback ...")

    try:
        # Wait for the event to be set (blocking, with timeout loop for Ctrl+C support)
        while not AUTH_EVENT.is_set():
            AUTH_EVENT.wait(0.5)
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled.")
        server.server_close()
        return None

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
            logger.error(f"Error {resp.status_code}: {resp.text}")
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
            logger.info(f"Token valid - User: {data.get('user_id')}, Client: {data.get('client_id')}")
            return True
        return False


def token_oauth() -> None:
    """Run the OAuth token flow."""
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":  # noqa: S105
        logger.error("ERROR: Set your MONZO_CLIENT_ID and MONZO_CLIENT_SECRET")
        logger.error("  1. Create a client at https://developers.monzo.com")
        logger.error("  2. Set redirect URI to: http://localhost:8080/callback")
        logger.error("  3. Export env vars or edit this script")
        logger.error("")
        logger.error("  export MONZO_CLIENT_ID='oauth2client_xxx'")
        logger.error("  export MONZO_CLIENT_SECRET='mnzconf.xxx'")
        return

    # Try loading existing token
    existing = load_token_data()
    if existing:
        logger.info("Found existing token, testing...")
        if test_token(existing["access_token"]):
            logger.info(f"Access token: {existing['access_token'][:20]}...")
            return

        # Try refresh if we have a refresh token
        if existing.get("refresh_token"):
            logger.info("Token expired, trying refresh...")
            try:
                token_data = refresh_token(existing["refresh_token"])
                save_token(token_data)
                logger.info(f"Token saved to {TOKEN_FILE}")

                logger.info("Token refreshed!")
                logger.info(f"Access token: {token_data['access_token'][:20]}...")
                return
            except httpx.HTTPStatusError:
                logger.warning("Refresh failed, need new auth...")

    # Full OAuth flow
    auth_code = get_auth_code()
    if not auth_code:
        return

    logger.info(f"Got authorization code: {auth_code[:10]}...")

    logger.info("Exchanging for access token...")
    token_data = exchange_code_for_token(auth_code)
    save_token(token_data)
    logger.info(f"Token saved to {TOKEN_FILE}")

    logger.info("")
    logger.info("=" * 57)
    logger.info("IMPORTANT: Open Monzo app and approve the access request!")
    logger.info("=" * 57)
    logger.info("")
    logger.info(f"Access token: {token_data['access_token']}")
    logger.info(
        f"Expires in: {token_data['expires_in']} seconds (~{token_data['expires_in'] // 3600} hours)"
    )
    if token_data.get("refresh_token"):
        logger.info(f"Refresh token: {token_data['refresh_token'][:20]}...")
    else:
        logger.info("No refresh token (non-confidential client)")


if __name__ == "__main__":
    token_oauth()
