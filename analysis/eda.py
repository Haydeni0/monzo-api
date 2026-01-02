# %%
from monzo_api.src.database import MonzoDatabase

from plots import balance_overview, transaction_waterfall

db = MonzoDatabase()
print("Connected to database")
db.print_stats()

# %% Generate balance overview
fig = balance_overview(db)
fig.show()

# %% Transaction waterfall - Current account
fig_waterfall = transaction_waterfall(db, account_type="uk_retail", days=None)
fig_waterfall.show()

# %% Export to HTML
fig.write_html("analysis/balance_overview.html", include_plotlyjs=True)
print("Exported to analysis/balance_overview.html")

# %%
