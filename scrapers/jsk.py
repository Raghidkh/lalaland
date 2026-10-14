"""JSK Real Estate (jskre.com).

Server-rendered HTML. The site has location landing pages such as
/listings/for-sale-in-adma-kesrouane-lebanon?page=N; we crawl those for property links,
then parse each property page.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from .common import categorize, finalize, make_session, parse_number

BASE = "https://www.jskre.com"
LOCATION_SLUG = "adma-kesrouane-lebanon"
LISTING_TYPES = {
    "for-sale": "Sale",
    "for-rent": "Rent",
    "for-seasonal-rent": "Rent",
}
MAX_PAGES = 60  # safety stop


def _collect_links(session, slug, log):
    links, page = [], 1
    while page <= MAX_PAGES:
        url = f"{BASE}/listings/{slug}-in-{LOCATION_SLUG}?page={page}"
        html = session.get(url, timeout=30).text
        found = re.findall(r'href="(/properties/[^"#?]+)"', html)
        new = [l for l in dict.fromkeys(found) if l not in links]
        if not new:
            break
        links.extend(new)
        page += 1
    log(f"[jsk] {slug}: {len(links)} property links")
    return links


def _text(el):
    return el.get_text(" ", strip=True) if el else None


def _parse_property(session, path, listing_type):
    url = BASE + path
    try:
        html = session.get(url, timeout=30).text
    except Exception as exc:
        print(f"  [jsk] failed {url}: {exc}")
        return None
    soup = BeautifulSoup(html, "lxml")

    ref_el = soup.find("address", string=re.compile(r"Ref:"))
    if not ref_el:
        return None
    block = ref_el.find_parent("div")  # the summary block: price, type, facts, title, address

    price_el = block.find("p", class_=re.compile(r"text-4xl"))
    price_label = _text(price_el)
    facts = block.find("div", class_=re.compile(r"text-\[#595959\]"))
    ptype = _text(facts.find("div")) if facts else None

    def fact(alt):
        img = facts.find("img", alt=alt) if facts else None
        return parse_number(_text(img.parent)) if img else None

    title_el = block.find("p", class_=re.compile(r"mb-4"))
    loc_el = block.find("address", class_=re.compile(r"flex"))
    location = _text(loc_el)

    m = re.search(r'let description = ("(?:[^"\\]|\\.)*");', html)
    description = json.loads(m.group(1)) if m else None
    og = soup.find("meta", property="og:image")
    title = _text(title_el)

    ref = (_text(ref_el) or "").replace("Ref:", "").strip()
    return finalize({
        "listing_id": f"JSK:{ref}",
        "source": "JSK",
        "ref": ref,
        "title": title,
        "listing_type": listing_type,
        "category": categorize(ptype, title),
        "property_type": ptype,
        "price_usd": parse_number(price_label),
        "price_label": price_label,
        "area_m2": fact("Area"),
        "bedrooms": fact("Bedrooms"),
        "bathrooms": fact("Bathrooms"),
        "location": location,
        "description": description,
        "image_url": og.get("content") if og else None,
        "url": url,
        "agent": "JSK Real Estate",
        "agent_phone": "+961 71 81 81 00",
    })


def scrape(log=print) -> list[dict]:
    session = make_session()
    jobs = []
    seen = set()
    for slug, listing_type in LISTING_TYPES.items():
        for path in _collect_links(session, slug, log):
            if path not in seen:
                seen.add(path)
                jobs.append((path, listing_type))

    log(f"[jsk] parsing {len(jobs)} property pages...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda j: _parse_property(session, *j), jobs))

    # Landing pages can pad with nearby listings - keep only those actually in Adma.
    rows = [r for r in rows if r and "adma" in ((r["location"] or "") + (r["title"] or "")).lower()]
    log(f"[jsk] done: {len(rows)} rows in Adma")
    return rows
