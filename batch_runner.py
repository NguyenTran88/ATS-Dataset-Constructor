#!/usr/bin/env python3
"""
run_batch.py  – end-to-end pipeline for the dark-pool paper
───────────────────────────────────────────────────────────
Outputs
  • data/ats_processed/ats_features_binary.csv
  • data/ats_processed/ats_features_longtext.csv
  • fig/fig2_stacked_area.png
  • fig/fig3_volume_vs_features.png
  • fig/fig4_feature_heatmap.png
  • tables/tab1_feature_summary.csv
  • tables/tab2_corr_matrix.csv
  • tables/tab3_missing_years.csv
  • tables/tab4_cross_feature_contingency.csv
"""

# ── std lib ───────────────────────────────────────────────
import json, pathlib, sys, warnings
from collections import Counter

# ── 3rd-party ─────────────────────────────────────────────
import numpy  as np
import pandas as pd
import matplotlib.pyplot as plt
from tqdm import tqdm

# ── local parser ──────────────────────────────────────────
from seminar_parse import extract_features_from_html   # <- no side effects

RAW_DIR = pathlib.Path("data/ATS_filings_data/data_raw/ats_filings")
CLEAN_DIR   = pathlib.Path("data/ats_processed");   CLEAN_DIR.mkdir(exist_ok=True)
FIG_DIR     = pathlib.Path("fig");          FIG_DIR.mkdir(exist_ok=True)
TAB_DIR     = pathlib.Path("tables");       TAB_DIR.mkdir(exist_ok=True)

WEEKLY_VOL  = pathlib.Path("data/volume data/data_clean/weekly_volume.csv")
ANNUAL_VOL  = pathlib.Path("data/volume data/data_clean/annual_volume.csv")

# ---------------------------------------------------------
# 1.  FEATURE EXTRACTION
# ---------------------------------------------------------
BIN_KEYS = [
    "offers_hosted_pool", "subscriber_opt_out_capability",
    "internal_trading_allowed", "affiliate_access_to_ats",
    "routing_to_affiliate_venue",
    "segmentation_supported", "segmentation_customer_flag",
    "segmentation_disclosed", "segmentation_uniform",
    "market_data_feed_available", "display_to_persons",
    "display_procedures_uniform", "supports_iois",
    "custom_order_types", "ecn_status"
]
TXT_KEYS = [
    "trading_access_summary", "data_segmentation_practices",
    "custom_order_types_list", "unrecognised_custom_orders"
]

def yni(v):                               # Yes/No/Unclear → 1/0/NaN
    if v is None or v.startswith("Unclear"):
        return np.nan
    return 1 if v.startswith("Yes") else 0

bin_rows, long_rows = [], []

for f in tqdm(sorted(RAW_DIR.glob("*.htm*")) + sorted(RAW_DIR.glob("*.xml")),
              desc="🔍 Parsing filings"):
    try:
        stem        = f.stem          # e.g.  SGMT_2025
        ats_id, yr  = stem.split("_")
        yr          = int(yr)
        feats       = extract_features_from_html(f.read_text(),
                                                 ats_id=ats_id, year=yr)

        # ---- numeric row ----
        nr          = {"ats_id": ats_id, "year": yr}
        for k in BIN_KEYS: nr[k] = yni(feats.get(k))
        # compound complexity score 0-6
        nr["order_type_complexity"] = sum(yni(feats.get(k)) == 1
              for k in ("supports_midpoint_orders",
                        "supports_market_peg_orders",
                        "supports_primary_peg_orders",
                        "supports_vwap_orders",
                        "supports_post_only_orders",
                        "supports_conditional_orders"))
        bin_rows.append(nr)

        # ---- long-text row ----
        lr          = nr.copy()
        for k in TXT_KEYS: lr[k] = feats.get(k, "")
        long_rows.append(lr)

    except Exception as e:
        warnings.warn(f"{f.name}: {e}")

bin_df  = pd.DataFrame(bin_rows)
long_df = pd.DataFrame(long_rows)
bin_df.to_csv(CLEAN_DIR / "ats_features_binary.csv",  index=False)
long_df.to_csv(CLEAN_DIR / "ats_features_longtext.csv", index=False)

# ---------------------------------------------------------
# 2.  FIGURE 2  – Stacked weekly volume (top-15)
# ---------------------------------------------------------
wk      = pd.read_csv(WEEKLY_VOL, parse_dates=["weekStartDate"])
top15   = (wk.groupby("MPID")["shares"].sum()
              .sort_values(ascending=False).head(15).index.tolist())
wk_top  = wk[wk["MPID"].isin(top15)]
# --- Pivot weekly data: rows = weeks, cols = MPIDs ---------------------
pivot = (wk_top.pivot_table(index="weekStartDate", columns="MPID", values="shares", fill_value=0)
               .sort_index())

# Optional: sort MPIDs by total volume for better layering (fat pools at bottom)
pivot = pivot[pivot.sum().sort_values(ascending=False).index]

x = pd.to_datetime(pivot.index)
y = pivot.T.values  # shape: (n_mpid, n_weeks)

