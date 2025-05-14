# -*- coding: utf-8 -*-
"""Simple ATS‑N HTML feature extractor

Usage::

    python ats_feature_parser.py primary_doc.xml.html

The script prints a dictionary of extracted features.  Adapt or import as
needed for batch processing.
""" 
from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import Dict, Optional, List
import warnings
from collections import defaultdict
from bs4 import BeautifulSoup, NavigableString, XMLParsedAsHTMLWarning
from radio_matrix import RadioMatrix  



# ---------------------------------------------------------------------------
# 1.  Feature definitions
# ---------------------------------------------------------------------------
# ---- 1‑a. Regex‑based features (free‑text search in the entire document) ----
REGEX_FEATURES: Dict[str, str] = {
    # key                                 pattern (case‑insensitive)
    "offers_hosted_pool":                 r"(hosted\s+pool|private\s+room|segregated\s+environment)",
    "supports_iois":                      r"(indication[s]?\s+of\s+interest|iois?|block\s+iois?)",
    "custom_order_types":                 r"(non[- ]?displayed|custom.*order\s+type|dark\s+liquidity)",
    "market_data_feed_available":         r"(market.*data.*(feed|availability|distribution)|real[- ]?time.*information)",
}

# ---- 1‑b. Yes/No questions addressed by radio buttons ----------------------
YES_NO_QUESTIONS: Dict[str, str] = {
    # Subscriber opt‑out
    "subscriber_opt_out_bdo": (
        "Can any Subscriber opt out from interacting with orders "
        "and trading interest of the Broker-Dealer Operator"
    ),
    "subscriber_opt_out_affiliate": (
        "opt out from interacting with the orders and trading interest "
        "of an Affiliate of the Broker-Dealer Operator"
    ),

    # Counter‑party selection (Item 14)
    "counterparty_selection_supported": (
        "a. Can orders or trading interest be designated to interact or not interact"
    ),
    "counterparty_selection_uniform": (
        "b. If yes to Item 14(a)"
    ),

    # Internal / affiliate trading access
    "internal_trading_allowed": (
        "Are business units of the Broker-Dealer Operator permitted to enter or direct the entry of orders"
    ),
    "affiliate_access_to_ats": (
        "Are Affiliates of the Broker-Dealer Operator permitted to enter or direct the entry of orders"
    ),
    "routing_to_affiliate_venue": (
        "be routed to a Trading Center operated or controlled by an Affiliate of the Broker-Dealer Operator"
    ),

    # Display & ECN status (Item 15)
    "ecn_status": (
        "operate as an Electronic Communication Network as defined in Rule 600"
    ),
    "display_to_persons": (
        "displayed or made known to any Person (not including those employees"
    ),
    "display_procedures_uniform": ("display procedures required to be identified in 15(b) the same"),

    # IOI / Conditional Orders (Item 9)
    "supports_iois": (
        "send or receive any messages indicating trading interest (e.g., IOIs, actionable IOIs, or conditional orders)"
    ),
    "ioi_uniform_treatment": (
        "b. If yes to Item 9(a), are the terms and conditions governing conditional orders"
    ),

    # --- Segmentation (Item 13) -------------------------------------------
    "segmentation_supported":        "segmented into categories, classifications, tiers, or levels",
    "segmentation_uniform":          "segmentation of orders and trading interest the same for all Subscribers",
    "segmentation_customer_flag":    "identify orders or trading interest entered by a customer",
    "segmentation_disclosed":        "does the NMS Stock ATS disclose to any Person the designated segmented",
    "segmentation_disclosure_uniform":"disclosures required to be identified in 13(d) the same",

   
}

# ---------------------------------------------------------------------------
# Patterns for quick recipient extraction from Item 15 explanation text
# ---------------------------------------------------------------------------
RECIPIENT_PATTERNS: Dict[str, str] = {
    "iqx_data_feed":   r"iqx data feed",
    "hosted_pool_participants": r"hosted\s+pools?",
    "sor":             r"\bSOR\b|smart order router",
    "dma_provider":    r"\bDMA\b|direct market access",
    "sponsored_firm":  r"sponsored\s+firm",
    "broker_dealer":   r"broker[- ]dealer operator|gsco personnel|execution coverage",
}

