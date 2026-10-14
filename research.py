"""Research layer on top of the scraped listings.

    enrich(df) adds:
      Duplicates   property_id, listings_in_group, group_sources, group_min_price, group_max_price, is_primary
      Fair price   fair_price_m2, fair_value, value_gap_pct, deal_label, comps_n, comps_ids, fair_confidence
      Rent/yield   monthly_rent (rentals), est_rent_month + gross_yield (apartments for sale)

Everything is a transparent rule or a "median of similar listings" - no black box - so each number
can be explained from the comparables it came from. Asking prices are not sale prices; treat the
results as research signals, not valuations.
"""
import re

import numpy as np
import pandas as pd

FEATURES = {  # keyword -> feature name, searched in title + description
    "sea_view": r"sea ?view|bay view|panoramic|open view",
    "terrace": r"terrace|roof ?top",
    "garden": r"garden",
    "duplex": r"duplex|triplex|penthouse",
    "furnished": r"(?<!un)(?<!semi )(?<!semi-)furnished",
    "new_build": r"brand ?new|new building|new construction",
    "under_construction": r"under construction|off[- ]plan",
    "gated": r"gated|compound|pool",
}
# Asking prices for similar properties typically differ by ±20%, so the bands are wide on purpose.
DEAL_LABELS = [(-50, "Check details"), (-25, "Great deal"), (-10, "Good price"), (10, "Fair price"),
               (25, "Above market"), (np.inf, "High price")]
# $/m² outside these ranges is almost always a typo (rent posted as sale, price per m² as total, …)
SANE_M2 = {"Apartment": (300, 10000), "Villa": (300, 15000), "Land": (50, 10000)}
STOP_WORDS = {"for", "sale", "rent", "the", "and", "with", "adma", "keserwan", "keserouan", "kesrouane", "dafnah",
              "apartment", "land", "villa", "sqm", "view", "sea", "in", "a", "of", "ref"}


# ---------------------------------------------------------------- helpers

def _text(df):
    return (df.title.fillna("") + " " + df.description.fillna("")).str.lower()


def _features(df) -> pd.DataFrame:
    text = _text(df)
    return pd.DataFrame({name: text.str.contains(rx, regex=True).astype(float) for name, rx in FEATURES.items()},
                        index=df.index)


def _words(title):
    return {w for w in re.findall(r"[a-z]{3,}", str(title).lower()) if w not in STOP_WORDS}


def _sane(df):
    lo = df.category.map(lambda c: SANE_M2.get(c, (0, 0))[0])
    hi = df.category.map(lambda c: SANE_M2.get(c, (0, 0))[1])
    return df.price_per_m2.between(lo, hi)


# ---------------------------------------------------------------- 1. duplicates

def _same_property(a, b) -> bool:
    if pd.notna(a.bedrooms) and pd.notna(b.bedrooms) and a.bedrooms != b.bedrooms:
        return False
    distinctive = a.area_m2 % 10 != 0  # 1,183 m² is a fingerprint; 200 m² is not
    if pd.notna(a.price_usd) and pd.notna(b.price_usd):
        gap = abs(a.price_usd - b.price_usd) / max(a.price_usd, b.price_usd)
    else:
        gap = None
    title_a, title_b = _words(a.title), _words(b.title)
    similar = bool(title_a and title_b) and len(title_a & title_b) / len(title_a | title_b) >= 0.3
    same_agent = isinstance(a.agent, str) and a.agent == b.agent
    if distinctive and a.category in ("Land", "Villa") and (gap is None or gap <= 0.4):
        return True  # agencies often list the same plot at quite different prices
    return gap is not None and gap <= 0.03 and (distinctive or same_agent or similar)


