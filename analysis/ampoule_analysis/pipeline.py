from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import DEFAULT_CONFIG, AnalysisConfig, load_config
from .derive import derive_trials, participant_flow
from .figures import generate_figures
from .models import ModelBundle, fit_models
from .report import write_reports
from .summaries import (
    order_balance,
    participant_characteristics,
    participant_style_summary,
    style_summary,
    training_summary,
)
from .validate import SnapshotValidationError, load_snapshot

TABLE_NAMES = (
    "model_coefficients",
    "global_tests",
    "marginal_means",
    "pairwise_contrasts",
    "training_effects",
    "sensitivity_analyses",
    "model_status",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_table(table: pd.DataFrame, path: Path) -> None:
    table.to_csv(path, index=False, lineterminator="\n")


def _model_tables(bundle: ModelBundle) -> tuple[pd.DataFrame, ...]:
    return (
        bundle.coefficients,
        bundle.global_tests,
        bundle.marginal_means,
        bundle.pairwise_contrasts,
        bundle.training_effects,
        bundle.sensitivity,
        bundle.status,
    )


def _versions() -> dict[str, str]:
    packages = ("numpy", "pandas", "scipy", "statsmodels", "matplotlib")
    return {package: importlib.metadata.version(package) for package in packages}


def _analysis_source_digest() -> dict[str, Any]:
    analysis_root = Path(__file__).resolve().parents[1]
    source_paths = [analysis_root / "__init__.py"]
    for source_root in (analysis_root / "ampoule_analysis", analysis_root / "config"):
        source_paths.extend(
            path
            for path in source_root.rglob("*")
            if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
        )
    digest = hashlib.sha256()
    files = 0
    for path in sorted(
        set(source_paths), key=lambda item: item.relative_to(analysis_root).as_posix()
    ):
        relative = path.relative_to(analysis_root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        files += 1
    return {"sha256": digest.hexdigest(), "files": files}


def _git_provenance(repository_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ("git", "-C", str(repository_root), "rev-parse", "HEAD"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if commit.returncode != 0:
            return {"available": False}
        status = subprocess.run(
            ("git", "-C", str(repository_root), "status", "--porcelain"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return {
            "available": True,
            "commit": commit.stdout.strip(),
            "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        }
    except OSError, subprocess.SubprocessError:
        return {"available": False}


def _write_manifest(
    output: Path,
    input_path: Path,
    config_path: Path,
    *,
    legacy_pilot: bool,
) -> Path:
    repository_root = Path(__file__).resolve().parents[2]
    lockfile = repository_root / "uv.lock"
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        if path.name == "analysis_manifest.json":
            continue
        relative = str(path.relative_to(output))
        files[relative] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    manifest = {
        "analysis_schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_snapshot": input_path.name,
        "input_snapshot_mode": json.loads(
            (input_path / "manifest.json").read_text(encoding="utf-8")
        ).get("mode"),
        "input_manifest_sha256": _sha256(input_path / "manifest.json"),
        "config_sha256": _sha256(config_path),
        "legacy_pilot": legacy_pilot,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable": Path(sys.executable).name,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "uv_lock_sha256": _sha256(lockfile) if lockfile.is_file() else None,
        "analysis_source_tree": _analysis_source_digest(),
        "git": _git_provenance(repository_root),
        "software_versions": _versions(),
        "files": files,
    }
    path = output / "analysis_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_pipeline(
    snapshot_path: str | Path,
    output_path: str | Path,
    *,
    config_path: str | Path | None = None,
    legacy_pilot: bool = False,
    strict: bool = False,
) -> Path:
    input_path = Path(snapshot_path).resolve()
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError(f"Analysis output already exists: {output}")
    config_file = Path(config_path).resolve() if config_path else DEFAULT_CONFIG.resolve()
    config: AnalysisConfig = load_config(config_file)
    snapshot = load_snapshot(input_path)
    snapshot_mode = snapshot.manifest["mode"]
    if snapshot_mode == "legacy_pilot" and not legacy_pilot:
        raise SnapshotValidationError(
            "Protocol-1 data require --legacy-pilot and must not be pooled with protocol 2"
        )
    if legacy_pilot and snapshot_mode != "legacy_pilot":
        raise SnapshotValidationError(
            "--legacy-pilot cannot be used for a snapshot containing protocol-2 data"
        )
    if strict and snapshot_mode == "protocol_2" and snapshot.quality_checks["errors"]:
        failed_checks = ", ".join(sorted(snapshot.quality_checks["errors"]))
        raise SnapshotValidationError(
            f"Protocol-2 snapshot integrity checks failed: {failed_checks}"
        )

    output.mkdir(mode=0o700, parents=True)
    output.chmod(0o700)
    tables_path = output / "tables"
    figures_path = output / "figures"
    tables_path.mkdir(mode=0o700)
    figures_path.mkdir(mode=0o700)
    try:
        shutil.copyfile(config_file, output / "analysis_config.toml")
        shutil.copyfile(input_path / "manifest.json", output / "input_snapshot_manifest.json")
        quality_path = input_path / "quality_checks.json"
        shutil.copyfile(quality_path, output / "input_quality_checks.json")
        trials = derive_trials(snapshot, config)
        flow = participant_flow(snapshot, trials)
        characteristics = participant_characteristics(snapshot.participants)
        participant = participant_style_summary(trials)
        summary = style_summary(trials, config)
        training = training_summary(trials, config)
        balance = order_balance(snapshot.runs, config.style_order)
        bundle = fit_models(trials, config, legacy_pilot=legacy_pilot)

        descriptive = (
            ("derived_trials", trials),
            ("participant_flow", flow),
            ("participant_characteristics", characteristics),
            ("participant_style_summary", participant),
            ("style_summary", summary),
            ("training_summary", training),
            ("randomisation_order_balance", balance),
        )
        for name, table in descriptive:
            _write_table(table, tables_path / f"{name}.csv")
        for name, table in zip(TABLE_NAMES, _model_tables(bundle), strict=True):
            _write_table(table, tables_path / f"{name}.csv")

        generate_figures(
            trials,
            participant,
            summary,
            training,
            bundle.pairwise_contrasts,
            figures_path,
            config,
        )
        write_reports(
            output,
            snapshot,
            trials,
            flow,
            bundle,
            summary,
            balance,
            config,
            legacy_pilot=legacy_pilot,
        )
        if strict and (bundle.status["status"] != "fitted").any():
            failed = ", ".join(bundle.status.loc[bundle.status["status"] != "fitted", "model"])
            raise RuntimeError(f"Required statistical models failed: {failed}")
        for generated_file in output.rglob("*"):
            if generated_file.is_file():
                generated_file.chmod(0o600)
            elif generated_file.is_dir():
                generated_file.chmod(0o700)
        manifest_path = _write_manifest(
            output,
            input_path,
            config_file,
            legacy_pilot=legacy_pilot,
        )
        manifest_path.chmod(0o600)
    except Exception:
        shutil.rmtree(output)
        raise
    return output
