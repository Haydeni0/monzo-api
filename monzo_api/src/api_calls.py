"""Monzo API calling functions.

Functions for fetching data from the Monzo API.
Uses yearly chunking with forward pagination to handle API limits.
"""

from datetime import UTC, datetime, timedelta

import httpx
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeElapsedColumn

from monzo_api.src.models import Account, Balance, MonzoExport, Pot, Transaction
from monzo_api.src.utils import console, monzo_client

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
                "or run 'monzo export --days 89' to get the last 89 days.\n"
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
    progress: Progress | None = None,
    task_id: TaskID | None = None,
) -> list[Transaction]:
    """Fetch transactions using yearly chunking.

    Monzo API limits:
    - 400 error if time range >= 365 days
    - 403 error if range >= 90 days and SCA expired (>5 min since auth)

    Args:
        client: HTTP client with auth.
        account: Account to fetch transactions for.
        days: Number of days to fetch. None = full history.
        progress: Optional rich Progress instance for progress bar.
        task_id: Optional task ID for progress updates.

    Returns:
        List of transactions sorted by created date.
    """
    now = datetime.now(UTC)
    account_created = account.created or now - timedelta(days=CHUNK_SIZE_DAYS)

    # Calculate start date
    if days is not None:
        start = max(now - timedelta(days=days), account_created)
    else:
        start = account_created

    # Calculate total chunks for progress
    total_days = (now - start).days
    total_chunks = max(1, (total_days + CHUNK_SIZE_DAYS - 1) // CHUNK_SIZE_DAYS)

    if progress and task_id is not None:
        progress.update(task_id, total=total_chunks)

    # Fetch in yearly chunks
    all_txs: list[Transaction] = []
    seen_ids: set[str] = set()
    chunk_start = start
    chunks_done = 0

    while chunk_start < now:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_SIZE_DAYS), now + timedelta(days=1))

        txs, sca_expired = _fetch_chunk(client, account.id, chunk_start, chunk_end, seen_ids)
        all_txs.extend(txs)
        chunks_done += 1

        if progress and task_id is not None:
            progress.update(
                task_id, completed=chunks_done, description=f"{account.type} ({len(all_txs)})"
            )

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
        console.print(f"[bold]Fetching last {days} days[/bold]\n")
    else:
        console.print("[bold]Fetching full transaction history[/bold]\n")

    with monzo_client() as client:
        # Accounts
        accounts = fetch_accounts(client)
        active = [a for a in accounts if not a.closed]
        console.print(f"Accounts: {len(accounts)} ({len(active)} active)")

        # Pots
        pots: list[Pot] = []
        for acc in active:
            pots.extend(fetch_pots(client, acc.id))
        console.print(f"Pots: {len(pots)}")

        # Transactions
        transactions: dict[str, list[Transaction]] = {}
        console.print()
        with Progress(
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            for acc in active:
                task = progress.add_task(acc.type, total=1)
                txs = fetch_transactions(client, acc, days, progress, task)
                transactions[acc.id] = txs
                progress.update(task, description=f"[green]{acc.type}[/green] ({len(txs)})")

        total = sum(len(t) for t in transactions.values())
        console.print(f"\n[bold]Total:[/bold] {total} transactions")

    return MonzoExport(
        exported_at=datetime.now(UTC),
        since=None,
        days=days,
        accounts=accounts,
        pots=pots,
        transactions=transactions,
    )
