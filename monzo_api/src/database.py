r"""Database schema for Monzo data.

This module defines the DuckDB schema and provides setup utilities.

Example Transaction (Card Payment)
----------------------------------
{
  "id": "tx_0000B0n9HF2BKpL4yNL1DF",
  "account_id": "acc_00009SjLNnVm2azUY0bgRt",
  "amount": -5603,                        # negative = spend, in minor units (pence)
  "currency": "GBP",
  "local_amount": -7394,                  # original currency amount
  "local_currency": "USD",
  "description": "TST* SDCM - KETTNER EX SAN DIEGO USA",
  "category": "eating_out",
  "merchant": "merch_0000AawzqnRZ8MtORKeHlx",   # just ID, need expand[] for details
  "created": "2025-12-01T03:17:51.795Z",
  "settled": "2025-12-02T02:16:02.035Z",
  "scheme": "mastercard",
  "is_load": false,
  "include_in_spending": true,
  "notes": "",
  "metadata": {
    "mcc": "5813",                         # merchant category code
    "mastercard_lifecycle_id": "...",
    "trip_id": "trip_0000B0mtQVzK4Uyrw2nsN1"
  }
}

Example Transaction (Income/BACS)
---------------------------------
{
  "id": "tx_0000B1HKxZPMu4KXaEBini",
  "amount": 51817,                         # positive = income
  "category": "income",
  "description": "PHYSICSX EXPENSES",
  "merchant": "merch_0000AbD7equcJuM3NmEzRJ",
  "scheme": "bacs",
  "counterparty": {                        # sender details for bank transfers
    "account_number": "01533886",
    "name": "PHYSICSX LIMITED T",
    "sort_code": "401016"
  },
  "metadata": {
    "payday": "true",
    "bacs_payment_id": "..."
  }
}

Expanded Merchant (via ?expand[]=merchant)
------------------------------------------
{
  "merchant": {
    "id": "merch_0000AawzqnRZ8MtORKeHlx",
    "group_id": "grp_0000AbJxu2rSj8klFpLqBP",
    "name": "SDCM Kettner Exchange",
    "logo": "https://mondo-logo-cache.appspot.com/...",
    "emoji": "🍔",
    "category": "eating_out",
    "online": false,
    "atm": false,
    "address": {
      "short_formatted": "2001 Kettner Blvd, San Diego",
      "formatted": "2001 Kettner Blvd\\nSan Diego\\nCA 92101\\nUnited States",
      "city": "San Diego",
      "region": "CA",
      "country": "USA",
      "postcode": "92101",
      "latitude": 32.7218,
      "longitude": -117.1693
    }
  }
}
"""

from pathlib import Path

import duckdb
from rich.progress import Progress
from rich.table import Table

from monzo_api.src.config import DB_FILE
from monzo_api.src.models import Account, Merchant, MonzoExport, Pot, Transaction
from monzo_api.src.utils import console

