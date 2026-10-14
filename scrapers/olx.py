"""OLX Lebanon (olx.com.lb).

The website pages sit behind a bot challenge, but the site loads its listings from a
public read-only search API (search-prod.olx-dubizzle.com). We query that API for active
ads in the Properties category located in Adma - cars, furniture etc. are excluded.
"""
import json
from datetime import datetime, timezone
from urllib.parse import quote

from .common import categorize, finalize, make_session, parse_number

SEARCH_URL = "https://search-prod.olx-dubizzle.com/_msearch"
# Read-only credential shipped in olx.com.lb's own JavaScript; sent by every visitor's browser.
AUTH = "Basic cmVhZG9ubHk6N31zYihfRHJhZm1tS1FOOA=="
ADS_INDEX = "olx-lb-production-ads-en"
LOCATIONS_INDEX = "olx-lb-production-locations-en"
LOCATION_NAME = "adma"
PAGE_SIZE = 200

# Fallback category per OLX sub-category when the ad has no "Property Type" field.
SLUG_TYPES = {
    "land-for-sale": "Land", "land-for-rent": "Land",
    "chalet-for-sale": "Chalet", "chalet-for-rent": "Chalet",
    "commercial-for-sale": "Commercial", "commercial-for-rent": "Commercial",
    "buildings-multiple-units-for-sale": "Building",
    "rooms-for-rent": "Room", "vacation-rentals-and-weekend-getaways": "Vacation rental",
}


def _msearch(session, index, body):
    payload = json.dumps({"index": index}) + "\n" + json.dumps(body) + "\n"
    r = session.post(SEARCH_URL, data=payload.encode("utf-8"), timeout=60,
                     headers={"authorization": AUTH, "content-type": "application/x-ndjson"})
    r.raise_for_status()
    response = r.json()["responses"][0]
    if "error" in response:
        raise RuntimeError(f"OLX search error: {response['error']}")
    return response["hits"]


def _find_location_ids(session):
    hits = _msearch(session, LOCATIONS_INDEX, {"query": {"prefix": {"slug": LOCATION_NAME}}, "size": 20})
    return [h["_source"]["externalID"] for h in hits["hits"]
            if LOCATION_NAME in h["_source"]["name"].lower()]


def _fetch_ads(session, location_ids):
    query = {"bool": {"must": [
        {"terms": {"location.externalID": location_ids}},
        {"term": {"category.slug": "properties"}},
        {"term": {"state": "active"}},
    ]}}
    ads, start = [], 0
    while True:
        hits = _msearch(session, ADS_INDEX, {
            "query": query, "size": PAGE_SIZE, "from": start, "sort": [{"id": "asc"}]})
        ads.extend(h["_source"] for h in hits["hits"])
        start += PAGE_SIZE
        if start >= hits["total"]["value"] or not hits["hits"]:
            return ads


def _fields(ad):
    """{'Property Type': 'Apartment', 'Bedrooms': '3', ...} from OLX's display labels."""
    out = {}
    for f in ad.get("formattedExtraFields") or []:
        value = f.get("formattedValue")
        out[f.get("name")] = ", ".join(value) if isinstance(value, list) else value
    return out


def _to_row(ad):
    extra, fields = ad.get("extraFields") or {}, _fields(ad)
    slug = ad["category"][-1]["slug"]
    is_rent = "for-rent" in slug or slug.startswith("vacation")
    ptype = fields.get("Property Type") or SLUG_TYPES.get(slug, ad["category"][-1]["name"])

    price = parse_number(extra.get("price")) if extra.get("price_type", "price") == "price" else None
    period = fields.get("Rental duration")
    if price:
        price_label = f"USD {price:,.0f}" + (f" / {period}" if is_rent and period else "")
    else:
        price_label = "Negotiable" if extra.get("price_type") == "arranged" else None

    agency = (ad.get("agency") or {}).get("name")
    seller = (ad.get("contactInfo") or {}).get("name")
    cover = (ad.get("coverPhoto") or {}).get("id")
    created = ad.get("createdAt")

    return finalize({
        "listing_id": f"OLX:{ad['externalID']}",
        "source": "OLX",
        "ref": ad["externalID"],
        "title": ad.get("title"),
        "listing_type": "Rent" if is_rent else "Sale",
        "category": categorize(ptype, ad.get("title")),
        "property_type": ptype,
        "price_usd": float(price) if price else None,
        "price_label": price_label,
        "area_m2": parse_number(extra.get("ft")),
        "bedrooms": _int(extra.get("rooms")),
        "bathrooms": _int(extra.get("bathrooms")),
        "location": ", ".join(loc["name"] for loc in reversed(ad.get("location") or [])),
        "status": fields.get("Condition"),
        "furnished": fields.get("Furnished"),
        "payment_type": fields.get("Payment method"),
        "agent": agency or seller or fields.get("Seller Type"),
        "publish_date": datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m-%d") if created else None,
        "description": ad.get("description"),
        "image_url": f"https://images-prod.olx-dubizzle.com/thumbnails/{cover}-400x300.webp" if cover else None,
        "url": f"https://www.olx.com.lb/ad/{quote(ad.get('slug') or 'ad')}-ID{ad['externalID']}.html",
    })


def _int(value):
    try:
        return int(str(value).rstrip("+"))
    except (TypeError, ValueError):
        return None


def scrape(log=print) -> list[dict]:
    session = make_session()
    session.headers.update({"Origin": "https://www.olx.com.lb", "Referer": "https://www.olx.com.lb/"})
    location_ids = _find_location_ids(session)
    log(f"[olx] Adma location ids: {location_ids}")
    if not location_ids:
        raise RuntimeError("Adma not found in OLX locations")
    ads = _fetch_ads(session, location_ids)
    rows = [_to_row(ad) for ad in ads]
    log(f"[olx] done: {len(rows)} property ads in Adma")
    return rows
