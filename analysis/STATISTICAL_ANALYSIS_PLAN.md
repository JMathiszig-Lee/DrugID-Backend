# Statistical analysis plan

Version: 0.1 draft  
Status: implementation-ready template; investigator and statistician sign-off required before confirmatory data inspection

## 1. Objective and design

The objective is to estimate how three ampoule display styles—Industry, ISO and black-and-white—affect drug-identification speed and accuracy. This is a three-treatment, three-period randomized crossover. Every participant encounters all styles; the order is randomly assigned at registration from the six possible permutations. Multiple drug-identification trials occur within each period.

The participant is the unit of randomization and statistical cluster. Trial rows are not independent sample-size units. Target drugs recur across participants and styles and are adjusted as fixed effects in the default GEE; a cross-classified participant/drug mixed model should be considered if inference must generalize to a broader drug population.

Where configured, participants complete a mandatory timed tutorial before the first randomized
measured period. Tutorial trials and responses are operational familiarisation data, stored in
separate tables. They are excluded from every measured outcome, estimand, figure and model in this
plan; the required tutorial length is retained as protocol-configuration provenance.

## 2. Analysis populations

### Protocol-2 core population

Include submitted protocol-2 measured trials whose target, offered options, randomized period,
asset order, timing, correctness and selected option pass export integrity checks. Exclude all
tutorial trials/results. Incomplete measured runs remain in the available-case core analysis
because GEE can use unequal cluster sizes; their number and missing measured trials are reported.
Complete measured runs form a sensitivity population.

### Correct-RT population

For the primary RT model, further require a correct response observed before the deadline and a positive response time. Timeout deadlines are not observed RTs.

### Legacy pilot

Protocol 1 is analyzed only with explicit `--legacy-pilot`. It is reported separately and is excluded from confirmatory estimates because randomization order was inferred, option display order is unavailable, sequence values can reset, deadlines differ, and original timestamps/app versions are absent.

## 3. Outcomes and estimands

### Primary outcome: correct response time

Outcome: milliseconds from display to recorded selection among correct responses before the deadline. Transform using natural logarithm.

Primary estimand: participant-population average ratio of geometric mean correct RT for each display-style pair, adjusted for period, within-period progress, target drug and configuration. A ratio below 1 indicates faster identification for the numerator style.

Selection into the correct-response population can produce a speed–accuracy trade-off. Accuracy, timeout composition and censored time-to-response sensitivity must therefore accompany this result.

### Key secondary outcome: correct within deadline

Outcome equals 1 for a correct selected drug before the deadline and 0 for an incorrect selection or timeout. A generated trial with no submitted result is missing, not automatically incorrect.

Estimand: standardized absolute difference in probability correct for each style pair, with the same covariate distribution.

### Supporting outcomes

- Timeout proportion.
- Proportion with any response.
- Time to any response, with timeouts right-censored at `Trial.time_limit_ms`.
- Missing-result proportion and run completion.

## 4. Core models

Let style reference Industry. Both GEE models cluster on pseudonymous participant ID, use an exchangeable working correlation, robust sandwich covariance and these fixed effects:

```text
style + categorical period + within-period progress + categorical target drug
+ categorical protocol configuration (only if more than one exists)
```

RT model: Gaussian family with identity link on log RT.  
Accuracy model: binomial family with logit link.

The global null is equality of the two non-reference style coefficients (2-df Wald test). Only after reporting the global test are Industry–ISO, Industry–black-and-white and ISO–black-and-white contrasts reported. Pairwise p values use Holm adjustment separately for each outcome. Report 95% CIs, raw p values and adjusted p values; do not replace estimates with significance stars.

Adjusted accuracy contrasts are standardized risk differences obtained by predicting every observed covariate row under each style and averaging. RT contrasts are exponentiated differences on the log scale.

## 5. Training, fatigue, period and carryover

The core period coefficient estimates systematic changes between the first, second and third blocks independently of randomized style. Within-period progress is scaled against the number of trials planned for that period: 0 at the first planned position and 1 at the final planned position. An interrupted period therefore remains correctly located near its beginning rather than stretching its last observed trial to 1. This term estimates practice/fatigue within a block.

