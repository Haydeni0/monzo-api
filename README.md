# Monzo API

Python tools for exporting and analyzing your Monzo data.

## Setup

```bash
uv sync
```

## Configuration

1. Create a client at [`https://developers.monzo.com`](https://developers.monzo.com)
   - Approve the login on the mobile app
   - Go to Clients, and create a new OAuth client
   - Set **Redirect URL** to: `http://localhost:8080/callback`
   - Set **Confidentiality** to confidential (so reauthentication is easy)
2. Create `.env.secrets` in project root:

```env
MONZO_CLIENT_ID=oauth2client_xxx
MONZO_CLIENT_SECRET=mnzconf.xxx
```

## Workflow

### Full History (default)

```bash
monzo auth --force    # fresh auth, approve in Monzo app
monzo export          # export full history + import to DuckDB (run within 5 mins)
```

> **Note:** Monzo limits transaction history to 90 days after 5 minutes of authentication.
> Use `--force` to get a fresh SCA window, then run `export` immediately.

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
monzo db              # ensure database schema exists
monzo db --stats      # show database row counts
monzo db --reset      # drop and recreate tables
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
    # Top merchants by spend
    rows = conn.execute("""
        SELECT m.emoji, m.name, COUNT(*) as txns, SUM(t.amount)/-100.0 as spent
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        WHERE t.amount < 0
        GROUP BY m.id, m.name, m.emoji
        ORDER BY spent DESC
        LIMIT 10
    """).fetchall()
```

## Analysis

Run `analysis/eda.py` (IPython notebook-style) to generate:
- `analysis/balance_overview.html` - interactive Plotly chart
- `analysis/daily_balances.csv` - daily balance data

## Documentation

See [`monzo_api_summary.md`](monzo_api_summary.md) for a complete guide to the Monzo API endpoints.
