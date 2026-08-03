from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AnalysisConfig
from .models import ModelBundle
from .validate import Snapshot


def _p(value: object) -> str:
    try:
        number = float(value)
    except TypeError, ValueError:
        return "p not estimable"
    if not np.isfinite(number):
        return "p not estimable"
    return "p<0.001" if number < 0.001 else f"p={number:.3f}"


def _number(value: object, digits: int = 2) -> str:
    try:
        number = float(value)
    except TypeError, ValueError:
        return "not estimable"
    if not np.isfinite(number):
        return "not estimable"
    return f"{number:.{digits}f}"


def _global_sentence(bundle: ModelBundle, model: str, outcome: str) -> str:
    if bundle.global_tests.empty or "model" not in bundle.global_tests:
        return f"The global display-style effect on {outcome} was not estimable."
    row = bundle.global_tests.loc[
        bundle.global_tests["model"].eq(model)
        & bundle.global_tests["hypothesis"].eq("display style")
    ]
    if row.empty:
        return f"The global display-style effect on {outcome} was not estimable."
    result = row.iloc[0]
    return (
        f"The global display-style test for {outcome} gave "
        f"Wald χ²({int(result['degrees_of_freedom'])})={_number(result['statistic'])}, "
        f"{_p(result['p_value'])}."
    )


def _contrast_sentences(bundle: ModelBundle, model: str, confidence_percent: float) -> list[str]:
    subset = bundle.pairwise_contrasts.loc[
        bundle.pairwise_contrasts.get("model", pd.Series(dtype=str)).eq(model)
    ]
    sentences = []
    for _, row in subset.iterrows():
        sentences.append(
            f"{row['contrast']}: {row['effect_measure']}={_number(row['estimate'], 3)} "
            f"({confidence_percent:g}% CI {_number(row['ci_low'], 3)} to "
            f"{_number(row['ci_high'], 3)}; "
            f"Holm-adjusted {_p(row.get('p_value_holm'))})."
        )
    return sentences


def _training_sentence(
    bundle: ModelBundle,
    model: str,
    outcome: str,
    confidence_percent: float,
) -> str:
    if bundle.training_effects.empty or "model" not in bundle.training_effects:
        return f"The within-period training effect for {outcome} was not estimable."
    interaction_model = model.replace("primary_", "training_interaction_")
    style_rows = bundle.training_effects.loc[bundle.training_effects["model"].eq(interaction_model)]
    row = bundle.training_effects.loc[bundle.training_effects["model"].eq(model)]
    interaction = bundle.global_tests.loc[
        bundle.global_tests["model"].eq(interaction_model)
        & bundle.global_tests["hypothesis"].eq("style × within-period progress")
    ]
    period_model = model.replace("primary_", "period_interaction_")
    period_interaction = bundle.global_tests.loc[
        bundle.global_tests["model"].eq(period_model)
        & bundle.global_tests["hypothesis"].eq("style × study period")
    ]
    if row.empty and style_rows.empty:
        return f"The within-period training effect for {outcome} was not estimable."
    interaction_text = (
        f" The style-by-progress interaction had {_p(interaction.iloc[0]['p_value'])}."
        if not interaction.empty
        else " The style-by-progress interaction was not estimable."
    )
    period_text = (
        f" The style-by-period interaction had {_p(period_interaction.iloc[0]['p_value'])}."
        if not period_interaction.empty
        else " The style-by-period interaction was not estimable."
    )
    if not style_rows.empty:
        effects = "; ".join(
            f"{effect['style']}: {effect['effect_measure']}="
            f"{_number(effect['estimate'], 3)} ({confidence_percent:g}% CI "
            f"{_number(effect['ci_low'], 3)} to {_number(effect['ci_high'], 3)})"
            for _, effect in style_rows.iterrows()
        )
        change_text = f"Adjusted start-to-end changes in {outcome} were {effects}."
    else:
        result = row.iloc[0]
        change_text = (
            f"From the start to the end of a display-style period, adjusted {outcome} "
            f"changed by {result['effect_measure']}={_number(result['estimate'], 3)} "
            f"({confidence_percent:g}% CI {_number(result['ci_low'], 3)} to "
            f"{_number(result['ci_high'], 3)}; {_p(result['p_value'])})."
        )
    return f"{change_text}{interaction_text}{period_text}"


