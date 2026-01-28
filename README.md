# Monzo API

Python tools for exporting and analyzing your own Monzo data, by pulling it from the [Monzo API](https://docs.monzo.com/#introduction).

## Setup

```bash
uv sync
```

## Authentication

1. Create a client at [`https://developers.monzo.com`](https://developers.monzo.com)
   - Approve the login on the mobile app
   - Go to Clients, and create a new OAuth client
   - Set **Redirect URL** to: `http://localhost:8080/callback`
   - Set **Confidentiality** to confidential
2. Create `./.env.secrets` in project root with your client ID and secret:

    ```env
    MONZO_CLIENT_ID=oauth2client_xxx
    MONZO_CLIENT_SECRET=mnzconf.xxx
    ```

## Workflow

### Full History (default)

```bash
# Activate python virtual environment
source .venv/bin/activate
# Authenticate with Monzo and export bank account history
monzo auth --force    # fresh auth, approve in Monzo app
monzo export          # export full history + import to DuckDB (run within 5 mins)
```

> **Note:** Monzo limits transaction history to 90 days after 5 minutes of authentication.
> Use `--force` to get a fresh 5-minute SCA window, then run `export` immediately.

### Quick Export / Update

For ≤90 days or updating existing data, you can use an existing token:

```bash
monzo auth            # reuse token if valid, or refresh
monzo export -d 30    # recent transactions only
monzo export          # or full history (upserts into database)
```

### JSON Only (no database)

```bash
monzo export --no-ingest    # export to JSON only, skip database
```

## CLI Reference

```bash
monzo --help          # show all commands
monzo status          # show token, cache, and database status
monzo auth            # authenticate with Monzo
monzo auth --force    # force new authentication
monzo export          # export full history + import to database
monzo export -d 30    # export only last 30 days
monzo export --no-ingest  # JSON only, skip database
monzo db setup        # ensure database schema exists
monzo db stats        # show database row counts
monzo db accounts     # show accounts table
monzo db reset        # drop and recreate tables
monzo dashboard       # launch interactive Dash dashboard
monzo dashboard -p 8080   # custom port
```

## Data Storage

| File | Description |
|------|-------------|
| `.monzo_token.json` | OAuth access token (expires ~6 hours) |
| `.monzo_data.json` | Exported data cache (Pydantic models) |
| `.monzo.duckdb` | DuckDB database for analysis |

## Querying the Database

```python
from monzo_api.src.database import MonzoDatabase

db = MonzoDatabase()
with db as conn:
    # Top merchants by spend (returns Polars DataFrame)
    df = conn.sql("""
        SELECT m.emoji, m.name, COUNT(*) as txns, SUM(t.amount)/-100.0 as spent
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        WHERE t.amount < 0
        GROUP BY m.id, m.name, m.emoji
        ORDER BY spent DESC
        LIMIT 10
    """).pl()
```

## Dashboard

Launch the interactive dashboard:

```bash
monzo dashboard
```

Opens at `http://127.0.0.1:8050` with:
- **Balance Overview** - all accounts and pots over time
- **Transaction Waterfall** - daily balance changes per account
- **Spending Waterfall** - cumulative spending (configurable category exclusions)

## Documentation

See [`monzo_api_summary.md`](monzo_api_summary.md) for a complete guide to the Monzo API endpoints.
