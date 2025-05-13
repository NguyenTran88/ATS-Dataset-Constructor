import os, csv, collections, requests, base64, datetime as dt
from dotenv import load_dotenv
from tqdm import tqdm
import pandas as pd
from pathlib import Path
import numpy as np

# Load FINRA credentials
load_dotenv("/Users/nguyentran/Desktop/Econ seminar/data/volume data/.env")
CLIENT_ID     = os.getenv("FINRA_CLIENT_ID")
CLIENT_SECRET = os.getenv("FINRA_CLIENT_SECRET")

auth_token = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
token_url = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token?grant_type=client_credentials"

resp = requests.post(token_url,
                     headers={"Authorization": f"Basic {auth_token}",
                              "Content-Type": "application/x-www-form-urlencoded"})
resp.raise_for_status()
access_token = resp.json()["access_token"]


# Generate all Mondays over the past 5 years
today = dt.date.today()
start = today - dt.timedelta(days=5*365)
mondays = []
cur = start
while cur <= today:
    if cur.weekday() == 0:
        mondays.append(cur)
    cur += dt.timedelta(days=1)



# Aggregate weekly top 30 ATS MPIDs
ats_counts = collections.Counter()
ats_volumes = collections.defaultdict(list)
ats_ranks = collections.defaultdict(list)
weekly_rows = []   # <-- collect (MPID, weekStartDate, shares)

for monday in tqdm(mondays, desc="📊 Fetching weekly ATS data"):
    monday_str = monday.isoformat()
    url = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"
    params = {
        "compareFilter": [
            "atsSymbolFlag:eq:Y",
            f"weekStartDate:eq:{monday_str}"
        ],
        "fields": "mpid,totalWeeklyShareQuantity",
        "limit": 10000
    }
    try:
        r = requests.get(url,
                         headers={"Authorization": f"Bearer {access_token}",
                                  "Accept": "text/plain"},
                         params=params)
        r.raise_for_status()
    except Exception:
        continue

    totals = collections.Counter()
    for row in csv.DictReader(r.text.splitlines()):
        try:
            mpid = row["MPID"].strip()
            # valid MPIDs are always four alphabetic characters (UBSA, SGMT, …)
            if len(mpid) != 4 or not mpid.isalpha():
                continue          # ← skip the aggregate “all ATS” row and any junk
            totals[mpid] += int(row["totalWeeklyShareQuantity"])
        except:
            pass

    for rank, (mpid, vol) in enumerate(totals.most_common(30), 1):
        ats_counts[mpid] += 1
        ats_volumes[mpid].append(vol)
        ats_ranks[mpid].append(rank)
        # for each week; get top 30 and add: # of times a firm is in the top 30; the firms' volume that week; the firm rank that week
        # print(f"{mpid:6} | {rank:2} | {vol:,.0f}")
        weekly_rows.append(
            {"MPID": mpid,
             "weekStartDate": monday_str,
             "shares": vol}
        )


# 3 .  Aggregate + save
# -----------------------------------------------------------------------
out_dir = Path("data_clean")
out_dir.mkdir(exist_ok=True)

# 3 a. weekly_volume.csv  --------------------------------------------
weekly_df = pd.DataFrame(weekly_rows)
weekly_df.to_csv(out_dir / "weekly_volume.csv", index=False)

# 3 b. annual_volume.csv  --------------------------------------------
annual_df = (
    weekly_df
      .assign(year=lambda d: pd.to_datetime(d.weekStartDate).dt.year)
      .groupby(["MPID", "year"], as_index=False)["shares"]
      .sum()
      .rename(columns={"shares": "annual_shares"})
)
annual_df.to_csv(out_dir / "annual_volume.csv", index=False)

# 3 c. top15_overall.csv  --------------------------------------------
top15_df = (
    annual_df.groupby("MPID", as_index=False)["annual_shares"].sum()
             .rename(columns={"annual_shares": "total_5yr_shares"})
             .sort_values("total_5yr_shares", ascending=False)
             .head(15)
)
top15_df.to_csv(out_dir / "top15_overall.csv", index=False)


# console printout
for m in top15_df.MPID:
    r = ats_ranks[m]
    print(m, " std-dev of weekly rank =", np.std(r).round(2))
for _, row in top15_df.iterrows():
    mpid        = row["MPID"]
    total_vol   = row["total_5yr_shares"]
    weeks       = len(ats_volumes[mpid])
    avg_rank    = sum(ats_ranks[mpid]) / weeks
    print(f"{mpid:6} | Total Vol 5y: {total_vol:>12,.0f} | "
          f"Weeks in top-30: {weeks:3} | Avg weekly rank: {avg_rank:5.3f}")