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

# %% Transaction waterfall - Joint account
fig_waterfall_joint = transaction_waterfall(db, account_type="uk_retail_joint", days=None)
fig_waterfall_joint.show()

# %% Export to HTML and PNG
fig.write_html("analysis/balance_overview.html", include_plotlyjs=True)
fig.write_image("analysis/balance_overview.png", scale=2)
fig_waterfall.write_html("analysis/waterfall_current.html", include_plotlyjs=True)
fig_waterfall.write_image("analysis/waterfall_current.png", scale=2)
fig_waterfall_joint.write_html("analysis/waterfall_joint.html", include_plotlyjs=True)
fig_waterfall_joint.write_image("analysis/waterfall_joint.png", scale=2)
print("Exported to analysis/")

# %%
