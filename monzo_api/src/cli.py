"""Monzo API CLI."""

import json

import typer

from monzo_api.src.config import CACHE_FILE, DB_FILE, TOKEN_FILE
from monzo_api.src.database import MonzoDatabase
from monzo_api.src.export_data import main as export_main
from monzo_api.src.get_token import main as get_token_main
from monzo_api.src.models import MonzoExport
from monzo_api.src.utils import load_token_data

app = typer.Typer(help="Monzo API tools for exporting and analyzing your data.")


@app.command()
def auth(
    force: bool = typer.Option(False, "--force", "-f", help="Force new authentication"),
) -> None:
    """Authenticate with Monzo and get an access token."""
    if force and TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        typer.echo("Removed existing token.")

    get_token_main()


@app.command()
def export(
    days: int | None = typer.Option(None, "--days", "-d", help="Days of history (omit for full)"),
) -> None:
    """Export Monzo data to JSON.

    Fetches full history by default using backward pagination.
    Use --days to limit to recent transactions only.
    """
    export_main(days)


@app.command()
def ingest() -> None:
    """Import cached JSON data into the database."""
    if not CACHE_FILE.exists():
        typer.echo(f"No cache file found at {CACHE_FILE}")
        typer.echo("Run 'monzo export' first.")
        raise typer.Exit(1)

    typer.echo(f"Loading {CACHE_FILE}...")
    data = MonzoExport.load(CACHE_FILE)
    typer.echo(f"Loaded {len(data.all_transactions)} transactions from {data.exported_at:%Y-%m-%d}\n")

    database = MonzoDatabase()
    database.import_data(data)
    database.print_stats()


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
