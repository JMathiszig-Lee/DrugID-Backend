from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
import shutil
import tomllib
import warnings
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from itertools import permutations, product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import expit
from statsmodels.genmod.cov_struct import Exchangeable
from statsmodels.genmod.families import Binomial, Gaussian
from statsmodels.genmod.generalized_estimating_equations import GEE

STYLES = ("Industry", "ISO", "Black and white")
STYLE_SLUGS = {
    "Industry": "industry",
    "ISO": "iso",
    "Black and white": "black_white",
}
DEFAULT_POWER_CONFIG = Path(__file__).resolve().parents[1] / "config" / "power.toml"
SIMULATION_COLUMNS = (
    "participant_id",
    "order_index",
    "assigned_order",
    "style",
    "period",
    "trial",
    "within_period_progress",
    "target_drug",
    "result_present",
    "choice_correct",
    "responded",
    "timed_out",
    "correct",
    "observed_rt_ms",
    "log_response_rt",
    "log_rt",
)


@dataclass(frozen=True)
class PowerConfig:
    status: str
    participant_counts: tuple[int, ...]
    trials_per_style: int
    trials_per_style_counts: tuple[int, ...]
    effect_scales: tuple[float, ...]
    learning_scales: tuple[float, ...]
    simulations: int
    seed: int
    alpha: float
    target_power: float
    covariance_estimator: str
    mc_confidence_level: float
    maximum_fit_failure_rate: float
    deadline_ms: float
    nonstarter_probability: float
    dropout_probability: float
    missing_result_probability: float
    number_of_target_drugs: int
    incorrect_choice_probabilities: tuple[float, float, float]
    participant_log_odds_sd: float
    participant_style_log_odds_sd: float
    drug_log_odds_sd: float
    drug_style_log_odds_sd: float
    period_log_odds_change: float
    within_period_log_odds_change: float
    industry_geometric_mean_ms: float
    rt_style_ratios: tuple[float, float, float]
    participant_log_sd: float
    participant_style_log_sd: float
    drug_log_sd: float
    drug_style_log_sd: float
    residual_log_sd: float
    participant_accuracy_rt_correlation: float
    participant_style_accuracy_rt_correlation: float
    drug_style_accuracy_rt_correlation: float
    period_log_change: float
    within_period_log_change: float
    figure_dpi: int


class PowerSimulationFitError(RuntimeError):
    """A simulated scenario whose model-fit failure limit was exceeded."""

    def __init__(
        self,
        message: str,
        *,
        scenario: str,
        effect_scale: float,
        learning_scale: float,
        details: dict[str, object],
        partial_rows: list[dict[str, object]],
    ) -> None:
        super().__init__(message)
        self.scenario = scenario
        self.effect_scale = effect_scale
        self.learning_scale = learning_scale
        self.details = details
        self.partial_rows = partial_rows


def _validate_power_config(config: PowerConfig) -> None:
    if not config.status.strip():
        raise ValueError("status must not be empty")
    if not config.participant_counts or min(config.participant_counts) < 6:
        raise ValueError("participant_counts must contain values of at least six")
    if tuple(sorted(set(config.participant_counts))) != config.participant_counts:
        raise ValueError("participant_counts must be unique and strictly increasing")
    if config.trials_per_style < 2 or config.simulations < 1:
        raise ValueError("trials_per_style must be >=2 and simulations must be positive")
    if (
        not config.trials_per_style_counts
        or min(config.trials_per_style_counts) < 2
        or tuple(sorted(set(config.trials_per_style_counts)))
        != config.trials_per_style_counts
    ):
        raise ValueError(
            "trials_per_style must be an integer or a strictly increasing list of integers >=2"
        )
    if not config.effect_scales or any(
        scale <= 0 or not math.isfinite(scale) for scale in config.effect_scales
    ):
        raise ValueError("effect_scales must contain positive finite values")
    if len(set(config.effect_scales)) != len(config.effect_scales):
        raise ValueError("effect_scales must contain unique values")
    if not config.learning_scales or any(
        scale < 0 or not math.isfinite(scale) for scale in config.learning_scales
    ):
        raise ValueError("learning_scales must contain non-negative finite values")
    if len(set(config.learning_scales)) != len(config.learning_scales):
        raise ValueError("learning_scales must contain unique values")
    if not 0 < config.alpha < 1 or not 0 < config.target_power < 1:
        raise ValueError("alpha and target_power must be between zero and one")
    if config.covariance_estimator not in {"robust", "bias_reduced"}:
        raise ValueError("covariance_estimator must be robust or bias_reduced")
    if not 0 < config.mc_confidence_level < 1:
        raise ValueError("mc_confidence_level must be between zero and one")
    if not 0 <= config.maximum_fit_failure_rate < 1:
        raise ValueError("maximum_fit_failure_rate must be in [0, 1)")
    for name, probability in (
        ("nonstarter_probability", config.nonstarter_probability),
        ("dropout_probability", config.dropout_probability),
        ("missing_result_probability", config.missing_result_probability),
    ):
        if not 0 <= probability < 1:
            raise ValueError(f"{name} must be in [0, 1)")
    if config.deadline_ms <= 0 or not math.isfinite(config.deadline_ms):
        raise ValueError("deadline_ms must be a positive finite number")
    if config.number_of_target_drugs < 2:
        raise ValueError("number_of_target_drugs must be at least two")
    if any(not 0 < probability < 1 for probability in config.incorrect_choice_probabilities):
        raise ValueError("incorrect-choice probabilities must be between zero and one")
    standard_deviations = {
        "participant_log_odds_sd": config.participant_log_odds_sd,
        "participant_style_log_odds_sd": config.participant_style_log_odds_sd,
        "drug_log_odds_sd": config.drug_log_odds_sd,
        "drug_style_log_odds_sd": config.drug_style_log_odds_sd,
        "participant_log_sd": config.participant_log_sd,
        "participant_style_log_sd": config.participant_style_log_sd,
        "drug_log_sd": config.drug_log_sd,
        "drug_style_log_sd": config.drug_style_log_sd,
        "residual_log_sd": config.residual_log_sd,
    }
    if any(value < 0 or not math.isfinite(value) for value in standard_deviations.values()):
        raise ValueError("all standard deviations must be finite and non-negative")
    if not -1 <= config.participant_accuracy_rt_correlation <= 1:
        raise ValueError("participant_accuracy_rt_correlation must be between -1 and 1")
    correlations = {
        "participant_style_accuracy_rt_correlation": (
            config.participant_style_accuracy_rt_correlation
        ),
        "drug_style_accuracy_rt_correlation": config.drug_style_accuracy_rt_correlation,
    }
    if any(not -1 <= value <= 1 for value in correlations.values()):
        raise ValueError("style accuracy/RT correlations must be between -1 and 1")
    if (
        config.industry_geometric_mean_ms <= 0
        or not math.isfinite(config.industry_geometric_mean_ms)
        or any(ratio <= 0 or not math.isfinite(ratio) for ratio in config.rt_style_ratios)
    ):
        raise ValueError("reaction-time means and ratios must be positive and finite")
    changes = (
        config.period_log_odds_change,
        config.within_period_log_odds_change,
        config.period_log_change,
        config.within_period_log_change,
    )
    if any(not math.isfinite(value) for value in changes):
        raise ValueError("period and progress effects must be finite")
    if config.figure_dpi < 1:
        raise ValueError("figure DPI must be positive")