# ---------------------------------------------------------------------------
# 2.  Low‑level helpers
# ---------------------------------------------------------------------------
# get soup helper
def _get_soup(html: str) -> BeautifulSoup:
    is_xml = html.lstrip().startswith("<?xml") or "<ATS-N" in html[:300]
    if is_xml:
        # silence “XMLParsedAsHTML” warning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        return BeautifulSoup(html, "xml")          # ← XML parser
    return BeautifulSoup(html, "html.parser")      # ← existing path

# Helper for text normalisation (hyphen → space, collapse whitespace)
_HYPHEN_WS = re.compile(r"[‐‑–—-]|\s+")

def _normalise(txt: str) -> str:
    """lower‑case and collapse whitespace / hyphens"""
    return _HYPHEN_WS.sub(" ", txt).lower().strip()

def _bool_to_word(value: Optional[bool]) -> str:
    # convert boolean to yes/no/unclear
    return {True: "Yes", False: "No"}.get(value, "Unclear")

def _bool_to_int(value: Optional[bool]) -> Optional[int]:
    return {True: 1, False: 0}.get(value, None)



# ---------------------------------------------------------------------------
# 3.  Feature‑specific helpers (compose low‑level answers if needed)
# ---------------------------------------------------------------------------

def _subscriber_opt_out(results: dict, radios) -> str:
    """Combine the two opt‑out questions into one human‑readable answer."""
    bdo = radios._radio_yes_no(YES_NO_QUESTIONS["subscriber_opt_out_bdo"])
    aff = radios._radio_yes_no(YES_NO_QUESTIONS["subscriber_opt_out_affiliate"])
    del results["subscriber_opt_out_bdo"]
    del results["subscriber_opt_out_affiliate"]
    if bdo is True and aff is True:
        return "Yes — Subscriber can opt out of both the ATS operator and its affiliates"
    if bdo is True and aff is False:
        return "Yes — Subscriber can opt out of ATS operator but not affiliates"
    if bdo is False and aff is True:
        return "Yes — Subscriber can opt out of affiliates but not ATS operator"
    if bdo is False and aff is False:
        return "No — Subscriber cannot opt out from either"
    return "Unclear"

def _counterparty_selection(results: dict, radios) -> str:
    """Extract counter-party selection logic and store description if available."""
    supported = radios._radio_yes_no(YES_NO_QUESTIONS["counterparty_selection_supported"])
    uniform = radios._radio_yes_no(YES_NO_QUESTIONS["counterparty_selection_uniform"])

    # Clean up intermediary keys
    del results["counterparty_selection_supported"]
    del results["counterparty_selection_uniform"]

    # Find explanation text (next <div class="fakeBox3"> after the label)
    explanation = None
    summary = _bool_to_word(supported)
    uniformity = _bool_to_word(uniform)

    result = f"{summary} — procedures are {'uniform' if uniform else 'not uniform'}"
    if explanation:
        result += f"\nDetails: {explanation}"

    return result

#internal/aff trading
def extract_internal_trading_access(radios) -> Dict[str, str]:
    a = radios._radio_yes_no(YES_NO_QUESTIONS["internal_trading_allowed"])
    b = radios._radio_yes_no(YES_NO_QUESTIONS["affiliate_access_to_ats"])
    c = radios._radio_yes_no(YES_NO_QUESTIONS["routing_to_affiliate_venue"])

    result = {}
    result["internal_trading_allowed"] = _bool_to_word(a)
    result["affiliate_access_to_ats"] = _bool_to_word(b)
    result["routing_to_affiliate_venue"] = _bool_to_word(c)

    summary_parts = []
    if a is True:
        summary_parts.append("ATS operator’s business units can trade on the ATS.")
    elif a is False:
        summary_parts.append("ATS operator’s business units are not allowed to trade on the ATS.")

    if b is True:
        summary_parts.append("Affiliates can also send orders into the ATS.")
    elif b is False:
        summary_parts.append("Affiliates are not allowed to send orders into the ATS.")

    if c is True:
        summary_parts.append("ATS can route orders to affiliated venues.")
    elif c is False:
        summary_parts.append("ATS cannot route orders to affiliated venues.")

    result["trading_access_summary"] = " ".join(summary_parts)
    return result

