"""Scrape Adma listings from Confidence Real Estate and JSK, save CSV + Excel report.

Usage:
    python scrape.py              # scrape both sites, write output/adma_listings.csv + .xlsx
    python scrape.py --from-csv   # only rebuild the Excel from the last CSV
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from report import build_workbook
from scrapers import confidence, jsk
from scrapers.common import COLUMNS

OUTPUT = Path(__file__).parent / "output"
CSV_PATH = OUTPUT / "adma_listings.csv"
XLSX_PATH = OUTPUT / "Adma_Real_Estate.xlsx"


def flag_cross_listings(df: pd.DataFrame) -> pd.Series:
    """The same property is often listed by both agencies. Flag land/villas with an identical
    area on the other site (and, for round sizes like 1,000 m², a price within 15%)."""
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
    rows = []
    for name, scraper in (("Confidence", confidence), ("JSK", jsk)):
        try:
            rows += scraper.scrape(log=log)
        except Exception as exc:  # one site failing shouldn't lose the other
            log(f"!! {name} scraper failed: {exc}")
    if not rows:
        raise RuntimeError("No listings scraped from either site")

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["also_listed_on"] = flag_cross_listings(df)
    df["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    OUTPUT.mkdir(exist_ok=True)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    save_excel(df, log)
    log(f"CSV saved:   {CSV_PATH}")
    return df


def save_excel(df: pd.DataFrame, log=print):
    try:
        build_workbook(df, XLSX_PATH)
        log(f"Excel saved: {XLSX_PATH}")
    except PermissionError:
        alt = XLSX_PATH.with_name(f"Adma_Real_Estate_{datetime.now():%Y%m%d_%H%M}.xlsx")
        build_workbook(df, alt)
        log(f"{XLSX_PATH.name} is open in Excel - saved to {alt.name} instead")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--from-csv" in sys.argv:  # rebuild the Excel from the last scrape, no network
        data = pd.read_csv(CSV_PATH)
        save_excel(data)
    else:
        data = run()
    print("\nSummary (Adma):")
    print(data.groupby(["listing_type", "category", "source"]).size().unstack(fill_value=0).to_string())
