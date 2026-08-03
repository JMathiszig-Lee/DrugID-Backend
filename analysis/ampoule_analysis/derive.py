from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AnalysisConfig
from .validate import Snapshot, SnapshotValidationError

STYLE_ALIASES = {
    "1": "Industry",
    "industry": "Industry",
    "pharma": "Industry",
    "2": "ISO",
    "iso": "ISO",
    "3": "Black and white",
    "black and white": "Black and white",
    "black & white": "Black and white",
    "blackwhite": "Black and white",
}
TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f", "", "<na>", "nan", "none"}


def _boolean(series: pd.Series, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.fillna(False).astype(bool)
    normalized = series.astype("string").str.lower().str.strip()
    unknown = set(normalized.dropna().unique()) - TRUE_VALUES - FALSE_VALUES
    if unknown:
        raise SnapshotValidationError(f"{name} contains invalid booleans: {sorted(unknown)}")
    return normalized.isin(TRUE_VALUES)


def _normalize_style(value: object) -> str:
    key = str(value).strip().lower()
    return STYLE_ALIASES.get(key, str(value).strip())


def derive_trials(snapshot: Snapshot, config: AnalysisConfig) -> pd.DataFrame:
    trials = snapshot.trials.copy()
    trials["style"] = trials["style"].map(_normalize_style)
    unknown_styles = set(trials["style"].dropna()) - set(config.style_order)
    if unknown_styles:
        raise SnapshotValidationError(f"Unknown display styles: {sorted(unknown_styles)}")
    trials["style"] = pd.Categorical(trials["style"], categories=config.style_order, ordered=True)

    for column in ("result_present", "timed_out", "correct"):
        trials[column] = _boolean(trials[column], column)
    if "responded" in trials:
        trials["responded"] = _boolean(trials["responded"], "responded")
    elif "response_event" in trials:
        trials["responded"] = _boolean(trials["response_event"], "response_event")
    else:
        trials["responded"] = trials["result_present"] & ~trials["timed_out"]

    for column in ("protocol_version", "period", "trial_index", "time_limit_ms"):
        trials[column] = pd.to_numeric(trials[column], errors="coerce")
    if "observed_rt_ms" not in trials:
        if "response_time_ms" in trials:
            trials["observed_rt_ms"] = trials["response_time_ms"]
        elif "time" in trials:
            trials["observed_rt_ms"] = trials["time"]
        else:
            trials["observed_rt_ms"] = pd.NA
    trials["observed_rt_ms"] = pd.to_numeric(trials["observed_rt_ms"], errors="coerce")

    invalid_timeout_rt = trials["timed_out"] & trials["observed_rt_ms"].notna()
    if invalid_timeout_rt.any():
        # A stored deadline is censoring information, never an observed reaction time.
        trials.loc[invalid_timeout_rt, "observed_rt_ms"] = np.nan
    trials.loc[~trials["responded"], "observed_rt_ms"] = np.nan
    invalid_observed = trials["responded"] & (
        trials["observed_rt_ms"].isna()
        | (trials["observed_rt_ms"] <= 0)
        | trials["time_limit_ms"].isna()
        | (trials["observed_rt_ms"] >= trials["time_limit_ms"])
    )
    trials["valid_observed_rt"] = ~invalid_observed & trials["responded"]
    trials["result_missing"] = ~trials["result_present"]
    trials["response_event"] = trials["responded"] & trials["valid_observed_rt"]
    trials["correct_response"] = (
        trials["result_present"]
        & trials["correct"]
        & ~trials["timed_out"]
        & trials["valid_observed_rt"]
    )
    if "exclusion_reason" in trials:
        acceptable_outcome_reasons = {"", "missing_result", "timeout", "incorrect"}

        def has_integrity_exclusion(row: pd.Series) -> bool:
            value = row["exclusion_reason"]
            text = "" if pd.isna(value) else str(value)
            reasons = {item.strip() for item in text.split(";")}
            acceptable = set(acceptable_outcome_reasons)
            if pd.to_numeric(row["protocol_version"], errors="coerce") < 2:
                # These are known limitations of the explicitly exploratory
                # legacy import, not reasons to discard every pilot row. Its
                # within-period order is derived deterministically below and
                # censoring uses each trial's preserved deadline rather than
                # the reconstructed run default.
                acceptable.update(
                    {
                        "legacy_pilot",
                        "trial_index_missing",
                        "trial_deadline_mismatch",
                    }
                )
                if bool(row["timed_out"]):
                    # Historic timeout rows did not retain the normalized
                    # response_time_ms representation used by protocol 2. The
                    # canonical export has already converted them to
                    # duration=deadline, event=0 and no observed RT.
                    acceptable.update({"invalid_response_time", "timeout_inconsistent"})
            return bool(reasons - acceptable)

        trials["integrity_excluded"] = trials.apply(has_integrity_exclusion, axis=1)
    else:
        trials["integrity_excluded"] = False
    trials["analysis_eligible"] = (
        trials["protocol_version"].ge(2) & trials["result_present"] & ~trials["integrity_excluded"]
    )
    trials["rt_primary_eligible"] = trials["analysis_eligible"] & trials["correct_response"]
    trials["duration_ms"] = trials["observed_rt_ms"]
    trials.loc[trials["timed_out"], "duration_ms"] = trials.loc[
        trials["timed_out"], "time_limit_ms"
    ]
    trials["analysis_rt_ms"] = trials["observed_rt_ms"].where(trials["correct_response"])
    trials["log_rt"] = np.nan
    correct_rt = trials["analysis_rt_ms"].notna() & trials["analysis_rt_ms"].gt(0)
    trials.loc[correct_rt, "log_rt"] = np.log(
        trials.loc[correct_rt, "analysis_rt_ms"].astype(float)
    )
    trials["log_response_rt"] = np.nan
    observed_rt = trials["valid_observed_rt"] & trials["observed_rt_ms"].gt(0)
    trials.loc[observed_rt, "log_response_rt"] = np.log(
        trials.loc[observed_rt, "observed_rt_ms"].astype(float)
    )

    # Canonical exports are one-based; tolerate zero-based external fixtures.
    per_period_min = trials.groupby("period_id", observed=True)["trial_index"].transform("min")
    # Unassigned legacy trials have no period/index and remain missing.
    one_based = per_period_min.ge(1).fillna(True)
    normalized_trial_number = trials["trial_index"] + (~one_based).astype(int)
    inferred_trial_number = trials.groupby("period_id", observed=True).cumcount() + 1
    trials["trial_order_inferred"] = normalized_trial_number.isna() & trials["period_id"].notna()
    trials["trial_number"] = normalized_trial_number.fillna(inferred_trial_number)
    period_size = trials.groupby("period_id", observed=True)["trial_number"].transform("max")
    if "planned_trials" in snapshot.periods:
        planned_by_period = pd.to_numeric(
            snapshot.periods.set_index("period_id")["planned_trials"],
            errors="coerce",
        )
        planned_period_size = trials["period_id"].map(planned_by_period)
    else:
        planned_period_size = pd.Series(np.nan, index=trials.index, dtype=float)
    valid_planned_period = planned_period_size.ge(1)
    trials["period_progress_denominator_inferred"] = ~valid_planned_period
    trials["planned_trials"] = planned_period_size.where(valid_planned_period, period_size)
    denominator = (trials["planned_trials"] - 1).clip(lower=1)
    trials["within_period_progress"] = (trials["trial_number"] - 1) / denominator
    trials["within_period_progress"] = trials["within_period_progress"].clip(0, 1)

    if "global_trial_index" in trials:
        global_number = pd.to_numeric(trials["global_trial_index"], errors="coerce")
        minimum_global_number = global_number.min(skipna=True)
        if pd.notna(minimum_global_number) and minimum_global_number == 0:
            global_number = global_number + 1
    else:
        trials = trials.sort_values(["participant_id", "period", "trial_number", "trial_id"])
        global_number = trials.groupby("run_id", observed=True).cumcount() + 1
    inferred_global_number = trials.groupby("run_id", observed=True).cumcount() + 1
    trials["global_order_inferred"] = global_number.isna() & trials["run_id"].notna()
    global_number = global_number.fillna(inferred_global_number)
    run_size = trials.groupby("run_id", observed=True)["trial_id"].transform("size")
    planned_run_size = pd.Series(np.nan, index=trials.index, dtype=float)
    if "total_trials_planned" in snapshot.runs:
        total_by_run = pd.to_numeric(
            snapshot.runs.set_index("run_id")["total_trials_planned"],
            errors="coerce",
        )
        planned_run_size = trials["run_id"].map(total_by_run)
    elif "trials_per_group" in snapshot.runs:
        per_group_by_run = pd.to_numeric(
            snapshot.runs.set_index("run_id")["trials_per_group"],
            errors="coerce",
        )
        planned_run_size = trials["run_id"].map(per_group_by_run) * 3
    valid_planned_run = planned_run_size.ge(1)
    trials["global_progress_denominator_inferred"] = ~valid_planned_run
    trials["total_trials_planned"] = planned_run_size.where(valid_planned_run, run_size)
    trials["global_trial_number"] = global_number
    trials["global_trial_progress"] = (global_number - 1) / (
        trials["total_trials_planned"] - 1
    ).clip(lower=1)
    trials["global_trial_progress"] = trials["global_trial_progress"].clip(0, 1)

    if "configuration_signature" not in trials:
        signature_columns = [column for column in ("time_limit_ms",) if column in trials]
        trials["configuration_signature"] = (
            trials[signature_columns].astype(str).agg("/".join, axis=1)
        )
    if "run_status" not in trials:
        status_column = "run_status" if "run_status" in snapshot.runs else "status"
        status_map = snapshot.runs.set_index("run_id").get(status_column)
        trials["run_status"] = (
            trials["run_id"].map(status_map) if status_map is not None else "unknown"
        )
    trials["complete_run"] = trials["run_status"].astype(str).eq("completed")
    trials["plausible_rt"] = trials["observed_rt_ms"].ge(config.minimum_plausible_rt_ms)
    return trials.sort_values(
        ["participant_id", "run_id", "period", "trial_number", "trial_id"]
    ).reset_index(drop=True)


def participant_flow(snapshot: Snapshot, trials: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    registered = snapshot.participants
    runs = snapshot.runs

    rows.append(
        {
            "stage": "registered",
            "participants": int(registered["participant_id"].nunique()),
            "runs": 0,
            "trials": 0,
        }
    )
    rows.append(
        {
            "stage": "study run created",
            "participants": int(runs["participant_id"].nunique()),
            "runs": int(runs["run_id"].nunique()),
            "trials": 0,
        }
    )
    stages = (
        ("trial generated", trials),
        ("result submitted", trials.loc[trials["result_present"]]),
        ("response observed", trials.loc[trials["valid_observed_rt"]]),
        ("correct response", trials.loc[trials["correct_response"]]),
    )
    for stage, subset in stages:
        rows.append(
            {
                "stage": stage,
                "participants": int(subset["participant_id"].nunique()),
                "runs": int(subset["run_id"].nunique()),
                "trials": int(len(subset)),
            }
        )

    if "run_complete" in runs:
        complete_mask = _boolean(runs["run_complete"], "run_complete")
    else:
        status_column = "run_status" if "run_status" in runs else "status"
        complete_mask = runs[status_column].astype(str).eq("completed")
    completed_runs = runs.loc[complete_mask]
    completed_run_ids = set(completed_runs["run_id"])
    complete_trials = trials.loc[trials["run_id"].isin(completed_run_ids)]
    rows.append(
        {
            "stage": "completed study run",
            "participants": int(completed_runs["participant_id"].nunique()),
            "runs": int(completed_runs["run_id"].nunique()),
            "trials": int(len(complete_trials)),
        }
    )
    return pd.DataFrame(rows)
