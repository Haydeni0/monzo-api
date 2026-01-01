"""Export Monzo data to JSON.

Simple script to fetch accounts, pots, and transactions, then save to JSON.

Usage:
    python -m monzo_api.src.export_data [--days 90]
"""

import json
from datetime import UTC, datetime, timedelta

import httpx

from monzo_api.src.config import CACHE_FILE
from monzo_api.src.utils import create_client, load_token


def fetch_accounts(client: httpx.Client) -> list[dict]:
    """Fetch all accounts."""
    resp = client.get("/accounts")
    resp.raise_for_status()
    return resp.json()["accounts"]


def fetch_pots(client: httpx.Client, account_id: str) -> list[dict]:
    """Fetch pots for an account."""
    resp = client.get("/pots", params={"current_account_id": account_id})
    resp.raise_for_status()
    return resp.json()["pots"]


def fetch_transactions(
    client: httpx.Client,
    account_id: str,
    since: str,
) -> list[dict]:
    """Fetch transactions for an account, paginating forward from `since`."""
    all_txs = []
    cursor = since

    while True:
        params = {"account_id": account_id, "limit": 100, "since": cursor, "expand[]": "merchant"}
        resp = client.get("/transactions", params=params)

        if resp.status_code == 403:
            print("    (90-day limit hit)")
            break

        resp.raise_for_status()
        txs = resp.json().get("transactions", [])

        if not txs:
            break

        all_txs.extend(txs)
        cursor = txs[-1]["id"]

        if len(all_txs) % 1000 < 100:
            print(f"    {len(all_txs)}...")

    return all_txs


def export(days: int = 90) -> dict:
    """Export Monzo data to dict."""
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Fetching data since {since[:10]} ({days} days)\n")

    token = load_token()
    client = create_client(token)

    # Accounts
    accounts = fetch_accounts(client)
    active = [a for a in accounts if not a.get("closed")]
    print(f"Accounts: {len(accounts)} ({len(active)} active)")

    # Pots
    pots = []
    for acc in active:
        pots.extend(fetch_pots(client, acc["id"]))
    print(f"Pots: {len(pots)}")

    # Transactions
    transactions = {}
    print("\nTransactions:")
    for acc in active:
        print(f"  {acc['type']}:")
        txs = fetch_transactions(client, acc["id"], since)
        transactions[acc["id"]] = txs
        print(f"    {len(txs)} transactions")

    client.close()

    total = sum(len(t) for t in transactions.values())
    print(f"\nTotal: {total} transactions")

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "since": since,
        "days": days,
        "accounts": accounts,
        "pots": pots,
        "transactions": transactions,
    }


def main(days: int = 90) -> None:
    """Export and save to JSON."""
    data = export(days)
    CACHE_FILE.write_text(json.dumps(data, indent=2))
    print(f"\nSaved to {CACHE_FILE}")


if __name__ == "__main__":
    import sys

    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    main(days)
