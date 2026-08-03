# Legacy-data-calibrated power simulation

Status: exploratory planning analysis based on early protocol-1 experimental data  
Not a confirmatory analysis, definitive recruitment calculation or guarantee of achieved power

## Purpose

This document records the simulation-based power analysis calibrated from the study's early
experimental data (the **legacy protocol-1 data**). Its purpose is to show how power may vary with
the number of recruited participants and the number of repeated trials per display style, while
using the same randomized crossover structure and global GEE tests planned for the main study.

The legacy-calibrated simulation is deliberately separate from both:

- the analysis of future protocol-2 study results; and
- a prospectively locked sample-size calculation based on an independently chosen scientifically
  meaningful effect.

It is scenario-based planning evidence. The early data can make nuisance assumptions more
realistic, but its estimated style effects are too uncertain to adopt uncritically.
It is also not a bootstrap or literal reproduction of the legacy experiment: the simulated
future protocol uses the deployed 3,000 ms deadline, whereas recoverable legacy rows used a
mixture of 3,000 and 5,000 ms limits. Realized timeout and accuracy rates must therefore be
interpreted as legacy-informed projections under the future deadline.

The early legacy experiment also predated the mandatory tutorial. The simulation starts at the
first measured period and does not generate or analyse tutorial outcomes. Its learning parameters
therefore represent the legacy no-tutorial setting, not a directly estimated tutorial benefit;
they may overstate or understate residual learning after current participants have practised.
This is an additional reason to treat the reported power values as conditional scenarios and to
recalibrate post-tutorial learning once sufficient current-protocol data are available.

## Legacy-data provenance

The calibration source is the preserved protocol-1 database exported with
`export_analysis_snapshot --legacy-pilot` and analyzed with the analysis pipeline's
`--legacy-pilot` mode. The source snapshot and the legacy analysis remain separate from all
protocol-2 data.

The calibration audit contained 12 registered participants, 1,710 generated trials and 1,642
submitted results. After legacy normalization, 1,640 submitted outcomes were assigned to an
analysis style; 70 generated rows were excluded from outcome analyses, principally because the
result was missing. These figures describe the early dataset, not the planned confirmatory sample.

The aggregate quantities available for calibration were:

| Legacy quantity | Industry | ISO | Black and white |
|---|---:|---:|---:|
| Participants contributing to the style | 12 | 11 | 11 |
| Valid submitted outcomes | 584 | 532 | 524 |
| Correct outcomes | 433 | 488 | 438 |
| Timeouts | 135 | 32 | 79 |
| Mean participant accuracy | 0.749 | 0.925 | 0.851 |
| Mean participant median correct RT (ms) | 2,042 | 1,243 | 2,157 |

The legacy adjusted GEE estimates used as calibration checks were an ISO-versus-Industry
correct-RT ratio of 0.700 and a black-and-white-versus-Industry ratio of 1.061. The corresponding
adjusted accuracy risk differences were 0.195 and 0.100. These are **checks on realized simulated
outcomes**, not necessarily direct simulator parameters: the simulator generates conditional
incorrect choices and latent response times before applying the deadline.

The completed exploratory runs have the following exact provenance:

