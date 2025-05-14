#!/usr/bin/env python3
"""
mini_fetch.py  – smoke-test downloader (HTML-first via xslATS-N_X01)

Downloads up to 5 primary_doc files so you can verify seminar_parse.py.
"""

import functools, pathlib, time, requests

# ╭─ what to grab ──────────────────────────────────────────────────────────╮
TEST_ROWS  = [("UBSA", "0000230611"),      # UBS ATS
              ("SGMT", "0000042352")]      # SIGMA X2
TEST_YEARS = [2024, 2025]
MAX_FILES  = 5
# ╰─────────────────────────────────────────────────────────────────────────╯

SEC   = "https://www.sec.gov"
UA    = {"User-Agent": "ats-smoke/0.3 nqt2001@columbia.edu"}
OUT   = pathlib.Path("data_raw/test").resolve()
OUT.mkdir(parents=True, exist_ok=True)

# ───────────────────────────────── helpers ────────────────────────────────
@functools.lru_cache(maxsize=None)
def _cik_index(cik: str) -> list[dict]:
    url = f"{SEC}/Archives/edgar/data/{int(cik):010d}/index.json"
    return requests.get(url, headers=UA, timeout=20).json()["directory"]["item"]

def _latest_accession(cik: str, year: int):
    yr = str(year)
    buckets = [b for b in _cik_index(cik)
               if b["type"].startswith("folder") and b["last-modified"][:4] == yr]
    return max(buckets, key=lambda d: d["last-modified"])["name"] if buckets else None

def _try_get(url: str):
    r = requests.get(url, headers=UA, timeout=20)
    return r.content if r.ok else None

def _fetch_primary(cik: str, acc: str) -> tuple[str, bytes]:
    base = f"{SEC}/Archives/edgar/data/{int(cik):010d}/{acc}"

    # 1️⃣ direct path to HTML inside xsl folder
    html = _try_get(f"{base}/xslATS-N_X01/primary_doc.html")
    if html:
        return "primary_doc.html", html

    # 2️⃣ direct path to XML inside xsl folder
    xml  = _try_get(f"{base}/xslATS-N_X01/primary_doc.xml")
    if xml:
        return "primary_doc.xml", xml

    # 3️⃣ fallback – list directory, grab first primary_doc*
    idx  = requests.get(base + "/index.json", headers=UA, timeout=20).json()["directory"]["item"]
    for pref in (".html", ".htm", ".xml"):
        for itm in idx:
            n = itm["name"].lower()
            if n.startswith("primary_doc") and n.endswith(pref):
                blob = _try_get(f"{base}/{itm['name']}")
                if blob:
                    return itm["name"], blob
    raise FileNotFoundError("no primary_doc found")

# ───────────────────────────────── main ───────────────────────────────────
dl = 0
for mpid, cik in TEST_ROWS:
    for yr in TEST_YEARS:
        if dl >= MAX_FILES:
            quit()

        acc = _latest_accession(cik, yr)
        if not acc:
            print(f"!! {mpid} {yr}: no accession")
            continue

        try:
            fname, blob = _fetch_primary(cik, acc)
            out_file = OUT / f"{mpid}_{yr}{pathlib.Path(fname).suffix.lower()}"
            out_file.write_bytes(blob)
            print(f"✓ {mpid} {yr} → {out_file.name}")
            dl += 1
            time.sleep(1)        # be polite
        except Exception as e:
            print(f"!! {mpid} {yr}: {e}")
