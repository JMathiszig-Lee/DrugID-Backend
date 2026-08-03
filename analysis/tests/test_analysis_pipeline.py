from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from analysis.ampoule_analysis.config import load_config
from analysis.ampoule_analysis.derive import derive_trials, participant_flow
from analysis.ampoule_analysis.pipeline import run_pipeline
from analysis.ampoule_analysis.report import build_methods
from analysis.ampoule_analysis.summaries import (
    order_balance,
    participant_style_summary,
    training_summary,
)
from analysis.ampoule_analysis.validate import SnapshotValidationError, load_snapshot


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _refresh_manifest_files(snapshot: Path, *filenames: str) -> None:
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename in filenames:
        manifest["files"][filename]["sha256"] = _sha256(snapshot / filename)
        if filename.endswith(".csv"):
            manifest["files"][filename]["rows"] = len(pd.read_csv(snapshot / filename))
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _convert_snapshot_to_legacy(snapshot: Path) -> None:
    for filename in ("runs.csv", "periods.csv", "trials.csv"):
        table = pd.read_csv(snapshot / filename)
        table["protocol_version"] = 1
        table.to_csv(snapshot / filename, index=False)
    quality_path = snapshot / "quality_checks.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality.update({"mode": "legacy_pilot", "protocol_version": 1})
    quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"mode": "legacy_pilot", "protocol_version": 1})
    for filename in ("runs.csv", "periods.csv", "trials.csv", "quality_checks.json"):
        manifest["files"][filename]["sha256"] = _sha256(snapshot / filename)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_timeout_is_censored_not_observed(synthetic_snapshot: Path) -> None:
    snapshot = load_snapshot(synthetic_snapshot)
    trials = derive_trials(snapshot, load_config())
    timeouts = trials.loc[trials["timed_out"]]

    assert not timeouts.empty
    assert timeouts["observed_rt_ms"].isna().all()
    assert (timeouts["duration_ms"] == timeouts["time_limit_ms"]).all()
    assert (~timeouts["response_event"]).all()
    assert (~timeouts["correct_response"]).all()


def test_progress_uses_planned_denominators_for_partial_periods(
    synthetic_snapshot: Path,
) -> None:
    snapshot = load_snapshot(synthetic_snapshot)
    period_id = snapshot.periods.iloc[0]["period_id"]
    partial_trials = snapshot.trials.loc[
        snapshot.trials["period_id"].ne(period_id) | snapshot.trials["trial_index"].le(1)
    ].copy()
    partial_snapshot = replace(snapshot, trials=partial_trials)

    derived = derive_trials(partial_snapshot, load_config())
    partial_period = derived.loc[derived["period_id"].eq(period_id)].sort_values("trial_number")

    assert len(partial_period) == 2
    assert partial_period.iloc[-1]["within_period_progress"] == pytest.approx(1 / 11)
    assert partial_period.iloc[-1]["global_trial_progress"] == pytest.approx(1 / 35)
    assert not partial_period["period_progress_denominator_inferred"].any()
    assert not partial_period["global_progress_denominator_inferred"].any()


def test_flow_and_order_balance_retain_registered_nonstarter(
    synthetic_snapshot: Path,
) -> None:
    snapshot = load_snapshot(synthetic_snapshot)
    participant_id = "p-nonstarter-synthetic"
    run_id = "r-nonstarter-synthetic"
    extra_participant = snapshot.participants.iloc[[0]].copy()
    extra_participant["participant_id"] = participant_id
    extra_run = snapshot.runs.iloc[[0]].copy()
    extra_run["participant_id"] = participant_id
    extra_run["run_id"] = run_id
    extra_run["run_status"] = "ready"
    extra_run["run_complete"] = False
    extra_run["assigned_style_order"] = "Industry|ISO|Black and white"
    expanded = replace(
        snapshot,
        participants=pd.concat([snapshot.participants, extra_participant], ignore_index=True),
        runs=pd.concat([snapshot.runs, extra_run], ignore_index=True),
    )
    trials = derive_trials(expanded, load_config())

    flow = participant_flow(expanded, trials).set_index("stage")
    balance = order_balance(expanded.runs, load_config().style_order)
    sequence = balance.loc[
        balance["sequence"].eq("Industry → ISO → Black and white") & ~balance["order_inferred"]
    ].iloc[0]

    assert flow.loc["registered", "participants"] == 19
    assert flow.loc["study run created", "runs"] == 19
    assert flow.loc["trial generated", "participants"] == 18
    assert sequence["runs"] == 4
    assert sequence["is_complete_assignment"]


