from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.genmod.cov_struct import Exchangeable, Independence
from statsmodels.genmod.families import Binomial, Gaussian
from statsmodels.genmod.generalized_estimating_equations import GEE

from .config import AnalysisConfig


@dataclass
class ModelBundle:
    coefficients: pd.DataFrame
    global_tests: pd.DataFrame
    marginal_means: pd.DataFrame
    pairwise_contrasts: pd.DataFrame
    training_effects: pd.DataFrame
    sensitivity: pd.DataFrame
    status: pd.DataFrame


def _covariance(name: str):
    if name == "exchangeable":
        return Exchangeable()
    if name == "independence":
        return Independence()
    raise ValueError(f"Unsupported GEE working covariance: {name}")


def _covariates(data: pd.DataFrame, config: AnalysisConfig) -> list[str]:
    terms: list[str] = []
    if config.adjust_for_period and data["period"].nunique() > 1:
        terms.append("C(period)")
    if config.adjust_for_within_period_progress:
        terms.append("within_period_progress")
    if (
        config.adjust_for_target_drug
        and data["target_drug"].nunique() > 1
        and len(data) > data["target_drug"].nunique() + 10
    ):
        terms.append("C(target_drug)")
    if (
        config.adjust_for_configuration
        and "configuration_signature" in data
        and data["configuration_signature"].nunique() > 1
    ):
        terms.append("C(configuration_signature)")
    return terms


def _formula(
    outcome: str,
    data: pd.DataFrame,
    config: AnalysisConfig,
    *,
    interaction: str | None = None,
):
    reference = config.style_reference.replace("'", "\\'")
    style = f"C(style, Treatment(reference='{reference}'))"
    if interaction == "progress":
        style = f"{style} * within_period_progress"
        covariates = [
            term for term in _covariates(data, config) if term != "within_period_progress"
        ]
    elif interaction == "period":
        style = f"{style} * C(period)"
        covariates = [term for term in _covariates(data, config) if term != "C(period)"]
    else:
        covariates = _covariates(data, config)
    return f"{outcome} ~ " + " + ".join([style, *covariates])


def _fit_gee(
    name: str,
    outcome: str,
    data: pd.DataFrame,
    config: AnalysisConfig,
    *,
    family,
    covariance: str | None = None,
    interaction: str | None = None,
    covariance_estimator: str = "robust",
):
    if data["participant_id"].nunique() < 3:
        raise ValueError(f"{name} needs at least three participant clusters")
    observed_styles = set(data["style"].dropna().astype(str))
    expected_styles = set(config.style_order)
    if observed_styles != expected_styles:
        missing = ", ".join(style for style in config.style_order if style not in observed_styles)
        unexpected = ", ".join(sorted(observed_styles - expected_styles))
        details = []
        if missing:
            details.append(f"missing: {missing}")
        if unexpected:
            details.append(f"unexpected: {unexpected}")
        raise ValueError(f"{name} requires all configured display styles ({'; '.join(details)})")
    formula = _formula(outcome, data, config, interaction=interaction)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = GEE.from_formula(
            formula,
            groups="participant_id",
            data=data,
            family=family,
            cov_struct=_covariance(covariance or config.covariance),
        )
        result = model.fit(maxiter=200, cov_type=covariance_estimator)
        if not getattr(result, "converged", True):
            raise RuntimeError("GEE did not converge within 200 iterations")
    return result, formula, "; ".join(str(item.message) for item in caught)


def _coefficient_table(name: str, result, effect_scale: str) -> pd.DataFrame:
    interval = result.conf_int()
    rows = []
    for index, term in enumerate(result.params.index):
        estimate = float(result.params.iloc[index])
        low = float(interval.iloc[index, 0])
        high = float(interval.iloc[index, 1])
        transformed = effect_scale in {"odds_ratio", "geometric_mean_ratio"}
        rows.append(
            {
                "model": name,
                "term": term,
                "coefficient": estimate,
                "std_error": float(result.bse.iloc[index]),
                "ci_low": low,
                "ci_high": high,
                "statistic": float(result.tvalues.iloc[index]),
                "p_value": float(result.pvalues.iloc[index]),
                "effect_scale": effect_scale,
                "effect_estimate": math.exp(estimate) if transformed else estimate,
                "effect_ci_low": math.exp(low) if transformed else low,
                "effect_ci_high": math.exp(high) if transformed else high,
            }
        )
    return pd.DataFrame(rows)


