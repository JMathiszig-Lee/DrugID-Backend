from __future__ import annotations

import csv
import json
import math
import stat
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from statsmodels.genmod.families import Binomial

from analysis.ampoule_analysis import power
from analysis.ampoule_analysis.power import (
    DEFAULT_POWER_CONFIG,
    STYLES,
    _add_minimum_eligibility,
    _centered_style_effects,
    _global_style_p,
    _monte_carlo_interval,
    _power_context_label,
    _power_warning,
    _scaled_style_assumptions,
    estimate_power,
    load_power_config,
    run_power_grid,
    simulate_crossover,
)


def _complete_config(**changes):
    values = {
        "trials_per_style": 4,
        "nonstarter_probability": 0,
        "dropout_probability": 0,
        "missing_result_probability": 0,
        "number_of_target_drugs": 3,
    }
    values.update(changes)
    return replace(load_power_config(), **values)


def test_simulation_assigns_every_style_within_complete_participant() -> None:
    config = _complete_config()
    data = simulate_crossover(config, participants=12, rng=np.random.default_rng(1234))

    counts = data.groupby("participant_id", observed=True)["style"].nunique()
    trials = data.groupby(["participant_id", "style"], observed=True).size()
    assert (counts == len(STYLES)).all()
    assert (trials == config.trials_per_style).all()
    assert len(data) == 12 * len(STYLES) * config.trials_per_style


def test_order_assignment_is_independent_and_matches_backend_semantics() -> None:
    config = _complete_config()
    seed = 417
    expected = np.random.default_rng(seed).integers(0, 6, size=24)
    data = simulate_crossover(config, participants=24, rng=np.random.default_rng(seed))
    observed = data.groupby("participant_id", observed=True)["order_index"].first().to_numpy(int)

    assert np.array_equal(observed, expected)
    assert np.ptp(np.bincount(observed, minlength=6)) > 1


def test_deadline_creates_timeouts_and_correct_rt_eligibility() -> None:
    config = _complete_config(
        deadline_ms=1,
        participant_log_sd=0,
        drug_log_sd=0,
        residual_log_sd=0,
    )
    data = simulate_crossover(config, participants=12, rng=np.random.default_rng(91))

    assert data["result_present"].all()
    assert data["timed_out"].all()
    assert not data["responded"].any()
    assert not data["correct"].any()
    assert data["observed_rt_ms"].isna().all()
    assert data["log_rt"].isna().all()


def test_incorrect_responses_keep_observed_rt_but_not_correct_rt() -> None:
    config = _complete_config(deadline_ms=1_000_000)
    data = simulate_crossover(config, participants=18, rng=np.random.default_rng(7))
    incorrect = data["result_present"] & data["responded"] & ~data["correct"].astype(bool)

    assert incorrect.any()
    assert data.loc[incorrect, "observed_rt_ms"].notna().all()
    assert data.loc[incorrect, "log_response_rt"].notna().all()
    assert data.loc[incorrect, "log_rt"].isna().all()


def test_nonstarters_midstudy_dropout_and_missing_results_are_distinct() -> None:
    base = _complete_config()
    nonstarters = simulate_crossover(
        replace(base, nonstarter_probability=1),
        participants=8,
        rng=np.random.default_rng(1),
    )
    assert nonstarters.empty

    dropout = simulate_crossover(
        replace(base, dropout_probability=1),
        participants=8,
        rng=np.random.default_rng(2),
    )
    per_participant = dropout.groupby("participant_id", observed=True).size()
    assert per_participant.between(1, len(STYLES) * base.trials_per_style - 1).all()
    assert dropout["result_present"].all()

    missing = simulate_crossover(
        replace(base, missing_result_probability=1),
        participants=8,
        rng=np.random.default_rng(3),
    )
    assert len(missing) == 8
    assert not missing["result_present"].any()
    assert missing["correct"].isna().all()


def test_global_test_is_finite_for_exactly_two_style_terms() -> None:
    config = _complete_config(trials_per_style=8, deadline_ms=1_000_000)
    data = simulate_crossover(config, participants=24, rng=np.random.default_rng(2026))
    p_value, fit_warnings = _global_style_p(data, "correct", Binomial())

    assert 0 <= p_value <= 1
    assert isinstance(fit_warnings, tuple)


