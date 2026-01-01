"""Tests for MonzoDatabase class."""

from pathlib import Path

import pytest

from monzo_api.src.db_schema import MonzoDatabase


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
