# Analysis snapshot data dictionary

The Django export is the canonical input. Values are formula-safe CSV text and direct database IDs are replaced with typed, keyed HMAC-SHA256 pseudonyms. Blank means unavailable/not applicable; it does not mean zero.

## `participants.csv`

| Field | Meaning |
|---|---|
| `participant_id` | Stable pseudonym under the supplied analysis key. |
| `speciality`, `speciality_label` | Registered clinical specialty code and label. Exploratory covariate only unless prespecified/powered. |
| `years_experience` | Registered whole years of experience. Exploratory covariate only. |

## `runs.csv`

| Field | Meaning |
|---|---|
| `run_id`, `participant_id` | Pseudonymous run and owning participant. |
| `protocol_version` | 1 legacy pilot; 2 current randomized protocol. Never pool versions. |
| `configuration_id`, `configuration_signature` | Hash-like label and readable run snapshot: `trials=<per-style>;choices=<n>;limit_ms=<n>`. Runs requiring practice append `;tutorial_trials=<n>`; absence of that token means no tutorial was required. |
| `run_status`, `run_complete` | Operational status and completed flag. |
| `assigned_style_order` | Three canonical style labels in randomized order, pipe-delimited. |
| `order_inferred` | True where historic order was reconstructed rather than prospectively stored. |
| `trials_per_group`, `choices_per_trial`, `time_limit_ms` | Configuration frozen at run creation. |
| `periods_present`, `generated_trials`, `results_present` | Observed measured-period counts; tutorial records are not included. |
| `completed_trials_counter`, `total_trials_planned` | Stored measured-trial counter and planned measured total, retained for QC. Tutorial progress is separate. |

## `periods.csv`

| Field | Meaning |
|---|---|
| `period_id`, `run_id`, `participant_id` | Pseudonymous period, run and participant keys. |
| `style` | `Industry`, `ISO` or `Black and white`. |
| `period` | One-based randomized crossover position. |
| `period_status` | Pending, active, completed or archived. |
| `planned_trials`, `generated_trials`, `results_present`, `missing_results` | Period flow counts. |
| `completed_trials_counter` | Operational counter retained for consistency checking. |

## `trials.csv`

Only randomized measured-period `Trial`/`TrialResult` records appear here. The separately stored
`TutorialTrial`/`TutorialTrialResult` practice records are intentionally absent from this table,
all derived tables, figures, and outcome models.

| Field | Meaning |
|---|---|
| `trial_id`, `period_id`, `run_id`, `participant_id` | Typed pseudonymous keys. |
| `style`, `period` | Display condition and one-based crossover period. |
| `trial_index` | One-based position within period in canonical exports. The analysis also tolerates zero-based external fixtures. |
| `global_trial_index` | One-based planned position across the run. |
| `target_drug`, `selected_drug` | Intended and selected drug name; selected is blank for timeout/missing. |
| `time_limit_ms` | Actual deadline for this trial. Use this—not a legacy run default—for censoring. |
| `result_present` | A result record was submitted. |
| `responded`, `response_event` | A valid response was recorded before timeout; event=1 for time-to-response analysis. |
| `timed_out` | Deadline reached without an observed selection. |
| `correct` | Server-stored correctness; blank when no result. |
| `duration_ms` | Observed RT for a response; actual deadline for a timeout; blank for a missing result. |
| `observed_rt_ms` | Observed response time only. Always blank for timeout/missing. |
| `primary_eligible` | Export-level eligibility for the correct-RT estimand, requiring a correct non-timeout outcome and all integrity checks. It is not the accuracy denominator. |
| `exclusion_reason` | Semicolon-delimited audit reasons. `timeout` and `incorrect` remain valid accuracy outcomes; integrity failures do not. |
| `choices_per_trial`, `offered_count` | Configured and actual number of displayed options. |
| `target_option_position`, `selected_option_position` | One-based display positions when recorded. |

The pipeline adds:

| Derived field | Meaning |
|---|---|
| `result_missing` | No submitted result exists. |
| `valid_observed_rt` | Positive observed response time on a response event. |
| `correct_response` | Submitted, correct, non-timeout result with valid observed RT. |
| `integrity_excluded` | An export exclusion other than valid outcome states. In explicit legacy mode, inferred trial order, preserved trial-vs-run deadline differences, and normalized timeout-storage flags are accepted; unassigned rows and genuinely invalid observed responses remain excluded. |
| `analysis_eligible` | Submitted protocol-2 outcome without an integrity exclusion; denominator source for accuracy/time-to-response. |
| `rt_primary_eligible` | `analysis_eligible` and `correct_response`. |
| `analysis_rt_ms`, `log_rt` | Correct observed RT and natural logarithm. |
| `log_response_rt` | Natural log of any valid observed response time. |
| `trial_number` | Normalized one-based within-period position. |
| `trial_order_inferred` | True when legacy within-period order was deterministically inferred from export row/record order because no canonical index exists. |
| `planned_trials`, `total_trials_planned` | Planned denominator used for period/run progress; generated counts are used only as an explicitly flagged compatibility fallback. |
| `period_progress_denominator_inferred`, `global_progress_denominator_inferred` | True only when a non-canonical snapshot omitted the corresponding planned denominator and the analysis had to infer it. |
| `within_period_progress` | Planned position scaled from 0 at the first trial to 1 at the final planned position. Partial periods are not stretched to 1. |
| `global_trial_progress` | Planned position scaled from 0 to 1 across the full planned run. |
| `global_order_inferred` | True when legacy across-run position had to be inferred. |
| `complete_run` | Trial belongs to a completed run. |
| `plausible_rt` | Observed RT is at least the configured 200-ms sensitivity threshold. |

## `trial_options.csv`

One row per offered asset. `display_position` is one-based when `display_position_known=1`; legacy M2M membership has no recoverable order. `drug`, `is_target` and `is_selected` support target/selection and confusion checks. `asset_id` is a typed pseudonym, not a database key.

## `quality_checks.json` and `manifest.json`

`quality_checks.json` separates protocol-2 errors from legacy warnings and records measured-study
flow totals. `manifest.json` documents schema/mode, migration leaf, configuration signatures,
pseudonym-key identifier, timeout semantics, exact CSV columns and SHA-256 file hashes. Its
`tutorial_provenance` object explicitly records that tutorial rows were excluded, gives aggregate
run counts by required tutorial length and tutorial completion state, and defines the optional
configuration-signature token. The same database state and pseudonym key produce byte-identical
snapshots.