def test_global_test_supports_bias_reduced_covariance() -> None:
    config = _complete_config(trials_per_style=8, deadline_ms=1_000_000)
    data = simulate_crossover(config, participants=36, rng=np.random.default_rng(2027))
    p_value, _ = _global_style_p(
        data, "correct", Binomial(), covariance_estimator="bias_reduced"
    )

    assert 0 <= p_value <= 1


def test_monte_carlo_confidence_is_separate_from_model_alpha() -> None:
    interval_90 = _monte_carlo_interval(50, 100, 0.90)
    interval_95 = _monte_carlo_interval(50, 100, 0.95)

    assert interval_95[0] < interval_90[0]
    assert interval_95[1] > interval_90[1]


def test_style_effect_scaling_uses_logit_and_log_contrasts() -> None:
    config = _complete_config()
    incorrect, rt_ratios = _scaled_style_assumptions(
        config, 0.5, null_effects=False
    )

    def logit(probability: float) -> float:
        return math.log(probability / (1 - probability))

    original_accuracy_contrast = logit(config.incorrect_choice_probabilities[1]) - logit(
        config.incorrect_choice_probabilities[0]
    )
    scaled_accuracy_contrast = logit(incorrect["ISO"]) - logit(incorrect["Industry"])
    assert scaled_accuracy_contrast == pytest.approx(0.5 * original_accuracy_contrast)
    assert math.log(rt_ratios["ISO"]) == pytest.approx(
        0.5 * math.log(config.rt_style_ratios[1])
    )


def test_config_accepts_repeat_grid_and_effect_scales(tmp_path) -> None:
    text = DEFAULT_POWER_CONFIG.read_text(encoding="utf-8")
    text = text.replace("trials_per_style = 50", "trials_per_style = [4, 8, 12]")
    text = text.replace("effect_scales = [1.0]", "effect_scales = [1.0, 0.5]")
    text = text.replace("learning_scales = [1.0]", "learning_scales = [1.0, 0.0]")
    path = tmp_path / "grid.toml"
    path.write_text(text, encoding="utf-8")

    config = load_power_config(path)

    assert config.trials_per_style == 4
    assert config.trials_per_style_counts == (4, 8, 12)
    assert config.effect_scales == (1.0, 0.5)
    assert config.learning_scales == (1.0, 0.0)
    assert config.covariance_estimator == "robust"


def test_legacy_power_outputs_are_explicitly_labelled_as_early_data() -> None:
    config = replace(_complete_config(), status="legacy_protocol_1_exploratory")

    assert _power_context_label(config) == "Legacy early-data-calibrated exploratory"
    assert "early experimental data" in _power_warning(config)


def test_unit_style_effects_are_centered_for_participants_and_drugs() -> None:
    accuracy, reaction_time = _centered_style_effects(
        20, 0.7, 0.3, 0.4, np.random.default_rng(61)
    )

    assert accuracy.shape == (20, len(STYLES))
    assert reaction_time.shape == (20, len(STYLES))
    assert np.allclose(accuracy.sum(axis=1), 0)
    assert np.allclose(reaction_time.sum(axis=1), 0)
    assert accuracy.std() > 0
    assert reaction_time.std() > 0

    drug_accuracy, drug_reaction_time = _centered_style_effects(
        20, 0.7, 0.3, 0.4, np.random.default_rng(62), double_center=True
    )
    assert np.allclose(drug_accuracy.mean(axis=1), 0)
    assert np.allclose(drug_accuracy.mean(axis=0), 0)
    assert np.allclose(drug_reaction_time.mean(axis=1), 0)
    assert np.allclose(drug_reaction_time.mean(axis=0), 0)


def test_power_requires_explicit_assumption_acknowledgement(tmp_path) -> None:
    with pytest.raises(ValueError, match="illustrative"):
        run_power_grid(tmp_path / "power")


def test_small_seeded_power_run_returns_power_and_calibration_rows() -> None:
    config = _complete_config(
        participant_counts=(24,),
        trials_per_style=6,
        simulations=1,
        deadline_ms=1_000_000,
        maximum_fit_failure_rate=0,
    )
    rows = estimate_power(
        config,
        participants=24,
        seed_sequence=np.random.SeedSequence(99),
    )

    assert {row["outcome"] for row in rows} == {"accuracy", "correct response time"}
    assert {row["scenario"] for row in rows} == {"alternative", "no_style_effect"}
    assert len(rows) == 4
    assert all(row["models_fitted"] == 1 for row in rows)
    assert all(row["model_failures"] == 0 for row in rows)
    assert all(0 <= row["estimated_rejection_rate"] <= 1 for row in rows)
    assert all("realized_accuracy_industry" in row for row in rows)


