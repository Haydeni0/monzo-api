"""Shared utilities for Monzo API scripts."""

import json
import os
from contextlib import contextmanager
from typing import Generator

import httpx

from monzo_api.src.config import API_URL, ENV_SECRETS_FILE, TOKEN_FILE


def load_env_secrets() -> None:
    """Load variables from .env.secrets file into environment."""
    if ENV_SECRETS_FILE.exists():
        for raw_line in ENV_SECRETS_FILE.read_text().splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def load_token_data() -> dict | None:
    """Load full token data from file if exists."""
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def load_token() -> str:
    """Load access token from file.

    Raises:
        FileNotFoundError: If token file doesn't exist.
    """
    data = load_token_data()
    if not data:
        msg = f"Token file not found: {TOKEN_FILE}\nRun: monzo auth"
        raise FileNotFoundError(msg)
    return data["access_token"]


def save_token(token_data: dict) -> None:
    """Save token data to file."""
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))


@contextmanager
def monzo_client(token: str | None = None) -> Generator[httpx.Client, None, None]:
    """Create authenticated HTTP client.

    Args:
        token: Access token. If None, loads from file.
    """
    if token is None:
        token = load_token()
    client = httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    try:
        yield client
    finally:
        client.close()
