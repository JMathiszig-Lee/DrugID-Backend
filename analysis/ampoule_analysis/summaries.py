from __future__ import annotations

from itertools import permutations

import numpy as np
import pandas as pd

from .config import AnalysisConfig


def _quantile_interval(values: np.ndarray, alpha: float) -> tuple[float, float]:
    return (
        float(np.nanquantile(values, alpha / 2)),
        float(np.nanquantile(values, 1 - alpha / 2)),
    )


def participant_characteristics(participants: pd.DataFrame) -> pd.DataFrame:
    """Create an aggregate, manuscript-oriented participant characteristics table."""

    total = int(participants["participant_id"].nunique())
    rows: list[dict[str, object]] = []
    speciality_column = "speciality_label" if "speciality_label" in participants else "speciality"
    speciality = participants[speciality_column].astype("string").fillna("Not recorded")
    for level, count in speciality.value_counts(dropna=False).sort_index().items():
        rows.append(
            {
                "characteristic": "Clinical speciality",
                "level": str(level),
                "participants": int(count),
                "percent": 100 * int(count) / total if total else np.nan,
                "mean": np.nan,
                "standard_deviation": np.nan,
                "median": np.nan,
                "quartile_1": np.nan,
                "quartile_3": np.nan,
            }
        )

    experience = pd.to_numeric(participants.get("years_experience"), errors="coerce").dropna()
    rows.append(
        {
            "characteristic": "Years of clinical experience",
            "level": "Valid observations",
            "participants": int(len(experience)),
            "percent": 100 * len(experience) / total if total else np.nan,
            "mean": float(experience.mean()) if len(experience) else np.nan,
            "standard_deviation": float(experience.std(ddof=1)) if len(experience) > 1 else np.nan,
            "median": float(experience.median()) if len(experience) else np.nan,
            "quartile_1": float(experience.quantile(0.25)) if len(experience) else np.nan,
            "quartile_3": float(experience.quantile(0.75)) if len(experience) else np.nan,
        }
    )
    return pd.DataFrame(rows)


