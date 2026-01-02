"""Monzo Dashboard - Interactive visualization of your Monzo data."""

from dash import Dash, dcc, html, callback, Input, Output

from monzo_api.src.database import MonzoDatabase
from plots import balance_overview, spending_waterfall, transaction_waterfall

# Initialize database
db = MonzoDatabase()

# Get available account types
account_types = db.account_types

# Get all categories from database
with db as conn:
    categories = [
        row[0]
        for row in conn.sql("SELECT DISTINCT category FROM transactions ORDER BY category").fetchall()
    ]

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
                dcc.Graph(id="balance-overview", figure=balance_overview(db)),
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
                    value=account_types[0] if account_types else None,
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
                        html.Label("Exclude categories:"),
                        dcc.Dropdown(
                            id="exclude-categories",
                            options=[{"label": c, "value": c} for c in categories],
                            value=DEFAULT_EXCLUDE,
                            multi=True,
                            style={"width": "500px"},
                        ),
                    ],
                    style={"marginBottom": "15px"},
                ),
                dcc.Graph(id="spending-waterfall"),
            ]
        ),
    ],
    style={"maxWidth": "1400px", "margin": "0 auto", "padding": "20px"},
)


@callback(
    Output("transaction-waterfall", "figure"),
    Input("account-dropdown", "value"),
    Input("days-input", "value"),
)
def update_transaction_waterfall(account_type: str | None, days: int | str | None):
    """Update transaction waterfall based on account selection."""
    if not account_type:
        return {}
    # Handle empty string from input
    days_int = int(days) if days else None
    return transaction_waterfall(db, account_type=account_type, days=days_int)


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
    if not account_type:
        return {}
    # Handle empty string from input
    days_int = int(days) if days else None
    exclude_list = exclude if exclude else []
    return spending_waterfall(
        db, account_type=account_type, days=days_int, exclude_categories=exclude_list
    )


if __name__ == "__main__":
    import os

    port = int(os.environ.get("DASH_PORT", 8050))
    print(f"Starting Monzo Dashboard at http://127.0.0.1:{port}")
    app.run(debug=True, port=port)

