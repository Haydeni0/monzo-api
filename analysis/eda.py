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
    # Pivot accounts to columns with daily transaction info
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

    # Get daily transaction summaries for hover info (with pot names resolved)
    tx_summary = conn.sql("""
        SELECT 
            t.created::DATE as date,
            CASE a.type 
                WHEN 'uk_retail' THEN 'Current'
                WHEN 'uk_retail_joint' THEN 'Joint'
            END as account,
            COUNT(*) as tx_count,
            SUM(t.amount) / 100.0 as net_change,
            FIRST(
                COALESCE(p.name, t.description)
                ORDER BY ABS(t.amount) DESC
            ) as biggest_tx
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        LEFT JOIN pots p ON t.description = p.id
        WHERE a.type IN ('uk_retail', 'uk_retail_joint')
          AND t.decline_reason IS NULL
        GROUP BY t.created::DATE, a.type
    """).pl()

    # Get current pot balances with account type
    pots = conn.sql("""
        SELECT 
            p.name, 
            p.balance / 100.0 as balance,
            CASE a.type 
                WHEN 'uk_retail' THEN 'Current'
                WHEN 'uk_retail_joint' THEN 'Joint'
            END as account
        FROM pots p
        JOIN accounts a ON p.account_id = a.id
        WHERE p.deleted = false
        ORDER BY a.type, p.balance DESC
    """).pl()

# Fill gaps: upsample to daily and forward-fill balances
df = df.upsample("date", every="1d").select(pl.all().forward_fill())

# Join transaction summaries for hover
tx_current = tx_summary.filter(pl.col("account") == "Current").select(
    "date", "tx_count", "net_change", "biggest_tx"
)
tx_joint = tx_summary.filter(pl.col("account") == "Joint").select(
    "date",
    pl.col("tx_count").alias("tx_count_joint"),
    pl.col("net_change").alias("net_change_joint"),
    pl.col("biggest_tx").alias("biggest_tx_joint"),
)
df = df.join(tx_current, on="date", how="left").join(tx_joint, on="date", how="left")

df

# %% Plot all balances
fig = make_subplots(
    rows=1,
    cols=2,
    column_widths=[0.7, 0.3],
    specs=[[{"type": "xy"}, {"type": "xy"}]],
    subplot_titles=["Balance Over Time", "Current Pots"],
)

# Build hover text for Current account
current_hover = [
    f"£{bal:,.2f}<br>{int(cnt) if cnt else 0} txns ({net:+,.2f})<br>{tx[:30] if tx else ''}"
    for bal, cnt, net, tx in zip(
        df["Current"].fill_null(0),
        df["tx_count"].fill_null(0),
        df["net_change"].fill_null(0),
        df["biggest_tx"].fill_null(""),
    )
]

fig.add_trace(
    go.Scatter(
        x=df["date"],
        y=df["Current"],
        name="Current",
        fill="tozeroy",
        line=dict(color="#00A4DB"),
        hovertemplate="%{customdata}<extra>Current</extra>",
        customdata=current_hover,
    ),
    row=1,
    col=1,
)

if "Joint" in df.columns:
    joint_hover = [
        f"£{bal:,.2f}<br>{int(cnt) if cnt else 0} txns ({net:+,.2f})<br>{tx[:30] if tx else ''}"
        for bal, cnt, net, tx in zip(
            df["Joint"].fill_null(0),
            df["tx_count_joint"].fill_null(0),
            df["net_change_joint"].fill_null(0),
            df["biggest_tx_joint"].fill_null(""),
        )
    ]
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["Joint"],
            name="Joint",
            fill="tozeroy",
            line=dict(color="#E54D42"),
            hovertemplate="%{customdata}<extra>Joint</extra>",
            customdata=joint_hover,
        ),
        row=1,
        col=1,
    )

# Pots bar chart - color by account
pot_colors = ["#00A4DB" if acc == "Current" else "#E54D42" for acc in pots["account"]]
fig.add_trace(
    go.Bar(
        y=pots["name"],
        x=pots["balance"],
        orientation="h",
        marker_color=pot_colors,
        showlegend=False,
    ),
    row=1,
    col=2,
)

fig.update_layout(
    template="plotly_white",
    height=600,
    width=1400,
    hovermode="x",
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
