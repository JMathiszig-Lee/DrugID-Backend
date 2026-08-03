from __future__ import annotations

import csv
import hashlib
import hmac
import json
import shutil
from collections import Counter
from pathlib import Path

from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Prefetch

from DrugID_API.models import (
    Asset,
    Group,
    GroupAttempt,
    StudyRun,
    Trial,
    TrialResult,
)

SNAPSHOT_SCHEMA_VERSION = "1.0"
MINIMUM_PSEUDONYM_KEY_BYTES = 32

CSV_SCHEMAS = {
    "participants.csv": (
        "participant_id",
        "speciality",
        "speciality_label",
        "years_experience",
    ),
    "runs.csv": (
        "participant_id",
        "run_id",
        "protocol_version",
        "configuration_id",
        "configuration_signature",
        "run_status",
        "assigned_style_order",
        "order_inferred",
        "trials_per_group",
        "choices_per_trial",
        "time_limit_ms",
        "periods_present",
        "generated_trials",
        "results_present",
        "completed_trials_counter",
        "total_trials_planned",
        "run_complete",
    ),
    "periods.csv": (
        "participant_id",
        "run_id",
        "period_id",
        "protocol_version",
        "configuration_id",
        "style",
        "period",
        "period_status",
        "planned_trials",
        "generated_trials",
        "results_present",
        "missing_results",
        "completed_trials_counter",
    ),
    "trials.csv": (
        "participant_id",
        "run_id",
        "period_id",
        "trial_id",
        "protocol_version",
        "configuration_id",
        "configuration_signature",
        "run_status",
        "style",
        "period",
        "trial_index",
        "global_trial_index",
        "time_limit_ms",
        "target_drug",
        "result_present",
        "responded",
        "timed_out",
        "response_event",
        "correct",
        "duration_ms",
        "observed_rt_ms",
        "primary_eligible",
        "exclusion_reason",
        "choices_per_trial",
        "offered_count",
        "selected_drug",
        "target_option_position",
        "selected_option_position",
    ),
    "trial_options.csv": (
        "participant_id",
        "run_id",
        "period_id",
        "trial_id",
        "asset_id",
        "style",
        "display_position",
        "display_position_known",
        "drug",
        "is_target",
        "is_selected",
    ),
}


class SnapshotValidationError(ValueError):
    pass


def _style_label(group_value) -> str:
    try:
        return Group(int(group_value)).label
    except TypeError, ValueError:
        return f"Unknown ({group_value})"


def _configuration_signature(run: StudyRun) -> str:
    signature = (
        f"trials={run.trials_per_group};choices={run.choices_per_trial};"
        f"limit_ms={run.time_limit_ms}"
    )
    tutorial_trials = int(getattr(run, "tutorial_trials_required", 0) or 0)
    if tutorial_trials:
        signature = f"{signature};tutorial_trials={tutorial_trials}"
    return signature


def _configuration_id(signature: str) -> str:
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
    return f"configuration_{digest}"


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=headers,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({header: _csv_value(row.get(header)) for header in headers})
    path.chmod(0o600)


def _write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(payload, output_file, indent=2, sort_keys=True, ensure_ascii=False)
        output_file.write("\n")
    path.chmod(0o600)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _migration_leaf() -> str | None:
    return (
        MigrationRecorder.Migration.objects.filter(app="DrugID_API")
        .order_by("name")
        .values_list("name", flat=True)
        .last()
    )


def _trial_result(trial: Trial) -> TrialResult | None:
    try:
        return trial.result
    except TrialResult.DoesNotExist:
        return None


