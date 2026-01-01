"""Monzo API calling functions.

Functions for fetching data from the Monzo API.
Uses yearly chunking with forward pagination to handle API limits.
"""

from datetime import UTC, datetime, timedelta

import httpx

from monzo_api.src.config import CACHE_FILE
from monzo_api.src.models import Account, Balance, MonzoExport, Pot, Transaction
from monzo_api.src.utils import create_client, load_token

CHUNK_SIZE_DAYS = 364  # Monzo API limit is 365 days


class SCAExpiredError(Exception):
    """Raised when the 90-day transaction limit is hit due to expired SCA.

    After 5 minutes of authentication, Monzo restricts access to last 90 days only.
    See: https://docs.monzo.com/#list-transactions
    """

    def __init__(self, msg: str | None = None) -> None:
        """Initialize with helpful message."""
        super().__init__(
            msg
            or (
                "SCA expired - can only access last 89 days.\n"
                "After 5 minutes of auth, Monzo limits transaction history to 89 days.\n"
                "Run 'monzo auth --force' to reauthenticate for full history.\n"
                "Docs: https://docs.monzo.com/#list-transactions"
            )
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


def fetch_balance(client: httpx.Client, account_id: str) -> Balance:
    """Fetch current balance for an account."""
    resp = client.get("/balance", params={"account_id": account_id})
    resp.raise_for_status()
    return Balance.model_validate(resp.json())


def fetch_transactions(
    client: httpx.Client,
    account: Account,
    days: int | None = None,
) -> list[Transaction]:
    """Fetch transactions using yearly chunking with forward pagination.

    Monzo API errors:
    (1) If you request a time range >= 365 days, you get a 400 error.
    (2) If you request a time range >= 90 days, AND you have not authenticated
        in the last 5 minutes, you get a 403 error.

    This implementation breaks the full history into 1-year chunks to avoid (1).

    Args:
        client: HTTP client with auth.
        account: Account to fetch transactions for.
        days: Number of days to fetch. None = full history from account creation.

    Returns:
        List of transactions sorted by created date.
    """
    account_created = account.created or datetime.now(UTC) - timedelta(days=CHUNK_SIZE_DAYS)

    # Calculate start date
    now = datetime.now(UTC)
    if days is not None:
        requested_start = now - timedelta(days=days)
        chunk_start = max(requested_start, account_created)
        account_age_days = (now - account_created).days
        if days > account_age_days:
            print(f"    Note: Account is only {account_age_days} days old")
    else:
        chunk_start = account_created

    all_txs: list[Transaction] = []
    seen_ids: set[str] = set()
    chunk_size = timedelta(days=CHUNK_SIZE_DAYS)

    while chunk_start < now:
        chunk_end = min(chunk_start + chunk_size, now + timedelta(days=1))
        since_cursor: str = chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        before_bound = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        while True:
            params = {
                "account_id": account.id,
                "limit": 100,
                "expand[]": "merchant",
                "since": since_cursor,
                "before": before_bound,
            }

            resp = client.get("/transactions", params=params)
            if resp.status_code == 403:
                if not all_txs:
                    raise SCAExpiredError
                return sorted(all_txs, key=lambda t: t.created)
            if resp.status_code == 400:
                break
            resp.raise_for_status()

            txs_raw = resp.json().get("transactions", [])
            if not txs_raw:
                break

            # Dedupe as we go (handles same-timestamp transactions)
            txs = [Transaction.model_validate(t) for t in txs_raw]
            new_txs = [t for t in txs if t.id not in seen_ids]
            if not new_txs:
                break  # All duplicates, done with this chunk

            for t in new_txs:
                seen_ids.add(t.id)
            all_txs.extend(new_txs)

            if len(all_txs) % 1000 < 100:
                print(f"    {len(all_txs)}...")

            # Use timestamp MINUS 1 second as cursor to ensure we catch all same-timestamp txs
            # This causes some duplicates, but seen_ids filters them out
            newest = max(new_txs, key=lambda t: t.created)
            cursor_time = newest.created - timedelta(seconds=1)
            since_cursor = cursor_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        chunk_start = chunk_end

    all_txs.sort(key=lambda t: t.created)
    return all_txs


def export(days: int | None = None) -> MonzoExport:
    """Export Monzo data.

    Args:
        days: Number of days to fetch. None = full history.
    """
    if days:
        print(f"Fetching last {days} days\n")
    else:
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
        txs = fetch_transactions(client, acc, days)
        transactions[acc.id] = txs
        print(f"    {len(txs)} transactions")

    client.close()

    total = sum(len(t) for t in transactions.values())
    print(f"\nTotal: {total} transactions")

    return MonzoExport(
        exported_at=datetime.now(UTC),
        since=None,
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
