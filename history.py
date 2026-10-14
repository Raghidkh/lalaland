"""Listing history across scrapes.

Every scrape is saved as a dated snapshot in output/snapshots/. Comparing snapshots tells us:
  - New:          listing appears that wasn't there before
  - Removed:      listing no longer on the site (sold, rented, expired or withdrawn - the
                  sites don't say which)
  - Price change: same listing, different asking price
A site that failed during a scrape is skipped in that comparison, so a network error never
shows up as "everything removed".
"""
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

SNAPSHOT_DIR = Path(__file__).parent / "output" / "snapshots"
# Snapshots keep everything except the long text columns, so they stay small (git-friendly).
SNAPSHOT_DROP = ["description"]
KEY_COLUMNS = ["listing_id", "source", "ref", "title", "category", "property_type", "listing_type",
               "price_usd", "price_label", "area_m2", "price_per_m2", "bedrooms", "agent", "url", "image_url"]


def add_listing_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Older CSVs predate the listing_id column - derive it the same way the scrapers do."""
    if "listing_id" in df.columns and df.listing_id.notna().all():
        return df

    def derive(row):
        if row["source"] == "Confidence":
            m = re.search(r"/property/(\d+)", str(row["url"]))
            return f"Confidence:{m.group(1) if m else row['ref']}"
        return f"{row['source']}:{row['ref']}"

    df = df.copy()
    df["listing_id"] = df.apply(derive, axis=1)
    return df


def save_snapshot(df: pd.DataFrame, when: datetime | None = None) -> Path:
    when = when or datetime.now()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"adma_{when:%Y-%m-%d_%H%M}.csv"
    snap = add_listing_ids(df).drop(columns=[c for c in SNAPSHOT_DROP if c in df.columns])
    snap.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def list_snapshots() -> list[tuple[datetime, Path]]:
    out = []
    for path in sorted(SNAPSHOT_DIR.glob("adma_*.csv")):
        try:
            out.append((datetime.strptime(path.stem[5:], "%Y-%m-%d_%H%M"), path))
        except ValueError:
            continue
    return out


def load_snapshot(path: Path) -> pd.DataFrame:
    return add_listing_ids(pd.read_csv(path)).drop_duplicates("listing_id")


def compare(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Rows describing what changed between two snapshots (one row per event)."""
    sources = set(new.source.unique())  # a source missing from `new` failed - don't treat as removals
    old = old[old.source.isin(sources)].set_index("listing_id")
    new = new.set_index("listing_id")

    added = new.loc[new.index.difference(old.index)].assign(change="New")
    removed = old.loc[old.index.difference(new.index)].assign(change="Removed")

    both = new.index.intersection(old.index)
    before, after = old.loc[both, "price_usd"], new.loc[both, "price_usd"]
    moved = both[(before.notna() & after.notna() & (before != after)).to_numpy()]
    changed = new.loc[moved].assign(
        old_price=old.loc[moved, "price_usd"],
        change=lambda d: ["Price drop" if n < o else "Price increase" for n, o in zip(d.price_usd, d.old_price)],
    )
    events = pd.concat([added, removed, changed]).reset_index()
    if "old_price" not in events:
        events["old_price"] = pd.NA
    events["price_change"] = events.price_usd - events.old_price
    events["price_change_pct"] = events.price_change / events.old_price * 100
    order = {"New": 0, "Price drop": 1, "Price increase": 2, "Removed": 3}
    cols = ["change"] + [c for c in KEY_COLUMNS if c in events.columns] + ["old_price", "price_change", "price_change_pct"]
    return events.sort_values(["change", "category"], key=lambda s: s.map(order) if s.name == "change" else s)[cols]


def latest_changes():
    """Changes in the newest snapshot, each site compared with its own previous successful scrape.

    Returns (events, {source: previous snapshot time}, newest snapshot time) or None if < 2 snapshots.
    """
    snaps = list_snapshots()
    if len(snaps) < 2:
        return None
    t_new, p_new = snaps[-1]
    new = load_snapshot(p_new)
    older = [(t, load_snapshot(p)) for t, p in reversed(snaps[:-1])]
    parts, prev_times = [], {}
    for src in sorted(new.source.unique()):
        for t, old in older:
            if (old.source == src).any():
                parts.append(compare(old[old.source == src], new[new.source == src]))
                prev_times[src] = t
                break
    events = pd.concat(parts, ignore_index=True) if parts else compare(new.iloc[:0], new.iloc[:0])
    return events, prev_times, t_new


def listing_history() -> pd.DataFrame:
    """One row per listing ever seen: first/last seen, still online?, first vs latest price."""
    snaps = list_snapshots()
    if not snaps:
        return pd.DataFrame()
    frames = [load_snapshot(p).assign(seen_at=t) for t, p in snaps]
    all_rows = pd.concat(frames, ignore_index=True).sort_values("seen_at")
    latest_time = snaps[-1][0]
    latest_sources = set(frames[-1].source.unique())

    g = all_rows.groupby("listing_id")
    hist = g.last()[[c for c in KEY_COLUMNS if c != "listing_id"]].copy()
    hist["first_seen"] = g.seen_at.min()
    hist["last_seen"] = g.seen_at.max()
    hist["times_seen"] = g.seen_at.nunique()
    hist["first_price"] = g.price_usd.first()
    hist["price_change"] = hist.price_usd - hist.first_price
    hist["online_status"] = [
        "Online" if last == latest_time or src not in latest_sources else "Removed"
        for last, src in zip(hist.last_seen, hist.source)
    ]
    hist["days_online"] = (hist.last_seen - hist.first_seen).dt.days
    return hist.reset_index().sort_values(["online_status", "first_seen"], ascending=[True, False])


def inventory_over_time() -> pd.DataFrame:
    """Listing counts and median prices per snapshot, source, category and sale/rent."""
    rows = []
    for t, p in list_snapshots():
        d = load_snapshot(p)
        for (src, cat, lt), g in d.groupby(["source", "category", "listing_type"]):
            rows.append({"snapshot": t, "source": src, "category": cat, "listing_type": lt,
                         "listings": len(g), "median_price": g.price_usd.median(),
                         "median_usd_m2": g.price_per_m2.median()})
    return pd.DataFrame(rows)