def _ioi_support(soup: BeautifulSoup, results: dict, radios) -> str:
    has_support = radios._radio_yes_no(YES_NO_QUESTIONS["supports_iois"])
    uniform = radios._radio_yes_no(YES_NO_QUESTIONS["ioi_uniform_treatment"])

    del results["supports_iois"]
    del results["ioi_uniform_treatment"]

    explanation = None
    label_node = soup.find("td", string=lambda s: s and "If yes, identify and explain the use of the messages" in s)
    if label_node:
        div = label_node.find_next("div", class_="fakeBox3")
        if div:
            explanation = div.get_text(" ", strip=True)

    summary = _bool_to_word(has_support)
    uniformity = _bool_to_word(uniform)
    result = f"{summary} — terms and conditions are {'uniform' if uniform else 'not uniform'}"

    # uncomment if want explanation
    # if explanation:
    #     result += f"\nDetails: {explanation}"

    return result


# Order-type detection patterns  (regex, case-insensitive)
# ---------------------------------------------------------------------------
ORDER_TYPE_PATTERNS: Dict[str, List[str]] = {
    #  ► write patterns in lower-case, no \b at ends – they are added later.
    "midpoint":      [r"mid point peg", r"mid peg", r"midpoint peg", r"mp peg"],
    "market_peg":    [r"market peg"],
    "primary_peg":   [r"primary peg"],
    "vwap":          [r"vwap"],
    "post_only":     [r"post ?only", r"add liquidity only", r"\balo\b"],
    "conditional":   [r"conditional order", r"firm up", r"firm-up"],
    "displayed":     [r"displayed order", r"non displayed"],   # presence alone
    "market":        [r"market order"],
    "limit":         [r"limit order"],
    "iceberg":       [r"ice ?berg",                  # “iceberg”, “ice-berg”
                      r"reserve order",              # alt marketing name
                      r"hidden size"],               # descriptive phrase
    "discretionary": [r"discretionary order",
                      r"disc ?order",                # “disc order”
                      r"dqr",                        # venue-specific acronym
                     ],
}

# Pre-compile once
ORDER_TYPE_REGEXES: Dict[str, List[re.Pattern]] = {
    k: [re.compile(rf"\b{p}\b", re.I) for p in lst] for k, lst in ORDER_TYPE_PATTERNS.items()
}

_UNKNOWN_PATTERN = re.compile(
    r"\b([A-Z0-9+/.-]{3,})\s+"
    r"(?:order(?:s)?|peg(?:ged)?|order\s+type|orders\s+type[s]?)\b",
    re.I,
)

def _item7_text(soup: BeautifulSoup) -> str:
    anchor = soup.find("a", {"name": "partIIIitem7"})
    if anchor:
        # grab everything until the next anchor or big header
        bits = []
        for sib in anchor.next_elements:
            if isinstance(sib, NavigableString):
                bits.append(str(sib))
                continue
            if sib.name == "a" and sib.get("name", "").startswith("partIIIitem") and sib != anchor:
                break
            bits.append(sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else "")
        return " ".join(bits)
    return ""


