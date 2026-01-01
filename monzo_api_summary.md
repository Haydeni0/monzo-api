# Monzo API Documentation Summary & Navigation Guide

## Preamble: How to Use This Guide

This document serves as an index and navigation guide to the Monzo API documentation. It is designed for both AI agents and humans to quickly locate relevant information.

### For AI Agents: Indexing Strategy

1. **Start here**: Scan this document first to understand the documentation structure
2. **Keyword matching**: Use the section headers and descriptions below to identify which source file(s) contain the information you need
3. **Read source files**: Once you've identified relevant files, read them directly for complete details
4. **Cross-reference**: Many concepts span multiple files (e.g., authentication is needed for all endpoints)

### Quick Topic Lookup

| Topic | Primary File |
|-------|-------------|
| OAuth, tokens, login | `_authentication.md` |
| Account list, account types | `_accounts.md` |
| Balance, spend today | `_balance.md` |
| Transactions, categories, merchants | `_transactions.md` |
| Pots, savings, deposits | `_pots.md` |
| Webhooks, real-time events | `_webhooks.md` |
| Receipts, line items | `_receipts.md` |
| Image attachments | `_attachments.md` |
| Feed items, notifications | `_feed_items.md` |
| HTTP errors, status codes | `_errors.md` |
| Pagination, limits | `_pagination.md` |
| Open Banking (AISP) | `_ais.md` |
| Open Banking (PISP) | `_pis.md` |
| Variable Recurring Payments | `_vrp.md` |
| Confirmation of Funds | `_cbpii.md` |

---

## Documentation Structure