def _style_parameter_indices(result) -> list[int]:
    return [
        index
        for index, term in enumerate(result.params.index)
        if "C(style" in term and ")[T." in term and ":" not in term
    ]


def _wald_rows(name: str, result, *, interaction: str | None = None) -> list[dict[str, object]]:
    if interaction == "progress":
        indices = [
            index
            for index, term in enumerate(result.params.index)
            if "C(style" in term and ":within_period_progress" in term
        ]
        hypothesis = "style × within-period progress"
    elif interaction == "period":
        indices = [
            index
            for index, term in enumerate(result.params.index)
            if "C(style" in term and ":C(period)" in term
        ]
        hypothesis = "style × study period"
    else:
        indices = _style_parameter_indices(result)
        hypothesis = "display style"
    if not indices:
        return []
    restriction = np.zeros((len(indices), len(result.params)))
    for row, index in enumerate(indices):
        restriction[row, index] = 1
    restricted_covariance = restriction @ np.asarray(result.cov_params()) @ restriction.T
    rank = int(np.linalg.matrix_rank(restricted_covariance))
    if rank != len(indices):
        raise ValueError(
            f"{name} style hypothesis is rank deficient "
            f"({rank} independent constraints for {len(indices)} coefficients)"
        )
    test = result.wald_test(restriction, scalar=True)
    return [
        {
            "model": name,
            "hypothesis": hypothesis,
            "statistic": float(np.asarray(test.statistic).squeeze()),
            "degrees_of_freedom": rank,
            "p_value": float(np.asarray(test.pvalue).squeeze()),
        }
    ]


def _design(result, data: pd.DataFrame) -> np.ndarray:
    from patsy import build_design_matrices

    return np.asarray(
        build_design_matrices([result.model.data.design_info], data, return_type="dataframe")[0]
    )


def _standardized_value(result, data: pd.DataFrame, outcome_kind: str):
    design = _design(result, data)
    linear = design @ np.asarray(result.params)
    if outcome_kind == "accuracy":
        values = 1 / (1 + np.exp(-linear))
        estimate = float(values.mean())
        gradient = np.mean(values[:, None] * (1 - values[:, None]) * design, axis=0)
        return estimate, gradient
    estimate = float(np.mean(linear))
    gradient = np.mean(design, axis=0)
    return estimate, gradient