def find_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    parent = {i: i for i in df.index}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for _, group in df[df.area_m2.notna()].groupby(["category", "listing_type", "area_m2"]):
        rows = list(group.itertuples())
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if root(a.Index) != root(b.Index) and _same_property(a, b):
                    parent[root(b.Index)] = root(a.Index)

    out = df.copy()
    groups = pd.Series({i: root(i) for i in df.index})
    out["_group"] = groups
    first_id = out.groupby("_group").listing_id.transform("min")
    out["property_id"] = first_id
    g = out.groupby("_group")
    out["listings_in_group"] = g.listing_id.transform("count")
    out["group_min_price"] = g.price_usd.transform("min")
    out["group_max_price"] = g.price_usd.transform("max")
    out["group_sources"] = g.source.transform(
        lambda s: ", ".join(f"{src} ×{n}" if n > 1 else src for src, n in s.value_counts().items()))
    # one representative per property: the cheapest asking price, then the most complete listing
    completeness = out[["price_usd", "area_m2", "bedrooms", "image_url", "description"]].notna().sum(axis=1)
    order = out.assign(_c=completeness).sort_values(["_group", "price_usd", "_c"], ascending=[True, True, False])
    out["is_primary"] = out.index.isin(order.drop_duplicates("_group").index)
    return out.drop(columns="_group")


# ---------------------------------------------------------------- 2. fair price

def _knn_median(train_x, train_y, query_x, k, exclude=None):
    """Median of the k nearest training targets for each query row (+ which rows were used)."""
    dist = np.sqrt(((query_x[:, None, :] - train_x[None, :, :]) ** 2).sum(axis=2))
    if exclude is not None:
        dist[exclude] = np.inf
    k = min(k, max(1, train_x.shape[0] - 1))
    idx = np.argsort(dist, axis=1)[:, :k]
    values = train_y[idx]
    return np.median(values, axis=1), np.percentile(values, 25, axis=1), np.percentile(values, 75, axis=1), idx


def _design(df, category):
    area = np.log(df.area_m2.to_numpy(float))
    cols = [area / 0.35 * 1.5]  # ~±35% size difference ≈ 1.5 units
    if category in ("Apartment", "Villa"):
        beds = df.bedrooms.fillna((df.area_m2 / 75).round().clip(1, 6)).to_numpy(float)
        cols.append(beds * 0.6)
    feats = _features(df)
    for name in FEATURES:
        cols.append(feats[name].to_numpy() * (0.5 if category != "Land" else (0.7 if name == "sea_view" else 0.0)))
    return np.column_stack(cols)


def fair_prices(df: pd.DataFrame, k: int = 15) -> pd.DataFrame:
    out = df.assign(fair_price_m2=np.nan, comps_n=np.nan, comps_ids=None, fair_confidence=None)
    sale = df[(df.listing_type == "Sale") & df.area_m2.notna()]
    for category in ("Apartment", "Land", "Villa"):
        targets = sale[sale.category == category]
        train = targets[targets.is_primary & _sane(targets)]
        if len(train) < 5 or targets.empty:
            continue
        tx, qx = _design(train, category), _design(targets, category)
        # never compare a listing with itself or its own duplicates
        same = targets.property_id.to_numpy()[:, None] == train.property_id.to_numpy()[None, :]
        med, p25, p75, idx = _knn_median(tx, train.price_per_m2.to_numpy(float), qx, k, exclude=same)
        spread = (p75 - p25) / med
        used = idx.shape[1]
        out.loc[targets.index, "fair_price_m2"] = med
        out.loc[targets.index, "comps_n"] = used
        ids = train.listing_id.to_numpy()
        out.loc[targets.index, "comps_ids"] = ["|".join(ids[row]) for row in idx]
        out.loc[targets.index, "fair_confidence"] = np.where(
            (used >= 10) & (spread < 0.35), "High", np.where((used >= 6) & (spread < 0.6), "Medium", "Low"))

    out["fair_value"] = out.fair_price_m2 * out.area_m2
    out["value_gap_pct"] = (out.price_usd - out.fair_value) / out.fair_value * 100
    insane = (out.listing_type == "Sale") & out.price_per_m2.notna() & ~_sane(out) & out.category.isin(SANE_M2)
    out.loc[insane, "value_gap_pct"] = np.nan  # don't advertise a typo as a bargain
    out["deal_label"] = out.value_gap_pct.map(
        lambda g: None if pd.isna(g) else next(label for limit, label in DEAL_LABELS if g <= limit))
    out.loc[insane, "deal_label"] = "Check price"
    return out