fig2, ax = plt.subplots(figsize=(10, 5))
ax.stackplot(x, y, labels=pivot.columns)
ax.set_title("Fig 2. Weekly share volume – top 15 ATSs (stacked)")
ax.set_ylabel("Shares")
ax.legend(loc="upper left", ncol=3, fontsize=8)
ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))  # nice axis scale
fig2.tight_layout()
fig2.savefig(FIG_DIR / "fig2_stacked_area.png", dpi=300, bbox_inches="tight")
plt.close(fig2)


# ---------------------------------------------------------
# 3.  FIGURE 3  – Annual volume vs. key binary feature
#                 (latest year only)
# ---------------------------------------------------------
ann = pd.read_csv(ANNUAL_VOL, delimiter=",", engine="python")
latest_year = ann["year"].max()
ann_latest  = ann[ann["year"] == latest_year]

merged = (ann_latest.merge(bin_df[bin_df["year"] == latest_year],
                           left_on="MPID", right_on="ats_id"))
FEATURE = "offers_hosted_pool"
merged.sort_values(FEATURE, ascending=False, inplace=True)

x_all = np.arange(len(merged))  # index for each ATS
w     = 0.4

fig3, ax = plt.subplots(figsize=(8, 4))

# --- Hosted Pool = 1 group ---
mask_yes = merged[FEATURE] == 1
x_yes    = x_all[mask_yes]
h_yes    = merged.loc[mask_yes, "annual_shares"]
ax.bar(x_yes - w/2, h_yes, width=w, label="Hosted pool = 1")

# --- Hosted Pool = 0 group ---
mask_no = ~mask_yes
x_no    = x_all[mask_no]
h_no    = merged.loc[mask_no, "annual_shares"]
ax.bar(x_no + w/2, h_no, width=w, label="Hosted pool = 0")

# --- Axis / Legend ---
ax.set_xticks(x_all)
ax.set_xticklabels(merged["MPID"], rotation=45, ha="right")
ax.set_title(f"Fig 3. {latest_year} annual volume by hosted-pool flag")
ax.set_ylabel("Shares")
ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
ax.legend()
fig3.tight_layout()
fig3.savefig(FIG_DIR / "fig3_volume_vs_features.png", dpi=300, bbox_inches="tight")
plt.close(fig3)



# ---------------------------------------------------------
# 4.  FIGURE 4  – Heat-map of feature adoption (balanced panel)
# ---------------------------------------------------------
panel = (bin_df.set_index(["ats_id","year"])
                .sort_index()
                .drop(columns=["order_type_complexity"]) )
# reshape to ATS × feature with many NaN → use imshow
heat  = panel.reset_index().melt(id_vars=["ats_id","year"],
                                 var_name="feature", value_name="flag")

# build 2-D matrix :  feature rows × years (sum over ATS)
mat = (heat.groupby(["feature","year"])["flag"]
            .mean()                # share of ATSs = 1
            .unstack(level=1)
            .sort_index())

fig4, ax = plt.subplots(figsize=(6,6))
im = ax.imshow(mat.values, aspect="auto")
ax.set_xticks(range(len(mat.columns)), labels=mat.columns, rotation=45)
ax.set_yticks(range(len(mat.index)),   labels=mat.index)
ax.set_title("Fig 4. Share of ATSs with feature = 1")
fig4.colorbar(im, ax=ax, fraction=.046)
fig4.savefig(FIG_DIR / "fig4_feature_heatmap.png", dpi=300,
             bbox_inches="tight"); plt.close(fig4)

# ---------------------------------------------------------
# 5.  TABLE 1 – Summary statistics of binary features
# ---------------------------------------------------------
tab1 = bin_df[BIN_KEYS].describe().T[["mean","std","min","max","count"]]
tab1.rename(columns={"mean":"share_yes"}, inplace=True)
tab1.to_csv(TAB_DIR / "tab1_feature_summary.csv")

# ---------------------------------------------------------
# 6.  TABLE 2 – Spearman correlation matrix
#               (annual volume vs. binary features)
# ---------------------------------------------------------
corr_src = (ann.merge(bin_df, left_on=["MPID","year"],
                      right_on=["ats_id","year"])
               .drop(columns=["ats_id"]))
num_cols = ["annual_shares"] + BIN_KEYS + ["order_type_complexity"]
tab2     = corr_src[num_cols].corr(method="spearman").round(3)
tab2.to_csv(TAB_DIR / "tab2_corr_matrix.csv")

# ---------------------------------------------------------
# 7.  TABLE 3 – Missing-year coverage per ATS
# ---------------------------------------------------------
years_all = range(bin_df["year"].min(), bin_df["year"].max()+1)
miss = {ats: [y for y in years_all
                    if not ((bin_df["ats_id"]==ats)&(bin_df["year"]==y)).any()]
        for ats in bin_df["ats_id"].unique()}
tab3 = (pd.Series(miss, name="missing_years")
          .apply(lambda x: ", ".join(map(str,x)) if x else "")
          .to_frame())
tab3.to_csv(TAB_DIR / "tab3_missing_years.csv")

# ---------------------------------------------------------
# 8.  TABLE 4 – Cross-feature contingency (HostedPool × IOI)
# ---------------------------------------------------------
crosstab = pd.crosstab(bin_df["offers_hosted_pool"],
                       bin_df["supports_iois"])
crosstab.to_csv(TAB_DIR / "tab4_cross_feature_contingency.csv")

print("\nPipeline complete  –  CSVs in data_clean/, figs in fig/, tables in tables/")
