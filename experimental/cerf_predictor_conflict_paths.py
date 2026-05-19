"""Conflict-routing code paths from cerf_predictor.py, preserved for v2.

NOT RUNNABLE on its own. These cells were extracted from the v1 app
when the conflict-specific model paths were stripped. They're kept
here so anyone reviving the conflict model in v2 doesn't have to
reconstruct them from git history.

Origin:
    Pre-strip file:  git show 48f88da~1:app/cerf_predictor.py
    Strip commit:    48f88da  feat: strip conflict-model code paths ... for v1

Companion archived modules:
    experimental/datasets/conflict.py    (load_conflict_training_frame)
    experimental/models/cerf_conflict.py (Models A/B + REGRESSORS + fit/predict)

What's preserved in this file:
    1. _load_conflict_context              (whole cell — was removed)
    2. _derive_conflict_context            (whole cell — was removed)
    3. _conflict_context_panel             (whole cell — was removed)
    4. FRAGMENTS to merge back into existing v1 cells:
       - additions to _load_data
       - the full _predict_cell with conflict branch
       - signature/body change to _prediction_layout
       - args/content additions to _technical_note

To re-enable conflict-specific modeling in a future v2:
    1. git mv experimental/datasets/conflict.py     src/datasets/
       git mv experimental/models/cerf_conflict.py  src/models/
    2. In app/cerf_predictor.py:
       a. Apply the FRAGMENT_LOAD_DATA additions to _load_data.
       b. Paste the 3 cells below back into the file in their original
          positions (load_conflict_context between _load_data and _intro;
          derive_conflict_context after _derive_composite; context_panel
          after _prediction_plot).
       c. Replace v1 _predict_cell with the FRAGMENT_PREDICT_CELL below.
       d. Apply FRAGMENT_PREDICTION_LAYOUT to add conflict_panel.
       e. Apply FRAGMENT_TECHNICAL_NOTE to restore conflict model rows
          + paragraphs.
    3. Verify ocha_stratus has Azure creds for stage="dev",
       container_name="global" (ACLED + IDMC parquets).

Important context:
    The trained INFORM-base model already knows "DisplConfl" as one of
    its 8 emergency-type dummies (src/models/cerf_inform.py). The
    conflict-specific Models A and B use ADDITIONAL regressors that
    the INFORM model does not:
        ln(monthly_fatalities + 1)  -- from ACLED
        ln(idps_30d + 1)            -- from IDMC
    That's the whole point of the separate conflict model — extra
    covariates only available for DisplConfl events.
"""

import marimo

app = marimo.App(width="medium")


# ===========================================================================
# CELL 1 — _load_conflict_context  (was at lines 126-147 of pre-strip)
# Standalone cell. Paste back as-is after _load_data.
# ===========================================================================
@app.cell
def _load_conflict_context():
    """Load small lookup parquets used only when emergency is DisplConfl.

    ACLED:  global/acled/monthly_fatalities.parquet (~25k rows)
    IDMC:   global/idmc/displacement_daily.parquet (Conflict-only, ~177k rows)

    Both are pre-aggregated by `scripts/refresh_acled_monthly.py` and
    `scripts/refresh_idmc_displacement.py`; the app just reads them.
    """
    import ocha_stratus as stratus

    acled_monthly = stratus.load_parquet_from_blob(
        "acled/monthly_fatalities.parquet",
        stage="dev", container_name="global",
    )
    idmc_daily = stratus.load_parquet_from_blob(
        "idmc/displacement_daily.parquet",
        stage="dev", container_name="global",
    )
    idmc_daily = idmc_daily[idmc_daily["displacement_type"] == "Conflict"].copy()
    return acled_monthly, idmc_daily