def _status_warnings(bundle: ModelBundle) -> list[str]:
    warnings: list[str] = []
    for _, row in bundle.status.iterrows():
        if row["status"] != "fitted" or str(row.get("warning", "")).strip():
            warnings.append(
                f"- `{row['model']}`: {row['status']}. {str(row.get('warning', '')).strip()}"
            )
    return warnings


def build_methods(config: AnalysisConfig, *, legacy_pilot: bool) -> str:
    if legacy_pilot:
        qualification = (
            "This run is a protocol-1 legacy pilot analysis and is exploratory only. "
            "Display sequence was reconstructed from historic session records; prospective "
            "randomisation could not be verified. "
        )
    else:
        qualification = (
            "The confirmatory population comprises eligible protocol-2 trials. "
            "Display order was randomised at participant registration. Where configured, "
            "a mandatory timed tutorial preceded the measured periods; tutorial trials and "
            "responses were operational practice records and were not exported or analysed "
            "as study outcomes. "
        )
    configured_covariates = []
    if config.adjust_for_period:
        configured_covariates.append("study period")
    if config.adjust_for_within_period_progress:
        configured_covariates.append("continuous progress through the current period")
    covariate_text = ", ".join(configured_covariates) or "no additional core covariates"
    confidence_percent = config.confidence_level * 100
    period_description = "reconstructed study period" if legacy_pilot else "randomised study period"
    return f"""# Statistical methods draft

{qualification}The study compared Industry, ISO and black-and-white ampoule displays within participants across up to three study periods.

The primary outcome was response time in milliseconds among correct responses observed before the trial deadline. Response time was log transformed because reaction-time distributions are right skewed. The key secondary outcome was correct identification within the deadline; timeouts were classified as incorrect for this endpoint. Generated trials without a submitted result were retained in the participant-flow and missingness summaries but were not treated as incorrect responses.

Population-averaged effects were estimated with generalised estimating equations (GEE), clustering repeated trials by participant and using a {config.covariance} working correlation with robust sandwich standard errors. The response-time model used a Gaussian family on log response time; the accuracy model used a binomial family with logit link. Core models were configured to include display style and {covariate_text}. Categorical target drug and protocol configuration were included only when present with more than one level and estimable from the available data. The {config.style_reference} style was the reference category. A two-degree-of-freedom Wald test assessed the global display-style effect before pairwise comparisons. Pairwise p values were adjusted within each outcome using Holm's method, and {confidence_percent:.0f}% confidence intervals were reported. Response-time effects are geometric-mean ratios; accuracy effects are standardised absolute risk differences.

Training, fatigue and time-varying style effects were assessed by adjustment for {period_description}, the continuous within-period progress term, a style-by-progress interaction testing whether learning differed by display style, and a style-by-period interaction testing whether style effects varied with period. A style-by-period interaction is not, by itself, a direct estimate of carryover from the preceding style. Graphical summaries used participant-level estimates and participant-resampling bootstrap confidence intervals ({config.bootstrap_iterations:,} samples; seed {config.bootstrap_seed}).

Sensitivity analyses included all observed responses irrespective of correctness, complete runs only, exclusion of responses shorter than {config.minimum_plausible_rt_ms} ms, and an independence working correlation. Accuracy was also repeated for complete runs and with independence working correlation. Both core outcomes were repeated using a bias-reduced GEE sandwich covariance as a small-cluster sensitivity; this does not make inference reliable with extremely few participant clusters. A Cox proportional-hazards sensitivity model of time to any response treated timeouts as right-censored at the trial deadline and used participant-clustered robust standard errors; a hazard ratio above one represents a faster response. Its proportional-hazards assumption requires diagnostic review before definitive interpretation. Timeout rates and the full composition of generated-trial outcomes were reported alongside reaction time to assess speed–accuracy trade-offs. No missing outcome was imputed.

These methods are an analysis-plan template. The final manuscript and registration should identify one primary outcome, state any multiplicity strategy across outcomes, define the recruitment cutoff, and document exclusions before the confirmatory dataset is inspected.
"""


