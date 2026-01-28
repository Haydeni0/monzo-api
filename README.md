# Monzo API

Python tools for interacting with the Monzo API.

## Setup

```bash
uv sync
```

## Configuration

1. Create a client at [`https://developers.monzo.com`](https://developers.monzo.com)
  - Approve the login on the mobile app
  - Go to Clients, and create a new oauth client
  - Set **Redirect URL** (in the client setup) to: [`http://localhost:8080/callback`](https://developers.monzo.com)
2. Create `.env.secrets` in project root:

```env
MONZO_CLIENT_ID=oauth2client_xxx
MONZO_CLIENT_SECRET=mnzconf.xxx
```

## CLI

After setup, the `monzo` command is available:

```bash
monzo --help          # Show all commands
monzo status          # Show token, cache, and database status
monzo auth            # Authenticate with Monzo
monzo auth --force    # Force new authentication
monzo export          # Export data to JSON cache
monzo export --full   # Fresh auth + export (for full history)
monzo db              # Setup DuckDB database
monzo db --stats      # Show database row counts
monzo db --reset      # Drop and recreate tables
```

## Authentication

```bash
monzo auth
```

This will:
1. Open browser for Monzo login
2. Capture the OAuth callback
3. Exchange for access token
4. Save to `.monzo_token.json`

**Important:** After running, open the Monzo app and approve the access request.

Token expires after ~6 hours. Run `monzo auth` again to refresh.

### Full Transaction History

Monzo limits transaction history to 90 days after 5 minutes of authentication. To get your full history:

```bash
monzo export --full
```

This forces fresh authentication and immediately exports. Run within 5 minutes of approving in the app.

## Documentation

See [`monzo_api_summary.md`](monzo_api_summary.md) for a complete guide to the Monzo API endpoints.