def load_power_config(path: str | Path | None = None) -> PowerConfig:
    config_path = Path(path) if path else DEFAULT_POWER_CONFIG
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    accuracy = raw["accuracy"]
    reaction_time = raw["reaction_time"]
    raw_trials_per_style = raw["trials_per_style"]
    if isinstance(raw_trials_per_style, list):
        trials_per_style_counts = tuple(int(value) for value in raw_trials_per_style)
    else:
        trials_per_style_counts = (int(raw_trials_per_style),)
    effect_scales = tuple(float(value) for value in raw.get("effect_scales", [1.0]))
    learning_scales = tuple(float(value) for value in raw.get("learning_scales", [1.0]))
    config = PowerConfig(
        status=str(raw["status"]),
        participant_counts=tuple(int(value) for value in raw["participant_counts"]),
        # Keep a scalar active value so simulation helpers and callers using
        # dataclasses.replace remain backwards compatible. run_power_grid
        # replaces it with each configured grid value in turn.
        trials_per_style=trials_per_style_counts[0],
        trials_per_style_counts=trials_per_style_counts,
        effect_scales=effect_scales,
        learning_scales=learning_scales,
        simulations=int(raw["simulations"]),
        seed=int(raw["seed"]),
        alpha=float(raw["alpha"]),
        target_power=float(raw["target_power"]),
        covariance_estimator=str(raw.get("covariance_estimator", "robust")),
        mc_confidence_level=float(raw["mc_confidence_level"]),
        maximum_fit_failure_rate=float(raw["maximum_fit_failure_rate"]),
        deadline_ms=float(raw["deadline_ms"]),
        nonstarter_probability=float(raw["nonstarter_probability"]),
        dropout_probability=float(raw["dropout_probability"]),
        missing_result_probability=float(raw["missing_result_probability"]),
        number_of_target_drugs=int(raw["number_of_target_drugs"]),
        incorrect_choice_probabilities=(
            float(accuracy["incorrect_choice_probability_industry"]),
            float(accuracy["incorrect_choice_probability_iso"]),
            float(accuracy["incorrect_choice_probability_black_white"]),
        ),
        participant_log_odds_sd=float(accuracy["participant_log_odds_sd"]),
        participant_style_log_odds_sd=float(
            accuracy.get("participant_style_log_odds_sd", 0.0)
        ),
        drug_log_odds_sd=float(accuracy["drug_log_odds_sd"]),
        drug_style_log_odds_sd=float(accuracy.get("drug_style_log_odds_sd", 0.0)),
        period_log_odds_change=float(accuracy["period_log_odds_change"]),
        within_period_log_odds_change=float(accuracy["within_period_log_odds_change"]),
        industry_geometric_mean_ms=float(reaction_time["industry_geometric_mean_ms"]),
        rt_style_ratios=(
            1.0,
            float(reaction_time["geometric_mean_ratio_iso"]),
            float(reaction_time["geometric_mean_ratio_black_white"]),
        ),
        participant_log_sd=float(reaction_time["participant_log_sd"]),
        participant_style_log_sd=float(
            reaction_time.get("participant_style_log_sd", 0.0)
        ),
        drug_log_sd=float(reaction_time["drug_log_sd"]),
        drug_style_log_sd=float(reaction_time.get("drug_style_log_sd", 0.0)),
        residual_log_sd=float(reaction_time["residual_log_sd"]),
        participant_accuracy_rt_correlation=float(
            reaction_time["participant_accuracy_rt_correlation"]
        ),
        participant_style_accuracy_rt_correlation=float(
            reaction_time.get("participant_style_accuracy_rt_correlation", 0.0)
        ),
        drug_style_accuracy_rt_correlation=float(
            reaction_time.get("drug_style_accuracy_rt_correlation", 0.0)
        ),
        period_log_change=float(reaction_time["period_log_change"]),
        within_period_log_change=float(reaction_time["within_period_log_change"]),
        figure_dpi=int(raw["figures"]["dpi"]),
    )
    _validate_power_config(config)
    return config


def _logit(probability: float) -> float:
    return math.log(probability / (1 - probability))


def _participant_effects(config: PowerConfig, rng: np.random.Generator) -> tuple[float, float]:
    covariance = np.array(
        [
            [
                config.participant_log_odds_sd**2,
                config.participant_accuracy_rt_correlation
                * config.participant_log_odds_sd
                * config.participant_log_sd,
            ],
            [
                config.participant_accuracy_rt_correlation
                * config.participant_log_odds_sd
                * config.participant_log_sd,
                config.participant_log_sd**2,
            ],
        ]
    )
    values = rng.multivariate_normal((0.0, 0.0), covariance, check_valid="raise")
    return float(values[0]), float(values[1])


