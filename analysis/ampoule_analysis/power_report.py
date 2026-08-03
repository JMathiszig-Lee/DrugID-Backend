from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

OUTCOMES = ("correct response time", "accuracy")
STYLES = ("industry", "iso", "black_white")
STYLE_LABELS = {
    "industry": "Industry",
    "iso": "ISO",
    "black_white": "Black and white",
}
SCENARIOS = ("alternative", "no_style_effect")
BOOLEAN_COLUMNS = (
    "lower_ci_meets_target",
    "operational_null_ci_contains_alpha",
    "conditional_null_ci_contains_alpha",
    "matched_null_mc_ci_contains_alpha",
    "design_eligible_for_minimum",
    "is_smallest_evaluated_n",
)
REQUIRED_NUMERIC_COLUMNS = (
    "effect_scale",
    "learning_scale",
    "participants_recruited",
    "trials_per_style",
    "successful_simulations_target",
    "simulation_datasets_generated",
    "models_fitted",
    "model_failures",
    "model_fit_attempts",
    "fit_failure_rate",
    "significant_global_tests",
    "mean_participants_started",
    "mean_participants_with_results",
    "mean_submitted_results",
    "mean_missing_results",
    "mean_timeouts",
)
OPTIONAL_NUMERIC_COLUMNS = (
    "estimated_rejection_rate",
    "conditional_rejection_rate_among_fitted",
    "estimated_power",
    "conditional_power_among_fitted",
    "estimated_type_i_error",
    "conditional_type_i_error_among_fitted",
    "mc_ci_low",
    "mc_ci_high",
    "conditional_mc_ci_low",
    "conditional_mc_ci_high",
    "mc_confidence_level",
    "target_power",
)
REALIZED_COLUMNS = tuple(
    f"realized_{metric}_{style}"
    for style in STYLES
    for metric in ("accuracy", "timeout_rate", "correct_rt_geometric_mean_ms")
)
REQUIRED_COLUMNS = {
    "scenario",
    "metric",
    "outcome",
    "simulation_status",
    "fit_failure_reasons",
    "fit_warnings",
    *BOOLEAN_COLUMNS,
    *REQUIRED_NUMERIC_COLUMNS,
    *OPTIONAL_NUMERIC_COLUMNS,
    *REALIZED_COLUMNS,
}
FORBIDDEN_INDIVIDUAL_COLUMNS = {
    "participant_id",
    "assigned_order",
    "target_drug",
    "trial",
    "choice_correct",
    "observed_rt_ms",
}
SCENARIO_KEY = (
    "scenario",
    "effect_scale",
    "learning_scale",
    "participants_recruited",
    "trials_per_style",
)
ROW_KEY = (*SCENARIO_KEY, "outcome")


