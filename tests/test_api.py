"""End-to-end tests for Monzo API.

These tests require a valid access token in .monzo_token.json.
Run `python src/get_token.py` first to authenticate.
"""

import httpx
import pytest

from tests.conftest import requires_token


@requires_token
class TestAuthentication:
    """Test authentication endpoints."""

    def test_whoami(self, monzo_client: httpx.Client) -> None:
        """Test /ping/whoami returns authenticated user info."""
        resp = monzo_client.get("/ping/whoami")
        assert resp.status_code == 200

        data = resp.json()
        assert data["authenticated"] is True
        assert "user_id" in data
        assert "client_id" in data


@requires_token
class TestAccounts:
    """Test account endpoints."""

    def test_list_accounts(self, monzo_client: httpx.Client) -> None:
        """Test listing all accounts."""
        resp = monzo_client.get("/accounts")
        assert resp.status_code == 200

        data = resp.json()
        assert "accounts" in data
        assert len(data["accounts"]) > 0

        # Check account structure
        account = data["accounts"][0]
        assert "id" in account
        assert "type" in account
        assert "currency" in account

    def test_list_retail_accounts(self, monzo_client: httpx.Client) -> None:
        """Test listing uk_retail accounts only."""
        resp = monzo_client.get("/accounts", params={"account_type": "uk_retail"})
        assert resp.status_code == 200

        data = resp.json()
        for account in data["accounts"]:
            assert account["type"] == "uk_retail"


@requires_token
class TestBalance:
    """Test balance endpoints."""

    def test_get_balance(self, monzo_client: httpx.Client, account_id: str) -> None:
        """Test getting account balance."""
        if not account_id:
            pytest.skip("No active account found")

        resp = monzo_client.get("/balance", params={"account_id": account_id})
        assert resp.status_code == 200

        data = resp.json()
        assert "balance" in data
        assert "total_balance" in data
        assert "currency" in data
        assert "spend_today" in data

        # Balance should be an integer (minor units)
        assert isinstance(data["balance"], int)
        assert data["currency"] == "GBP"


@requires_token
class TestPots:
    """Test pots endpoints."""

    def test_list_pots(self, monzo_client: httpx.Client, account_id: str) -> None:
        """Test listing pots for an account."""
        if not account_id:
            pytest.skip("No active account found")

        resp = monzo_client.get("/pots", params={"current_account_id": account_id})
        assert resp.status_code == 200

        data = resp.json()
        assert "pots" in data

        # If there are pots, check structure
        if data["pots"]:
            pot = data["pots"][0]
            assert "id" in pot
            assert "name" in pot
            assert "balance" in pot
            assert "currency" in pot


@requires_token
class TestTransactions:
    """Test transaction endpoints."""

    def test_list_transactions(self, monzo_client: httpx.Client, account_id: str) -> None:
        """Test listing recent transactions."""
        if not account_id:
            pytest.skip("No active account found")

        resp = monzo_client.get(
            "/transactions",
            params={"account_id": account_id, "limit": 10},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert "transactions" in data

        # If there are transactions, check structure
        if data["transactions"]:
            tx = data["transactions"][0]
            assert "id" in tx
            assert "amount" in tx
            assert "currency" in tx
            assert "created" in tx

    def test_get_single_transaction(self, monzo_client: httpx.Client, account_id: str) -> None:
        """Test getting a single transaction with expanded merchant."""
        if not account_id:
            pytest.skip("No active account found")

        # First get a transaction ID
        resp = monzo_client.get(
            "/transactions",
            params={"account_id": account_id, "limit": 1},
        )
        assert resp.status_code == 200

        transactions = resp.json().get("transactions", [])
        if not transactions:
            pytest.skip("No transactions found")

        tx_id = transactions[0]["id"]

        # Now get it with expanded merchant
        resp = monzo_client.get(
            f"/transactions/{tx_id}",
            params={"expand[]": "merchant"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert "transaction" in data
        assert data["transaction"]["id"] == tx_id


@requires_token
class TestWebhooks:
    """Test webhook endpoints."""

    def test_list_webhooks(self, monzo_client: httpx.Client, account_id: str) -> None:
        """Test listing webhooks for an account."""
        if not account_id:
            pytest.skip("No active account found")

        resp = monzo_client.get("/webhooks", params={"account_id": account_id})
        assert resp.status_code == 200

        data = resp.json()
        assert "webhooks" in data