| Item | Recorded value |
|---|---|
| Legacy snapshot manifest SHA-256 | `9a461694112804310d167df1401b68c89f5a8fc3101ededfb19fe5447b5230b4` |
| Legacy analysis manifest SHA-256 | `67359f313eb82e5c07b5c76ecad23a46ee45cfe7f5d9115df91285e5a4ed6d76` |
| Aggregate calibration artifact SHA-256 | `327eeff12d39421c31fdb2e87fdaf7f3cb0449db0463cdd346a39d850df4dcee` |
| Main source/effective configuration SHA-256 | `5a4d4a14329b2aeeba4a2499100d2f707e9d416de82c3a8ee7f4fe689232a9ad` / `6611fc35ae01a1760be8c227bafa584ad8295a9c673e15abc863f58c4b4b0379` |
| Main results/manifest SHA-256 | `a1dab0bc884ceed8ab41b6e309bb4aafa9aa66cfe5dbbee7ec014f6c37e8bdba` / `032ec203376da6210d20bb0b3090c1084cbd4dd061a92939fd24fda5ac1e8a0e` |
| Main validated report SHA-256 | `4a747fd88f83bef01490d450853e77d75204050b12e601f656c45e98c85b6bd7` |
| Training source/effective configuration SHA-256 | `e1489d3298ef42249baee332184bdb942cac4e4c59652842525f6ab6c8254a7c` / `1a66127420612e5727e313fa8af5b088f24304b939a71be98fcc278f6d0807b7` |
| Training results/manifest SHA-256 | `54e2d283c5702aef4b774a824968601be751689a324ae33e9b326f3d2d89f04b` / `08d0c43c600d96bf3881ed93fdf6a2eb4830b1e7119700cbd6d71e9adc7e0b5e` |
| Training validated report SHA-256 | `0d530e179710e0f425913cc1b05d2d247c3e128455f2400c511309e85fc95992` |
| Simulation source SHA-256 (both runs) | `a6e6761d2f87cf4c625a4e638cb12231d5df440b65c1d2ce5c60c1a4017f6c35` |
| Random seeds, main/training | `20260802` / `20260803` |
| Software versions | matplotlib 3.11.1; NumPy 2.5.1; pandas 3.0.5; SciPy 1.18.0; statsmodels 0.14.6 |

No direct identifiers, row-level legacy data or pseudonym keys belong in this document or in the
repository.

The aggregate calibration is reproducible after running the legacy analysis pipeline:

```bash
uv run python -m analysis.ampoule_analysis.legacy_power_calibration \
  --input /path/to/legacy-results/tables/derived_trials.csv \
  --output /new/path/legacy_protocol_1_power_calibration.json
```

The checked-in [aggregate calibration artifact](calibration/legacy_protocol_1_power_calibration.json)
contains its input and implementation hashes, model formulas, optimizer diagnostics, software
versions and rounded TOML alignment. It contains no row or participant identifiers.

## Empirical and assumed inputs

Each parameter must be labelled by its evidential source. “Legacy-calibrated” does not mean that
every simulator parameter was reliably estimated from 12 participants.

| Input | Treatment in the simulation | Source and interpretation |
|---|---|---|
| Style-specific incorrect choice | Estimated among observed responses, on the model/log-odds scale | Legacy-informed. Do not use `1 - accuracy`, because observed accuracy also includes timeouts. |
| Style-specific correct RT | Estimated on the log-ms scale | Legacy-informed. Use eligible trial-level correct RT; participant medians above are descriptive checks only. |
| Style contrasts | Applied on the accuracy model scale and log-RT-ratio scale | Legacy-informed, then reduced toward the null in shrinkage scenarios. |
| Participant heterogeneity | Correlated participant accuracy and RT effects | Partly legacy-informed but weakly identified; treat as an explicit assumption and examine sensitivity. |
| Drug heterogeneity | Accuracy and RT effects for target drugs | Weakly identified by the legacy data; assumed or regularized rather than presented as a precise estimate. |
| Period and within-period learning | Period and progress terms beginning at the first measured trial | Legacy-informed in a no-tutorial cohort; uncertainty, stronger training/fatigue scenarios and later post-tutorial recalibration should be considered. |
| Deadline | Applied to each latent response time | Use the intended deployed protocol value for the scenario, not an undocumented historical value. |
| Non-start, dropout and missing results | Simulated before and during the run | Planning assumptions informed by legacy completeness but chosen for the future deployment context. |
| Randomized style order | Independent draw from all six permutations | Fixed by the deployed design rather than estimated from the legacy order reconstruction. |
| Trials per style | Scenario grid value | A design choice. Total planned trials per participant equal three times this value. |

For transparency, the effective machine-readable configuration and manifest are authoritative.
This document summarizes them but must not silently override them.

The checked-in calibration is
[`config/power_legacy_pilot.toml`](config/power_legacy_pilot.toml). The legacy-informed values in
that file are:

