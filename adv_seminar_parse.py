import re
from bs4 import BeautifulSoup, NavigableString

# Regex-based patterns for structural features
regex_features = {
    "Hosted pool presence": r"(hosted\s+pool|private\s+room|segregated\s+environment)",
    "Counterparty selection controls": r"(counterparty.*selection|preference.*interaction|limit.*access)",
    "Support for IOIs or Block IOIs": r"(indication[s]? of interest|IOIs?|block IOIs?)",
    "Custom/non-displayed order types": r"(non[- ]?displayed|custom.*order type|dark liquidity)",
    "Market data feed availability": r"(market.*data.*(feed|availability|distribution)|real-time.*information)",
    "Smart routing / sponsored access": r"(smart.*routing|sponsored.*access|route.*external)"
}

# Placeholder for simple yes/no logic
yes_no_features = {
    # Example: "Feature label": "Question text"
}

# ---------- REGEX HELPER ----------
def extract_regex_feature(text, pattern):
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        snippet = text[max(0, match.start()-100):match.end()+100]
        return snippet.strip()
    return "Not mentioned"

# ---------- YES/NO PARSER ----------
#currently work for opt out only
# def get_radio_button_answer(soup, label_fragment):
#     for row in soup.find_all("tr"):
#         label = row.find("td", class_="label")
#         if label and label_fragment.lower() in label.text.lower():
#             # This is the row that presumably contains the yes/no radio buttons
#             answer_td = row.find_all("td")[-1]
#             #print(answer_td.prettify())
            
#             # Debug: print(answer_td.prettify()) if you want to see the exact structure
#             spans = answer_td.find_all("span", class_="yesNo")
    
#             for span in spans:
#                 contents = list(span.children)  # a mix of <img> tags and text nodes
#                 for i, node in enumerate(contents):
#                     if node.name == "img":
#                         print(node.get("alt", ""))
#                     if node.name == "img" and "Radio button checked" in node.get("alt", "").lower():
                        
#                         # Found the not checked radio button.
#                         # Now find the subsequent text node to see if it’s "yes" or "no".
#                         # if we didn't check yes -> return False; else True
#                         for j in range(i+1, len(contents)):
#                             if isinstance(contents[j], str):
#                                 label_text = contents[j].strip().lower()
#                                 if label_text == "yes":
#                                     return True 
#                                 elif label_text == "no":
#                                     return False
#     return None

def get_radio_button_answer(soup: BeautifulSoup, label_fragment: str):
    for row in soup.find_all("tr"):
        label_cell = row.find("td", class_="label")
        if label_cell and label_fragment.lower() in label_cell.get_text(" ", strip=True).lower():

            # 1) EITHER look at the src -------------------------------------------------
            checked = row.find("img", src=lambda s: s and "radio-checked" in s)
            # ---------------------------------------------------------------------------

            if not checked:
                return None

            # Walk forward until we hit the “Yes” / “No” text node
            node = checked.next_sibling
            while node and (not isinstance(node, str) or not node.strip()):
                node = node.next_sibling

            if node:
                return node.strip().lower() == "yes"
            return None
    return None



def extract_yes_no_feature(soup, question_start):
    result = get_radio_button_answer(soup, question_start)
    if result is True:
        return "Yes"
    elif result is False:
        return "No"
    else:
        return "Not found or unclear"

# ---------- SPECIAL: OPT-OUT CAPABILITY ----------
def extract_opt_out_logic(soup: BeautifulSoup):
    a_label = ("Can any Subscriber opt out from interacting with orders "
               "and trading interest of the Broker-Dealer Operator")
    b_label = ("Can any Subscriber opt out from interacting with the orders "
               "and trading interest of an Affiliate of the Broker-Dealer Operator")

    a = get_radio_button_answer(soup, a_label)
    b = get_radio_button_answer(soup, b_label)
    print(a, b, "opt_out_logic")       # keep your debug line if useful

    if a is True and b is True:
        return ("Yes — Subscriber can opt out of both the ATS operator "
                "and its affiliates")
    elif a is True and b is False:
        return ("Yes — Subscriber can opt out of ATS operator "
                "but not affiliates")
    elif a is False and b is True:
        return ("Yes — Subscriber can opt out of affiliates "
                "but not ATS operator")
    elif a is False and b is False:
        return ("No — Subscriber cannot opt out from either")
    else:
        return ("Unclear — at least one of the two answers was not found "
                "or could not be parsed")

# ---------- SPECIAL: INTERNAL/AFFILIATE ACCESS ----------
def extract_internal_affiliate_access(soup):
    q1 = "Are business units of the Broker-Dealer Operator permitted to enter or direct the entry of orders"
    q2 = "Are Affiliates of the Broker-Dealer Operator permitted to enter or direct the entry of orders"
    a = get_radio_button_answer(soup, q1)
    b = get_radio_button_answer(soup, q2)
    if a and b:
        return "Yes — Both broker-dealer operator and its affiliates have trading access"
    elif a and not b:
        return "Yes — Only the broker-dealer operator has access"
    elif not a and b:
        return "Yes — Only affiliates have access"
    elif a is False and b is False:
        return "No — Neither the operator nor its affiliates have trading access"
    else:
        return "Unclear or mixed — unable to determine"

# ---------- MAIN FUNCTION ----------
def extract_features_from_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    results = {}

    # Regex features
    # for label, pattern in regex_features.items():
    #     results[label] = extract_regex_feature(html, pattern)

    # Special-case features
    results["Subscriber opt-out capability"] = extract_opt_out_logic(soup)
    #results["Internal/Affiliate Trading Access"] = extract_internal_affiliate_access(soup)

    # Generic yes/no features
    for label, question in yes_no_features.items():
        results[label] = extract_yes_no_feature(soup, question)

    for k, v in results.items():
        print(f"{k}:\n{v}\n{'-'*40}")

    return results

if __name__ == "__main__":
    extract_features_from_file("primary_doc.xml.html")