For tutorial-exposed cohorts, progress zero is the first **measured** trial after familiarisation;
the tutorial sequence is not prepended to global or within-period progress. These coefficients
therefore estimate residual training/fatigue during measured data collection, not learning during
the tutorial. The tutorial requirement is part of `configuration_signature`; if both tutorial and
no-tutorial protocol-2 runs contribute measured data, retain configuration adjustment and present
stratum-specific descriptive estimates rather than attributing cohort differences to the tutorial.

Two additional joint Wald tests are prespecified:

1. `style × within-period progress`: does the training/fatigue slope differ by display style?
2. `style × categorical period`: does the style effect vary depending on when it appears in the crossover, consistent with carryover, imbalance or temporal effect modification?

The six assigned order counts are reported. If allocation is materially imbalanced, sequence-specific descriptive estimates should be added and the cause investigated. Interaction estimates are interpreted with CIs; absence of statistical significance is not proof of identical learning curves.

## 6. Missing data and protocol deviations

- Export every generated measured trial, not only measured results; do not export tutorial rows.
- Keep `result_missing`, `timed_out`, `responded` and `incorrect` as distinct states.
- Do not impute a deadline as observed RT.
- Core GEE uses available eligible submitted outcomes.
- Report missing results by style, period, sequence and run-completion status.
- Repeat RT and accuracy among completed runs.
- Do not silently delete a participant because one period is incomplete.
- Review whether missingness is associated with assigned order/style. If substantial or differential, add inverse-probability weighting or a multiple-imputation strategy in a signed amendment before final analysis.

## 7. Sensitivity analyses

Prespecified automated analyses are:

1. log RT for all observed responses, regardless of correctness;
2. correct RT in completed runs;
3. correct RT after excluding responses below 200 ms as physiologically/operationally implausible;
4. correct RT with independence working correlation;
5. accuracy in completed runs;
6. accuracy with independence working correlation;
7. both core outcomes with Statsmodels' bias-reduced GEE sandwich covariance as a small-cluster sensitivity;
8. Cox proportional-hazards model of time to any response, timeout right-censored at the actual trial deadline, Efron ties and participant-clustered robust covariance.

The proportional-hazards assumption should be assessed before treating the Cox hazard ratio as a definitive summary. If visibly or statistically violated, report it as an omnibus time-to-response sensitivity and add a prespecified restricted-mean-time or accelerated-failure-time analysis.

If configuration signatures differ in measured-trial count, number of choices, deadline or
tutorial requirement, retain configuration adjustment and report stratum-specific descriptive
estimates. Do not pool protocol 1 and 2. Tutorial-versus-no-tutorial comparisons are not causal:
the tutorial was not separately randomized and grandfathered cohorts may differ historically.

## 8. Descriptive summaries and figures

Report aggregate participant speciality and experience, participant/run/trial flow, sequence balance, result completeness, accuracy, timeout rate and participant-level median/geometric-mean correct RT. Descriptive CIs use participant resampling so repeated trial rows are not mistaken for independent observations.

Figures:

1. paired participant accuracy and median correct RT by style, with group estimates and 95% CIs;
2. binned within-period accuracy and median RT trajectories by style;
3. adjusted GEE pairwise estimates with 95% CIs and null reference lines;
4. correct, incorrect, timeout, missing-result and integrity/QC-exclusion proportions.

Export PNG (300 DPI), SVG and PDF. Use the fixed colour-blind-accessible palette and retain the same style ordering in all outputs.

## 9. Statistical thresholds and reporting

Two-sided alpha is 0.05; CIs are 95%. Exact p values are exported. Manuscript text reports `p<0.001` below that threshold and three decimals otherwise. Effect estimates and CIs take priority over dichotomous labels.

The final protocol must decide whether RT alone is primary or whether RT and accuracy are co-primary. If co-primary, specify an across-outcome multiplicity procedure or require both outcomes to meet their criterion. The current Holm adjustment covers pairwise contrasts within an outcome only.

## 10. Power and sample size

The attached `GEE_simulation.ipynb` has no valid sample-size conclusion. Its group-label construction assigns different labels and outcome probabilities to misaligned rows, so all labelled groups have approximately the same event probability; its reported 2–10% values estimate type-I error. It also uses only 100 simulations, an `if/elif` counting error, no repeated-measures correlation and no global style test.

A replacement simulation must reproduce the deployed design and final estimator:

- independently randomize each participant across all six style orders, matching
  the deployed allocator, and retain the resulting finite-sample imbalance;
