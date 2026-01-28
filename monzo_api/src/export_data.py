"""Export Monzo data to JSON.

Uses backward pagination with `before` param to get full transaction history.
No 365-day limit when using `before` instead of `since` alone.

Usage:
    monzo export           # full history
    monzo export -d 30     # last 30 days only
"""

from datetime import UTC, datetime, timedelta

import httpx

from monzo_api.src.config import CACHE_FILE
from monzo_api.src.models import Account, MonzoExport, Pot, Transaction
from monzo_api.src.utils import create_client, load_token


class SCAExpiredError(Exception):
    """Raised when the 90-day transaction limit is hit due to expired SCA.

    After 5 minutes of authentication, Monzo restricts access to last 90 days only.
    See: https://docs.monzo.com/#list-transactions
    """

    def __init__(self) -> None:
        """Initialize with helpful message."""
        super().__init__(
            "SCA expired - can only access last 89 days.\n"
            "After 5 minutes of auth, Monzo limits transaction history to 89 days.\n"
            "Run 'monzo auth --force' to reauthenticate for full history (for 5 minutes).\n"
            "Docs: https://docs.monzo.com/#list-transactions"
        )


def fetch_accounts(client: httpx.Client) -> list[Account]:
    """Fetch all accounts."""
    resp = client.get("/accounts")
    resp.raise_for_status()
    return [Account.model_validate(a) for a in resp.json()["accounts"]]


def fetch_pots(client: httpx.Client, account_id: str) -> list[Pot]:
    """Fetch pots for an account."""
    resp = client.get("/pots", params={"current_account_id": account_id})
    resp.raise_for_status()
    return [Pot.model_validate(p) for p in resp.json()["pots"]]


def fetch_transactions(
    client: httpx.Client,
    account_id: str,
    since: str | None = None,
) -> list[Transaction]:
    """Fetch transactions using backward pagination with `before`.

    Uses `before` param to avoid the 365-day `since` limit.
    Optionally stops at `since` date if provided.
    """
    all_txs: list[Transaction] = []
    before_cursor: str | None = None  # Start from now

    while True:
        params: dict = {
            "account_id": account_id,
            "limit": 100,
            "expand[]": "merchant",
        }
        if before_cursor:
            params["before"] = before_cursor

        resp = client.get("/transactions", params=params)
        if resp.status_code == 403:
            raise SCAExpiredError
        resp.raise_for_status()
        txs_raw = resp.json().get("transactions", [])

        if not txs_raw:
            break

        txs = [Transaction.model_validate(t) for t in txs_raw]

        # Filter out transactions before our cutoff date
        if since:
            txs = [t for t in txs if t.created.isoformat() >= since]
            if not txs:
                break

        all_txs.extend(txs)

        # Set cursor to oldest transaction's timestamp for next page
        oldest = min(txs, key=lambda t: t.created)
        before_cursor = oldest.created.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        if len(all_txs) % 1000 < 100:
            print(f"    {len(all_txs)}...")

        # If we filtered any out, we've hit the boundary
        if since and len(txs) < len(txs_raw):
            break

    # Sort oldest first (consistent with forward pagination)
    all_txs.sort(key=lambda t: t.created)
    return all_txs


def export(days: int | None = None) -> MonzoExport:
    """Export Monzo data.

    Args:
        days: Number of days to fetch. None = full history.
    """
    if days:
        since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"Fetching last {days} days (since {since[:10]})\n")
    else:
        since = None
        print("Fetching full transaction history\n")

    token = load_token()
    client = create_client(token)

    # Accounts
    accounts = fetch_accounts(client)
    active = [a for a in accounts if not a.closed]
    print(f"Accounts: {len(accounts)} ({len(active)} active)")

    # Pots
    pots: list[Pot] = []
    for acc in active:
        pots.extend(fetch_pots(client, acc.id))
    print(f"Pots: {len(pots)}")

    # Transactions
    transactions: dict[str, list[Transaction]] = {}
    print("\nTransactions:")
    for acc in active:
        print(f"  {acc.type}:")
        txs = fetch_transactions(client, acc.id, since)
        transactions[acc.id] = txs
        print(f"    {len(txs)} transactions")

    client.close()

    total = sum(len(t) for t in transactions.values())
    print(f"\nTotal: {total} transactions")

    return MonzoExport(
        exported_at=datetime.now(UTC),
        since=since,
        days=days,
        accounts=accounts,
        pots=pots,
        transactions=transactions,
    )


def main(days: int | None = None) -> None:
    """Export and save to JSON."""
    data = export(days)
    data.save(CACHE_FILE)
    print(f"\nSaved to {CACHE_FILE}")
