"""Tests for api_calls.py fetch_transactions."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pytest_mock import MockerFixture

from monzo_api.src.api_calls import SCAExpiredError, fetch_transactions
from monzo_api.src.models import Account


def make_tx(tx_id: str, created: datetime, amount: int = -100) -> dict:
    """Create a minimal transaction dict for testing."""
    return {
        "id": tx_id,
        "created": created.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "amount": amount,
        "currency": "GBP",
        "description": f"Test tx {tx_id}",
        "account_id": "acc_test",
    }


@pytest.fixture
def mock_client(mocker: MockerFixture):
    """Create a mock httpx.Client."""
    return mocker.MagicMock(spec=httpx.Client)


@pytest.fixture
def make_response(mocker: MockerFixture):
    """Factory fixture to create mock response objects."""

    def _make_response(txs: list[dict], status: int = 200):
        resp = mocker.MagicMock()
        resp.status_code = status
        resp.json.return_value = {"transactions": txs}
        if status >= 400:
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Error", request=mocker.MagicMock(), response=resp
            )
        return resp

    return _make_response


@pytest.fixture
def test_account() -> Account:
    """Create a test account."""
    return Account(
        id="acc_test",
        type="uk_retail",
        created=datetime.now(UTC) - timedelta(days=100),
        closed=False,
    )


class TestFetchTransactions:
    """Tests for fetch_transactions (yearly chunking)."""

    def test_full_history_uses_account_created(self, mock_client, make_response, test_account):
        """Test that days=None fetches from account creation."""
        now = datetime.now(UTC)
        txs_data = [make_tx(f"tx_{i}", now - timedelta(days=i)) for i in range(5)]

        mock_client.get.side_effect = [
            make_response(txs_data),
            make_response([]),
        ]

        txs = fetch_transactions(mock_client, test_account, days=None)
        assert len(txs) == 5

    def test_days_limits_history(self, mock_client, make_response):
        """Test that days param limits how far back we fetch."""
        now = datetime.now(UTC)
        account = Account(
            id="acc_test",
            type="uk_retail",
            created=now - timedelta(days=500),
            closed=False,
        )
        txs_data = [make_tx(f"tx_{i}", now - timedelta(days=i)) for i in range(10)]

        mock_client.get.side_effect = [
            make_response(txs_data),
            make_response([]),
        ]

        txs = fetch_transactions(mock_client, account, days=30)
        assert len(txs) == 10

    def test_days_exceeding_account_age(self, mock_client, make_response, capsys):
        """Test that requesting more days than account age uses account creation."""
        now = datetime.now(UTC)
        account = Account(
            id="acc_test",
            type="uk_retail",
            created=now - timedelta(days=50),
            closed=False,
        )
        txs_data = [make_tx(f"tx_{i}", now - timedelta(days=i)) for i in range(5)]

        mock_client.get.side_effect = [
            make_response(txs_data),
            make_response([]),
        ]

        txs = fetch_transactions(mock_client, account, days=100)
        assert len(txs) == 5
        assert "only 50 days old" in capsys.readouterr().out

    def test_sca_expired_on_first_request_raises(self, mock_client, make_response, test_account):
        """Test that SCAExpiredError is raised when 403 on first tx request."""
        mock_client.get.return_value = make_response([], status=403)

        with pytest.raises(SCAExpiredError):
            fetch_transactions(mock_client, test_account)

    def test_sca_expired_mid_pagination_returns_partial(
        self, mock_client, make_response, test_account
    ):
        """Test graceful stop if 403 mid-way."""
        now = datetime.now(UTC)
        page1 = [make_tx(f"tx_{i}", now - timedelta(days=i)) for i in range(10)]

        mock_client.get.side_effect = [
            make_response(page1),
            make_response([], status=403),
        ]

        txs = fetch_transactions(mock_client, test_account)
        assert len(txs) == 10

    def test_returns_sorted_by_created(self, mock_client, make_response, test_account):
        """Test that results are sorted oldest first."""
        now = datetime.now(UTC)

        txs_data = [
            make_tx("tx_new", now - timedelta(days=5)),
            make_tx("tx_old", now - timedelta(days=50)),
        ]

        mock_client.get.side_effect = [
            make_response(txs_data),
            make_response([]),
        ]

        txs = fetch_transactions(mock_client, test_account)

        assert txs[0].id == "tx_old"
        assert txs[1].id == "tx_new"

    def test_pagination_within_chunk(self, mock_client, make_response, test_account):
        """Test pagination when >100 transactions in a chunk."""
        now = datetime.now(UTC)

        page1 = [make_tx(f"tx_{i}", now - timedelta(days=i)) for i in range(100)]
        page2 = [make_tx(f"tx_{i}", now - timedelta(days=i)) for i in range(100, 150)]

        mock_client.get.side_effect = [
            make_response(page1),
            make_response(page2),
            make_response([]),
        ]

        txs = fetch_transactions(mock_client, test_account)
        assert len(txs) == 150

    def test_multi_year_account(self, mock_client, make_response):
        """Test account spanning multiple years."""
        now = datetime.now(UTC)
        account = Account(
            id="acc_test",
            type="uk_retail",
            created=now - timedelta(days=800),
            closed=False,
        )

        year1_txs = [make_tx(f"tx_y1_{i}", now - timedelta(days=700 + i)) for i in range(30)]
        year2_txs = [make_tx(f"tx_y2_{i}", now - timedelta(days=350 + i)) for i in range(40)]
        year3_txs = [make_tx(f"tx_y3_{i}", now - timedelta(days=i)) for i in range(20)]

        mock_client.get.side_effect = [
            make_response(year1_txs),
            make_response([]),
            make_response(year2_txs),
            make_response([]),
            make_response(year3_txs),
            make_response([]),
        ]

        txs = fetch_transactions(mock_client, account)
        assert len(txs) == 90

    def test_handles_400_invalid_range(self, mock_client, make_response):
        """Test that 400 errors are handled gracefully."""
        now = datetime.now(UTC)
        account = Account(
            id="acc_test",
            type="uk_retail",
            created=now - timedelta(days=500),
            closed=False,
        )

        year1_txs = [make_tx(f"tx_{i}", now - timedelta(days=400 + i)) for i in range(20)]

        mock_client.get.side_effect = [
            make_response(year1_txs),
            make_response([]),
            make_response([], status=400),
            make_response([]),
        ]

        txs = fetch_transactions(mock_client, account)
        assert len(txs) == 20
