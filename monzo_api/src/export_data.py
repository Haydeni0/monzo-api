"""Export all Monzo data to JSON.

This script fetches and caches all available data from the Monzo API:
- Accounts
- Transactions (with expanded merchant data)
- Pots

Run within 5 minutes of authentication to fetch FULL transaction history.
After 5 mins, API limits transactions to last 90 days only.

Cached data is merged with new data on each run, so history accumulates.

Usage:
    python src/export_data.py
"""

import json
from datetime import datetime

import httpx

from monzo_api.src.config import CACHE_FILE
from monzo_api.src.utils import create_client, load_token


def load_cache() -> dict:
    """Load cached data from file."""
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {
        "accounts": [],
        "transactions": {},  # keyed by account_id
        "merchants": {},  # keyed by merchant_id
        "pots": [],
        "last_updated": None,
    }


def save_cache(cache: dict) -> None:
    """Save data to cache file."""
    cache["last_updated"] = datetime.now().isoformat()
    CACHE_FILE.write_text(json.dumps(cache, indent=2))
    print(f"Saved to {CACHE_FILE}")


def fetch_accounts(client: httpx.Client) -> list[dict]:
    """Fetch all accounts."""
    resp = client.get("/accounts")
    resp.raise_for_status()
    accounts = resp.json()["accounts"]
    print(f"Accounts: {len(accounts)}")
    return accounts


def fetch_pots(client: httpx.Client, account_id: str) -> list[dict]:
    """Fetch all pots for an account."""
    resp = client.get("/pots", params={"current_account_id": account_id})
    resp.raise_for_status()
    pots = resp.json()["pots"]
    return pots


def fetch_transactions(
    client: httpx.Client,
    account_id: str,
    expand_merchant: bool = True,
) -> list[dict]:
    """Fetch all transactions for an account (paginated).

    Args:
        client: HTTP client
        account_id: Account to fetch transactions for
        expand_merchant: Include full merchant details (slower but more data)
    """
    all_transactions = []
    since = None
    page = 0

    while True:
        params: dict = {"account_id": account_id, "limit": 100}
        if since:
            params["since"] = since
        if expand_merchant:
            params["expand[]"] = "merchant"

        resp = client.get("/transactions", params=params)
        resp.raise_for_status()
        transactions = resp.json().get("transactions", [])

        if not transactions:
            break

        all_transactions.extend(transactions)
        since = transactions[-1]["id"]
        page += 1

        if page % 10 == 0:
            print(f"    ... {len(all_transactions)} transactions")

        if len(all_transactions) > 50000:
            print("    Warning: Hit 50k limit")
            break

    return all_transactions


def extract_merchants(transactions: list[dict]) -> dict[str, dict]:
    """Extract merchant objects from transactions."""
    merchants = {}
    for tx in transactions:
        merchant = tx.get("merchant")
        if merchant and isinstance(merchant, dict) and merchant.get("id"):
            merchants[merchant["id"]] = merchant
    return merchants


def merge_transactions(cached: list[dict], new: list[dict]) -> tuple[list[dict], int]:
    """Merge new transactions with cached, deduplicating by ID."""
    tx_by_id = {tx["id"]: tx for tx in cached}
    new_count = sum(1 for tx in new if tx["id"] not in tx_by_id)
    for tx in new:
        tx_by_id[tx["id"]] = tx
    merged = sorted(tx_by_id.values(), key=lambda x: x["created"])
    return merged, new_count


def main() -> None:
    """Export all Monzo data to JSON."""
    print("Monzo Data Export\n")

    # Load token and create client
    token = load_token()
    client = create_client(token)

    # Load existing cache
    cache = load_cache()
    if cache["last_updated"]:
        print(f"Cache from {cache['last_updated'][:19]}\n")

    # Fetch accounts
    accounts = fetch_accounts(client)
    cache["accounts"] = accounts
    active_accounts = [a for a in accounts if not a.get("closed")]

    # Fetch pots for each account
    all_pots = []
    for acc in active_accounts:
        pots = fetch_pots(client, acc["id"])
        all_pots.extend(pots)
    cache["pots"] = all_pots
    print(f"Pots: {len(all_pots)}")

    # Fetch transactions for each account
    print(f"\nFetching transactions for {len(active_accounts)} accounts...")

    all_merchants: dict[str, dict] = cache.get("merchants", {})

    for acc in active_accounts:
        acc_id = acc["id"]
        acc_type = acc["type"]
        print(f"\n  {acc_type}:")

        # Fetch from API
        new_txs = fetch_transactions(client, acc_id, expand_merchant=True)

        # Extract merchants before we strip them
        new_merchants = extract_merchants(new_txs)
        all_merchants.update(new_merchants)

        # Merge with cache
        cached_txs = cache["transactions"].get(acc_id, [])
        merged, new_count = merge_transactions(cached_txs, new_txs)
        cache["transactions"][acc_id] = merged

        print(f"    {len(new_txs)} fetched, +{new_count} new, {len(merged)} total")

    cache["merchants"] = all_merchants
    print(f"\nMerchants: {len(all_merchants)}")

    # Summary
    total_txs = sum(len(txs) for txs in cache["transactions"].values())
    print(f"\nTotal: {total_txs} transactions across {len(active_accounts)} accounts")

    # Save
    save_cache(cache)
    client.close()


if __name__ == "__main__":
    main()
