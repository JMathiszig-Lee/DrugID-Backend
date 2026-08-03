import os

from django.core.management.base import BaseCommand, CommandError

from DrugID_API.analysis_export import (
    SnapshotValidationError,
    export_analysis_snapshot,
)


class Command(BaseCommand):
    help = (
        "Export a deterministic, pseudonymized protocol-2 analysis snapshot. "
        "Legacy data requires the explicit --legacy-pilot flag."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            required=True,
            help="New directory in which to write the snapshot.",
        )
        parser.add_argument(
            "--legacy-pilot",
            action="store_true",
            help="Export protocol-1 pilot records instead of protocol 2.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Refuse protocol-2 export when an integrity check fails.",
        )

    def handle(self, *args, **options):
        pseudonym_key = os.environ.get("ANALYSIS_PSEUDONYM_KEY")
        if not pseudonym_key:
            raise CommandError("Set ANALYSIS_PSEUDONYM_KEY to a secret value of at least 32 bytes.")

        try:
            manifest = export_analysis_snapshot(
                output_dir=options["output"],
                pseudonym_key=pseudonym_key,
                legacy_pilot=options["legacy_pilot"],
                strict=options["strict"],
            )
        except (FileExistsError, SnapshotValidationError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        counts = manifest["counts"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {counts['runs']} runs and {counts['trials']} trials "
                f"to {options['output']}."
            )
        )
