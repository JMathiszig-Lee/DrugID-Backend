from django.contrib import admin

from DrugID_API.actions import export_trial_results_csv
from DrugID_API.models import (
    Asset,
    Drug,
    ExperimentConfiguration,
    GroupAttempt,
    MagicLink,
    Participant,
    StudyRun,
    Trial,
    TrialResult,
    TutorialTrial,
    TutorialTrialResult,
)


class ReadOnlyResearchAdminMixin:
    """Research records are changed only by the transactional study service."""

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.get_fields() if field.concrete)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExperimentConfiguration)
class ExperimentConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "trials_per_group",
        "tutorial_trials",
        "choices_per_trial",
        "time_limit_ms",
        "updated_at",
    )

    def has_add_permission(self, request):
        return not ExperimentConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Participant)
class ParticipantAdmin(ReadOnlyResearchAdminMixin, admin.ModelAdmin):
    list_display = ("id", "email", "speciality", "years_experience", "created_at")
    search_fields = ("email",)
    list_filter = ("speciality",)
    readonly_fields = ("created_at",)


@admin.register(StudyRun)
class StudyRunAdmin(ReadOnlyResearchAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "participant",
        "protocol_version",
        "status",
        "tutorial_progress",
        "completed_trials",
        "created_at",
    )
    list_filter = ("protocol_version", "status", "order_inferred")
    readonly_fields = ("created_at", "completed_at")

    @admin.display(description="Tutorial")
    def tutorial_progress(self, obj):
        return f"{obj.tutorial_completed_trials}/{obj.tutorial_trials_required}"


@admin.register(GroupAttempt)
class GroupAttemptAdmin(ReadOnlyResearchAdminMixin, admin.ModelAdmin):
    list_display = ("id", "study_run", "position", "group", "status", "completed_trials")
    list_filter = ("group", "status")


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("id", "drug", "group", "asset_url")
    list_filter = ("group",)
    search_fields = ("drug__name", "asset_url")


@admin.register(Trial)
class TrialAdmin(ReadOnlyResearchAdminMixin, admin.ModelAdmin):
    list_display = ("id", "group_attempt", "trial_index", "group", "target", "time_limit_ms")
    list_filter = ("group",)
    readonly_fields = ("created_at",)


@admin.register(TrialResult)
class TrialResultAdmin(ReadOnlyResearchAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "trial",
        "group_attempt",
        "response_time_ms",
        "correct",
        "timed_out",
        "group",
    )
    list_filter = ("group", "correct", "timed_out")
    readonly_fields = ("created_at",)
    actions = (export_trial_results_csv,)


@admin.register(TutorialTrial)
class TutorialTrialAdmin(ReadOnlyResearchAdminMixin, admin.ModelAdmin):
    list_display = ("id", "study_run", "sequence", "group", "target", "time_limit_ms")
    list_filter = ("group",)


@admin.register(TutorialTrialResult)
class TutorialTrialResultAdmin(ReadOnlyResearchAdminMixin, admin.ModelAdmin):
    list_display = ("id", "trial", "response_time_ms", "correct", "timed_out")
    list_filter = ("correct", "timed_out")


@admin.register(MagicLink)
class MagicLinkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "participant",
        "study_run",
        "created_at",
        "expires_at",
        "used_at",
        "delivery_failed_at",
    )
    readonly_fields = (
        "token_hash",
        "email",
        "participant",
        "study_run",
        "created_at",
        "expires_at",
        "used_at",
        "delivery_failed_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
