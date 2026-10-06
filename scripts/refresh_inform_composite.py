"""Refresh the processed INFORM parquet on blob storage.

Reads the existing parquet, fetches fresh Risk + Severity,
and writes back a unified (iso3, year, month, year_month) table with
raw Risk + Severity columns. The composite is *not* materialized in
the parquet; it is computed on access by callers.

Incremental behaviour
---------------------
The DRMKC Trends endpoint's default workflow returns only the latest
INFORM Risk year (e.g. "INFORM Risk Mid 2026" returns 2026 only), so
older published Risk years exist only in the existing parquet. They
are preserved from it, and only the most-recent year is allowed to be
restated from a new fetch. INFORM Severity is full-refreshed every
run (cheap blob read) so late-arriving monthly rows are caught.

Scheduling this script (cron, GitHub Actions, Azure Function) is out
of scope here -- run it manually or wire it up separately.
"""

from __future__ import annotations

import sys
from datetime import date, timezone
from pathlib import Path

import ocha_stratus as stratus
import pandas as pd
from azure.core.exceptions import ResourceNotFoundError
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datasets.inform import (  # noqa: E402
    INFORM_BLOB_PATH,
    build_inform_frame,
    fetch_inform_risk,
    load_inform_severity,
)

load_dotenv()


def _load_existing() -> pd.DataFrame:
    try:
        df = stratus.load_parquet_from_blob(INFORM_BLOB_PATH)
    except ResourceNotFoundError as exc:
        raise FileNotFoundError(
            f"No existing parquet at {INFORM_BLOB_PATH}. It is the only copy of "
            "the frozen older INFORM Risk years (the DRMKC API returns only the "
            "latest year), so it cannot be rebuilt from scratch. Restore it from "
            "ds-cerf-3rm-app/processed/backups/ before re-running."
        ) from exc
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    df["year_month"] = df["year_month"].astype("period[M]")
    return df


def _merge_risk(
    fresh_risk: pd.DataFrame, existing: pd.DataFrame
) -> pd.DataFrame:
    """Preserve older Risk years from existing; adopt fresh for latest year.

    Keep existing rows for year < max_existing_year, take fresh rows
    for year >= max_existing_year (so the latest year gets restated
    if DRMKC updated it).
    """
    existing_risk = (
        existing[["iso3", "year", "inform_risk", "inform_ha",
                  "inform_vu", "inform_cc"]]
        .drop_duplicates(subset=["iso3", "year"])
    )
    max_year = int(existing_risk["year"].max())
    frozen = existing_risk[existing_risk["year"] < max_year]
    fresh = fresh_risk[fresh_risk["year"] >= max_year]
    return pd.concat([frozen, fresh], ignore_index=True)


def main() -> None:
    print("Loading existing INFORM parquet from blob...")
    existing = _load_existing()

    print("Fetching INFORM Risk from DRMKC API...")
    fresh_risk = fetch_inform_risk()
    print(f"  {len(fresh_risk)} rows, years {fresh_risk['year'].min()}"
          f"-{fresh_risk['year'].max()}")

    risk = _merge_risk(fresh_risk, existing)
    print(f"After merge: {len(risk)} Risk rows covering "
          f"{risk['year'].min()}-{risk['year'].max()}")

    # Forward-carry the latest published Risk assessment to the current
    # calendar year so the app can predict for the current year. INFORM
    # Risk YYYY+1 is typically published late in year YYYY with the latest
    # GNAYear being YYYY -- i.e. there's always a one-year lag between
    # calendar time and the latest available Risk score. Analysts use the
    # most recent score as the "current" assessment in practice.
    risk["risk_source_year"] = risk["year"].astype(int)
    current_year = date.today().year
    max_risk_year = int(risk["year"].max())
    if max_risk_year < current_year:
        latest = risk[risk["year"] == max_risk_year].copy()
        carried_frames = []
        for y in range(max_risk_year + 1, current_year + 1):
            carried = latest.copy()
            carried["year"] = y
            # risk_source_year stays as max_risk_year -- records the carry
            carried_frames.append(carried)
        risk = pd.concat([risk, *carried_frames], ignore_index=True)
        print(f"Forward-carried INFORM Risk {max_risk_year} to "
              f"{max_risk_year + 1}-{current_year} "
              f"({sum(len(f) for f in carried_frames)} rows added)")

    print("Loading INFORM Severity from blob...")
    severity = load_inform_severity()
    print(f"  {len(severity)} country-months, "
          f"{severity['year_month'].min()} to {severity['year_month'].max()}")

    print("Building unified frame (Risk expanded to monthly, joined with Severity)...")
    frame = build_inform_frame(risk, severity)
    frame["refreshed_at"] = pd.Timestamp.now(tz=timezone.utc).isoformat()

    # year_month is a PeriodDtype; parquet needs a str or timestamp.
    to_write = frame.copy()
    to_write["year_month"] = to_write["year_month"].astype(str)

    print(f"Writing {len(to_write)} rows to {INFORM_BLOB_PATH}...")
    stratus.upload_parquet_to_blob(to_write, INFORM_BLOB_PATH)
    print("Done.")


if __name__ == "__main__":
    main()
