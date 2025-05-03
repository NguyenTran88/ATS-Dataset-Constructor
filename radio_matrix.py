from bs4 import BeautifulSoup
import re
from typing import Optional

class RadioMatrix:
    """Caches radio‑button rows for one HTML document."""

    _HYPHEN_WS = re.compile(r"[‐‑–—-]|\s+")

    def __init__(self, soup: BeautifulSoup):
        self.rows: list[tuple[str, BeautifulSoup]] = []
        self._build_rows_cache(soup)

    @classmethod
    def _normalise(cls, txt: str) -> str:
        return cls._HYPHEN_WS.sub(" ", txt).lower().strip()

    def _build_rows_cache(self, soup: BeautifulSoup) -> None:
        """Build internal cache of normalized label + row pairs."""
        for row in soup.select("tr:has(td.label)"):
            label = self._normalise(row.td.get_text(" ", strip=True))
            self.rows.append((label, row))

    def _radio_yes_no(self, label_fragment: str) -> Optional[bool]:
        """Return True (Yes), False (No), or None based on checked radio button and nearby text."""
        frag = self._normalise(label_fragment)

        for label, row in self.rows:
            if frag not in label:
                continue

            img = row.select_one('img[src*="radio-checked"]')
            if not img:
                return None

            txt = (img.next_sibling or "").lower()
            return "yes" in txt

        return None
    

'''
 radio_matrix.py   (you can keep it in the same repo or package)

from bs4 import BeautifulSoup, NavigableString
import re
from typing import Optional

class RadioMatrix:
    """Caches radio‑button rows for one HTML document."""

    _HYPHEN_WS = re.compile(r"[‐‑–—-]|\s+")

    def __init__(self, soup: BeautifulSoup):
        self.rows: list[tuple[str, BeautifulSoup]] = []
        for row in soup.select("tr:has(td.label)"):
            norm = self._normalise(row.td.get_text(" ", strip=True))
            self.rows.append((norm, row))

    # ------------------------------------------------------------
    @classmethod
    def _normalise(cls, txt: str) -> str:
        return cls._HYPHEN_WS.sub(" ", txt).lower().strip()

    # PUBLIC API -----------------------------------------------
    def _radio_yes_no(self, key_text: str) -> Optional[bool]:
        key = self._normalise(key_text)

        # 1️ Locate the row (exact match or 'a./b./c.' heuristic)
        row = None
        for label, r in self.rows:
            if label == key or (key in label and re.match(r"^[a-z]\.", label)):
                row = r
                break
        if not row:
            return None

        # 2️ Inspect the Yes and No cells individually
        yes_checked = no_checked = None
        for cell in row.find_all("td"):
            txt = cell.get_text(" ", strip=True).lower()
            img = cell.find("img", src=re.compile(r"radio"))
            if not img:
                continue
            checked = "radio-checked" in img["src"]
            if txt.startswith("yes"):
                yes_checked = checked
            elif txt.startswith("no"):
                no_checked = checked

        if yes_checked is True and no_checked is False:
            return True
        if yes_checked is False and no_checked is True:
            return False
        return None  # ambiguous / malformed'''
