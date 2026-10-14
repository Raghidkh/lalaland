"""Listings the user chose to hide (✕ in the dashboard).

Stored in output/hidden_listings.csv by listing_id, so they stay hidden across re-scrapes.
Hidden listings are left out of the dashboard and the Excel report, but never deleted from the
scraped data or the history snapshots - they can be restored at any time.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

HIDDEN_PATH = Path(__file__).parent / "output" / "hidden_listings.csv"
COLUMNS = ["listing_id", "hidden_at", "source", "ref", "category", "title", "price_usd", "url"]


def load() -> pd.DataFrame:
    if not HIDDEN_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(HIDDEN_PATH, dtype={"listing_id": str, "ref": str})


def ids() -> set[str]:
    return set(load().listing_id)


def hide(listings: pd.DataFrame):
    """Hide the given rows (needs at least listing_id; other columns are kept for reference)."""
    current = load()
    new = listings[~listings.listing_id.isin(current.listing_id)].copy()
    if new.empty:
        return
    new["hidden_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save(pd.concat([current, new.reindex(columns=COLUMNS)], ignore_index=True))


def restore(listing_ids):
    current = load()
    _save(current[~current.listing_id.isin(set(listing_ids))])


def _save(frame: pd.DataFrame):
    HIDDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(HIDDEN_PATH, index=False, encoding="utf-8-sig")
