import csv
from datetime import date, datetime

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def export_as_csv(*, description="Download selected rows as CSV", fields=None):
    """Build an admin CSV action without relying on model string rendering."""

    @admin.action(description=description)
    def action(modeladmin, request, queryset):
        if not request.user.is_staff:
            raise PermissionDenied

        selected_fields = fields or [field.name for field in queryset.model._meta.fields]
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        model_name = queryset.model._meta.model_name
        response["Content-Disposition"] = f'attachment; filename="{model_name}.csv"'
        writer = csv.writer(response)
        writer.writerow(selected_fields)

        model_fields = {field.name: field for field in queryset.model._meta.fields}
        for instance in queryset.iterator():
            row = []
            for field_name in selected_fields:
                field = model_fields[field_name]
                row.append(_csv_value(field.value_from_object(instance)))
            writer.writerow(row)
        return response

    return action


download_csv = export_as_csv(description="Download selected rows as CSV")


@admin.action(description="Download analysis-ready CSV", permissions=("view",))
def export_trial_results_csv(modeladmin, request, queryset):
    if not request.user.is_staff:
        raise PermissionDenied

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="trial-results.csv"'
    writer = csv.writer(response)
    columns = (
        "result_id",
        "participant_id",
        "speciality",
        "years_experience",
        "study_run_id",
        "protocol_version",
        "group_order",
        "group_position",
        "group_style",
        "trial_id",
        "trial_sequence",
        "target_drug",
        "offered_drugs",
        "selected_asset_id",
        "selected_drug",
        "response_time_ms",
        "correct",
        "timed_out",
        "raw_time",
        "raw_selected",
        "raw_sequence",
        "created_at",
    )
    writer.writerow(columns)

    results = queryset.select_related(
        "trial__target",
        "group_attempt__study_run__participant",
        "selected_asset__drug",
    ).prefetch_related("trial__assets__drug")
    for result in results.iterator(chunk_size=500):
        attempt = result.group_attempt
        run = attempt.study_run
        participant = run.participant
        trial = result.trial
        offered = []
        if trial is not None:
            assets_by_id = {asset.pk: asset for asset in trial.assets.all()}
            ordered_ids = trial.asset_order or sorted(assets_by_id)
            offered = [
                assets_by_id[asset_id].drug.name
                for asset_id in ordered_ids
                if asset_id in assets_by_id
            ]

        values = (
            result.pk,
            participant.pk,
            participant.speciality,
            participant.years_experience,
            run.pk,
            run.protocol_version,
            "|".join(str(group) for group in run.group_order),
            attempt.position + 1,
            result.get_group_display(),
            trial.pk if trial else None,
            trial.trial_index if trial else None,
            trial.target.name if trial else None,
            "|".join(offered),
            result.selected_asset_id,
            result.selected_asset.drug.name if result.selected_asset else None,
            result.response_time_ms,
            result.correct,
            result.timed_out,
            result.time,
            result.selected,
            result.sequence_id,
            result.created_at,
        )
        writer.writerow([_csv_value(value) for value in values])

    return response
