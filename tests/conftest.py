"""Pytest fixtures for Monzo API tests."""

import json
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
TOKEN_FILE = PROJECT_ROOT / ".monzo_token.json"
API_URL = "https://api.monzo.com"


@pytest.fixture(scope="session")
def access_token() -> str | None:
    """Load access token from file if available."""
    if not TOKEN_FILE.exists():
        return None
    data = json.loads(TOKEN_FILE.read_text())
    return data.get("access_token")


@pytest.fixture(scope="session")
def monzo_client(access_token: str | None) -> httpx.Client | None:
    """Create authenticated httpx client."""
    if not access_token:
        return None
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30.0,
    )


@pytest.fixture(scope="session")
def account_id(monzo_client: httpx.Client | None) -> str | None:
    """Get the first active uk_retail account ID."""
    if not monzo_client:
        return None
    resp = monzo_client.get("/accounts", params={"account_type": "uk_retail"})
    if resp.status_code != 200:
        return None
    accounts = resp.json().get("accounts", [])
    for acc in accounts:
        if not acc.get("closed", False):
            return acc["id"]
    return None


requires_token = pytest.mark.skipif(
    not TOKEN_FILE.exists(),
    reason="No .monzo_token.json found - run get_token.py first",
)
