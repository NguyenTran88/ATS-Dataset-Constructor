import os, csv, collections, requests, base64, datetime as dt
from dotenv import load_dotenv

# 1️⃣  Load credentials ------------------------------------------------------
load_dotenv("/Users/nguyentran/Desktop/Econ seminar/data/volume data/.env")
CLIENT_ID     = os.getenv("FINRA_CLIENT_ID")
CLIENT_SECRET = os.getenv("FINRA_CLIENT_SECRET")

if not (CLIENT_ID and CLIENT_SECRET):
    raise SystemExit("env vars FINRA_CLIENT_ID / FINRA_CLIENT_SECRET not found")

# 2️⃣  Get access token -------------------------------------------------------
auth_token   = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
token_url    = ("https://ews.fip.finra.org/fip/rest/ews/oauth2/"
                "access_token?grant_type=client_credentials")

resp = requests.post(token_url,
                     headers={"Authorization": f"Basic {auth_token}",
                              "Content-Type": "application/x-www-form-urlencoded"})

resp.raise_for_status()
access_token = resp.json()["access_token"]
print("Got token")


# --- pick the latest Monday -------------------------------------------------
monday = (dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
         ).isoformat()                      # e.g. '2025-05-05'

# ---------- 2. pull the rows ----------
url = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"
params = {
    "compareFilter": [
        "atsSymbolFlag:eq:Y",
        f"weekStartDate:eq:{monday}"
    ],
    "fields": "mpid,totalWeeklyShareQuantity",
    "limit": 100000
}
r = requests.get(url,
                 headers={"Authorization": f"Bearer {access_token}",
                          "Accept": "text/plain"},
                 params=params)
r.raise_for_status()

# ---------- 3. aggregate + top‑5 ----------
totals = collections.Counter()
for row in csv.DictReader(r.text.splitlines()):
    totals[row["MPID"]] += int(row["totalWeeklyShareQuantity"])

print("Top‑5 ATS by share volume – week of", monday)
for mpid, vol in totals.most_common(5):
    print(f"{mpid:6}  {vol:,}")