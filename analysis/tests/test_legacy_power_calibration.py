from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.ampoule_analysis.legacy_power_calibration import (
    LegacyCalibrationError,
    calibrate_legacy_power,
    write_legacy_power_calibration,
)

STYLES = ("Industry", "ISO", "Black and white")


def _derived_legacy_trials(path: Path) -> Path:
    rows: list[dict[str, object]] = []
    style_log_rt = {"Industry": 0.0, "ISO": -0.24, "Black and white": -0.04}
    error_modulus = {"Industry": 5, "ISO": 8, "Black and white": 7}
    drugs = ("drug-a", "drug-b", "drug-c", "drug-d")
    for participant in range(12):
        participant_id = f"secret-participant-{participant:02d}"
        order = STYLES[participant % 3 :] + STYLES[: participant % 3]
        for period, style in enumerate(order, start=1):
            for trial in range(12):
                progress = trial / 11
                drug_index = (participant + trial) % len(drugs)
                log_rt = (
                    math.log(2450)
                    + style_log_rt[style]
                    + 0.025 * (participant - 5.5)
                    + 0.025 * (drug_index - 1.5)
                    - 0.03 * (period - 1)
                    - 0.09 * progress
                    + 0.07 * math.sin(participant * 5 + trial * 3)
                )
                latent_rt = math.exp(log_rt)
                response_event = latent_rt < 2650
                incorrect = (trial + 2 * participant + STYLES.index(style)) % error_modulus[
                    style
                ] == 0
                correct = bool(response_event and not incorrect)
                rows.append(
                    {
                        "participant_id": participant_id,
                        "protocol_version": 1,
                        "style": style,
                        "period": period,
                        "within_period_progress": progress,
                        "target_drug": drugs[drug_index],
                        "result_present": True,
                        "response_event": response_event,
                        "correct": correct,
                        "integrity_excluded": False,
                        "observed_rt_ms": latent_rt if response_event else np.nan,
                        "time_limit_ms": 2650,
                    }
                )
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n")
    return path


def test_calibration_is_deterministic_aggregate_only_and_writes_private_json(
    tmp_path: Path,
) -> None:
    source = _derived_legacy_trials(tmp_path / "derived_trials.csv")

    first = calibrate_legacy_power(source)
    second = calibrate_legacy_power(source)

    assert first == second
    assert first["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert first["counts"]["participants"] == 12
    assert first["counts"]["valid_submitted_outcomes"] == 12 * 3 * 12
    assert first["conditional_error_model"]["optimizer"]["success"] is True
    assert first["censored_lognormal_response_time_model"]["optimizer"]["success"] is True
    assert np.isfinite(first["crude_participant_accuracy_rt_correlation"]["pearson_correlation"])
    assert (
        first["participant_by_style_heterogeneity_diagnostics"][
            "participants_with_all_three_styles"
        ]
        == 12
    )
    drug_diagnostics = first["drug_by_style_heterogeneity_diagnostics"]
    assert drug_diagnostics["target_drugs_with_all_three_styles"] == 4
    assert drug_diagnostics["planning_value_classification"].startswith("explicit")
    assert drug_diagnostics["planning_drug_style_log_odds_sd"] == 0.35
    assert drug_diagnostics["planning_drug_style_log_sd"] == 0.08
    alignment = first["power_legacy_pilot_toml_alignment"]
    assert alignment["accuracy"]["drug_style_log_odds_sd"] == 0.35
    assert alignment["reaction_time"]["drug_style_log_sd"] == 0.08
    encoded = json.dumps(first, sort_keys=True)
    assert "secret-participant" not in encoded
    assert "drug-a" not in encoded

    output = write_legacy_power_calibration(source, tmp_path / "calibration.json")
    assert json.loads(output.read_text(encoding="utf-8")) == first
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_legacy_power_calibration(source, output)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.drop(columns="target_drug"), "missing required columns"),
        (lambda data: data.assign(protocol_version=2), "requires a protocol-1"),
        (
            lambda data: data.assign(
                observed_rt_ms=np.where(data["response_event"], 2650, data["observed_rt_ms"])
            ),
            "below their trial deadline",
        ),
    ],
)
def test_calibration_rejects_invalid_derived_data(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    source = _derived_legacy_trials(tmp_path / "derived_trials.csv")
    data = mutation(pd.read_csv(source))
    data.to_csv(source, index=False, lineterminator="\n")

    with pytest.raises(LegacyCalibrationError, match=message):
        calibrate_legacy_power(source)