class _SnapshotBuilder:
    def __init__(self, *, pseudonym_key: bytes, legacy_pilot: bool):
        self.pseudonym_key = pseudonym_key
        self.legacy_pilot = legacy_pilot
        self.protocol_version = 1 if legacy_pilot else 2
        self.rows = {filename: [] for filename in CSV_SCHEMAS}
        self.integrity_issues = Counter()
        self.configuration_signatures = set()
        self.tutorial_runs_by_required_count = Counter()
        self.tutorial_completion_counts = Counter()

    def pseudonym(self, entity: str, primary_key) -> str:
        message = f"drugid-analysis:{entity}:{primary_key}".encode("utf-8")
        digest = hmac.new(self.pseudonym_key, message, hashlib.sha256).hexdigest()
        return f"{entity}_{digest}"

    def record_issue(self, issue: str, count: int = 1) -> None:
        self.integrity_issues[issue] += count

    def add_participant(self, participant) -> None:
        speciality_labels = dict(participant.SPECIALITY_CHOICES)
        self.rows["participants.csv"].append(
            {
                "participant_id": self.pseudonym("participant", participant.pk),
                "speciality": participant.speciality,
                "speciality_label": speciality_labels.get(participant.speciality, "Unknown"),
                "years_experience": participant.years_experience,
            }
        )

    def add_trial(
        self,
        *,
        trial: Trial,
        run: StudyRun | None,
        attempt: GroupAttempt | None,
        duplicate_trial_index: bool = False,
        noncontiguous_trial_indices: bool = False,
    ) -> None:
        participant_id = self.pseudonym("participant", run.participant_id) if run else ""
        run_id = self.pseudonym("run", run.pk) if run else ""
        period_id = self.pseudonym("period", attempt.pk) if attempt else ""
        trial_id = self.pseudonym("trial", trial.pk)
        signature = _configuration_signature(run) if run else ""
        configuration_id = _configuration_id(signature) if signature else ""
        period = (
            attempt.position + 1 if attempt is not None and attempt.position is not None else None
        )
        trial_index = trial.trial_index
        global_trial_index = None
        if run is not None and period is not None and trial_index is not None and trial_index > 0:
            global_trial_index = (period - 1) * run.trials_per_group + trial_index

        assets = sorted(trial.assets.all(), key=lambda asset: asset.pk)
        assets_by_id = {asset.pk: asset for asset in assets}
        asset_ids = [asset.pk for asset in assets]
        order = trial.asset_order if isinstance(trial.asset_order, list) else []
        try:
            asset_order_valid = (
                len(order) == len(asset_ids)
                and len(set(order)) == len(order)
                and set(order) == set(asset_ids)
            )
        except TypeError:
            asset_order_valid = False
        if asset_order_valid:
            ordered_assets = [assets_by_id[asset_id] for asset_id in order]
        else:
            ordered_assets = assets
            self.record_issue("asset_order_unavailable_or_invalid")

        offered_count_matches = run is None or len(assets) == run.choices_per_trial
        if not offered_count_matches:
            self.record_issue("offered_count_mismatch")

        target_offered = any(asset.drug_id == trial.target_id for asset in assets)
        if not target_offered:
            self.record_issue("target_not_offered")

        trial_group_matches = attempt is None or trial.group == attempt.group
        if not trial_group_matches:
            self.record_issue("trial_group_mismatch")
        trial_deadline_matches = run is None or trial.time_limit_ms == run.time_limit_ms
        if not trial_deadline_matches:
            self.record_issue("trial_deadline_mismatch")

        result = _trial_result(trial)
        result_present = result is not None
        timed_out = bool(result.timed_out) if result else False
        responded = bool(result is not None and not timed_out)
        response_event = responded
        correct = bool(result.correct) if result else None
        response_time = result.response_time_ms if result else None
        duration_ms = None
        observed_rt_ms = None
        if result is not None:
            duration_ms = trial.time_limit_ms if timed_out else response_time
            observed_rt_ms = None if timed_out else response_time

        selected_asset = result.selected_asset if result else None
        selected_drug = selected_asset.drug.name if selected_asset else ""
        selected_offered = selected_asset is None or selected_asset.pk in assets_by_id
        if not selected_offered:
            self.record_issue("selected_asset_not_offered")

        expected_correct = bool(
            selected_asset is not None and selected_asset.drug_id == trial.target_id
        )
        correctness_matches = result is None or result.correct == expected_correct
        if not correctness_matches:
            self.record_issue("correctness_mismatch")

        result_group_matches = result is None or (
            result.group == trial.group
            and (attempt is None or result.group_attempt_id == attempt.pk)
        )
        if not result_group_matches:
            self.record_issue("result_group_or_period_mismatch")

        response_time_valid = result is None or (
            response_time is not None
            and 0 < response_time <= trial.time_limit_ms
            and not (responded and response_time >= trial.time_limit_ms)
        )
        if not response_time_valid:
            self.record_issue("response_time_invalid")

        timeout_consistent = result is None or (
            (timed_out and selected_asset is None) or (not timed_out and selected_asset is not None)
        )
        if result is not None and timed_out and response_time != trial.time_limit_ms:
            timeout_consistent = False
        if not timeout_consistent:
            self.record_issue("timeout_inconsistent")

        trial_index_valid = trial_index is not None and trial_index > 0
        if not trial_index_valid:
            self.record_issue("trial_index_missing_or_invalid")
        if duplicate_trial_index:
            self.record_issue("duplicate_trial_index")
        if noncontiguous_trial_indices:
            self.record_issue("noncontiguous_trial_indices")

        reasons = []
        if self.legacy_pilot:
            reasons.append("legacy_pilot")
        if run is None or attempt is None:
            reasons.append("unassigned_legacy_trial")
        if result is None:
            reasons.append("missing_result")
        if not trial_index_valid:
            reasons.append("trial_index_missing")
        if duplicate_trial_index:
            reasons.append("duplicate_trial_index")
        if noncontiguous_trial_indices:
            reasons.append("noncontiguous_trial_indices")
        if not target_offered:
            reasons.append("target_not_offered")
        if not offered_count_matches:
            reasons.append("offered_count_mismatch")
        if not trial_group_matches:
            reasons.append("trial_group_mismatch")
        if not trial_deadline_matches:
            reasons.append("trial_deadline_mismatch")
        if not asset_order_valid and not self.legacy_pilot:
            reasons.append("asset_order_invalid")
        if not result_group_matches:
            reasons.append("result_group_or_period_mismatch")
        if not selected_offered:
            reasons.append("selected_asset_not_offered")
        if not correctness_matches:
            reasons.append("correctness_mismatch")
        if not response_time_valid:
            reasons.append("invalid_response_time")
        if not timeout_consistent:
            reasons.append("timeout_inconsistent")
        if timed_out:
            reasons.append("timeout")
        elif result is not None and not result.correct:
            reasons.append("incorrect")
        reasons = list(dict.fromkeys(reasons))

        target_position = None
        selected_position = None
        if asset_order_valid:
            for position, asset in enumerate(ordered_assets, start=1):
                if target_position is None and asset.drug_id == trial.target_id:
                    target_position = position
                if selected_asset is not None and asset.pk == selected_asset.pk:
                    selected_position = position

        self.rows["trials.csv"].append(
            {
                "participant_id": participant_id,
                "run_id": run_id,
                "period_id": period_id,
                "trial_id": trial_id,
                "protocol_version": run.protocol_version if run else 1,
                "configuration_id": configuration_id,
                "configuration_signature": signature,
                "run_status": run.status if run else "",
                "style": _style_label(trial.group),
                "period": period,
                "trial_index": trial_index,
                "global_trial_index": global_trial_index,
                "time_limit_ms": trial.time_limit_ms,
                "target_drug": trial.target.name,
                "result_present": result_present,
                "responded": responded,
                "timed_out": timed_out if result else None,
                "response_event": response_event,
                "correct": correct,
                "duration_ms": duration_ms,
                "observed_rt_ms": observed_rt_ms,
                "primary_eligible": not reasons,
                "exclusion_reason": ";".join(reasons),
                "choices_per_trial": run.choices_per_trial if run else None,
                "offered_count": len(assets),
                "selected_drug": selected_drug,
                "target_option_position": target_position,
                "selected_option_position": selected_position,
            }
        )

        for position, asset in enumerate(ordered_assets, start=1):
            self.rows["trial_options.csv"].append(
                {
                    "participant_id": participant_id,
                    "run_id": run_id,
                    "period_id": period_id,
                    "trial_id": trial_id,
                    "asset_id": self.pseudonym("asset", asset.pk),
                    "style": _style_label(trial.group),
                    "display_position": position if asset_order_valid else None,
                    "display_position_known": asset_order_valid,
                    "drug": asset.drug.name,
                    "is_target": asset.drug_id == trial.target_id,
                    "is_selected": (selected_asset is not None and asset.pk == selected_asset.pk),
                }
            )

    def quality_payload(self) -> dict:
        summary = {
            "participants": len(self.rows["participants.csv"]),
            "runs": len(self.rows["runs.csv"]),
            "periods": len(self.rows["periods.csv"]),
            "trials": len(self.rows["trials.csv"]),
            "trial_options": len(self.rows["trial_options.csv"]),
            "results_present": sum(int(row["result_present"]) for row in self.rows["trials.csv"]),
            "responded": sum(int(row["responded"]) for row in self.rows["trials.csv"]),
            "timed_out": sum(int(bool(row["timed_out"])) for row in self.rows["trials.csv"]),
            "primary_eligible": sum(
                int(row["primary_eligible"]) for row in self.rows["trials.csv"]
            ),
        }
        issue_payload = dict(sorted(self.integrity_issues.items()))
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "mode": "legacy_pilot" if self.legacy_pilot else "protocol_2",
            "protocol_version": self.protocol_version,
            "summary": summary,
            "errors": {} if self.legacy_pilot else issue_payload,
            "warnings": issue_payload if self.legacy_pilot else {},
        }


