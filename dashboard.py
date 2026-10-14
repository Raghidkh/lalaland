"""Adma Property Explorer — interactive dashboard for the scraped Adma listings.

Run:  streamlit run dashboard.py
"""
import html
import math
import re

import altair as alt
import pandas as pd
import streamlit as st

import hidden
import history
import research
from report import BEDROOM_LABELS, SIZE_BANDS, SIZE_LABELS, apartments_by_bedrooms, bedroom_band
from scrape import CSV_PATH, XLSX_PATH, run

st.set_page_config(page_title="Adma Property Explorer", page_icon="🏡", layout="wide")

# Fixed colour per entity (reference palette order) so filtering never repaints survivors.
SOURCES = ["Confidence", "JSK", "OLX"]
SOURCE_COLORS = {"Confidence": "#2a78d6", "JSK": "#eb6834", "OLX": "#1baf7a"}
SOURCE_SCALE = alt.Scale(domain=SOURCES, range=list(SOURCE_COLORS.values()))
CATEGORIES = ["Land", "Villa", "Apartment", "Commercial", "Other"]
USD = "$,.0f"
PAGE_SIZE = 24
SORTS = {
    "Newest first": ("publish_date", False),
    "Price: low to high": ("price_usd", True),
    "Price: high to low": ("price_usd", False),
    "Price per m²: low to high": ("price_per_m2", True),
    "Size: largest first": ("area_m2", False),
    "Best deal first": ("value_gap_pct", True),
    "Highest rental yield": ("gross_yield", False),
}
DEAL_ORDER = ["Great deal", "Good price", "Fair price", "Above market", "High price", "Check details"]

CSS = """
<style>
.block-container {padding-top: 1.4rem; max-width: 1440px;}
.hero {background: linear-gradient(120deg, #0b3d3a 0%, #0f6e63 55%, #1f8f7f 100%); border-radius: 18px;
       padding: 30px 34px 26px; color: #fff; margin-bottom: 18px; box-shadow: 0 6px 24px rgba(15,110,99,.18);}
.hero .eyebrow {text-transform: uppercase; letter-spacing: .14em; font-size: .72rem; opacity: .8; font-weight: 600;}
.hero h1 {color: #fff; font-size: 2.15rem; line-height: 1.15; margin: 6px 0 6px; padding: 0; font-weight: 750;}
.hero p {margin: 0; opacity: .88; font-size: 1rem;}
.hero .chips {margin-top: 14px;}
.hero .chips span {display: inline-block; background: rgba(255,255,255,.13); border: 1px solid rgba(255,255,255,.28);
       border-radius: 999px; padding: 4px 12px; margin: 0 8px 6px 0; font-size: .82rem;}
[data-testid="stMetric"] {background: #fff; border: 1px solid #e7e6e1; border-radius: 14px; padding: 14px 18px;
       box-shadow: 0 1px 2px rgba(0,0,0,.04);}
[data-testid="stMetricLabel"] p {color: #6b6a65; font-size: .82rem;}
[data-testid="stMetricValue"] {font-size: 1.55rem; font-weight: 750;}
[data-testid="stSidebar"] {border-right: 1px solid #e7e6e1;}
.side-brand {font-size: 1.15rem; font-weight: 750; color: #0f6e63; margin: -8px 0 6px;}
.side-h {text-transform: uppercase; letter-spacing: .1em; font-size: .7rem; font-weight: 700; color: #8a8986;
       margin: 18px 0 2px;}
.results-h {font-size: 1.35rem; font-weight: 750; margin: 4px 0 0;}
.results-sub {color: #6b6a65; font-size: .88rem; margin-bottom: 6px;}
.grid {display: grid; grid-template-columns: repeat(auto-fill, minmax(275px, 1fr)); gap: 18px; margin: 6px 0 16px;}
a.card {background: #fff; border: 1px solid #e7e6e1; border-radius: 14px; overflow: hidden; display: flex;
       flex-direction: column; text-decoration: none !important; color: #1b1b1a !important;
       transition: box-shadow .15s ease, transform .15s ease;}
a.card:hover {box-shadow: 0 10px 28px rgba(0,0,0,.10); transform: translateY(-2px);}
.ph {position: relative; height: 185px; background: #e4e9e7 center / cover no-repeat;}
.ph .noimg {position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
       color: #9aa5a1; font-size: .8rem; z-index: 0;}
.ph img {position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; border: 0;
       margin: 0; max-width: none;}
.badges {position: absolute; top: 10px; left: 10px; display: flex; gap: 6px; flex-wrap: wrap; z-index: 2;}
.b {font-size: .68rem; font-weight: 750; letter-spacing: .03em; padding: 3px 8px; border-radius: 6px;
       background: rgba(255,255,255,.95); color: #1b1b1a; text-transform: uppercase;}
.b.new {background: #0f6e63; color: #fff;}
.b.drop {background: #b9471c; color: #fff;}
.prow {display: flex; align-items: center; justify-content: space-between; gap: 8px;}
.deal {font-size: .7rem; font-weight: 700; padding: 3px 8px; border-radius: 999px; white-space: nowrap;}
.deal.good {background: #e3f4ef; color: #0b5c52;} .deal.fair {background: #f0efeb; color: #52514e;}
.deal.high {background: #fbeee6; color: #9a3d15;} .deal.check {background: #fff4d6; color: #7a5600;}
.dup {font-size: .74rem; color: #0f6e63; background: #eef7f5; border-radius: 6px; padding: 3px 7px;}
.src {position: absolute; bottom: 10px; left: 10px; z-index: 2; font-size: .72rem; font-weight: 650; color: #fff;
       background: rgba(20,20,20,.62); padding: 3px 9px 3px 7px; border-radius: 999px; display: flex;
       align-items: center; gap: 6px;}
.src i {width: 8px; height: 8px; border-radius: 50%; display: inline-block;}
.cbody {padding: 12px 15px 13px; display: flex; flex-direction: column; gap: 5px; flex: 1;}
.price {font-size: 1.28rem; font-weight: 800; letter-spacing: -.01em;}
.price small {font-weight: 500; color: #6b6a65; font-size: .8rem; margin-left: 2px;}
.ppm {color: #6b6a65; font-size: .78rem; margin-top: -3px;}
.ttl {font-weight: 600; font-size: .9rem; line-height: 1.32; display: -webkit-box; -webkit-line-clamp: 2;
       -webkit-box-orient: vertical; overflow: hidden; min-height: 2.4em;}
.loc {color: #6b6a65; font-size: .78rem; display: flex; align-items: center; gap: 4px;}
.facts {display: flex; gap: 16px; font-size: .84rem; color: #3d3c38; border-top: 1px solid #efeee9;
       padding-top: 9px; margin-top: auto;}
.facts span {display: flex; align-items: center; gap: 5px;}
.foot {display: flex; justify-content: space-between; font-size: .72rem; color: #8a8986; gap: 8px;}
.foot span:first-child {overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
@media (max-width: 640px) {
  .hero {padding: 22px 20px 16px;} .hero h1 {font-size: 1.6rem;}
  [data-testid="stMetric"] {padding: 8px 14px;} [data-testid="stMetricValue"] {font-size: 1.2rem;}
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {gap: 8px;}
}
[class*="st-key-card_"] {position: relative; gap: 0 !important;}
[class*="st-key-hide_"] {position: absolute; top: 9px; right: 9px; z-index: 5; width: auto !important;}
[class*="st-key-hide_"] button {min-height: 0; height: 30px; width: 30px; padding: 0; border-radius: 50%;
       background: rgba(255,255,255,.94); border: 1px solid rgba(0,0,0,.12); color: #3d3c38; line-height: 1;
       box-shadow: 0 1px 4px rgba(0,0,0,.18);}
[class*="st-key-hide_"] button:hover {background: #b9471c; border-color: #b9471c; color: #fff;}
.cardwrap {margin-bottom: 14px;}
svg.i {width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round;
       stroke-linejoin: round; flex-shrink: 0;}
</style>
"""

