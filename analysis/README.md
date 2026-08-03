# Ampoule statistical analysis

This directory contains the reproducible analysis layer for the three-period Ampoule display-style study. It replaces the hard-coded summaries in `pilotanalysis.ipynb` with validated participant-level data, repeated-measures models, exact result tables and publication-quality figures.

The analysis is deliberately separated into two steps:

1. Django exports an immutable, direct-identifier-free research snapshot.
2. The statistical package validates that snapshot and creates all derived data, models, figures and paper-oriented text in a new output directory.

No real snapshot or generated output should be committed. `analysis/data/` and `analysis/build/` are ignored because even pseudonymised health-research data can remain identifiable.

## Quick start

Install the locked analysis environment:

```bash
uv sync --frozen --group dev --group analysis
```

Create a secret pseudonym key of at least 32 bytes and store it outside the repository. Use the same key for successive study snapshots when participants must be linked across snapshots. Losing or changing the key breaks that linkage; disclosing it weakens pseudonymisation.

Export protocol-2 data from the Django database:

```bash
ANALYSIS_PSEUDONYM_KEY='replace-with-a-secret-of-at-least-32-bytes' \
uv run python manage.py export_analysis_snapshot \
  --output analysis/data/protocol-2-snapshot \
  --strict
```

The destination must not already exist. The command exports every generated **measured** trial,
including missing results and timeouts, with HMAC-SHA256 pseudonyms and no email, account,
magic-link or session fields. Tutorial trials and responses are operational practice records in
separate database tables and are not exported or analysed as outcomes. The manifest records this
exclusion and aggregate run-level tutorial provenance. A nonzero tutorial length is also appended
to the protocol configuration signature, so tutorial and grandfathered/no-tutorial cohorts are
adjusted for or reported separately when both occur. `--strict` refuses a protocol-2 snapshot with
failed integrity checks.

Run the analysis:

```bash
MPLCONFIGDIR=/tmp/ampoule-matplotlib \
uv run python -m analysis.ampoule_analysis \
  --input analysis/data/protocol-2-snapshot \
  --output analysis/build/protocol-2-results \
  --strict
```

The analysis also refuses to overwrite an existing directory. This makes each result bundle traceable to one input manifest and one configuration file.
Snapshot and result directories are created with owner-only permissions (0700 directories and 0600 files).

The web image intentionally excludes scientific packages. For an isolated Docker analysis runtime, build the optional target and mount only the required snapshot/output directories:

```bash
docker build --target analysis --tag ampoule-analysis .
mkdir -p analysis/build
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD/analysis/data:/data:ro" \
  --volume "$PWD/analysis/build:/output" \
  ampoule-analysis \
  --input /data/protocol-2-snapshot \
  --output /output/protocol-2-results \
  --strict
```

Snapshot extraction itself remains a Django management command run against the application database; the analysis container needs no database credentials.

Legacy protocol-1 data require explicit acknowledgement:

```bash
ANALYSIS_PSEUDONYM_KEY='replace-with-a-secret-of-at-least-32-bytes' \
uv run python manage.py export_analysis_snapshot \
  --output analysis/data/legacy-pilot \
  --legacy-pilot

uv run python -m analysis.ampoule_analysis \
  --input analysis/data/legacy-pilot \
  --output analysis/build/legacy-pilot-results \
  --legacy-pilot
```

Protocol 1 is exploratory only and is never pooled with protocol 2. Its original assignment/order, option display order and timing provenance cannot be fully recovered.

## Outputs

Each result bundle contains:

```text
analysis_manifest.json          hashes, software versions and input provenance
analysis_config.toml            exact analysis settings used
input_snapshot_manifest.json    frozen export schema, counts and input hashes
input_quality_checks.json       frozen export integrity findings
paper_methods.md                manuscript-ready methods draft
paper_results.md                data-driven results draft
figure_captions.md              manuscript-ready figure legends
report.md / report.html         combined human-readable report
tables/
  derived_trials.csv            normalized analysis variables
  participant_flow.csv          registered, generated, submitted, observed and complete counts
  participant_characteristics.csv aggregate speciality and experience summary
  participant_style_summary.csv participant-paired descriptive values
  style_summary.csv             participant-bootstrap estimates and 95% CIs
  randomisation_order_balance.csv
  training_summary.csv
  model_coefficients.csv         coefficients, p values and confidence intervals
  global_tests.csv               global style/training/period Wald tests
  marginal_means.csv             adjusted style-specific estimates
  pairwise_contrasts.csv         effects, 95% CIs, raw and Holm-adjusted p values
  training_effects.csv           estimated start-to-end practice/fatigue effects
  sensitivity_analyses.csv
  model_status.csv               formulas, sample sizes, warnings and failures
figures/
  figure_1_paired_outcomes.*     accuracy and RT, linked within participant
  figure_2_training_effects.*    within-period practice/fatigue trajectories
  figure_3_adjusted_contrasts.*  model effects with 95% CIs
  figure_4_trial_outcomes.*      correct/incorrect/timeout/missing/QC composition
```

