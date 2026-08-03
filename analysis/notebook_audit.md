# Source notebook audit

The attached notebooks were used as study context, not copied as executable analysis. Neither notebook includes a statistical plan or a reproducible embedded dataset, so reusable transformations and models now live in `analysis/ampoule_analysis/`.

## `pilotanalysis.ipynb`

The notebook reads an old admin CSV with `id, time, selected, correct, sequence_id, group, user`. It calls `dropna()` without assigning the result, then drops selected drug, splits participants at the unexplained boundary `user < 8`, and manually pastes summary numbers into plots.

Useful design ideas retained:

- compare accuracy and time across all three styles;
- show participant-specific results as well as group summaries;
- show response time across trial sequence;
- retain the blue/orange/green visual distinction.

Publication-breaking issues corrected:

- row-level means/SDs are replaced by participant-clustered estimates and 95% CIs;
- deadlines/timeouts are not treated as observed RTs;
- participant IDs and styles are not pooled across sessions without run/period context;
- hard-coded bars are generated from a locked snapshot;
- raw sequence resets are replaced by canonical period/trial positions;
- numeric group/style and deadline cohorts are explicitly modeled;
- outputs include n, units, legends, accessible colors and vector formats.

Removed example remnants include four live variables called `penguin_means`, commented penguin template values, hidden `Length (mm)` axis labels, `Pharma`/`pharma` labels, and `% Correct` on a 0–1 scale.

The notebook's saved complete-case display has 1,333 rows while its RangeIndex reaches 1,568, consistent with 236 incomplete rows. Its correct-only subset has 1,302 observations. Those counts are historical context only: the source CSV is not embedded, and the current snapshot export is canonical.

## `GEE_simulation.ipynb`

The intended model is a binomial-logit GEE with participant clusters, independence working correlation and formula:

```text
outcome ~ categorical group + repetition
```

It assumes baseline event probability 0.08 and an “effect size” of 0.1, intended to produce probabilities 0.080, 0.076 and 0.072. It never defines whether the event is success or failure; 8% is more plausible as failure.

The saved power output is invalid because `group_id` is not tiled within participant. Participant labels and probability blocks are misaligned, making each labelled group average approximately 0.076. The fitted effect is therefore null and printed values near 0.05 are type-I error. In addition:

- one normal scalar multiplies the entire simulated dataset, creating no repeated-measures correlation;
- `if ... elif` prevents the second contrast being counted when the first is significant;
- separate coefficient p values replace the required global style test;
- only 100 simulations are run per saved scenario, with no seed or Monte Carlo CI;
- there is no randomized order, period, drug, training, censoring, missingness or dropout;
- the grid stops with a keyboard interrupt and identifies no sample size.

Consequently this notebook must not be cited as evidence of achieved power or a required participant count. The replacement requirements are recorded in the statistical analysis plan. The analysis engine itself fits the declared participant-clustered exchangeable GEE, performs global and adjusted pairwise tests, and repeats independence correlation as sensitivity.