| Simulator input | Industry/reference | ISO | Black and white | Calibration method |
|---|---:|---:|---:|---|
| Conditional incorrect-choice probability | 0.043 | 0.024 | 0.018 | Bayesian binomial mixed model of 1,394 valid observed responses |
| Latent pre-deadline RT ratio | 1.000 | 0.601 | 0.969 | Censored log-normal calibration |
| Latent Industry geometric-mean RT | 2,557 ms | — | — | Censored log-normal calibration |
| Participant/drug incorrect-choice log-odds SD | 0.98 / 0.72 | — | — | Exploratory mixed-model posterior estimates; only 35 observed incorrect choices |
| Participant/drug/residual log-RT SD | 0.17 / 0.16 / 0.44 | — | — | Legacy log-RT variance decomposition |
| Participant/drug × style incorrect-choice log-odds SD | 0.45 / 0.35 | — | — | Regularized planning values from crude legacy contrast diagnostics |
| Participant/drug × style log-RT SD | 0.10 / 0.08 | — | — | Regularized planning values from crude legacy contrast diagnostics |
| Later-period incorrect-choice log-odds change | −0.327 per period | — | — | Legacy conditional-error model |
| Within-period incorrect-choice log-odds change | −0.614 from start to end | — | — | Legacy conditional-error model |
| Later-period / within-period log-RT change | −0.035 / −0.107 | — | — | Legacy censored-RT model |

The drug-by-style values are explicitly classified as regularized assumptions in the calibration
artifact because finite-cell noise, participant mix and censoring cannot be separated reliably in
12 participants. The planned 3,000 ms deadline, 5% non-start rate, 10% mid-study dropout, 0.025% terminal
missing-result probability per generated trial and 20 target drugs are future-study assumptions.
The historical rows contained both 3,000 and 5,000 ms timing limits, all 12 registered people
started, and one person contributed only the first style; these few observations cannot identify
future operational attrition or missingness reliably.

## Effect-size scenarios

The simulation should not rely on the observed legacy contrast alone. The small pilot can
overestimate effects through sampling variation and selection of encouraging early results. Run
the following alternatives with the same nuisance assumptions and design grid:

1. **Observed legacy effect:** retain 100% of each fitted legacy style coefficient. This is an
   optimistic reference scenario, not the preferred recruitment basis.
2. **50% legacy effect:** multiply each non-reference style coefficient by 0.50, moving it halfway
   toward the null.
3. **25% legacy effect:** multiply each non-reference style coefficient by 0.25. This is the more
   conservative legacy-informed scenario.
4. **No style effect:** set all style coefficients to zero to estimate type-I error calibration.

Shrink correct-RT effects on the log-ratio scale and accuracy effects on the simulator's model
scale, not by multiplying marginal percentages. Report the realized marginal accuracy,
timeout rate and geometric-mean correct RT for every style so that each generated scenario can be
checked against its intended estimand.

## Simulation and analysis method

For every participant-count × trials-per-style × effect-size cell, the simulation should:

1. independently randomize each recruited participant to one of the six display-style orders;
2. generate the three crossover periods and the configured number of trials per style;
3. generate correlated participant and target-drug effects plus centered participant-by-style
   and drug-by-style deviations, period effects and within-period practice or fatigue;
4. generate incorrect choices and latent response times, then apply the trial deadline to create
   observed responses and timeouts;
5. generate non-start, mid-study dropout and terminal missing results;
6. fit a participant-clustered exchangeable GEE using the configured robust or bias-reduced
   sandwich covariance; and
7. test the 2-df global display-style hypothesis separately for correct RT and accuracy.

The legacy exploratory grid uses the bias-reduced covariance because a bounded preliminary null
diagnostic showed material liberal rejection with the ordinary sandwich estimator. This is an
explicit planning choice, not a post-hoc claim that the ordinary primary model is calibrated.
Every candidate-design flag additionally requires its matched no-style-effect Monte Carlo
interval to contain the nominal 0.05 alpha.

A later recruitment-grade calculation should target at least 5,000 successful GEE model fits per
scenario and outcome, including a matched set under the no-style-effect scenario. The completed runs below
use 500 and 300 targets to cover the full exploratory scenario grids with bounded computing time;
their wider Monte Carlo intervals are retained and they must not be relabelled as recruitment-grade.
Retain the fixed seed, configuration, source hashes, fit warnings and failure reasons. Power is the
proportion of global tests below the two-sided alpha threshold. The operational estimate counts a
failed model fit as a non-rejection; it is therefore preferred to an estimate conditioned on
successful fitting. Report exact 95% Monte Carlo intervals for both power and null rejection rates.

