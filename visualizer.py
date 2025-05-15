import pandas as pd

# Load the existing cleaned binary panel
bin_df = pd.read_csv("data/ats_processed/ats_features_binary.csv")

# Create the labeled cross-tab
crosstab = pd.crosstab(bin_df["offers_hosted_pool"], bin_df["supports_iois"])
crosstab.index.name = "Hosted Pool"
crosstab.columns.name = "IOI Support"

# Save it (optional)
crosstab.to_csv("tables/tab4_cross_feature_contingency.csv")

# Preview
print(crosstab)
