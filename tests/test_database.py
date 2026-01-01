"""Tests for MonzoDatabase class."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from monzo_api.src.database import MonzoDatabase
from monzo_api.src.models import Account, Merchant, MonzoExport, Pot, Transaction


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Return a path for a temporary database (file doesn't exist yet)."""
    return tmp_path / "test.duckdb"


class TestMonzoDatabase:
    """End-to-end tests for MonzoDatabase."""

    def test_setup_creates_tables(self, temp_db: Path, capsys: pytest.CaptureFixture) -> None:
        """Setup should create all tables and indexes."""
        db = MonzoDatabase(temp_db)
        db.setup()

        captured = capsys.readouterr()
        assert "Database setup complete" in captured.out

        # Verify tables exist by querying them
        with db as conn:
            for table in ["accounts", "merchants", "transactions", "pots"]:
                result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                assert result is not None

    def test_context_manager_returns_connection(self, temp_db: Path) -> None:
        """Context manager should return a working DuckDB connection."""
        db = MonzoDatabase(temp_db)
        db.setup()

        with db as conn:
            conn.execute("INSERT INTO accounts (id, type) VALUES ('acc_123', 'uk_retail')")
            result = conn.execute("SELECT id FROM accounts").fetchone()
            assert result[0] == "acc_123"

    def test_stats_returns_row_counts(self, temp_db: Path) -> None:
        """Stats should return dict with row counts for all tables."""
        db = MonzoDatabase(temp_db)
        db.setup()

        # Insert some test data
        with db as conn:
            conn.execute("INSERT INTO accounts (id, type) VALUES ('acc_1', 'uk_retail')")
            conn.execute("INSERT INTO accounts (id, type) VALUES ('acc_2', 'uk_retail')")
            conn.execute("INSERT INTO merchants (id, name) VALUES ('merch_1', 'Test Shop')")

        stats = db.stats()
        assert stats["accounts"] == 2
        assert stats["merchants"] == 1
        assert stats["transactions"] == 0
        assert stats["pots"] == 0

    def test_reset_clears_all_data(self, temp_db: Path) -> None:
        """Reset should drop and recreate all tables."""
        db = MonzoDatabase(temp_db)
        db.setup()

        # Insert data
        with db as conn:
            conn.execute("INSERT INTO accounts (id, type) VALUES ('acc_1', 'uk_retail')")
            conn.execute("INSERT INTO merchants (id, name) VALUES ('merch_1', 'Shop')")

        # Reset
        db.reset()

        # Verify empty
        stats = db.stats()
        assert all(count == 0 for count in stats.values())

    def test_read_only_connection(self, temp_db: Path) -> None:
        """Read-only connection should prevent writes."""
        db = MonzoDatabase(temp_db)
        db.setup()

        db_ro = MonzoDatabase(temp_db, read_only=True)
        with db_ro as conn:
            # Read should work
            conn.execute("SELECT * FROM accounts")

            # Write should fail
            with pytest.raises(Exception):  # noqa: B017
                conn.execute("INSERT INTO accounts (id, type) VALUES ('x', 'y')")

    def test_daily_balances_view(self, temp_db: Path) -> None:
        """Daily balances view should calculate running totals."""
        db = MonzoDatabase(temp_db)
        db.setup()

        with db as conn:
            conn.execute("INSERT INTO accounts (id, type) VALUES ('acc_1', 'uk_retail')")
            conn.execute("""
                INSERT INTO transactions (id, account_id, amount, created, currency)
                VALUES
                    ('tx_1', 'acc_1', 10000, '2024-01-01 10:00:00', 'GBP'),
                    ('tx_2', 'acc_1', -2000, '2024-01-01 14:00:00', 'GBP'),
                    ('tx_3', 'acc_1', -3000, '2024-01-02 10:00:00', 'GBP')
            """)

            result = conn.execute("""
                SELECT date, daily_net, eod_balance
                FROM daily_balances
                ORDER BY date
            """).fetchall()

            # Day 1: +10000 - 2000 = 8000 net, 8000 eod
            # Day 2: -3000 net, 5000 eod
            assert len(result) == 2
            assert result[0][1] == 8000  # daily_net day 1
            assert result[0][2] == 8000  # eod_balance day 1
            assert result[1][1] == -3000  # daily_net day 2
            assert result[1][2] == 5000  # eod_balance day 2

    def test_import_accounts(self, temp_db: Path) -> None:
        """Should import Account models."""
        db = MonzoDatabase(temp_db)
        db.setup()

        accounts = [
            Account(id="acc_1", type="uk_retail", closed=False),
            Account(id="acc_2", type="uk_retail_joint", closed=True),
        ]
        count = db.import_accounts(accounts)

        assert count == 2
        with db as conn:
            rows = conn.execute("SELECT id, type, closed FROM accounts ORDER BY id").fetchall()
            assert rows[0] == ("acc_1", "uk_retail", False)
            assert rows[1] == ("acc_2", "uk_retail_joint", True)

    def test_import_merchants(self, temp_db: Path) -> None:
        """Should import Merchant models."""
        db = MonzoDatabase(temp_db)
        db.setup()

        merchants = {
            "merch_1": Merchant(
                id="merch_1", name="Coffee Shop", category="eating_out", emoji="☕"
            ),
            "merch_2": Merchant(id="merch_2", name="Supermarket", category="groceries"),
        }
        count = db.import_merchants(merchants)

        assert count == 2
        with db as conn:
            rows = conn.execute("SELECT id, name, category FROM merchants ORDER BY id").fetchall()
            assert rows[0] == ("merch_1", "Coffee Shop", "eating_out")
            assert rows[1] == ("merch_2", "Supermarket", "groceries")

    def test_import_transactions(self, temp_db: Path) -> None:
        """Should import Transaction models."""
        db = MonzoDatabase(temp_db)
        db.setup()

        # Need account first due to FK
        with db as conn:
            conn.execute("INSERT INTO accounts (id, type) VALUES ('acc_1', 'uk_retail')")

        transactions = [
            Transaction(
                id="tx_1",
                account_id="acc_1",
                amount=-500,
                created=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
                category="eating_out",
            ),
        ]
        count = db.import_transactions(transactions)

        assert count == 1
        with db as conn:
            row = conn.execute("SELECT id, amount, category FROM transactions").fetchone()
            assert row == ("tx_1", -500, "eating_out")

    def test_import_pots(self, temp_db: Path) -> None:
        """Should import Pot models."""
        db = MonzoDatabase(temp_db)
        db.setup()

        # Need account first due to FK
        with db as conn:
            conn.execute("INSERT INTO accounts (id, type) VALUES ('acc_1', 'uk_retail')")

        pots = [
            Pot(id="pot_1", name="Savings", balance=10000, current_account_id="acc_1"),
        ]
        count = db.import_pots(pots)

        assert count == 1
        with db as conn:
            row = conn.execute("SELECT id, name, balance FROM pots").fetchone()
            assert row == ("pot_1", "Savings", 10000)

    def test_import_data_full_export(self, temp_db: Path, capsys: pytest.CaptureFixture) -> None:
        """Should import a complete MonzoExport."""
        db = MonzoDatabase(temp_db)

        export = MonzoExport(
            exported_at=datetime.now(UTC),
            accounts=[Account(id="acc_1", type="uk_retail")],
            pots=[Pot(id="pot_1", name="Savings", balance=5000, current_account_id="acc_1")],
            transactions={
                "acc_1": [
                    Transaction(
                        id="tx_1",
                        account_id="acc_1",
                        amount=-100,
                        created=datetime(2024, 1, 1, tzinfo=UTC),
                        merchant=Merchant(id="merch_1", name="Shop"),
                    ),
                ]
            },
        )

        counts = db.import_data(export)

        assert counts["accounts"] == 1
        assert counts["merchants"] == 1
        assert counts["transactions"] == 1
        assert counts["pots"] == 1

        # Verify data in DB
        stats = db.stats()
        assert stats["accounts"] == 1
        assert stats["merchants"] == 1
        assert stats["transactions"] == 1
        assert stats["pots"] == 1