The candidate sample size for an outcome is the smallest **evaluated** recruited participant count
whose **lower Monte Carlo confidence limit** reaches the configured power target and whose matched
null interval contains alpha. It is not a
mathematical minimum if the first grid value already qualifies. If RT and accuracy are made
co-primary, a separate joint decision rule and across-outcome multiplicity strategy must be fixed;
two outcome-specific minima do not by themselves define one recruitment target.

## Generated outputs

The private result directory should retain:

- the effective configuration and `power_manifest.json`;
- a tidy results table containing every participant, repeat-length, effect and null-calibration
  scenario;
- operational and successful-fit-conditional power/type-I-error estimates with Monte Carlo CIs;
- model fit counts, warning/failure reasons and attrition diagnostics;
- realized accuracy, timeout and correct-RT summaries by style; and
- publication-quality power and type-I-calibration figures whose titles state that they are
  “Legacy early-data-calibrated exploratory” scenarios.

“Repeat length” must always be labelled **trials per style**. For example, a design with `R` trials
per style contains `3R` planned trials per complete participant.

## Completed exploratory simulations

> **EARLY LEGACY DATA — EXPLORATORY ONLY.** These completed grids are calibrated from the early
> protocol-1 experimental data. They are not independent confirmation, a locked sample-size
> calculation, a recruitment recommendation or a guarantee of achieved power. The prospective
> scenarios use a 3,000 ms deadline and assumed future attrition; they do not literally reproduce
> the legacy rows, which used mixed 3,000 and 5,000 ms deadlines.

The runs completed on 3 August 2026. Their aggregate-only outputs are retained in private, ignored
build directories:

- [validated main-grid report](build/legacy-power-exploratory-2026-08-02/power_report.md),
  [tidy main results](build/legacy-power-exploratory-2026-08-02/power_results.csv) and
  [main power/type-I figure](build/legacy-power-exploratory-2026-08-02/power_curve.png);
- [validated training-sensitivity report](build/legacy-power-training-sensitivity-2026-08-02/power_report.md),
  [tidy sensitivity results](build/legacy-power-training-sensitivity-2026-08-02/power_results.csv)
  and [training-sensitivity figure](build/legacy-power-training-sensitivity-2026-08-02/power_learning_sensitivity.png).

Do not pool the two runs' overlapping cells: they use independent seeds and different Monte Carlo
targets.

### Run identity and computation

| Quantity | Main participant × repeat grid | Training-effect sensitivity |
|---|---:|---:|
| Grid status | Completed with 1 non-estimable outcome row | Complete |
| Recruited N | 24, 30, 36, 48, 60 | 24, 30, 36, 48, 60 |
| Trials per style | 10, 25, 50 | 25 |
| Legacy style-effect scales | 100%, 50%, 25% | 25% |
| Legacy learning scales | 100% | 0%, 100%, 150% |
| Fitted-model target per scenario/outcome | 500 | 300 |
| Alternative/null result rows | 90 / 30 | 30 / 30 |
| Simulated study datasets | 30,110 | 9,001 |
| GEE models fitted/attempted | 59,985 / 60,110 | 18,000 / 18,001 |
| Model-fit failures | 125 | 1 |
| Seed | 20260802 | 20260803 |

Both runs used a two-sided alpha of 0.05, 80% target power, participant-clustered exchangeable GEE,
bias-reduced sandwich covariance and exact 95% binomial Monte Carlo intervals. Failed fits counted
as non-rejections in operational power.

### Main-grid power results

A row below is eligible only when it was estimable, its **lower** operational-power interval reached
80%, and its matched null interval contained 5%. Values are the smallest **evaluated** recruited N;
`24*` is the lower grid boundary, so smaller values were not tested.

