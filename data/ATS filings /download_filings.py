#!/usr/bin/env python3
"""
Download the most-recent ATS-N “primary_doc” for each MPID and year.

  • Years: 2020-2025 (edit YEARS below)
  • MPID mapping file: ats_lookup.csv
      mpid,ats_name,cik,file_no,status,notes
  • Files saved to  data_raw/ats_filings/  as  MPID_YYYY.xml|html

SEC rate-limit is ~10 requests/second.  We stay far below that (0.8 s delay)
and cache the per-CIK index so every CIK costs only ONE hit.
"""

import csv, pathlib, time, requests, functools
from typing import Dict, List, Optional

YEARS         = range(2020, 2026)
LOOKUP_CSV    = "ats_lookup.csv"
OUT_DIR       = pathlib.Path("data_raw/ats_filings")
INCLUDE_CEASED = True                 # False → skip rows whose status=ceased
UA           = {"User-Agent": "ats-research/0.3 nqt2001@columbia.edu"}
DELAY_SEC     = 0.8                   # be nice
SEC_ROOT      = "https://www.sec.gov"

# ─────────────────────────── helpers ────────────────────────────
def backoff_json(url: str, tries: int = 5) -> Dict:
    """GET url → .json() with naive back-off on 429/5xx."""
    for k in range(tries):
        r = requests.get(url, headers=UA, timeout=20)
        if r.ok:
            return r.json()
        if r.status_code in (429, 502, 503, 504):
            time.sleep(2 ** k)          # 1 s, 2 s, 4 s, …
            continue
        r.raise_for_status()
    r.raise_for_status()


@functools.lru_cache(maxsize=None)
def cik_index(cik: str) -> List[dict]:
    url = f"{SEC_ROOT}/Archives/edgar/data/{int(cik):010d}/index.json"
    return backoff_json(url)["directory"]["item"]


def latest_accession_for_year(cik: str, year: int) -> Optional[str]:
    buckets = [
        itm for itm in cik_index(cik)
        if itm["type"].startswith("folder")             # 'folder.gif'
        and itm["last-modified"][:4] == str(year)
    ]
    if not buckets:
        return None
    newest = max(buckets, key=lambda d: d["last-modified"])
    return newest["name"]                               # accession folder


def download_primary(cik: str, accession: str) -> tuple[str, bytes]:
    base = f"{SEC_ROOT}/Archives/edgar/data/{int(cik):010d}/{accession}"
    items = backoff_json(base + "/index.json")["directory"]["item"]

    cand = [i for i in items if i["name"].lower().startswith("primary_doc")]
    if not cand:
        cand = [i for i in items if i["name"].lower().endswith(
                 (".xml", ".htm", ".html"))]
    if not cand:
        raise FileNotFoundError("no xml/html in " + accession)

    fname = cand[0]["name"]
    blob  = requests.get(f"{base}/{fname}", headers=UA, timeout=30)
    blob.raise_for_status()
    return fname, blob.content


# ─────────────────────────── main ───────────────────────────────
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(LOOKUP_CSV, newline="") as fh:
        rows = list(csv.DictReader(fh))

    for row in rows:
        if row["status"].lower() == "ceased" and not INCLUDE_CEASED:
            continue

        mpid, cik = row["mpid"], row["cik"]
        for yr in YEARS:
            try:
                acc = latest_accession_for_year(cik, yr)
                if not acc:
                    print(f"!! {mpid} {yr}: no filing")
                    continue

                fname, data = download_primary(cik, acc)
                ext   = pathlib.Path(fname).suffix.lower()
                out_f = OUT_DIR / f"{mpid}_{yr}{ext}"
                out_f.write_bytes(data)
                print(f"✓  {mpid} {yr}  ({acc})  → {out_f.name}")
                time.sleep(DELAY_SEC)

            except Exception as e:
                print(f"!! {mpid} {yr}: {e}")


if __name__ == "__main__":
    main()
