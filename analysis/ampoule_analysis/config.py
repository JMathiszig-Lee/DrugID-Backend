from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalysisConfig:
    schema_version: int
    analysis_name: str
    style_reference: str
    style_order: tuple[str, ...]
    alpha: float
    confidence_level: float
    bootstrap_iterations: int
    bootstrap_seed: int
    training_bins: int
    minimum_plausible_rt_ms: int
    covariance: str
    adjust_for_period: bool
    adjust_for_within_period_progress: bool
    adjust_for_target_drug: bool
    adjust_for_configuration: bool
    figure_dpi: int
    figure_width: float
    figure_height: float


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "primary.toml"


def load_config(path: str | Path | None = None) -> AnalysisConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    model = raw["models"]
    figure = raw["figures"]
    config = AnalysisConfig(
        schema_version=int(raw["schema_version"]),
        analysis_name=str(raw["analysis_name"]),
        style_reference=str(raw["style_reference"]),
        style_order=tuple(str(value) for value in raw["style_order"]),
        alpha=float(raw["alpha"]),
        confidence_level=float(raw["confidence_level"]),
        bootstrap_iterations=int(raw["bootstrap_iterations"]),
        bootstrap_seed=int(raw["bootstrap_seed"]),
        training_bins=int(raw["training_bins"]),
        minimum_plausible_rt_ms=int(raw["minimum_plausible_rt_ms"]),
        covariance=str(model["covariance"]),
        adjust_for_period=bool(model["adjust_for_period"]),
        adjust_for_within_period_progress=bool(model["adjust_for_within_period_progress"]),
        adjust_for_target_drug=bool(model["adjust_for_target_drug"]),
        adjust_for_configuration=bool(model["adjust_for_configuration"]),
        figure_dpi=int(figure["dpi"]),
        figure_width=float(figure["width_inches"]),
        figure_height=float(figure["height_inches"]),
    )
    if not 0 < config.alpha < 1:
        raise ValueError("alpha must be between zero and one")
    if not 0 < config.confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")
    if not abs(config.confidence_level - (1 - config.alpha)) < 1e-12:
        raise ValueError("confidence_level must equal 1 - alpha")
    if len(config.style_order) != 3 or len(set(config.style_order)) != 3:
        raise ValueError("style_order must contain exactly three unique display styles")
    if config.style_reference not in config.style_order:
        raise ValueError("style_reference must be present in style_order")
    if config.bootstrap_iterations < 100:
        raise ValueError("bootstrap_iterations must be at least 100")
    if config.training_bins < 2:
        raise ValueError("training_bins must be at least two")
    if config.minimum_plausible_rt_ms <= 0:
        raise ValueError("minimum_plausible_rt_ms must be positive")
    if config.covariance not in {"exchangeable", "independence"}:
        raise ValueError("covariance must be exchangeable or independence")
    if config.figure_dpi <= 0 or config.figure_width <= 0 or config.figure_height <= 0:
        raise ValueError("figure dimensions and DPI must be positive")
    return config
