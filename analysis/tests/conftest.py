from __future__ import annotations

import csv
import hashlib
import json
import math
from itertools import permutations
from pathlib import Path

import numpy as np
import pytest

from analysis.ampoule_analysis.validate import SNAPSHOT_COLUMNS

STYLES = ("Industry", "ISO", "Black and white")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def synthetic_snapshot(tmp_path: Path) -> Path:
    output = tmp_path / "snapshot"
    output.mkdir()
    rng = np.random.default_rng(271828)
    participants: list[dict[str, object]] = []
    runs: list[dict[str, object]] = []
    periods: list[dict[str, object]] = []
    trials: list[dict[str, object]] = []
    options: list[dict[str, object]] = []
    orders = list(permutations(STYLES))
    style_accuracy = {"Industry": -0.55, "ISO": 0.75, "Black and white": 0.15}
    style_log_rt = {"Industry": 0.16, "ISO": -0.24, "Black and white": 0.02}
    drugs = ("adrenaline", "atropine", "fentanyl", "ketamine", "morphine")

    for participant_number in range(18):
        participant_id = f"p-{participant_number:03d}-synthetic"
        run_id = f"r-{participant_number:03d}-synthetic"
        participants.append(
            {
                "participant_id": participant_id,
                "speciality": "GAS" if participant_number % 2 else "ICM",
                "speciality_label": (
                    "General anaesthesia" if participant_number % 2 else "Intensive care medicine"
                ),
                "years_experience": 2 + participant_number % 12,
            }
        )
        order = orders[participant_number % len(orders)]
        runs.append(
            {
                "participant_id": participant_id,
                "run_id": run_id,
                "protocol_version": 2,
                "configuration_id": "configuration-synthetic",
                "configuration_signature": "trials=12;choices=3;limit_ms=3000",
                "run_status": "completed",
                "assigned_style_order": "|".join(order),
                "order_inferred": False,
                "trials_per_group": 12,
                "choices_per_trial": 3,
                "time_limit_ms": 3000,
                "periods_present": 3,
                "generated_trials": 36,
                "results_present": 36,
                "completed_trials_counter": 36,
                "total_trials_planned": 36,
                "run_complete": True,
            }
        )
        participant_accuracy = rng.normal(0, 0.45)
        participant_log_rt = rng.normal(0, 0.12)
        global_index = 0
        for period, style in enumerate(order, start=1):
            period_id = f"period-{participant_number:03d}-{period}"
            periods.append(
                {
                    "participant_id": participant_id,
                    "run_id": run_id,
                    "period_id": period_id,
                    "protocol_version": 2,
                    "configuration_id": "configuration-synthetic",
                    "style": style,
                    "period": period,
                    "period_status": "completed",
                    "planned_trials": 12,
                    "generated_trials": 12,
                    "results_present": 12,
                    "missing_results": 0,
                    "completed_trials_counter": 12,
                }
            )
            for trial_index in range(12):
                progress = trial_index / 11
                target = drugs[(trial_index + participant_number) % len(drugs)]
                logit = (
                    1.65
                    + participant_accuracy
                    + style_accuracy[style]
                    + 0.30 * progress
                    + 0.08 * (period - 1)
                )
                probability = 1 / (1 + math.exp(-logit))
                correct = bool(rng.binomial(1, probability))
                timed_out = bool(not correct and rng.random() < 0.55)
                responded = not timed_out
                log_rt = (
                    math.log(1850)
                    + participant_log_rt
                    + style_log_rt[style]
                    - 0.15 * progress
                    - 0.035 * (period - 1)
                    + rng.normal(0, 0.15)
                )
                observed_rt = int(np.clip(math.exp(log_rt), 250, 2850)) if responded else ""
                trial_id = f"t-{participant_number:03d}-{period}-{trial_index:03d}"
                selected_position = (1 if correct else 2) if responded else ""
                selected_drug = (
                    target
                    if correct
                    else drugs[(trial_index + participant_number + 1) % len(drugs)]
                    if responded
                    else ""
                )
                trials.append(
                    {
                        "participant_id": participant_id,
                        "run_id": run_id,
                        "period_id": period_id,
                        "trial_id": trial_id,
                        "protocol_version": 2,
                        "configuration_id": "configuration-synthetic",
                        "configuration_signature": "trials=12;choices=3;limit_ms=3000",
                        "run_status": "completed",
                        "style": style,
                        "period": period,
                        "trial_index": trial_index,
                        "global_trial_index": global_index,
                        "time_limit_ms": 3000,
                        "target_drug": target,
                        "result_present": True,
                        "responded": responded,
                        "timed_out": timed_out,
                        "response_event": responded,
                        "correct": correct,
                        "duration_ms": observed_rt if responded else 3000,
                        "observed_rt_ms": observed_rt,
                        "primary_eligible": correct and responded,
                        "exclusion_reason": (
                            "timeout" if timed_out else ("" if correct else "incorrect")
                        ),
                        "choices_per_trial": 3,
                        "offered_count": 3,
                        "selected_drug": selected_drug,
                        "target_option_position": 1,
                        "selected_option_position": selected_position,
                    }
                )
                for position in range(3):
                    option = drugs[(trial_index + participant_number + position) % len(drugs)]
                    options.append(
                        {
                            "participant_id": participant_id,
                            "run_id": run_id,
                            "period_id": period_id,
                            "trial_id": trial_id,
                            "asset_id": f"asset-{trial_id}-{position + 1}",
                            "style": style,
                            "display_position": position + 1,
                            "display_position_known": True,
                            "drug": option,
                            "is_target": option == target,
                            "is_selected": responded and position + 1 == selected_position,
                        }
                    )
                global_index += 1

    rows = {
        "participants.csv": participants,
        "runs.csv": runs,
        "periods.csv": periods,
        "trials.csv": trials,
        "trial_options.csv": options,
    }
    for filename, values in rows.items():
        assert tuple(values[0]) == SNAPSHOT_COLUMNS[filename]
        _write_csv(output / filename, values)
    quality = {
        "schema_version": "1.0",
        "mode": "protocol_2",
        "protocol_version": 2,
        "summary": {
            "participants": len(participants),
            "runs": len(runs),
            "periods": len(periods),
            "trials": len(trials),
            "trial_options": len(options),
            "results_present": len(trials),
        },
        "errors": {},
        "warnings": {},
    }
    (output / "quality_checks.json").write_text(
        json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": "1.0",
        "mode": "protocol_2",
        "protocol_version": 2,
        "csv_columns": {filename: list(columns) for filename, columns in SNAPSHOT_COLUMNS.items()},
        "files": {
            filename: {"sha256": _sha256(output / filename), "rows": len(values)}
            for filename, values in rows.items()
        },
    }
    manifest["files"]["quality_checks.json"] = {
        "sha256": _sha256(output / "quality_checks.json"),
        "rows": None,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output