ICONS = {
    "bed": '<svg class="i" viewBox="0 0 24 24"><path d="M3 19V6M3 14h18v5M21 14v-2a3 3 0 0 0-3-3h-7v5"/><circle cx="7" cy="11" r="1.7"/></svg>',
    "bath": '<svg class="i" viewBox="0 0 24 24"><path d="M4 12h16v2a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM6 12V6a2 2 0 0 1 4 0M7 19l-1 2M17 19l1 2"/></svg>',
    "area": '<svg class="i" viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
    "pin": '<svg class="i" viewBox="0 0 24 24"><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.4"/></svg>',
}
COLUMNS_SEARCHED = ["listing_id", "source", "ref", "title", "listing_type", "category", "property_type",
                    "price_usd", "price_label", "area_m2", "price_per_m2", "bedrooms", "bathrooms", "parking",
                    "location", "status", "furnished", "payment_type", "agent", "agent_phone", "publish_date",
                    "views", "description", "url", "also_listed_on", "deal_label", "group_sources"]
RENT_PERIODS = {"monthly": "month", "month": "month", "yearly": "year", "year": "year", "daily": "day", "weekly": "week"}


@st.cache_data
def load(mtime: float) -> pd.DataFrame:  # mtime busts the cache after a re-scrape
    df = history.add_listing_ids(pd.read_csv(CSV_PATH))
    df["publish_date"] = pd.to_datetime(df["publish_date"], errors="coerce")
    # OLX only serves newer thumbnails as .webp (older scrapes saved .jpeg links)
    is_olx = df["image_url"].str.contains("olx-dubizzle.com/thumbnails/", na=False, regex=False)
    df.loc[is_olx, "image_url"] = df.loc[is_olx, "image_url"].str.replace("-400x300.jpeg", "-400x300.webp", regex=False)
    df = research.enrich(df)  # duplicates, fair price, rent & yield estimates
    # One lower-case text per listing with every field (source, ref, agent, price, description, …) for keywords
    searchable = df[[c for c in df.columns if c in COLUMNS_SEARCHED]]
    as_text = searchable.apply(lambda col: col.map(lambda v: "" if pd.isna(v) else str(v)))
    df["_search"] = as_text.agg(" ".join, axis=1).str.lower()
    return df


@st.cache_data
def load_history(snapshot_names: tuple):  # cache key = the list of snapshot files
    return history.latest_changes(), history.listing_history(), history.inventory_over_time()


def money(v):
    return "—" if pd.isna(v) else f"${v:,.0f}"


def esc(v):
    """HTML-escape, and escape $ so Streamlit's markdown never reads prices as LaTeX."""
    return html.escape(str(v)).replace("$", "&#36;")


def card(r, badges: dict) -> str:
    """One listing card (a link to the original listing)."""
    if pd.isna(r.price_usd):
        price = '<div class="price">Price on request</div>'
    else:
        suffix = ""
        if r.listing_type == "Rent" and isinstance(r.price_label, str) and "/" in r.price_label:
            period = r.price_label.split("/", 1)[1].strip().lower()
            suffix = f"<small>/ {RENT_PERIODS.get(period, period)}</small>" if period and period != "any" else ""
        price = f'<div class="price">&#36;{r.price_usd:,.0f}{suffix}</div>'
    if isinstance(r.deal_label, str):
        gap = r.value_gap_pct
        if r.deal_label in ("Great deal", "Good price"):
            pill = f'<span class="deal good">{abs(gap):.0f}% below market</span>'
        elif r.deal_label in ("Above market", "High price"):
            pill = f'<span class="deal high">{gap:.0f}% above market</span>'
        elif r.deal_label == "Fair price":
            pill = '<span class="deal fair">Fair price</span>'
        else:
            pill = '<span class="deal check">Check details</span>'
        price = f'<div class="prow">{price}{pill}</div>'
    ppm = f'<div class="ppm">&#36;{r.price_per_m2:,.0f} / m²</div>' if pd.notna(r.price_per_m2) else '<div class="ppm">&nbsp;</div>'

    tags = [f'<span class="b">{"For rent" if r.listing_type == "Rent" else "For sale"}</span>',
            f'<span class="b">{esc(r.category)}</span>']
    kind, value = badges.get(r.listing_id, (None, None))
    if kind == "New":
        tags.insert(0, '<span class="b new">New</span>')
    elif kind == "Price drop":
        tags.insert(0, f'<span class="b drop">Price ↓ {abs(value):.0f}%</span>')

    facts = []
    if pd.notna(r.bedrooms):
        facts.append(f'<span>{ICONS["bed"]}{r.bedrooms:.0f} bd</span>')
    if pd.notna(r.bathrooms):
        facts.append(f'<span>{ICONS["bath"]}{r.bathrooms:.0f} ba</span>')
    if pd.notna(r.area_m2):
        facts.append(f'<span>{ICONS["area"]}{r.area_m2:,.0f} m²</span>')

    listed = ""
    if pd.notna(r.publish_date):
        days = (pd.Timestamp.now().normalize() - r.publish_date.normalize()).days
        listed = "Listed today" if days <= 0 else f"Listed {days} day{'s' * (days > 1)} ago" if days < 60 \
            else f"Listed {r.publish_date:%b %Y}"

    img = f'<img src="{esc(r.image_url)}" alt="" loading="lazy">' if isinstance(r.image_url, str) else ""
    location = str(r.location).split(",")[0] if isinstance(r.location, str) else "Adma"
    dup = ""
    if r.listings_in_group > 1:
        spread = ""
        if pd.notna(r.group_min_price) and r.group_max_price > r.group_min_price:
            spread = f" · &#36;{r.group_min_price:,.0f}–&#36;{r.group_max_price:,.0f}"
        dup = f'<div class="dup">🔁 Listed {r.listings_in_group:.0f}× ({esc(r.group_sources)}){spread}</div>'
    return (
        f'<a class="card" href="{esc(r.url)}" target="_blank" rel="noopener">'
        f'<div class="ph"><div class="noimg">No photo</div>{img}<div class="badges">{"".join(tags)}</div>'
        f'<div class="src"><i style="background:{SOURCE_COLORS.get(r.source, "#999")}"></i>{esc(r.source)}</div></div>'
        f'<div class="cbody">{price}{ppm}<div class="ttl">{esc(r.title)}</div>'
        f'<div class="loc">{ICONS["pin"]}{esc(location)}, Keserwan</div>'
        f'{dup}'
        f'<div class="facts">{"".join(facts) or "<span>&nbsp;</span>"}</div>'
        f'<div class="foot"><span>{esc(r.agent) if isinstance(r.agent, str) else ""}</span><span>{listed}</span></div>'
        f'</div></a>'
    )