Every figure is written as 300-DPI PNG, editable SVG and journal-friendly PDF. The design keeps the original notebook's comparison of styles and participants while replacing unlabelled hard-coded bars and row-level standard deviations with paired participant data and confidence intervals. The inherited `penguin_means`, `Length (mm)` and `Pharma` example labels are gone; `Industry`, `ISO` and `Black and white` are canonical throughout.

## How to read the main estimates

- `primary_correct_rt` is a Gaussian GEE on log response time among correct, non-timeout responses. Pairwise effects are geometric-mean ratios. A ratio below 1 means the first named style was faster than the style after “vs”.
- `primary_accuracy` is a binomial-logit GEE on correct identification within the deadline. Pairwise results are standardized absolute risk differences. A positive value means the first named style was more accurate.
- `censored_time_to_response` is a Cox sensitivity analysis of any observed selection, with timeout right-censored at the actual trial deadline. A hazard ratio above 1 means the first named style produced faster responses.
- Each outcome first receives a global display-style test. The three follow-up pairwise p values are Holm adjusted within that outcome. Confidence intervals and effect estimates should be interpreted ahead of a binary “significant/not significant” label.

The GEE working correlation is exchangeable, with participant as the cluster and robust sandwich covariance. Independence working correlation and bias-reduced sandwich covariance are rerun as sensitivity analyses. This matches the role of GEE for clustered or repeated observations described in the [Statsmodels GEE documentation](https://www.statsmodels.org/stable/gee.html). The censoring status and robust group covariance follow the [Statsmodels PHReg documentation](https://www.statsmodels.org/stable/generated/statsmodels.formula.api.phreg.html) and [robust covariance documentation](https://www.statsmodels.org/stable/generated/statsmodels.duration.hazard_regression.PHReg.robust_covariance.html).

## Training, fatigue and randomised order

Randomizing the six possible display-style orders prevents a style from systematically occupying the same study period when allocation is balanced. It does not make learning disappear, so the pipeline:

- reports allocation counts for every observed sequence;
- adjusts both core models for study period;
- estimates progress from 0 to 1 within each style period;
- tests style-by-progress interaction, asking whether learning differs between styles;
- tests style-by-period interaction, asking whether the style effect changes across the crossover;
- plots binned participant-level accuracy and median RT across each period.

A common negative RT progress effect with no interaction means participants became faster but the relative style comparison was broadly stable. A style interaction suggests differential learning and should be reported, not “controlled away.” A period interaction can indicate carryover, imbalance or a time-varying style effect and warrants careful interpretation.

The first measured trial follows the tutorial where one was configured. Consequently, measured
progress estimates residual practice or fatigue after familiarisation; it does not estimate the
tutorial learning curve itself. Tutorial response times and correctness must not be joined into
`trials.csv` or used to increase the repeated-measure count.

## Important decisions before confirmatory recruitment

The default plan treats correct response time as primary and accuracy as key secondary because this is described as a reaction-time study. Before looking at confirmatory results, the investigator/statistician should freeze:

- the single primary estimand and clinically/scientifically meaningful target difference;
- whether multiplicity correction is also required across RT and accuracy, not only within pairwise contrasts;
- recruitment cutoff, eligibility rules and treatment of interrupted sessions;
- whether the tested ampoules are the full population of interest or a sample requiring a drug random effect;
- planned minimum participant count and a corrected simulation-based power analysis;
- consent version, withdrawal handling, device/input provenance and deployed stimulus checksum.

GEE sandwich standard errors can be unreliable with very few participant clusters. The legacy pilot has too few complete participants for confirmatory inference; use it to test the pipeline and inform plausible simulation parameters, then determine sample size at the participant—not trial-row—level.

## Replacement power simulation

`analysis/config/power.toml` contains an explicitly illustrative crossover simulation for both the global correct-RT and accuracy GEE tests. It independently randomizes each participant to one of the six orders, matching the deployed backend rather than assuming blocked balance. It simulates correlated participant accuracy/RT effects, participant-by-style and drug-by-style heterogeneity, period and learning effects, non-starters, mid-study dropout and terminal missing results. A latent response time is generated for correct and incorrect choices; the configured deadline then determines timeout, observed RT and eligibility for the correct-RT analysis. The covariance estimator (`robust` or `bias_reduced`), style-effect shrinkage and learning-effect scale are explicit configuration values.

Two uses of the simulator must remain distinct. The generic `power.toml` is a pipeline example with placeholder assumptions. The [legacy-data-calibrated simulation](LEGACY_POWER_SIMULATION.md) is an exploratory planning exercise based on early protocol-1 experimental data and includes observed-effect and shrunken-effect scenarios. Its aggregate inputs can be regenerated with `legacy_power_calibration.py`; the checked-in [calibration artifact](calibration/legacy_protocol_1_power_calibration.json) contains source/code hashes and no participant identifiers. Neither use is a prospectively locked recruitment calculation, and neither should be described as guaranteeing power for protocol 2.

The early legacy experiment predated the mandatory tutorial. The simulator starts at the first
measured period and does not simulate tutorial outcomes, so its learning inputs describe the
legacy no-tutorial setting rather than a directly estimated tutorial effect. Treat the completed
power values as conditional scenario results and recalibrate residual post-tutorial learning when
enough current-protocol data are available.

The completed 3 August 2026 exploratory exercise covers the full N × trials-per-style grid with
500 fitted-model targets per main scenario/outcome and a focused 300-fit learning sensitivity.
Its exact tables, hashes, caveats and publication-adaptable wording are in
[LEGACY_POWER_SIMULATION.md](LEGACY_POWER_SIMULATION.md). The private generated
[main report](build/legacy-power-exploratory-2026-08-02/power_report.md) and
[training report](build/legacy-power-training-sensitivity-2026-08-02/power_report.md) are retained
under the ignored `analysis/build/` directory. Only 20/30 main matched-null intervals contained
nominal alpha and all misses were liberal, so its scenario-specific eligible grid points are not
recruitment recommendations. A later locked calculation still requires agreed target effects,
estimator calibration and at least 5,000 fitted simulations per scenario/outcome.

The inherited 8.0%, 7.6% and 7.2% values are now labelled conditional incorrect-choice probabilities. Timeouts are additional failures after applying the deadline, so the generated marginal accuracy is not simply 92.0%, 92.4% and 92.8%. These values and all nuisance parameters remain transparent placeholders—not a recruitment recommendation.

After a statistician has replaced the target effects and nuisance assumptions, run:

```bash
MPLCONFIGDIR=/tmp/ampoule-matplotlib \
uv run python -m analysis.ampoule_analysis.power \
  --output analysis/build/power \
  --config analysis/config/power.toml \
  --acknowledge-assumptions
```

To reproduce the completed 500-fit exploratory early-data grid, use
`analysis/config/power_legacy_pilot.toml`. It evaluates the configured Cartesian
grid of recruited participants and trials per style at 100%, 50% and 25% of the
legacy style contrasts, with one matched no-style-effect calibration per design
cell. Independent cells can be run concurrently without changing their seeds:

```bash
MPLCONFIGDIR=/tmp/ampoule-matplotlib \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
uv run python -m analysis.ampoule_analysis.power \
  --output analysis/build/legacy-power \
  --config analysis/config/power_legacy_pilot.toml \
  --simulations 500 \
  --workers 2 \
  --acknowledge-assumptions
```

The practice-effect sensitivity uses
`analysis/config/power_legacy_training_sensitivity.toml`, which fixes 25 trials/style and the
25%-legacy style effect while comparing 0%, 100% and 150% of the legacy learning terms. Use a new
output directory and the same command structure. The completed exploratory runs used explicit
`--simulations 500` and `--simulations 300` overrides respectively; the checked-in configurations
retain 5,000 as the intended minimum for a future higher-precision run.

The small generic default of 50 successful GEE model fits per scenario and outcome is only a reasonably bounded pipeline diagnostic. It is far too imprecise for recruitment. After locking scientifically justified assumptions, pass `--simulations 5000` (or more) and benchmark the run environment. Each participant-count × trials-per-style cell is run under every configured alternative effect scale and once under a no-style-effect null scenario. `power_results.csv` reports power, type-I-error calibration, Monte Carlo 95% CIs, fit warnings/failure reasons, dropout diagnostics, and realized marginal accuracy, timeout and correct-RT summaries by style. Both successful-fit-conditional and conservative operational rejection rates are exported; the latter counts failed fits as non-rejections and supplies the lower CI used with matched-null calibration for minimum-N decisions. A scenario exceeding the fit-failure tolerance is retained as non-estimable in `power_results.csv` and `non_estimable_scenarios.csv`, while other grid cells continue. Unexpected execution errors still remove the incomplete output. `power_curve.png/.svg/.pdf`, the effective configuration and `power_manifest.json` are produced alongside it. Completed directories use mode `0700` and files `0600`.

After a run completes, validate its manifest and render the aggregate, paper-adaptable report with:

```bash
uv run python -m analysis.ampoule_analysis.power_report \
  --input analysis/build/legacy-power \
  --output analysis/build/legacy-power/power_report.md
```

See [STATISTICAL_ANALYSIS_PLAN.md](STATISTICAL_ANALYSIS_PLAN.md), [data_dictionary.md](data_dictionary.md), and [notebook_audit.md](notebook_audit.md). The generated reporting follows the principle in the [SAMPL biomedical reporting guidance](https://www.equator-network.org/reporting-guidelines/sampl/) that p values alone are insufficient: exact effects, uncertainty, numerators/denominators and analysis details are retained.

## Development checks

All tests use generated, non-identifying data:

```bash
SECRET_KEY='analysis-tests-only-secret-key-0123456789abcdefghijklmnopqrstuvwxyz' \
DEBUG=True \
MPLCONFIGDIR=/tmp/ampoule-matplotlib \
uv run pytest analysis/tests DrugID_API/test_analysis_export.py

uv run ruff check analysis DrugID_API/analysis_export.py \
  DrugID_API/management/commands/export_analysis_snapshot.py \
  DrugID_API/test_analysis_export.py
```