def test_integrity_exclusions_are_removed_from_descriptive_summaries(
    synthetic_snapshot: Path,
) -> None:
    trials = derive_trials(load_snapshot(synthetic_snapshot), load_config())
    participant_id = trials.iloc[0]["participant_id"]
    style = str(trials.iloc[0]["style"])
    excluded = trials["participant_id"].eq(participant_id) & trials["style"].astype(str).eq(style)
    trials.loc[excluded, "integrity_excluded"] = True

    participant = participant_style_summary(trials)
    training = training_summary(trials, load_config())

    assert not (
        participant["participant_id"].eq(participant_id) & participant["style"].eq(style)
    ).any()
    style_accuracy_bins = training.loc[
        training["style"].eq(style) & training["metric"].eq("accuracy")
    ]
    assert style_accuracy_bins["participants"].max() == 17


def test_legacy_methods_do_not_claim_verified_randomisation() -> None:
    methods = build_methods(load_config(), legacy_pilot=True)

    assert "prospective randomisation could not be verified" in methods
    assert "Display order was randomised at participant registration" not in methods


def test_legacy_missing_trial_indices_are_explicitly_inferred(
    synthetic_snapshot: Path,
) -> None:
    _convert_snapshot_to_legacy(synthetic_snapshot)
    trials_path = synthetic_snapshot / "trials.csv"
    source = pd.read_csv(trials_path)
    source["trial_index"] = pd.NA
    source["global_trial_index"] = pd.NA
    source.to_csv(trials_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "trials.csv")

    trials = derive_trials(load_snapshot(synthetic_snapshot), load_config())

    assert trials["trial_order_inferred"].all()
    assert trials["global_order_inferred"].all()
    assert trials.groupby("period_id", observed=True)["trial_number"].min().eq(1).all()


def test_flagged_legacy_deadline_response_is_retained_but_excluded(
    synthetic_snapshot: Path,
) -> None:
    _convert_snapshot_to_legacy(synthetic_snapshot)
    trials_path = synthetic_snapshot / "trials.csv"
    source = pd.read_csv(trials_path)
    row_index = source.index[source["result_present"] & ~source["timed_out"]][0]
    source.loc[row_index, "observed_rt_ms"] = source.loc[row_index, "time_limit_ms"]
    source.loc[row_index, "duration_ms"] = source.loc[row_index, "time_limit_ms"]
    source.loc[row_index, "exclusion_reason"] = (
        "legacy_pilot;trial_index_missing;invalid_response_time"
    )
    source.to_csv(trials_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "trials.csv")

    derived = derive_trials(load_snapshot(synthetic_snapshot), load_config())
    row = derived.loc[derived["trial_id"].eq(source.loc[row_index, "trial_id"])].iloc[0]

    assert row["integrity_excluded"]
    assert not row["valid_observed_rt"]
    assert not row["correct_response"]


def test_normalized_legacy_timeout_flags_remain_valid_accuracy_outcome(
    synthetic_snapshot: Path,
) -> None:
    _convert_snapshot_to_legacy(synthetic_snapshot)
    trials_path = synthetic_snapshot / "trials.csv"
    source = pd.read_csv(trials_path)
    row_index = source.index[source["timed_out"]][0]
    source.loc[row_index, "exclusion_reason"] = (
        "legacy_pilot;trial_index_missing;trial_deadline_mismatch;"
        "invalid_response_time;timeout_inconsistent;timeout"
    )
    source.to_csv(trials_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "trials.csv")

    derived = derive_trials(load_snapshot(synthetic_snapshot), load_config())
    row = derived.loc[derived["trial_id"].eq(source.loc[row_index, "trial_id"])].iloc[0]

    assert not row["integrity_excluded"]
    assert row["timed_out"]
    assert not row["correct"]
    assert not row["response_event"]
    assert row["duration_ms"] == row["time_limit_ms"]


