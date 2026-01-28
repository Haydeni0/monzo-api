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

## Get Access Token

```bash
python src/get_token.py
```

This will:
1. Open browser for Monzo login
2. Capture the OAuth callback
3. Exchange for access token
4. Save to `.monzo_token.json`

**Important:** After running, open the Monzo app and approve the access request.

Token expires after ~6 hours. Run the script again to auto-refresh (confidential clients) or re-authenticate.

## Documentation

See [`monzo_api_summary.md`](monzo_api_summary.md) for a complete guide to the Monzo API endpoints.

