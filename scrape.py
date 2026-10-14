"""Scrape Adma listings from Confidence Real Estate, JSK and OLX; save CSV, history snapshot + Excel.

Usage:
    python scrape.py              # scrape all sites, write output/adma_listings.csv + .xlsx + snapshot
    python scrape.py --from-csv   # only rebuild the Excel from the last CSV
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import hidden
import history
import research
from report import build_workbook
from scrapers import confidence, jsk, olx
from scrapers.common import COLUMNS

OUTPUT = Path(__file__).parent / "output"
CSV_PATH = OUTPUT / "adma_listings.csv"
XLSX_PATH = OUTPUT / "Adma_Real_Estate.xlsx"


def flag_cross_listings(df: pd.DataFrame) -> pd.Series:
    """The same property is often listed by several agencies/sites. Flag land/villas with an identical
    area on another site (and, for round sizes like 1,000 m², a price within 15%)."""
    notes = []
    for row in df.itertuples():
        note = None
        if row.category in ("Land", "Villa") and pd.notna(row.area_m2):
            others = df[(df.source != row.source) & (df.category == row.category)
                        & (df.listing_type == row.listing_type) & (df.area_m2 == row.area_m2)]
            if row.area_m2 % 50 == 0 and pd.notna(row.price_usd):
                others = others[(others.price_usd - row.price_usd).abs() <= 0.15 * row.price_usd]
            if len(others):
                note = "; ".join(f"{o.source} {o.ref} (${o.price_usd:,.0f})" for o in others.itertuples())
        notes.append(note)
    return pd.Series(notes, index=df.index)


def run(log=print) -> pd.DataFrame:
    rows, failed = [], []
    for name, scraper in (("Confidence", confidence), ("JSK", jsk), ("OLX", olx)):
        try:
            rows += scraper.scrape(log=log)
        except Exception as exc:  # one site failing shouldn't lose the others
            log(f"!! {name} scraper failed: {exc}")
            failed.append(name)
    if not rows:
        raise RuntimeError("No listings scraped from any site")

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    OUTPUT.mkdir(exist_ok=True)
    seed_history_from_last_csv(log)
    snap = history.save_snapshot(df)  # only what was actually scraped now

    # Keep a failed site's previous listings in the report/dashboard (not in the history snapshot).
    if failed and CSV_PATH.exists():
        prev = history.add_listing_ids(pd.read_csv(CSV_PATH))
        carried = prev[prev.source.isin(failed)]
        if len(carried):
            df = pd.concat([df, carried[[c for c in df.columns if c in carried.columns]]], ignore_index=True)
            log(f"Kept {len(carried)} listings from the previous scrape for: {', '.join(failed)}")
    df["also_listed_on"] = flag_cross_listings(df)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    save_excel(df, log)
    log(f"CSV saved:   {CSV_PATH}")
    log(f"Snapshot:    {snap.name} ({len(history.list_snapshots())} in history)")
    return df


def seed_history_from_last_csv(log=print):
    """First run with history: keep the previous scrape as the first snapshot so changes show immediately."""
    if history.list_snapshots() or not CSV_PATH.exists():
        return
    old = pd.read_csv(CSV_PATH)
    when = pd.to_datetime(old.scraped_at.iloc[0]).to_pydatetime() if "scraped_at" in old else datetime.now()
    history.save_snapshot(old, when)
    log(f"History started from the previous scrape ({when:%Y-%m-%d %H:%M})")


def save_excel(df: pd.DataFrame, log=print):
    hidden_rows = hidden.load()  # listings hidden with ✕ in the dashboard stay out of the report
    df = research.enrich(history.add_listing_ids(df))  # duplicates, fair price, rent & yield
    df = df[~df.listing_id.isin(hidden_rows.listing_id)]
    try:
        build_workbook(df, XLSX_PATH, hidden_rows)
        log(f"Excel saved: {XLSX_PATH}")
    except PermissionError:
        alt = XLSX_PATH.with_name(f"Adma_Real_Estate_{datetime.now():%Y%m%d_%H%M}.xlsx")
        build_workbook(df, alt, hidden_rows)
        log(f"{XLSX_PATH.name} is open in Excel - saved to {alt.name} instead")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--from-csv" in sys.argv:  # rebuild the Excel from the last scrape, no network
        data = history.add_listing_ids(pd.read_csv(CSV_PATH))
        save_excel(data)
    else:
        data = run()
    print("\nSummary (Adma):")
    print(data.groupby(["listing_type", "category", "source"]).size().unstack(fill_value=0).to_string())
