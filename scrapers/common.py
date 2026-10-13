"""Shared helpers: HTTP session, number parsing, category normalisation, output schema."""
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# Column order of the final dataset (every scraper returns dicts with these keys).
COLUMNS = [
    "source", "ref", "title", "listing_type", "category", "property_type",
    "price_usd", "price_label", "area_m2", "price_per_m2",
    "bedrooms", "bathrooms", "parking",
    "location", "status", "furnished", "payment_type",
    "agent", "agent_phone", "publish_date", "views",
    "description", "image_url", "url",
]


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    retry = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=10))
    return s


def parse_number(text):
    """'$1,200,000' -> 1200000.0, '1307 m²' -> 1307.0, anything unparseable -> None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text) if text else None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(text))
    if not m:
        return None
    value = float(m.group(0).replace(",", ""))
    return value or None


# Order matters: a title saying "apartment in a villa" is an apartment, "land ... villa area" is land.
_CATEGORY_RULES = [
    ("Land", ("land", "plot", "lands")),
    ("Apartment", ("apartment", "duplex", "triplex", "penthouse", "studio", "loft", "flat")),
    ("Villa", ("villa", "house", "chalet", "cabin", "townhouse", "mansion")),
    ("Commercial", ("commercial", "office", "shop", "showroom", "warehouse", "building",
                    "store", "restaurant", "hotel", "industrial", "clinic")),
]


def categorize(property_type: str, title: str = "") -> str:
    """Map a listing onto Land / Villa / Apartment / Commercial / Other.

    The title is checked first because agents often pick a generic type on the site
    (e.g. a penthouse filed under "House/Villa", or land filed under "House");
    the site's own type is the fallback.
    """
    for text in (title or "", property_type or ""):
        words = set(re.findall(r"[a-z]+", text.lower()))
        for category, keys in _CATEGORY_RULES:
            if words & set(keys):
                return category
    return "Other"


def finalize(row: dict) -> dict:
    """Fill derived fields and make sure every column exists."""
    row = {col: row.get(col) for col in COLUMNS}
    price, area = row["price_usd"], row["area_m2"]
    if price and area and row["listing_type"] == "Sale":
        row["price_per_m2"] = round(price / area, 1)
    for key in ("title", "description", "ref", "location", "property_type", "status", "furnished"):
        if isinstance(row[key], str):
            row[key] = row[key].strip() or None
    return row