def _snapshot_querysets(protocol_version: int):
    # Deliberately traverse only the measured GroupAttempt -> Trial graph.
    # TutorialTrial/TutorialTrialResult are operational practice data and are
    # represented only by aggregate run provenance in the manifest.
    asset_queryset = Asset.objects.select_related("drug").order_by("pk")
    trial_queryset = (
        Trial.objects.select_related("target", "result__selected_asset__drug")
        .prefetch_related(Prefetch("assets", queryset=asset_queryset))
        .order_by("pk")
    )
    result_queryset = TrialResult.objects.order_by("pk")
    attempt_queryset = GroupAttempt.objects.prefetch_related(
        Prefetch("trials", queryset=trial_queryset),
        Prefetch("results", queryset=result_queryset),
    ).order_by("study_run_id", "position", "pk")
    runs = (
        StudyRun.objects.filter(protocol_version=protocol_version)
        .select_related("participant")
        .prefetch_related(Prefetch("group_attempts", queryset=attempt_queryset))
        .order_by("pk")
    )
    return runs, trial_queryset


def _collect_snapshot(*, pseudonym_key: bytes, legacy_pilot: bool):
    builder = _SnapshotBuilder(
        pseudonym_key=pseudonym_key,
        legacy_pilot=legacy_pilot,
    )
    runs_queryset, trial_queryset = _snapshot_querysets(builder.protocol_version)
    runs = list(runs_queryset)

    seen_participants = set()
    for run in runs:
        if run.participant_id not in seen_participants:
            builder.add_participant(run.participant)
            seen_participants.add(run.participant_id)

        participant_id = builder.pseudonym("participant", run.participant_id)
        run_id = builder.pseudonym("run", run.pk)
        signature = _configuration_signature(run)
        configuration_id = _configuration_id(signature)
        builder.configuration_signatures.add(signature)
        tutorial_trials_required = int(getattr(run, "tutorial_trials_required", 0) or 0)
        builder.tutorial_runs_by_required_count[str(tutorial_trials_required)] += 1
        if tutorial_trials_required == 0:
            builder.tutorial_completion_counts["not_required"] += 1
        elif run.tutorial_complete:
            builder.tutorial_completion_counts["complete"] += 1
        else:
            builder.tutorial_completion_counts["incomplete"] += 1
        attempts = sorted(
            run.group_attempts.all(),
            key=lambda attempt: (
                attempt.position is None,
                attempt.position if attempt.position is not None else 0,
                attempt.pk,
            ),
        )

        try:
            order_values = [int(value) for value in run.group_order]
        except TypeError, ValueError:
            order_values = []
        if run.protocol_version >= 2 and (
            len(order_values) != 3 or set(order_values) != set(Group.values)
        ):
            builder.record_issue("invalid_group_order")
        if run.protocol_version >= 2 and len(attempts) != 3:
            builder.record_issue("period_count_mismatch")

        generated_for_run = 0
        results_for_run = 0
        for attempt in attempts:
            period = attempt.position + 1 if attempt.position is not None else None
            if (
                attempt.position is None
                or attempt.position < 0
                or attempt.position >= len(order_values)
                or order_values[attempt.position] != attempt.group
            ):
                builder.record_issue("period_assignment_mismatch")

            trials = sorted(
                attempt.trials.all(),
                key=lambda trial: (
                    trial.trial_index is None,
                    trial.trial_index if trial.trial_index is not None else 0,
                    trial.pk,
                ),
            )
            attempt_results = list(attempt.results.all())
            linked_results = sum(int(_trial_result(trial) is not None) for trial in trials)
            unlinked_results = sum(int(result.trial_id is None) for result in attempt_results)
            if unlinked_results:
                builder.record_issue("unlinked_results", unlinked_results)
            if attempt.completed_trials != len(attempt_results):
                builder.record_issue("period_counter_mismatch")

            index_counts = Counter(
                trial.trial_index
                for trial in trials
                if trial.trial_index is not None and trial.trial_index > 0
            )
            positive_indices = sorted(index_counts)
            indices_contiguous = positive_indices == list(range(1, len(positive_indices) + 1))

            for trial in trials:
                builder.add_trial(
                    trial=trial,
                    run=run,
                    attempt=attempt,
                    duplicate_trial_index=(
                        trial.trial_index is not None and index_counts[trial.trial_index] > 1
                    ),
                    noncontiguous_trial_indices=(
                        trial.trial_index is not None and not indices_contiguous
                    ),
                )

            generated_for_run += len(trials)
            results_for_run += len(attempt_results)
            builder.rows["periods.csv"].append(
                {
                    "participant_id": participant_id,
                    "run_id": run_id,
                    "period_id": builder.pseudonym("period", attempt.pk),
                    "protocol_version": run.protocol_version,
                    "configuration_id": configuration_id,
                    "style": _style_label(attempt.group),
                    "period": period,
                    "period_status": attempt.status,
                    "planned_trials": run.trials_per_group,
                    "generated_trials": len(trials),
                    "results_present": linked_results,
                    "missing_results": len(trials) - linked_results,
                    "completed_trials_counter": attempt.completed_trials,
                }
            )

        if run.completed_trials != results_for_run:
            builder.record_issue("run_counter_mismatch")
        if run.status == StudyRun.Status.COMPLETED and (results_for_run != run.total_trials):
            builder.record_issue("completed_run_trial_count_mismatch")
        if results_for_run > run.total_trials:
            builder.record_issue("results_exceed_planned_total")

        assigned_style_order = "|".join(_style_label(value) for value in order_values)
        builder.rows["runs.csv"].append(
            {
                "participant_id": participant_id,
                "run_id": run_id,
                "protocol_version": run.protocol_version,
                "configuration_id": configuration_id,
                "configuration_signature": signature,
                "run_status": run.status,
                "assigned_style_order": assigned_style_order,
                "order_inferred": run.order_inferred,
                "trials_per_group": run.trials_per_group,
                "choices_per_trial": run.choices_per_trial,
                "time_limit_ms": run.time_limit_ms,
                "periods_present": len(attempts),
                "generated_trials": generated_for_run,
                "results_present": results_for_run,
                "completed_trials_counter": run.completed_trials,
                "total_trials_planned": run.total_trials,
                "run_complete": run.status == StudyRun.Status.COMPLETED,
            }
        )

    if legacy_pilot:
        unassigned_trials = list(trial_queryset.filter(group_attempt__isnull=True).order_by("pk"))
        if unassigned_trials:
            builder.record_issue("unassigned_legacy_trials", len(unassigned_trials))
        for trial in unassigned_trials:
            builder.add_trial(trial=trial, run=None, attempt=None)

    builder.rows["participants.csv"].sort(key=lambda row: row["participant_id"])
    return builder, _migration_leaf()


