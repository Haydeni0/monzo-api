"""Monzo Dashboard - Interactive visualization of your Monzo data."""

import logging
from pathlib import Path

from dash import Dash, dcc, html, callback, Input, Output

from monzo_api.src.database import MonzoDatabase
from plots import balance_overview, pot_history, spending_waterfall, transaction_waterfall

# Setup logging (reset log file each run)
LOG_FILE = Path(__file__).parent / "dashboard.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w"),  # 'w' overwrites on each start
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Get initial data (these don't change during runtime)
_init_db = MonzoDatabase()
account_types = _init_db.account_types
with _init_db as conn:
    categories = [
        row[0]
        for row in conn.sql(
            "SELECT DISTINCT category FROM transactions ORDER BY category"
        ).fetchall()
    ]
del _init_db  # Close init connection


def get_db() -> MonzoDatabase:
    """Get a fresh database connection for each callback."""
    return MonzoDatabase()


# Default exclusions
DEFAULT_EXCLUDE = ["savings", "transfers"]

# Create Dash app
app = Dash(__name__)

app.layout = html.Div(
    [
        html.H1("Monzo Dashboard", style={"textAlign": "center", "marginBottom": "30px"}),
        # Balance Overview (always shown)
        html.Div(
            [
                html.H2("Balance Overview"),
                dcc.Graph(id="balance-overview", figure=balance_overview(get_db())),
            ]
        ),
        html.Hr(),
        # Account selector for waterfalls
        html.Div(
            [
                html.Label("Select Account:"),
                dcc.Dropdown(
                    id="account-dropdown",
                    options=[{"label": t, "value": t} for t in account_types],
                    value="uk_retail"
                    if "uk_retail" in account_types
                    else (account_types[0] if account_types else None),
                    style={"width": "300px"},
                ),
                html.Label("Days of history:", style={"marginLeft": "20px"}),
                dcc.Input(
                    id="days-input",
                    type="number",
                    placeholder="Leave empty for all",
                    style={"width": "150px", "marginLeft": "10px"},
                ),
            ],
            style={"display": "flex", "alignItems": "center", "marginBottom": "20px"},
        ),
        # Transaction Waterfall
        html.Div(
            [
                html.H2("Transaction Waterfall"),
                dcc.Graph(id="transaction-waterfall"),
            ]
        ),
        html.Hr(),
        # Spending Waterfall
        html.Div(
            [
                html.H2("Spending Waterfall"),
                html.Div(
                    [
                        html.Label("Exclude categories:", style={"marginBottom": "5px"}),
                        html.Div(
                            [
                                html.Button(
                                    "Exclude All",
                                    id="exclude-all-btn",
                                    style={"marginRight": "5px"},
                                ),
                                html.Button(
                                    "Reset",
                                    id="reset-exclude-btn",
                                ),
                            ],
                            style={"marginBottom": "10px"},
                        ),
                        dcc.Dropdown(
                            id="exclude-categories",
                            options=[{"label": c, "value": c} for c in categories],
                            value=DEFAULT_EXCLUDE,
                            multi=True,
                            style={"width": "100%"},
                        ),
                    ],
                    style={"marginBottom": "15px", "maxWidth": "800px"},
                ),
                dcc.Graph(id="spending-waterfall"),
            ]
        ),
        html.Hr(),
        # Pot History
        html.Div(
            [
                html.H2("Pot History"),
                dcc.Graph(id="pot-history", figure=pot_history(get_db())),
            ]
        ),
    ],
    style={"maxWidth": "1400px", "margin": "0 auto", "padding": "20px"},
)


@callback(
    Output("exclude-categories", "value"),
    Input("exclude-all-btn", "n_clicks"),
    Input("reset-exclude-btn", "n_clicks"),
    prevent_initial_call=True,
)
def update_exclude_dropdown(exclude_all_clicks: int | None, reset_clicks: int | None):
    """Update exclude dropdown based on button clicks."""
    from dash import ctx

    logger.debug(f"Exclude dropdown: triggered_id={ctx.triggered_id}")
    if ctx.triggered_id == "exclude-all-btn":
        return categories
    elif ctx.triggered_id == "reset-exclude-btn":
        return DEFAULT_EXCLUDE
    return DEFAULT_EXCLUDE


@callback(
    Output("transaction-waterfall", "figure"),
    Input("account-dropdown", "value"),
    Input("days-input", "value"),
)
def update_transaction_waterfall(account_type: str | None, days: int | str | None):
    """Update transaction waterfall based on account selection."""
    logger.debug(f"Transaction waterfall: account={account_type}, days={days}")
    try:
        if not account_type:
            return {}
        days_int = int(days) if days else None
        return transaction_waterfall(get_db(), account_type=account_type, days=days_int)
    except Exception as e:
        logger.exception(f"Error in transaction_waterfall: {e}")
        raise


@callback(
    Output("spending-waterfall", "figure"),
    Input("account-dropdown", "value"),
    Input("days-input", "value"),
    Input("exclude-categories", "value"),
)
def update_spending_waterfall(
    account_type: str | None, days: int | str | None, exclude: list[str] | None
):
    """Update spending waterfall based on account selection."""
    logger.debug(f"Spending waterfall: account={account_type}, days={days}, exclude={exclude}")
    try:
        if not account_type:
            return {}
        days_int = int(days) if days else None
        exclude_list = exclude if exclude else []
        return spending_waterfall(
            get_db(), account_type=account_type, days=days_int, exclude_categories=exclude_list
        )
    except Exception as e:
        logger.exception(f"Error in spending_waterfall: {e}")
        raise


if __name__ == "__main__":
    import os

    port = int(os.environ.get("DASH_PORT", 8050))
    logger.info(f"Starting Monzo Dashboard at http://127.0.0.1:{port}")
    logger.info(f"Log file: {LOG_FILE}")
    app.run(debug=True, port=port)
