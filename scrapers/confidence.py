"""Confidence Real Estate (confidencerealestate.com).

The site is a React app backed by a public JSON API (api.mearealestate.com). We call the
same endpoints the browser does: a paged search filtered on the Adma area, then one
detail request per listing for description, agent, status, etc.
"""
from concurrent.futures import ThreadPoolExecutor

from .common import categorize, finalize, make_session

API = "https://api.mearealestate.com/api"
# Public key shipped in the site's own JavaScript bundle; sent by every visitor's browser.
API_KEY = "46SyX$tm=hR*k*hUHL9dVyqswy3E$3zhS9HD2#xD6Gex+pM=C9Kb#2b%3%@7LD45"
ADMA_AREA_NAME = "adma"  # matched against the site's location tree ("Adma w Dafnah")
PAGE_SIZE = 50


def _find_adma_area_ids(session) -> list[int]:
    r = session.get(f"{API}/Web/Properties/Filters", params={"Lang": "en"}, timeout=30)
    r.raise_for_status()
    ids = []

    def walk(nodes):
        for node in nodes or []:
            if ADMA_AREA_NAME in (node.get("Name") or "").lower():
                ids.append(node["Id"])
            walk(node.get("Children"))

    walk(r.json()["content"]["LocationsTree"])
    return ids


def _search(session, area_ids):
    page, results = 0, []
    while True:
        body = {
            "SelectedAreaUnitId": 1, "SelectedCurrencyId": 2, "AdTypesIds": [],
            "Featured": False, "Premium": False, "SearchTerm": "", "AgentId": 0,
            "Rooms": 0, "CountryId": None, "CityId": None, "AreaIds": area_ids,
            "Amenities": [], "PriceFrom": 0, "PriceTo": 0, "AreaFrom": 0, "AreaTo": 0,
            "Pager": {"PageNumber": page, "PageSize": PAGE_SIZE},
        }
        r = session.post(f"{API}/Web/v2/Properties/All", params={"Lang": "en"}, json=body, timeout=30)
        r.raise_for_status()
        content = r.json()["content"]
        results.extend(content.get("Data") or [])
        paging = content.get("PagingInfo") or {}
        if not paging.get("HasNext"):
            return results
        page += 1


def _details(session, prop_id):
    try:
        r = session.get(f"{API}/Web/Properties", params={"Lang": "en", "Id": prop_id}, timeout=30)
        r.raise_for_status()
        return r.json().get("content") or {}
    except Exception as exc:  # keep the summary row even if details fail
        print(f"  [confidence] details failed for {prop_id}: {exc}")
        return {}


def scrape(log=print) -> list[dict]:
    session = make_session()
    session.headers.update({"ApiKey": API_KEY, "Origin": "https://confidencerealestate.com"})

    area_ids = _find_adma_area_ids(session)
    log(f"[confidence] Adma area ids: {area_ids}")
    summaries = _search(session, area_ids)
    log(f"[confidence] {len(summaries)} listings found, fetching details...")

    with ThreadPoolExecutor(max_workers=6) as pool:
        details = list(pool.map(lambda p: _details(session, p["Id"]), summaries))

    rows = []
    for s, d in zip(summaries, details):
        agent = d.get("Agent") or {}
        ptype = d.get("Type") or s.get("Type")
        title = d.get("Name") or s.get("Name")
        rows.append(finalize({
            "listing_id": f"Confidence:{s['Id']}",
            "source": "Confidence",
            "ref": (d.get("Reference") or s.get("Reference") or "").strip().lstrip("#"),
            "title": title,
            "listing_type": "Rent" if (s.get("BusinessTypeName") or "").lower().startswith("rent") else "Sale",
            "category": categorize(ptype, title),
            "property_type": ptype,
            "price_usd": s.get("Price") or None,
            "price_label": s.get("Pricelbl"),
            "area_m2": s.get("Area") or None,
            "bedrooms": s.get("NumberOfBedrooms"),
            "bathrooms": s.get("NumberOfBathrooms"),
            "parking": s.get("NumberOfParkingSpaces"),
            "location": ", ".join(x for x in (s.get("AreaName"), s.get("City"), s.get("Country")) if x),
            "status": d.get("Status"),
            "furnished": d.get("Furnished"),
            "payment_type": d.get("PaymentType"),
            "agent": agent.get("FullName"),
            "agent_phone": agent.get("FullNumber"),
            "publish_date": (s.get("PublishDate") or "")[:10] or None,
            "views": s.get("NumberOfViews"),
            "description": d.get("Description"),
            "image_url": s.get("ImgUrl"),
            "url": d.get("ShareURL") or f"https://confidencerealestate.com/property/{s['Id']}",
        }))
    log(f"[confidence] done: {len(rows)} rows")
    return rows