SCHEMA = """
-- ============================================
-- MONZO DATABASE SCHEMA
-- ============================================

-- Accounts table
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    description TEXT,
    created TIMESTAMP,
    closed BOOLEAN DEFAULT FALSE,
    currency TEXT DEFAULT 'GBP'
);

-- Merchants table (normalized)
CREATE TABLE IF NOT EXISTS merchants (
    id TEXT PRIMARY KEY,
    group_id TEXT,
    name TEXT,
    category TEXT,
    emoji TEXT,
    logo_url TEXT,
    online BOOLEAN DEFAULT FALSE,
    atm BOOLEAN DEFAULT FALSE,

    -- Address
    address TEXT,
    city TEXT,
    region TEXT,
    country TEXT,
    postcode TEXT,
    latitude DOUBLE,
    longitude DOUBLE,

    -- Stats
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    transaction_count INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    merchant_id TEXT,

    -- Timing
    created TIMESTAMP NOT NULL,
    settled TIMESTAMP,

    -- Money (pence)
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'GBP',
    local_amount INTEGER,
    local_currency TEXT,

    -- Description
    description TEXT,
    category TEXT,
    notes TEXT,

    -- Metadata
    mcc TEXT,
    scheme TEXT,
    is_load BOOLEAN DEFAULT FALSE,
    include_in_spending BOOLEAN DEFAULT TRUE,
    decline_reason TEXT,

    -- Foreign keys
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

-- Pots table
CREATE TABLE IF NOT EXISTS pots (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    name TEXT,
    style TEXT,
    balance INTEGER,
    goal INTEGER,
    currency TEXT DEFAULT 'GBP',
    created TIMESTAMP,
    updated TIMESTAMP,
    deleted BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- Daily balances (view - calculated from transactions)
-- Shows cumulative balance at end of each day
-- EXCLUDES declined transactions (decline_reason IS NOT NULL)
CREATE OR REPLACE VIEW daily_balances AS
WITH daily_totals AS (
    SELECT
        DATE_TRUNC('day', created)::DATE as date,
        account_id,
        SUM(amount) as daily_net
    FROM transactions
    WHERE decline_reason IS NULL  -- Exclude declined transactions
    GROUP BY 1, 2
)
SELECT
    date,
    account_id,
    daily_net,
    SUM(daily_net) OVER (PARTITION BY account_id ORDER BY date) as eod_balance
FROM daily_totals;

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX IF NOT EXISTS idx_tx_account_date ON transactions(account_id, created);
CREATE INDEX IF NOT EXISTS idx_tx_merchant ON transactions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created);
CREATE INDEX IF NOT EXISTS idx_merchants_group ON merchants(group_id);
CREATE INDEX IF NOT EXISTS idx_merchants_category ON merchants(category);
CREATE INDEX IF NOT EXISTS idx_pots_account ON pots(account_id);
"""