def build_results(
    snapshot: Snapshot,
    trials: pd.DataFrame,
    flow: pd.DataFrame,
    bundle: ModelBundle,
    style_summary: pd.DataFrame,
    order_balance: pd.DataFrame,
    config: AnalysisConfig,
    *,
    legacy_pilot: bool,
) -> str:
    def flow_row(stage: str) -> pd.Series:
        matching = flow.loc[flow["stage"].eq(stage)]
        if matching.empty:
            return pd.Series({"participants": 0, "runs": 0, "trials": 0})
        return matching.iloc[0]

    registered = flow_row("registered")
    created = flow_row("study run created")
    generated = flow_row("trial generated")
    submitted = flow.loc[flow["stage"].eq("result submitted")].iloc[0]
    correct = flow.loc[flow["stage"].eq("correct response")].iloc[0]
    completed = flow_row("completed study run")
    banner = (
        "> **Exploratory legacy pilot:** protocol-1 order, timing and stimulus-order provenance are incomplete. These estimates must not be pooled with protocol 2 or presented as confirmatory.\n\n"
        if legacy_pilot
        else ""
    )
    primary_status = bundle.status.loc[
        bundle.status["model"].isin({"primary_accuracy", "primary_correct_rt"})
    ]
    primary_clusters = pd.to_numeric(
        primary_status.get("participants", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    small_cluster_warning = ""
    if not primary_clusters.empty and primary_clusters.min() < 30:
        cluster_count = int(primary_clusters.min())
        small_cluster_warning = (
            f"> **Small-cluster warning:** at least one primary GEE used only "
            f"{cluster_count} participant clusters. Robust sandwich confidence intervals "
            "and p values can be unreliable below 30 clusters and must be treated as "
            "exploratory. Bias-reduced covariance is a sensitivity analysis, not a cure "
            "for an extremely small participant sample.\n"
        )

    submitted_denominator = int(generated["trials"])
    submitted_percent = (
        100 * int(submitted["trials"]) / submitted_denominator if submitted_denominator else np.nan
    )
    correct_denominator = int(submitted["trials"])
    correct_percent = (
        100 * int(correct["trials"]) / correct_denominator if correct_denominator else np.nan
    )
    speciality_column = (
        "speciality_label" if "speciality_label" in snapshot.participants else "speciality"
    )
    speciality_counts = (
        snapshot.participants[speciality_column]
        .astype("string")
        .fillna("Not recorded")
        .value_counts()
        .sort_index()
    )
    speciality_text = "; ".join(
        f"{level}, n={int(count)}" for level, count in speciality_counts.items()
    )
    experience = pd.to_numeric(snapshot.participants["years_experience"], errors="coerce").dropna()
    experience_text = (
        f"median clinical experience was {_number(experience.median(), 1)} years "
        f"(IQR {_number(experience.quantile(0.25), 1)} to "
        f"{_number(experience.quantile(0.75), 1)}; n={len(experience)})"
        if len(experience)
        else "clinical experience was not recorded"
    )
    confidence_percent = config.confidence_level * 100
    completion_text = (
        f"{int(completed['participants'])} participants completed "
        f"{int(completed['runs'])} study runs."
        if int(completed["runs"])
        else "No study runs were marked completed in the snapshot."
    )
    tutorial_note = ""
    tutorial_provenance = snapshot.manifest.get("tutorial_provenance")
    if isinstance(tutorial_provenance, dict):
        required_counts = tutorial_provenance.get("runs_by_required_trial_count", {})
        completion_counts = tutorial_provenance.get("tutorial_completion_counts", {})
        required_text = (
            "; ".join(
                f"{required} required trials (n={int(count)})"
                for required, count in sorted(
                    required_counts.items(), key=lambda item: int(item[0])
                )
            )
            if isinstance(required_counts, dict)
            else ""
        )
        completion_text_parts = (
            "; ".join(
                f"{status.replace('_', ' ')} (n={int(count)})"
                for status, count in sorted(completion_counts.items())
            )
            if isinstance(completion_counts, dict)
            else ""
        )
        tutorial_note = (
            "Tutorial trial and response records were excluded from this measured-study "
            "snapshot and all outcome analyses."
            + (f" Run-level tutorial requirements were {required_text}." if required_text else "")
            + (
                f" Tutorial completion provenance was {completion_text_parts}."
                if completion_text_parts
                else ""
            )
        )
    lines = [
        "# Statistical results draft",
        "",
        banner.rstrip(),
        small_cluster_warning.rstrip(),
        "",
        (
            f"The snapshot contained {int(registered['participants'])} registered participants "
            f"and {int(created['runs'])} study runs. {int(generated['participants'])} participants "
            f"generated {int(generated['trials'])} trials. Results were submitted for "
            f"{int(submitted['trials'])} trials ({_number(submitted_percent, 1)}% of generated "
            f"trials); {int(correct['trials'])} were correct responses with an observed response "
            f"time ({_number(correct_percent, 1)}% of submitted results). "
            f"{completion_text}"
        ),
        (
            f"Participant specialities were {speciality_text or 'not recorded'}; "
            f"{experience_text}. Full aggregate characteristics are provided in "
            "`tables/participant_characteristics.csv`."
        ),
        "",
    ]
    if tutorial_note:
        lines.extend([tutorial_note, ""])
    lines.extend(
        [
            "## Descriptive outcomes by display style",
            "",
        ]
    )

    eligible_submitted = trials.loc[trials["result_present"] & ~trials["integrity_excluded"]]
    for style in style_summary["style"].drop_duplicates() if not style_summary.empty else ():
        style_trials = trials.loc[trials["style"].astype(str).eq(style)]
        style_results = eligible_submitted.loc[eligible_submitted["style"].astype(str).eq(style)]

        def metric_row(metric: str) -> pd.Series:
            matching = style_summary.loc[
                style_summary["style"].eq(style) & style_summary["metric"].eq(metric)
            ]
            return matching.iloc[0] if not matching.empty else pd.Series(dtype=float)

        accuracy = metric_row("accuracy")
        timeout = metric_row("timeout_rate")
        median_rt = metric_row("median_correct_rt_ms")
        correct_count = int(style_results["correct"].sum())
        timeout_count = int(style_results["timed_out"].sum())
        lines.append(
            f"- **{style}:** {len(style_results)} valid submitted results from "
            f"{style_results['participant_id'].nunique()} participants across "
            f"{len(style_trials)} generated trials; {correct_count} correct and "
            f"{timeout_count} timed out. Mean participant-level proportion correct "
            f"{_number(accuracy.get('estimate'), 3)} ({confidence_percent:g}% bootstrap CI "
            f"{_number(accuracy.get('ci_low'), 3)} to {_number(accuracy.get('ci_high'), 3)}); "
            f"mean participant-level timeout proportion {_number(timeout.get('estimate'), 3)} "
            f"({confidence_percent:g}% bootstrap CI {_number(timeout.get('ci_low'), 3)} to "
            f"{_number(timeout.get('ci_high'), 3)}); mean participant median correct RT "
            f"{_number(median_rt.get('estimate'), 0)} ms ({confidence_percent:g}% bootstrap CI "
            f"{_number(median_rt.get('ci_low'), 0)} to {_number(median_rt.get('ci_high'), 0)} ms)."
        )

    qc_exclusions = int(trials["integrity_excluded"].sum())
    missing_results = int(trials["result_missing"].sum())
    configurations = trials["configuration_signature"].astype(str).value_counts()
    deadline_counts = pd.to_numeric(trials["time_limit_ms"], errors="coerce").value_counts()
    lines.extend(
        [
            "",
            (
                f"There were {missing_results} generated trials without a submitted result and "
                f"{qc_exclusions} trials with an integrity exclusion. Integrity-excluded trials "
                "were omitted from descriptive estimates and models and are shown separately in "
                "the trial-outcome figure."
            ),
            (
                "Observed protocol configuration counts were: "
                + "; ".join(
                    f"{signature} (n={count})" for signature, count in configurations.items()
                )
                + "."
            ),
            (
                "Actual trial deadlines were: "
                + "; ".join(
                    f"{deadline:g} ms (n={int(count)})"
                    for deadline, count in deadline_counts.sort_index().items()
                )
                + "."
            ),
            "",
            "## Randomisation order and participant flow",
            "",
        ]
    )
    if order_balance.empty:
        lines.append("Assigned display-style order was unavailable.")
    else:
        for _, row in order_balance.iterrows():
            source = (
                "inferred historic order" if bool(row["order_inferred"]) else "recorded assignment"
            )
            completeness = "complete" if bool(row["is_complete_assignment"]) else "incomplete"
            lines.append(
                f"- {row['sequence']}: {int(row['participants'])} participants / "
                f"{int(row['runs'])} runs ({source}; {completeness})."
            )
    lines.extend(
        [
            "",
            (
                "Participant flow is retained in `tables/participant_flow.csv`, including "
                "registered participants and assigned runs that never generated a trial."
            ),
            "",
            "## Adjusted primary and secondary outcomes",
            "",
            _global_sentence(bundle, "primary_correct_rt", "correct response time"),
            *_contrast_sentences(bundle, "primary_correct_rt", confidence_percent),
            "",
            _global_sentence(bundle, "primary_accuracy", "correct identification"),
            *_contrast_sentences(bundle, "primary_accuracy", confidence_percent),
            "",
            "## Training, fatigue and order",
            "",
            _training_sentence(
                bundle,
                "primary_correct_rt",
                "geometric-mean response time",
                confidence_percent,
            ),
            _training_sentence(
                bundle,
                "primary_accuracy",
                "probability of a correct response",
                confidence_percent,
            ),
            (
                "Study-period coefficients are available in `tables/model_coefficients.csv`. "
                + (
                    "Because legacy order was inferred rather than prospectively randomized, period "
                    "adjustment cannot recover the protection of a randomized crossover."
                    if legacy_pilot
                    else "Randomized order protects the style comparison from systematic period bias in expectation; observed allocation counts are reported above."
                )
            ),
            "",
            "## Sensitivity analyses",
            "",
        ]
    )
    if bundle.sensitivity.empty:
        lines.append("Sensitivity models were not estimable.")
    else:
        for _, row in bundle.sensitivity.iterrows():
            warning_text = str(row.get("warning", "")).strip()
            warning_suffix = (
                f" Warning: {warning_text}" if warning_text and warning_text != "nan" else ""
            )
            lines.append(
                f"- {row['model']}: global style {_p(row['p_value'])} "
                f"({int(row['participants'])} participants; {int(row['observations'])} observations)."
                f"{warning_suffix}"
            )
            lines.extend(
                f"  - {sentence}"
                for sentence in _contrast_sentences(bundle, row["model"], confidence_percent)
            )
        if "censored_time_to_response" in set(bundle.sensitivity["model"]):
            lines.append(
                "- The Cox time-to-response estimates remain a sensitivity analysis pending "
                "diagnostic review of the proportional-hazards assumption."
            )
    warnings = _status_warnings(bundle)
    if warnings:
        lines.extend(["", "## Model diagnostics", "", *warnings])
    lines.extend(
        [
            "",
            "## Figures and supporting tables",
            "",
            "- Figure 1 shows participant-paired accuracy and median correct response time.",
            "- Figure 2 shows within-period training/fatigue trajectories.",
            "- Figure 3 shows adjusted pairwise GEE contrasts with 95% confidence intervals.",
            "- Figure 4 separates correct, incorrect, timed-out, missing and QC-excluded trials.",
            "- Exact estimates, unadjusted and Holm-adjusted p values, confidence intervals, model formulas and fit warnings are exported as CSV files.",
            "",
            "This text is generated directly from the locked snapshot and should be checked by the study statistician before use in a manuscript.",
        ]
    )
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def write_reports(
    output: str | Path,
    snapshot: Snapshot,
    trials: pd.DataFrame,
    flow: pd.DataFrame,
    bundle: ModelBundle,
    style_summary: pd.DataFrame,
    order_balance: pd.DataFrame,
    config: AnalysisConfig,
    *,
    legacy_pilot: bool,
) -> list[Path]:
    output_path = Path(output)
    methods = build_methods(config, legacy_pilot=legacy_pilot)
    results = build_results(
        snapshot,
        trials,
        flow,
        bundle,
        style_summary,
        order_balance,
        config,
        legacy_pilot=legacy_pilot,
    )
    methods_path = output_path / "paper_methods.md"
    results_path = output_path / "paper_results.md"
    report_path = output_path / "report.md"
    methods_path.write_text(methods, encoding="utf-8")
    results_path.write_text(results, encoding="utf-8")
    report = (
        f"# {config.analysis_name}\n\n"
        f"Generated {datetime.now(timezone.utc).isoformat()} from an immutable study snapshot.\n\n"
        f"{methods}\n{results}"
    )
    report_path.write_text(report, encoding="utf-8")
    captions_path = output_path / "figure_captions.md"
    descriptive_participants = int(
        trials.loc[
            trials["result_present"] & ~trials["integrity_excluded"],
            "participant_id",
        ].nunique()
    )
    generated_trials = int(len(trials))
    confidence_percent = config.confidence_level * 100
    captions_path.write_text(
        f"""# Figure legends

**Figure 1. Participant-paired accuracy and response time by ampoule display style.** Each coloured point is one participant's proportion correct (A) or median response time among correct responses observed before the deadline (B); grey lines connect observations from the same participant. Diamonds show the mean participant-level estimate and bars show participant-resampling {confidence_percent:g}% confidence intervals. Up to {descriptive_participants} participants contributed; exact style-specific denominators are reported in the accompanying table. Lower response time indicates faster identification.

**Figure 2. Within-period practice and fatigue.** Trial position was normalized against the number of trials planned for each display-style period and divided into equal-width bins. Lines show the mean participant-level proportion correct (A) and mean participant-level median correct response time (B); shaded regions are participant-resampling {confidence_percent:g}% confidence intervals. Bin-specific participant counts are reported in the accompanying table. These unadjusted trajectories complement the adjusted continuous progress and style-by-progress terms in the GEE models.

**Figure 3. Adjusted display-style contrasts from generalized estimating equations.** Points and bars show adjusted pairwise estimates and {confidence_percent:g}% confidence intervals. Accuracy is expressed as an absolute risk difference (A), for which zero indicates no difference. Correct response time is expressed as a geometric-mean ratio (B), for which one indicates no difference; ratios below one indicate a faster numerator style. Exact and Holm-adjusted p values are reported in the accompanying table.

**Figure 4. Composition of generated trial outcomes.** Bars show the proportion of all {generated_trials} generated trials classified as correct observed response, incorrect observed response, timeout at the trial-specific deadline, missing result, or integrity/QC exclusion. Missing and excluded results are displayed rather than classified as incorrect.
""",
        encoding="utf-8",
    )
    html_path = output_path / "report.html"
    html_path.write_text(
        "<!doctype html><meta charset='utf-8'><title>Ampoule analysis</title>"
        "<style>body{max-width:900px;margin:3rem auto;font:16px/1.55 system-ui;color:#222}"
        "pre{white-space:pre-wrap;font:inherit}code{background:#f2f2f2;padding:.1rem .25rem}</style>"
        f"<pre>{html.escape(report)}</pre>",
        encoding="utf-8",
    )
    return [methods_path, results_path, captions_path, report_path, html_path]
