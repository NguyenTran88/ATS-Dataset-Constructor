#!/usr/bin/env python3
"""
Download the most-recent Form ATS-N “primary_doc” for each MPID & year.

• Years 2020-2025  (edit YEARS below)
• Mapping file  ats_lookup.csv
      mpid,ats_name,cik,file_no,status,notes
• Files land in  data_raw/ats_filings/   as  MPID_YYYY.html|xml

SEC rate-limit ≈10 req/s – we stay far below (0.8 s delay) and cache
the per-CIK listing so each CIK costs only ONE index hit.
"""

import csv, functools, pathlib, time, requests
from typing import Dict, List, Optional, Tuple

# ─────────── knobs ──────────────────────────────────────────────────────
YEARS          = range(2020, 2026)          # 2020-2025 inclusive
LOOKUP_CSV     = "ats_lookup.csv"
OUT_DIR        = pathlib.Path("data_raw/ats_filings")
INCLUDE_CEASED = True                       # False ⇒ skip rows with status=ceased
UA             = {"User-Agent": "ats-research/0.4 nqt2001@columbia.edu"}
DELAY_SEC      = 0.8
SEC_ROOT       = "https://www.sec.gov"

# ─────────── tiny helpers ───────────────────────────────────────────────
def _get_json(url: str, tries: int = 5) -> Dict:
    """GET → .json() with naive back-off on 429/5xx."""
    for k in range(tries):
        r = requests.get(url, headers=UA, timeout=20)
        if r.ok:
            return r.json()
        if r.status_code in (429, 502, 503, 504):
            time.sleep(2 ** k)          # 1 s → 2 s → 4 s …
            continue
        r.raise_for_status()
    r.raise_for_status()                # last raise

@functools.lru_cache(maxsize=None)
def cik_index(cik: str) -> List[dict]:
    url = f"{SEC_ROOT}/Archives/edgar/data/{int(cik):010d}/index.json"
    return _get_json(url)["directory"]["item"]

def latest_accession(cik: str, year: int) -> Optional[str]:
    buckets = [i for i in cik_index(cik)
               if i["type"].startswith("folder") and i["last-modified"][:4] == str(year)]
    return (max(buckets, key=lambda d: d["last-modified"])["name"]               # newest
            if buckets else None)

def _try_get(url: str) -> Optional[bytes]:
    r = requests.get(url, headers=UA, timeout=25)
    return r.content if r.ok else None

def download_primary(cik: str, accession: str) -> Tuple[str, bytes]:
    """
    Returns (filename, blob)  where filename is primary_doc.html|xml.
    Search order:
        1.   …/xslATS-N_X01/primary_doc.html
        2.   …/xslATS-N_X01/primary_doc.xml
        3.   first primary_doc* in accession root  (old behaviour)
    """
    base = f"{SEC_ROOT}/Archives/edgar/data/{int(cik):010d}/{accession}"

    # 1️⃣ direct HTML inside xsl folder
    blob = _try_get(f"{base}/xslATS-N_X01/primary_doc.html")
    if blob:
        return "primary_doc.html", blob

    # 2️⃣ direct XML inside xsl folder
    blob = _try_get(f"{base}/xslATS-N_X01/primary_doc.xml")
    if blob:
        return "primary_doc.xml", blob

    # 3️⃣ fallback – scan root directory
    items = _get_json(base + "/index.json")["directory"]["item"]
    for ext in (".html", ".htm", ".xml"):
        for itm in items:
            name = itm["name"].lower()
            if name.startswith("primary_doc") and name.endswith(ext):
                blob = _try_get(f"{base}/{itm['name']}")
                if blob:
                    return itm["name"], blob
    raise FileNotFoundError(f"primary_doc not found in {accession}")

# ─────────── main loop ───────────────────────────────────────────────────
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(LOOKUP_CSV, newline="") as fh:
        recs = list(csv.DictReader(fh))

    for row in recs:
        if row["status"].lower() == "ceased" and not INCLUDE_CEASED:
            continue

        mpid, cik = row["mpid"], row["cik"]
        for yr in YEARS:
            try:
                acc = latest_accession(cik, yr)
                if not acc:
                    print(f"!! {mpid} {yr}: no filing")
                    continue

                fname, data = download_primary(cik, acc)
                ext  = pathlib.Path(fname).suffix.lower()
                out  = OUT_DIR / f"{mpid}_{yr}{ext}"
                out.write_bytes(data)
                print(f"✓ {mpid} {yr} ({acc}) → {out.name}")
                time.sleep(DELAY_SEC)

            except Exception as exc:
                print(f"!! {mpid} {yr}: {exc}")

if __name__ == "__main__":
    main()