def test_snapshot_rejects_pii_column(synthetic_snapshot: Path) -> None:
    participants_path = synthetic_snapshot / "participants.csv"
    participants = pd.read_csv(participants_path)
    participants["email"] = "person@example.test"
    participants.to_csv(participants_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "participants.csv")

    with pytest.raises(SnapshotValidationError, match="identifying columns"):
        load_snapshot(synthetic_snapshot)


def test_snapshot_rejects_deadline_as_observed_reaction_time(
    synthetic_snapshot: Path,
) -> None:
    trials_path = synthetic_snapshot / "trials.csv"
    trials = pd.read_csv(trials_path)
    timeout_index = trials.index[trials["timed_out"]].tolist()[0]
    trials.loc[timeout_index, "observed_rt_ms"] = trials.loc[timeout_index, "time_limit_ms"]
    trials.to_csv(trials_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "trials.csv")

    with pytest.raises(SnapshotValidationError, match="Timeouts must be censored"):
        load_snapshot(synthetic_snapshot)


def test_pipeline_generates_models_figures_and_paper_drafts(
    synthetic_snapshot: Path, tmp_path: Path
) -> None:
    output = tmp_path / "publication-analysis"
    run_pipeline(synthetic_snapshot, output, strict=True)

    expected = (
        "paper_methods.md",
        "paper_results.md",
        "figure_captions.md",
        "report.md",
        "report.html",
        "analysis_manifest.json",
        "input_snapshot_manifest.json",
        "input_quality_checks.json",
        "tables/participant_characteristics.csv",
        "tables/global_tests.csv",
        "tables/pairwise_contrasts.csv",
        "tables/training_effects.csv",
        "tables/sensitivity_analyses.csv",
        "figures/figure_1_paired_outcomes.png",
        "figures/figure_2_training_effects.svg",
        "figures/figure_3_adjusted_contrasts.pdf",
        "figures/figure_4_trial_outcomes.png",
    )
    for relative in expected:
        assert (output / relative).is_file(), relative
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "paper_results.md").stat().st_mode) == 0o600

    global_tests = pd.read_csv(output / "tables/global_tests.csv")
    assert {
        "primary_accuracy",
        "primary_correct_rt",
        "training_interaction_accuracy",
        "training_interaction_correct_rt",
    }.issubset(set(global_tests["model"]))
    primary_global = global_tests.loc[
        global_tests["model"].isin({"primary_accuracy", "primary_correct_rt"})
    ]
    assert primary_global["degrees_of_freedom"].eq(2).all()
    status = pd.read_csv(output / "tables/model_status.csv")
    accuracy_status = status.loc[status["model"].eq("primary_accuracy")].iloc[0]
    assert accuracy_status["observations"] == 18 * 3 * 12
    contrasts = pd.read_csv(output / "tables/pairwise_contrasts.csv")
    assert contrasts["ci_low"].notna().all()
    assert contrasts["ci_high"].notna().all()
    assert contrasts["p_value_holm"].between(0, 1).all()
    iso_rt = contrasts.loc[
        contrasts["model"].eq("primary_correct_rt") & contrasts["contrast"].eq("ISO vs Industry")
    ].iloc[0]
    assert iso_rt["estimate"] < 1
    training_effects = pd.read_csv(output / "tables/training_effects.csv")
    for model in ("training_interaction_accuracy", "training_interaction_correct_rt"):
        style_effects = training_effects.loc[training_effects["model"].eq(model)]
        assert set(style_effects["style"]) == {"Industry", "ISO", "Black and white"}
        assert len(style_effects) == 3
    methods = (output / "paper_methods.md").read_text(encoding="utf-8")
    assert "generalised estimating equations" in methods
    assert "training" in methods.lower()
    assert "penguin" not in methods.lower()
    results = (output / "paper_results.md").read_text(encoding="utf-8")
    assert "Small-cluster warning" in results
    assert "Full aggregate characteristics" in results
    assert "Descriptive outcomes by display style" in results
    assert "Randomisation order and participant flow" in results
    analysis_manifest = json.loads((output / "analysis_manifest.json").read_text(encoding="utf-8"))
    assert analysis_manifest["input_snapshot"] == synthetic_snapshot.name
    assert analysis_manifest["analysis_source_tree"]["files"] > 0
    assert len(analysis_manifest["analysis_source_tree"]["sha256"]) == 64
    assert analysis_manifest["python"]["version"]


