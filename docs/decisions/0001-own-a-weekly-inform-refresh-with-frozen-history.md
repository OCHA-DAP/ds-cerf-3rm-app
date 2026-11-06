---
status: accepted
date: 2026-05-20  # amended 2026-10-06 (fail loudly on the existing-parquet read)
decision-makers: ["@zackarno"]
consulted: []
informed: OCHA CHD Data Science team
---

# Own a weekly INFORM refresh here, freezing published Risk years and forward-carrying the latest

## Context and Problem Statement

The estimator needs an INFORM Composite (mean of INFORM Risk and INFORM
Severity) for any country and month an analyst picks, including the current
one. Risk is annual and lags by about a year; Severity is monthly. The app was
ported from `ds-storm-impact-harmonisation`, which built the processed parquet
by hand and never scheduled it. Something has to keep
`ds-cerf-3rm-app/processed/inform.parquet` current, and decide what "current"
means when Risk for the present year does not exist yet.

A second problem surfaced in October 2026: the DRMKC API's default workflow
now returns **only the latest Risk year** (2026). The 2016–2025 history the
model is trained on exists solely in our parquet.

## Considered Options

* **A — Weekly refresh script owned by this repo**, writing one parquet:
  older Risk years frozen from the existing file, only the latest year
  restated from the API, the latest year forward-carried to the current
  calendar year, Severity fully re-read every run.
* **B — Read the upstream sources at app startup**, no processed parquet.
* **C — Leave the refresh in the research repo** it came from.
* **D — Daily cadence** instead of weekly.
* **E — On a failed read of the existing parquet, rebuild from the API**
  (the original script's behaviour).

## Decision Outcome

Chosen: **A**, on a Monday 00:00 UTC cron (`.github/workflows/refresh-inform.yml`).

* B — rejected: the DRMKC call plus the Severity parquet add seconds to every
  session start, and since the API now returns only one year, startup could not
  reconstruct the training history at all.
* C — rejected: ADR 0006/0007 in `ds-storm-impact-harmonisation` moved all 3RM
  code out of that repo; the only producer of a blob should sit with its
  consumer.
* D — rejected: Risk republishes annually and Severity monthly, so weekly
  catches a new Severity month within seven days at a seventh of the runs.
* E — rejected (amendment, PR #4): with the API returning one year, "rebuild
  from scratch" on a transient auth or network error would silently replace
  eleven years of Risk with one. The script now raises on anything except a
  genuine blob-not-found, and tells the operator to restore from
  `processed/backups/`.

Forward-carry is deliberate: analysts treat the most recent Risk score as the
current one. The parquet records `risk_source_year` so the app can show a
"carried" warning, and training (`build_training_frame`) drops carried rows so
the model only ever fits real assessments.

### Consequences

* Good, because the app reads one small parquet and the composite rule lives in
  one helper shared by refresh, training and prediction.
* Good, because a bad run is red in Actions rather than a quietly degraded blob.
* Bad, because the parquet is now the only copy of Risk 2016–2025. Keep the
  backup under `ds-cerf-3rm-app/processed/backups/` and take a new one before
  any change to the merge logic.
* Bad, because the workflow needs the dev **write** SAS
  (`DSCI_AZ_BLOB_DEV_SAS_WRITE`) as well as the read tokens; it failed on every
  scheduled run from 2026-08-31 to 2026-11-02 for lack of it (PR #3).

## More Information

* Commit b3a2ecb (ownership + cadence), PR #3 (write SAS), PR #4 (fail loudly).
* `scripts/refresh_inform_composite.py`, `src/datasets/inform.py`.
* Upstream Severity: `hdx-signals` ACAPS monitor (prod blob
  `hdx-signals/output/acaps_inform_severity/raw.parquet`).