The docs are built with [Slate](https://github.com/slatedocs/slate). Source files are located at:

```
docs/source/
├── index.html.md              # Main API docs entry point
├── open-banking/
│   └── index.html.md          # Open Banking API entry point
└── includes/
    └── _*.md                  # Individual topic files
```

---

## Part 1: Public Developer API

**Base URL**: `https://api.monzo.com`

> ⚠️ **Important**: The Monzo Developer API is NOT suitable for building public applications. You may only connect to your own account or a small set of explicitly allowed users.

### Main Entry Point
📄 **File**: [`docs/source/index.html.md`](docs/source/index.html.md)

- API endpoint: `https://api.monzo.com`
- Examples use [httpie](https://github.com/jkbrzt/httpie)
- Links to Monzo developer community forum

---

### Authentication
📄 **File**: [`docs/source/includes/_authentication.md`](docs/source/includes/_authentication.md)

**What's covered:**
- OAuth 2.0 implementation
- Access token acquisition (3-step process)
- Redirect flow to `https://auth.monzo.com`
- Token exchange at `/oauth2/token`
- Authenticating requests with `Authorization: Bearer` header
- Refresh token usage (confidential clients only)
- Token expiry (~6 hours, `expires_in: 21600`)
- Logout endpoint `/oauth2/logout`
- Strong Customer Authentication (SCA) - user must approve in Monzo app
- Confidential vs non-confidential clients
- `/ping/whoami` endpoint for token info

**Key endpoints:**
- `POST /oauth2/token` - Exchange authorization code or refresh token
- `POST /oauth2/logout` - Invalidate token

---

### Pagination
📄 **File**: [`docs/source/includes/_pagination.md`](docs/source/includes/_pagination.md)

**What's covered:**
- Time-based and cursor-based pagination
- Parameters: `limit` (default 30, max 100), `since`, `before`
- RFC 3339 timestamp format or object IDs for `since`

---

### Object Expansion
📄 **File**: [`docs/source/includes/_object_expansion.md`](docs/source/includes/_object_expansion.md)

**What's covered:**
- Using `expand[]` parameter to inline related objects
- Avoids additional round-trips (e.g., expand merchant in transactions)

---

### Accounts
📄 **File**: [`docs/source/includes/_accounts.md`](docs/source/includes/_accounts.md)

**What's covered:**
- List accounts owned by authenticated user
- Account object properties: `id`, `description`, `created`
- Filtering by `account_type`: `uk_retail`, `uk_retail_joint`

**Key endpoints:**
- `GET /accounts` - List all accounts
- `GET /accounts?account_type=uk_retail` - Filter by type

---

### Balance
📄 **File**: [`docs/source/includes/_balance.md`](docs/source/includes/_balance.md)

**What's covered:**
- Read balance for a specific account
- Response fields:
  - `balance` - Available balance in minor units (pennies)
  - `total_balance` - Balance + all pots combined
  - `currency` - ISO 4217 code (e.g., GBP)
  - `spend_today` - Amount spent today (from ~4am)

**Key endpoints:**
- `GET /balance?account_id=` - Read account balance

---

### Pots
📄 **File**: [`docs/source/includes/_pots.md`](docs/source/includes/_pots.md)

**What's covered:**
- Pots = separate money containers within an account
- List pots for an account
- Deposit money into a pot
- Withdraw money from a pot
- Pot properties: `id`, `name`, `style`, `balance`, `currency`, `created`, `updated`, `deleted`
- `dedupe_id` required for deposits/withdrawals (idempotency key)
- Added security pots cannot be withdrawn via API

**Key endpoints:**
- `GET /pots?current_account_id=` - List pots
- `PUT /pots/{pot_id}/deposit` - Deposit into pot
- `PUT /pots/{pot_id}/withdraw` - Withdraw from pot

---

### Transactions
📄 **File**: [`docs/source/includes/_transactions.md`](docs/source/includes/_transactions.md)

**What's covered:**
- Transactions = movements of funds (negative = debit, positive = credit)
- Key properties:
  - `amount` - In minor units, negative for spending
  - `decline_reason` - Only on declined transactions (INSUFFICIENT_FUNDS, CARD_INACTIVE, etc.)
  - `is_load` - True for top-ups
  - `settled` - Timestamp when settled (24-48h after created), empty if pending
  - `category` - User-settable: general, eating_out, expenses, transport, cash, bills, entertainment, shopping, holidays, groceries
  - `merchant` - Can be expanded with `expand[]=merchant`
- Retrieve single transaction with expanded merchant info
- List transactions with pagination
- **SCA limitation**: After 5 minutes, can only sync last 90 days
- Annotate transactions with custom metadata

**Key endpoints:**
- `GET /transactions/{transaction_id}?expand[]=merchant` - Get single transaction
- `GET /transactions?account_id=&since=&before=` - List transactions
- `PATCH /transactions/{transaction_id}` - Annotate with metadata

---

### Feed Items
📄 **File**: [`docs/source/includes/_feed_items.md`](docs/source/includes/_feed_items.md)

**What's covered:**
- Create custom items in user's Monzo feed
- Feed items are discrete events at a point in time
- Currently only `basic` type supported
- Customizable: title, image_url, body, colors (background, title, body)
- Supports animated GIFs
- Optional URL to open on tap

**Key endpoints:**
- `POST /feed` - Create a feed item

---

### Attachments
📄 **File**: [`docs/source/includes/_attachments.md`](docs/source/includes/_attachments.md)

**What's covered:**
- Attach images (receipts, etc.) to transactions
- Two hosting options: Monzo-hosted or remote URL
- Upload flow: get temp URL → upload file → register against transaction
- Deregister to remove attachments

**Key endpoints:**
- `POST /attachment/upload` - Get upload URL (returns `file_url`, `upload_url`)
- `POST /attachment/register` - Attach to transaction
- `POST /attachment/deregister` - Remove attachment

---

### Receipts
📄 **File**: [`docs/source/includes/_receipts.md`](docs/source/includes/_receipts.md)

**What's covered:**
- Detailed line-item purchase data on transactions
- Used by Flux integration
- Receipt structure:
  - `items[]` - Products with description, quantity, unit, amount, tax, sub_items
  - `taxes[]` - VAT etc.
  - `payments[]` - How paid (card, cash, gift_card)
  - `merchant` - Store details
- `external_id` used as idempotency key (can update by resending)
- **Note**: Uses JSON body (not form-encoded)

**Key endpoints:**
- `PUT /transaction-receipts` - Create/update receipt (JSON body)
- `GET /transaction-receipts?external_id=` - Retrieve receipt
- `DELETE /transaction-receipts?external_id=` - Delete receipt

---

### Webhooks
📄 **File**: [`docs/source/includes/_webhooks.md`](docs/source/includes/_webhooks.md)

**What's covered:**
- Real-time push notifications of account events
- Register webhook URL per account
- Retry up to 5 times with exponential backoff
- `transaction.created` event - fires immediately on new transaction
- Event payload includes full transaction with merchant details

**Key endpoints:**
- `POST /webhooks` - Register webhook
- `GET /webhooks?account_id=` - List webhooks
- `DELETE /webhooks/{webhook_id}` - Delete webhook

---

### Errors
📄 **File**: [`docs/source/includes/_errors.md`](docs/source/includes/_errors.md)

**What's covered:**
- HTTP status codes and meanings:
  - `200` OK
  - `400` Bad Request - malformed/missing arguments
  - `401` Unauthorized - not authenticated
  - `403` Forbidden - insufficient permissions
  - `404` Not Found
  - `405` Method Not Allowed - wrong HTTP verb
  - `406` Not Acceptable - Accept header mismatch
  - `429` Too Many Requests - rate limited
  - `500` Internal Server Error
  - `504` Gateway Timeout
- Authentication error: `invalid_token` when token expired/invalid

---

## Part 2: Open Banking API

> ⚠️ **For licensed Third Party Providers only** (AISPs, PISPs, CBPIIs under PSD2)

📄 **Entry Point**: [`docs/source/open-banking/index.html.md`](docs/source/open-banking/index.html.md)

**Support**: Open Banking Service Desk or openbanking@monzo.com

---

### Account Information Services (AIS)
📄 **File**: [`docs/source/includes/_ais.md`](docs/source/includes/_ais.md)

**What's covered:**
- For licensed Account Information Service Providers
- Well-Known endpoints (sandbox + production)
- Base URLs: `https://openbanking.monzo.com/open-banking/v3.1/aisp`
- Dynamic Client Registration (v3.2 spec)
- OAuth 2 + OpenID Connect, `tls_client_auth` only
- **Accounts**: Personal, Joint, Business, Flex accounts
  - Business company types affect payment limits
- **Balances**: `InterimAvailable` (real-time), optional `includePots` parameter
- **Transactions**: RFC3339 timestamps, `Rejected` status, `order=desc` for reverse order
  - ProprietaryBankTransactionCode values listed
- **Parties**: `/party`, `/accounts/{id}/party`, `/accounts/{id}/parties`
- **Pots**: Extension to OB spec - List pots with type, balance, goal, lock status
- **Direct Debits**: Last 90 days after 5 min SCA
- **Scheduled Payments**: Access with valid SCA in last 90 days
- **Standing Orders**: Last 90 days or future first payment
- **Sandbox testing**: Auto-approve consents with `SupplementaryData`
- Sandbox user IDs provided

---

### Payment Initiation Services (PIS)
📄 **File**: [`docs/source/includes/_pis.md`](docs/source/includes/_pis.md)

**What's covered:**
- For licensed Payment Initiation Service Providers
- Base URL: `https://openbanking.monzo.com/open-banking/v3.1/pisp`
- All payments via Faster Payments
- **Domestic Payments**:
  - `LocalInstrument`: `UK.OBIE.FPS`
  - `UK.OBIE.SortCodeAccountNumber` only (no IBAN)
  - GBP only
  - Limits: Personal £10k, Joint £10k, Sole Trader £25k, Ltd £50k
- **Scheduled Payments**: RFC3339 format, early morning execution
- **Standing Orders**: Frequencies - EvryDay, IntrvlWkDay, IntrvlMnthDay
- **International Payments**: v3.1.11 spec
  - Multiple currencies: EUR, USD, AUD, CAD, CHF, etc.
  - Rails: SEPA, SWIFT, ABA, FEDWIRE, etc.
  - Currency-specific requirements table
- **Refund Accounts**: Set `ReadRefundAccount: Yes`
- **Rejected Payments**: Detailed rejection reasons in SupplementaryData
- Sandbox testing with `DesiredStatus`

---

### Variable Recurring Payments (VRP)
📄 **File**: [`docs/source/includes/_vrp.md`](docs/source/includes/_vrp.md)

**What's covered:**
- Multiple payments under single long-lived consent
- No per-payment authentication needed
- v3.1.10 of Open Banking VRP spec
- Base URL: Same as PISP
- `PeriodicAlignment`: `Consent` only
- `PeriodType`: Day, Week, Month, Year
- OAuth tokens: Refresh token 3-year expiry, access token 30 hours
- `UK.OBIE.SortCodeAccountNumber` only, GBP only
- Sandbox testing with `DesiredStatus` in `ControlParameters/SupplementaryData`

---

### Confirmation of Funds (CBPII)
📄 **File**: [`docs/source/includes/_cbpii.md`](docs/source/includes/_cbpii.md)

**What's covered:**
- For Card Based Payment Instrument Issuers
- Check customer has sufficient funds
- Base URL: `https://openbanking.monzo.com/open-banking/v3.1/cbpii`
- v3.1.10 spec, redirection flow
- `UK.OBIE.SortCodeAccountNumber` scheme only
- Consents are ongoing (no regular re-auth needed)

---

### Open Banking Errors
📄 **File**: [`docs/source/includes/_ob_errors.md`](docs/source/includes/_ob_errors.md)

**What's covered:**
- OB-compliant error structure (`OBErrorResponse1`, `OBError1`)
- Error codes: `UK.OBIE.*` and custom `UK.MONZO.*`
- Custom codes: `UK.MONZO.Generic`, `UK.MONZO.Forbidden`
- Status code mapping (400, 401, 403, 404, 406, 412, 429, 500, 504)
- **Rate Limiting**: 100 req/sec per TPP
- Platform-wide rate limiting during high load
- Legacy error opt-out header: `X-Open-Banking-Legacy-Errors`

---

### SCA-RTS (Strong Customer Authentication)
📄 **File**: [`docs/source/includes/_scarts.md`](docs/source/includes/_scarts.md)

**What's covered:**
- FCA rules change (PS21/19) from 2022-08-01
- AIS consents now long-lived (no 90-day expiry)
- TPPs can still set `ExpirationDateTime` if desired

---

### EU PSD2 API
📄 **File**: [`docs/source/includes/_eu.md`](docs/source/includes/_eu.md)

**What's covered:**
- Production EU API in Alpha (contact openbanking@monzo.com)
- Built on Open Banking spec with EU differences
- Currently AIS + CBPII only (no PIS yet)
- Different Well-Known endpoints and Base URLs
- DCR: Self-signed SSA allowed (`alg: none`)
- eIDAS QWAC/QSealC certificates required
- **EU Accounts**: Pots returned as separate accounts
- **EU Balances**: No `includePots` param (pots are accounts)
- **EU CBPII**: Uses `UK.OBIE.IBAN` scheme

---

## Development & Deployment

📄 **File**: [`docs/README.md`](docs/README.md)

- Docker recommended for local development
- Run locally: `docker run --rm -p 4567:4567 -v $(pwd)/source:/srv/slate/source slatedocs/slate serve`
- View at http://localhost:4567
- Build: `docker run ... slatedocs/slate build`
- Deploy: `./deploy.sh --push-only`

📄 **File**: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)

- Monzo staff: Merge to master and run `./deploy.sh`
- External: Submit PRs or raise issues

---

## File Reference Index

| File | Path | Primary Topics |
|------|------|----------------|
| Main API Index | `docs/source/index.html.md` | Introduction, API endpoint, overview |
| Open Banking Index | `docs/source/open-banking/index.html.md` | Open Banking introduction |
| Authentication | `docs/source/includes/_authentication.md` | OAuth 2.0, tokens, login, SCA |
| Accounts | `docs/source/includes/_accounts.md` | List accounts, account types |
| Balance | `docs/source/includes/_balance.md` | Balance, spend today, total balance |
| Transactions | `docs/source/includes/_transactions.md` | List/get/annotate transactions, categories |
| Pots | `docs/source/includes/_pots.md` | Savings pots, deposit, withdraw |
| Feed Items | `docs/source/includes/_feed_items.md` | Custom feed items, notifications |
| Attachments | `docs/source/includes/_attachments.md` | Image upload, attach to transactions |
| Receipts | `docs/source/includes/_receipts.md` | Line-item receipts, Flux integration |
| Webhooks | `docs/source/includes/_webhooks.md` | Real-time events, transaction.created |
| Errors | `docs/source/includes/_errors.md` | HTTP status codes, error handling |
| Pagination | `docs/source/includes/_pagination.md` | limit, since, before parameters |
| Object Expansion | `docs/source/includes/_object_expansion.md` | expand[] parameter |
| AIS (Open Banking) | `docs/source/includes/_ais.md` | Account info services, OB accounts/transactions |
| PIS (Open Banking) | `docs/source/includes/_pis.md` | Payment initiation, domestic/international |
| VRP (Open Banking) | `docs/source/includes/_vrp.md` | Variable recurring payments |
| CBPII (Open Banking) | `docs/source/includes/_cbpii.md` | Confirmation of funds |
| OB Errors | `docs/source/includes/_ob_errors.md` | Open Banking error format |
| SCA-RTS | `docs/source/includes/_scarts.md` | Strong Customer Auth rules |
| EU PSD2 | `docs/source/includes/_eu.md` | EU-specific API differences |
| Docs README | `docs/README.md` | Development setup, deployment |
| Contributing | `docs/CONTRIBUTING.md` | How to contribute |

