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

from monzo_api.src.config import DB_FILE

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
    sort_code TEXT,
    account_number TEXT,
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
CREATE OR REPLACE VIEW daily_balances AS
WITH daily_totals AS (
    SELECT
        DATE_TRUNC('day', created)::DATE as date,
        account_id,
        SUM(amount) as daily_net
    FROM transactions
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
        print(f"Database setup complete: {self.db_path}")

    def reset(self) -> None:
        """Drop all tables and recreate."""
        with self as conn:
            conn.execute("DROP VIEW IF EXISTS daily_balances")
            conn.execute("DROP TABLE IF EXISTS transactions")
            conn.execute("DROP TABLE IF EXISTS pots")
            conn.execute("DROP TABLE IF EXISTS merchants")
            conn.execute("DROP TABLE IF EXISTS accounts")
            conn.execute(SCHEMA)
        print(f"Database reset complete: {self.db_path}")

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
        print("\nDatabase Statistics")
        print("=" * 30)
        for table, count in self.stats().items():
            print(f"  {table:20} {count:>6} rows")
        print()
