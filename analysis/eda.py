# %%
import plotly.express as px

from monzo_api.src.database import MonzoDatabase

db = MonzoDatabase()
print("Connected to database")
db.print_stats()

# %% Get daily balances for accounts + current pot balances
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

with db as conn:
    # Pivot accounts to columns
    df = conn.sql("""
        PIVOT (
            SELECT 
                d.date,
                CASE a.type 
                    WHEN 'uk_retail' THEN 'Current'
                    WHEN 'uk_retail_joint' THEN 'Joint'
                END as account,
                d.eod_balance / 100.0 as balance
            FROM daily_balances d
            JOIN accounts a ON d.account_id = a.id
            WHERE a.type IN ('uk_retail', 'uk_retail_joint')
        )
        ON account USING SUM(balance)
        ORDER BY date
    """).pl()

    # Get current pot balances
    pots = conn.sql("""
        SELECT name, balance / 100.0 as balance
        FROM pots WHERE deleted = false
        ORDER BY balance DESC
    """).pl()

# Fill gaps: upsample to daily and forward-fill balances
df = df.upsample("date", every="1d").select(pl.all().forward_fill())

df

# %% Plot all balances
fig = make_subplots(
    rows=1,
    cols=2,
    column_widths=[0.7, 0.3],
    specs=[[{"type": "xy"}, {"type": "xy"}]],
    subplot_titles=["Balance Over Time", "Current Pots"],
)

# Account balances over time
fig.add_trace(
    go.Scatter(
        x=df["date"], y=df["Current"], name="Current", fill="tozeroy", line=dict(color="#00A4DB")
    ),
    row=1,
    col=1,
)

if "Joint" in df.columns:
    fig.add_trace(
        go.Scatter(
            x=df["date"], y=df["Joint"], name="Joint", fill="tozeroy", line=dict(color="#E54D42")
        ),
        row=1,
        col=1,
    )

# Pots bar chart
fig.add_trace(
    go.Bar(
        y=pots["name"], x=pots["balance"], orientation="h", marker_color="#00A4DB", showlegend=False
    ),
    row=1,
    col=2,
)

fig.update_layout(
    template="plotly_white",
    height=600,
    width=1400,
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(t=80, l=60, r=40, b=60),
    title=dict(text="Monzo Balance Overview", x=0.5, font=dict(size=20)),
)
fig.update_xaxes(title_text="", row=1, col=2)
fig.show()

# %% Export to HTML and CSV
fig.write_html("analysis/balance_overview.html", include_plotlyjs=True)
print("Exported to analysis/balance_overview.html")

df.write_csv("analysis/daily_balances.csv")
print("Exported to analysis/daily_balances.csv")

# %%