def participant_style_summary(trials: pd.DataFrame) -> pd.DataFrame:
    analysed = trials.loc[trials["result_present"] & ~trials["integrity_excluded"]].copy()
    rows: list[dict[str, object]] = []
    for (participant_id, style), subset in analysed.groupby(
        ["participant_id", "style"], observed=True
    ):
        correct_rts = subset.loc[subset["correct_response"], "analysis_rt_ms"]
        rows.append(
            {
                "participant_id": participant_id,
                "style": str(style),
                "trials": int(len(subset)),
                "accuracy": float(subset["correct"].mean()),
                "timeout_rate": float(subset["timed_out"].mean()),
                "response_rate": float(subset["responded"].mean()),
                "median_correct_rt_ms": (
                    float(correct_rts.median()) if not correct_rts.empty else np.nan
                ),
                "geometric_mean_correct_rt_ms": (
                    float(np.exp(np.log(correct_rts).mean())) if not correct_rts.empty else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def style_summary(trials: pd.DataFrame, config: AnalysisConfig) -> pd.DataFrame:
    participant = participant_style_summary(trials)
    rng = np.random.default_rng(config.bootstrap_seed)
    rows: list[dict[str, object]] = []
    metrics = (
        ("accuracy", "proportion"),
        ("timeout_rate", "proportion"),
        ("response_rate", "proportion"),
        ("median_correct_rt_ms", "ms"),
        ("geometric_mean_correct_rt_ms", "ms"),
    )
    for style in config.style_order:
        style_trials = trials.loc[trials["style"].astype(str).eq(style)]
        style_participants = participant.loc[participant["style"].eq(style)]
        for metric, unit in metrics:
            values = style_participants[metric].dropna().to_numpy(dtype=float)
            if not len(values):
                estimate = ci_low = ci_high = np.nan
            else:
                sampled = rng.choice(
                    values,
                    size=(config.bootstrap_iterations, len(values)),
                    replace=True,
                )
                if metric == "geometric_mean_correct_rt_ms":
                    estimate = float(np.exp(np.log(values).mean()))
                    samples = np.exp(np.log(sampled).mean(axis=1))
                else:
                    estimate = float(np.mean(values))
                    samples = sampled.mean(axis=1)
                ci_low, ci_high = _quantile_interval(samples, config.alpha)
            rows.append(
                {
                    "style": style,
                    "metric": metric,
                    "unit": unit,
                    "estimate": estimate,
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "participants": int(style_participants["participant_id"].nunique()),
                    "trials_generated": int(len(style_trials)),
                    "results_submitted": int(style_trials["result_present"].sum()),
                }
            )
    return pd.DataFrame(rows)


def training_summary(trials: pd.DataFrame, config: AnalysisConfig) -> pd.DataFrame:
    analysed = trials.loc[trials["result_present"] & ~trials["integrity_excluded"]].copy()
    boundaries = np.linspace(0, 1, config.training_bins + 1)
    labels = np.arange(1, config.training_bins + 1)
    analysed["training_bin"] = pd.cut(
        analysed["within_period_progress"],
        bins=boundaries,
        labels=labels,
        include_lowest=True,
    )
    per_participant = (
        analysed.groupby(["participant_id", "style", "training_bin"], observed=True)
        .agg(
            accuracy=("correct", "mean"),
            timeout_rate=("timed_out", "mean"),
            median_correct_rt_ms=("analysis_rt_ms", "median"),
            trials=("trial_id", "size"),
        )
        .reset_index()
    )
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(config.bootstrap_seed + 1)
    for (style, training_bin), subset in per_participant.groupby(
        ["style", "training_bin"], observed=True
    ):
        for metric in ("accuracy", "timeout_rate", "median_correct_rt_ms"):
            values = subset[metric].dropna().to_numpy(dtype=float)
            if not len(values):
                continue
            samples = rng.choice(
                values,
                size=(config.bootstrap_iterations, len(values)),
                replace=True,
            ).mean(axis=1)
            ci_low, ci_high = _quantile_interval(samples, config.alpha)
            rows.append(
                {
                    "style": str(style),
                    "training_bin": int(training_bin),
                    "progress_midpoint": (int(training_bin) - 0.5) / config.training_bins,
                    "metric": metric,
                    "estimate": float(values.mean()),
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "participants": int(
                        subset.loc[subset[metric].notna(), "participant_id"].nunique()
                    ),
                }
            )
    return pd.DataFrame(rows)


def order_balance(runs: pd.DataFrame, style_order: tuple[str, ...]) -> pd.DataFrame:
    assignments = runs[["run_id", "participant_id"]].copy()
    if "assigned_style_order" in runs:
        assignments["assigned_style_order"] = runs["assigned_style_order"]
    elif "group_order" in runs:
        assignments["assigned_style_order"] = runs["group_order"]
    else:
        assignments["assigned_style_order"] = ""

    def sequence_label(value: object) -> str:
        if pd.isna(value):
            return "Assignment unavailable"
        parts = [part.strip() for part in str(value).split("|") if part.strip()]
        return " → ".join(parts) if parts else "Assignment unavailable"

    assignments["sequence"] = assignments["assigned_style_order"].map(sequence_label)
    if "order_inferred" in runs:
        assignments["order_inferred"] = (
            runs["order_inferred"]
            .astype("string")
            .str.lower()
            .str.strip()
            .isin({"true", "1", "yes", "y", "t"})
        )
    else:
        assignments["order_inferred"] = False

    complete_sequences = {" → ".join(sequence) for sequence in permutations(style_order)}
    assignments["is_complete_assignment"] = assignments["sequence"].isin(complete_sequences)
    expected = " → ".join(style_order)
    result = (
        assignments.groupby(
            ["sequence", "order_inferred", "is_complete_assignment"],
            observed=True,
            dropna=False,
        )
        .agg(participants=("participant_id", "nunique"), runs=("run_id", "nunique"))
        .reset_index()
        .sort_values(["participants", "sequence"], ascending=[False, True])
    )
    result["is_reference_sequence"] = result["sequence"].eq(expected)
    return result
