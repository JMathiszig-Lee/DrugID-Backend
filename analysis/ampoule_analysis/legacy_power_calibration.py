from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from patsy import dmatrix
from scipy.optimize import minimize
from scipy.special import expit, log_ndtr
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

STYLES = ("Industry", "ISO", "Black and white")
STYLE_PAIRS = (
    ("ISO", "Industry"),
    ("Black and white", "Industry"),
    ("Black and white", "ISO"),
)
REQUIRED_COLUMNS = {
    "participant_id",
    "protocol_version",
    "style",
    "period",
    "within_period_progress",
    "target_drug",
    "result_present",
    "response_event",
    "correct",
    "integrity_excluded",
    "observed_rt_ms",
    "time_limit_ms",
}
TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f"}


class LegacyCalibrationError(ValueError):
    """Raised when a derived legacy table cannot support the declared calibration."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_boolean(series: pd.Series, name: str) -> pd.Series:
    if series.isna().any():
        raise LegacyCalibrationError(f"{name} contains missing values")
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.astype(bool)
    normalized = series.astype("string").str.strip().str.lower()
    unknown = set(normalized.unique()) - TRUE_VALUES - FALSE_VALUES
    if unknown:
        raise LegacyCalibrationError(f"{name} contains values that are not boolean")
    return normalized.isin(TRUE_VALUES)


def _numeric(series: pd.Series, name: str, *, allow_missing: bool = False) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if not allow_missing and values.isna().any():
        raise LegacyCalibrationError(f"{name} contains missing or non-numeric values")
    finite = values.dropna().to_numpy(float)
    if not np.isfinite(finite).all():
        raise LegacyCalibrationError(f"{name} contains non-finite values")
    return values


def _read_and_validate(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not path.is_file():
        raise LegacyCalibrationError(f"Derived-trial table does not exist: {path}")
    if path.name != "derived_trials.csv":
        raise LegacyCalibrationError("Calibration input must be the pipeline's derived_trials.csv")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        try:
            header = next(csv.reader(handle))
        except StopIteration as exc:
            raise LegacyCalibrationError("Derived-trial table is empty") from exc
    if len(header) != len(set(header)):
        raise LegacyCalibrationError("Derived-trial table contains duplicate column names")
    missing = sorted(REQUIRED_COLUMNS - set(header))
    if missing:
        raise LegacyCalibrationError(f"Derived-trial table is missing required columns: {missing}")

    data = pd.read_csv(path, low_memory=False)
    if data.empty:
        raise LegacyCalibrationError("Derived-trial table contains no rows")
    for column in ("result_present", "response_event", "correct", "integrity_excluded"):
        data[column] = _parse_boolean(data[column], column)
    data["protocol_version"] = _numeric(data["protocol_version"], "protocol_version")
    if not data["protocol_version"].eq(1).all():
        raise LegacyCalibrationError(
            "Legacy calibration requires a protocol-1 derived_trials.csv with no mixed protocol"
        )

    valid = data.loc[data["result_present"] & ~data["integrity_excluded"]].copy()
    if valid.empty:
        raise LegacyCalibrationError("No valid submitted legacy outcomes remain after exclusions")
    for column in ("participant_id", "style", "target_drug"):
        if valid[column].isna().any() or valid[column].astype(str).str.strip().eq("").any():
            raise LegacyCalibrationError(f"Valid outcomes contain a missing {column}")
    unknown_styles = set(valid["style"].astype(str)) - set(STYLES)
    missing_styles = set(STYLES) - set(valid["style"].astype(str))
    if unknown_styles or missing_styles:
        raise LegacyCalibrationError(
            "Valid outcomes must contain exactly Industry, ISO and Black and white styles"
        )
    valid["style"] = pd.Categorical(valid["style"], categories=STYLES, ordered=True)
    for column in ("period", "within_period_progress", "time_limit_ms"):
        valid[column] = _numeric(valid[column], column)
    valid["observed_rt_ms"] = _numeric(
        valid["observed_rt_ms"], "observed_rt_ms", allow_missing=True
    )
    periods = set(valid["period"].astype(int))
    if periods != {1, 2, 3} or not np.equal(valid["period"], valid["period"].astype(int)).all():
        raise LegacyCalibrationError("Valid outcomes must use integer periods 1, 2 and 3")
    valid["period"] = valid["period"].astype(int)
    if not valid["within_period_progress"].between(0, 1, inclusive="both").all():
        raise LegacyCalibrationError("within_period_progress must be between zero and one")
    if not valid["time_limit_ms"].gt(0).all():
        raise LegacyCalibrationError("time_limit_ms must be positive")
    observed = valid["response_event"]
    if valid.loc[observed, "observed_rt_ms"].isna().any():
        raise LegacyCalibrationError("Observed responses must have an observed_rt_ms")
    if not valid.loc[observed, "observed_rt_ms"].gt(0).all():
        raise LegacyCalibrationError("Observed response times must be positive")
    if not (valid.loc[observed, "observed_rt_ms"] < valid.loc[observed, "time_limit_ms"]).all():
        raise LegacyCalibrationError("Observed response times must be below their trial deadline")
    if valid.loc[~observed, "observed_rt_ms"].notna().any():
        raise LegacyCalibrationError("Censored trials must not contain an observed response time")
    if (valid["correct"] & ~valid["response_event"]).any():
        raise LegacyCalibrationError("A correct outcome cannot occur without an observed response")
    if valid["participant_id"].nunique() < 6 or valid["target_drug"].nunique() < 2:
        raise LegacyCalibrationError(
            "Calibration requires at least six participants and two target drugs"
        )
    for style in STYLES:
        style_responses = valid.loc[valid["style"].eq(style) & observed]
        errors = (~style_responses["correct"]).sum()
        if len(style_responses) < 2 or errors == 0 or errors == len(style_responses):
            raise LegacyCalibrationError(
                f"{style} needs both correct and incorrect observed choices for calibration"
            )

    valid = valid.sort_values(
        ["participant_id", "target_drug", "style", "period", "within_period_progress"],
        kind="mergesort",
    ).reset_index(drop=True)
    return data, valid


def _conditional_error_model(valid: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    responses = valid.loc[valid["response_event"]].copy()
    responses["incorrect"] = (~responses["correct"]).astype(int)
    responses["period_linear"] = responses["period"] - 1
    model = BinomialBayesMixedGLM.from_formula(
        (
            "incorrect ~ C(style, Treatment(reference='Industry')) + "
            "period_linear + within_period_progress"
        ),
        {
            "participant": "0 + C(participant_id)",
            "target_drug": "0 + C(target_drug)",
        },
        responses,
        vcp_p=1,
        fe_p=2,
    )
    if np.linalg.matrix_rank(model.exog) != model.k_fep:
        raise LegacyCalibrationError("Conditional-error fixed-effect design is rank deficient")
    parameter_count = model.k_fep + model.k_vcp + model.k_vc
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = model.fit_vb(
            mean=np.zeros(parameter_count),
            sd=np.full(parameter_count, math.exp(-0.5)),
            verbose=False,
            minim_opts={"maxiter": 2000},
        )
    optimization = getattr(result, "optim_retvals", {})
    if not bool(optimization.get("success", False)):
        raise LegacyCalibrationError(
            f"Conditional-error variational fit failed: {optimization.get('message', 'unknown')}"
        )
    fixed = dict(zip(model.exog_names, result.fe_mean, strict=True))
    log_sd = dict(zip(model.vcp_names, result.vcp_mean, strict=True))
    iso_term = "C(style, Treatment(reference='Industry'))[T.ISO]"
    black_white_term = "C(style, Treatment(reference='Industry'))[T.Black and white]"
    coefficients = {
        "intercept": float(fixed["Intercept"]),
        "style_log_odds_iso_vs_industry": float(fixed[iso_term]),
        "style_log_odds_black_white_vs_industry": float(fixed[black_white_term]),
        "period_linear_log_odds_change": float(fixed["period_linear"]),
        "within_period_log_odds_change": float(fixed["within_period_progress"]),
    }
    probabilities = {
        "industry": float(expit(coefficients["intercept"])),
        "iso": float(
            expit(coefficients["intercept"] + coefficients["style_log_odds_iso_vs_industry"])
        ),
        "black_white": float(
            expit(
                coefficients["intercept"] + coefficients["style_log_odds_black_white_vs_industry"]
            )
        ),
    }
    warnings_seen = sorted({f"{item.category.__name__}: {item.message}" for item in caught})
    payload: dict[str, object] = {
        "method": (
            "Statsmodels BinomialBayesMixedGLM variational Bayes; incorrect choice among "
            "valid observed responses; participant and target-drug random intercepts"
        ),
        "formula": (
            "incorrect ~ style + linear period + within-period progress + "
            "(1|participant) + (1|target drug)"
        ),
        "observations": int(len(responses)),
        "incorrect_choices": int(responses["incorrect"].sum()),
        "participants": int(responses["participant_id"].nunique()),
        "target_drugs": int(responses["target_drug"].nunique()),
        "priors": {
            "fixed_effect_prior_sd": 2.0,
            "log_random_sd_prior_sd": 1.0,
        },
        "fixed_effects": coefficients,
        "conditional_incorrect_choice_probability_at_period_1_progress_0": probabilities,
        "random_intercept_log_sd": {
            "participant": float(log_sd["participant"]),
            "target_drug": float(log_sd["target_drug"]),
        },
        "random_intercept_sd": {
            "participant": float(math.exp(log_sd["participant"])),
            "target_drug": float(math.exp(log_sd["target_drug"])),
        },
        "simulator_training_parameters": {
            "period_log_odds_change": float(-coefficients["period_linear_log_odds_change"]),
            "within_period_log_odds_change": float(-coefficients["within_period_log_odds_change"]),
            "sign_convention": (
                "Positive simulator values are subtracted from incorrect-choice log odds"
            ),
        },
        "optimizer": {
            "name": "BFGS via fit_vb",
            "deterministic_start": "all posterior means 0; all posterior SDs exp(-0.5)",
            "success": True,
            "iterations": int(optimization.get("nit", 0)),
        },
        "fit_warnings": warnings_seen,
        "caveat": (
            "Only observed responses reveal the selected choice. With few errors and several "
            "zero-error participant/drug cells, random-effect SDs are prior-sensitive exploratory "
            "nuisance estimates, not precise variance components."
        ),
    }
    return payload, responses


def _censored_objective(
    theta: np.ndarray,
    design: np.ndarray,
    log_duration: np.ndarray,
    event: np.ndarray,
) -> tuple[float, np.ndarray]:
    coefficients = theta[:-1]
    log_sigma = theta[-1]
    sigma = math.exp(log_sigma)
    standardized = (log_duration - design @ coefficients) / sigma
    log_likelihood = np.empty(len(log_duration), dtype=float)
    log_likelihood[event] = (
        -0.5 * standardized[event] ** 2 - log_sigma - 0.5 * math.log(2 * math.pi)
    )
    log_likelihood[~event] = log_ndtr(-standardized[~event])

    inverse_mills = np.exp(
        np.clip(
            -0.5 * standardized[~event] ** 2
            - 0.5 * math.log(2 * math.pi)
            - log_ndtr(-standardized[~event]),
            -745,
            700,
        )
    )
    location_score = np.empty(len(log_duration), dtype=float)
    location_score[event] = standardized[event] / sigma
    location_score[~event] = inverse_mills / sigma
    coefficient_score = design.T @ location_score
    log_sigma_score = float(
        np.sum(standardized[event] ** 2 - 1) + np.sum(inverse_mills * standardized[~event])
    )
    return -float(log_likelihood.sum()), -np.r_[coefficient_score, log_sigma_score]


def _factor_values(coefficients: pd.Series, prefix: str, levels: int) -> np.ndarray:
    values = np.r_[0.0, coefficients[coefficients.index.str.startswith(prefix)].to_numpy(float)]
    if len(values) != levels:
        raise LegacyCalibrationError(f"Censored RT model did not estimate all {prefix} levels")
    return values


def _censored_rt_model(valid: pd.DataFrame) -> dict[str, object]:
    formula = (
        "1 + C(style, Treatment(reference='Industry')) + C(period) + "
        "within_period_progress + C(target_drug) + C(participant_id)"
    )
    design_frame = dmatrix(formula, valid, return_type="dataframe")
    design = design_frame.to_numpy(float)
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise LegacyCalibrationError("Censored RT fixed-effect design is rank deficient")
    event = valid["response_event"].to_numpy(bool)
    duration = np.where(
        event,
        valid["observed_rt_ms"].to_numpy(float),
        valid["time_limit_ms"].to_numpy(float),
    )
    log_duration = np.log(duration)
    initial_coefficients = np.linalg.lstsq(design[event], log_duration[event], rcond=None)[0]
    initial_residual = log_duration[event] - design[event] @ initial_coefficients
    initial_sigma = float(np.std(initial_residual))
    if not math.isfinite(initial_sigma) or initial_sigma <= 0:
        raise LegacyCalibrationError("Censored RT model has no positive starting residual SD")
    initial = np.r_[initial_coefficients, math.log(initial_sigma)]
    result = minimize(
        lambda values: _censored_objective(values, design, log_duration, event)[0],
        initial,
        jac=lambda values: _censored_objective(values, design, log_duration, event)[1],
        method="L-BFGS-B",
        bounds=[(None, None)] * design.shape[1] + [(-5.0, 3.0)],
        options={"maxiter": 5000, "ftol": 1e-12, "gtol": 1e-7, "maxls": 50},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise LegacyCalibrationError(f"Censored RT fit failed: {result.message}")
    coefficients = pd.Series(result.x[:-1], index=design_frame.columns, dtype=float)
    iso_term = "C(style, Treatment(reference='Industry'))[T.ISO]"
    black_white_term = "C(style, Treatment(reference='Industry'))[T.Black and white]"
    period_2 = float(coefficients["C(period)[T.2]"])
    period_3 = float(coefficients["C(period)[T.3]"])
    participant_values = _factor_values(
        coefficients, "C(participant_id)", valid["participant_id"].nunique()
    )
    drug_values = _factor_values(coefficients, "C(target_drug)", valid["target_drug"].nunique())
    centered_industry_intercept = float(
        coefficients["Intercept"] + participant_values.mean() + drug_values.mean()
    )
    style_ratios = {
        "industry": 1.0,
        "iso": float(math.exp(coefficients[iso_term])),
        "black_white": float(math.exp(coefficients[black_white_term])),
    }
    variance = {
        "participant_log_sd": float(np.std(participant_values, ddof=0)),
        "target_drug_log_sd": float(np.std(drug_values, ddof=0)),
        "residual_log_sd": float(math.exp(result.x[-1])),
    }
    payload: dict[str, object] = {
        "method": (
            "Right-censored Gaussian likelihood on log milliseconds; timeouts censored at each "
            "trial's preserved deadline; participant and target drug included as fixed effects"
        ),
        "formula": (
            "log(response time) ~ style + categorical period + within-period progress + "
            "target drug + participant"
        ),
        "observations": int(len(valid)),
        "response_events": int(event.sum()),
        "right_censored": int((~event).sum()),
        "fixed_effects": {
            "style_log_ratio_iso_vs_industry": float(coefficients[iso_term]),
            "style_log_ratio_black_white_vs_industry": float(coefficients[black_white_term]),
            "period_2_vs_1_log_change": period_2,
            "period_3_vs_1_log_change": period_3,
            "within_period_log_change": float(coefficients["within_period_progress"]),
        },
        "latent_style_geometric_mean_ratios": style_ratios,
        "mean_centered_industry_geometric_mean_ms_at_period_1_progress_0": float(
            math.exp(centered_industry_intercept)
        ),
        "variance_decomposition": variance,
        "simulator_training_parameters": {
            "period_log_change": period_3 / 2,
            "within_period_log_change": float(coefficients["within_period_progress"]),
            "period_method": (
                "One linear simulator step is half the fitted period-3-versus-period-1 contrast"
            ),
        },
        "optimizer": {
            "name": "scipy L-BFGS-B with analytic gradient",
            "success": True,
            "iterations": int(result.nit),
            "maximum_absolute_gradient": float(np.max(np.abs(result.jac))),
        },
        "caveat": (
            "Participant and drug SDs are the population SDs of mean-centered fixed-effect "
            "coefficients, not REML random-effect estimates. They are exploratory variance "
            f"decomposition inputs from {valid['participant_id'].nunique()} participants and "
            f"{valid['target_drug'].nunique()} legacy target labels."
        ),
    }
    return payload


def _raw_style_checks(valid: pd.DataFrame) -> dict[str, dict[str, object]]:
    checks: dict[str, dict[str, object]] = {}
    for style in STYLES:
        subset = valid.loc[valid["style"].eq(style)]
        responses = subset.loc[subset["response_event"]]
        incorrect = int((~responses["correct"]).sum())
        correct_rt = responses.loc[responses["correct"], "observed_rt_ms"]
        deadline_counts = {
            str(int(deadline)): int(count)
            for deadline, count in subset["time_limit_ms"].value_counts().sort_index().items()
        }
        checks[style] = {
            "participants": int(subset["participant_id"].nunique()),
            "valid_submitted_outcomes": int(len(subset)),
            "observed_responses": int(len(responses)),
            "timeouts_or_other_censored_responses": int((~subset["response_event"]).sum()),
            "correct_outcomes": int(subset["correct"].sum()),
            "incorrect_observed_choices": incorrect,
            "raw_conditional_incorrect_choice_probability": float(incorrect / len(responses)),
            "correct_response_geometric_mean_ms": float(
                math.exp(np.log(correct_rt.to_numpy(float)).mean())
            ),
            "deadline_ms_counts": deadline_counts,
        }
    return checks


def _cluster_style_contrasts(
    data: pd.DataFrame,
    cluster: str,
    unit_label: str,
) -> dict[str, object]:
    cells = data.groupby([cluster, "style"], observed=True).agg(
        responses=("incorrect", "size"),
        incorrect=("incorrect", "sum"),
        mean_log_rt=("log_observed_rt", "mean"),
    )
    cells["jeffreys_incorrect_log_odds"] = np.log(
        (cells["incorrect"] + 0.5) / (cells["responses"] - cells["incorrect"] + 0.5)
    )
    complete = cells.reset_index().groupby(cluster, observed=True)["style"].nunique()
    complete_ids = complete.index[complete.eq(len(STYLES))]
    if len(complete_ids) < 3:
        raise LegacyCalibrationError(
            f"{cluster}-by-style diagnostics need at least three clusters with all styles"
        )
    complete_cells = cells.loc[cells.index.get_level_values(cluster).isin(complete_ids)]

    def contrasts(column: str) -> tuple[dict[str, dict[str, float | int]], float]:
        wide = complete_cells[column].unstack("style").dropna()
        values: dict[str, dict[str, float | int]] = {}
        squared_sds = []
        for numerator, denominator in STYLE_PAIRS:
            difference = wide[numerator] - wide[denominator]
            standard_deviation = float(difference.std(ddof=1))
            squared_sds.append(standard_deviation**2)
            values[f"{numerator} vs {denominator}"] = {
                unit_label: int(len(difference)),
                "sample_sd": standard_deviation,
            }
        return values, float(math.sqrt(sum(squared_sds) / len(squared_sds)))

    rt_contrasts, rt_rms = contrasts("mean_log_rt")
    accuracy_contrasts, accuracy_rms = contrasts("jeffreys_incorrect_log_odds")
    cell_sizes = complete_cells["responses"].to_numpy(int)
    return {
        "clusters_with_all_three_styles": int(len(complete_ids)),
        "observed_responses_per_cell": {
            "minimum": int(cell_sizes.min()),
            "median": float(np.median(cell_sizes)),
            "maximum": int(cell_sizes.max()),
        },
        "zero_error_cells": int(complete_cells["incorrect"].eq(0).sum()),
        "log_rt_pairwise_contrast_sd": rt_contrasts,
        "log_rt_contrast_sd_root_mean_square": rt_rms,
        "implied_independent_style_log_sd": rt_rms / math.sqrt(2),
        "incorrect_log_odds_pairwise_contrast_sd": accuracy_contrasts,
        "incorrect_log_odds_contrast_sd_root_mean_square": accuracy_rms,
        "implied_independent_style_log_odds_sd": accuracy_rms / math.sqrt(2),
    }


def _participant_diagnostics(
    responses: pd.DataFrame,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    data = responses.copy()
    data["log_observed_rt"] = np.log(data["observed_rt_ms"].to_numpy(float))
    for column in ("incorrect", "log_observed_rt"):
        data[f"{column}_style_residual"] = data[column] - data.groupby("style", observed=True)[
            column
        ].transform("mean")
    participant_means = data.groupby("participant_id", observed=True).agg(
        incorrect_style_residual=("incorrect_style_residual", "mean"),
        log_rt_style_residual=("log_observed_rt_style_residual", "mean"),
    )
    correlation = float(
        participant_means["incorrect_style_residual"].corr(
            participant_means["log_rt_style_residual"], method="pearson"
        )
    )
    correlation_payload: dict[str, object] = {
        "participants": int(len(participant_means)),
        "pearson_correlation": correlation,
        "method": (
            "Subtract each style's row-level mean incorrect indicator and mean log observed RT; "
            "average each residual by participant; correlate the two participant means"
        ),
        "caveat": (
            "Crude observed-response diagnostic only: it ignores censoring, drug, period and "
            f"progress and is extremely unstable with {len(participant_means)} participants."
        ),
    }

    participant = _cluster_style_contrasts(data, "participant_id", "participants")
    implied_rt_sd = float(participant["implied_independent_style_log_sd"])
    implied_accuracy_sd = float(participant["implied_independent_style_log_odds_sd"])
    regularized_accuracy_sd = implied_accuracy_sd / math.sqrt(2)
    slopes_payload: dict[str, object] = {
        "participants_with_all_three_styles": participant["clusters_with_all_three_styles"],
        "observed_responses_per_participant_style_cell": participant["observed_responses_per_cell"],
        "zero_error_participant_style_cells": participant["zero_error_cells"],
        "log_rt_pairwise_contrast_sd": participant["log_rt_pairwise_contrast_sd"],
        "log_rt_contrast_sd_root_mean_square": participant["log_rt_contrast_sd_root_mean_square"],
        "implied_independent_participant_style_log_sd": implied_rt_sd,
        "incorrect_log_odds_pairwise_contrast_sd": participant[
            "incorrect_log_odds_pairwise_contrast_sd"
        ],
        "incorrect_log_odds_contrast_sd_root_mean_square": participant[
            "incorrect_log_odds_contrast_sd_root_mean_square"
        ],
        "implied_independent_participant_style_log_odds_sd": implied_accuracy_sd,
        "regularized_planning_participant_style_log_odds_sd": regularized_accuracy_sd,
        "regularization": (
            "The conditional-error implied SD is divided by sqrt(2) once more before use, "
            f"because only {int(data['incorrect'].sum())} errors create many zero-error cells; "
            "this is explicit shrinkage, not an estimated variance component."
        ),
        "caveat": (
            "These are non-identifying participant-by-style contrast diagnostics, not fitted "
            "random-slope variances. The legacy order is inferred and cell sizes are uneven."
        ),
    }

    drug = _cluster_style_contrasts(data, "target_drug", "target_drugs")
    drug_payload: dict[str, object] = {
        "target_drugs_with_all_three_styles": drug["clusters_with_all_three_styles"],
        "observed_responses_per_drug_style_cell": drug["observed_responses_per_cell"],
        "zero_error_drug_style_cells": drug["zero_error_cells"],
        "log_rt_pairwise_contrast_sd": drug["log_rt_pairwise_contrast_sd"],
        "log_rt_contrast_sd_root_mean_square": drug["log_rt_contrast_sd_root_mean_square"],
        "implied_independent_drug_style_log_sd": drug["implied_independent_style_log_sd"],
        "incorrect_log_odds_pairwise_contrast_sd": drug["incorrect_log_odds_pairwise_contrast_sd"],
        "incorrect_log_odds_contrast_sd_root_mean_square": drug[
            "incorrect_log_odds_contrast_sd_root_mean_square"
        ],
        "implied_independent_drug_style_log_odds_sd": drug["implied_independent_style_log_odds_sd"],
        "planning_drug_style_log_sd": 0.08,
        "planning_drug_style_log_odds_sd": 0.35,
        "planning_value_classification": "explicit regularized planning assumptions",
        "regularization": (
            "The raw contrast dispersion includes finite-cell sampling noise, unequal drug use, "
            "participant mix and deadline selection. A defensible noise subtraction is not "
            "identified by this small legacy table, especially for sparse binary errors. The "
            "configured 0.08 and 0.35 values are therefore conservative planning assumptions, "
            "not rounded variance-component estimates."
        ),
        "caveat": (
            "These aggregate target-drug-by-style contrasts do not fit a drug random-slope model "
            "and do not establish generalization to ampoules outside the tested set."
        ),
    }
    return correlation_payload, slopes_payload, drug_payload


def calibrate_legacy_power(input_path: str | Path) -> dict[str, object]:
    source = Path(input_path).resolve()
    all_rows, valid = _read_and_validate(source)
    conditional_error, responses = _conditional_error_model(valid)
    censored_rt = _censored_rt_model(valid)
    correlation, participant_slopes, drug_slopes = _participant_diagnostics(responses)
    conditional_probabilities = conditional_error[
        "conditional_incorrect_choice_probability_at_period_1_progress_0"
    ]
    assert isinstance(conditional_probabilities, dict)
    random_sd = conditional_error["random_intercept_sd"]
    assert isinstance(random_sd, dict)
    rt_ratios = censored_rt["latent_style_geometric_mean_ratios"]
    assert isinstance(rt_ratios, dict)
    rt_variance = censored_rt["variance_decomposition"]
    assert isinstance(rt_variance, dict)
    accuracy_training = conditional_error["simulator_training_parameters"]
    assert isinstance(accuracy_training, dict)
    rt_training = censored_rt["simulator_training_parameters"]
    assert isinstance(rt_training, dict)
    raw_checks = _raw_style_checks(valid)
    artifact: dict[str, object] = {
        "schema_version": "1.0",
        "status": "exploratory_legacy_protocol_1_calibration_not_for_recruitment",
        "source": {
            "kind": "pipeline derived_trials.csv in explicit legacy-pilot mode",
            "filename": "derived_trials.csv",
            "sha256": _sha256(source),
            "bytes": int(source.stat().st_size),
        },
        "implementation": {
            "module_sha256": _sha256(Path(__file__).resolve()),
            "python": platform.python_version(),
            "software_versions": {
                package: importlib.metadata.version(package)
                for package in ("numpy", "pandas", "patsy", "scipy", "statsmodels")
            },
        },
        "privacy": {
            "direct_identifiers_emitted": False,
            "pseudonymous_row_or_group_identifiers_emitted": False,
            "statement": (
                "Only aggregate counts, coefficients and diagnostics are written; participant "
                "and row identifiers are used transiently for clustering and are never emitted."
            ),
        },
        "counts": {
            "input_rows": int(len(all_rows)),
            "excluded_or_missing_outcome_rows": int(len(all_rows) - len(valid)),
            "valid_submitted_outcomes": int(len(valid)),
            "participants": int(valid["participant_id"].nunique()),
            "target_drug_labels": int(valid["target_drug"].nunique()),
            "observed_responses": int(valid["response_event"].sum()),
            "right_censored": int((~valid["response_event"]).sum()),
            "incorrect_observed_choices": int((~responses["correct"]).sum()),
            "correct_response_times": int((valid["response_event"] & valid["correct"]).sum()),
        },
        "raw_style_checks": raw_checks,
        "conditional_error_model": conditional_error,
        "censored_lognormal_response_time_model": censored_rt,
        "crude_participant_accuracy_rt_correlation": correlation,
        "participant_by_style_heterogeneity_diagnostics": participant_slopes,
        "drug_by_style_heterogeneity_diagnostics": drug_slopes,
        "power_legacy_pilot_toml_alignment": {
            "accuracy": {
                "incorrect_choice_probability_industry": round(
                    float(conditional_probabilities["industry"]), 3
                ),
                "incorrect_choice_probability_iso": round(
                    float(conditional_probabilities["iso"]), 3
                ),
                "incorrect_choice_probability_black_white": round(
                    float(conditional_probabilities["black_white"]), 3
                ),
                "participant_log_odds_sd": round(float(random_sd["participant"]), 2),
                "drug_log_odds_sd": round(float(random_sd["target_drug"]), 2),
                "participant_style_log_odds_sd": round(
                    float(participant_slopes["regularized_planning_participant_style_log_odds_sd"]),
                    2,
                ),
                "drug_style_log_odds_sd": float(drug_slopes["planning_drug_style_log_odds_sd"]),
                "period_log_odds_change": round(
                    float(accuracy_training["period_log_odds_change"]), 3
                ),
                "within_period_log_odds_change": round(
                    float(accuracy_training["within_period_log_odds_change"]), 3
                ),
            },
            "reaction_time": {
                "industry_geometric_mean_ms": round(
                    float(
                        censored_rt[
                            "mean_centered_industry_geometric_mean_ms_at_period_1_progress_0"
                        ]
                    )
                ),
                "geometric_mean_ratio_iso": round(float(rt_ratios["iso"]), 3),
                "geometric_mean_ratio_black_white": round(float(rt_ratios["black_white"]), 3),
                "participant_log_sd": round(float(rt_variance["participant_log_sd"]), 2),
                "drug_log_sd": round(float(rt_variance["target_drug_log_sd"]), 2),
                "residual_log_sd": round(float(rt_variance["residual_log_sd"]), 2),
                "participant_style_log_sd": round(
                    float(participant_slopes["implied_independent_participant_style_log_sd"]), 2
                ),
                "drug_style_log_sd": float(drug_slopes["planning_drug_style_log_sd"]),
                "participant_accuracy_rt_correlation": round(
                    float(correlation["pearson_correlation"]), 2
                ),
                "period_log_change": round(float(rt_training["period_log_change"]), 3),
                "within_period_log_change": round(
                    float(rt_training["within_period_log_change"]), 3
                ),
            },
            "rounding_statement": (
                "Fitted and crude diagnostic values reproduce the checked-in exploratory TOML "
                "after declared rounding or regularization. Drug-by-style values are explicitly "
                "classified as planning assumptions rather than aligned estimates."
            ),
        },
        "methodological_caveats": [
            "The source is early protocol-1 experimental data, not confirmatory protocol-2 data.",
            f"Only {valid['participant_id'].nunique()} participants contributed; style order was "
            "reconstructed and not verified.",
            "Historical deadlines are handled trial by trial rather than replaced by one value.",
            "Choice correctness is unknowable for timeouts, so the error model conditions on response.",
            "No formal participant-by-style random-slope model is fit; crude contrast diagnostics "
            "are weak planning inputs and repeated-trial gains may otherwise be overstated.",
            "Observed legacy style effects may be exaggerated; power simulations must include "
            "prespecified shrinkage toward the null and a no-style-effect calibration.",
        ],
    }
    return artifact


def write_legacy_power_calibration(
    input_path: str | Path,
    output_path: str | Path,
) -> Path:
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Calibration output already exists: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"Calibration output parent does not exist: {output.parent}")
    artifact = calibrate_legacy_power(input_path)
    encoded = json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
    output.chmod(0o600)
    return output


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description=(
            "Calibrate exploratory power inputs from the analysis pipeline's legacy "
            "derived_trials.csv"
        )
    )
    command.add_argument("--input", required=True, type=Path, help="Legacy derived_trials.csv")
    command.add_argument("--output", required=True, type=Path, help="New aggregate JSON artifact")
    return command


def main() -> None:
    args = parser().parse_args()
    output = write_legacy_power_calibration(args.input, args.output)
    print(f"Legacy power calibration written to {output}")


if __name__ == "__main__":
    main()