def test_effect_sensitivities_share_one_null_run_per_design_cell() -> None:
    config = _complete_config(
        participant_counts=(24,),
        trials_per_style=6,
        effect_scales=(1.0, 0.5),
        simulations=1,
        deadline_ms=1_000_000,
        maximum_fit_failure_rate=0,
    )
    rows = estimate_power(
        config,
        participants=24,
        seed_sequence=np.random.SeedSequence(190),
    )

    alternatives = [row for row in rows if row["scenario"] == "alternative"]
    calibration = [row for row in rows if row["scenario"] == "no_style_effect"]
    assert len(alternatives) == 4
    assert {row["effect_scale"] for row in alternatives} == {1.0, 0.5}
    assert len(calibration) == 2
    assert {row["effect_scale"] for row in calibration} == {0.0}


def test_learning_sensitivities_run_each_effect_and_one_matched_null() -> None:
    config = _complete_config(
        participant_counts=(24,),
        trials_per_style=6,
        effect_scales=(1.0, 0.5),
        learning_scales=(1.0, 0.0),
        simulations=1,
        deadline_ms=1_000_000,
        maximum_fit_failure_rate=0,
    )
    rows = estimate_power(config, 24, seed_sequence=np.random.SeedSequence(812))

    alternatives = [row for row in rows if row["scenario"] == "alternative"]
    calibration = [row for row in rows if row["scenario"] == "no_style_effect"]
    assert len(alternatives) == 8
    assert {(row["effect_scale"], row["learning_scale"]) for row in alternatives} == {
        (1.0, 1.0),
        (0.5, 1.0),
        (1.0, 0.0),
        (0.5, 0.0),
    }
    assert len(calibration) == 4
    assert {row["learning_scale"] for row in calibration} == {1.0, 0.0}


def test_minimum_eligibility_requires_matched_null_calibration() -> None:
    config = _complete_config(participant_counts=(24, 36))
    rows = pd.DataFrame(
        [
            {
                "scenario": "alternative",
                "participants_recruited": 24,
                "trials_per_style": 4,
                "learning_scale": 1.0,
                "outcome": "accuracy",
                "simulation_status": "complete",
                "lower_ci_meets_target": True,
                "operational_null_ci_contains_alpha": False,
            },
            {
                "scenario": "no_style_effect",
                "participants_recruited": 24,
                "trials_per_style": 4,
                "learning_scale": 1.0,
                "outcome": "accuracy",
                "simulation_status": "complete",
                "lower_ci_meets_target": False,
                "operational_null_ci_contains_alpha": False,
            },
            {
                "scenario": "alternative",
                "participants_recruited": 36,
                "trials_per_style": 4,
                "learning_scale": 1.0,
                "outcome": "accuracy",
                "simulation_status": "complete",
                "lower_ci_meets_target": True,
                "operational_null_ci_contains_alpha": False,
            },
            {
                "scenario": "no_style_effect",
                "participants_recruited": 36,
                "trials_per_style": 4,
                "learning_scale": 1.0,
                "outcome": "accuracy",
                "simulation_status": "complete",
                "lower_ci_meets_target": False,
                "operational_null_ci_contains_alpha": True,
            },
        ]
    )
    checked = _add_minimum_eligibility(rows, config)
    alternative = checked.loc[checked["scenario"].eq("alternative")]

    assert alternative["design_eligible_for_minimum"].tolist() == [False, True]
    assert alternative["is_smallest_evaluated_n"].tolist() == [True, False]


