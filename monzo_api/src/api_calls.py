"""Monzo API calling functions.

Functions for fetching data from the Monzo API.
Uses yearly chunking with forward pagination to handle API limits.
"""

from datetime import UTC, datetime, timedelta

import httpx

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


def _to_timestamp(dt: datetime) -> str:
    """Convert datetime to Monzo API timestamp format."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _fetch_chunk(
    client: httpx.Client,
    account_id: str,
    since: datetime,
    before: datetime,
    seen_ids: set[str],
) -> tuple[list[Transaction], bool]:
    """Fetch all transactions in a time chunk with pagination.

    Returns:
        Tuple of (transactions, sca_expired). If sca_expired is True,
        the caller should stop fetching and return what we have.
    """
    txs: list[Transaction] = []
    cursor = _to_timestamp(since)
    before_str = _to_timestamp(before)

    while True:
        resp = client.get(
            "/transactions",
            params={
                "account_id": account_id,
                "limit": 100,
                "expand[]": "merchant",
                "since": cursor,
                "before": before_str,
            },
        )

        if resp.status_code == 403:
            return txs, True  # SCA expired
        if resp.status_code == 400:
            break  # Invalid range, skip chunk
        resp.raise_for_status()

        raw = resp.json().get("transactions", [])
        if not raw:
            break

        page = [Transaction.model_validate(t) for t in raw]
        new = [t for t in page if t.id not in seen_ids]
        if not new:
            break  # All duplicates

        for t in new:
            seen_ids.add(t.id)
        txs.extend(new)

        # Back up cursor by 1s to catch same-timestamp transactions
        newest = max(new, key=lambda t: t.created)
        cursor = _to_timestamp(newest.created - timedelta(seconds=1))

    return txs, False


def fetch_transactions(
    client: httpx.Client,
    account: Account,
    days: int | None = None,
) -> list[Transaction]:
    """Fetch transactions using yearly chunking.

    Monzo API limits:
    - 400 error if time range >= 365 days
    - 403 error if range >= 90 days and SCA expired (>5 min since auth)

    Args:
        client: HTTP client with auth.
        account: Account to fetch transactions for.
        days: Number of days to fetch. None = full history.

    Returns:
        List of transactions sorted by created date.
    """
    now = datetime.now(UTC)
    account_created = account.created or now - timedelta(days=CHUNK_SIZE_DAYS)

    # Calculate start date
    if days is not None:
        start = max(now - timedelta(days=days), account_created)
        if days > (now - account_created).days:
            print(f"    Note: Account is only {(now - account_created).days} days old")
    else:
        start = account_created

    # Fetch in yearly chunks
    all_txs: list[Transaction] = []
    seen_ids: set[str] = set()
    chunk_start = start

    while chunk_start < now:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_SIZE_DAYS), now + timedelta(days=1))

        txs, sca_expired = _fetch_chunk(client, account.id, chunk_start, chunk_end, seen_ids)
        all_txs.extend(txs)

        if len(all_txs) % 1000 < 100 and all_txs:
            print(f"    {len(all_txs)}...")

        if sca_expired:
            if not all_txs:
                raise SCAExpiredError
            break

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
    client = create_client(token)  # TODO: context manager

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

    total = sum(len(t) for t in transactions.values())
    print(f"\nTotal: {total} transactions")

    client.close()

    return MonzoExport(
        exported_at=datetime.now(UTC),
        since=None,
        days=days,
        accounts=accounts,
        pots=pots,
        transactions=transactions,
    )