| Legacy effect | Outcome | 10 trials/style | 25 trials/style | 50 trials/style |
|---|---|---:|---:|---:|
| 100% | Correct RT | 24* | 24* | 36 |
| 100% | Accuracy | 30 | 30 | 24* |
| 50% | Correct RT | 24* | 24* | 36 |
| 50% | Accuracy | 24* | 30 | 24* |
| 25% | Correct RT | None in grid | 48 | 36 |
| 25% | Accuracy | None in grid | 48 | 36 |

The 25%-legacy scenario is the more conservative legacy-informed sensitivity, although it has not
been selected as a definitive planning effect. Its operational point-power estimates were:

| Outcome and trials/style | N=24 | N=30 | N=36 | N=48 | N=60 |
|---|---:|---:|---:|---:|---:|
| Correct RT, 10 | 33.0% | 39.4% | 46.4% | 59.4% | 70.0% |
| Accuracy, 10 | 33.7% | 44.5% | 51.1% | 64.3% | 75.4% |
| Correct RT, 25 | 54.4% | 67.8% | 76.6% | 90.6% | 94.8% |
| Accuracy, 25 | 62.7% | 72.0% | 78.6% | 94.8% | 96.4% |
| Correct RT, 50 | 76.2% | 85.0% | 92.6% | 98.0% | 99.6% |
| Accuracy, 50 | 76.8% | 87.2% | 92.8% | 99.4% | 100.0% |

At 25 trials/style, N=48 was the first locally eligible point: correct-RT power was 90.6%
(95% MC CI 87.7%–93.0%; matched-null rejection 7.0%, 4.9%–9.6%) and accuracy power was
94.8% (92.5%–96.6%; matched null 6.6%, 4.6%–9.1%). At 50 trials/style, N=36 was the
first locally eligible point: correct-RT power was 92.6% (89.9%–94.7%; matched null 6.2%,
4.3%–8.7%) and accuracy power was 92.8% (90.2%–94.9%; matched null 6.8%, 4.8%–9.4%).
Neither outcome reached the power criterion at 10 trials/style anywhere from N=24 to N=60.

These local eligibility checks do **not** overcome the broader calibration problem below and must
not be interpreted as recruitment recommendations.

### Null calibration, fit diagnostics and realized outcomes

Only 20 of 30 main-grid null intervals contained nominal alpha: 8/15 for correct RT and 12/15 for
accuracy. The ten misses were all liberal. Point rejection rates ranged from 5.0% to 9.6% for RT
and 4.6% to 8.8% for accuracy; the longest-repeat RT cells were particularly inconsistent. This
systematic pattern is the principal blocker to using the reported minima for recruitment.

The main grid had 125 failed fits in 60,110 attempts: 64 rank-zero style restrictions and 61 GEE
non-convergences, all in accuracy models. Full-effect accuracy at N=24 and 10 trials/style exceeded
the configured 5% tolerance and was retained as non-estimable (485/526 fitted; 41 failures, 7.8%).
There were also 562 retained numerical overflow warnings. The training run had one rank-zero
accuracy failure in 18,001 attempts, no retained warnings and no non-estimable row.

Under the main 25%-effect scenario, realized marginal ranges were:

| Style | Accuracy | Timeout rate | Correct-RT geometric mean |
|---|---:|---:|---:|
| Industry | 64.6%–65.3% | 31.3%–32.0% | 1,799–1,806 ms |
| ISO | 73.2%–73.6% | 23.1%–23.5% | 1,684–1,692 ms |
| Black and white | 66.1%–66.5% | 30.7%–31.2% | 1,791–1,799 ms |

Across main cells, a mean 94.7%–95.3% of recruited participants started and 94.7%–95.3% provided
at least one result. The latter is not a completion rate and does not by itself justify a recruitment
inflation factor.

### Training-effect sensitivity

At 25 trials/style and the 25%-legacy style effect, the smallest locally eligible evaluated N was
48 for both outcomes under all three learning assumptions:

| Learning terms | Correct-RT power at N=48 (95% MC CI) | Accuracy power at N=48 (95% MC CI) |
|---|---:|---:|
| None (0%) | 85.0% (80.4%–88.8%) | 94.3% (91.1%–96.7%) |
| Legacy-sized (100%) | 86.3% (81.9%–90.0%) | 92.0% (88.3%–94.8%) |
| Stronger (150%) | 92.3% (88.7%–95.1%) | 91.3% (87.6%–94.3%) |

