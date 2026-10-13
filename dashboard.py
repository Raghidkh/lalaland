"""Interactive dashboard for the scraped Adma listings.

Run:  streamlit run dashboard.py
"""
import altair as alt
import pandas as pd
import streamlit as st

from report import BEDROOM_LABELS, SIZE_BANDS, SIZE_LABELS, apartments_by_bedrooms, bedroom_band
from scrape import CSV_PATH, XLSX_PATH, run

st.set_page_config(page_title="Adma Real Estate", page_icon="🏡", layout="wide")

# Fixed colour per entity (reference palette order) so filtering never repaints survivors.
SOURCE_SCALE = alt.Scale(domain=["Confidence", "JSK"], range=["#2a78d6", "#eb6834"])
CATEGORY_SCALE = alt.Scale(
    domain=["Land", "Villa", "Apartment", "Commercial", "Other"],
    range=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a8986"],
)
USD = "$,.0f"


@st.cache_data
def load(mtime: float) -> pd.DataFrame:  # mtime busts the cache after a re-scrape
    df = pd.read_csv(CSV_PATH)
    df["publish_date"] = pd.to_datetime(df["publish_date"], errors="coerce")
    return df


def money(v):
    return "—" if pd.isna(v) else f"${v:,.0f}"


# ---------------------------------------------------------------- data + sidebar

with st.sidebar:
    st.header("Data")
    if st.button("🔄 Re-scrape both websites", width="stretch"):
        with st.status("Scraping confidencerealestate.com and jskre.com…", expanded=True) as status:
            run(log=st.write)
            status.update(label="Done — data refreshed", state="complete")
        st.cache_data.clear()

if not CSV_PATH.exists():
    st.info("No data yet. Click **Re-scrape both websites** in the sidebar (takes ~1 minute).")
    st.stop()

df = load(CSV_PATH.stat().st_mtime)

with st.sidebar:
    st.caption(f"Last scraped: {df.scraped_at.iloc[0]} · {len(df)} Adma listings")
    st.header("Filters")
    listing_type = st.radio("Listing", ["Sale", "Rent"], horizontal=True)
    categories = st.multiselect("Category", list(CATEGORY_SCALE.domain), default=["Land", "Villa", "Apartment"])
    sources = st.multiselect("Agency", ["Confidence", "JSK"], default=["Confidence", "JSK"])
    base = df[(df.listing_type == listing_type) & df.category.isin(categories) & df.source.isin(sources)]

    prices = base.price_usd.dropna()
    if len(prices) > 1 and prices.min() < prices.max():
        lo, hi = st.slider("Price (USD)", float(prices.min()), float(prices.max()),
                           (float(prices.min()), float(prices.max())), step=10000.0, format="$%,d")
        base = base[base.price_usd.isna() | base.price_usd.between(lo, hi)]
    areas = base.area_m2.dropna()
    if len(areas) > 1 and areas.min() < areas.max():
        alo, ahi = st.slider("Area (m²)", float(areas.min()), float(areas.max()),
                             (float(areas.min()), float(areas.max())), step=10.0, format="%,d m²")
        base = base[base.area_m2.isna() | base.area_m2.between(alo, ahi)]
    text = st.text_input("Search title / description", placeholder="e.g. sea view, pool")
    if text:
        mask = (base.title.fillna("") + " " + base.description.fillna("")).str.contains(text, case=False, regex=False)
        base = base[mask]

view = base

# ---------------------------------------------------------------- header + KPIs

st.title("Adma real estate — land, villas & apartments")
st.caption("Listings scraped from confidencerealestate.com and jskre.com, located in Adma (Keserwan, Lebanon). "
           "Prices are asking prices in USD.")

k = st.columns(5)
k[0].metric("Listings", f"{len(view):,}")
k[1].metric("Median price", money(view.price_usd.median()))
k[2].metric("Median USD / m²", money(view.price_per_m2.median()) if listing_type == "Sale" else "n/a for rent")
k[3].metric("Median area", "—" if view.area_m2.dropna().empty else f"{view.area_m2.median():,.0f} m²")
k[4].metric("Lowest USD / m²", money(view.price_per_m2.min()) if listing_type == "Sale" else "n/a for rent")

if view.empty:
    st.warning("No listings match these filters.")
    st.stop()

tooltip = [
    alt.Tooltip("title:N", title="Title"),
    alt.Tooltip("source:N", title="Agency"),
    alt.Tooltip("ref:N", title="Ref"),
    alt.Tooltip("price_usd:Q", title="Price", format=USD),
    alt.Tooltip("area_m2:Q", title="Area m²", format=",.0f"),
    alt.Tooltip("price_per_m2:Q", title="USD/m²", format=USD),
]

tab_overview, tab_land, tab_villa, tab_apt, tab_compare, tab_table = st.tabs(
    ["📊 Overview", "🌄 Land", "🏡 Villas", "🏢 Apartments", "🔁 Agencies compared", "📋 All listings"])

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
                color=alt.Color("source:N", scale=SOURCE_SCALE, title="Agency", legend=alt.Legend(orient="top")),
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
                color=alt.Color("category:N", scale=CATEGORY_SCALE, legend=None),
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
        "category": "Category", "source": "Agency", "listings": "Listings",
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
                    color=alt.Color("source:N", scale=SOURCE_SCALE, title="Agency", legend=alt.Legend(orient="top")),
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
                        color=alt.Color("source:N", scale=SOURCE_SCALE, title="Agency", legend=alt.Legend(orient="top")),
                        tooltip=[alt.Tooltip("source:N", title="Agency"), alt.Tooltip("count():Q", title="Plots")],
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
                "source": "Agency", "ref": "Ref", "title": "Title",
                "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
                "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
                "price_per_m2": st.column_config.NumberColumn("USD/m²", format="dollar", step=1),
                "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
            })

