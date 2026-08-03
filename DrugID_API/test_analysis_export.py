import csv
import hashlib
import hmac
import json
import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from DrugID_API.analysis_export import export_analysis_snapshot
from DrugID_API.models import (
    Asset,
    Drug,
    Group,
    GroupAttempt,
    Participant,
    StudyRun,
    Trial,
    TrialResult,
    TutorialTrial,
    TutorialTrialResult,
)


class AnalysisSnapshotExportTests(TestCase):
    pseudonym_key = "analysis-test-key-that-is-longer-than-thirty-two-bytes"

    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.output_root = Path(self.temporary_directory.name)

        account = get_user_model().objects.create_user(
            username="private-study-account",
            email="direct-identifier@example.test",
            password=None,
        )
        self.participant = Participant.objects.create(
            account=account,
            email="direct-identifier@example.test",
            speciality="ICM",
            years_experience=9,
        )
        self.run = StudyRun.objects.create(
            participant=self.participant,
            protocol_version=2,
            status=StudyRun.Status.IN_PROGRESS,
            group_order=[Group.INDUSTRY, Group.ISO, Group.BLACK_WHITE],
            order_inferred=False,
            trials_per_group=1,
            choices_per_trial=2,
            time_limit_ms=1000,
            current_group_position=2,
            completed_trials=2,
        )
        self.attempts = []
        for position, group in enumerate(self.run.group_order):
            self.attempts.append(
                GroupAttempt.objects.create(
                    study_run=self.run,
                    position=position,
                    group=group,
                    status=(
                        GroupAttempt.Status.ACTIVE
                        if position == 2
                        else GroupAttempt.Status.COMPLETED
                    ),
                    completed_trials=0 if position == 2 else 1,
                )
            )

        self.drugs = [Drug.objects.create(name=name) for name in ("adrenaline", "atropine")]
        self.assets = {}
        for group in Group.values:
            self.assets[group] = [
                Asset.objects.create(
                    drug=drug,
                    group=group,
                    asset_url=f"group-{group}/{drug.name}.png",
                )
                for drug in self.drugs
            ]

        self.trials = []
        for position, attempt in enumerate(self.attempts):
            first_asset, second_asset = self.assets[attempt.group]
            ordered_assets = (
                [second_asset, first_asset] if position == 0 else [first_asset, second_asset]
            )
            target = first_asset.drug if position != 1 else second_asset.drug
            trial = Trial.objects.create(
                group_attempt=attempt,
                group=attempt.group,
                target=target,
                time_limit_ms=1000,
                trial_index=1,
                asset_order=[asset.pk for asset in ordered_assets],
            )
            trial.assets.set(ordered_assets)
            self.trials.append(trial)

        selected_asset = self.assets[Group.INDUSTRY][0]
        TrialResult.objects.create(
            trial=self.trials[0],
            time="250",
            selected=selected_asset.drug.name,
            correct=True,
            sequence_id="1",
            group_attempt=self.attempts[0],
            group=Group.INDUSTRY,
            response_time_ms=250,
            selected_asset=selected_asset,
            timed_out=False,
        )
        unassigned_legacy_trial = Trial.objects.create(
            group_attempt=None,
            group=Group.INDUSTRY,
            target=self.drugs[1],
            time_limit_ms=1000,
            trial_index=None,
            asset_order=[],
        )
        unassigned_legacy_trial.assets.set(self.assets[Group.INDUSTRY])
        TrialResult.objects.create(
            trial=self.trials[1],
            time="1000",
            selected=None,
            correct=False,
            sequence_id="1",
            group_attempt=self.attempts[1],
            group=Group.ISO,
            response_time_ms=1000,
            selected_asset=None,
            timed_out=True,
        )

    def export(self, name, **options):
        output = self.output_root / name
        with mock.patch.dict(
            os.environ,
            {"ANALYSIS_PSEUDONYM_KEY": self.pseudonym_key},
        ):
            call_command(
                "export_analysis_snapshot",
                output=str(output),
                verbosity=0,
                **options,
            )
        return output

    def read_csv(self, output, filename):
        with (output / filename).open(encoding="utf-8", newline="") as input_file:
            return list(csv.DictReader(input_file))

    def test_protocol_2_snapshot_is_private_deterministic_and_analysis_ready(self):
        first_output = self.export("first")
        second_output = self.export("second")

        expected_files = {
            "manifest.json",
            "participants.csv",
            "periods.csv",
            "quality_checks.json",
            "runs.csv",
            "trial_options.csv",
            "trials.csv",
        }
        self.assertEqual({path.name for path in first_output.iterdir()}, expected_files)
        self.assertEqual(stat.S_IMODE(first_output.stat().st_mode), 0o700)
        self.assertTrue(
            all(
                stat.S_IMODE((first_output / filename).stat().st_mode) == 0o600
                for filename in expected_files
            )
        )
        for filename in expected_files:
            self.assertEqual(
                (first_output / filename).read_bytes(),
                (second_output / filename).read_bytes(),
                filename,
            )

        all_csv_text = "\n".join(
            (first_output / filename).read_text(encoding="utf-8")
            for filename in expected_files
            if filename.endswith(".csv")
        )
        self.assertNotIn("direct-identifier@example.test", all_csv_text)
        self.assertNotIn("private-study-account", all_csv_text)

        participants = self.read_csv(first_output, "participants.csv")
        self.assertEqual(len(participants), 1)
        expected_digest = hmac.new(
            self.pseudonym_key.encode(),
            f"drugid-analysis:participant:{self.participant.pk}".encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(participants[0]["participant_id"], f"participant_{expected_digest}")
        self.assertEqual(participants[0]["speciality"], "ICM")
        self.assertEqual(participants[0]["years_experience"], "9")

        trials = {row["style"]: row for row in self.read_csv(first_output, "trials.csv")}
        correct = trials["Industry"]
        self.assertEqual(correct["period"], "1")
        self.assertEqual(correct["global_trial_index"], "1")
        self.assertEqual(correct["result_present"], "1")
        self.assertEqual(correct["responded"], "1")
        self.assertEqual(correct["response_event"], "1")
        self.assertEqual(correct["duration_ms"], "250")
        self.assertEqual(correct["observed_rt_ms"], "250")
        self.assertEqual(correct["primary_eligible"], "1")
        self.assertEqual(correct["exclusion_reason"], "")
        self.assertEqual(correct["target_option_position"], "2")
        self.assertEqual(correct["selected_option_position"], "2")

        timeout = trials["ISO"]
        self.assertEqual(timeout["period"], "2")
        self.assertEqual(timeout["global_trial_index"], "2")
        self.assertEqual(timeout["result_present"], "1")
        self.assertEqual(timeout["responded"], "0")
        self.assertEqual(timeout["timed_out"], "1")
        self.assertEqual(timeout["response_event"], "0")
        self.assertEqual(timeout["duration_ms"], "1000")
        self.assertEqual(timeout["observed_rt_ms"], "")
        self.assertEqual(timeout["primary_eligible"], "0")
        self.assertEqual(timeout["exclusion_reason"], "timeout")

        missing = trials["Black and white"]
        self.assertEqual(missing["period"], "3")
        self.assertEqual(missing["global_trial_index"], "3")
        self.assertEqual(missing["result_present"], "0")
        self.assertEqual(missing["duration_ms"], "")
        self.assertEqual(missing["observed_rt_ms"], "")
        self.assertEqual(missing["exclusion_reason"], "missing_result")

        quality = json.loads((first_output / "quality_checks.json").read_text(encoding="utf-8"))
        self.assertEqual(quality["errors"], {})
        self.assertEqual(quality["summary"]["trials"], 3)
        self.assertEqual(quality["summary"]["primary_eligible"], 1)

        manifest = json.loads((first_output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["mode"], "protocol_2")
        self.assertEqual(manifest["period_numbering"], "1-based")
        self.assertEqual(manifest["timeout_semantics"]["response_event"], 0)
        self.assertIn("global_trial_index", manifest["csv_columns"]["trials.csv"])
        for filename, metadata in manifest["files"].items():
            self.assertEqual(
                metadata["sha256"],
                hashlib.sha256((first_output / filename).read_bytes()).hexdigest(),
            )

    def test_tutorial_trials_and_results_are_excluded_from_analysis_snapshot(self):
        tutorial_only_drug = Drug.objects.create(name="tutorial-only-marker")
        tutorial_only_asset = Asset.objects.create(
            drug=tutorial_only_drug,
            group=Group.INDUSTRY,
            asset_url="tutorial/tutorial-only-marker.png",
        )
        tutorial_trial = TutorialTrial.objects.create(
            study_run=self.run,
            group=Group.INDUSTRY,
            target=tutorial_only_drug,
            time_limit_ms=1000,
            sequence=1,
            asset_order=[tutorial_only_asset.pk],
        )
        tutorial_trial.assets.add(tutorial_only_asset)
        TutorialTrialResult.objects.create(
            trial=tutorial_trial,
            selected_asset=tutorial_only_asset,
            response_time_ms=250,
            correct=True,
            timed_out=False,
        )

        output = self.export("tutorial-excluded")
        exported_csv = "\n".join(path.read_text(encoding="utf-8") for path in output.glob("*.csv"))
        quality = json.loads((output / "quality_checks.json").read_text(encoding="utf-8"))

        self.assertNotIn("tutorial-only-marker", exported_csv)
        self.assertEqual(len(self.read_csv(output, "trials.csv")), 3)
        self.assertEqual(len(self.read_csv(output, "trial_options.csv")), 6)
        self.assertEqual(quality["summary"]["trials"], 3)
        self.assertEqual(quality["warnings"].get("unassigned_legacy_trials", 0), 0)

    def test_existing_destination_and_missing_or_short_key_are_refused(self):
        existing = self.output_root / "existing"
        existing.mkdir()
        sentinel = existing / "keep.txt"
        sentinel.write_text("unchanged", encoding="utf-8")

        with mock.patch.dict(
            os.environ,
            {"ANALYSIS_PSEUDONYM_KEY": self.pseudonym_key},
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "export_analysis_snapshot",
                    output=str(existing),
                    verbosity=0,
                )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(CommandError):
                call_command(
                    "export_analysis_snapshot",
                    output=str(self.output_root / "missing-key"),
                    verbosity=0,
                )

        with mock.patch.dict(os.environ, {"ANALYSIS_PSEUDONYM_KEY": "too-short"}):
            with self.assertRaises(CommandError):
                call_command(
                    "export_analysis_snapshot",
                    output=str(self.output_root / "short-key"),
                    verbosity=0,
                )

    def test_legacy_records_require_explicit_pilot_mode(self):
        legacy_run = StudyRun.objects.create(
            participant=self.participant,
            protocol_version=1,
            status=StudyRun.Status.ARCHIVED,
            group_order=[Group.BLACK_WHITE],
            order_inferred=True,
            trials_per_group=1,
            choices_per_trial=2,
            time_limit_ms=1000,
            current_group_position=None,
            completed_trials=1,
        )
        legacy_attempt = GroupAttempt.objects.create(
            study_run=legacy_run,
            position=0,
            group=Group.BLACK_WHITE,
            status=GroupAttempt.Status.ARCHIVED,
            completed_trials=1,
        )
        legacy_trial = Trial.objects.create(
            group_attempt=legacy_attempt,
            group=Group.BLACK_WHITE,
            target=self.drugs[0],
            time_limit_ms=1000,
            trial_index=None,
            asset_order=[],
        )
        legacy_trial.assets.set(self.assets[Group.BLACK_WHITE])
        selected_asset = self.assets[Group.BLACK_WHITE][0]
        TrialResult.objects.create(
            trial=legacy_trial,
            time="400.4",
            selected=selected_asset.drug.name,
            correct=True,
            sequence_id="0",
            group_attempt=legacy_attempt,
            group=Group.BLACK_WHITE,
            response_time_ms=400,
            selected_asset=selected_asset,
            timed_out=False,
        )

        protocol_2_output = self.export("protocol-2")
        self.assertEqual(
            {row["protocol_version"] for row in self.read_csv(protocol_2_output, "trials.csv")},
            {"2"},
        )

        legacy_output = self.export("legacy", legacy_pilot=True)
        legacy_rows = self.read_csv(legacy_output, "trials.csv")
        self.assertEqual(len(legacy_rows), 2)
        self.assertEqual({row["protocol_version"] for row in legacy_rows}, {"1"})
        self.assertTrue(all(row["primary_eligible"] == "0" for row in legacy_rows))
        self.assertTrue(all("legacy_pilot" in row["exclusion_reason"] for row in legacy_rows))
        self.assertTrue(
            all("trial_index_missing" in row["exclusion_reason"] for row in legacy_rows)
        )
        unassigned_row = next(row for row in legacy_rows if row["run_id"] == "")
        self.assertIn("unassigned_legacy_trial", unassigned_row["exclusion_reason"])
        self.assertIn("missing_result", unassigned_row["exclusion_reason"])

        options = self.read_csv(legacy_output, "trial_options.csv")
        self.assertTrue(options)
        self.assertTrue(all(row["display_position"] == "" for row in options))
        self.assertTrue(all(row["display_position_known"] == "0" for row in options))

        quality = json.loads((legacy_output / "quality_checks.json").read_text(encoding="utf-8"))
        self.assertEqual(quality["mode"], "legacy_pilot")
        self.assertEqual(quality["errors"], {})
        self.assertIn("asset_order_unavailable_or_invalid", quality["warnings"])
        self.assertEqual(quality["warnings"]["unassigned_legacy_trials"], 1)

    def test_strict_mode_fails_before_writing_a_corrupt_protocol_2_snapshot(self):
        unoffered_target = Drug.objects.create(name="not-offered")
        self.trials[0].target = unoffered_target
        self.trials[0].save(update_fields=("target",))
        destination = self.output_root / "strict"

        with mock.patch.dict(
            os.environ,
            {"ANALYSIS_PSEUDONYM_KEY": self.pseudonym_key},
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "export_analysis_snapshot",
                    output=str(destination),
                    strict=True,
                    verbosity=0,
                )
        self.assertFalse(destination.exists())

    def test_group_and_deadline_mismatches_are_trial_exclusion_reasons(self):
        trial = self.trials[0]
        trial.group = Group.ISO
        trial.time_limit_ms = 900
        trial.save(update_fields=("group", "time_limit_ms"))

        output = self.export("row-integrity-reasons")
        trial_rows = self.read_csv(output, "trials.csv")
        affected = next(
            row for row in trial_rows if "trial_group_mismatch" in row["exclusion_reason"]
        )

        self.assertIn("trial_deadline_mismatch", affected["exclusion_reason"])
        self.assertEqual(affected["primary_eligible"], "0")
        quality = json.loads((output / "quality_checks.json").read_text(encoding="utf-8"))
        self.assertEqual(quality["errors"]["trial_group_mismatch"], 1)
        self.assertEqual(quality["errors"]["trial_deadline_mismatch"], 1)

    def test_write_failure_removes_partial_snapshot(self):
        destination = self.output_root / "partial"

        with mock.patch(
            "DrugID_API.analysis_export._write_csv",
            side_effect=OSError("simulated write failure"),
        ):
            with self.assertRaisesRegex(OSError, "simulated write failure"):
                export_analysis_snapshot(
                    output_dir=destination,
                    pseudonym_key=self.pseudonym_key,
                )

        self.assertFalse(destination.exists())
