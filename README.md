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
2. Create `.env.secrets` in project root:

```env
MONZO_CLIENT_ID=oauth2client_xxx
MONZO_CLIENT_SECRET=mnzconf.xxx
```

## Workflow

### Quick Start (last 89 days)

```bash
monzo auth            # authenticate, approve in Monzo app
monzo export          # export to JSON (default 89 days)
monzo ingest          # import JSON into DuckDB
```

### Full History

Monzo limits transaction access to 89 days after 5 minutes of authentication.
To get your full history, you must export immediately after authenticating:

```bash
monzo auth --force    # force new authentication
# Approve in Monzo app immediately!
monzo export -d 3650  # export 10 years (within 5 mins of approval)
monzo ingest          # import into database
```

### Updating Data

```bash
monzo export          # fetch latest 89 days
monzo ingest          # upserts into database (existing data preserved)
```

## CLI Reference

```bash
monzo --help          # show all commands
monzo status          # show token, cache, and database status
monzo auth            # authenticate with Monzo
monzo auth --force    # force new authentication
monzo export          # export to JSON cache (default 89 days)
monzo export -d 365   # export specific number of days
monzo ingest          # import JSON cache into DuckDB
monzo db              # setup DuckDB database
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

## Documentation

See [`monzo_api_summary.md`](monzo_api_summary.md) for a complete guide to the Monzo API endpoints.
