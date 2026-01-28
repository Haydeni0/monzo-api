"""Monzo API CLI."""

import json

import typer
from rich.table import Table

from monzo_api.src.api_calls import export as export_data
from monzo_api.src.api_calls import fetch_accounts, fetch_balance
from monzo_api.src.config import CACHE_FILE, DB_FILE, TOKEN_FILE
from monzo_api.src.database import MonzoDatabase
from monzo_api.src.get_token import token_oauth
from monzo_api.src.utils import console, load_token_data, monzo_client

app = typer.Typer(help="Monzo API tools for exporting and analyzing your data.")


@app.command()
def auth(
    force: bool = typer.Option(False, "--force", "-f", help="Force new authentication"),
) -> None:
    """Authenticate with Monzo and get an access token."""
    if force and TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        console.print("[yellow]Removed existing token.[/yellow]")

    token_oauth()


def _verify_balances(
    accounts: list, api_balances: dict[str, float], db_balances: dict[str, float]
) -> bool:
    """Verify API balances match database. Returns True if all OK."""
    # Build balance table
    table = Table(title="Account Balances", show_header=True, header_style="bold")
    table.add_column("Account")
    table.add_column("Balance", justify="right")
    table.add_column("Status", justify="center")

    all_ok = True
    for acc in accounts:
        if acc.closed or acc.id not in api_balances:
            continue
        api_bal = api_balances[acc.id]
        db_bal = db_balances.get(acc.id, 0.0)
        diff = api_bal - db_bal
        ok = abs(diff) < 0.01

        if ok:
            status = "[green]OK[/green]"
        else:
            status = f"[red]diff {diff:+.2f}[/red]"
            all_ok = False

        table.add_row(acc.type, f"£{api_bal:,.2f}", status)

    console.print()
    console.print(table)

    if not all_ok:
        console.print(
            "\n[yellow]Warning: Balances do not match between the API and the database."
            " Full export may be required (run `monzo export` again)[/yellow]"
        )
    return all_ok


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
    console.print(f"Saved to [cyan]{CACHE_FILE}[/cyan]")

    if no_ingest:
        console.print("[dim]Skipping database ingest (--no-ingest)[/dim]")
        return

    database = MonzoDatabase()
    database.import_data(results)

    # Verify balances against database
    with monzo_client() as client:
        accounts = fetch_accounts(client)
        api_balances = {
            acc.id: fetch_balance(client, acc.id).balance_pounds
            for acc in accounts
            if not acc.closed
        }

    db_balances = database.account_balances

    _verify_balances(accounts, api_balances, db_balances)


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
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(1)
    elif stats:
        database.print_stats()
    else:
        console.print("[dim]Ensuring database schema...[/dim]")
        database.setup()
        database.print_stats()


@app.command()
def status() -> None:
    """Show current authentication and cache status."""
    console.print("[bold]Monzo API Status[/bold]\n")

    # Token status
    token_data = load_token_data()
    if token_data:
        console.print(f"  [green]Token:[/green] {TOKEN_FILE.name}")
        if "access_token" in token_data:
            console.print(f"         [dim]{token_data['access_token'][:30]}...[/dim]")
    else:
        console.print("  [red]Token:[/red] Not found")

    # Cache status
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text())
        tx_count = sum(len(txs) for txs in cache.get("transactions", {}).values())
        console.print(f"\n  [green]Cache:[/green] {CACHE_FILE.name}")
        console.print(f"         Accounts: {len(cache.get('accounts', []))}")
        console.print(f"         Pots: {len(cache.get('pots', []))}")
        console.print(f"         Transactions: {tx_count}")
        if cache.get("exported_at"):
            console.print(f"         Exported: {cache['exported_at'][:19]}")
        if cache.get("days"):
            console.print(f"         Days: {cache['days']}")
    else:
        console.print("\n  [red]Cache:[/red] Not found")

    # Database status
    if DB_FILE.exists():
        database = MonzoDatabase()
        db_stats = database.stats()
        table = Table(title="Database", show_header=True, header_style="bold")
        table.add_column("Table")
        table.add_column("Rows", justify="right")
        for tbl, count in db_stats.items():
            table.add_row(tbl, str(count))
        console.print()
        console.print(table)
    else:
        console.print("\n  [red]Database:[/red] Not found")


if __name__ == "__main__":
    app()