def parse_order_type_features(item7_raw: str) -> Dict[str, str]:
    text_norm = _normalise(item7_raw)

    features: Dict[str, str] = {}
    raw_hits: Dict[str, List[str]] = defaultdict(list)

    # 1️⃣  search known patterns
    detected: List[str] = []
    for key, patterns in ORDER_TYPE_REGEXES.items():
        hit = False
        for rx in patterns:
            m = rx.search(text_norm)
            if m:
                raw_hits[key].append(m.group(0))
                detected.append(key)
                hit = True
        features[f"supports_{key}_orders"] = "Yes" if hit else "No"

    # 2️⃣  catch any *unknown* “… order(s)” / “… peg” phrase
    unknown_tokens: List[str] = sorted({m.group(1).upper() for m in _UNKNOWN_PATTERN.finditer(item7_raw)
                                        if m.group(1).lower() not in detected})
    STOP = {
    "THE","AND","FOR","UPON","WHICH","EACH","OTHER","SUCH","THESE","THREE",
    "ANOTHER","DAY","BUY","SELL","FIRM","ORDER","ORDERS","LIMIT","MARKET",
    "PRIMARY","PEGGED","ARRIVING","FOLLOWING","INCOMPLETE","NECESSARY","CENTERS.",
    "CONNECTIVITY.","CONTRA-SIDE","ATTRIBUTES"
}
    unknown_tokens = list({tok for tok in unknown_tokens if tok.upper() not in STOP})
    features["custom_order_types_detected"] = "Yes" if detected or unknown_tokens else "No"
    features["custom_order_types_list"]     = ", ".join(sorted(detected + unknown_tokens))
    features["custom_order_types_raw_matches"] = "; ".join(
        f"{k}:{'|'.join(v)}" for k, v in raw_hits.items()
    ) or "None"
    features["unrecognised_custom_orders"]  = ", ".join(unknown_tokens) or "None"

    return features


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
#  ✨  Market-data feed discovery helpers  (Item 15, 5(a) + optional 23)  ✨
# ---------------------------------------------------------------------------

# 1️⃣  broader synonym list for the Yes/No scan --------------------------------
REGEX_FEATURES["market_data_feed_available"] = (
    r"(market|proprietary|depth[- ]of[- ]book|order|liquidity).*data.*feed"
    r"|data.*(distribution|service|availability)"
)

# 2️⃣  feed-token regex, now case-insensitive & handles quotes
CAP_FEED = re.compile(
    r"['\"]?([A-Z0-9][A-Z0-9_-]{1,})['\"]?\s+(?:depth[- ]of[- ]book\s+)?data\s+feed",
    re.I,
)
GENERIC_FEED = re.compile(r"\b(\w+?)\s+data\s+feed\b", re.I)

# 3️⃣  vendor hints => public/private classifier
VENDORS = r"Bloomberg|Pico|Exegy|ICE|CQS|CQG|Thesys|Extranet|SIP"
PUBLIC_HINTS  = re.compile(
    r"(available to (all )?(participants|subscribers)|open to external|full depth of book"
    rf"|via (?:{VENDORS}))", re.I)
PRIVATE_HINTS = re.compile(
    r"(internal\s+(?:SOR|router|algo|tool)|internal\s+only|not\s+displayed"
    r"|aggregated\s+and\s+anonymized)", re.I)

# 4️⃣  grab-section helper -----------------------------------------------------
def _section_text(soup: BeautifulSoup, anchor_name: str) -> str:
    """Return all text under <a name="anchor_name"> … until the next Item anchor."""
    a = soup.find("a", {"name": anchor_name})
    if not a:
        return ""
    bits = []
    for n in a.next_elements:
        if isinstance(n, NavigableString):
            bits.append(str(n))
            continue
        if n.name == "a" and n.get("name", "").startswith("partIIIitem") and n != a:
            break
        bits.append(n.get_text(" ", strip=True) if hasattr(n, "get_text") else "")
    return " ".join(bits)

