"""Visualization library for Monzo data.

Functions that return Plotly Figures from the database.
"""

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from monzo_api.src.database import MonzoDatabase


def balance_overview(db: MonzoDatabase) -> go.Figure:
    """Create balance overview figure with account balances over time and current pots.

    Args:
        db: MonzoDatabase instance.

    Returns:
        Plotly Figure with two subplots:
        - Left: Balance over time for Current and Joint accounts
        - Right: Current pot balances as horizontal bar chart
    """
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

    # Create figure
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
            line={"color": "#00A4DB"},
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
                line={"color": "#E54D42"},
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
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"t": 80, "l": 60, "r": 40, "b": 60},
        title={"text": "Monzo Balance Overview", "x": 0.5, "font": {"size": 20}},
    )
    fig.update_xaxes(title_text="", row=1, col=2)

    return fig


def transaction_waterfall(
    db: MonzoDatabase,
    account_type: str = "uk_retail",
    days: int | None = 30,
) -> go.Figure:
    """Create waterfall chart showing balance changes from transactions.

    Args:
        db: MonzoDatabase instance.
        account_type: Account type from the `accounts` table (e.g., query db for options).
        days: Number of days to show. None = all history.

    Returns:
        Plotly Waterfall Figure showing how balance changes over time.

    Raises:
        ValueError: If account_type is not valid.
    """
    valid_types = db.account_types
    if account_type not in valid_types:
        raise ValueError(f"Invalid account_type '{account_type}'. Valid: {valid_types}")

    date_filter = f"AND t.created >= CURRENT_DATE - INTERVAL '{days} days'" if days else ""

    with db as conn:
        # Get daily net change with transaction details
        df = conn.sql(f"""
            SELECT 
                t.created::DATE as date,
                SUM(t.amount) / 100.0 as net_change,
                STRING_AGG(
                    COALESCE(t.description, 'Unknown') || ': £' || 
                    PRINTF('%.2f', t.amount / 100.0),
                    '<br>'
                    ORDER BY t.amount DESC
                ) as transactions
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            WHERE a.type = '{account_type}'
              AND t.decline_reason IS NULL
              {date_filter}
            GROUP BY t.created::DATE
            ORDER BY t.created::DATE
        """).pl()  # noqa: S608

    if df.is_empty():
        fig = go.Figure()
        fig.add_annotation(text="No data", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig

    # Build waterfall data
    dates = df["date"].to_list()
    values = df["net_change"].to_list()
    transactions = df["transactions"].to_list()
    measures = ["relative"] * len(values)

    # Format dates for display - use shorter format for large datasets
    if len(dates) > 60:
        x_labels = [d.strftime("%Y-%m-%d") for d in dates]
    else:
        x_labels = [d.strftime("%d %b") for d in dates]

    # Disable connector lines for large datasets (they become visual noise)
    connector_config = (
        {"visible": False} if len(values) > 60 else {"line": {"color": "#ccc", "width": 1}}
    )

    # Build custom hover text with transaction details
    hover_texts = []
    for date, val, txns in zip(x_labels, values, transactions):
        # Truncate if too many transactions
        txn_lines = txns.split("<br>") if txns else []
        if len(txn_lines) > 8:
            txns = "<br>".join(txn_lines[:8]) + f"<br>... +{len(txn_lines) - 8} more"
        hover_texts.append(f"<b>{date}</b><br>Net: £{val:+,.2f}<br><br>{txns}")

    fig = go.Figure(
        go.Waterfall(
            x=x_labels,
            y=values,
            measure=measures,
            increasing={"marker": {"color": "#26A69A"}},
            decreasing={"marker": {"color": "#EF5350"}},
            connector=connector_config,
            hovertext=hover_texts,
            hoverinfo="text",
        )
    )

    # Account name for title
    account_names = {
        "uk_retail": "Current Account",
        "uk_retail_joint": "Joint Account",
        "uk_monzo_flex": "Monzo Flex",
    }
    title = account_names.get(account_type, account_type)

    fig.update_layout(
        template="plotly_white",
        height=500,
        width=1200,
        hovermode="x",
        margin={"t": 80, "l": 80, "r": 40, "b": 80},
        title={"text": f"{title} - Balance Waterfall", "x": 0.5, "font": {"size": 18}},
        yaxis_title="Daily Net Change (£)",
        xaxis_tickangle=-45,
    )

    return fig
