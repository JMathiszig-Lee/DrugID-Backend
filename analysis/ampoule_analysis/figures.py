from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import AnalysisConfig

COLOURS = {
    "Industry": "#0072B2",
    "ISO": "#E69F00",
    "Black and white": "#009E73",
}


def _style(config: AnalysisConfig) -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "figure.dpi": config.figure_dpi,
            "savefig.dpi": config.figure_dpi,
            "savefig.bbox": "tight",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def _save(fig: plt.Figure, output: Path, stem: str) -> list[Path]:
    paths = []
    for extension in ("png", "svg", "pdf"):
        path = output / f"{stem}.{extension}"
        fig.savefig(path)
        paths.append(path)
    plt.close(fig)
    return paths


def participant_paired_figure(
    participant: pd.DataFrame,
    summary: pd.DataFrame,
    output: Path,
    config: AnalysisConfig,
) -> list[Path]:
    _style(config)
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(config.figure_width, config.figure_height),
        constrained_layout=True,
    )
    metrics = (
        ("accuracy", "Proportion correct", (0, 1.02), "A"),
        ("median_correct_rt_ms", "Median correct response time (ms)", None, "B"),
    )
    x = np.arange(len(config.style_order))
    for axis, (metric, label, limits, panel) in zip(axes, metrics, strict=True):
        wide = participant.pivot(index="participant_id", columns="style", values=metric)
        for _, values in wide.reindex(columns=config.style_order).iterrows():
            axis.plot(x, values.to_numpy(float), color="#999999", alpha=0.35, linewidth=0.7)
        for position, style in enumerate(config.style_order):
            values = participant.loc[participant["style"].eq(style), metric].dropna()
            if not values.empty:
                jitter = np.linspace(-0.055, 0.055, len(values))
                axis.scatter(
                    position + jitter,
                    values,
                    s=11,
                    alpha=0.65,
                    color=COLOURS[style],
                    edgecolors="none",
                    zorder=3,
                )
            estimate = summary.loc[summary["style"].eq(style) & summary["metric"].eq(metric)]
            if not estimate.empty:
                row = estimate.iloc[0]
                axis.errorbar(
                    position,
                    row["estimate"],
                    yerr=[
                        [row["estimate"] - row["ci_low"]],
                        [row["ci_high"] - row["estimate"]],
                    ],
                    fmt="D",
                    color="#111111",
                    markerfacecolor=COLOURS[style],
                    markersize=5,
                    capsize=3,
                    linewidth=1.2,
                    zorder=5,
                )
        axis.set_xticks(x, config.style_order, rotation=18, ha="right")
        axis.set_ylabel(label)
        axis.set_ylim(limits)
        axis.grid(axis="y", color="#dddddd", linewidth=0.6)
        axis.set_title(f"{panel}   Participant-paired {label.lower()}", loc="left")
    fig.suptitle("Accuracy and response time by ampoule display style", fontsize=11)
    return _save(fig, output, "figure_1_paired_outcomes")


def training_figure(
    training: pd.DataFrame,
    output: Path,
    config: AnalysisConfig,
) -> list[Path]:
    _style(config)
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(config.figure_width, config.figure_height),
        constrained_layout=True,
    )
    metrics = (
        ("accuracy", "Proportion correct", (0, 1.02), "A"),
        ("median_correct_rt_ms", "Median correct response time (ms)", None, "B"),
    )
    for axis, (metric, label, limits, panel) in zip(axes, metrics, strict=True):
        for style in config.style_order:
            subset = training.loc[
                training["style"].eq(style) & training["metric"].eq(metric)
            ].sort_values("training_bin")
            if subset.empty:
                continue
            x = subset["progress_midpoint"].to_numpy(float)
            estimate = subset["estimate"].to_numpy(float)
            low = subset["ci_low"].to_numpy(float)
            high = subset["ci_high"].to_numpy(float)
            axis.plot(x, estimate, marker="o", markersize=3, color=COLOURS[style], label=style)
            axis.fill_between(x, low, high, color=COLOURS[style], alpha=0.14, linewidth=0)
        axis.set_xlabel("Progress through each display-style period")
        axis.set_ylabel(label)
        axis.set_ylim(limits)
        axis.grid(axis="y", color="#dddddd", linewidth=0.6)
        axis.set_title(f"{panel}   {label}", loc="left")
    axes[0].legend(title="Display style")
    fig.suptitle("Within-period practice and fatigue", fontsize=11)
    return _save(fig, output, "figure_2_training_effects")


