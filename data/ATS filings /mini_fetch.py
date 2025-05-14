#!/usr/bin/env python3
"""
mini_fetch.py  – download *one* primary_doc from a few CIKs/years
Edit TEST_ROWS / TEST_YEARS to taste.  Creates data_raw/test/.
"""

import pathlib, time, requests, functools

TEST_ROWS   = [("UBSA", "0000230611"),     # UBS ATS
               ("SGMT", "0000042352")]     # SIGMA X2
TEST_YEARS  = [2024, 2025]                 # will stop after 5 files
OUT_DIR     = pathlib.Path("data_raw/test")
UA          = {"User-Agent": "ats-smoke/0.1 nqt2001@columbia.edu"}
SEC         = "https://www.sec.gov"
OUT_DIR.mkdir(parents=True, exist_ok=True)

@functools.lru_cache(maxsize=None)
def cik_index(cik):
    url = f"{SEC}/Archives/edgar/data/{int(cik):010d}/index.json"
    return requests.get(url, headers=UA, timeout=20).json()["directory"]["item"]

def newest_accession(cik, year):
    items = [i for i in cik_index(cik)
             if i["type"].startswith("folder") and i["last-modified"][:4]==str(year)]
    return max(items, key=lambda d: d["last-modified"])["name"] if items else None

def primary_doc(cik, acc):
    base  = f"{SEC}/Archives/edgar/data/{int(cik):010d}/{acc}"
    idx   = requests.get(base+"/index.json", headers=UA, timeout=20).json()
    name  = next(i["name"] for i in idx["directory"]["item"]
                 if i["name"].lower().startswith("primary_doc"))
    return name, requests.get(f"{base}/{name}", headers=UA, timeout=30).content

count = 0
for mpid, cik in TEST_ROWS:
    for yr in TEST_YEARS:
        if count == 5:
            quit()                       # safety cap
        acc = newest_accession(cik, yr)
        if not acc:
            print(f"!! {mpid} {yr}: none")
            continue
        fname, blob = primary_doc(cik, acc)
        out = OUT_DIR / f"{mpid}_{yr}{pathlib.Path(fname).suffix.lower()}"
        out.write_bytes(blob)
        print(f"✓  {mpid} {yr} -> {out.name}")
        count += 1
        time.sleep(1)
