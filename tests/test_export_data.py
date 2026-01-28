"""Tests for export_data module using mock API."""

import sys
from pathlib import Path

import httpx
from pytest_mock import MockerFixture

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from export_data import (
    extract_merchants,
    fetch_accounts,
    fetch_pots,
    fetch_transactions,
    merge_transactions,
)


class TestExtractMerchants:
    """Tests for extract_merchants function."""

    def test_extracts_merchant_objects(self) -> None:
        """Should extract merchant dicts from transactions."""
        transactions = [
            {
                "id": "tx_1",
                "merchant": {"id": "merch_1", "name": "Coffee Shop", "category": "eating_out"},
            },
            {
                "id": "tx_2",
                "merchant": {"id": "merch_2", "name": "Supermarket", "category": "groceries"},
            },
        ]
        merchants = extract_merchants(transactions)

        assert len(merchants) == 2
        assert merchants["merch_1"]["name"] == "Coffee Shop"
        assert merchants["merch_2"]["name"] == "Supermarket"

    def test_handles_string_merchant_id(self) -> None:
        """Should skip transactions where merchant is just a string ID."""
        transactions = [
            {"id": "tx_1", "merchant": "merch_1"},  # String, not dict
            {"id": "tx_2", "merchant": {"id": "merch_2", "name": "Shop"}},
        ]
        merchants = extract_merchants(transactions)

        assert len(merchants) == 1
        assert "merch_2" in merchants

    def test_handles_null_merchant(self) -> None:
        """Should skip transactions with null merchant."""
        transactions = [
            {"id": "tx_1", "merchant": None},
            {"id": "tx_2"},  # No merchant key
        ]
        merchants = extract_merchants(transactions)

        assert len(merchants) == 0

    def test_deduplicates_merchants(self) -> None:
        """Same merchant appearing multiple times should only appear once."""
        transactions = [
            {"id": "tx_1", "merchant": {"id": "merch_1", "name": "Shop"}},
            {"id": "tx_2", "merchant": {"id": "merch_1", "name": "Shop"}},
        ]
        merchants = extract_merchants(transactions)

        assert len(merchants) == 1


class TestMergeTransactions:
    """Tests for merge_transactions function."""

    def test_merges_new_transactions(self) -> None:
        """Should add new transactions to cached ones."""
        cached = [{"id": "tx_1", "created": "2024-01-01T10:00:00Z", "amount": -100}]
        new = [{"id": "tx_2", "created": "2024-01-02T10:00:00Z", "amount": -200}]

        merged, new_count = merge_transactions(cached, new)

        assert len(merged) == 2
        assert new_count == 1

    def test_deduplicates_by_id(self) -> None:
        """Should not duplicate transactions with same ID."""
        cached = [{"id": "tx_1", "created": "2024-01-01T10:00:00Z", "amount": -100}]
        new = [
            {"id": "tx_1", "created": "2024-01-01T10:00:00Z", "amount": -100},  # Duplicate
            {"id": "tx_2", "created": "2024-01-02T10:00:00Z", "amount": -200},
        ]

        merged, new_count = merge_transactions(cached, new)

        assert len(merged) == 2
        assert new_count == 1

    def test_updates_existing_transaction(self) -> None:
        """Should update existing transaction if data changed."""
        cached = [
            {"id": "tx_1", "created": "2024-01-01T10:00:00Z", "amount": -100, "settled": None}
        ]
        new = [
            {"id": "tx_1", "created": "2024-01-01T10:00:00Z", "amount": -100, "settled": "2024-01-02"}
        ]

        merged, new_count = merge_transactions(cached, new)

        assert len(merged) == 1
        assert merged[0]["settled"] == "2024-01-02"
        assert new_count == 0

    def test_sorts_by_created_date(self) -> None:
        """Should sort merged transactions by created date."""
        cached = [{"id": "tx_3", "created": "2024-01-03T10:00:00Z"}]
        new = [
            {"id": "tx_1", "created": "2024-01-01T10:00:00Z"},
            {"id": "tx_2", "created": "2024-01-02T10:00:00Z"},
        ]

        merged, _ = merge_transactions(cached, new)

        assert [tx["id"] for tx in merged] == ["tx_1", "tx_2", "tx_3"]

    def test_empty_cached(self) -> None:
        """Should handle empty cached list."""
        new = [{"id": "tx_1", "created": "2024-01-01T10:00:00Z"}]

        merged, new_count = merge_transactions([], new)

        assert len(merged) == 1
        assert new_count == 1


