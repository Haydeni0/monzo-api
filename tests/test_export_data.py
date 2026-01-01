"""Tests for export_data module using mock API."""

import httpx
import pytest
from pytest_mock import MockerFixture

from monzo_api.src.export_data import (
    SCAExpiredError,
    fetch_accounts,
    fetch_pots,
    fetch_transactions,
)


class TestFetchAccounts:
    """Tests for fetch_accounts function with mock client."""

    def test_fetches_accounts(self, mocker: MockerFixture) -> None:
        """Should return Account models from API."""
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
        assert accounts[0].id == "acc_1"
        assert accounts[0].type == "uk_retail"
        mock_client.get.assert_called_once_with("/accounts")


class TestFetchPots:
    """Tests for fetch_pots function with mock client."""

    def test_fetches_pots_for_account(self, mocker: MockerFixture) -> None:
        """Should fetch Pot models for specific account."""
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
        assert pots[0].id == "pot_1"
        assert pots[0].balance == 10000
        mock_client.get.assert_called_once_with("/pots", params={"current_account_id": "acc_123"})


class TestFetchTransactions:
    """Tests for fetch_transactions function with mock client."""

    def test_fetches_single_page(self, mocker: MockerFixture) -> None:
        """Should fetch Transaction models when all fit in one page."""
        responses = [
            {"transactions": [
                {"id": "tx_1", "account_id": "acc_1", "amount": -100, "created": "2024-01-01T10:00:00Z"},
                {"id": "tx_2", "account_id": "acc_1", "amount": -200, "created": "2024-01-01T11:00:00Z"},
            ]},
            {"transactions": []},
        ]

        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.side_effect = [self._make_response(mocker, r) for r in responses]

        txs = fetch_transactions(mock_client, "acc_123", "2024-01-01T00:00:00Z")

        assert len(txs) == 2
        assert txs[0].id == "tx_1"
        assert txs[0].amount == -100

    def test_paginates_multiple_pages(self, mocker: MockerFixture) -> None:
        """Should paginate through multiple pages."""
        responses = [
            {"transactions": [{"id": "tx_1", "account_id": "acc_1", "amount": -100, "created": "2024-01-01T10:00:00Z"}]},
            {"transactions": [{"id": "tx_2", "account_id": "acc_1", "amount": -200, "created": "2024-01-01T11:00:00Z"}]},
            {"transactions": []},
        ]

        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.side_effect = [self._make_response(mocker, r) for r in responses]

        txs = fetch_transactions(mock_client, "acc_123", "2024-01-01T00:00:00Z")

        assert len(txs) == 2
        # Second call should use last tx ID as since
        calls = mock_client.get.call_args_list
        assert calls[1][1]["params"]["since"] == "tx_1"

    def test_raises_sca_expired_on_403(self, mocker: MockerFixture) -> None:
        """Should raise SCAExpiredError on 403 (90-day limit)."""
        mock_response = mocker.Mock()
        mock_response.status_code = 403

        mock_client = mocker.Mock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        with pytest.raises(SCAExpiredError) as exc_info:
            fetch_transactions(mock_client, "acc_123", "2024-01-01T00:00:00Z")

        assert "monzo auth --force" in str(exc_info.value)

    @staticmethod
    def _make_response(mocker: MockerFixture, data: dict):
        """Create a mock response object."""
        mock = mocker.Mock()
        mock.json.return_value = data
        mock.status_code = 200
        return mock