# ===========================================================================
# CELL 2 — _derive_conflict_context  (was at lines 350-400 of pre-strip)
# Standalone cell. Paste back as-is after _derive_composite.
# ===========================================================================
@app.cell
def _derive_conflict_context(
    acled_monthly, country, emergency, idmc_daily, month, year,
):
    """Auto-lookup ACLED monthly fatalities + IDMC 30d at the alloc-period.

    Active only when emergency type == DisplConfl. Otherwise returns
    `{"active": False}` and the prediction path uses the INFORM-base model.

    For the IDMC lookup we need a specific date; user picks year + month.
    We use the **last day of the selected month** (most recent IDMC
    snapshot for that period). If month is "annual", we fall back to
    Dec 31 of the year.
    """
    import calendar as _cal
    import pandas as _pd

    if emergency.value != "DisplConfl":
        conflict_ctx = {"active": False, "fatalities": 0.0, "idps_30d": 0.0,
                        "missing_acled": False, "missing_idmc": False,
                        "lookup_date": None}
    else:
        _yr = int(year.value)
        _mo = 12 if month.value == "none" else int(month.value)
        _last_day = _cal.monthrange(_yr, _mo)[1]
        _lookup_date = _pd.Timestamp(year=_yr, month=_mo, day=_last_day)

        _ac = acled_monthly[
            (acled_monthly["iso3"] == country.value)
            & (acled_monthly["year"] == _yr)
            & (acled_monthly["month"] == _mo)
        ]
        _fat = float(_ac["fatalities"].iloc[0]) if len(_ac) else 0.0
        _missing_acled = len(_ac) == 0

        _idmc = idmc_daily[
            (idmc_daily["iso3"] == country.value)
            & (idmc_daily["date"] == _lookup_date)
        ]
        _idp = float(_idmc["displacement_30d"].iloc[0]) if len(_idmc) else 0.0
        _missing_idmc = len(_idmc) == 0

        conflict_ctx = {
            "active": True,
            "fatalities": _fat,
            "idps_30d": _idp,
            "missing_acled": _missing_acled,
            "missing_idmc": _missing_idmc,
            "lookup_date": _lookup_date,
        }
    return (conflict_ctx,)


# ===========================================================================
# CELL 3 — _conflict_context_panel  (was at lines 603-637 of pre-strip)
# Standalone cell. Paste back as-is after _prediction_plot.
# ===========================================================================
@app.cell
def _conflict_context_panel(conflict_ctx, country, mo):
    """Display the auto-looked-up ACLED + IDMC values when in conflict mode."""
    def _fmt(v: float) -> str:
        if v >= 1e6:
            return f"{v / 1e6:.2f}M"
        if v >= 1e3:
            return f"{v / 1e3:.1f}K"
        return f"{v:.0f}"

    if not conflict_ctx["active"]:
        conflict_panel = mo.md("")
    else:
        _date_label = (conflict_ctx["lookup_date"].strftime("%b %Y")
                       if conflict_ctx["lookup_date"] is not None else "—")
        _fat_note = (" <span style='color:#c46;font-size:0.85em;'>(no events recorded)</span>"
                     if conflict_ctx["missing_acled"] else "")
        _idp_note = (" <span style='color:#c46;font-size:0.85em;'>(no IDMC record)</span>"
                     if conflict_ctx["missing_idmc"] else "")
        conflict_panel = mo.Html(
            f"""
<div style="background:#fdf6ec;border-left:3px solid #d9a43a;
            padding:10px 14px;border-radius:4px;font-size:0.9em;
            color:#333;margin-bottom:8px;display:inline-block;">
  <div style="font-size:0.7em;text-transform:uppercase;letter-spacing:0.05em;
              color:#7a5d1a;font-weight:600;margin-bottom:4px;">
    Auto-looked-up conflict covariates &nbsp;·&nbsp; {country.value} &nbsp;·&nbsp; {_date_label}
  </div>
  <span><b>ACLED monthly fatalities:</b> {_fmt(conflict_ctx['fatalities'])}{_fat_note}</span>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <span><b>IDMC IDPs (30-day rolling):</b> {_fmt(conflict_ctx['idps_30d'])}{_idp_note}</span>
</div>
"""
        )
    return (conflict_panel,)