def _centered_style_effects(
    units: int,
    accuracy_sd: float,
    rt_sd: float,
    correlation: float,
    rng: np.random.Generator,
    *,
    double_center: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw correlated unit-by-style deviations centered within each unit."""

    if accuracy_sd == 0 and rt_sd == 0:
        zeros = np.zeros((units, len(STYLES)))
        return zeros.copy(), zeros
    covariance = np.array(
        [
            [accuracy_sd**2, correlation * accuracy_sd * rt_sd],
            [correlation * accuracy_sd * rt_sd, rt_sd**2],
        ]
    )
    values = rng.multivariate_normal(
        (0.0, 0.0), covariance, size=(units, len(STYLES)), check_valid="raise"
    )
    values -= values.mean(axis=1, keepdims=True)
    if double_center:
        # Row centering makes each drug's style interaction sum to zero. The
        # subsequent column centering also makes the configured finite drug set
        # average to zero for every style; its column offsets sum to zero, so
        # the row constraint is retained.
        values -= values.mean(axis=0, keepdims=True)
    return values[:, :, 0], values[:, :, 1]


def _scaled_style_assumptions(
    config: PowerConfig,
    effect_scale: float,
    *,
    null_effects: bool,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return style assumptions with contrasts shrunk towards Industry.

    Accuracy is parameterised as an incorrect-choice probability, so its
    contrasts are scaled on that probability's logit scale. Reaction-time
    ratios are scaled on the log scale. Nuisance period, progress and variance
    assumptions are deliberately unchanged.
    """

    if effect_scale <= 0 or not math.isfinite(effect_scale):
        raise ValueError("effect_scale must be positive and finite")
    industry_incorrect_logit = _logit(config.incorrect_choice_probabilities[0])
    incorrect_by_style = {
        style: float(
            expit(
                industry_incorrect_logit
                + effect_scale * (_logit(probability) - industry_incorrect_logit)
            )
        )
        for style, probability in zip(
            STYLES, config.incorrect_choice_probabilities, strict=True
        )
    }
    rt_ratio_by_style = {
        style: math.exp(effect_scale * math.log(ratio))
        for style, ratio in zip(STYLES, config.rt_style_ratios, strict=True)
    }
    if null_effects:
        incorrect_by_style = dict.fromkeys(STYLES, config.incorrect_choice_probabilities[0])
        rt_ratio_by_style = dict.fromkeys(STYLES, 1.0)
    return incorrect_by_style, rt_ratio_by_style


def simulate_crossover(
    config: PowerConfig,
    participants: int,
    rng: np.random.Generator,
    *,
    null_effects: bool = False,
    effect_scale: float = 1.0,
    learning_scale: float = 1.0,
) -> pd.DataFrame:
    """Simulate recruited participants and trial rows from the deployed crossover.

    Orders are sampled independently, as they are by the backend. A non-starter
    contributes no trial rows. Scheduled dropout occurs after a randomly selected
    completed trial, while a missing result leaves one final generated trial and
    stops that participant because the application cannot advance past it.
    """

    if participants < 1:
        raise ValueError("participants must be positive")
    if learning_scale < 0 or not math.isfinite(learning_scale):
        raise ValueError("learning_scale must be non-negative and finite")
    orders = tuple(permutations(STYLES))
    assignments = rng.integers(0, len(orders), size=participants)
    accuracy_drug_effects = rng.normal(0, config.drug_log_odds_sd, config.number_of_target_drugs)
    rt_drug_effects = rng.normal(0, config.drug_log_sd, config.number_of_target_drugs)
    accuracy_participant_style, rt_participant_style = _centered_style_effects(
        participants,
        config.participant_style_log_odds_sd,
        config.participant_style_log_sd,
        config.participant_style_accuracy_rt_correlation,
        rng,
    )
    accuracy_drug_style, rt_drug_style = _centered_style_effects(
        config.number_of_target_drugs,
        config.drug_style_log_odds_sd,
        config.drug_style_log_sd,
        config.drug_style_accuracy_rt_correlation,
        rng,
        double_center=True,
    )
    incorrect_by_style, rt_ratio_by_style = _scaled_style_assumptions(
        config, effect_scale, null_effects=null_effects
    )
    rows: list[dict[str, object]] = []
    planned_trials = len(STYLES) * config.trials_per_style
    style_indices = {style: index for index, style in enumerate(STYLES)}

    for participant in range(participants):
        order_index = int(assignments[participant])
        order = orders[order_index]
        if rng.random() < config.nonstarter_probability:
            continue
        accuracy_participant, rt_participant = _participant_effects(config, rng)
        completed_results_before_dropout = planned_trials
        if rng.random() < config.dropout_probability:
            completed_results_before_dropout = int(rng.integers(1, planned_trials))
        completed_results = 0
        stopped = False

        for period, style in enumerate(order, start=1):
            if stopped:
                break
            style_incorrect_logit = _logit(incorrect_by_style[style])
            style_index = style_indices[style]
            for trial in range(config.trials_per_style):
                if completed_results >= completed_results_before_dropout:
                    stopped = True
                    break
                progress = trial / (config.trials_per_style - 1)
                drug = int(rng.integers(0, config.number_of_target_drugs))
                base_row: dict[str, object] = {
                    "participant_id": participant,
                    "order_index": order_index,
                    "assigned_order": " > ".join(order),
                    "style": style,
                    "period": period,
                    "trial": trial,
                    "within_period_progress": progress,
                    "target_drug": f"drug_{drug:02d}",
                }
                if rng.random() < config.missing_result_probability:
                    rows.append(
                        {
                            **base_row,
                            "result_present": False,
                            "choice_correct": np.nan,
                            "responded": np.nan,
                            "timed_out": np.nan,
                            "correct": np.nan,
                            "observed_rt_ms": np.nan,
                            "log_response_rt": np.nan,
                            "log_rt": np.nan,
                        }
                    )
                    stopped = True
                    break

                incorrect_logit = (
                    style_incorrect_logit
                    + accuracy_participant
                    + accuracy_participant_style[participant, style_index]
                    + accuracy_drug_effects[drug]
                    + accuracy_drug_style[drug, style_index]
                    - learning_scale * config.period_log_odds_change * (period - 1)
                    - learning_scale * config.within_period_log_odds_change * progress
                )
                choice_correct = bool(rng.random() >= expit(incorrect_logit))
                log_response_rt = (
                    math.log(config.industry_geometric_mean_ms)
                    + math.log(rt_ratio_by_style[style])
                    + rt_participant
                    + rt_participant_style[participant, style_index]
                    + rt_drug_effects[drug]
                    + rt_drug_style[drug, style_index]
                    + learning_scale * config.period_log_change * (period - 1)
                    + learning_scale * config.within_period_log_change * progress
                    + rng.normal(0, config.residual_log_sd)
                )
                response_time_ms = math.exp(min(log_response_rt, math.log(np.finfo(float).max)))
                responded = response_time_ms < config.deadline_ms
                timed_out = not responded
                correct = bool(responded and choice_correct)
                rows.append(
                    {
                        **base_row,
                        "result_present": True,
                        "choice_correct": choice_correct if responded else np.nan,
                        "responded": responded,
                        "timed_out": timed_out,
                        "correct": int(correct),
                        "observed_rt_ms": response_time_ms if responded else np.nan,
                        "log_response_rt": log_response_rt if responded else np.nan,
                        "log_rt": log_response_rt if correct else np.nan,
                    }
                )
                completed_results += 1

    data = pd.DataFrame.from_records(rows, columns=SIMULATION_COLUMNS)
    data["style"] = pd.Categorical(data["style"], categories=STYLES, ordered=True)
    data.attrs["participants_recruited"] = participants
    data.attrs["assigned_order_counts"] = np.bincount(assignments, minlength=len(orders)).tolist()
    return data


def _global_style_p(
    data: pd.DataFrame,
    outcome: str,
    family,
    *,
    covariance_estimator: str = "robust",
) -> tuple[float, tuple[str, ...]]:
    eligible = data.loc[data["result_present"].eq(True)].copy()  # noqa: E712
    if outcome == "log_rt":
        eligible = eligible.loc[eligible["log_rt"].notna()].copy()
    if eligible["participant_id"].nunique() < 3:
        raise ValueError("global test needs at least three participant clusters")
    if eligible["style"].nunique() != len(STYLES):
        raise ValueError("global test needs observed results from all three styles")
    formula = (
        f"{outcome} ~ C(style, Treatment(reference='Industry')) + C(period) + "
        "within_period_progress + C(target_drug)"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = GEE.from_formula(
            formula,
            groups="participant_id",
            data=eligible,
            cov_struct=Exchangeable(),
            family=family,
        )
        result = model.fit(maxiter=200, cov_type=covariance_estimator)
        if not getattr(result, "converged", True):
            raise RuntimeError("GEE did not converge")
        indices = [
            index
            for index, term in enumerate(result.params.index)
            if "C(style" in term and ")[T." in term and ":" not in term
        ]
        expected_terms = len(STYLES) - 1
        if len(indices) != expected_terms:
            raise RuntimeError(
                f"expected {expected_terms} style coefficients, found {len(indices)}"
            )
        restriction = np.zeros((expected_terms, len(result.params)))
        for row, index in enumerate(indices):
            restriction[row, index] = 1
        restriction_covariance = restriction @ np.asarray(result.cov_params()) @ restriction.T
        if not np.isfinite(restriction_covariance).all():
            raise RuntimeError("global style restriction covariance is non-finite")
        rank = int(np.linalg.matrix_rank(restriction_covariance))
        if rank != expected_terms:
            raise RuntimeError(
                f"global style restriction has rank {rank}, expected {expected_terms}"
            )
        test = result.wald_test(restriction, scalar=True)
        p_value = float(np.asarray(test.pvalue).squeeze())
        if not np.isfinite(p_value):
            raise RuntimeError("global style test returned a non-finite p value")
    warning_messages = tuple(f"{item.category.__name__}: {item.message}" for item in caught)
    return p_value, warning_messages


def _monte_carlo_interval(
    successes: int, attempts: int, confidence_level: float
) -> tuple[float, float]:
    if not attempts:
        return np.nan, np.nan
    tail = (1 - confidence_level) / 2
    low = (
        0.0 if successes == 0 else float(stats.beta.ppf(tail, successes, attempts - successes + 1))
    )
    high = (
        1.0
        if successes == attempts
        else float(stats.beta.ppf(1 - tail, successes + 1, attempts - successes))
    )
    return low, high


def _scenario_power(
    config: PowerConfig,
    participants: int,
    *,
    scenario: str,
    effect_scale: float,
    learning_scale: float,
    seed_sequence: np.random.SeedSequence,
) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed_sequence)
    labels = ("correct response time", "accuracy")
    successes = Counter({label: 0 for label in labels})
    fitted = Counter({label: 0 for label in labels})
    failures = Counter({label: 0 for label in labels})
    failure_reasons = {label: Counter() for label in labels}
    warning_reasons = {label: Counter() for label in labels}
    diagnostics = Counter()
    allowed_failures = math.floor(
        config.simulations * config.maximum_fit_failure_rate / (1 - config.maximum_fit_failure_rate)
    )
    maximum_datasets = config.simulations + allowed_failures
    datasets = 0
    specifications = (
        ("correct response time", "log_rt", Gaussian()),
        ("accuracy", "correct", Binomial()),
    )

    while datasets < maximum_datasets and any(
        fitted[label] < config.simulations for label in labels
    ):
        data = simulate_crossover(
            config,
            participants,
            rng,
            null_effects=scenario == "no_style_effect",
            effect_scale=effect_scale,
            learning_scale=learning_scale,
        )
        datasets += 1
        present = data["result_present"].eq(True)  # noqa: E712
        diagnostics["participants_started"] += data["participant_id"].nunique()
        diagnostics["participants_with_results"] += data.loc[present, "participant_id"].nunique()
        diagnostics["submitted_results"] += int(present.sum())
        diagnostics["missing_results"] += int(data["result_present"].eq(False).sum())  # noqa: E712
        diagnostics["timeouts"] += int(data.loc[present, "timed_out"].eq(True).sum())  # noqa: E712
        for style, slug in STYLE_SLUGS.items():
            style_present = present & data["style"].eq(style)
            style_correct = style_present & data["correct"].eq(1)
            diagnostics[f"{slug}_submitted"] += int(style_present.sum())
            diagnostics[f"{slug}_correct"] += int(style_correct.sum())
            diagnostics[f"{slug}_timeouts"] += int(
                (style_present & data["timed_out"].eq(True)).sum()  # noqa: E712
            )
            diagnostics[f"{slug}_correct_rt_count"] += int(
                data.loc[style_correct, "log_rt"].notna().sum()
            )
            diagnostics[f"{slug}_correct_log_rt_sum"] += float(
                data.loc[style_correct, "log_rt"].sum()
            )

        for label, outcome, family in specifications:
            if fitted[label] >= config.simulations:
                continue
            try:
                p_value, fit_warnings = _global_style_p(
                    data,
                    outcome,
                    family,
                    covariance_estimator=config.covariance_estimator,
                )
                fitted[label] += 1
                successes[label] += int(p_value < config.alpha)
                warning_reasons[label].update(fit_warnings)
            except Exception as exc:
                failures[label] += 1
                failure_reasons[label][f"{type(exc).__name__}: {exc}"] += 1

    incomplete = [label for label in labels if fitted[label] < config.simulations]
    excessive = [
        label
        for label in labels
        if failures[label] / max(fitted[label] + failures[label], 1)
        > config.maximum_fit_failure_rate
    ]
    invalid_labels = sorted(set(incomplete + excessive))
    detail: dict[str, object] = {}
    if invalid_labels:
        detail = {
            label: {
                "fitted": fitted[label],
                "failures": failures[label],
                "reasons": dict(failure_reasons[label]),
            }
            for label in invalid_labels
        }

    rows: list[dict[str, object]] = []
    for label in labels:
        model_attempts = fitted[label] + failures[label]
        complete = label not in invalid_labels
        operational_estimate = (
            successes[label] / model_attempts if complete and model_attempts else np.nan
        )
        conditional_estimate = (
            successes[label] / fitted[label] if complete and fitted[label] else np.nan
        )
        low, high = _monte_carlo_interval(
            successes[label], model_attempts, config.mc_confidence_level
        )
        conditional_low, conditional_high = _monte_carlo_interval(
            successes[label], fitted[label], config.mc_confidence_level
        )
        if not complete:
            low = high = conditional_low = conditional_high = np.nan
        is_alternative = scenario == "alternative"
        realized: dict[str, float] = {}
        for _, slug in STYLE_SLUGS.items():
            submitted = diagnostics[f"{slug}_submitted"]
            correct_rt_count = diagnostics[f"{slug}_correct_rt_count"]
            realized[f"realized_accuracy_{slug}"] = (
                diagnostics[f"{slug}_correct"] / submitted if submitted else np.nan
            )
            realized[f"realized_timeout_rate_{slug}"] = (
                diagnostics[f"{slug}_timeouts"] / submitted if submitted else np.nan
            )
            realized[f"realized_correct_rt_geometric_mean_ms_{slug}"] = (
                math.exp(diagnostics[f"{slug}_correct_log_rt_sum"] / correct_rt_count)
                if correct_rt_count
                else np.nan
            )
        rows.append(
            {
                "scenario": scenario,
                "effect_scale": effect_scale if is_alternative else 0.0,
                "learning_scale": learning_scale,
                "metric": "power" if is_alternative else "type I error",
                "outcome": label,
                "simulation_status": (
                    "complete" if complete else "non_estimable_fit_failure"
                ),
                "participants_recruited": participants,
                "trials_per_style": config.trials_per_style,
                "successful_simulations_target": config.simulations,
                "simulation_datasets_generated": datasets,
                "models_fitted": fitted[label],
                "model_failures": failures[label],
                "model_fit_attempts": model_attempts,
                "fit_failure_rate": (
                    failures[label] / model_attempts if model_attempts else np.nan
                ),
                "significant_global_tests": successes[label],
                # The operational estimate conservatively treats a failed fit as
                # a non-rejection. Recruitment decisions use this rate and CI.
                "estimated_rejection_rate": operational_estimate,
                "conditional_rejection_rate_among_fitted": conditional_estimate,
                "estimated_power": operational_estimate if is_alternative else np.nan,
                "conditional_power_among_fitted": (
                    conditional_estimate if is_alternative else np.nan
                ),
                "estimated_type_i_error": (operational_estimate if not is_alternative else np.nan),
                "conditional_type_i_error_among_fitted": (
                    conditional_estimate if not is_alternative else np.nan
                ),
                "mc_ci_low": low,
                "mc_ci_high": high,
                "conditional_mc_ci_low": conditional_low,
                "conditional_mc_ci_high": conditional_high,
                "mc_confidence_level": config.mc_confidence_level,
                "target_power": config.target_power if is_alternative else np.nan,
                "lower_ci_meets_target": bool(
                    is_alternative and np.isfinite(low) and low >= config.target_power
                ),
                "operational_null_ci_contains_alpha": bool(
                    not is_alternative and low <= config.alpha <= high
                ),
                "conditional_null_ci_contains_alpha": bool(
                    not is_alternative and conditional_low <= config.alpha <= conditional_high
                ),
                "mean_participants_started": diagnostics["participants_started"] / datasets,
                "mean_participants_with_results": diagnostics["participants_with_results"]
                / datasets,
                "mean_submitted_results": diagnostics["submitted_results"] / datasets,
                "mean_missing_results": diagnostics["missing_results"] / datasets,
                "mean_timeouts": diagnostics["timeouts"] / datasets,
                "fit_failure_reasons": json.dumps(dict(failure_reasons[label]), sort_keys=True),
                "fit_warnings": json.dumps(dict(warning_reasons[label]), sort_keys=True),
                **realized,
            }
        )
    if invalid_labels:
        raise PowerSimulationFitError(
            f"Power simulation exceeded its fit-failure limit for {scenario} "
            f"at effect scale {effect_scale:g} and learning scale {learning_scale:g}: "
            + json.dumps(detail, sort_keys=True),
            scenario=scenario,
            effect_scale=effect_scale,
            learning_scale=learning_scale,
            details=detail,
            partial_rows=rows,
        )
    return rows


def _estimate_power_cell(
    config: PowerConfig,
    participants: int,
    *,
    seed_sequence: np.random.SeedSequence,
    continue_on_fit_failure: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    _validate_power_config(config)
    # Give each learning scenario its own deterministic subtree. Within it,
    # spawn the null first so adding an effect sensitivity does not change the
    # matched type-I-error calibration stream.
    specifications = []
    learning_seeds = seed_sequence.spawn(len(config.learning_scales))
    for learning_scale, learning_seed in zip(
        config.learning_scales, learning_seeds, strict=True
    ):
        null_seed, *alternative_seeds = learning_seed.spawn(1 + len(config.effect_scales))
        specifications.extend(
            (
                "alternative",
                effect_scale,
                learning_scale,
                alternative_seed,
            )
            for effect_scale, alternative_seed in zip(
                config.effect_scales, alternative_seeds, strict=True
            )
        )
        specifications.append(("no_style_effect", 1.0, learning_scale, null_seed))
    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for scenario, effect_scale, learning_scale, child_seed in specifications:
        try:
            rows.extend(
                _scenario_power(
                    config,
                    participants,
                    scenario=scenario,
                    effect_scale=effect_scale,
                    learning_scale=learning_scale,
                    seed_sequence=child_seed,
                )
            )
        except PowerSimulationFitError as exc:
            if not continue_on_fit_failure:
                raise
            rows.extend(exc.partial_rows)
            failures.append(
                {
                    "participants_recruited": participants,
                    "trials_per_style": config.trials_per_style,
                    "scenario": exc.scenario,
                    "effect_scale": (
                        exc.effect_scale if exc.scenario == "alternative" else 0.0
                    ),
                    "learning_scale": exc.learning_scale,
                    "failure_details": json.dumps(exc.details, sort_keys=True),
                }
            )
    return rows, failures


def estimate_power(
    config: PowerConfig,
    participants: int,
    *,
    seed_sequence: np.random.SeedSequence,
) -> list[dict[str, object]]:
    rows, _ = _estimate_power_cell(
        config,
        participants,
        seed_sequence=seed_sequence,
        continue_on_fit_failure=False,
    )
    return rows


def _run_power_cell_task(
    config: PowerConfig, participants: int, trials_per_style: int
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Run one independent design cell without writing shared output files."""

    cell_config = replace(config, trials_per_style=trials_per_style)
    seed_sequence = np.random.SeedSequence([config.seed, participants, trials_per_style])
    return _estimate_power_cell(
        cell_config,
        participants,
        seed_sequence=seed_sequence,
        continue_on_fit_failure=True,
    )


def _add_minimum_eligibility(results: pd.DataFrame, config: PowerConfig) -> pd.DataFrame:
    """Match each power row to its null calibration before selecting minima."""

    results = results.copy()
    results["matched_null_mc_ci_contains_alpha"] = False
    results["design_eligible_for_minimum"] = False
    smallest_n = min(config.participant_counts)
    results["is_smallest_evaluated_n"] = results["participants_recruited"].eq(smallest_n)
    calibration = results.loc[results["scenario"].eq("no_style_effect")]
    for index, row in results.loc[results["scenario"].eq("alternative")].iterrows():
        matched = calibration.loc[
            calibration["participants_recruited"].eq(row["participants_recruited"])
            & calibration["trials_per_style"].eq(row["trials_per_style"])
            & calibration["learning_scale"].eq(row["learning_scale"])
            & calibration["outcome"].eq(row["outcome"])
        ]
        calibrated = bool(
            len(matched) == 1
            and matched.iloc[0]["simulation_status"] == "complete"
            and matched.iloc[0]["operational_null_ci_contains_alpha"]
        )
        results.at[index, "matched_null_mc_ci_contains_alpha"] = calibrated
        results.at[index, "design_eligible_for_minimum"] = bool(
            row["simulation_status"] == "complete"
            and row["lower_ci_meets_target"]
            and calibrated
        )
    return results


def _power_context_label(config: PowerConfig) -> str:
    if "legacy" in config.status.lower():
        return "Legacy early-data-calibrated exploratory"
    return "Exploratory simulation"


def _power_warning(config: PowerConfig) -> str:
    if "legacy" in config.status.lower():
        return (
            "Legacy early-data-calibrated exploratory simulation based on protocol-1 "
            "early experimental data; it is not a recruitment recommendation."
        )
    return "Illustrative assumptions are not a recruitment recommendation."


def _power_figure(results: pd.DataFrame, output: Path, config: PowerConfig) -> list[Path]:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "savefig.dpi": config.figure_dpi,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )
    complete = results.loc[results["simulation_status"].eq("complete")].copy()
    reference_learning = config.learning_scales[0]
    reference = complete.loc[complete["learning_scale"].eq(reference_learning)]
    alternative = reference.loc[reference["scenario"].eq("alternative")]
    calibration = reference.loc[reference["scenario"].eq("no_style_effect")]
    repeat_values = sorted(complete["trials_per_style"].dropna().astype(int).unique())
    colour_values = (
        plt.cm.viridis(np.linspace(0.15, 0.85, len(repeat_values)))
        if repeat_values
        else []
    )
    repeat_colours = dict(zip(repeat_values, colour_values, strict=True))
    line_styles = ("-", "--", ":", "-.")
    scale_values = list(config.effect_scales)
    scale_styles = {
        scale: line_styles[index % len(line_styles)] for index, scale in enumerate(scale_values)
    }

    outcomes = ("correct response time", "accuracy")
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True, sharex=True)
    calibration_high_values = calibration["mc_ci_high"].dropna().to_numpy(float)
    calibration_limit = (
        min(1.02, max(0.2, float(calibration_high_values.max()) * 1.1))
        if calibration_high_values.size
        else 0.2
    )
    for row_index, outcome in enumerate(outcomes):
        alternative_axis = axes[row_index, 0]
        calibration_axis = axes[row_index, 1]
        outcome_alternative = alternative.loc[alternative["outcome"].eq(outcome)]
        for (repeats, scale), subset in outcome_alternative.groupby(
            ["trials_per_style", "effect_scale"], observed=True
        ):
            repeats = int(repeats)
            scale = float(scale)
            subset = subset.sort_values("participants_recruited")
            x = subset["participants_recruited"].to_numpy(float)
            estimate = subset["estimated_rejection_rate"].to_numpy(float)
            low = subset["mc_ci_low"].to_numpy(float)
            high = subset["mc_ci_high"].to_numpy(float)
            colour = repeat_colours[repeats]
            label = f"{repeats} trials/style; {scale:g}× effect"
            alternative_axis.plot(
                x,
                estimate,
                marker="o",
                color=colour,
                linestyle=scale_styles.get(scale, "-"),
                label=label,
            )
            alternative_axis.fill_between(x, low, high, color=colour, alpha=0.10)
        alternative_axis.axhline(
            config.target_power,
            color="#555555",
            linestyle="--",
            linewidth=1,
            label=f"Target {config.target_power:.0%}",
        )
        alternative_axis.set_ylim(0, 1.02)
        alternative_axis.set_ylabel(f"{outcome.title()}\nOperational power")
        alternative_axis.legend(fontsize=7)

        outcome_calibration = calibration.loc[calibration["outcome"].eq(outcome)]
        for repeats, subset in outcome_calibration.groupby("trials_per_style", observed=True):
            repeats = int(repeats)
            subset = subset.sort_values("participants_recruited")
            x = subset["participants_recruited"].to_numpy(float)
            estimate = subset["estimated_rejection_rate"].to_numpy(float)
            low = subset["mc_ci_low"].to_numpy(float)
            high = subset["mc_ci_high"].to_numpy(float)
            colour = repeat_colours[repeats]
            calibration_axis.plot(
                x,
                estimate,
                marker="o",
                color=colour,
                label=f"{repeats} trials/style",
            )
            calibration_axis.fill_between(x, low, high, color=colour, alpha=0.10)
        calibration_axis.axhline(
            config.alpha,
            color="#555555",
            linestyle="--",
            linewidth=1,
            label=f"Nominal alpha {config.alpha:.0%}",
        )
        calibration_axis.set_ylim(0, calibration_limit)
        calibration_axis.set_ylabel(f"{outcome.title()}\nNull rejection rate")
        calibration_axis.legend(fontsize=7)

    axes[0, 0].set_title("Alternative scenarios")
    axes[0, 1].set_title("Type-I-error calibration (one run per design cell)")
    for axis in axes.flat:
        axis.set_xlabel("Participants recruited")
        axis.grid(axis="y", color="#dddddd", linewidth=0.6)
    fig.suptitle(
        f"{_power_context_label(config)}: randomized crossover diagnostics "
        f"(learning scale {reference_learning:g})"
    )
    paths = []
    for extension in ("png", "svg", "pdf"):
        path = output / f"power_curve.{extension}"
        fig.savefig(path, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def _learning_sensitivity_figure(
    results: pd.DataFrame, output: Path, config: PowerConfig
) -> list[Path]:
    if len(config.learning_scales) < 2:
        return []
    complete = results.loc[
        results["simulation_status"].eq("complete")
        & results["scenario"].eq("alternative")
    ]
    repeats = list(config.trials_per_style_counts)
    colours = dict(
        zip(repeats, plt.cm.viridis(np.linspace(0.15, 0.85, len(repeats))), strict=True)
    )
    line_styles = ("-", "--", ":", "-.")
    style_by_effect = {
        scale: line_styles[index % len(line_styles)]
        for index, scale in enumerate(config.effect_scales)
    }
    outcomes = ("correct response time", "accuracy")
    columns = len(config.learning_scales)
    fig, axes = plt.subplots(
        2,
        columns,
        figsize=(max(10, 3.7 * columns), 7),
        sharex=True,
        sharey=True,
        squeeze=False,
        constrained_layout=True,
    )
    for row_index, outcome in enumerate(outcomes):
        for column_index, learning_scale in enumerate(config.learning_scales):
            axis = axes[row_index, column_index]
            subset = complete.loc[
                complete["outcome"].eq(outcome)
                & complete["learning_scale"].eq(learning_scale)
            ]
            for (trials_per_style, effect_scale), line in subset.groupby(
                ["trials_per_style", "effect_scale"], observed=True
            ):
                line = line.sort_values("participants_recruited")
                axis.plot(
                    line["participants_recruited"],
                    line["estimated_rejection_rate"],
                    marker="o",
                    color=colours[int(trials_per_style)],
                    linestyle=style_by_effect[float(effect_scale)],
                    label=f"{int(trials_per_style)}/style; {float(effect_scale):g}× effect",
                )
            axis.axhline(config.target_power, color="#555555", linestyle="--", linewidth=1)
            axis.set_ylim(0, 1.02)
            axis.grid(axis="y", color="#dddddd", linewidth=0.6)
            axis.set_xlabel("Participants recruited")
            if row_index == 0:
                axis.set_title(f"Learning scale {learning_scale:g}")
            if column_index == 0:
                axis.set_ylabel(f"{outcome.title()}\nOperational power")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="outside lower center", ncol=min(3, len(handles)), fontsize=7)
    fig.suptitle(f"{_power_context_label(config)}: training-effect sensitivity")
    paths = []
    for extension in ("png", "svg", "pdf"):
        path = output / f"power_learning_sensitivity.{extension}"
        fig.savefig(path, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def run_power_grid(
    output_path: str | Path,
    *,
    config_path: str | Path | None = None,
    simulations: int | None = None,
    workers: int = 1,
    covariance_estimator: str | None = None,
    acknowledge_assumptions: bool = False,
) -> Path:
    if not acknowledge_assumptions:
        raise ValueError(
            "Power assumptions are illustrative. Review power.toml and pass "
            "--acknowledge-assumptions to run."
        )
    if workers < 1:
        raise ValueError("workers must be a positive integer")
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Power output already exists: {output}")
    config_file = Path(config_path).resolve() if config_path else DEFAULT_POWER_CONFIG.resolve()
    config_file_bytes = config_file.read_bytes()
    source_bytes = Path(__file__).read_bytes()
    config = load_power_config(config_file)
    if simulations is not None:
        if simulations < 1:
            raise ValueError("simulations override must be positive")
        config = PowerConfig(**{**asdict(config), "simulations": simulations})
        _validate_power_config(config)
    if covariance_estimator is not None:
        config = replace(config, covariance_estimator=covariance_estimator)
        _validate_power_config(config)
    effective_config_json = json.dumps(asdict(config), indent=2, sort_keys=True) + "\n"
    output.mkdir(mode=0o700, parents=True)
    try:
        output.chmod(0o700)
        (output / "effective_power_config.json").write_text(effective_config_json, encoding="utf-8")
        rows: list[dict[str, object]] = []
        cell_failures: list[dict[str, object]] = []
        design_cells = list(product(config.participant_counts, config.trials_per_style_counts))
        cell_outputs: dict[
            tuple[int, int], tuple[list[dict[str, object]], list[dict[str, object]]]
        ] = {}
        if workers == 1:
            for participants, trials_per_style in design_cells:
                print(
                    f"Simulating {participants} recruited participants, "
                    f"{trials_per_style} trials/style and "
                    f"{len(config.effect_scales)} alternative effect scale(s) "
                    f"across {len(config.learning_scales)} learning scale(s) "
                    f"({config.simulations:,} successful fits per scenario and outcome)...",
                    flush=True,
                )
                cell_outputs[(participants, trials_per_style)] = _run_power_cell_task(
                    config, participants, trials_per_style
                )
        else:
            # Spawned workers inherit these limits before importing NumPy,
            # avoiding BLAS oversubscription when several GEE fits run at once.
            thread_variables = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
            added_thread_limits = [name for name in thread_variables if name not in os.environ]
            for name in added_thread_limits:
                os.environ[name] = "1"
            try:
                with ProcessPoolExecutor(
                    max_workers=workers, mp_context=multiprocessing.get_context("spawn")
                ) as executor:
                    futures = {
                        executor.submit(
                            _run_power_cell_task, config, participants, trials_per_style
                        ): (participants, trials_per_style)
                        for participants, trials_per_style in design_cells
                    }
                    for future in as_completed(futures):
                        participants, trials_per_style = futures[future]
                        cell_outputs[(participants, trials_per_style)] = future.result()
                        print(
                            f"Completed {participants} recruited participants and "
                            f"{trials_per_style} trials/style.",
                            flush=True,
                        )
            finally:
                for name in added_thread_limits:
                    os.environ.pop(name, None)
        # Aggregate in configured order so output hashes are independent of
        # worker scheduling.
        for design_cell in design_cells:
            cell_rows, failures = cell_outputs[design_cell]
            rows.extend(cell_rows)
            cell_failures.extend(failures)
        results = _add_minimum_eligibility(pd.DataFrame(rows), config)
        results.to_csv(output / "power_results.csv", index=False, lineterminator="\n")
        if cell_failures:
            pd.DataFrame(cell_failures).to_csv(
                output / "non_estimable_scenarios.csv", index=False, lineterminator="\n"
            )
        _power_figure(results, output, config)
        _learning_sensitivity_figure(results, output, config)
        minimums: dict[str, object] = {}
        alternative = results.loc[
            results["scenario"].eq("alternative")
            & results["simulation_status"].eq("complete")
        ]
        for effect_scale in config.effect_scales:
            scale_minimums: dict[str, object] = {}
            for learning_scale in config.learning_scales:
                learning_minimums: dict[str, object] = {}
                for trials_per_style in config.trials_per_style_counts:
                    repeat_minimums: dict[str, object] = {}
                    design = alternative.loc[
                        alternative["effect_scale"].eq(effect_scale)
                        & alternative["learning_scale"].eq(learning_scale)
                        & alternative["trials_per_style"].eq(trials_per_style)
                    ]
                    for outcome in ("correct response time", "accuracy"):
                        eligible = design.loc[
                            design["outcome"].eq(outcome)
                            & design["design_eligible_for_minimum"]
                        ]
                        minimum_n = (
                            int(eligible["participants_recruited"].min())
                            if not eligible.empty
                            else None
                        )
                        repeat_minimums[outcome] = {
                            "participants_recruited": minimum_n,
                            "is_smallest_evaluated_n": bool(
                                minimum_n == min(config.participant_counts)
                                if minimum_n is not None
                                else False
                            ),
                        }
                    learning_minimums[str(trials_per_style)] = repeat_minimums
                scale_minimums[f"{learning_scale:g}"] = learning_minimums
            minimums[f"{effect_scale:g}"] = scale_minimums
        manifest = {
            "status": config.status,
            "warning": _power_warning(config),
            "grid_status": (
                "completed_with_non_estimable_scenarios" if cell_failures else "complete"
            ),
            "non_estimable_scenario_count": len(cell_failures),
            "smallest_evaluated_participant_count": min(config.participant_counts),
            "execution_workers": workers,
            "config": asdict(config),
            "config_file_sha256": hashlib.sha256(config_file_bytes).hexdigest(),
            "effective_config_sha256": hashlib.sha256(
                effective_config_json.encode("utf-8")
            ).hexdigest(),
            "power_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            # These minima use the operational lower CI, which counts failed
            # fits as non-rejections rather than silently conditioning on success.
            "minimum_n_with_power_and_matched_null_calibration_by_effect_learning_and_trials_per_style": minimums,
            "software_versions": {
                package: importlib.metadata.version(package)
                for package in ("numpy", "pandas", "scipy", "statsmodels", "matplotlib")
            },
            "files": {
                path.name: {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
                for path in sorted(output.iterdir())
                if path.is_file()
            },
        }
        manifest_path = output / "power_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        for generated_file in output.iterdir():
            if generated_file.is_file():
                generated_file.chmod(0o600)
        return output
    except Exception:
        shutil.rmtree(output)
        raise


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Simulate power and type-I error for the Ampoule crossover GEE models"
    )
    command.add_argument("--output", required=True, type=Path)
    command.add_argument("--config", type=Path)
    command.add_argument(
        "--simulations", type=int, help="Override successful fits per scenario and outcome"
    )
    command.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Independent design cells to run concurrently (default: 1)",
    )
    command.add_argument(
        "--covariance-estimator",
        choices=("robust", "bias_reduced"),
        help="GEE sandwich covariance estimator (overrides the power config)",
    )
    command.add_argument(
        "--acknowledge-assumptions",
        action="store_true",
        help="Confirm that the illustrative target effects have been reviewed",
    )
    return command


def main() -> None:
    args = parser().parse_args()
    output = run_power_grid(
        args.output,
        config_path=args.config,
        simulations=args.simulations,
        workers=args.workers,
        covariance_estimator=args.covariance_estimator,
        acknowledge_assumptions=args.acknowledge_assumptions,
    )
    print(f"Power analysis written to {output}")


if __name__ == "__main__":
    main()
