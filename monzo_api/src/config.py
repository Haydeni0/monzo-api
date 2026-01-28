"""Configuration and paths for Monzo API tools."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Data files
TOKEN_FILE = PROJECT_ROOT / ".monzo_token.json"
CACHE_FILE = PROJECT_ROOT / ".monzo_data.json"
DB_FILE = PROJECT_ROOT / ".monzo.duckdb"
ENV_SECRETS_FILE = PROJECT_ROOT / ".env.secrets"

# API URLs
API_URL = "https://api.monzo.com"
AUTH_URL = "https://auth.monzo.com"