def export_analysis_snapshot(
    *,
    output_dir: str | Path,
    pseudonym_key: str | bytes,
    legacy_pilot: bool = False,
    strict: bool = False,
) -> dict:
    """Write a deterministic, direct-identifier-free analysis snapshot."""

    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Snapshot destination already exists: {destination}")

    key_bytes = pseudonym_key.encode("utf-8") if isinstance(pseudonym_key, str) else pseudonym_key
    if len(key_bytes) < MINIMUM_PSEUDONYM_KEY_BYTES:
        raise ValueError(
            f"The analysis pseudonym key must be at least {MINIMUM_PSEUDONYM_KEY_BYTES} bytes."
        )

    already_in_transaction = connection.in_atomic_block
    with transaction.atomic():
        if connection.vendor == "postgresql" and not already_in_transaction:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        builder, migration_leaf = _collect_snapshot(
            pseudonym_key=key_bytes,
            legacy_pilot=legacy_pilot,
        )

    quality = builder.quality_payload()
    if strict and quality["errors"]:
        issue_names = ", ".join(quality["errors"])
        raise SnapshotValidationError(f"Protocol-2 integrity checks failed: {issue_names}")

    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    destination.chmod(0o700)
    try:
        for filename, headers in CSV_SCHEMAS.items():
            _write_csv(destination / filename, headers, builder.rows[filename])
        _write_json(destination / "quality_checks.json", quality)

        file_metadata = {}
        for filename in (*CSV_SCHEMAS, "quality_checks.json"):
            file_metadata[filename] = {
                "sha256": _file_digest(destination / filename),
                "rows": (len(builder.rows[filename]) if filename in builder.rows else None),
            }

        key_id = hmac.new(
            key_bytes,
            b"drugid-analysis-pseudonym-key-id",
            hashlib.sha256,
        ).hexdigest()[:16]
        manifest = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "mode": "legacy_pilot" if legacy_pilot else "protocol_2",
            "protocol_version": 1 if legacy_pilot else 2,
            "database_vendor": connection.vendor,
            "migration_leaf": migration_leaf,
            "pseudonymization": "typed HMAC-SHA256",
            "pseudonym_key_id": key_id,
            "direct_identifiers_excluded": [
                "account",
                "email",
                "magic_link",
                "session",
            ],
            "period_numbering": "1-based",
            "timeout_semantics": {
                "duration_ms": "trial time limit",
                "observed_rt_ms": None,
                "response_event": 0,
            },
            "primary_eligible_definition": (
                "Protocol-2 correct, non-timeout result with valid trial, option, "
                "ordering, timing, and provenance invariants. Run completion is not required."
            ),
            "tutorial_provenance": {
                "configuration_signature_semantics": (
                    "tutorial_trials=<n> is appended when a run required a tutorial; "
                    "an absent token means that no tutorial was required"
                ),
                "measured_trial_sources": ["Trial", "TrialResult"],
                "excluded_operational_sources": [
                    "TutorialTrial",
                    "TutorialTrialResult",
                ],
                "tutorial_trial_rows_exported": False,
                "tutorial_result_rows_exported": False,
                "runs_by_required_trial_count": dict(
                    sorted(builder.tutorial_runs_by_required_count.items())
                ),
                "tutorial_completion_counts": dict(
                    sorted(builder.tutorial_completion_counts.items())
                ),
            },
            "csv_columns": {filename: list(headers) for filename, headers in CSV_SCHEMAS.items()},
            "configuration_signatures": sorted(builder.configuration_signatures),
            "counts": quality["summary"],
            "files": file_metadata,
        }
        _write_json(destination / "manifest.json", manifest)
        return manifest
    except Exception:
        shutil.rmtree(destination)
        raise