class TestFetchAccounts:
    """Tests for fetch_accounts function with mock client."""

    def test_fetches_accounts(self, mocker: MockerFixture) -> None:
        """Should return accounts from API."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "accounts": [
                {"id": "acc_1", "type": "uk_retail", "closed": False},
                {"id": "acc_2", "type": "uk_retail_joint", "closed": False},
            ]
        }

        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        accounts = fetch_accounts(mock_client)

        assert len(accounts) == 2
        assert accounts[0]["id"] == "acc_1"
        mock_client.get.assert_called_once_with("/accounts")


class TestFetchPots:
    """Tests for fetch_pots function with mock client."""

    def test_fetches_pots_for_account(self, mocker: MockerFixture) -> None:
        """Should fetch pots for specific account."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "pots": [
                {"id": "pot_1", "name": "Savings", "balance": 10000},
                {"id": "pot_2", "name": "Holiday", "balance": 5000},
            ]
        }

        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        pots = fetch_pots(mock_client, "acc_123")

        assert len(pots) == 2
        mock_client.get.assert_called_once_with("/pots", params={"current_account_id": "acc_123"})


class TestFetchTransactions:
    """Tests for fetch_transactions function with mock client."""

    def test_fetches_single_page(self, mocker: MockerFixture) -> None:
        """Should fetch transactions when all fit in one page."""
        responses = [
            {"transactions": [{"id": "tx_1", "amount": -100}, {"id": "tx_2", "amount": -200}]},
            {"transactions": []},
        ]

        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.side_effect = [self._make_response(mocker, r) for r in responses]

        txs = fetch_transactions(mock_client, "acc_123", expand_merchant=True)

        assert len(txs) == 2
        assert txs[0]["id"] == "tx_1"

    def test_paginates_multiple_pages(self, mocker: MockerFixture) -> None:
        """Should paginate through multiple pages."""
        responses = [
            {"transactions": [{"id": "tx_1", "amount": -100}]},
            {"transactions": [{"id": "tx_2", "amount": -200}]},
            {"transactions": []},
        ]

        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.side_effect = [self._make_response(mocker, r) for r in responses]

        txs = fetch_transactions(mock_client, "acc_123")

        assert len(txs) == 2
        calls = mock_client.get.call_args_list
        assert calls[1][1]["params"]["since"] == "tx_1"

    def test_includes_expand_merchant_param(self, mocker: MockerFixture) -> None:
        """Should include expand[] param when expand_merchant=True."""
        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.return_value = self._make_response(mocker, {"transactions": []})

        fetch_transactions(mock_client, "acc_123", expand_merchant=True)

        call_params = mock_client.get.call_args[1]["params"]
        assert call_params["expand[]"] == "merchant"

    def test_excludes_expand_merchant_param(self, mocker: MockerFixture) -> None:
        """Should not include expand[] param when expand_merchant=False."""
        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.return_value = self._make_response(mocker, {"transactions": []})

        fetch_transactions(mock_client, "acc_123", expand_merchant=False)

        call_params = mock_client.get.call_args[1]["params"]
        assert "expand[]" not in call_params

    @staticmethod
    def _make_response(mocker: MockerFixture, data: dict):
        """Create a mock response object."""
        mock = mocker.Mock()
        mock.json.return_value = data
        return mock