The null interval contained 5% in 29/30 training-sensitivity rows; the exception was the N=24,
150%-learning RT row (10.3%, 95% MC CI 7.1%–14.3%). Simulated practice materially changed
overall performance: across styles, accuracy rose and correct RT fell as learning increased.
Nevertheless, random sequence allocation plus period/progress adjustment left the N=48 grid
conclusion unchanged. This supports robustness to the tested practice-effect magnitudes, but the
300-fit Monte Carlo precision is exploratory and does not establish absence of carry-over or more
complex learning mechanisms.

No investigator/statistician planning scenario or single recruitment target has been selected.

## Publication-adaptable Methods wording

> An exploratory simulation-based power analysis was calibrated using early protocol-1 experimental
> data from 12 participants (the legacy data), separately from any future confirmatory dataset. The
> intended future three-period randomized crossover was represented using independent allocation
> among all six display-style sequences, participant and target-drug random effects including
> style-specific heterogeneity, period and within-period learning terms, a 3,000 ms deadline, and
> assumed non-start, dropout and missing results. The main grid evaluated 24–60 recruited
> participants, 10, 25 or 50 trials per style, and 100%, 50% or 25% of the legacy-calibrated style
> contrasts, targeting 500 successful GEE model fits per scenario and outcome with matched null runs. A
> separate 300-fit sensitivity used the 25% style effect and 25 trials per style with learning terms
> set to 0%, 100% or 150% of the legacy estimates. Each dataset was analyzed using a
> participant-clustered exchangeable GEE, bias-reduced sandwich covariance and a 2-df global style
> test at alpha 0.05. Operational power counted failed fits as non-rejections and used exact 95%
> binomial Monte Carlo intervals. A grid point was eligible only when the lower power interval
> reached the configured 80% target and its matched null interval contained alpha. These complete
> exploratory grids used fewer replicates than a recruitment-grade calculation.

## Publication-adaptable Results wording

> Under the configured 25%-legacy effect scenario, neither outcome met the power and matched-null
> criteria with 10 trials per style over the evaluated N=24–60 range. With 25 trials per style,
> N=48 was the first eligible evaluated point: correct-RT power was 90.6% (95% MC CI 87.7%–93.0%)
> and accuracy power was 94.8% (92.5%–96.6%). With 50 trials per style, N=36 was the first eligible
> evaluated point: corresponding powers were 92.6% (89.9%–94.7%) and 92.8% (90.2%–94.9%). In the
> focused 25-trial sensitivity, the first eligible evaluated N remained 48 for both outcomes with
> no, legacy-sized and 1.5-times legacy learning effects. However, only 20/30 main-grid null
> intervals contained nominal alpha and all departures were liberal. The results therefore remain
> early-legacy-data scenario evidence, not a definitive sample-size recommendation or guarantee of
> achieved power.

## Limitations and interpretation

- Only 12 people contributed legacy data, so participant-level variance, correlation, learning and
  attrition parameters are estimated imprecisely.
- Protocol-1 assignment order was reconstructed; option display order, original timestamps,
  deployed application version and some timing provenance cannot be recovered.
- Eleven rather than all 12 participants contributed observed outcomes to two styles.
- The legacy and future protocols may differ in deadline, number of trials, assets, hardware,
  participant population and operational missingness.
- Reusing an observed pilot effect can produce winner's-curse optimism; the shrunken scenarios are
  essential, and a scientifically meaningful effect should ultimately be selected independently.
- Monte Carlo precision describes simulation error conditional on the chosen inputs. It does not
  quantify all uncertainty in those inputs or validate the data-generating model.
- Adding repeated trials improves within-person precision but cannot substitute indefinitely for
  additional independent participant clusters in a GEE analysis.

This analysis should be updated or superseded by a prospectively frozen calculation before final
recruitment decisions, with investigator and statistician agreement on the primary outcome,
minimum important effect, target power, attrition allowance and multiplicity strategy.