# ---------------------------------------------------------------- 3. rent & yield

def monthly_rent(row) -> float:
    if row.listing_type != "Rent" or pd.isna(row.price_usd):
        return np.nan
    label, price = str(row.price_label).lower(), row.price_usd
    if "day" in label or "week" in label:
        return np.nan
    if "year" in label:
        rent = price / 12
    elif "month" in label:
        rent = price
    else:  # no period given: big numbers are yearly
        rent = price / 12 if price > 20000 else price
    return rent if 150 <= rent <= 30000 else np.nan


def rental_estimates(df: pd.DataFrame, k: int = 10) -> pd.DataFrame:
    out = df.copy()
    out["monthly_rent"] = out.apply(monthly_rent, axis=1)
    out["est_rent_month"] = np.nan
    out["gross_yield"] = np.nan
    rentals = out[(out.category == "Apartment") & out.monthly_rent.notna() & out.area_m2.notna() & out.is_primary]
    targets = out[(out.category == "Apartment") & (out.listing_type == "Sale") & out.area_m2.notna()]
    if len(rentals) < 5 or targets.empty:
        return out
    rent_m2 = (rentals.monthly_rent / rentals.area_m2).to_numpy(float)
    med, *_ = _knn_median(_design(rentals, "Apartment"), rent_m2, _design(targets, "Apartment"), k)
    out.loc[targets.index, "est_rent_month"] = med * targets.area_m2
    out["gross_yield"] = out.est_rent_month * 12 / out.price_usd * 100
    out.loc[~_sane(out) & out.gross_yield.notna(), "gross_yield"] = np.nan
    return out


def estimate_rent(df: pd.DataFrame, area_m2: float, bedrooms: float | None, k: int = 10):
    """Calculator helper: (median, p25, p75, comps) monthly rent for an apartment of this size."""
    rentals = df[(df.category == "Apartment") & df.monthly_rent.notna() & df.area_m2.notna() & df.is_primary]
    if len(rentals) < 3:
        return None
    probe = pd.DataFrame({"area_m2": [area_m2], "bedrooms": [bedrooms], "title": [""], "description": [""]})
    med, p25, p75, idx = _knn_median(_design(rentals, "Apartment"), (rentals.monthly_rent / rentals.area_m2).to_numpy(float),
                                     _design(probe, "Apartment"), k)
    return med[0] * area_m2, p25[0] * area_m2, p75[0] * area_m2, rentals.iloc[idx[0]]


def yield_by_bedrooms(df: pd.DataFrame) -> pd.DataFrame:
    def band(b):
        return "Not listed" if pd.isna(b) else ("5+" if b >= 5 else "Studio / 1" if b <= 1 else str(int(b)))

    apts = df[(df.category == "Apartment") & df.is_primary]
    sale = apts[(apts.listing_type == "Sale") & _sane(apts)]
    rent = apts[apts.monthly_rent.notna()]
    rows = []
    for b in ["Studio / 1", "2", "3", "4", "5+"]:
        s, r = sale[sale.bedrooms.map(band) == b], rent[rent.bedrooms.map(band) == b]
        if len(s) < 3 or len(r) < 3:  # too few listings for a meaningful median
            continue
        price, monthly = s.price_usd.median(), r.monthly_rent.median()
        rows.append({"Bedrooms": b, "For sale": len(s), "Median price": price, "For rent": len(r),
                     "Median rent / month": monthly, "Gross yield %": monthly * 12 / price * 100,
                     "Price-to-rent (years)": price / (monthly * 12)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- all together

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    return rental_estimates(fair_prices(find_duplicates(df)))