def test_pipeline_refuses_overwrite(synthetic_snapshot: Path, tmp_path: Path) -> None:
    output = tmp_path / "already-there"
    output.mkdir()
    with pytest.raises(FileExistsError):
        run_pipeline(synthetic_snapshot, output)


def test_protocol_one_requires_explicit_legacy_flag(
    synthetic_snapshot: Path, tmp_path: Path
) -> None:
    _convert_snapshot_to_legacy(synthetic_snapshot)

    with pytest.raises(SnapshotValidationError, match="--legacy-pilot"):
        run_pipeline(synthetic_snapshot, tmp_path / "analysis")


def test_snapshot_requires_every_canonical_file_hash(synthetic_snapshot: Path) -> None:
    manifest_path = synthetic_snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].pop("trials.csv")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SnapshotValidationError, match="missing required file hashes"):
        load_snapshot(synthetic_snapshot)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("schema_version", "2.0", "Unsupported snapshot schema_version"),
        ("mode", "combined_protocols", "Snapshot mode must be"),
    ),
)
def test_snapshot_rejects_unsupported_schema_or_mode(
    synthetic_snapshot: Path, field: str, value: str, message: str
) -> None:
    manifest_path = synthetic_snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SnapshotValidationError, match=message):
        load_snapshot(synthetic_snapshot)


def test_snapshot_rejects_unsafe_manifest_paths(synthetic_snapshot: Path) -> None:
    manifest_path = synthetic_snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["../outside.csv"] = {
        "sha256": "0" * 64,
        "rows": 0,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SnapshotValidationError, match="Unsafe manifest file path"):
        load_snapshot(synthetic_snapshot)


def test_snapshot_rejects_unexpected_non_blacklisted_column(
    synthetic_snapshot: Path,
) -> None:
    trials_path = synthetic_snapshot / "trials.csv"
    trials = pd.read_csv(trials_path)
    trials["free_text_notes"] = "must not reach derived output"
    trials.to_csv(trials_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "trials.csv")

    with pytest.raises(SnapshotValidationError, match="unexpected free_text_notes"):
        load_snapshot(synthetic_snapshot)


def test_protocol_two_requires_non_null_relationship_keys(synthetic_snapshot: Path) -> None:
    trials_path = synthetic_snapshot / "trials.csv"
    trials = pd.read_csv(trials_path)
    trials.loc[0, "run_id"] = pd.NA
    trials.to_csv(trials_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "trials.csv")

    with pytest.raises(SnapshotValidationError, match="requires non-null relationship keys"):
        load_snapshot(synthetic_snapshot)


def test_snapshot_rejects_cross_table_participant_mismatch(synthetic_snapshot: Path) -> None:
    trials_path = synthetic_snapshot / "trials.csv"
    trials = pd.read_csv(trials_path)
    trials.loc[0, "participant_id"] = trials.loc[
        trials["participant_id"].ne(trials.loc[0, "participant_id"]), "participant_id"
    ].iloc[0]
    trials.to_csv(trials_path, index=False)
    _refresh_manifest_files(synthetic_snapshot, "trials.csv")

    with pytest.raises(SnapshotValidationError, match="participant_id does not match its run"):
        load_snapshot(synthetic_snapshot)


def test_strict_pipeline_rejects_export_quality_errors(
    synthetic_snapshot: Path, tmp_path: Path
) -> None:
    quality_path = synthetic_snapshot / "quality_checks.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["errors"] = {"trial_group_mismatch": 1}
    quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_manifest_files(synthetic_snapshot, "quality_checks.json")
    output = tmp_path / "analysis"

    with pytest.raises(SnapshotValidationError, match="integrity checks failed"):
        run_pipeline(synthetic_snapshot, output, strict=True)
    assert not output.exists()