- simulate participant and drug heterogeneity, including centered participant-by-style and drug-by-style deviations, exchangeable/realistic within-person dependence, period and learning effects;
- simulate log RT, incorrect responses, deadline censoring, missing runs and dropout;
- fit the exact core GEE and test the global style hypothesis;
- use a fixed seed and target at least 5,000–10,000 successful GEE model fits per scenario and outcome;
- report convergence, type-I calibration, Monte Carlo 95% CIs and operational attrition diagnostics;
- select the minimum recruited participant count whose lower Monte Carlo CI meets the chosen power
  target and whose matched-null interval contains nominal alpha.

Pilot data may inform plausible nuisance distributions but should not fix an over-optimistic target effect. The scientifically meaningful minimum difference must be chosen independently of observed significance.

The early protocol-1 experimental data predated the mandatory tutorial. The current simulator
starts at the first measured period and does not simulate tutorial outcomes. Legacy-calibrated
learning parameters therefore describe a no-tutorial cohort and may not equal residual learning
after familiarisation. Treat those power estimates as conditional sensitivity scenarios and
recalibrate post-tutorial learning once sufficient current-protocol data exist.

An exploratory legacy-calibrated exercise is documented separately in [LEGACY_POWER_SIMULATION.md](LEGACY_POWER_SIMULATION.md). It uses early protocol-1 experimental data to inform plausible inputs and evaluates the observed style effects alongside coefficients shrunken to 50% and 25% of their legacy values. Its results must be labelled as legacy-based scenario analyses, kept separate from protocol 2, and must not be presented as a definitive recruitment guarantee. The exact source and configuration hashes, empirical-versus-assumed parameter classification, null calibration and Monte Carlo uncertainty are retained with that exercise.

The complete exploratory grid run on 3 August 2026 targeted 500 fitted models per main
scenario/outcome; a separate learning sensitivity targeted 300. These are full scenario grids but
not recruitment-grade Monte Carlo precision. Only 20 of 30 main matched-null 95% intervals
contained nominal alpha, with every departure in the liberal direction. The scenario-specific
eligible grid points are therefore descriptive planning sensitivities, not sample-size selections.
The focused sensitivity found the same smallest locally eligible evaluated N across no,
legacy-sized and 1.5-times legacy learning terms, but it does not remove the main null-calibration
concern.

The implemented replacement is `analysis/ampoule_analysis/power.py`, with the generic example in `analysis/config/power.toml` and the early-data scenarios in `analysis/config/power_legacy_pilot.toml`. It applies the trial deadline to latent response times, distinguishes incorrect observed responses from timeouts and missing results, permits non-start and mid-study attrition, and runs configured alternative effect scales plus one null-calibration scenario for every participant-count × trials-per-style cell. It requires exactly two estimable style coefficients with a full-rank joint restriction and retains numerical warnings and failure reasons. A scenario exceeding the configured fit-failure tolerance is reported as non-estimable; it is not converted to zero power and does not erase otherwise valid grid cells.

Power is exported both conditional on a successfully fitted model and as an operational rate that treats fit failures as non-rejections. A candidate-design flag requires both an operational lower Monte Carlo confidence limit at or above target and a matched no-style-effect interval compatible with the nominal alpha. Realized marginal accuracy, timeout rate and correct-response geometric-mean RT by style are retained so the simulated effect can be checked against the intended estimand rather than inferred from conditional input parameters. The legacy exploratory configuration uses the bias-reduced GEE covariance after a preliminary calibration diagnostic found the ordinary sandwich test tended to reject too often at the evaluated cluster counts; this does not silently redefine the confirmatory primary model.

The generic example remains intentionally labelled `illustrative_not_for_recruitment` and requires explicit acknowledgement at runtime. Its small default simulation count tests the pipeline only; it does not satisfy the target of 5,000–10,000 successful GEE model fits per scenario and outcome required for a locked recruitment run. Once target effects, deadline, attrition and nuisance distributions are agreed, lock the amended TOML and retain its effective configuration and source hashes with the output.

## 11. Reproducibility and amendments

The locked snapshot manifest, analysis TOML, output manifest, code revision and software versions define one analysis run. Snapshot and output directories cannot be overwritten. Model failures and warnings are exported instead of hidden. Any change after confirmatory data access should be dated, justified and retained as an SAP amendment.