def reset_filters():
    for key in list(st.session_state):
        if key.startswith("f_"):
            del st.session_state[key]


st.markdown(CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------- data + sidebar

if not CSV_PATH.exists():
    st.info("No data yet — scraping all three websites now (about a minute)…")
    with st.status("Scraping confidencerealestate.com, jskre.com and olx.com.lb…", expanded=True):
        run(log=st.write)
    st.rerun()

df_all = load(CSV_PATH.stat().st_mtime)
hidden_ids = hidden.ids()
df = df_all[~df_all.listing_id.isin(hidden_ids)]  # everything below works on visible listings only
latest, hist_all, inventory = load_history(tuple(p.name for _, p in history.list_snapshots()))
badges = {}
if latest is not None:
    for e in latest[0].itertuples():
        if e.change in ("New", "Price drop"):
            badges[e.listing_id] = (e.change, e.price_change_pct)

with st.sidebar:
    st.markdown('<div class="side-brand">🏡 Adma Property Explorer</div>', unsafe_allow_html=True)
    purpose = st.segmented_control("I want to", ["Buy", "Rent"], default="Buy", key="f_purpose", width="stretch") or "Buy"
    listing_type = "Sale" if purpose == "Buy" else "Rent"
    categories = st.pills("Property type", CATEGORIES, selection_mode="multi",
                          default=["Land", "Villa", "Apartment"], key="f_cats")
    sources = st.pills("Source", SOURCES, selection_mode="multi", default=SOURCES, key="f_srcs")
    merge = st.toggle("Count each property once", value=True, key="f_merge",
                      help="The same property is often posted several times (reposts on OLX, several agencies, "
                           "several sites). When on, each property appears once — its cheapest listing — and "
                           "the card says where else it is listed.")
    base = df[(df.listing_type == listing_type) & df.category.isin(categories) & df.source.isin(sources)]
    if merge:
        base = base[base.is_primary]

    st.markdown('<div class="side-h">Price & size</div>', unsafe_allow_html=True)
    prices = base.price_usd.dropna()
    if len(prices) > 1 and prices.min() < prices.max():
        lo, hi = st.slider("Price (USD)", float(prices.min()), float(prices.max()),
                           (float(prices.min()), float(prices.max())), step=10000.0 if listing_type == "Sale" else 100.0,
                           format="$%,d", key=f"f_price_{listing_type}")
        base = base[base.price_usd.isna() | base.price_usd.between(lo, hi)]
    areas = base.area_m2.dropna()
    if len(areas) > 1 and areas.min() < areas.max():
        alo, ahi = st.slider("Area (m²)", float(areas.min()), float(areas.max()),
                             (float(areas.min()), float(areas.max())), step=10.0, format="%,d m²", key="f_area")
        base = base[base.area_m2.isna() | base.area_m2.between(alo, ahi)]
    ppm = base.price_per_m2.dropna()
    if listing_type == "Sale" and len(ppm) > 1 and ppm.min() < ppm.max():
        full = (float(ppm.min()), float(ppm.max()))
        plo, phi = st.slider("Price per m² (USD)", *full, full, step=10.0, format="$%,d", key="f_ppm",
                             help="Listings without a price or area have no price per m²; "
                                  "they are hidden once you narrow this range.")
        if (plo, phi) != full:
            base = base[base.price_per_m2.between(plo, phi)]
    if listing_type == "Sale":
        deal_pick = st.pills("Price vs market", DEAL_ORDER, selection_mode="multi", key="f_deal",
                             help="Compared with the median price per m² of the 15 most similar listings "
                                  "(see the 💎 Deals tab).")
        if deal_pick:
            base = base[base.deal_label.isin(deal_pick)]
    beds = st.pills("Bedrooms", ["1", "2", "3", "4", "5+"], selection_mode="multi", key="f_beds",
                    help="Only applies to listings that state a bedroom count; land is unaffected.")
    if beds:
        band = base.bedrooms.map(lambda b: None if pd.isna(b) else "5+" if b >= 5 else str(max(1, int(b))))
        base = base[band.isna() | band.isin(beds)]

    st.markdown('<div class="side-h">Keywords</div>', unsafe_allow_html=True)
    include = st.multiselect("✅ Must contain", [], accept_new_options=True, key="f_inc",
                             placeholder="e.g. sea view, pool",
                             help="Type a word or phrase and press Enter — add as many as you like. Searches "
                                  "every field: title, description, source, ref, agent, phone, type, location, "
                                  "status, price, link…; not case-sensitive.")
    match_all = st.radio("Must contain…", ["All of the words", "Any of the words"], horizontal=True,
                         disabled=len(include) < 2, key="f_match") == "All of the words"
    exclude = st.multiselect("🚫 Must NOT contain", [], accept_new_options=True, key="f_exc",
                             placeholder="e.g. under construction")
    if include or exclude:
        text = base["_search"]
        has = {word: text.str.contains(word.strip().lower(), regex=False) for word in include + exclude}
        if include:
            hits = pd.concat([has[w] for w in include], axis=1)
            base = base[hits.all(axis=1) if match_all else hits.any(axis=1)]
        for word in exclude:
            base = base[~has[word].loc[base.index]]

    st.button("↺ Reset all filters", on_click=reset_filters, width="stretch")

    st.markdown('<div class="side-h">Data</div>', unsafe_allow_html=True)
    st.caption(f"Last updated {pd.to_datetime(df.scraped_at.iloc[0]):%d %b %Y, %H:%M} · "
               f"{len(history.list_snapshots())} scrape(s) in history")
    if st.button("🔄 Re-scrape all websites", width="stretch"):
        with st.status("Scraping confidencerealestate.com, jskre.com and olx.com.lb…", expanded=True) as status:
            run(log=st.write)
            status.update(label="Done — data refreshed", state="complete")
        st.cache_data.clear()
        st.rerun()

view = base

# ---------------------------------------------------------------- hero + KPIs

st.markdown(
    '<div class="hero"><div class="eyebrow">Keserwan · Lebanon</div>'
    '<h1>Property in Adma</h1>'
    '<p>Land, villas and apartments from Confidence Real Estate, JSK Real Estate and OLX — in one place.</p>'
    '<div class="chips">'
    f'<span>📍 Adma w Dafnah</span><span>🏷️ {len(df):,} listings · {int(df.is_primary.sum()):,} unique properties</span>'
    f'<span>🕒 Updated {pd.to_datetime(df.scraped_at.iloc[0]):%d %b %Y}</span>'
    f'<span>🔁 {len(history.list_snapshots())} scrape(s) of history</span>'
    '</div></div>',
    unsafe_allow_html=True)

new_in_view = sum(1 for i in view.listing_id if badges.get(i, (None,))[0] == "New")
k = st.columns(5)
k[0].metric("Listings", f"{len(view):,}")
k[1].metric("Median price" if listing_type == "Sale" else "Median rent", money(view.price_usd.median()))
k[2].metric("Median USD / m²", money(view.price_per_m2.median()) if listing_type == "Sale" else "n/a for rent")
k[3].metric("Median size", "—" if view.area_m2.dropna().empty else f"{view.area_m2.median():,.0f} m²")
k[4].metric("New since last scrape", f"{new_in_view:,}",
            help="Listings that appeared since each site's previous scrape (see Changes & history).")

if view.empty:
    st.warning("No listings match these filters — try widening them or click **Reset all filters**.")
    st.stop()

tooltip = [
    alt.Tooltip("title:N", title="Title"),
    alt.Tooltip("source:N", title="Source"),
    alt.Tooltip("ref:N", title="Ref"),
    alt.Tooltip("price_usd:Q", title="Price", format=USD),
    alt.Tooltip("area_m2:Q", title="Area m²", format=",.0f"),
    alt.Tooltip("price_per_m2:Q", title="USD/m²", format=USD),
]

tab_browse, tab_deals, tab_invest, tab_overview, tab_land, tab_apt, tab_hist, tab_compare, tab_table, tab_hidden = st.tabs(
    ["🏠 Browse listings", "💎 Deals", "💰 Investment", "📊 Market overview", "🌄 Land", "🏢 Apartments", "🕒 Changes & history",
     "🔁 Sites compared", "📋 Data table", f"🙈 Hidden ({len(hidden_ids)})"])

# ---------------------------------------------------------------- browse


def go_to(page):
    st.session_state.page = page


def key_of(listing_id) -> str:
    return re.sub(r"\W", "_", str(listing_id))


def hide_listing(listing_id):
    property_id = df_all.loc[df_all.listing_id == listing_id, "property_id"].iloc[0]
    hidden.hide(df_all[df_all.property_id == property_id])  # with all its duplicate listings
    st.toast("Listing hidden — restore it any time from the 🙈 Hidden tab", icon="🙈")


with tab_browse:
    head, sort_col = st.columns([3, 1], vertical_alignment="bottom")
    what = ", ".join(c.lower() + ("s" if c not in ("Land", "Commercial", "Other") else "") for c in categories)
    head.markdown(f'<div class="results-h">{len(view):,} properties {"for sale" if listing_type == "Sale" else "for rent"}'
                  f' in Adma</div><div class="results-sub">{esc(what.capitalize())} · '
                  f'{", ".join(sources)}</div>', unsafe_allow_html=True)
    sort = sort_col.selectbox("Sort by", list(SORTS), key="sort")
    col, ascending = SORTS[sort]
    ordered = view.sort_values(col, ascending=ascending, na_position="last")

    pages = max(1, math.ceil(len(ordered) / PAGE_SIZE))
    signature = hash((sort, tuple(ordered.listing_id)))
    if st.session_state.get("browse_sig") != signature:  # new results → back to page 1
        st.session_state.browse_sig, st.session_state.page = signature, 1
    page = min(st.session_state.get("page", 1), pages)
    chunk = ordered.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    rows = list(chunk.itertuples())
    for start in range(0, len(rows), 3):
        for column, r in zip(st.columns(3, gap="medium"), rows[start:start + 3]):
            with column.container(key=f"card_{key_of(r.listing_id)}"):
                st.markdown(f'<div class="cardwrap">{card(r, badges)}</div>', unsafe_allow_html=True)
                st.button("✕", key=f"hide_{key_of(r.listing_id)}", help="Hide this listing",
                          on_click=hide_listing, args=(r.listing_id,))

    prev_col, info_col, next_col = st.columns([1, 2, 1], vertical_alignment="center")
    prev_col.button("← Previous", on_click=go_to, args=(page - 1,), disabled=page <= 1, width="stretch")
    info_col.markdown(f'<div style="text-align:center;color:#6b6a65">Page {page} of {pages} · showing '
                      f'{(page - 1) * PAGE_SIZE + 1}–{(page - 1) * PAGE_SIZE + len(chunk)} of {len(ordered):,}</div>',
                      unsafe_allow_html=True)
    next_col.button("Next →", on_click=go_to, args=(page + 1,), disabled=page >= pages, width="stretch")

# ---------------------------------------------------------------- deals

with tab_deals:
    if listing_type != "Sale":
        st.info("Deals compare asking prices of properties **for sale** — switch the sidebar to **Buy**.")
    else:
        rated = view[view.value_gap_pct.notna()]
        st.markdown('<div class="results-h">Is the asking price fair?</div><div class="results-sub">Each listing is '
                    "compared with the <b>15 most similar listings</b> (same type; closest in size and bedrooms; "
                    "same features like sea view, terrace, garden, duplex, furnished, new build, gated/pool). "
                    "Its estimated market value = their median price per m² × its size. Duplicates of the same "
                    "property are never used as its own comparables. Asking prices ≠ sale prices: use this as a "
                    "research signal, not a valuation.</div>", unsafe_allow_html=True)
        counts = rated.deal_label.value_counts()
        k = st.columns(4)
        k[0].metric("Great deals", int(counts.get("Great deal", 0)), help="25–50% below the estimate")
        k[1].metric("Good prices", int(counts.get("Good price", 0)), help="10–25% below the estimate")
        k[2].metric("Above market", int(counts.get("Above market", 0) + counts.get("High price", 0)),
                    help="More than 10% above the estimate")
        k[3].metric("Check details", int(counts.get("Check details", 0)),
                    help="More than 50% below the estimate — usually a data issue (plot size counted as built "
                         "size, rent posted as sale, typo). Worth a look, but verify first.")

        st.subheader("Asking vs estimated price per m²")
        st.caption("Each dot is a listing. Below the dashed line = cheaper than similar listings. "
                   "Hover for details; click to open.")
        chart_data = rated[~rated.deal_label.isin(["Check details", "Check price"])]
        top = float(max(chart_data.price_per_m2.max(), chart_data.fair_price_m2.max())) if len(chart_data) else 1
        line = alt.Chart(pd.DataFrame({"x": [0, top], "y": [0, top]})).mark_line(
            strokeDash=[5, 4], color="#8a8986", strokeWidth=1.5).encode(x="x:Q", y="y:Q")
        dots = alt.Chart(chart_data).mark_circle(size=70, opacity=0.8, stroke="white", strokeWidth=1).encode(
            x=alt.X("fair_price_m2:Q", title="Estimated market price per m² (USD)", axis=alt.Axis(format="$,.0f")),
            y=alt.Y("price_per_m2:Q", title="Asking price per m² (USD)", axis=alt.Axis(format="$,.0f")),
            color=alt.Color("source:N", scale=SOURCE_SCALE, title="Source", legend=alt.Legend(orient="top")),
            href="url:N",
            tooltip=tooltip + [alt.Tooltip("fair_price_m2:Q", title="Est. USD/m²", format=USD),
                               alt.Tooltip("value_gap_pct:Q", title="vs market %", format="+.0f"),
                               alt.Tooltip("comps_n:Q", title="Comparables")],
        )
        st.altair_chart((line + dots).properties(height=420).interactive(), width="stretch")

        st.subheader("Ranked: cheapest relative to similar listings")
        show_checks = st.checkbox("Include listings flagged “Check details”", value=False)
        ranked = rated if show_checks else rated[~rated.deal_label.isin(["Check details", "Check price"])]
        ranked = ranked.sort_values("value_gap_pct")
        st.dataframe(ranked[["deal_label", "value_gap_pct", "title", "source", "category", "area_m2", "bedrooms",
                             "price_usd", "fair_value", "price_per_m2", "fair_price_m2", "comps_n",
                             "fair_confidence", "listings_in_group", "url"]],
                     hide_index=True, width="stretch", height=420, column_config={
            "deal_label": "Verdict", "title": "Title", "source": "Source", "category": "Category",
            "value_gap_pct": st.column_config.NumberColumn("vs market", format="%+.0f%%"),
            "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
            "bedrooms": st.column_config.NumberColumn("Beds", format="%d"),
            "price_usd": st.column_config.NumberColumn("Asking price", format="dollar", step=1),
            "fair_value": st.column_config.NumberColumn("Est. market value", format="dollar", step=1),
            "price_per_m2": st.column_config.NumberColumn("USD/m²", format="dollar", step=1),
            "fair_price_m2": st.column_config.NumberColumn("Est. USD/m²", format="dollar", step=1),
            "comps_n": st.column_config.NumberColumn("Comparables", format="%d"),
            "fair_confidence": st.column_config.TextColumn("Confidence", help="High: ≥10 comparables that agree "
                                                           "closely; Low: few or widely spread comparables"),
            "listings_in_group": st.column_config.NumberColumn("Times listed", format="%d"),
            "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
        })

        st.subheader("Why this estimate? See the comparables")
        if len(ranked):
            pick = st.selectbox(
                "Listing", ranked.listing_id.tolist(), key="deal_pick",
                format_func=lambda i: (lambda r: f"{r.value_gap_pct:+.0f}% · ${r.price_usd:,.0f} · {r.area_m2:,.0f} m² · "
                                                 f"{str(r.title)[:70]}")(ranked.set_index("listing_id").loc[i]))
            r = ranked.set_index("listing_id").loc[pick]
            comps = df_all[df_all.listing_id.isin(str(r.comps_ids).split("|"))]
            st.markdown(
                f"Asking **${r.price_usd:,.0f}** for **{r.area_m2:,.0f} m²** = **${r.price_per_m2:,.0f}/m²**. "
                f"The {len(comps)} most similar listings ask a median **${r.fair_price_m2:,.0f}/m²** → estimated "
                f"value **${r.fair_value:,.0f}** ({r.value_gap_pct:+.0f}%, confidence {str(r.fair_confidence).lower()}).".replace("$", "\\$"))
            st.dataframe(comps[["source", "title", "area_m2", "bedrooms", "price_usd", "price_per_m2", "url"]]
                         .sort_values("price_per_m2"), hide_index=True, width="stretch", column_config={
                "source": "Source", "title": "Title",
                "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
                "bedrooms": st.column_config.NumberColumn("Beds", format="%d"),
                "price_usd": st.column_config.NumberColumn("Asking price", format="dollar", step=1),
                "price_per_m2": st.column_config.NumberColumn("USD/m²", format="dollar", step=1),
                "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
            })

# ---------------------------------------------------------------- investment

with tab_invest:
    st.markdown('<div class="results-h">Rental yield & investment</div><div class="results-sub">Rents are '
                "normalised to per month (yearly rents ÷ 12). Each apartment for sale gets an estimated rent from "
                "the 10 most similar apartments for rent (rent per m² × its size). Gross yield = 12 × rent ÷ price, "
                "before costs, vacancy and taxes. Based on all Adma apartments (sidebar filters don't apply to the "
                "market table).</div>", unsafe_allow_html=True)
    by_beds = research.yield_by_bedrooms(df)
    for_sale = df[(df.category == "Apartment") & (df.listing_type == "Sale") & df.is_primary & df.gross_yield.notna()]
    k = st.columns(4)
    k[0].metric("Median gross yield", f"{for_sale.gross_yield.median():.1f}%" if len(for_sale) else "—",
                help="Estimated for every apartment for sale in Adma")
    k[1].metric("Median price-to-rent", f"{(100 / for_sale.gross_yield).median():.0f} years" if len(for_sale) else "—",
                help="Years of gross rent needed to pay the asking price")
    k[2].metric("Apartments for rent", f"{int((df.monthly_rent.notna() & (df.category == 'Apartment') & df.is_primary).sum())}")
    k[3].metric("Median rent / month", money(df[(df.category == "Apartment") & df.is_primary].monthly_rent.median()))

    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader("By bedrooms")
        st.dataframe(by_beds, hide_index=True, width="stretch", column_config={
            "Median price": st.column_config.NumberColumn(format="dollar", step=1),
            "Median rent / month": st.column_config.NumberColumn(format="dollar", step=1),
            "Gross yield %": st.column_config.NumberColumn(format="%.1f%%"),
            "Price-to-rent (years)": st.column_config.NumberColumn(format="%.0f"),
        })
        st.caption("Rows need at least 3 listings for sale and 3 for rent.")
    with c2:
        if len(by_beds):
            st.altair_chart(alt.Chart(by_beds).mark_bar(cornerRadiusEnd=4, color="#0f6e63").encode(
                x=alt.X("Bedrooms:N", sort=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Gross yield %:Q", title="Gross yield (%)"),
                tooltip=["Bedrooms", alt.Tooltip("Gross yield %:Q", format=".1f"),
                         alt.Tooltip("Median price:Q", format=USD), alt.Tooltip("Median rent / month:Q", format=USD)],
            ).properties(height=260), width="stretch")

    st.subheader("Yield calculator")
    options = view[(view.category == "Apartment") & (view.listing_type == "Sale") & view.area_m2.notna()]
    options = options.sort_values("gross_yield", ascending=False, na_position="last")
    choice = st.selectbox("Start from a listing (optional)", [None] + options.listing_id.tolist(), key="calc_pick",
                          format_func=lambda i: "— enter your own numbers —" if i is None else
                          (lambda r: f"${r.price_usd:,.0f} · {r.area_m2:,.0f} m² · {str(r.title)[:70]}")(
                              options.set_index("listing_id").loc[i]))
    picked = options.set_index("listing_id").loc[choice] if choice else None
    left, right = st.columns([2, 3])
    with left:
        price_in = st.number_input("Purchase price (USD)", min_value=10000, step=10000, key=f"calc_price_{choice}",
                                   value=int(picked.price_usd) if picked is not None and pd.notna(picked.price_usd) else 300000)
        area_in = st.number_input("Size (m²)", min_value=30, step=5, key=f"calc_area_{choice}",
                                  value=int(picked.area_m2) if picked is not None else 200)
        beds_in = st.number_input("Bedrooms", min_value=1, max_value=8, step=1, key=f"calc_beds_{choice}",
                                  value=int(picked.bedrooms) if picked is not None and pd.notna(picked.bedrooms) else 3)
        costs = st.slider("Yearly costs & vacancy (% of rent)", 0, 50, 20, key="calc_costs",
                          help="Maintenance, building fees, vacancy months, agency fees…")
    with right:
        est = research.estimate_rent(df, area_in, beds_in)
        if est is None:
            st.info("Not enough rental listings to estimate rent.")
        else:
            rent, rent_lo, rent_hi, rent_comps = est
            gross = rent * 12 / price_in * 100
            net = gross * (1 - costs / 100)
            m = st.columns(2)
            m[0].metric("Estimated rent / month", f"${rent:,.0f}", help=f"Typical range ${rent_lo:,.0f}–${rent_hi:,.0f}")
            m[1].metric("Gross yield", f"{gross:.1f}%")
            m = st.columns(2)
            m[0].metric("Net yield", f"{net:.1f}%", help=f"After {costs}% costs & vacancy")
            m[1].metric("Payback (net)", f"{100 / net:.0f} years" if net > 0 else "—")
            st.caption(f"Typical rent for similar apartments: ${rent_lo:,.0f}–${rent_hi:,.0f} / month "
                       f"(middle half of {len(rent_comps)} comparables).".replace("$", "\\$"))
            with st.expander(f"Rental comparables ({len(rent_comps)})"):
                st.dataframe(rent_comps[["source", "title", "area_m2", "bedrooms", "monthly_rent", "url"]],
                             hide_index=True, width="stretch", column_config={
                    "source": "Source", "title": "Title",
                    "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
                    "bedrooms": st.column_config.NumberColumn("Beds", format="%d"),
                    "monthly_rent": st.column_config.NumberColumn("Rent / month", format="dollar", step=1),
                    "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
                })

    st.subheader("Highest estimated yields (current filters)")
    best = options[options.gross_yield.notna() & ~options.deal_label.isin(["Check details", "Check price"])]
    st.dataframe(best.head(20)[["gross_yield", "est_rent_month", "price_usd", "area_m2", "bedrooms", "deal_label",
                                "title", "source", "url"]], hide_index=True, width="stretch", column_config={
        "gross_yield": st.column_config.NumberColumn("Gross yield", format="%.1f%%"),
        "est_rent_month": st.column_config.NumberColumn("Est. rent / month", format="dollar", step=1),
        "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
        "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
        "bedrooms": st.column_config.NumberColumn("Beds", format="%d"),
        "deal_label": "Price vs market", "title": "Title", "source": "Source",
        "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
    })

# ---------------------------------------------------------------- overview

with tab_overview:
    market = df[(df.listing_type == listing_type) & df.source.isin(sources)]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader(f"All Adma listings for {listing_type.lower()}, by category")
        counts = market.groupby(["category", "source"]).size().reset_index(name="listings")
        st.altair_chart(
            alt.Chart(counts).mark_bar(cornerRadiusEnd=4).encode(
                y=alt.Y("category:N", sort="-x", title=None),
                x=alt.X("listings:Q", title="Listings"),
                yOffset="source:N",
                color=alt.Color("source:N", scale=SOURCE_SCALE, title="Source", legend=alt.Legend(orient="top")),
                tooltip=["category", "source", "listings"],
            ).properties(height=300),
            width="stretch")
    with c2:
        st.subheader("Median asking price by category")
        med = market.groupby("category").price_usd.median().reset_index()
        st.altair_chart(
            alt.Chart(med).mark_bar(cornerRadiusEnd=4).encode(
                y=alt.Y("category:N", sort="-x", title=None),
                x=alt.X("price_usd:Q", title="Median price (USD)", axis=alt.Axis(format="$,.2s")),
                color=alt.value("#8a8986"),
                tooltip=["category", alt.Tooltip("price_usd:Q", title="Median price", format=USD)],
            ).properties(height=300),
            width="stretch")

    st.subheader("Summary for the current filters")
    summary = view.groupby(["category", "source"]).agg(
        listings=("ref", "count"),
        median_price=("price_usd", "median"),
        min_price=("price_usd", "min"),
        max_price=("price_usd", "max"),
        median_area=("area_m2", "median"),
        median_usd_m2=("price_per_m2", "median"),
    ).reset_index()
    st.dataframe(summary, hide_index=True, width="stretch", column_config={
        "category": "Category", "source": "Source", "listings": "Listings",
        "median_price": st.column_config.NumberColumn("Median price", format="dollar", step=1),
        "min_price": st.column_config.NumberColumn("Min price", format="dollar", step=1),
        "max_price": st.column_config.NumberColumn("Max price", format="dollar", step=1),
        "median_area": st.column_config.NumberColumn("Median area m²", format="%,d"),
        "median_usd_m2": st.column_config.NumberColumn("Median USD/m²", format="dollar", step=1),
    })

# ---------------------------------------------------------------- land

with tab_land:
    land = view[view.category == "Land"]
    if land.empty:
        st.info("Add **Land** to the Category filter to see this tab.")
    else:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.subheader("Plot size vs asking price")
            st.caption("Log scales: plots range from under 1,000 m² to over 10,000 m². Hover a dot for details; click to open.")
            st.altair_chart(
                alt.Chart(land.dropna(subset=["area_m2", "price_usd"])).mark_circle(size=90, opacity=0.85, stroke="white", strokeWidth=1).encode(
                    x=alt.X("area_m2:Q", scale=alt.Scale(type="log", nice=False, padding=12), title="Plot area (m²)",
                            axis=alt.Axis(format=",.0f", values=[500, 1000, 2000, 5000, 10000, 20000], grid=False)),
                    y=alt.Y("price_usd:Q", scale=alt.Scale(type="log", nice=False, padding=12), title="Asking price (USD)",
                            axis=alt.Axis(format="$,.2s", values=[300_000, 1_000_000, 3_000_000, 10_000_000, 30_000_000])),
                    color=alt.Color("source:N", scale=SOURCE_SCALE, title="Source", legend=alt.Legend(orient="top")),
                    href="url:N",
                    tooltip=tooltip,
                ).properties(height=380).interactive(),
                width="stretch")
        with c2:
            st.subheader("Price per m² distribution")
            st.caption("How many plots fall in each USD/m² range.")
            if listing_type == "Sale":
                st.altair_chart(
                    alt.Chart(land.dropna(subset=["price_per_m2"])).mark_bar(cornerRadiusEnd=4).encode(
                        x=alt.X("price_per_m2:Q", bin=alt.Bin(step=200), title="USD per m²", axis=alt.Axis(format="$,.0f")),
                        y=alt.Y("count():Q", title="Plots", stack=True),
                        color=alt.Color("source:N", scale=SOURCE_SCALE, title="Source", legend=alt.Legend(orient="top")),
                        tooltip=[alt.Tooltip("source:N", title="Source"), alt.Tooltip("count():Q", title="Plots")],
                    ).properties(height=380),
                    width="stretch")
            else:
                st.info("Price per m² is only computed for listings for sale.")

        st.subheader("By plot size")
        bands = land.assign(band=pd.cut(land.area_m2, SIZE_BANDS, labels=SIZE_LABELS, right=False))
        band_tbl = bands.groupby("band", observed=False).agg(
            plots=("ref", "count"), median_price=("price_usd", "median"), median_usd_m2=("price_per_m2", "median")
        ).reset_index()
        st.dataframe(band_tbl, hide_index=True, width="stretch", column_config={
            "band": "Plot size", "plots": "Plots",
            "median_price": st.column_config.NumberColumn("Median price", format="dollar", step=1),
            "median_usd_m2": st.column_config.NumberColumn("Median USD/m²", format="dollar", step=1),
        })

        if listing_type == "Sale":
            st.subheader("Best value: lowest price per m²")
            best = land.nsmallest(10, "price_per_m2")[["source", "ref", "title", "area_m2", "price_usd", "price_per_m2", "url"]]
            st.dataframe(best, hide_index=True, width="stretch", column_config={
                "source": "Source", "ref": "Ref", "title": "Title",
                "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
                "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
                "price_per_m2": st.column_config.NumberColumn("USD/m²", format="dollar", step=1),
                "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
            })

# ---------------------------------------------------------------- apartments

with tab_apt:
    apts = view[view.category == "Apartment"]
    if apts.empty:
        st.info("Add **Apartment** to the Category filter to see this tab.")
    else:
        apts = apts.assign(bedroom_band=apts.bedrooms.map(bedroom_band))
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Median price by bedrooms")
            st.caption("Per source. Hover a bar for the number of listings behind it.")
            by_beds = apts[apts.bedroom_band != "Not listed"].groupby(["bedroom_band", "source"]).agg(
                median_price=("price_usd", "median"), listings=("ref", "count")).reset_index()
            st.altair_chart(
                alt.Chart(by_beds).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X("bedroom_band:N", sort=BEDROOM_LABELS, title="Bedrooms", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("median_price:Q", title="Median price (USD)", axis=alt.Axis(format="$,.2s")),
                    xOffset="source:N",
                    color=alt.Color("source:N", scale=SOURCE_SCALE, title="Source", legend=alt.Legend(orient="top")),
                    tooltip=[alt.Tooltip("bedroom_band:N", title="Bedrooms"), alt.Tooltip("source:N", title="Source"),
                             alt.Tooltip("median_price:Q", title="Median price", format=USD),
                             alt.Tooltip("listings:Q", title="Listings")],
                ).properties(height=360),
                width="stretch")
        with c2:
            st.subheader("Size vs asking price")
            st.caption("Hover a dot for details; click to open the listing.")
            st.altair_chart(
                alt.Chart(apts.dropna(subset=["area_m2", "price_usd"])).mark_circle(size=80, opacity=0.85, stroke="white", strokeWidth=1).encode(
                    x=alt.X("area_m2:Q", title="Area (m²)", scale=alt.Scale(zero=False), axis=alt.Axis(format=",.0f")),
                    y=alt.Y("price_usd:Q", title="Asking price (USD)", scale=alt.Scale(zero=False), axis=alt.Axis(format="$,.2s")),
                    color=alt.Color("source:N", scale=SOURCE_SCALE, title="Source", legend=alt.Legend(orient="top")),
                    href="url:N",
                    tooltip=tooltip + [alt.Tooltip("bedrooms:Q", title="Bedrooms")],
                ).properties(height=360).interactive(),
                width="stretch")

        st.subheader("By bedrooms")
        st.dataframe(apartments_by_bedrooms(view, listing_type), hide_index=True, width="stretch", column_config={
            "Median price": st.column_config.NumberColumn(format="dollar", step=1),
            "Median area (m²)": st.column_config.NumberColumn(format="%,d"),
            "Median USD/m²": st.column_config.NumberColumn(format="dollar", step=1),
        })

        if listing_type == "Sale":
            st.subheader("Best value: lowest price per m²")
            st.caption("Very low values are usually listing typos (e.g. a rent price posted as a sale) — check the link.")
            pick = apts.dropna(subset=["price_per_m2"]).nsmallest(10, "price_per_m2")
        else:
            st.subheader("Cheapest rentals")
            st.caption("Rent prices are as listed — check 'Price as listed' for monthly vs yearly.")
            pick = apts.dropna(subset=["price_usd"]).nsmallest(10, "price_usd")
        st.dataframe(pick[["source", "ref", "title", "bedrooms", "area_m2", "price_usd", "price_label", "price_per_m2", "url"]],
                     hide_index=True, width="stretch", column_config={
            "source": "Source", "ref": "Ref", "title": "Title", "price_label": "Price as listed",
            "bedrooms": st.column_config.NumberColumn("Beds", format="%d"),
            "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
            "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
            "price_per_m2": st.column_config.NumberColumn("USD/m²", format="dollar", step=1),
            "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
        })

# ---------------------------------------------------------------- changes & history


def in_filters(d):
    keep = d.listing_type.eq(listing_type) & d.category.isin(categories) & d.source.isin(sources)
    if "listing_id" in d:
        keep &= ~d.listing_id.isin(hidden_ids)
    return d[keep]


with tab_hist:
    if latest is None:
        st.info("History starts with your first scrape. Each re-scrape is saved as a snapshot in "
                "`output/snapshots/`; from the second one on, this tab shows what's new, removed and re-priced.")
    else:
        events, prev_times, t_new = latest
        events = in_filters(events)
        since = ", ".join(f"{src} {t:%d %b %H:%M}" for src, t in prev_times.items())
        st.caption(f"Latest scrape {t_new:%d %b %Y %H:%M} compared with each site's previous scrape ({since}). "
                   "Uses the Listing / Category / Source filters.")
        counts = events.change.value_counts()
        k = st.columns(4)
        k[0].metric("🆕 New listings", int(counts.get("New", 0)))
        k[1].metric("❌ Removed", int(counts.get("Removed", 0)), help="No longer on the site: sold, rented, "
                    "expired or withdrawn — the sites don't say which.")
        k[2].metric("📉 Price drops", int(counts.get("Price drop", 0)))
        k[3].metric("📈 Price increases", int(counts.get("Price increase", 0)))

        change_cols = {
            "source": "Source", "ref": "Ref", "category": "Category", "title": "Title",
            "old_price": st.column_config.NumberColumn("Previous price", format="dollar", step=1),
            "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
            "price_change": st.column_config.NumberColumn("Change", format="dollar", step=1),
            "price_change_pct": st.column_config.NumberColumn("Change %", format="%.1f%%"),
            "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
            "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
        }
        for label, kinds, cols in [
            ("🆕 New listings", ["New"], ["source", "ref", "category", "title", "price_usd", "area_m2", "url"]),
            ("📉📈 Price changes", ["Price drop", "Price increase"],
             ["source", "ref", "category", "title", "old_price", "price_usd", "price_change", "price_change_pct", "url"]),
            ("❌ Removed since last scrape", ["Removed"], ["source", "ref", "category", "title", "price_usd", "area_m2", "url"]),
        ]:
            part = events[events.change.isin(kinds)]
            with st.expander(f"{label} ({len(part)})", expanded=0 < len(part) <= 30):
                if part.empty:
                    st.caption("None.")
                else:
                    st.dataframe(part[cols], hide_index=True, width="stretch", column_config=change_cols)

    if not inventory.empty and inventory.snapshot.nunique() > 1:
        st.subheader("Listings online over time")
        inv = in_filters(inventory).groupby(["snapshot", "source"]).listings.sum().reset_index()
        st.altair_chart(
            alt.Chart(inv).mark_line(point=alt.OverlayMarkDef(size=60), strokeWidth=2).encode(
                x=alt.X("snapshot:T", title="Scrape date"),
                y=alt.Y("listings:Q", title="Listings online"),
                color=alt.Color("source:N", scale=SOURCE_SCALE, title="Source", legend=alt.Legend(orient="top")),
                tooltip=[alt.Tooltip("snapshot:T", title="Scrape", format="%d %b %Y %H:%M"), "source", "listings"],
            ).properties(height=280),
            width="stretch")

    if not hist_all.empty:
        st.subheader("Every listing ever seen")
        show = st.radio("Show", ["All", "Online", "Removed"], horizontal=True, key="hist_show")
        h = in_filters(hist_all)
        if show != "All":
            h = h[h.online_status == show]
        st.dataframe(h[["online_status", "source", "ref", "category", "title", "first_seen", "last_seen",
                        "days_online", "first_price", "price_usd", "price_change", "url"]],
                     hide_index=True, width="stretch", height=420, column_config={
            "online_status": "Online?", "source": "Source", "ref": "Ref", "category": "Category", "title": "Title",
            "first_seen": st.column_config.DatetimeColumn("First seen", format="D MMM YYYY"),
            "last_seen": st.column_config.DatetimeColumn("Last seen", format="D MMM YYYY"),
            "days_online": st.column_config.NumberColumn("Days online", format="%d"),
            "first_price": st.column_config.NumberColumn("First price", format="dollar", step=1),
            "price_usd": st.column_config.NumberColumn("Latest price", format="dollar", step=1),
            "price_change": st.column_config.NumberColumn("Change", format="dollar", step=1),
            "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
        })

# ---------------------------------------------------------------- sites compared

with tab_compare:
    st.subheader("Same property on several sites?")
    st.caption("Land/villas whose exact area appears on another site (for round sizes, also within 15% on price). "
               "Possible matches only — check the links.")
    by_key = {(r.source, str(r.ref)): r for r in df.itertuples()}
    pairs, seen = [], set()
    for rec in df[df.also_listed_on.notna()].itertuples():
        for part in rec.also_listed_on.split("; "):
            src, ref = part.split(" ")[:2]
            other = by_key.get((src, ref))
            key = frozenset([(rec.source, str(rec.ref)), (src, ref)])
            if other is None or key in seen:
                continue
            seen.add(key)
            pairs.append({
                "category": rec.category, "area_m2": rec.area_m2,
                "site_a": rec.source, "price_a": rec.price_usd, "url_a": rec.url,
                "site_b": other.source, "price_b": other.price_usd, "url_b": other.url,
                "difference": rec.price_usd - other.price_usd,
            })
    if pairs:
        st.dataframe(pd.DataFrame(pairs), hide_index=True, width="stretch", column_config={
            "category": "Category", "site_a": "Site A", "site_b": "Site B",
            "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
            "price_a": st.column_config.NumberColumn("Price A", format="dollar", step=1),
            "price_b": st.column_config.NumberColumn("Price B", format="dollar", step=1),
            "difference": st.column_config.NumberColumn("A − B", format="dollar", step=1),
            "url_a": st.column_config.LinkColumn("Listing A", display_text="Open ↗"),
            "url_b": st.column_config.LinkColumn("Listing B", display_text="Open ↗"),
        })
    else:
        st.info("No likely cross-listings found.")

    st.subheader("Land price per m² by site")
    land_sale = df[(df.category == "Land") & (df.listing_type == "Sale")].dropna(subset=["price_per_m2"])
    st.altair_chart(
        alt.Chart(land_sale).mark_tick(thickness=2, size=28).encode(
            x=alt.X("price_per_m2:Q", title="USD per m²", axis=alt.Axis(format="$,.0f")),
            y=alt.Y("source:N", title=None),
            color=alt.Color("source:N", scale=SOURCE_SCALE, legend=None),
            tooltip=tooltip,
        ).properties(height=160),
        width="stretch")

# ---------------------------------------------------------------- table + downloads

with tab_table:
    cols = ["image_url", "source", "ref", "category", "property_type", "title", "price_usd", "area_m2",
            "price_per_m2", "deal_label", "value_gap_pct", "fair_value", "est_rent_month", "gross_yield",
            "listings_in_group", "group_sources", "bedrooms", "bathrooms", "location", "agent", "agent_phone",
            "publish_date", "url"]
    st.caption("Tick **✕** on a row to hide that listing (it moves to the 🙈 Hidden tab).")
    table = view[cols].copy()
    table.insert(0, "hide", False)
    version = st.session_state.get("table_version", 0)
    edited = st.data_editor(table, key=f"table_{version}", hide_index=True, width="stretch", height=560,
                            disabled=[c for c in table.columns if c != "hide"], column_config={
        "hide": st.column_config.CheckboxColumn("✕", help="Tick to hide this listing", width="small"),
        "source": "Source", "ref": "Ref", "category": "Category", "title": "Title",
        "bedrooms": st.column_config.NumberColumn("Beds", format="%d"),
        "bathrooms": st.column_config.NumberColumn("Baths", format="%d"),
        "location": "Location", "agent": "Agent", "agent_phone": "Phone",
        "image_url": st.column_config.ImageColumn("Photo", width="small"),
        "property_type": "Site type",
        "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
        "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
        "price_per_m2": st.column_config.NumberColumn("USD/m²", format="dollar", step=1),
        "publish_date": st.column_config.DateColumn("Published"),
        "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
        "deal_label": "Price vs market",
        "value_gap_pct": st.column_config.NumberColumn("vs market", format="%+.0f%%"),
        "fair_value": st.column_config.NumberColumn("Est. market value", format="dollar", step=1),
        "est_rent_month": st.column_config.NumberColumn("Est. rent / month", format="dollar", step=1),
        "gross_yield": st.column_config.NumberColumn("Gross yield", format="%.1f%%"),
        "listings_in_group": st.column_config.NumberColumn("Times listed", format="%d"),
        "group_sources": "Listed on",
    })
    ticked = edited.index[edited.hide]
    if len(ticked):
        hidden.hide(df_all[df_all.property_id.isin(view.loc[ticked, "property_id"])])
        st.session_state.table_version = version + 1  # fresh editor: rows below the hidden ones shift up
        st.toast(f"{len(ticked)} listing(s) hidden — see the 🙈 Hidden tab", icon="🙈")
        st.rerun()
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Filtered rows (CSV)", view.to_csv(index=False).encode("utf-8-sig"),
                       "adma_filtered.csv", "text/csv", width="stretch")
    if XLSX_PATH.exists():
        d2.download_button("⬇️ Full Excel report", XLSX_PATH.read_bytes(), XLSX_PATH.name,
                           width="stretch")

# ---------------------------------------------------------------- hidden by the user

with tab_hidden:
    hidden_rows = hidden.load()
    if hidden_rows.empty:
        st.info("Nothing hidden. Click **✕** on a listing card in *Browse listings*, or tick **✕** in the "
                "*Data table*, to hide listings you're not interested in.")
    else:
        st.markdown(f'<div class="results-h">{len(hidden_rows)} hidden listing(s)</div>'
                    '<div class="results-sub">Left out of every tab, chart and total (and the Excel report). '
                    "They stay hidden after re-scrapes. Tick ↩ to bring one back.</div>", unsafe_allow_html=True)
        table = hidden_rows.sort_values("hidden_at", ascending=False).copy()
        table.insert(0, "restore", False)
        version = st.session_state.get("hidden_version", 0)
        edited = st.data_editor(
            table[["restore", "hidden_at", "source", "ref", "category", "title", "price_usd", "url"]],
            key=f"hidden_{version}", hide_index=True, width="stretch",
            disabled=["hidden_at", "source", "ref", "category", "title", "price_usd", "url"], column_config={
                "restore": st.column_config.CheckboxColumn("↩", help="Tick to restore this listing", width="small"),
                "hidden_at": "Hidden on", "source": "Source", "ref": "Ref", "category": "Category", "title": "Title",
                "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
                "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
            })
        ticked = edited.index[edited.restore]
        if len(ticked):
            hidden.restore(table.loc[ticked, "listing_id"])
            st.session_state.hidden_version = version + 1
            st.rerun()
        if st.button("↩ Restore all hidden listings"):
            hidden.restore(hidden_rows.listing_id)
            st.rerun()