class PowerReportValidationError(ValueError):
    """A completed power output is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class ValidatedPowerRun:
    input_directory: Path
    manifest: dict[str, Any]
    results: pd.DataFrame
    results_sha256: str
    manifest_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_manifest_dict(manifest: dict[str, Any], key: str) -> dict[str, Any]:
    value = manifest.get(key)
    if not isinstance(value, dict):
        raise PowerReportValidationError(f"power_manifest.json field {key!r} must be an object")
    return value


def _config_numbers(
    config: dict[str, Any], key: str, *, integer: bool = False
) -> tuple[int | float, ...]:
    values = config.get(key)
    if not isinstance(values, list) or not values:
        raise PowerReportValidationError(f"manifest config field {key!r} must be a non-empty list")
    converted: list[int | float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise PowerReportValidationError(
                f"manifest config field {key!r} contains a non-numeric value"
            ) from exc
        if not math.isfinite(number):
            raise PowerReportValidationError(
                f"manifest config field {key!r} contains a non-finite value"
            )
        if integer:
            if not number.is_integer():
                raise PowerReportValidationError(
                    f"manifest config field {key!r} must contain integers"
                )
            converted.append(int(number))
        else:
            converted.append(number)
    if len(converted) != len(set(converted)):
        raise PowerReportValidationError(f"manifest config field {key!r} contains duplicates")
    return tuple(converted)


def _coerce_boolean(series: pd.Series, column: str) -> pd.Series:
    converted: list[bool] = []
    for value in series:
        if isinstance(value, (bool, np.bool_)):
            converted.append(bool(value))
            continue
        if isinstance(value, (int, np.integer)) and value in (0, 1):
            converted.append(bool(value))
            continue
        text = str(value).strip().lower()
        if text in {"true", "1"}:
            converted.append(True)
        elif text in {"false", "0"}:
            converted.append(False)
        else:
            raise PowerReportValidationError(f"column {column!r} contains a non-boolean value")
    return pd.Series(converted, index=series.index, dtype=bool)


def _coerce_numeric(results: pd.DataFrame, column: str, *, required: bool) -> None:
    original = results[column]
    converted = pd.to_numeric(original, errors="coerce")
    invalid = original.notna() & converted.isna()
    if invalid.any() or (required and converted.isna().any()):
        raise PowerReportValidationError(f"column {column!r} contains invalid numeric values")
    results[column] = converted


def _rounded(value: object) -> float:
    return round(float(value), 12)


def _validate_manifest_and_hashes(
    manifest: dict[str, Any], results_path: Path, results_sha256: str
) -> dict[str, Any]:
    required_manifest = {
        "status",
        "warning",
        "grid_status",
        "non_estimable_scenario_count",
        "config",
        "config_file_sha256",
        "effective_config_sha256",
        "power_source_sha256",
        "software_versions",
        "files",
    }
    missing = sorted(required_manifest - manifest.keys())
    if missing:
        raise PowerReportValidationError(
            "power_manifest.json is missing required fields: " + ", ".join(missing)
        )
    config = _require_manifest_dict(manifest, "config")
    required_config = {
        "status",
        "participant_counts",
        "trials_per_style_counts",
        "effect_scales",
        "learning_scales",
        "simulations",
        "seed",
        "alpha",
        "target_power",
        "covariance_estimator",
        "mc_confidence_level",
    }
    missing_config = sorted(required_config - config.keys())
    if missing_config:
        raise PowerReportValidationError(
            "manifest config is missing required fields: " + ", ".join(missing_config)
        )
    files = _require_manifest_dict(manifest, "files")
    _require_manifest_dict(manifest, "software_versions")
    result_record = files.get("power_results.csv")
    if not isinstance(result_record, dict):
        raise PowerReportValidationError(
            "power_manifest.json does not contain a power_results.csv file record"
        )
    if result_record.get("sha256") != results_sha256:
        raise PowerReportValidationError(
            "power_results.csv SHA-256 does not match power_manifest.json"
        )
    if result_record.get("bytes") != results_path.stat().st_size:
        raise PowerReportValidationError(
            "power_results.csv byte count does not match power_manifest.json"
        )
    if str(manifest["status"]) != str(config.get("status")):
        raise PowerReportValidationError("manifest status does not match effective config status")
    for key in ("config_file_sha256", "effective_config_sha256", "power_source_sha256"):
        value = manifest[key]
        if not isinstance(value, str) or len(value) != 64:
            raise PowerReportValidationError(f"manifest field {key!r} is not a SHA-256 digest")
    return config


def _validate_grid(results: pd.DataFrame, manifest: dict[str, Any], config: dict[str, Any]) -> None:
    participants = _config_numbers(config, "participant_counts", integer=True)
    repeats = _config_numbers(config, "trials_per_style_counts", integer=True)
    effects = _config_numbers(config, "effect_scales")
    learning = _config_numbers(config, "learning_scales")

    if set(results["participants_recruited"].astype(int)) != set(participants):
        raise PowerReportValidationError("CSV participant grid does not match the manifest config")
    if set(results["trials_per_style"].astype(int)) != set(repeats):
        raise PowerReportValidationError(
            "CSV trials-per-style grid does not match the manifest config"
        )

    actual_keys = {
        (
            row.scenario,
            _rounded(row.effect_scale),
            _rounded(row.learning_scale),
            int(row.participants_recruited),
            int(row.trials_per_style),
            row.outcome,
        )
        for row in results.itertuples(index=False)
    }
    if len(actual_keys) != len(results):
        raise PowerReportValidationError("power_results.csv contains duplicate scenario rows")
    expected_keys = {
        (
            "alternative",
            _rounded(effect),
            _rounded(learning_scale),
            participant_count,
            repeat_count,
            outcome,
        )
        for effect in effects
        for learning_scale in learning
        for participant_count in participants
        for repeat_count in repeats
        for outcome in OUTCOMES
    }
    expected_keys.update(
        {
            (
                "no_style_effect",
                0.0,
                _rounded(learning_scale),
                participant_count,
                repeat_count,
                outcome,
            )
            for learning_scale in learning
            for participant_count in participants
            for repeat_count in repeats
            for outcome in OUTCOMES
        }
    )
    if actual_keys != expected_keys:
        missing = len(expected_keys - actual_keys)
        unexpected = len(actual_keys - expected_keys)
        raise PowerReportValidationError(
            f"CSV scenario grid is incomplete or unexpected ({missing} missing, "
            f"{unexpected} unexpected rows)"
        )

    simulations = config.get("simulations")
    try:
        simulations = int(simulations)
    except (TypeError, ValueError) as exc:
        raise PowerReportValidationError("manifest simulation count is invalid") from exc
    if simulations < 1 or not results["successful_simulations_target"].eq(simulations).all():
        raise PowerReportValidationError("CSV simulation targets do not match the manifest config")

    expected_bad = (
        results.loc[~results["simulation_status"].eq("complete"), list(SCENARIO_KEY)]
        .drop_duplicates()
        .shape[0]
    )
    try:
        declared_bad = int(manifest["non_estimable_scenario_count"])
    except (TypeError, ValueError) as exc:
        raise PowerReportValidationError(
            "manifest non-estimable scenario count is invalid"
        ) from exc
    if expected_bad != declared_bad:
        raise PowerReportValidationError(
            "manifest non-estimable scenario count does not match power_results.csv"
        )
    expected_status = "completed_with_non_estimable_scenarios" if expected_bad else "complete"
    if manifest["grid_status"] != expected_status:
        raise PowerReportValidationError("manifest grid status does not match power_results.csv")


def _validate_row_semantics(results: pd.DataFrame, config: dict[str, Any]) -> None:
    statuses = set(results["simulation_status"])
    allowed_statuses = {"complete", "non_estimable_fit_failure"}
    if not statuses <= allowed_statuses:
        raise PowerReportValidationError("power_results.csv contains an unknown simulation status")
    if set(results["scenario"]) != set(SCENARIOS):
        raise PowerReportValidationError("power_results.csv must contain alternative and null rows")
    if set(results["outcome"]) != set(OUTCOMES):
        raise PowerReportValidationError("power_results.csv contains an unexpected outcome")

    integer_columns = (
        "participants_recruited",
        "trials_per_style",
        "successful_simulations_target",
        "simulation_datasets_generated",
        "models_fitted",
        "model_failures",
        "model_fit_attempts",
        "significant_global_tests",
    )
    for column in integer_columns:
        values = results[column].to_numpy(float)
        if (values < 0).any() or not np.equal(values, np.floor(values)).all():
            raise PowerReportValidationError(
                f"column {column!r} must contain non-negative integers"
            )
    if (results["participants_recruited"] < 1).any() or (results["trials_per_style"] < 2).any():
        raise PowerReportValidationError("participant and repeat counts must be positive")

    bounded_columns = (
        "fit_failure_rate",
        "estimated_rejection_rate",
        "conditional_rejection_rate_among_fitted",
        "estimated_power",
        "conditional_power_among_fitted",
        "estimated_type_i_error",
        "conditional_type_i_error_among_fitted",
        "mc_ci_low",
        "mc_ci_high",
        "conditional_mc_ci_low",
        "conditional_mc_ci_high",
        "mc_confidence_level",
        "target_power",
        *(f"realized_accuracy_{style}" for style in STYLES),
        *(f"realized_timeout_rate_{style}" for style in STYLES),
    )
    for column in bounded_columns:
        finite = results[column].dropna()
        if not finite.between(0, 1).all():
            raise PowerReportValidationError(f"column {column!r} has a value outside [0, 1]")
    for style in STYLES:
        finite_rt = results[f"realized_correct_rt_geometric_mean_ms_{style}"].dropna()
        if (finite_rt <= 0).any():
            raise PowerReportValidationError("realized correct-RT geometric means must be positive")

    simulations = int(config["simulations"])
    alpha = float(config["alpha"])
    target_power = float(config["target_power"])
    mc_confidence = float(config["mc_confidence_level"])
    if not (0 < alpha < 1 and 0 < target_power < 1 and 0 < mc_confidence < 1):
        raise PowerReportValidationError("manifest alpha, target power or MC confidence is invalid")
    if not results["mc_confidence_level"].eq(mc_confidence).all():
        raise PowerReportValidationError("CSV Monte Carlo confidence levels do not match config")

    complete = results["simulation_status"].eq("complete")
    if not results.loc[complete, "models_fitted"].eq(simulations).all():
        raise PowerReportValidationError("a complete row does not contain the target fitted models")
    if (
        not results["model_fit_attempts"]
        .eq(results["models_fitted"] + results["model_failures"])
        .all()
    ):
        raise PowerReportValidationError("model-fit attempt counts are inconsistent")
    attempts = results["model_fit_attempts"].replace(0, np.nan)
    expected_failure_rate = results["model_failures"] / attempts
    if not np.allclose(
        results["fit_failure_rate"], expected_failure_rate, equal_nan=True, rtol=1e-9, atol=1e-12
    ):
        raise PowerReportValidationError("fit-failure rates are inconsistent with fit counts")
    expected_operational = results["significant_global_tests"] / attempts
    if not np.allclose(
        results.loc[complete, "estimated_rejection_rate"],
        expected_operational.loc[complete],
        equal_nan=False,
        rtol=1e-9,
        atol=1e-12,
    ):
        raise PowerReportValidationError("operational rejection rates are inconsistent")

    complete_rows = results.loc[complete]
    if (
        (complete_rows["mc_ci_low"] > complete_rows["estimated_rejection_rate"])
        | (complete_rows["estimated_rejection_rate"] > complete_rows["mc_ci_high"])
    ).any():
        raise PowerReportValidationError("an operational rejection estimate is outside its MC CI")

    alternative = results["scenario"].eq("alternative")
    null = results["scenario"].eq("no_style_effect")
    if not results.loc[alternative, "target_power"].eq(target_power).all():
        raise PowerReportValidationError("alternative target-power values do not match config")
    computed_meets = alternative & complete & results["mc_ci_low"].ge(target_power)
    if not results["lower_ci_meets_target"].eq(computed_meets).all():
        raise PowerReportValidationError("lower_ci_meets_target is inconsistent with the MC CI")
    computed_null = (
        null & complete & results["mc_ci_low"].le(alpha) & results["mc_ci_high"].ge(alpha)
    )
    if not results["operational_null_ci_contains_alpha"].eq(computed_null).all():
        raise PowerReportValidationError(
            "operational_null_ci_contains_alpha is inconsistent with the MC CI"
        )

    null_lookup = {
        (
            _rounded(row.learning_scale),
            int(row.participants_recruited),
            int(row.trials_per_style),
            row.outcome,
        ): bool(row.operational_null_ci_contains_alpha)
        for row in results.loc[null].itertuples(index=False)
    }
    expected_matched = pd.Series(False, index=results.index)
    for index, row in results.loc[alternative].iterrows():
        key = (
            _rounded(row["learning_scale"]),
            int(row["participants_recruited"]),
            int(row["trials_per_style"]),
            row["outcome"],
        )
        expected_matched.at[index] = null_lookup[key]
    if not results["matched_null_mc_ci_contains_alpha"].eq(expected_matched).all():
        raise PowerReportValidationError("matched null-calibration flags are inconsistent")
    expected_eligible = alternative & complete & computed_meets & expected_matched
    if not results["design_eligible_for_minimum"].eq(expected_eligible).all():
        raise PowerReportValidationError(
            "design_eligible_for_minimum is inconsistent with power and null calibration"
        )

    scenario_fields = ("simulation_datasets_generated", *REALIZED_COLUMNS)
    for _, subset in results.groupby(list(SCENARIO_KEY), dropna=False, sort=False):
        for column in scenario_fields:
            values = subset[column].dropna().to_numpy(float)
            if len(values) > 1 and not np.allclose(values, values[0], rtol=1e-9, atol=1e-12):
                raise PowerReportValidationError(
                    f"scenario-level field {column!r} differs between outcome rows"
                )


def load_completed_power_run(input_path: str | Path) -> ValidatedPowerRun:
    input_directory = Path(input_path).resolve()
    if not input_directory.is_dir():
        raise PowerReportValidationError(f"power input directory does not exist: {input_directory}")
    results_path = input_directory / "power_results.csv"
    manifest_path = input_directory / "power_manifest.json"
    if not results_path.is_file() or not manifest_path.is_file():
        raise PowerReportValidationError(
            "power input must contain power_results.csv and power_manifest.json"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PowerReportValidationError("power_manifest.json is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise PowerReportValidationError("power_manifest.json must contain a JSON object")

    results_sha256 = _sha256(results_path)
    config = _validate_manifest_and_hashes(manifest, results_path, results_sha256)
    try:
        results = pd.read_csv(results_path)
    except (OSError, pd.errors.ParserError) as exc:
        raise PowerReportValidationError("power_results.csv could not be read") from exc
    if results.empty:
        raise PowerReportValidationError("power_results.csv contains no rows")
    missing_columns = sorted(REQUIRED_COLUMNS - set(results.columns))
    if missing_columns:
        raise PowerReportValidationError(
            "power_results.csv is missing required columns: " + ", ".join(missing_columns)
        )
    forbidden = sorted(FORBIDDEN_INDIVIDUAL_COLUMNS & set(results.columns))
    if forbidden:
        raise PowerReportValidationError(
            "power_results.csv unexpectedly contains individual-level columns: "
            + ", ".join(forbidden)
        )
    results = results.copy()
    for column in REQUIRED_NUMERIC_COLUMNS:
        _coerce_numeric(results, column, required=True)
    for column in (*OPTIONAL_NUMERIC_COLUMNS, *REALIZED_COLUMNS):
        _coerce_numeric(results, column, required=False)
    for column in BOOLEAN_COLUMNS:
        results[column] = _coerce_boolean(results[column], column)
    for column in ("scenario", "metric", "outcome", "simulation_status"):
        if results[column].isna().any():
            raise PowerReportValidationError(f"column {column!r} contains missing values")
        results[column] = results[column].astype(str)

    _validate_grid(results, manifest, config)
    _validate_row_semantics(results, config)
    return ValidatedPowerRun(
        input_directory=input_directory,
        manifest=manifest,
        results=results,
        results_sha256=results_sha256,
        manifest_sha256=_sha256(manifest_path),
    )


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> list[str]:
    lines = [
        "| " + " | ".join(_cell(header) for header in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return lines


def _number(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
    except TypeError, ValueError:
        return "not estimable"
    if not math.isfinite(number):
        return "not estimable"
    if number == 0:
        return "0"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _integer(value: object) -> str:
    try:
        number = float(value)
    except TypeError, ValueError:
        return "not estimable"
    return f"{int(number):,}" if math.isfinite(number) else "not estimable"


def _percent(value: object, digits: int = 1) -> str:
    try:
        number = float(value)
    except TypeError, ValueError:
        return "not estimable"
    return f"{100 * number:.{digits}f}%" if math.isfinite(number) else "not estimable"


def _interval(row: pd.Series) -> str:
    return f"{_percent(row['estimated_rejection_rate'])} ({_percent(row['mc_ci_low'])}–{_percent(row['mc_ci_high'])})"


def _range(values: pd.Series, *, percent: bool = False, milliseconds: bool = False) -> str:
    finite = pd.to_numeric(values, errors="coerce").dropna()
    if finite.empty:
        return "not estimable"
    low = float(finite.min())
    high = float(finite.max())
    if percent:
        low_text, high_text = _percent(low), _percent(high)
    elif milliseconds:
        low_text, high_text = f"{low:,.0f} ms", f"{high:,.0f} ms"
    else:
        low_text, high_text = _number(low), _number(high)
    return low_text if math.isclose(low, high) else f"{low_text}–{high_text}"


def _outcome_label(outcome: str) -> str:
    return "Correct response time" if outcome == "correct response time" else "Accuracy"


def _candidate_rows(run: ValidatedPowerRun) -> list[dict[str, Any]]:
    config = run.manifest["config"]
    results = run.results
    rows: list[dict[str, Any]] = []
    alternative = results.loc[results["scenario"].eq("alternative")]
    null = results.loc[results["scenario"].eq("no_style_effect")]
    smallest_n = min(int(value) for value in config["participant_counts"])
    for effect in config["effect_scales"]:
        for learning in config["learning_scales"]:
            for outcome in OUTCOMES:
                for repeats in config["trials_per_style_counts"]:
                    subset = alternative.loc[
                        np.isclose(alternative["effect_scale"], float(effect))
                        & np.isclose(alternative["learning_scale"], float(learning))
                        & alternative["outcome"].eq(outcome)
                        & alternative["trials_per_style"].eq(int(repeats))
                    ]
                    eligible = subset.loc[subset["design_eligible_for_minimum"]].sort_values(
                        "participants_recruited"
                    )
                    candidate = eligible.iloc[0] if not eligible.empty else None
                    matched_null = None
                    if candidate is not None:
                        match = null.loc[
                            np.isclose(null["learning_scale"], float(learning))
                            & null["participants_recruited"].eq(
                                int(candidate["participants_recruited"])
                            )
                            & null["trials_per_style"].eq(int(repeats))
                            & null["outcome"].eq(outcome)
                        ]
                        matched_null = match.iloc[0]
                    rows.append(
                        {
                            "effect_scale": float(effect),
                            "learning_scale": float(learning),
                            "outcome": outcome,
                            "trials_per_style": int(repeats),
                            "candidate": candidate,
                            "matched_null": matched_null,
                            "is_lower_boundary": bool(
                                candidate is not None
                                and int(candidate["participants_recruited"]) == smallest_n
                            ),
                        }
                    )
    return rows


def _render_candidate_minima(run: ValidatedPowerRun) -> tuple[list[str], list[dict[str, Any]]]:
    candidates = _candidate_rows(run)
    table_rows: list[tuple[object, ...]] = []
    for item in candidates:
        candidate = item["candidate"]
        matched_null = item["matched_null"]
        if candidate is None:
            participant_count = "None in evaluated grid"
            power = "—"
            null_rate = "—"
            note = "No row passed both the power lower-CI and matched-null criteria"
        else:
            participant_count = int(candidate["participants_recruited"])
            power = _interval(candidate)
            null_rate = _interval(matched_null)
            note = (
                "Lower grid boundary; smaller N was not evaluated"
                if item["is_lower_boundary"]
                else "Smallest evaluated eligible N"
            )
        repeats = item["trials_per_style"]
        table_rows.append(
            (
                _number(item["effect_scale"]),
                _number(item["learning_scale"]),
                _outcome_label(item["outcome"]),
                repeats,
                repeats * 3,
                participant_count,
                power,
                null_rate,
                note,
            )
        )
    lines = _table(
        (
            "Legacy effect scale",
            "Learning scale",
            "Outcome",
            "Trials/style",
            "Total trials/complete participant",
            "Candidate recruited N",
            "Operational power (MC CI)",
            "Matched null rejection (MC CI)",
            "Interpretation",
        ),
        table_rows,
    )
    return lines, candidates


def _render_null_calibration(run: ValidatedPowerRun) -> list[str]:
    config = run.manifest["config"]
    null = run.results.loc[run.results["scenario"].eq("no_style_effect")]
    rows: list[tuple[object, ...]] = []
    for learning in config["learning_scales"]:
        for outcome in OUTCOMES:
            for repeats in config["trials_per_style_counts"]:
                subset = null.loc[
                    np.isclose(null["learning_scale"], float(learning))
                    & null["outcome"].eq(outcome)
                    & null["trials_per_style"].eq(int(repeats))
                ].sort_values("participants_recruited")
                complete = subset.loc[subset["simulation_status"].eq("complete")]
                rows.append(
                    (
                        _number(learning),
                        _outcome_label(outcome),
                        int(repeats),
                        ", ".join(str(int(value)) for value in subset["participants_recruited"]),
                        f"{int(complete['operational_null_ci_contains_alpha'].sum())}/{len(subset)}",
                        _range(complete["estimated_rejection_rate"], percent=True),
                        (
                            f"{_percent(complete['mc_ci_low'].min())}–"
                            f"{_percent(complete['mc_ci_high'].max())}"
                            if not complete.empty
                            else "not estimable"
                        ),
                        len(subset) - len(complete),
                    )
                )
    return _table(
        (
            "Learning scale",
            "Outcome",
            "Trials/style",
            "Evaluated recruited N",
            "Null CIs containing α",
            "Rejection-rate range",
            "MC-CI envelope",
            "Non-estimable rows",
        ),
        rows,
    )


def _failure_reasons(value: object) -> str:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return str(value).strip() or "not recorded"
    if not isinstance(parsed, dict) or not parsed:
        return "not recorded"
    return "; ".join(f"{reason} ({count})" for reason, count in sorted(parsed.items()))


def _render_non_estimable(run: ValidatedPowerRun) -> list[str]:
    bad = run.results.loc[~run.results["simulation_status"].eq("complete")]
    declared = int(run.manifest["non_estimable_scenario_count"])
    if bad.empty:
        return [
            f"The manifest records {declared} non-estimable scenario cells; no outcome rows "
            "were marked non-estimable."
        ]
    rows = []
    for _, row in bad.sort_values(list(ROW_KEY)).iterrows():
        effect = "Null" if row["scenario"] == "no_style_effect" else _number(row["effect_scale"])
        rows.append(
            (
                "No style effect" if row["scenario"] == "no_style_effect" else "Alternative",
                effect,
                _number(row["learning_scale"]),
                _outcome_label(row["outcome"]),
                int(row["participants_recruited"]),
                int(row["trials_per_style"]),
                f"{int(row['models_fitted'])}/{int(row['model_fit_attempts'])}",
                _percent(row["fit_failure_rate"]),
                _failure_reasons(row["fit_failure_reasons"]),
            )
        )
    return [
        f"The manifest records **{declared}** non-estimable scenario cell(s), represented by "
        f"**{len(bad)}** non-estimable outcome row(s).",
        "",
        *_table(
            (
                "Scenario",
                "Effect scale",
                "Learning scale",
                "Outcome",
                "Recruited N",
                "Trials/style",
                "Fitted/attempted",
                "Fit-failure rate",
                "Aggregate failure reasons",
            ),
            rows,
        ),
    ]


def _render_realized_ranges(run: ValidatedPowerRun) -> list[str]:
    config = run.manifest["config"]
    scenario_rows = run.results.drop_duplicates(list(SCENARIO_KEY)).copy()
    rows: list[tuple[object, ...]] = []
    specifications = [
        ("alternative", float(effect), float(learning))
        for effect in config["effect_scales"]
        for learning in config["learning_scales"]
    ]
    specifications.extend(
        ("no_style_effect", 0.0, float(learning)) for learning in config["learning_scales"]
    )
    for scenario, effect, learning in specifications:
        subset = scenario_rows.loc[
            scenario_rows["scenario"].eq(scenario)
            & np.isclose(scenario_rows["effect_scale"], effect)
            & np.isclose(scenario_rows["learning_scale"], learning)
        ]
        for style in STYLES:
            rows.append(
                (
                    "Alternative" if scenario == "alternative" else "No style effect",
                    _number(effect) if scenario == "alternative" else "Null",
                    _number(learning),
                    STYLE_LABELS[style],
                    len(subset),
                    _range(subset[f"realized_accuracy_{style}"], percent=True),
                    _range(subset[f"realized_timeout_rate_{style}"], percent=True),
                    _range(
                        subset[f"realized_correct_rt_geometric_mean_ms_{style}"],
                        milliseconds=True,
                    ),
                )
            )
    return _table(
        (
            "Scenario",
            "Effect scale",
            "Learning scale",
            "Style",
            "Design cells",
            "Realized accuracy range",
            "Realized timeout range",
            "Realized correct-RT GM range",
        ),
        rows,
    )


def render_power_report(run: ValidatedPowerRun) -> str:
    manifest = run.manifest
    config = manifest["config"]
    results = run.results
    legacy = (
        "legacy" in str(manifest["status"]).lower() or "legacy" in str(manifest["warning"]).lower()
    )
    warning = (
        "This simulation was calibrated from **early protocol-1 experimental data "
        "(the legacy data)**. It is exploratory planning evidence, not independent "
        "confirmation, a definitive recruitment recommendation or a guarantee of achieved power. "
        "It represents the intended future protocol with its configured deadline and operational "
        "assumptions; it is not a literal reproduction of legacy rows, which used mixed 3,000 and "
        "5,000 ms deadlines."
        if legacy
        else (
            "This is an exploratory simulation report. The manifest does not identify the run "
            "as legacy-calibrated; do not describe it as based on legacy data without verifying "
            "the configuration provenance."
        )
    )

    scenario_level = results.drop_duplicates(list(SCENARIO_KEY))
    total_datasets = int(scenario_level["simulation_datasets_generated"].sum())
    total_fitted = int(results["models_fitted"].sum())
    total_attempts = int(results["model_fit_attempts"].sum())
    total_failures = int(results["model_failures"].sum())
    alternative_rows = results["scenario"].eq("alternative")
    null_rows = results["scenario"].eq("no_style_effect")
    candidates_table, candidates = _render_candidate_minima(run)
    candidate_values = [item for item in candidates if item["candidate"] is not None]
    no_candidate_count = len(candidates) - len(candidate_values)
    calibrated_nulls = int(results.loc[null_rows, "operational_null_ci_contains_alpha"].sum())
    non_estimable_rows = int((~results["simulation_status"].eq("complete")).sum())

    software = manifest["software_versions"]
    software_text = ", ".join(f"{name} {version}" for name, version in sorted(software.items()))
    participants = [int(value) for value in config["participant_counts"]]
    repeats = [int(value) for value in config["trials_per_style_counts"]]
    effects = [float(value) for value in config["effect_scales"]]
    learning = [float(value) for value in config["learning_scales"]]
    estimator = str(config["covariance_estimator"])
    estimator_label = (
        "bias-reduced sandwich covariance"
        if estimator == "bias_reduced"
        else "robust sandwich covariance"
    )
    effect_descriptions = ", ".join(
        f"{_number(value)} ({100 * value:g}% of the legacy-calibrated style contrasts)"
        for value in effects
    )
    learning_descriptions = ", ".join(
        f"{_number(value)} ({100 * value:g}% of the legacy-calibrated learning terms)"
        for value in learning
    )

    lines = [
        "# Legacy-data-calibrated GEE power simulation report",
        "",
        f"> **EARLY LEGACY DATA — EXPLORATORY ONLY.** {warning}",
        "",
        f"> **Manifest warning:** {_cell(manifest['warning'])}",
        "",
        "## Run identity and validation",
        "",
        *_table(
            ("Item", "Recorded value"),
            [
                ("Status", manifest["status"]),
                ("Grid status", manifest["grid_status"]),
                ("Random seed", config["seed"]),
                ("GEE covariance estimator", f"{estimator} ({estimator_label})"),
                ("Power-results SHA-256", f"`{run.results_sha256}`"),
                ("Power-manifest SHA-256", f"`{run.manifest_sha256}`"),
                ("Source configuration SHA-256", f"`{manifest['config_file_sha256']}`"),
                ("Effective configuration SHA-256", f"`{manifest['effective_config_sha256']}`"),
                ("Simulation source SHA-256", f"`{manifest['power_source_sha256']}`"),
                ("Software", software_text),
            ],
        ),
        "",
        (
            "The reporter verified the manifest/CSV hash and byte count, the configured Cartesian "
            "scenario grid, fitted-model accounting, Monte Carlo interval flags, matched null "
            "calibration and candidate-design eligibility. Only aggregate simulation outputs are "
            "included below."
        ),
        "",
        "## Simulation count and estimator",
        "",
        *_table(
            ("Quantity", "Value"),
            [
                (
                    "Successful GEE model fits targeted per scenario and outcome",
                    _integer(config["simulations"]),
                ),
                ("Alternative model-result rows", int(alternative_rows.sum())),
                ("Matched no-style-effect model-result rows", int(null_rows.sum())),
                ("Unique simulated scenario cells", len(scenario_level)),
                ("Simulated study datasets generated across those cells", f"{total_datasets:,}"),
                ("GEE models fitted", f"{total_fitted:,}"),
                ("GEE model-fit attempts", f"{total_attempts:,}"),
                ("Model-fit failures", f"{total_failures:,}"),
                ("Test", f"2-df global display-style test at α={float(config['alpha']):g}"),
                ("Working correlation and covariance", f"Exchangeable; {estimator_label}"),
                (
                    "Monte Carlo interval",
                    f"{100 * float(config['mc_confidence_level']):g}% exact binomial",
                ),
                ("Power target", _percent(config["target_power"], 0)),
            ],
        ),
        "",
        "A failed fit is counted as a non-rejection in the operational estimate. The null scenario is reused across effect scales within each matched design and learning scenario.",
        "",
        "## Evaluated grids",
        "",
        *_table(
            ("Dimension", "Configured values"),
            [
                ("Recruited participants", ", ".join(map(str, participants))),
                (
                    "Trials per style",
                    ", ".join(
                        f"{value} ({3 * value} total per complete participant)" for value in repeats
                    ),
                ),
                ("Legacy effect scales", effect_descriptions),
                ("Learning scales", learning_descriptions),
                (
                    "Outcomes",
                    "Correct response time among correct responses; accuracy within deadline",
                ),
            ],
        ),
        "",
        "## Candidate minima by effect, learning, outcome and repeat length",
        "",
        (
            "A candidate is selected only from rows where `design_eligible_for_minimum` is true: "
            "the simulation was estimable, the **lower** operational-power Monte Carlo limit met "
            "the target, and the matched no-style-effect interval contained nominal alpha. "
            "These are scenario-specific grid minima, not an automatically selected recruitment target."
        ),
        "",
        *candidates_table,
        "",
        "## No-style-effect calibration",
        "",
        (
            f"Nominal alpha was {_number(config['alpha'])}. The table summarizes operational null "
            "rejection rates over recruited-participant levels; the envelope is the smallest lower "
            "to largest upper Monte Carlo limit in each row."
        ),
        "",
        *_render_null_calibration(run),
        "",
        "## Non-estimable scenarios",
        "",
        *_render_non_estimable(run),
        "",
        "## Realized simulated outcome ranges",
        "",
        (
            "These are aggregate realized ranges across recruited-participant and trials-per-style "
            "design cells. They are simulation diagnostics, not observed outcomes from the future study."
        ),
        "",
        *_render_realized_ranges(run),
        "",
        "## Publication-adaptable Methods wording",
        "",
        (
            "> An exploratory simulation-based power analysis was calibrated using early protocol-1 "
            "experimental data (the legacy data), separately from any future confirmatory dataset. "
            "Simulated studies represented the intended future three-period randomized crossover, "
            "independent allocation "
            "among the six display-style sequences, participant and target-drug heterogeneity, period and "
            "within-period learning effects, the response deadline, non-start, dropout and missing results. "
            f"The design grid included recruited participant counts of {', '.join(map(str, participants))} "
            f"and {', '.join(map(str, repeats))} trials per style. Style contrasts were simulated at "
            f"{', '.join(f'{100 * value:g}%' for value in effects)} of the legacy-calibrated magnitude, "
            f"and learning terms at {', '.join(f'{100 * value:g}%' for value in learning)} of their "
            f"legacy-calibrated magnitude. For each scenario and outcome, {int(config['simulations']):,} "
            "successful GEE model fits were targeted, together with matched no-style-effect runs. "
            "Each dataset was analyzed with a participant-clustered exchangeable GEE, "
            f"{estimator_label}, and a 2-df global display-style test at alpha "
            f"{float(config['alpha']):g}. Operational power counted model-fit failures as "
            f"non-rejections and was reported with {100 * float(config['mc_confidence_level']):g}% exact "
            "binomial Monte Carlo confidence intervals. A design was considered a candidate only when "
            f"the lower power interval reached {100 * float(config['target_power']):g}% and its matched "
            "null interval contained nominal alpha."
        ),
        "",
        "## Publication-adaptable Results wording",
        "",
    ]

    if candidate_values:
        candidate_ns = [
            int(item["candidate"]["participants_recruited"]) for item in candidate_values
        ]
        candidate_powers = [
            float(item["candidate"]["estimated_rejection_rate"]) for item in candidate_values
        ]
        candidate_sentence = (
            f"Candidate recruited sample sizes ranged from {min(candidate_ns)} to {max(candidate_ns)} "
            f"across {len(candidate_values)} of {len(candidates)} configured effect-by-learning-by-"
            f"outcome-by-repeat combinations. Operational power at those candidate grid points ranged "
            f"from {_percent(min(candidate_powers))} to {_percent(max(candidate_powers))}. "
            f"No candidate was identified within the evaluated grid for {no_candidate_count} combination(s)."
        )
    else:
        candidate_sentence = (
            "No configured effect-by-learning-by-outcome-by-repeat combination produced an eligible "
            "candidate within the evaluated participant grid."
        )
    results_wording = (
        f"> The completed early-legacy-data exploratory simulation evaluated {int(alternative_rows.sum())} "
        f"alternative model-result cells and {int(null_rows.sum())} matched no-style-effect cells. "
        f"The nominal-alpha value lay within {calibrated_nulls} of {int(null_rows.sum())} operational "
        f"null Monte Carlo intervals. {candidate_sentence} {non_estimable_rows} outcome row(s) were "
        "non-estimable. Candidate values remained scenario-dependent; no single recruitment target was "
        "selected automatically. Because calibration used early experimental legacy data, these results "
        "are planning sensitivities rather than confirmatory evidence or a guarantee of achieved power."
    )
    lines.extend(
        [
            results_wording,
            "",
            (
                "Use the stratified candidate table—not the range alone—when adapting the Results text, "
                "and prespecify the effect scenario, learning scenario, outcome hierarchy and repeat length "
                "before choosing a recruitment target."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def build_power_report(input_path: str | Path, output_path: str | Path) -> Path:
    run = load_completed_power_run(input_path)
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Power report output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = render_power_report(run)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(report)
    output.chmod(0o600)
    return output


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Validate a completed power run and render an aggregate Markdown report"
    )
    command.add_argument(
        "--input", required=True, type=Path, help="Completed power output directory"
    )
    command.add_argument("--output", required=True, type=Path, help="New Markdown report path")
    return command


def main() -> None:
    args = parser().parse_args()
    output = build_power_report(args.input, args.output)
    print(f"Validated power report written to {output}")


if __name__ == "__main__":
    main()
