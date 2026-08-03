from decimal import Decimal, InvalidOperation

from django.db import migrations


def import_legacy_study_runs(apps, schema_editor):
    ExperimentConfiguration = apps.get_model("DrugID_API", "ExperimentConfiguration")
    Participant = apps.get_model("DrugID_API", "Participant")
    StudyRun = apps.get_model("DrugID_API", "StudyRun")
    GroupAttempt = apps.get_model("DrugID_API", "GroupAttempt")
    Trial = apps.get_model("DrugID_API", "Trial")
    TrialResult = apps.get_model("DrugID_API", "TrialResult")
    Asset = apps.get_model("DrugID_API", "Asset")

    ExperimentConfiguration.objects.get_or_create(
        pk=1,
        defaults={
            "trials_per_group": 50,
            "choices_per_trial": 8,
            "time_limit_ms": 3000,
        },
    )

    for participant in Participant.objects.order_by("pk").iterator():
        attempts = list(
            GroupAttempt.objects.filter(participant_id=participant.pk).order_by("pk")
        )
        if not attempts:
            continue

        group_order = [attempt.group for attempt in attempts]
        completed_by_attempt = [
            TrialResult.objects.filter(group_attempt_id=attempt.pk).count()
            for attempt in attempts
        ]
        inferred_trials_per_group = max(completed_by_attempt, default=1)
        run = StudyRun.objects.create(
            participant_id=participant.pk,
            protocol_version=1,
            status="archived",
            group_order=group_order,
            order_inferred=True,
            trials_per_group=inferred_trials_per_group,
            choices_per_trial=8,
            time_limit_ms=3000,
            current_group_position=None,
            completed_trials=0,
        )

        run_completed = 0
        for position, attempt in enumerate(attempts):
            completed = completed_by_attempt[position]
            GroupAttempt.objects.filter(pk=attempt.pk).update(
                study_run_id=run.pk,
                position=position,
                status="archived",
                completed_trials=completed,
            )
            run_completed += completed

        StudyRun.objects.filter(pk=run.pk).update(completed_trials=run_completed)

    for result in TrialResult.objects.select_related("trial").order_by("pk").iterator():
        response_time = None
        try:
            parsed_time = Decimal(result.time)
            if parsed_time.is_finite() and parsed_time >= 0:
                response_time = int(parsed_time.to_integral_value())
        except (InvalidOperation, TypeError, ValueError):
            pass

        selected_asset_id = None
        if result.selected and result.trial_id:
            selected_asset_id = (
                result.trial.assets.filter(drug__name__iexact=result.selected)
                .values_list("id", flat=True)
                .first()
            )

        TrialResult.objects.filter(pk=result.pk).update(
            response_time_ms=response_time,
            selected_asset_id=selected_asset_id,
            timed_out=result.selected is None,
        )
        if result.trial_id:
            Trial.objects.filter(pk=result.trial_id, group_attempt__isnull=True).update(
                group_attempt_id=result.group_attempt_id
            )

    for asset in Asset.objects.exclude(asset_url="").iterator():
        normalized = asset.asset_url.lstrip("/")
        if normalized.startswith("static/"):
            normalized = normalized[len("static/") :]
        if normalized != asset.asset_url:
            Asset.objects.filter(pk=asset.pk).update(asset_url=normalized)


def reverse_legacy_study_runs(apps, schema_editor):
    StudyRun = apps.get_model("DrugID_API", "StudyRun")
    GroupAttempt = apps.get_model("DrugID_API", "GroupAttempt")
    Trial = apps.get_model("DrugID_API", "Trial")
    TrialResult = apps.get_model("DrugID_API", "TrialResult")
    Asset = apps.get_model("DrugID_API", "Asset")

    # Restore the participant relationship required by the pre-rescue Session
    # table before its renamed parent link is removed on rollback.
    for run in StudyRun.objects.order_by("pk").iterator():
        GroupAttempt.objects.filter(study_run_id=run.pk).update(
            participant_id=run.participant_id
        )

    imported_run_ids = list(
        StudyRun.objects.filter(protocol_version=1, order_inferred=True).values_list(
            "id", flat=True
        )
    )
    imported_attempt_ids = list(
        GroupAttempt.objects.filter(study_run_id__in=imported_run_ids).values_list(
            "id", flat=True
        )
    )
    TrialResult.objects.filter(group_attempt_id__in=imported_attempt_ids).update(
        response_time_ms=None,
        selected_asset_id=None,
        timed_out=False,
    )
    Trial.objects.filter(group_attempt_id__in=imported_attempt_ids).update(
        group_attempt_id=None
    )
    GroupAttempt.objects.filter(id__in=imported_attempt_ids).update(
        study_run_id=None,
        position=None,
        status="pending",
        completed_trials=0,
    )
    StudyRun.objects.filter(id__in=imported_run_ids).delete()

    for asset in Asset.objects.exclude(asset_url="").iterator():
        if not asset.asset_url.startswith("static/"):
            Asset.objects.filter(pk=asset.pk).update(
                asset_url=f"static/{asset.asset_url.lstrip('/')}"
            )


class Migration(migrations.Migration):
    dependencies = [("DrugID_API", "0008_study_rescue_schema")]

    operations = [
        migrations.RunPython(import_legacy_study_runs, reverse_legacy_study_runs),
    ]