class MonzoDatabase:
    """Interface for Monzo DuckDB database. Also a context manager for connections."""

    def __init__(self, db_path: str | Path = DB_FILE, read_only: bool = False) -> None:
        """Initialize database with given path."""
        self.db_path = Path(db_path)
        self.read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> duckdb.DuckDBPyConnection:
        """Open database connection."""
        self._conn = duckdb.connect(str(self.db_path), read_only=self.read_only)
        return self._conn

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def setup(self) -> None:
        """Create all tables, views, and indexes."""
        with self as conn:
            conn.execute(SCHEMA)
        console.print(f"[green]Database setup complete:[/green] {self.db_path}")

    def reset(self) -> None:
        """Drop all tables and recreate."""
        with self as conn:
            conn.execute("DROP VIEW IF EXISTS daily_balances")
            conn.execute("DROP TABLE IF EXISTS transactions")
            conn.execute("DROP TABLE IF EXISTS pots")
            conn.execute("DROP TABLE IF EXISTS merchants")
            conn.execute("DROP TABLE IF EXISTS accounts")
            conn.execute(SCHEMA)
        console.print(f"[yellow]Database reset complete:[/yellow] {self.db_path}")

    def stats(self) -> dict[str, int]:
        """Get row counts for all tables and views."""
        tables = ["accounts", "merchants", "transactions", "pots"]

        with MonzoDatabase(self.db_path, read_only=True) as conn:
            result = {}
            for table in [*tables, "daily_balances"]:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                result[table] = row[0] if row else 0
            return result

    def print_stats(self) -> None:
        """Print database statistics."""
        table = Table(title="Database Statistics", show_header=True, header_style="bold")
        table.add_column("Table")
        table.add_column("Rows", justify="right")
        for tbl, count in self.stats().items():
            table.add_row(tbl, f"{count:,}")
        console.print()
        console.print(table)

    # ==========================================
    # IMPORT METHODS
    # ==========================================

    def import_accounts(self, accounts: list[Account]) -> int:
        """Import accounts into database. Returns count imported."""
        with self as conn:
            for acc in accounts:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO accounts
                    (id, type, description, created, closed, currency)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        acc.id,
                        acc.type,
                        acc.description,
                        acc.created,
                        acc.closed,
                        acc.currency,
                    ),
                )
        return len(accounts)

    def import_merchants(self, merchants: dict[str, Merchant]) -> int:
        """Import merchants into database. Returns count imported."""
        with self as conn:
            for m in merchants.values():
                addr = m.address
                conn.execute(
                    """
                    INSERT OR REPLACE INTO merchants
                    (id, group_id, name, category, emoji, logo_url, online, atm,
                     address, city, region, country, postcode, latitude, longitude)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m.id,
                        m.group_id,
                        m.name,
                        m.category,
                        m.emoji,
                        m.logo,
                        m.online,
                        m.atm,
                        addr.formatted if addr else None,
                        addr.city if addr else None,
                        addr.region if addr else None,
                        addr.country if addr else None,
                        addr.postcode if addr else None,
                        addr.latitude if addr else None,
                        addr.longitude if addr else None,
                    ),
                )
        return len(merchants)

    def import_transactions(self, transactions: list[Transaction]) -> int:
        """Import transactions into database. Returns count imported."""
        with self as conn:
            for tx in transactions:
                # Handle settled being empty string
                settled = tx.settled if tx.settled and tx.settled != "" else None

                # Extract MCC from metadata
                mcc = tx.metadata.get("mcc") if tx.metadata else None

                conn.execute(
                    """
                    INSERT OR REPLACE INTO transactions
                    (id, account_id, merchant_id, created, settled, amount, currency,
                     local_amount, local_currency, description, category, notes,
                     mcc, scheme, is_load, include_in_spending, decline_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tx.id,
                        tx.account_id,
                        tx.merchant_id,
                        tx.created,
                        settled,
                        tx.amount,
                        tx.currency,
                        tx.local_amount,
                        tx.local_currency,
                        tx.description,
                        tx.category,
                        tx.notes,
                        mcc,
                        tx.scheme,
                        tx.is_load,
                        tx.include_in_spending,
                        tx.decline_reason,
                    ),
                )
        return len(transactions)

    def import_pots(self, pots: list[Pot]) -> int:
        """Import pots into database. Returns count imported."""
        with self as conn:
            for pot in pots:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pots
                    (id, account_id, name, style, balance, goal, currency, created, updated, deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pot.id,
                        pot.current_account_id,
                        pot.name,
                        pot.style,
                        pot.balance,
                        pot.goal_amount,
                        pot.currency,
                        pot.created,
                        pot.updated,
                        pot.deleted,
                    ),
                )
        return len(pots)

    def import_data(self, data: MonzoExport) -> dict[str, int]:
        """Import all data from a MonzoExport. Returns counts per table."""
        # Ensure schema exists
        self.setup()

        counts = {}

        with Progress(console=console) as progress:
            task = progress.add_task("[cyan]Importing...", total=4)

            counts["accounts"] = self.import_accounts(data.accounts)
            progress.update(task, advance=1, description="[cyan]Accounts done")

            counts["merchants"] = self.import_merchants(data.all_merchants)
            progress.update(task, advance=1, description="[cyan]Merchants done")

            counts["transactions"] = self.import_transactions(data.all_transactions)
            progress.update(task, advance=1, description="[cyan]Transactions done")

            counts["pots"] = self.import_pots(data.pots)
            progress.update(task, advance=1, description="[cyan]Pots done")

        # Show import summary
        table = Table(title="Import Complete", show_header=True, header_style="bold")
        table.add_column("Table")
        table.add_column("Rows", justify="right")
        for tbl, count in counts.items():
            table.add_row(tbl, f"{count:,}")
        console.print(table)

        return counts

    @property
    def account_balances(self) -> dict[str, float]:
        """Get current balance per account from database.

        Returns dict of account_id -> balance in pounds (from daily_balances view).
        """
        with self as conn:
            rows = conn.execute("""
                SELECT account_id, eod_balance / 100.0 as balance
                FROM daily_balances
                WHERE (account_id, date) IN (
                    SELECT account_id, MAX(date) FROM daily_balances GROUP BY account_id
                )
            """).fetchall()
        return {row[0]: row[1] for row in rows}