# ---------------------------------------------------------------- villas

with tab_villa:
    villas = view[view.category == "Villa"]
    if villas.empty:
        st.info("Add **Villa** to the Category filter to see this tab (few villas are listed in Adma).")
    else:
        st.caption(f"{len(villas)} villa/house listing(s) match the current filters.")
        for rec in villas.sort_values("price_usd").itertuples():
            with st.container(border=True):
                img, info = st.columns([1, 3])
                if isinstance(rec.image_url, str):
                    img.image(rec.image_url, width="stretch")
                info.markdown(f"**{rec.title}**  \n{rec.source} · Ref {rec.ref} · {rec.location}")
                facts = info.columns(4)
                facts[0].metric("Price", money(rec.price_usd))
                facts[1].metric("Area", "—" if pd.isna(rec.area_m2) else f"{rec.area_m2:,.0f} m²")
                facts[2].metric("Bedrooms", "—" if pd.isna(rec.bedrooms) else f"{rec.bedrooms:.0f}")
                facts[3].metric("Bathrooms", "—" if pd.isna(rec.bathrooms) else f"{rec.bathrooms:.0f}")
                info.link_button("Open listing ↗", rec.url)
                if isinstance(rec.description, str):
                    with info.expander("Description"):
                        st.text(rec.description)

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
            st.caption("Per agency. Hover a bar for the number of listings behind it.")
            by_beds = apts[apts.bedroom_band != "Not listed"].groupby(["bedroom_band", "source"]).agg(
                median_price=("price_usd", "median"), listings=("ref", "count")).reset_index()
            st.altair_chart(
                alt.Chart(by_beds).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X("bedroom_band:N", sort=BEDROOM_LABELS, title="Bedrooms", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("median_price:Q", title="Median price (USD)", axis=alt.Axis(format="$,.2s")),
                    xOffset="source:N",
                    color=alt.Color("source:N", scale=SOURCE_SCALE, title="Agency", legend=alt.Legend(orient="top")),
                    tooltip=[alt.Tooltip("bedroom_band:N", title="Bedrooms"), alt.Tooltip("source:N", title="Agency"),
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
                    color=alt.Color("source:N", scale=SOURCE_SCALE, title="Agency", legend=alt.Legend(orient="top")),
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
            "source": "Agency", "ref": "Ref", "title": "Title", "price_label": "Price as listed",
            "bedrooms": st.column_config.NumberColumn("Beds", format="%d"),
            "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
            "price_usd": st.column_config.NumberColumn("Price", format="dollar", step=1),
            "price_per_m2": st.column_config.NumberColumn("USD/m²", format="dollar", step=1),
            "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
        })

# ---------------------------------------------------------------- agencies compared

with tab_compare:
    st.subheader("Same property, two agencies?")
    st.caption("Land/villas whose exact area appears on both sites (for round sizes, also within 15% on price). "
               "Possible matches only — check the links.")
    pairs = []
    conf = df[(df.source == "Confidence") & df.also_listed_on.notna()]
    jsk = df[df.source == "JSK"].set_index("ref")
    for rec in conf.itertuples():
        for part in rec.also_listed_on.split("; "):
            ref = part.split(" ")[1]
            if ref in jsk.index:
                other = jsk.loc[ref]
                pairs.append({
                    "category": rec.category, "area_m2": rec.area_m2,
                    "confidence_ref": rec.ref, "confidence_price": rec.price_usd, "confidence_url": rec.url,
                    "jsk_ref": ref, "jsk_price": other.price_usd, "jsk_url": other.url,
                    "difference": rec.price_usd - other.price_usd,
                })
    if pairs:
        st.dataframe(pd.DataFrame(pairs), hide_index=True, width="stretch", column_config={
            "category": "Category", "confidence_ref": "Confidence ref", "jsk_ref": "JSK ref",
            "area_m2": st.column_config.NumberColumn("Area m²", format="%,d"),
            "confidence_price": st.column_config.NumberColumn("Confidence price", format="dollar", step=1),
            "jsk_price": st.column_config.NumberColumn("JSK price", format="dollar", step=1),
            "difference": st.column_config.NumberColumn("Confidence − JSK", format="dollar", step=1),
            "confidence_url": st.column_config.LinkColumn("Confidence", display_text="Open ↗"),
            "jsk_url": st.column_config.LinkColumn("JSK", display_text="Open ↗"),
        })
    else:
        st.info("No likely cross-listings found.")

    st.subheader("Land price per m² by agency")
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
            "price_per_m2", "bedrooms", "bathrooms", "location", "agent", "agent_phone", "publish_date", "url"]
    st.dataframe(view[cols], hide_index=True, width="stretch", height=560, column_config={
        "source": "Agency", "ref": "Ref", "category": "Category", "title": "Title",
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
    })
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Filtered rows (CSV)", view.to_csv(index=False).encode("utf-8-sig"),
                       "adma_filtered.csv", "text/csv", width="stretch")
    if XLSX_PATH.exists():
        d2.download_button("⬇️ Full Excel report", XLSX_PATH.read_bytes(), XLSX_PATH.name,
                           width="stretch")