# 5️⃣  master feed-extraction routine -----------------------------------------
def _extract_display_features(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Looks at:
      • Part III Item 15  (Display)      – mandatory if a feed exists
      • Part II  Item 5(a) (Products)    – many ATSs describe feeds here
      • Part III Item 23  (Market Data)  – optional; toggle via ITEM23_FALLBACK
    """
    ITEM23_FALLBACK = True   # ← flip to False if you don’t want Item 23 parsing

    # --- collect raw text blocks --------------------------------------------
    txt_blocks = []

    # Item 15 – first try original label search (keeps speed)
    node = soup.find("td", string=lambda s: s and "display procedures" in s.lower())
    if node:
        div = node.find_next("div", class_="fakeBox3")
        if div:
            txt_blocks.append(div.get_text(" ", strip=True))

    # If that failed, or as a complement, take the whole Item 15 section
    txt_blocks.append(_section_text(soup, "partIIIitem15"))

    # Item 5(a)
    txt_blocks.append(_section_text(soup, "partIIitem5"))

    # Optional Item 23 fallback
    if ITEM23_FALLBACK:
        txt_blocks.append(_section_text(soup, "partIIIitem23"))

    txt = " ".join(txt_blocks)
    txt_norm = _normalise(txt)

    # --- discover feeds ------------------------------------------------------
    feeds   = _discover_feed_tokens(txt)
    recips  = " / ".join(
        m.group(0) for m in re.finditer(r"(?:to|for)\s+[^.]{1,60}\.", txt, re.I)
    ) or "Unspecified recipients"

    mech_re = re.search(r"(data\s+feed|depth[- ]of[- ]book|ioi|fix|sor)", txt, re.I)
    mech    = mech_re.group(1) if mech_re else "Unspecified mechanism"

    return {
        #"display_description_summary":  txt[:450].strip(),          # keep it short
        #"display_recipients":           recips,
        "display_mechanism":            mech,
        "display_public_private_guess": _classify_public_private(txt_norm),
        "display_feed_names":           ", ".join(feeds) or "None",
    }

# Dynamic feed‑name discovery for market data feed
def _classify_public_private(text: str) -> str:
    if re.search(PUBLIC_HINTS, text):
        return "public_like"
    if re.search(PRIVATE_HINTS, text):
        return "private_like"
    return "unclear"


def _discover_feed_tokens(text: str) -> List[str]:
    """Return every unique feed token, e.g. IQX, Ocean, Exegy."""
    tokens = set(m.group(1).upper() for m in CAP_FEED.finditer(text))
    tokens.update(m.group(1).upper() for m in GENERIC_FEED.finditer(text))
    return sorted(tokens)

# 3.  Segmentation extraction ------------------------------------------------

SEG_TAG_PATTERNS = [
    r"taker\s+level",            # Specific matching tiers (Sigma X2 style)
    r"taker\s+category",          # a/b/c labels
    r"inclusion\s+level",         # matching willingness settings
    r"contra\s+category",         # matching filter set by liquidity provider
    r"counterparty\s+classification", # general matching framework

    r"mark[- ]?out\s+analysis",   # post-trade quality analysis
    r"category\s+id",             # flow segmentation label (could be called Category ID)
    r"taker\s+token",             # flow segmentation token (participant-applied)

    # NEW broader patterns:
    r"order\s+type\s+segmentation",    # segmentation by type of order
    r"participant\s+(type|class|segmentation)", # segmentation by participant group
    r"counterparty\s+restriction",     # general restrictions on counterparty matching
    r"segmentation\s+(token|label|category)", # catch other variations of segmentation
]
# ---------------------------------------------------------------------------
# 🔸  Data‑segmentation extraction (Item 13) 🔸
# ---------------------------------------------------------------------------

def _item13_text(soup: BeautifulSoup) -> str:
    """
    Return the raw plain‑text that the filer wrote in Item 13(c)
    ‘If yes, explain the segmentation procedures…’.
    """
    anchor = soup.find("a", {"name": "partIIIitem13"})
    if not anchor:
        return ""
    for sib in anchor.next_elements:
        if isinstance(sib, NavigableString):
            continue
        # The narrative is always inside the first fakeBox3 <div>
        if sib.name == "div" and sib.get("class") == ["fakeBox3"]:
            return sib.get_text(" ", strip=True)
        # Don’t wander into the next Item
        if sib.name == "a" and sib.get("name", "").startswith("partIIIitem") and sib is not anchor:
            break
    return ""

# Pre‑compiled token matcher (same patterns list you already have)
_seg_token_rx = re.compile("|".join(SEG_TAG_PATTERNS), re.I)

def _extract_segmentation_features(soup: BeautifulSoup, res: Dict[str, str]) -> Dict[str, str]:
    """
    Builds a single dict with:
      • Yes/No answers to 13 (a)‑(e)   (already stored in *res*)
      • Detected segmentation keywords
      • Optional short prose summary
    """
    prose = _item13_text(soup)
    tokens = sorted({m.group(0).lower() for m in _seg_token_rx.finditer(prose)})

    features = {
        # radio buttons – they were filled earlier, just move & pop
        "segmentation_supported":        res.pop("segmentation_supported", "Unclear"),
        "segmentation_uniform":          res.pop("segmentation_uniform", "Unclear"),
        "segmentation_customer_flag":    res.pop("segmentation_customer_flag", "Unclear"),
        "segmentation_disclosed":        res.pop("segmentation_disclosed", "Unclear"),
        "segmentation_disclosure_uniform": res.pop("segmentation_disclosure_uniform", "Unclear"),

        # free‑text analysis
        "segmentation_tags": ", ".join(tokens) if tokens else "None detected",
        "data_segmentation_practices": (prose[:400] + "…") if len(prose) > 400 else prose or "No narrative provided",
    }
    return features


# ---------------------------------------------------------------------------
# 4.  Master extractor
# ---------------------------------------------------------------------------

def extract_features_from_html(html: str, ats_id: Optional[str] = None, year: Optional[int] = None) -> Dict[str, str]:
    #soup = BeautifulSoup(html, "html.parser")
    soup = _get_soup(html)
    radios = RadioMatrix(soup) 
    results: Dict[str, str] = {}
    if ats_id: results["ats_id"] = ats_id
    if year:   results["year"] = year

    # 4‑a. Regex features -----------------------------------------------------
    for key, pattern in REGEX_FEATURES.items():
        results[key] = (
            "Yes" if re.search(pattern, html, flags=re.IGNORECASE) else "No"
        )

    # 4‑b. Simple Yes/No radio questions -------------------------------------
    for key, fragment in YES_NO_QUESTIONS.items():
        results[key] = _bool_to_word(radios._radio_yes_no(fragment))

    # 4‑c. Composed / multi‑step features ------------------------------------

    #subscriber logic
    results["subscriber_opt_out_capability"] = _subscriber_opt_out(results, radios)
    #counterparty logic
    results["counterparty_selection"] = _counterparty_selection(results, radios)
    # Add new internal/affiliate access logic
    results.update(extract_internal_trading_access(radios))
    # ioi logic
    results["supports_iois"] = _ioi_support(soup, results, radios)
    # order type
    results.update(parse_order_type_features(_item7_text(soup)))
    
    # # -- display block -------------------------------------------------------
    results.update(_extract_display_features(soup))
    # # segmentation block
    results.update(_extract_segmentation_features(soup, results))




    return results


# ---------------------------------------------------------------------------
# 5.  CLI convenience wrapper
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python seminar_parse.py <html-file>")
        sys.exit(1)

    html_file = Path(sys.argv[1])
    if not html_file.exists():
        print(f"File not found: {html_file}")
        sys.exit(1)

    features = extract_features_from_html(html_file.read_text(encoding="utf‑8"))
    for k, v in features.items():
        print(f"{k:35}: {v}")


# if __name__ == "__main__":
#     main()

if __name__ == "__main__":
    from pathlib import Path, PurePath
    import sys, json

    if len(sys.argv) != 2:
        print("Usage: python seminar_parse.py <html-file>")
        sys.exit(1)

    html_path = Path(sys.argv[1])
    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    ats_id = PurePath(sys.argv[1]).stem.split("_")[0]
    year = int(PurePath(sys.argv[1]).stem.split("_")[1]) 
    
    features = extract_features_from_html(html_text, ats_id=ats_id, year=year)
    print(json.dumps(features, indent=2))

