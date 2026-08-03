from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd


class SnapshotValidationError(ValueError):
    """Raised when a snapshot is unsafe or internally inconsistent."""


SNAPSHOT_SCHEMA_VERSION = "1.0"
SNAPSHOT_COLUMNS: dict[str, tuple[str, ...]] = {
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
FILES = tuple(filename.removesuffix(".csv") for filename in SNAPSHOT_COLUMNS)
HASHED_FILES = frozenset((*SNAPSHOT_COLUMNS, "quality_checks.json"))
FORBIDDEN_COLUMN_PARTS = (
    "email",
    "first_name",
    "last_name",
    "magic",
    "password",
    "session_key",
    "auth_token",
)


@dataclass(frozen=True)
class Snapshot:
    path: Path
    manifest: dict[str, Any]
    quality_checks: dict[str, Any]
    participants: pd.DataFrame
    runs: pd.DataFrame
    periods: pd.DataFrame
    trials: pd.DataFrame
    trial_options: pd.DataFrame


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SnapshotValidationError(f"Snapshot is missing a regular {label} file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SnapshotValidationError(f"{label} is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise SnapshotValidationError(f"{label} must contain a JSON object")
    return payload


def _read_manifest(path: Path) -> dict[str, Any]:
    return _read_json(path / "manifest.json", "manifest.json")


def _safe_manifest_filename(filename: object) -> bool:
    if not isinstance(filename, str):
        return False
    relative = PurePosixPath(filename)
    return (
        filename not in {"", ".", ".."}
        and not relative.is_absolute()
        and len(relative.parts) == 1
        and relative.name == filename
    )


def _validate_manifest(manifest: dict[str, Any]) -> tuple[str, int]:
    if str(manifest.get("schema_version")) != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError(
            f"Unsupported snapshot schema_version; expected {SNAPSHOT_SCHEMA_VERSION}"
        )
    mode = manifest.get("mode")
    expected_protocol = {"protocol_2": 2, "legacy_pilot": 1}.get(mode)
    if expected_protocol is None:
        raise SnapshotValidationError("Snapshot mode must be protocol_2 or legacy_pilot")
    try:
        manifest_protocol = int(manifest.get("protocol_version"))
    except (TypeError, ValueError) as exc:
        raise SnapshotValidationError("Manifest protocol_version must be an integer") from exc
    if manifest_protocol != expected_protocol:
        raise SnapshotValidationError("Snapshot mode and protocol_version are inconsistent")

    declared_columns = manifest.get("csv_columns")
    expected_columns = {filename: list(columns) for filename, columns in SNAPSHOT_COLUMNS.items()}
    if declared_columns != expected_columns:
        raise SnapshotValidationError("Manifest csv_columns do not match snapshot schema 1.0")

    tutorial_provenance = manifest.get("tutorial_provenance")
    if tutorial_provenance is not None:
        if not isinstance(tutorial_provenance, dict):
            raise SnapshotValidationError("Manifest tutorial_provenance must be an object")
        for field in ("tutorial_trial_rows_exported", "tutorial_result_rows_exported"):
            if tutorial_provenance.get(field) is not False:
                raise SnapshotValidationError(f"Manifest tutorial_provenance.{field} must be false")

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise SnapshotValidationError("Manifest files must be an object")
    unsafe = [str(filename) for filename in files if not _safe_manifest_filename(filename)]
    if unsafe:
        raise SnapshotValidationError(f"Unsafe manifest file path: {unsafe[0]}")
    declared_files = set(files)
    missing = HASHED_FILES - declared_files
    unexpected = declared_files - HASHED_FILES
    if missing:
        raise SnapshotValidationError(
            "Manifest is missing required file hashes: " + ", ".join(sorted(missing))
        )
    if unexpected:
        raise SnapshotValidationError(
            "Manifest contains unexpected files: " + ", ".join(sorted(unexpected))
        )
    return str(mode), expected_protocol


def _verify_hashes(path: Path, manifest: dict[str, Any]) -> None:
    hashes = manifest["files"]
    for filename in sorted(HASHED_FILES):
        details = hashes[filename]
        if not isinstance(details, dict):
            raise SnapshotValidationError(f"Manifest metadata for {filename} must be an object")
        expected = details.get("sha256")
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise SnapshotValidationError(f"Manifest has an invalid SHA-256 for {filename}")
        file_path = path / filename
        if file_path.is_symlink() or not file_path.is_file():
            raise SnapshotValidationError(f"Manifest file is missing or not regular: {filename}")
        if _sha256(file_path) != expected:
            raise SnapshotValidationError(f"Checksum mismatch for {filename}")


def _validate_quality_checks(quality: dict[str, Any], *, mode: str, protocol_version: int) -> None:
    if str(quality.get("schema_version")) != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError("quality_checks.json has an unsupported schema_version")
    if quality.get("mode") != mode or quality.get("protocol_version") != protocol_version:
        raise SnapshotValidationError(
            "Quality checks and manifest describe different snapshot modes"
        )
    for field in ("errors", "warnings"):
        if not isinstance(quality.get(field), dict):
            raise SnapshotValidationError(f"quality_checks.{field} must be an object")


def _validate_table_schema(filename: str, table: pd.DataFrame, manifest: dict[str, Any]) -> None:
    forbidden = [
        column
        for column in table.columns
        if any(part in column.lower() for part in FORBIDDEN_COLUMN_PARTS)
    ]
    if forbidden:
        raise SnapshotValidationError(
            f"Potentially identifying columns in {filename}: {', '.join(forbidden)}"
        )
    expected = SNAPSHOT_COLUMNS[filename]
    actual = tuple(str(column) for column in table.columns)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        if not details:
            details.append("columns are in the wrong order")
        raise SnapshotValidationError(f"{filename} schema mismatch: {'; '.join(details)}")

    declared_rows = manifest["files"][filename].get("rows")
    if (
        isinstance(declared_rows, bool)
        or not isinstance(declared_rows, int)
        or declared_rows < 0
        or declared_rows != len(table)
    ):
        raise SnapshotValidationError(f"Manifest row count does not match {filename}")


def load_snapshot(path: str | Path, *, verify_hashes: bool = True) -> Snapshot:
    snapshot_path = Path(path).resolve()
    if not snapshot_path.is_dir():
        raise SnapshotValidationError(f"Snapshot directory does not exist: {snapshot_path}")
    manifest = _read_manifest(snapshot_path)
    mode, protocol_version = _validate_manifest(manifest)
    if verify_hashes:
        _verify_hashes(snapshot_path, manifest)

    quality = _read_json(snapshot_path / "quality_checks.json", "quality_checks.json")
    _validate_quality_checks(quality, mode=mode, protocol_version=protocol_version)

    tables: dict[str, pd.DataFrame] = {}
    for stem in FILES:
        filename = f"{stem}.csv"
        csv_path = snapshot_path / filename
        if csv_path.is_symlink() or not csv_path.is_file():
            raise SnapshotValidationError(f"Snapshot is missing a regular {filename} file")
        table = pd.read_csv(csv_path, dtype_backend="numpy_nullable")
        _validate_table_schema(filename, table, manifest)
        tables[stem] = table

    _validate_protocol_versions(tables, expected=protocol_version)
    _validate_keys(tables, require_relations=mode == "protocol_2")
    _validate_trial_outcomes(
        tables["trials"],
        allow_flagged_legacy_timing=mode == "legacy_pilot",
    )
    return Snapshot(
        path=snapshot_path,
        manifest=manifest,
        quality_checks=quality,
        **tables,
    )


def _validate_protocol_versions(tables: dict[str, pd.DataFrame], *, expected: int) -> None:
    for stem in ("runs", "periods", "trials"):
        versions = pd.to_numeric(tables[stem]["protocol_version"], errors="coerce")
        if versions.isna().any() or versions.ne(expected).any():
            raise SnapshotValidationError(
                f"{stem}.protocol_version must contain only protocol {expected}"
            )


def _require_non_null(table: pd.DataFrame, stem: str, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if table[column].isna().any()]
    if missing:
        raise SnapshotValidationError(
            f"{stem} requires non-null relationship keys: {', '.join(missing)}"
        )


def _same_keys(actual: pd.Series, expected: pd.Series) -> bool:
    missing_marker = "__drugid_missing_relationship_key__"
    left = actual.astype("string").fillna(missing_marker)
    right = expected.astype("string").fillna(missing_marker)
    return bool(left.eq(right).all())


def _validate_relationship_consistency(tables: dict[str, pd.DataFrame]) -> None:
    runs = tables["runs"]
    periods = tables["periods"]
    trials = tables["trials"]
    options = tables["trial_options"]

    run_participants = runs.set_index("run_id")["participant_id"]
    if not _same_keys(periods["participant_id"], periods["run_id"].map(run_participants)):
        raise SnapshotValidationError("periods participant_id does not match its run")

    if not _same_keys(trials["participant_id"], trials["run_id"].map(run_participants)):
        raise SnapshotValidationError("trials participant_id does not match its run")

    period_runs = periods.set_index("period_id")["run_id"]
    period_participants = periods.set_index("period_id")["participant_id"]
    if not _same_keys(trials["run_id"], trials["period_id"].map(period_runs)):
        raise SnapshotValidationError("trials run_id does not match its period")
    if not _same_keys(trials["participant_id"], trials["period_id"].map(period_participants)):
        raise SnapshotValidationError("trials participant_id does not match its period")

    trial_relationships = trials.set_index("trial_id")
    for column in ("participant_id", "run_id", "period_id"):
        if not _same_keys(options[column], options["trial_id"].map(trial_relationships[column])):
            raise SnapshotValidationError(f"trial_options {column} does not match its trial")


def _validate_keys(tables: dict[str, pd.DataFrame], *, require_relations: bool) -> None:
    for stem, key in (
        ("participants", "participant_id"),
        ("runs", "run_id"),
        ("periods", "period_id"),
        ("trials", "trial_id"),
    ):
        table = tables[stem]
        if table[key].isna().any() or table[key].duplicated().any():
            raise SnapshotValidationError(f"{stem}.{key} must be present and unique")

    if require_relations:
        _require_non_null(tables["runs"], "runs", ("participant_id",))
        _require_non_null(tables["periods"], "periods", ("participant_id", "run_id"))
        _require_non_null(tables["trials"], "trials", ("participant_id", "run_id", "period_id"))
        _require_non_null(
            tables["trial_options"],
            "trial_options",
            ("participant_id", "run_id", "period_id", "trial_id"),
        )

    foreign_keys = (
        ("runs", "participant_id", "participants", "participant_id"),
        ("periods", "participant_id", "participants", "participant_id"),
        ("periods", "run_id", "runs", "run_id"),
        ("trials", "participant_id", "participants", "participant_id"),
        ("trials", "run_id", "runs", "run_id"),
        ("trials", "period_id", "periods", "period_id"),
        ("trial_options", "participant_id", "participants", "participant_id"),
        ("trial_options", "run_id", "runs", "run_id"),
        ("trial_options", "period_id", "periods", "period_id"),
        ("trial_options", "trial_id", "trials", "trial_id"),
    )
    for child, child_key, parent, parent_key in foreign_keys:
        unknown = set(tables[child][child_key].dropna()) - set(tables[parent][parent_key])
        if unknown:
            raise SnapshotValidationError(
                f"{child}.{child_key} contains {len(unknown)} unknown {parent} keys"
            )

    _validate_relationship_consistency(tables)

    options = tables["trial_options"]
    positioned = options.loc[options["display_position"].notna()]
    if positioned[["trial_id", "display_position"]].duplicated().any():
        raise SnapshotValidationError("Trial option positions must be unique within a trial")


def _as_boolean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.lower().str.strip().isin({"true", "1", "yes", "y", "t"})


def _validate_trial_outcomes(
    trials: pd.DataFrame,
    *,
    allow_flagged_legacy_timing: bool = False,
) -> None:
    present = _as_boolean(trials["result_present"])
    timed_out = _as_boolean(trials["timed_out"])
    correct = _as_boolean(trials["correct"])
    responded = _as_boolean(trials["responded"])
    response_event = _as_boolean(trials["response_event"])
    observed = pd.to_numeric(trials["observed_rt_ms"], errors="coerce")
    duration = pd.to_numeric(trials["duration_ms"], errors="coerce")
    deadline = pd.to_numeric(trials["time_limit_ms"], errors="coerce")

    if ((~present) & (timed_out | responded | response_event | correct)).any():
        raise SnapshotValidationError("A missing result cannot contain an outcome event")
    if ((~present) & duration.notna()).any():
        raise SnapshotValidationError("A missing result cannot contain an analysis duration")
    if (present & ~timed_out & ~responded).any():
        raise SnapshotValidationError("Every submitted result must be a response or timeout")
    if (timed_out & (responded | response_event | correct | observed.notna())).any():
        raise SnapshotValidationError("Timeouts must be censored and cannot contain observed RT")
    if (timed_out & (duration.isna() | deadline.isna() | duration.ne(deadline))).any():
        raise SnapshotValidationError("Timeout duration must equal the trial deadline")
    invalid_observed_timing = responded & (
        ~response_event
        | observed.isna()
        | observed.le(0)
        | deadline.isna()
        | observed.ge(deadline)
        | duration.ne(observed)
    )
    if invalid_observed_timing.any():
        explicitly_excluded = (
            trials["exclusion_reason"]
            .astype("string")
            .str.contains(
                r"(?:^|;)invalid_response_time(?:;|$)",
                regex=True,
                na=False,
            )
        )
        if (
            not allow_flagged_legacy_timing
            or (invalid_observed_timing & ~explicitly_excluded).any()
        ):
            raise SnapshotValidationError("Observed responses contain invalid timing/event values")
    if ((~responded) & (~timed_out) & observed.notna()).any():
        raise SnapshotValidationError("A non-response cannot contain an observed RT")
