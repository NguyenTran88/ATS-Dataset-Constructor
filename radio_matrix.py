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
        """Return True (Yes), False (No), or None based on checked radio button and nearby text."""
        key = self._normalise(key_text)

        for label, row in self.rows:
            if key == label or (key in label and re.match(r"^[a-z]\.", label)):
                img = row.find("img", src=lambda s: s and "radio-checked" in s)
                if not img:
                    return None

                # Walk forward to find sibling text
                node = img.next_sibling
                while node and (not isinstance(node, str) or not node.strip()):
                    node = node.next_sibling

                if node:
                    return node.strip().lower() == "yes"
                return None

        return None