# ===========================================================================
# FRAGMENT_PREDICT_CELL — full pre-strip _predict_cell with conflict branch.
# Replaces v1 _predict_cell entirely (don't merge — overwrite).
# ===========================================================================
@app.cell
def _predict_cell(
    REGRESSORS,
    REGRESSORS_NO_TARGETED,
    cerf_conflict,
    conflict_ctx,
    emergency,
    funding,
    lookup,
    model,
    model_conflict_a,
    model_conflict_b,
    model_no_t,
    predict,
    targeted,
):
    """Pick the right model and produce a prediction.

    Routing matrix:
        emergency_type     | targeted > 0  | model
        ───────────────────┼───────────────┼──────────────────
        DisplConfl         | yes           | conflict A
        DisplConfl         | no            | conflict B
        anything else      | yes           | INFORM (with targeted)
        anything else      | no            | INFORM (no targeted)
    """
    is_conflict = emergency.value == "DisplConfl"
    has_targeted = targeted.value is not None and float(targeted.value) > 0

    state = "ok"
    result = None
    active_model = None

    if lookup is None:
        state = "no_inform"
    elif funding.value is None or float(funding.value) <= 0:
        state = "missing_inputs"
    else:
        if is_conflict:
            if has_targeted:
                _chosen = model_conflict_a
                _regs = cerf_conflict.REGRESSORS_A
                _label = "Conflict, with Targeted"
            else:
                _chosen = model_conflict_b
                _regs = cerf_conflict.REGRESSORS_B
                _label = "Conflict, without Targeted"
            result = cerf_conflict.predict(
                _chosen,
                {
                    "inform_composite": lookup["composite"],
                    "funding_required": float(funding.value),
                    "people_targeted": float(targeted.value or 0),
                    "monthly_fatalities": float(conflict_ctx["fatalities"]),
                    "idps_30d": float(conflict_ctx["idps_30d"]),
                },
                alpha=0.20, regressors=_regs,
            )
        else:
            if has_targeted:
                _chosen = model
                _regs = REGRESSORS
                _label = "INFORM-base, with Targeted"
            else:
                _chosen = model_no_t
                _regs = REGRESSORS_NO_TARGETED
                _label = "INFORM-base, without Targeted"
            result = predict(
                _chosen,
                {
                    "emergency_type": emergency.value,
                    "inform_composite": lookup["composite"],
                    "funding_required": float(funding.value),
                    "people_targeted": float(targeted.value or 0),
                },
                alpha=0.20, regressors=_regs,
            )
        active_model = {
            "label": _label,
            "n": int(_chosen.nobs),
            "adj_r2": float(_chosen.rsquared_adj),
            "aic": float(_chosen.aic),
        }
    return active_model, result, state


# ===========================================================================
# FRAGMENTS that aren't whole cells — copy/paste into existing v1 cells.
# Kept as strings (not executable) because they live inside other cells.
# ===========================================================================

FRAGMENT_LOAD_DATA = '''
# Add these imports inside _load_data:
from src.datasets.conflict import load_conflict_training_frame
from src.models import cerf_conflict

# After the INFORM-base fits, add these model fits:
# Conflict-specific models: read corrected live training frame from blob,
# filter to Xuan-corrected sample, fit Models A (w/ Targeted) and B.
conflict_df_full = load_conflict_training_frame()
conflict_df = conflict_df_full[~conflict_df_full["xuan_refugee_excluded"]]
model_conflict_a = cerf_conflict.fit_model(
    conflict_df, regressors=cerf_conflict.REGRESSORS_A
)
model_conflict_b = cerf_conflict.fit_model(
    conflict_df, regressors=cerf_conflict.REGRESSORS_B
)

# Add these to the return tuple of _load_data (alphabetical position):
#   cerf_conflict,
#   model_conflict_a,
#   model_conflict_b,
'''

FRAGMENT_PREDICTION_LAYOUT = '''
# Change _prediction_layout signature to include `conflict_panel`:
@app.cell
def _prediction_layout(banner, chart, conflict_panel, mo, numbers):
    mo.vstack(
        [
            mo.md("## Predicted allocation"),
            conflict_panel,   # <-- insert this line
            banner,
            mo.hstack(
                [chart, numbers],
                widths=[3, 1],
                gap=2,
                align="center",
                justify="start",
            ),
        ],
        gap=0.5,
    )
    return
'''

FRAGMENT_TECHNICAL_NOTE = '''
# Args: add model_conflict_a, model_conflict_b to _technical_note signature.
# Table: change "Two model variants" to "Four model variants" and add two
# rows after the existing two:

| Displacement & Conflict | provided | Conflict, with Targeted | {int(model_conflict_a.nobs)} | {model_conflict_a.rsquared_adj:.3f} | {model_conflict_a.aic:.1f} |
| Displacement & Conflict | left at 0 | Conflict, without Targeted | {int(model_conflict_b.nobs)} | {model_conflict_b.rsquared_adj:.3f} | {model_conflict_b.aic:.1f} |

# Add this paragraph after the without-Targeted paragraph:

The **conflict-specific** variants (Models A and B) are fit on a separate
training set of 97 conflict-typed allocations from 2018 onward
(ch. 02d), with monthly ACLED fatalities and 30-day IDMC IDPs as
additional regressors. The vulnerability index is `inform_composite`
(substituting for Finn's CIRV; ~1% Adj R² gap per ch. 02d).

# Add this Features paragraph after "Features (INFORM-base)":

**Features (Conflict).** INFORM Composite. ln(funding required).
ln(people targeted) when applicable. ln(monthly fatalities + 1).
ln(IDPs 30d + 1).

# Data sources addition (append to existing data-sources paragraph):

CERF conflict-model xlsx (Zimmermann 2025); ACLED conflict events via
hdx-signals; IDMC daily IDP updates (refreshed by
`scripts/refresh_idmc_displacement.py`).
'''
