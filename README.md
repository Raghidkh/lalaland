# Adma real estate scraper

Scrapes all property listings located in **Adma (Keserwan, Lebanon)** from

- **Confidence Real Estate** — confidencerealestate.com (via the site's own JSON API)
- **JSK Real Estate** — jskre.com (HTML pages)
- **OLX Lebanon** — olx.com.lb (its public search API; Properties category only — no cars, furniture etc.)

…and produces an Excel report plus an interactive dashboard focused on **land, villas and apartments**.

## Quick start (Windows)

| Double-click | What it does |
|---|---|
| `1_scrape.bat` | Scrapes all 3 sites (~1 min) → `output/Adma_Real_Estate.xlsx`, `output/adma_listings.csv` and a history snapshot |
| `2_dashboard.bat` | Opens the interactive dashboard in your browser |

First time only, install the dependencies:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Manual commands:

```
.venv\Scripts\python scrape.py              # scrape + snapshot + build Excel
.venv\Scripts\python scrape.py --from-csv   # rebuild Excel only, no internet
.venv\Scripts\streamlit run dashboard.py    # dashboard (also has a Re-scrape button)
```

## The dashboard

- **🏠 Browse listings** — property cards like a real-estate portal: photo, price, USD/m², beds/baths/size,
  badges (For sale/rent, **NEW**, **PRICE ↓**), source and agent. Click a card to open the original listing.
  Sort by newest, price, price per m² or size; 24 per page.
- **Filters (sidebar)** — Buy/Rent, property type, source, price, size, price per m², bedrooms,
  keywords to include/exclude (searched in every field: title, description, source, ref, agent, phone…), and *Reset all filters*.
- **✕ Hide a listing** — the ✕ on a card (or the ✕ column in *Data table*) hides a listing you're not
  interested in. It disappears from every tab, total and the Excel report, and shows up in the **🙈 Hidden**
  tab, where you can restore it. Saved in `output/hidden_listings.csv`, so it stays hidden after re-scrapes.
- **Market overview, Land, Apartments** — charts and stats; **Changes & history**; **Sites compared**;
  **Data table** with CSV/Excel downloads.
- The look (colours, fonts) is set in `.streamlit/config.toml`.

## Research features (`research.py`)

- **Duplicates merged** — the same property posted several times (OLX reposts, several agencies, several
  sites) is grouped into one *property*: same type and size, plus a matching price and agent/title (plots and
  villas with an unusual size like 1,183 m² match even when agencies ask different prices). Sidebar toggle
  *Count each property once*; cards show "Listed 3× (JSK, OLX) · $1.2M–$1.75M".
- **Fair price / 💎 Deals** — every listing for sale is compared with the 15 most similar listings (type, size,
  bedrooms, sea view, terrace, garden, duplex, furnished, new build, gated/pool). Estimated value = their median
  price per m² × size → "18% below market". Bands: ±10% fair, 10–25% good/above, >25% great/high;
  >50% below = *Check details* (usually a data issue). The Deals tab shows the comparables behind each estimate.
- **💰 Investment** — rents normalised to per month; each apartment for sale gets an estimated rent from the 10
  most similar rentals → gross yield. Yield by bedrooms, a yield calculator (with costs/vacancy), top yields.
- All of this is based on **asking** prices — research signals, not valuations.

## What's in the Excel

| Sheet | Content |
|---|---|
| **Dashboard** | KPI tiles, summary by category, land price per m² by agency and by plot size, apartments by bedrooms, 4 charts |
| **Land** | Every land listing (sale first, cheapest per m² first) |
| **Villas** | Every villa/house listing |
| **Apartments** | Every apartment listing (sale first, cheapest per m² first) |
| **All Adma Listings** | Everything in Adma, incl. commercial, for context |
| **Changes** | What changed since the previous scrape: new, removed, price drops/increases |
| **History** | Every listing ever seen: first/last seen, still online?, first vs latest price |
| **Deals** | Each property vs similar listings: estimated value, % vs market, confidence |
| **Investment** | Rents and gross yield by bedrooms + highest estimated yields |

## History (new / removed / price changes)

Every scrape saves a snapshot in `output/snapshots/adma_YYYY-MM-DD_HHMM.csv`. Comparing snapshots shows:

- **New** — listing that wasn't there in the previous scrape
- **Removed** — listing no longer on the site: sold, rented, expired or withdrawn (the sites don't say which)
- **Price drop / increase** — same listing, new asking price

Each site is compared with its own last successful scrape, so if a site is down during a scrape it is
not reported as "everything removed" (its previous listings are kept in the report for that run).
Scrape regularly (e.g. once a week) to build up the history. To keep history online (Streamlit Cloud),
commit and push the `output/snapshots/` folder after scraping.

Each listing row has: agency, reference, category, the site's own type, sale/rent, title, price, area, USD/m²,
bedrooms, bathrooms, parking, status, furnished, payment type, agent + phone, publish date, views,
a link to the listing, the full description, and a **"Possibly also listed as"** column flagging land/villas
that seem to be listed on both sites (same exact area) so you can compare their asking prices.

## Notes

- **Category** comes from the listing title first, then the site's type, because agents often mis-file listings
  (e.g. penthouses under "House/Villa", land under "House"). The original site type is kept in its own column.
- **USD/m²** is computed only for listings for sale. Rent prices are as listed (monthly or yearly — see "Price as listed").
- Data is whatever the agencies publish; a few entries contain obvious typos (e.g. an apartment "for sale" at $1,500).
- If a site changes its layout, the matching file in `scrapers/` is the one to update.
# lalaland