def _style_margins(
    name: str,
    result,
    data: pd.DataFrame,
    config: AnalysisConfig,
    outcome_kind: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    covariance = np.asarray(result.cov_params())
    z = stats.norm.ppf(1 - config.alpha / 2)
    values: dict[str, tuple[float, np.ndarray]] = {}
    margin_rows: list[dict[str, object]] = []
    for style in config.style_order:
        if style not in set(data["style"].astype(str)):
            continue
        counterfactual = data.copy()
        counterfactual["style"] = style
        estimate, gradient = _standardized_value(result, counterfactual, outcome_kind)
        variance = max(float(gradient @ covariance @ gradient), 0)
        standard_error = math.sqrt(variance)
        if outcome_kind == "reaction_time":
            transformed = math.exp(estimate)
            low = math.exp(estimate - z * standard_error)
            high = math.exp(estimate + z * standard_error)
            measure = "adjusted geometric mean (ms)"
        else:
            transformed = estimate
            low = max(0.0, estimate - z * standard_error)
            high = min(1.0, estimate + z * standard_error)
            measure = "adjusted probability correct"
        values[style] = (estimate, gradient)
        margin_rows.append(
            {
                "model": name,
                "style": style,
                "effect_measure": measure,
                "estimate": transformed,
                "ci_low": low,
                "ci_high": high,
            }
        )

    contrast_rows: list[dict[str, object]] = []
    for first, second in combinations(values, 2):
        estimate_first, gradient_first = values[first]
        estimate_second, gradient_second = values[second]
        difference = estimate_second - estimate_first
        gradient = gradient_second - gradient_first
        standard_error = math.sqrt(max(float(gradient @ covariance @ gradient), 0))
        if not np.isfinite(standard_error) or (outcome_kind == "accuracy" and standard_error > 1):
            raise RuntimeError(
                f"{name} produced an unstable standardized {outcome_kind} contrast covariance"
            )
        statistic = difference / standard_error if standard_error else np.nan
        p_value = float(2 * stats.norm.sf(abs(statistic))) if standard_error else np.nan
        if outcome_kind == "reaction_time":
            estimate = math.exp(difference)
            low = math.exp(difference - z * standard_error)
            high = math.exp(difference + z * standard_error)
            measure = "geometric mean ratio"
        else:
            estimate = difference
            low = difference - z * standard_error
            high = difference + z * standard_error
            measure = "risk difference"
        contrast_rows.append(
            {
                "model": name,
                "contrast": f"{second} vs {first}",
                "effect_measure": measure,
                "estimate": estimate,
                "ci_low": low,
                "ci_high": high,
                "std_error_linear_scale": standard_error,
                "statistic": statistic,
                "p_value": p_value,
            }
        )
    contrasts = pd.DataFrame(contrast_rows)
    if not contrasts.empty:
        contrasts["p_value_holm"] = _holm(contrasts["p_value"].to_numpy(float))
    return pd.DataFrame(margin_rows), contrasts


def _holm(p_values: np.ndarray) -> np.ndarray:
    adjusted = np.full(len(p_values), np.nan)
    finite = np.flatnonzero(np.isfinite(p_values))
    if not len(finite):
        return adjusted
    ordered = finite[np.argsort(p_values[finite])]
    running = 0.0
    total = len(ordered)
    for rank, index in enumerate(ordered):
        running = max(running, (total - rank) * p_values[index])
        adjusted[index] = min(running, 1.0)
    return adjusted


def _progress_effect(
    name: str,
    result,
    data: pd.DataFrame,
    config: AnalysisConfig,
    outcome_kind: str,
    *,
    style: str | None = None,
) -> dict[str, object]:
    covariance = np.asarray(result.cov_params())
    start = data.copy()
    finish = data.copy()
    if style is not None:
        start["style"] = style
        finish["style"] = style
    start["within_period_progress"] = 0.0
    finish["within_period_progress"] = 1.0
    estimate_start, gradient_start = _standardized_value(result, start, outcome_kind)
    estimate_finish, gradient_finish = _standardized_value(result, finish, outcome_kind)
    difference = estimate_finish - estimate_start
    gradient = gradient_finish - gradient_start
    standard_error = math.sqrt(max(float(gradient @ covariance @ gradient), 0))
    z = stats.norm.ppf(1 - config.alpha / 2)
    p_value = (
        float(2 * stats.norm.sf(abs(difference / standard_error))) if standard_error else np.nan
    )
    if outcome_kind == "reaction_time":
        estimate = math.exp(difference)
        low = math.exp(difference - z * standard_error)
        high = math.exp(difference + z * standard_error)
        measure = "end/start geometric mean ratio"
    else:
        estimate = difference
        low = difference - z * standard_error
        high = difference + z * standard_error
        measure = "end-minus-start probability"
    return {
        "model": name,
        "style": style or "Common slope (no interaction)",
        "training_contrast": "end vs start of each style period",
        "effect_measure": measure,
        "estimate": estimate,
        "ci_low": low,
        "ci_high": high,
        "p_value": p_value,
    }


def _analysis_population(trials: pd.DataFrame, *, legacy_pilot: bool) -> pd.DataFrame:
    data = trials.loc[trials["result_present"]].copy()
    if legacy_pilot:
        assigned = data[["participant_id", "run_id", "period_id"]].notna().all(axis=1)
        if "integrity_excluded" in data:
            assigned &= ~data["integrity_excluded"]
        data = data.loc[assigned]
    else:
        if "analysis_eligible" in data:
            data = data.loc[data["analysis_eligible"]]
        else:
            data = data.loc[data["protocol_version"].ge(2)]
    # Patsy/statsmodels does not accept pandas nullable extension dtypes. Keep
    # snapshot loading strict, then present a conventional numerical model frame.
    for column in (
        "period",
        "within_period_progress",
        "global_trial_progress",
        "correct",
        "log_rt",
        "log_response_rt",
        "observed_rt_ms",
        "duration_ms",
        "response_event",
    ):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce").astype(float)
    for column in ("participant_id", "target_drug", "configuration_signature"):
        if column in data:
            data[column] = data[column].astype(str)
    return data


def fit_models(
    trials: pd.DataFrame,
    config: AnalysisConfig,
    *,
    legacy_pilot: bool = False,
) -> ModelBundle:
    population = _analysis_population(trials, legacy_pilot=legacy_pilot)
    coefficient_tables: list[pd.DataFrame] = []
    global_rows: list[dict[str, object]] = []
    margin_tables: list[pd.DataFrame] = []
    contrast_tables: list[pd.DataFrame] = []
    training_rows: list[dict[str, object]] = []
    sensitivity_rows: list[dict[str, object]] = []
    status_rows: list[dict[str, object]] = []

    primary_specs = (
        (
            "primary_accuracy",
            "correct",
            population,
            Binomial(),
            "accuracy",
            "odds_ratio",
        ),
        (
            "primary_correct_rt",
            "log_rt",
            population.loc[population["correct_response"]],
            Gaussian(),
            "reaction_time",
            "geometric_mean_ratio",
        ),
    )
    fitted: dict[str, tuple[object, pd.DataFrame, str]] = {}
    for name, outcome, data, family, kind, scale in primary_specs:
        try:
            result, formula, warning_text = _fit_gee(name, outcome, data, config, family=family)
            global_test = _wald_rows(name, result)
            coefficients = _coefficient_table(name, result, scale)
            margins, contrasts = _style_margins(name, result, data, config, kind)
            fitted[name] = (result, data, kind)
            coefficient_tables.append(coefficients)
            global_rows.extend(global_test)
            margin_tables.append(margins)
            contrast_tables.append(contrasts)
            training_rows.append(_progress_effect(name, result, data, config, kind))
            status_rows.append(
                {
                    "model": name,
                    "status": "fitted",
                    "formula": formula,
                    "observations": int(result.nobs),
                    "participants": int(data["participant_id"].nunique()),
                    "working_covariance": config.covariance,
                    "warning": warning_text,
                }
            )
        except Exception as exc:  # model failures must remain visible in the report
            status_rows.append(
                {
                    "model": name,
                    "status": "failed",
                    "formula": "",
                    "observations": int(len(data)),
                    "participants": int(data["participant_id"].nunique()),
                    "working_covariance": config.covariance,
                    "warning": f"{type(exc).__name__}: {exc}",
                }
            )

    # Directly test whether learning/fatigue differs by display style.
    for name, outcome, data, family, _kind, _scale in primary_specs:
        interaction_name = name.replace("primary_", "training_interaction_")
        try:
            result, formula, warning_text = _fit_gee(
                interaction_name,
                outcome,
                data,
                config,
                family=family,
                interaction="progress",
            )
            global_rows.extend(_wald_rows(interaction_name, result, interaction="progress"))
            training_rows.extend(
                _progress_effect(
                    interaction_name,
                    result,
                    data,
                    config,
                    _kind,
                    style=style,
                )
                for style in config.style_order
            )
            status_rows.append(
                {
                    "model": interaction_name,
                    "status": "fitted",
                    "formula": formula,
                    "observations": int(result.nobs),
                    "participants": int(data["participant_id"].nunique()),
                    "working_covariance": config.covariance,
                    "warning": warning_text,
                }
            )
        except Exception as exc:
            status_rows.append(
                {
                    "model": interaction_name,
                    "status": "failed",
                    "formula": "",
                    "observations": int(len(data)),
                    "participants": int(data["participant_id"].nunique()),
                    "working_covariance": config.covariance,
                    "warning": f"{type(exc).__name__}: {exc}",
                }
            )

    # A style-by-period test detects a display-style effect that changes as the
    # participant moves through the randomized crossover (carryover/order risk).
    for name, outcome, data, family, _kind, _scale in primary_specs:
        interaction_name = name.replace("primary_", "period_interaction_")
        try:
            result, formula, warning_text = _fit_gee(
                interaction_name,
                outcome,
                data,
                config,
                family=family,
                interaction="period",
            )
            global_rows.extend(_wald_rows(interaction_name, result, interaction="period"))
            status_rows.append(
                {
                    "model": interaction_name,
                    "status": "fitted",
                    "formula": formula,
                    "observations": int(result.nobs),
                    "participants": int(data["participant_id"].nunique()),
                    "working_covariance": config.covariance,
                    "warning": warning_text,
                }
            )
        except Exception as exc:
            status_rows.append(
                {
                    "model": interaction_name,
                    "status": "failed",
                    "formula": "",
                    "observations": int(len(data)),
                    "participants": int(data["participant_id"].nunique()),
                    "working_covariance": config.covariance,
                    "warning": f"{type(exc).__name__}: {exc}",
                }
            )

    sensitivity_specs = (
        (
            "all_observed_responses_rt",
            "log_response_rt",
            population.loc[population["valid_observed_rt"]],
            Gaussian(),
            "exchangeable",
            "robust",
            "reaction_time",
        ),
        (
            "complete_runs_correct_rt",
            "log_rt",
            population.loc[population["correct_response"] & population["complete_run"]],
            Gaussian(),
            "exchangeable",
            "robust",
            "reaction_time",
        ),
        (
            "plausible_correct_rt",
            "log_rt",
            population.loc[population["correct_response"] & population["plausible_rt"]],
            Gaussian(),
            "exchangeable",
            "robust",
            "reaction_time",
        ),
        (
            "independence_correct_rt",
            "log_rt",
            population.loc[population["correct_response"]],
            Gaussian(),
            "independence",
            "robust",
            "reaction_time",
        ),
        (
            "complete_runs_accuracy",
            "correct",
            population.loc[population["complete_run"]],
            Binomial(),
            "exchangeable",
            "robust",
            "accuracy",
        ),
        (
            "independence_accuracy",
            "correct",
            population,
            Binomial(),
            "independence",
            "robust",
            "accuracy",
        ),
        (
            "bias_reduced_correct_rt",
            "log_rt",
            population.loc[population["correct_response"]],
            Gaussian(),
            "exchangeable",
            "bias_reduced",
            "reaction_time",
        ),
        (
            "bias_reduced_accuracy",
            "correct",
            population,
            Binomial(),
            "exchangeable",
            "bias_reduced",
            "accuracy",
        ),
    )
    for (
        name,
        outcome,
        data,
        family,
        covariance,
        covariance_estimator,
        outcome_kind,
    ) in sensitivity_specs:
        try:
            result, formula, warning_text = _fit_gee(
                name,
                outcome,
                data,
                config,
                family=family,
                covariance=covariance,
                covariance_estimator=covariance_estimator,
            )
            tests = _wald_rows(name, result)
            if tests:
                margin_warning = ""
                try:
                    margins, contrasts = _style_margins(
                        name,
                        result,
                        data,
                        config,
                        outcome_kind,
                    )
                    margin_tables.append(margins)
                    contrast_tables.append(contrasts)
                except Exception as exc:
                    margin_warning = f"{type(exc).__name__}: {exc}"
                combined_warning = "; ".join(
                    item for item in (warning_text, margin_warning) if item
                )
                sensitivity_rows.append(
                    {
                        **tests[0],
                        "observations": int(result.nobs),
                        "participants": int(data["participant_id"].nunique()),
                        "formula": formula,
                        "covariance_estimator": covariance_estimator,
                        "warning": combined_warning,
                    }
                )
        except Exception as exc:
            sensitivity_rows.append(
                {
                    "model": name,
                    "hypothesis": "display style",
                    "statistic": np.nan,
                    "degrees_of_freedom": np.nan,
                    "p_value": np.nan,
                    "observations": int(len(data)),
                    "participants": int(data["participant_id"].nunique()),
                    "formula": "",
                    "covariance_estimator": covariance_estimator,
                    "warning": f"{type(exc).__name__}: {exc}",
                }
            )

    # Timeouts carry right-censoring information. A participant-clustered Cox
    # model tests time to any selection without pretending the deadline was an
    # observed reaction time. Hazard ratios above one indicate faster responses.
    censored_name = "censored_time_to_response"
    censored = population.loc[
        population["duration_ms"].notna() & population["response_event"].notna()
    ].copy()
    censored_formula = _formula("duration_ms", censored, config)
    try:
        if censored["participant_id"].nunique() < 3:
            raise ValueError("censored analysis needs at least three participant clusters")
        observed_styles = set(censored["style"].dropna().astype(str))
        if observed_styles != set(config.style_order):
            raise ValueError("censored analysis requires all configured display styles")
        if censored["response_event"].sum() < 3:
            raise ValueError("censored analysis needs at least three observed responses")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = PHReg.from_formula(
                censored_formula,
                status=censored["response_event"],
                data=censored,
                ties="efron",
            )
            result = model.fit(groups=censored["participant_id"])
        names = list(result.model.exog_names)
        parameters = np.asarray(result.params, dtype=float)
        standard_errors = np.asarray(result.bse, dtype=float)
        p_values = np.asarray(result.pvalues, dtype=float)
        interval = np.asarray(result.conf_int(), dtype=float)
        coefficient_tables.append(
            pd.DataFrame(
                {
                    "model": censored_name,
                    "term": names,
                    "coefficient": parameters,
                    "std_error": standard_errors,
                    "ci_low": interval[:, 0],
                    "ci_high": interval[:, 1],
                    "statistic": parameters / standard_errors,
                    "p_value": p_values,
                    "effect_scale": "hazard_ratio",
                    "effect_estimate": np.exp(parameters),
                    "effect_ci_low": np.exp(interval[:, 0]),
                    "effect_ci_high": np.exp(interval[:, 1]),
                }
            )
        )
        style_indices = [
            index
            for index, term in enumerate(names)
            if "C(style" in term and ")[T." in term and ":" not in term
        ]
        if not style_indices:
            raise ValueError("censored model did not estimate a display-style contrast")
        style_parameters = parameters[style_indices]
        style_covariance = np.asarray(result.cov_params())[np.ix_(style_indices, style_indices)]
        style_rank = int(np.linalg.matrix_rank(style_covariance))
        if style_rank != len(config.style_order) - 1:
            raise ValueError(
                "censored display-style hypothesis is rank deficient "
                f"({style_rank} independent constraints)"
            )
        statistic = float(style_parameters @ np.linalg.pinv(style_covariance) @ style_parameters)
        global_test = {
            "model": censored_name,
            "hypothesis": "display style",
            "statistic": statistic,
            "degrees_of_freedom": style_rank,
            "p_value": float(stats.chi2.sf(statistic, style_rank)),
        }
        global_rows.append(global_test)
        sensitivity_rows.append(
            {
                **global_test,
                "observations": int(len(censored)),
                "participants": int(censored["participant_id"].nunique()),
                "formula": censored_formula,
                "covariance_estimator": "participant-clustered robust",
                "warning": "; ".join(str(item.message) for item in caught),
            }
        )

        style_vectors: dict[str, np.ndarray] = {}
        for style in config.style_order:
            vector = np.zeros(len(parameters))
            if style != config.style_reference:
                matches = [
                    index
                    for index, term in enumerate(names)
                    if "C(style" in term and f"[T.{style}]" in term and ":" not in term
                ]
                if not matches:
                    continue
                vector[matches[0]] = 1
            style_vectors[style] = vector
        covariance_matrix = np.asarray(result.cov_params())
        z = stats.norm.ppf(1 - config.alpha / 2)
        censored_contrasts: list[dict[str, object]] = []
        for first, second in combinations(style_vectors, 2):
            vector = style_vectors[second] - style_vectors[first]
            difference = float(vector @ parameters)
            standard_error = math.sqrt(max(float(vector @ covariance_matrix @ vector), 0))
            score = difference / standard_error if standard_error else np.nan
            censored_contrasts.append(
                {
                    "model": censored_name,
                    "contrast": f"{second} vs {first}",
                    "effect_measure": "response hazard ratio (higher is faster)",
                    "estimate": math.exp(difference),
                    "ci_low": math.exp(difference - z * standard_error),
                    "ci_high": math.exp(difference + z * standard_error),
                    "std_error_linear_scale": standard_error,
                    "statistic": score,
                    "p_value": (float(2 * stats.norm.sf(abs(score))) if standard_error else np.nan),
                }
            )
        censored_contrasts_table = pd.DataFrame(censored_contrasts)
        censored_contrasts_table["p_value_holm"] = _holm(
            censored_contrasts_table["p_value"].to_numpy(float)
        )
        contrast_tables.append(censored_contrasts_table)
        status_rows.append(
            {
                "model": censored_name,
                "status": "fitted",
                "formula": censored_formula,
                "covariance_estimator": "participant-clustered robust",
                "observations": int(len(censored)),
                "participants": int(censored["participant_id"].nunique()),
                "working_covariance": "Cox PH; participant-clustered robust covariance",
                "warning": "; ".join(str(item.message) for item in caught),
            }
        )
    except Exception as exc:
        sensitivity_rows.append(
            {
                "model": censored_name,
                "hypothesis": "display style",
                "statistic": np.nan,
                "degrees_of_freedom": np.nan,
                "p_value": np.nan,
                "observations": int(len(censored)),
                "participants": int(censored["participant_id"].nunique()),
                "formula": censored_formula,
                "warning": f"{type(exc).__name__}: {exc}",
            }
        )
        status_rows.append(
            {
                "model": censored_name,
                "status": "failed",
                "formula": censored_formula,
                "observations": int(len(censored)),
                "participants": int(censored["participant_id"].nunique()),
                "working_covariance": "Cox PH; participant-clustered robust covariance",
                "warning": f"{type(exc).__name__}: {exc}",
            }
        )

    def combine(tables: list[pd.DataFrame]) -> pd.DataFrame:
        nonempty = [table for table in tables if not table.empty]
        return pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame()

    training_effects = pd.DataFrame(training_rows)
    if not training_effects.empty:
        training_effects["p_value_holm"] = np.nan
        interaction_mask = training_effects["model"].str.startswith("training_interaction_")
        for model_name, model_rows in training_effects.loc[interaction_mask].groupby(
            "model", observed=True
        ):
            training_effects.loc[model_rows.index, "p_value_holm"] = _holm(
                model_rows["p_value"].to_numpy(float)
            )

    return ModelBundle(
        coefficients=combine(coefficient_tables),
        global_tests=pd.DataFrame(global_rows),
        marginal_means=combine(margin_tables),
        pairwise_contrasts=combine(contrast_tables),
        training_effects=training_effects,
        sensitivity=pd.DataFrame(sensitivity_rows),
        status=pd.DataFrame(status_rows),
    )