def contrast_figure(
    contrasts: pd.DataFrame,
    output: Path,
    config: AnalysisConfig,
) -> list[Path]:
    _style(config)
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(config.figure_width, config.figure_height),
        constrained_layout=True,
    )
    panels = (
        ("primary_accuracy", "Accuracy risk difference", 0.0, "A"),
        ("primary_correct_rt", "Geometric-mean correct RT ratio", 1.0, "B"),
    )
    for axis, (model, label, reference, panel) in zip(axes, panels, strict=True):
        subset = contrasts.loc[contrasts.get("model", pd.Series(dtype=str)).eq(model)].copy()
        subset = subset.iloc[::-1].reset_index(drop=True)
        if subset.empty:
            axis.text(
                0.5, 0.5, "Model unavailable", ha="center", va="center", transform=axis.transAxes
            )
            axis.set_axis_off()
            continue
        y = np.arange(len(subset))
        estimate = subset["estimate"].to_numpy(float)
        low = subset["ci_low"].to_numpy(float)
        high = subset["ci_high"].to_numpy(float)
        axis.errorbar(
            estimate,
            y,
            xerr=np.vstack([estimate - low, high - estimate]),
            fmt="o",
            color="#333333",
            markerfacecolor="#0072B2",
            capsize=3,
        )
        axis.axvline(reference, color="#777777", linestyle="--", linewidth=0.9)
        axis.set_yticks(y, subset["contrast"])
        axis.set_xlabel(label + " (95% CI)")
        axis.grid(axis="x", color="#dddddd", linewidth=0.6)
        axis.set_title(f"{panel}   Adjusted pairwise contrasts", loc="left")
    fig.suptitle("GEE estimates by ampoule display style", fontsize=11)
    return _save(fig, output, "figure_3_adjusted_contrasts")


def outcome_composition_figure(
    trials: pd.DataFrame,
    output: Path,
    config: AnalysisConfig,
) -> list[Path]:
    _style(config)
    categorised = trials.copy()
    categorised["outcome"] = "Incorrect response"
    categorised.loc[categorised["correct_response"], "outcome"] = "Correct response"
    categorised.loc[categorised["timed_out"], "outcome"] = "Timed out"
    categorised.loc[categorised["result_missing"], "outcome"] = "Missing result"
    categorised.loc[categorised["integrity_excluded"], "outcome"] = "QC exclusion"
    order = [
        "Correct response",
        "Incorrect response",
        "Timed out",
        "Missing result",
        "QC exclusion",
    ]
    colours = ["#009E73", "#D55E00", "#CC79A7", "#999999", "#0072B2"]
    table = pd.crosstab(categorised["style"], categorised["outcome"], normalize="index")
    table = table.reindex(index=config.style_order, columns=order, fill_value=0)
    fig, axis = plt.subplots(
        figsize=(config.figure_width * 0.72, config.figure_height * 0.9),
        constrained_layout=True,
    )
    table.plot.bar(stacked=True, color=colours, ax=axis, width=0.7)
    axis.set_xlabel("")
    axis.set_ylabel("Proportion of generated trials")
    axis.set_ylim(0, 1)
    axis.set_xticklabels(config.style_order, rotation=18, ha="right")
    axis.legend(title="Trial outcome", bbox_to_anchor=(1.01, 1), loc="upper left")
    axis.set_title("Trial outcomes by ampoule display style", loc="left")
    axis.grid(axis="y", color="#dddddd", linewidth=0.6)
    return _save(fig, output, "figure_4_trial_outcomes")


def generate_figures(
    trials: pd.DataFrame,
    participant: pd.DataFrame,
    summary: pd.DataFrame,
    training: pd.DataFrame,
    contrasts: pd.DataFrame,
    output: str | Path,
    config: AnalysisConfig,
) -> list[Path]:
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    if not participant.empty:
        generated.extend(participant_paired_figure(participant, summary, output_path, config))
    if not training.empty:
        generated.extend(training_figure(training, output_path, config))
    generated.extend(contrast_figure(contrasts, output_path, config))
    if not trials.empty:
        generated.extend(outcome_composition_figure(trials, output_path, config))
    return generated
