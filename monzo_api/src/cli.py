"""Monzo API CLI."""

import json

import typer

from monzo_api.src.api_calls import export as export_data
from monzo_api.src.api_calls import fetch_accounts, fetch_balance
from monzo_api.src.config import CACHE_FILE, DB_FILE, TOKEN_FILE
from monzo_api.src.database import MonzoDatabase
from monzo_api.src.get_token import token_oauth
from monzo_api.src.utils import load_token, load_token_data, monzo_client

app = typer.Typer(help="Monzo API tools for exporting and analyzing your data.")


@app.command()
def auth(
    force: bool = typer.Option(False, "--force", "-f", help="Force new authentication"),
) -> None:
    """Authenticate with Monzo and get an access token."""
    if force and TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        typer.echo("Removed existing token.")

    token_oauth()


def _verify_balances(api_balances: dict[str, float], db_balances: dict[str, float]) -> bool:
    typer.echo("Balance verification:")
    all_ok = True
    for acc_id, api_bal in api_balances.items():
        db_bal = db_balances.get(acc_id, 0.0)
        diff = api_bal - db_bal
        if abs(diff) >= 0.01:
            typer.echo(
                f"  {acc_id}: MISMATCH (API={api_bal:.2f}, DB={db_bal:.2f}, diff={diff:+.2f})"
            )
            all_ok = False

    if not all_ok:
        typer.echo("\n  Warning: Balance mismatch may indicate missing transactions")


@app.command()
def export(
    days: int | None = typer.Option(None, "--days", "-d", help="Days of history (omit for full)"),
    no_ingest: bool = typer.Option(False, "--no-ingest", help="Skip database import (JSON only)"),
) -> None:
    """Export Monzo data to JSON and ingest into database.

    Fetches full history by default using backward pagination.
    Use --days to limit to recent transactions only.

    Verifies balances against database after export, and shows a warning if there are any mismatches.
    """
    results = export_data(days)
    results.save(CACHE_FILE)
    typer.echo(f"Saved to {CACHE_FILE}")

    if no_ingest:
        typer.echo("Skipping database ingest (--no-ingest)")
        return

    database = MonzoDatabase()
    database.import_data(results)
    database.print_stats()

    # Verify balances against database
    with monzo_client() as client:
        accounts = fetch_accounts(client)
        api_balances = {
            acc.id: fetch_balance(client, acc.id).balance_pounds
            for acc in accounts
            if not acc.closed
        }

    db_balances = database.account_balances

    _verify_balances(api_balances, db_balances)


@app.command()
def db(
    reset: bool = typer.Option(False, "--reset", help="Drop and recreate all tables"),
    stats: bool = typer.Option(False, "--stats", "-s", help="Show database statistics"),
) -> None:
    """Manage the DuckDB database."""
    database = MonzoDatabase()

    if reset:
        confirm = typer.confirm("This will DELETE all data. Continue?")
        if confirm:
            database.reset()
        else:
            typer.echo("Aborted.")
            raise typer.Exit(1)
    elif stats:
        database.print_stats()
    else:
        typer.echo("Ensuring database schema...")
        database.setup()
        database.print_stats()


@app.command()
def status() -> None:
    """Show current authentication and cache status."""
    typer.echo("Monzo API Status\n")

    # Token status
    token_data = load_token_data()
    if token_data:
        typer.echo(f"  Token: Found ({TOKEN_FILE.name})")
        if "access_token" in token_data:
            typer.echo(f"         {token_data['access_token'][:30]}...")
    else:
        typer.echo("  Token: Not found")

    # Cache status
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text())
        tx_count = sum(len(txs) for txs in cache.get("transactions", {}).values())
        typer.echo(f"\n  Cache: {CACHE_FILE.name}")
        typer.echo(f"         Accounts: {len(cache.get('accounts', []))}")
        typer.echo(f"         Pots: {len(cache.get('pots', []))}")
        typer.echo(f"         Transactions: {tx_count}")
        if cache.get("exported_at"):
            typer.echo(f"         Exported: {cache['exported_at'][:19]}")
        if cache.get("days"):
            typer.echo(f"         Days: {cache['days']}")
    else:
        typer.echo("\n  Cache: Not found")

    # Database status
    if DB_FILE.exists():
        database = MonzoDatabase()
        db_stats = database.stats()
        typer.echo(f"\n  Database: {DB_FILE.name}")
        for table, count in db_stats.items():
            typer.echo(f"            {table}: {count}")
    else:
        typer.echo("\n  Database: Not found")


if __name__ == "__main__":
    app()
