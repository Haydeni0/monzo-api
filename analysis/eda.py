# %%
from monzo_api.src.database import MonzoDatabase

from plots import balance_overview

db = MonzoDatabase()
print("Connected to database")
db.print_stats()

# %% Generate balance overview
fig = balance_overview(db)
fig.show()

# %% Export to HTML
fig.write_html("analysis/balance_overview.html", include_plotlyjs=True)
print("Exported to analysis/balance_overview.html")

# %%
