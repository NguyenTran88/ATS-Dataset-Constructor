import os, csv, collections, requests, base64, datetime as dt
from dotenv import load_dotenv
from tqdm import tqdm

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
            totals[row["MPID"]] += int(row["totalWeeklyShareQuantity"])
        except:
            pass

    for rank, (mpid, vol) in enumerate(totals.most_common(30), 1):
        ats_counts[mpid] += 1
        ats_volumes[mpid].append(vol)
        ats_ranks[mpid].append(rank)

# Summarize results
# print("\n🏁 Top 15 Consistently High-Volume ATSs Over Past 5 Years:\n")
# ranked_ats = sorted(ats_counts.items(), key=lambda x: (-x[1], x[0]))[:15]


# for mpid, weeks in ranked_ats:
#     avg_rank = sum(ats_ranks[mpid]) / len(ats_ranks[mpid])
#     avg_volume = sum(ats_volumes[mpid]) / len(ats_volumes[mpid])
#     print(f"{mpid:6} | Weeks in Top 30: {weeks:3} | Avg Rank: {avg_rank:4.1f} | Avg Volume: {avg_volume:,.0f}")

cumulative_volume = {mpid: sum(vols) for mpid, vols in ats_volumes.items()}
ranked_ats = sorted(cumulative_volume.items(), key=lambda x: -x[1])[:15]

for mpid, total_vol in ranked_ats:
    weeks = len(ats_volumes[mpid])
    avg_rank = sum(ats_ranks[mpid]) / weeks
    avg_volume = total_vol / weeks
    print(f"{mpid:6} | Total Volume: {total_vol:,.0f} | Weeks: {weeks:3} | Avg Rank: {avg_rank:4.1f}")
