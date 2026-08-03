from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.ampoule_analysis.power_report import (
    PowerReportValidationError,
    build_power_report,
    load_completed_power_run,
)


def _write_manifest(directory: Path, manifest: dict[str, object]) -> None:
    results_path = directory / "power_results.csv"
    manifest["files"] = {
        "power_results.csv": {
            "sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
            "bytes": results_path.stat().st_size,
        }
    }
    (directory / "power_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _synthetic_power_output(directory: Path) -> dict[str, object]:
    directory.mkdir()
    participants = (24, 36)
    repeats = (10, 25)
    effects = (1.0, 0.5)
    learning = (1.0, 0.0)
    rows: list[dict[str, object]] = []
    specifications = [
        ("alternative", effect, learning_scale) for effect in effects for learning_scale in learning
    ] + [("no_style_effect", 0.0, learning_scale) for learning_scale in learning]
    for scenario, effect, learning_scale in specifications:
        for participant_count in participants:
            for repeat_count in repeats:
                for outcome in ("correct response time", "accuracy"):
                    is_alternative = scenario == "alternative"
                    calibrated = participant_count == 36
                    successes = 90 if is_alternative else (5 if calibrated else 10)
                    rejection_rate = successes / 100
                    ci_low, ci_high = (
                        (0.82, 0.95)
                        if is_alternative
                        else ((0.02, 0.10) if calibrated else (0.06, 0.16))
                    )
                    rows.append(
                        {
                            "scenario": scenario,
                            "effect_scale": effect,
                            "learning_scale": learning_scale,
                            "metric": "power" if is_alternative else "type I error",
                            "outcome": outcome,
                            "simulation_status": "complete",
                            "participants_recruited": participant_count,
                            "trials_per_style": repeat_count,
                            "successful_simulations_target": 100,
                            "simulation_datasets_generated": 100,
                            "models_fitted": 100,
                            "model_failures": 0,
                            "model_fit_attempts": 100,
                            "fit_failure_rate": 0.0,
                            "significant_global_tests": successes,
                            "estimated_rejection_rate": rejection_rate,
                            "conditional_rejection_rate_among_fitted": rejection_rate,
                            "estimated_power": rejection_rate if is_alternative else np.nan,
                            "conditional_power_among_fitted": (
                                rejection_rate if is_alternative else np.nan
                            ),
                            "estimated_type_i_error": (
                                rejection_rate if not is_alternative else np.nan
                            ),
                            "conditional_type_i_error_among_fitted": (
                                rejection_rate if not is_alternative else np.nan
                            ),
                            "mc_ci_low": ci_low,
                            "mc_ci_high": ci_high,
                            "conditional_mc_ci_low": ci_low,
                            "conditional_mc_ci_high": ci_high,
                            "mc_confidence_level": 0.95,
                            "target_power": 0.8 if is_alternative else np.nan,
                            "lower_ci_meets_target": is_alternative,
                            "operational_null_ci_contains_alpha": (
                                not is_alternative and calibrated
                            ),
                            "conditional_null_ci_contains_alpha": (
                                not is_alternative and calibrated
                            ),
                            "matched_null_mc_ci_contains_alpha": (is_alternative and calibrated),
                            "design_eligible_for_minimum": is_alternative and calibrated,
                            "is_smallest_evaluated_n": participant_count == 24,
                            "mean_participants_started": participant_count - 1,
                            "mean_participants_with_results": participant_count - 2,
                            "mean_submitted_results": participant_count * repeat_count * 2.5,
                            "mean_missing_results": 0.2,
                            "mean_timeouts": participant_count * 2,
                            "fit_failure_reasons": "{}",
                            "fit_warnings": "{}",
                            "realized_accuracy_industry": 0.75,
                            "realized_timeout_rate_industry": 0.20,
                            "realized_correct_rt_geometric_mean_ms_industry": (
                                2_000 + participant_count
                            ),
                            "realized_accuracy_iso": 0.91,
                            "realized_timeout_rate_iso": 0.05,
                            "realized_correct_rt_geometric_mean_ms_iso": 1_300 + participant_count,
                            "realized_accuracy_black_white": 0.85,
                            "realized_timeout_rate_black_white": 0.10,
                            "realized_correct_rt_geometric_mean_ms_black_white": (
                                2_100 + participant_count
                            ),
                        }
                    )
    pd.DataFrame(rows).to_csv(directory / "power_results.csv", index=False, lineterminator="\n")
    status = "exploratory_legacy_protocol_1_calibrated_not_for_recruitment"
    manifest: dict[str, object] = {
        "status": status,
        "warning": (
            "Legacy early-data-calibrated exploratory simulation based on protocol-1 early "
            "experimental data; it is not a recruitment recommendation."
        ),
        "grid_status": "complete",
        "non_estimable_scenario_count": 0,
        "smallest_evaluated_participant_count": 24,
        "execution_workers": 2,
        "config": {
            "status": status,
            "participant_counts": list(participants),
            "trials_per_style": repeats[0],
            "trials_per_style_counts": list(repeats),
            "effect_scales": list(effects),
            "learning_scales": list(learning),
            "simulations": 100,
            "seed": 20260802,
            "alpha": 0.05,
            "target_power": 0.8,
            "covariance_estimator": "bias_reduced",
            "mc_confidence_level": 0.95,
        },
        "config_file_sha256": "a" * 64,
        "effective_config_sha256": "b" * 64,
        "power_source_sha256": "c" * 64,
        "software_versions": {
            "numpy": "test",
            "pandas": "test",
            "scipy": "test",
            "statsmodels": "test",
            "matplotlib": "test",
        },
    }
    _write_manifest(directory, manifest)
    return manifest


def test_report_uses_only_eligible_rows_for_stratified_candidate_minima(tmp_path) -> None:
    power_output = tmp_path / "power"
    _synthetic_power_output(power_output)

    report_path = build_power_report(power_output, tmp_path / "legacy-power-report.md")
    report = report_path.read_text(encoding="utf-8")

    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert "EARLY LEGACY DATA — EXPLORATORY ONLY" in report
    assert "early protocol-1 experimental data (the legacy data)" in report
    assert "| 1 | 1 | Correct response time | 10 | 30 | 36 |" in report
    assert "Smallest evaluated eligible N" in report
    assert "Null CIs containing α" in report
    assert "1/2" in report
    assert "Realized simulated outcome ranges" in report
    assert "Publication-adaptable Methods wording" in report
    assert "Publication-adaptable Results wording" in report
    assert "participant_id" not in report


def test_report_rejects_a_results_file_that_no_longer_matches_manifest(tmp_path) -> None:
    power_output = tmp_path / "power"
    _synthetic_power_output(power_output)
    with (power_output / "power_results.csv").open("a", encoding="utf-8") as handle:
        handle.write("\n")

    with pytest.raises(PowerReportValidationError, match="SHA-256"):
        load_completed_power_run(power_output)


def test_report_rejects_an_ineligible_row_marked_as_a_candidate(tmp_path) -> None:
    power_output = tmp_path / "power"
    manifest = _synthetic_power_output(power_output)
    results_path = power_output / "power_results.csv"
    results = pd.read_csv(results_path)
    row = (
        results["scenario"].eq("alternative")
        & results["participants_recruited"].eq(24)
        & results["outcome"].eq("accuracy")
    )
    results.loc[row, "design_eligible_for_minimum"] = True
    results.to_csv(results_path, index=False, lineterminator="\n")
    _write_manifest(power_output, manifest)

    with pytest.raises(PowerReportValidationError, match="design_eligible_for_minimum"):
        load_completed_power_run(power_output)


def test_report_lists_non_estimable_rows_without_inventing_a_candidate(tmp_path) -> None:
    power_output = tmp_path / "power"
    manifest = _synthetic_power_output(power_output)
    results_path = power_output / "power_results.csv"
    results = pd.read_csv(results_path)
    row = (
        results["scenario"].eq("alternative")
        & results["effect_scale"].eq(1.0)
        & results["learning_scale"].eq(1.0)
        & results["participants_recruited"].eq(36)
        & results["trials_per_style"].eq(10)
        & results["outcome"].eq("accuracy")
    )
    results.loc[row, "simulation_status"] = "non_estimable_fit_failure"
    results.loc[row, "models_fitted"] = 90
    results.loc[row, "model_failures"] = 6
    results.loc[row, "model_fit_attempts"] = 96
    results.loc[row, "fit_failure_rate"] = 6 / 96
    results.loc[row, "significant_global_tests"] = 80
    for column in (
        "estimated_rejection_rate",
        "conditional_rejection_rate_among_fitted",
        "estimated_power",
        "conditional_power_among_fitted",
        "mc_ci_low",
        "mc_ci_high",
        "conditional_mc_ci_low",
        "conditional_mc_ci_high",
    ):
        results.loc[row, column] = np.nan
    results.loc[row, "lower_ci_meets_target"] = False
    results.loc[row, "design_eligible_for_minimum"] = False
    results.loc[row, "fit_failure_reasons"] = json.dumps({"RuntimeError: synthetic failure": 6})
    results.to_csv(results_path, index=False, lineterminator="\n")
    manifest["grid_status"] = "completed_with_non_estimable_scenarios"
    manifest["non_estimable_scenario_count"] = 1
    _write_manifest(power_output, manifest)

    report = build_power_report(power_output, tmp_path / "report.md").read_text(encoding="utf-8")

    assert "None in evaluated grid" in report
    assert "RuntimeError: synthetic failure (6)" in report
    assert "**1** non-estimable scenario cell" in report