def test_operational_power_counts_failed_fit_as_non_rejection(monkeypatch) -> None:
    config = _complete_config(
        participant_counts=(24,),
        simulations=1,
        maximum_fit_failure_rate=0.5,
    )
    calls = 0

    def flaky_global_test(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic fit failure")
        return 0.01, ("SyntheticWarning",)

    monkeypatch.setattr(power, "_global_style_p", flaky_global_test)
    rows = estimate_power(
        config,
        participants=24,
        seed_sequence=np.random.SeedSequence(404),
    )
    rt = next(
        row
        for row in rows
        if row["scenario"] == "alternative" and row["outcome"] == "correct response time"
    )

    assert rt["models_fitted"] == 1
    assert rt["model_failures"] == 1
    assert rt["conditional_rejection_rate_among_fitted"] == 1
    assert rt["estimated_rejection_rate"] == 0.5


def test_all_failed_models_abort_instead_of_reporting_zero_power() -> None:
    config = _complete_config(
        participant_counts=(12,),
        simulations=1,
        deadline_ms=1,
        participant_log_sd=0,
        drug_log_sd=0,
        residual_log_sd=0,
        maximum_fit_failure_rate=0,
    )
    with pytest.raises(RuntimeError, match="fit-failure limit"):
        estimate_power(
            config,
            participants=12,
            seed_sequence=np.random.SeedSequence(101),
        )


def _small_power_config(
    path,
    *,
    trials_per_style: str = "4",
    effect_scales: str | None = None,
    learning_scales: str | None = None,
) -> None:
    text = DEFAULT_POWER_CONFIG.read_text(encoding="utf-8")
    replacements = {
        "participant_counts = [24, 36, 48, 60, 72, 90, 120]": "participant_counts = [24]",
        "trials_per_style = 50": f"trials_per_style = {trials_per_style}",
        "deadline_ms = 3000": "deadline_ms = 1000000",
        "nonstarter_probability = 0.05": "nonstarter_probability = 0",
        "dropout_probability = 0.10": "dropout_probability = 0",
        "missing_result_probability = 0.0005": "missing_result_probability = 0",
        "number_of_target_drugs = 20": "number_of_target_drugs = 3",
    }
    for old, new in replacements.items():
        assert old in text
        text = text.replace(old, new)
    if effect_scales is not None:
        text = text.replace("effect_scales = [1.0]", f"effect_scales = {effect_scales}")
    if learning_scales is not None:
        text = text.replace("learning_scales = [1.0]", f"learning_scales = {learning_scales}")
    path.write_text(text, encoding="utf-8")


def test_power_output_is_private_and_null_scenario_survives_csv(tmp_path) -> None:
    config_path = tmp_path / "power.toml"
    _small_power_config(config_path)
    output = run_power_grid(
        tmp_path / "power",
        config_path=config_path,
        simulations=1,
        covariance_estimator="bias_reduced",
        acknowledge_assumptions=True,
    )

    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())
    with (output / "power_results.csv").open(newline="", encoding="utf-8") as handle:
        scenarios = {row["scenario"] for row in csv.DictReader(handle)}
    assert scenarios == {"alternative", "no_style_effect"}
    effective = json.loads((output / "effective_power_config.json").read_text(encoding="utf-8"))
    assert effective["covariance_estimator"] == "bias_reduced"


def test_power_grid_crosses_repeat_counts_and_effect_scales(tmp_path) -> None:
    config_path = tmp_path / "power.toml"
    _small_power_config(
        config_path,
        trials_per_style="[4, 5]",
        effect_scales="[1.0, 0.5]",
        learning_scales="[1.0, 0.0]",
    )
    output = run_power_grid(
        tmp_path / "power-grid",
        config_path=config_path,
        simulations=1,
        workers=2,
        acknowledge_assumptions=True,
    )

    with (output / "power_results.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    alternative_cells = {
        (
            int(row["trials_per_style"]),
            float(row["effect_scale"]),
            float(row["learning_scale"]),
        )
        for row in rows
        if row["scenario"] == "alternative"
    }
    null_cells = {
        (
            int(row["trials_per_style"]),
            float(row["effect_scale"]),
            float(row["learning_scale"]),
        )
        for row in rows
        if row["scenario"] == "no_style_effect"
    }
    assert alternative_cells == {
        (repeats, effect, learning)
        for repeats in (4, 5)
        for effect in (1.0, 0.5)
        for learning in (1.0, 0.0)
    }
    assert null_cells == {
        (repeats, 0.0, learning) for repeats in (4, 5) for learning in (1.0, 0.0)
    }
    manifest = json.loads((output / "power_manifest.json").read_text(encoding="utf-8"))
    minimums = manifest[
        "minimum_n_with_power_and_matched_null_calibration_by_effect_learning_and_trials_per_style"
    ]
    assert set(minimums) == {"1", "0.5"}
    assert set(minimums["1"]) == {"1", "0"}
    assert set(minimums["1"]["1"]) == {"4", "5"}
    assert (output / "power_learning_sensitivity.png").exists()


def test_failed_power_run_removes_partial_output(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "power.toml"
    _small_power_config(config_path)
    output = tmp_path / "failed-power"

    def fail_estimation(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(power, "_estimate_power_cell", fail_estimation)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        run_power_grid(
            output,
            config_path=config_path,
            simulations=1,
            acknowledge_assumptions=True,
        )
    assert not output.exists()
