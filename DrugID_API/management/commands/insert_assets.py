from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from DrugID_API.models import Asset, Drug, ExperimentConfiguration, Group


class Command(BaseCommand):
    help = "Idempotently load the private ampoule image catalogue."

    @transaction.atomic
    def handle(self, *args, **options):
        asset_root = Path(settings.STUDY_ASSET_ROOT).resolve()
        group_directories = {
            Group.INDUSTRY: "industry",
            Group.ISO: "iso",
            Group.BLACK_WHITE: "blackwhite",
        }
        supported_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
        loaded = 0

        for group, directory_name in group_directories.items():
            directory = asset_root / directory_name
            if not directory.is_dir():
                raise CommandError(f"Asset directory does not exist: {directory}")

            for image_path in sorted(directory.iterdir()):
                if not image_path.is_file() or image_path.suffix.lower() not in supported_suffixes:
                    continue
                drug, _ = Drug.objects.get_or_create(name=image_path.stem)
                Asset.objects.update_or_create(
                    drug=drug,
                    group=group,
                    defaults={"asset_url": f"{directory_name}/{image_path.name}"},
                )
                loaded += 1

        common_catalog_size = (
            Drug.objects.annotate(group_count=Count("assets__group", distinct=True))
            .filter(group_count=len(Group.values))
            .count()
        )
        required_choices = ExperimentConfiguration.load().choices_per_trial
        if common_catalog_size < required_choices:
            raise CommandError(
                "The common three-group drug catalogue has "
                f"{common_catalog_size} drugs, but {required_choices} choices are configured."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {loaded} ampoule image records; "
                f"{common_catalog_size} drugs are available in every group."
            )
        )
