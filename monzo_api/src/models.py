"""Pydantic models for Monzo API data."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class Address(BaseModel):
    """Merchant address."""

    short_formatted: str | None = None
    formatted: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    postcode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    zoom_level: int | None = None
    approximate: bool | None = None


class Merchant(BaseModel):
    """Merchant details (expanded from transaction)."""

    id: str
    group_id: str | None = None
    name: str | None = None
    category: str | None = None
    emoji: str | None = None
    logo: str | None = None
    online: bool = False
    atm: bool = False
    address: Address | None = None
    disable_feedback: bool | None = None

    model_config = {"extra": "ignore"}


class Counterparty(BaseModel):
    """Bank transfer counterparty details."""

    account_number: str | None = None
    name: str | None = None
    sort_code: str | None = None
    user_id: str | None = None

    model_config = {"extra": "ignore"}


class Transaction(BaseModel):
    """A single transaction."""

    id: str
    account_id: str
    amount: int  # In minor units (pence), negative = spend
    currency: str = "GBP"
    created: datetime
    settled: datetime | str | None = None  # Can be empty string
    description: str | None = None
    category: str | None = None
    notes: str | None = None

    # Merchant - can be string ID or expanded object
    merchant: Merchant | str | None = None

    # Foreign currency
    local_amount: int | None = None
    local_currency: str | None = None

    # Metadata
    scheme: str | None = None  # mastercard, bacs, etc
    is_load: bool = False
    include_in_spending: bool = True
    decline_reason: str | None = None

    # Bank transfers
    counterparty: Counterparty | None = None

    # Raw metadata dict (MCC, trip_id, etc)
    metadata: dict | None = None

    model_config = {"extra": "ignore"}

    @property
    def merchant_id(self) -> str | None:
        """Get merchant ID whether expanded or not."""
        if isinstance(self.merchant, Merchant):
            return self.merchant.id
        return self.merchant if self.merchant else None

    @property
    def amount_pounds(self) -> float:
        """Get amount in pounds (e.g. -5.03 instead of -503)."""
        return self.amount / 100


class Account(BaseModel):
    """A Monzo account."""

    id: str
    type: str  # uk_retail, uk_retail_joint, uk_monzo_flex
    description: str | None = None
    created: datetime | None = None
    closed: bool = False
    currency: str = "GBP"

    model_config = {"extra": "ignore"}


class Pot(BaseModel):
    """A savings pot."""

    id: str
    name: str
    balance: int  # In minor units
    currency: str = "GBP"
    style: str | None = None
    goal_amount: int | None = None
    created: datetime | None = None
    updated: datetime | None = None
    deleted: bool = False
    locked: bool = False
    current_account_id: str | None = Field(None, alias="current_account_id")

    model_config = {"extra": "ignore"}

    @property
    def balance_pounds(self) -> float:
        """Get balance in pounds."""
        return self.balance / 100


class MonzoExport(BaseModel):
    """Complete export of Monzo data."""

    exported_at: datetime
    since: str | None = None  # ISO date string, None = full history
    days: int | None = None  # None = full history
    accounts: list[Account]
    pots: list[Pot]
    transactions: dict[str, list[Transaction]]  # Keyed by account_id

    @property
    def all_transactions(self) -> list[Transaction]:
        """Get all transactions across all accounts."""
        return [tx for txs in self.transactions.values() for tx in txs]

    @property
    def all_merchants(self) -> dict[str, Merchant]:
        """Extract unique merchants from all transactions."""
        merchants = {}
        for tx in self.all_transactions:
            if isinstance(tx.merchant, Merchant):
                merchants[tx.merchant.id] = tx.merchant
        return merchants

    def save(self, path: str | Path) -> None:
        """Save to JSON file."""
        Path(path).write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "MonzoExport":
        """Load from JSON file."""
        return cls.model_validate_json(Path(path).read_text())
