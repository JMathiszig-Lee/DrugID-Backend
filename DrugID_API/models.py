from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Group(models.IntegerChoices):
    INDUSTRY = 1, "Industry"
    ISO = 2, "ISO"
    BLACK_WHITE = 3, "Black and white"


class Participant(models.Model):
    SPECIALITY_CHOICES = [
        ("GAS", "Anaesthetics"),
        ("A+E", "Emergency Medicine"),
        ("ICM", "Intensive Care"),
        ("OTH", "Other"),
    ]

    account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="participant",
    )
    email = models.EmailField(max_length=254)
    speciality = models.CharField(
        max_length=3,
        choices=SPECIALITY_CHOICES,
        default="GAS",
    )
    years_experience = models.PositiveSmallIntegerField(
        null=True,
        validators=[MaxValueValidator(80)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="drugid_participant_email_ci_unique",
            ),
        ]
        ordering = ("id",)

    def __str__(self) -> str:
        return f"Participant {self.pk}"


class ExperimentConfiguration(models.Model):
    """The singleton protocol used when a new study run is created.

    Values are snapshotted onto :class:`StudyRun`, so changing the protocol in
    the admin never changes an experiment already in progress.
    """

    trials_per_group = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(1)],
    )
    choices_per_trial = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(2), MaxValueValidator(20)],
    )
    time_limit_ms = models.PositiveIntegerField(
        default=3000,
        validators=[MinValueValidator(100), MaxValueValidator(600_000)],
    )
    tutorial_trials = models.PositiveSmallIntegerField(
        default=6,
        validators=[MinValueValidator(5), MaxValueValidator(10)],
        help_text="Practice trials shown before the measured experiment (5 to 10).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "experiment configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pragma: no cover - guarded in admin too
        raise ValidationError("The experiment configuration cannot be deleted.")

    @classmethod
    def load(cls) -> "ExperimentConfiguration":
        configuration, _ = cls.objects.get_or_create(pk=1)
        return configuration

    def __str__(self) -> str:
        return "Experiment configuration"


class StudyRun(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Ready"
        IN_PROGRESS = "in_progress", "In progress"
        BETWEEN_GROUPS = "between_groups", "Between groups"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived legacy run"

    participant = models.ForeignKey(
        Participant,
        on_delete=models.PROTECT,
        related_name="study_runs",
    )
    protocol_version = models.PositiveSmallIntegerField(default=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.READY,
    )
    group_order = models.JSONField(default=list)
    order_inferred = models.BooleanField(default=False)
    trials_per_group = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
    )
    choices_per_trial = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2), MaxValueValidator(20)],
    )
    time_limit_ms = models.PositiveIntegerField(
        validators=[MinValueValidator(100), MaxValueValidator(600_000)],
    )
    tutorial_trials_required = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(10)],
        help_text="A snapshot of the tutorial length; zero identifies grandfathered runs.",
    )
    tutorial_group_order = models.JSONField(default=list)
    tutorial_completed_trials = models.PositiveSmallIntegerField(default=0)
    tutorial_completed_at = models.DateTimeField(blank=True, null=True)
    current_group_position = models.PositiveSmallIntegerField(default=0, null=True)
    completed_trials = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("participant", "protocol_version"),
                name="drugid_participant_protocol_unique",
            ),
            models.UniqueConstraint(
                fields=("participant",),
                condition=models.Q(
                    status__in=(
                        "ready",
                        "in_progress",
                        "between_groups",
                    )
                ),
                name="drugid_one_active_run_per_participant",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tutorial_trials_required=0)
                    | models.Q(tutorial_trials_required__gte=5, tutorial_trials_required__lte=10)
                ),
                name="drugid_tutorial_required_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    tutorial_completed_trials__lte=models.F("tutorial_trials_required")
                ),
                name="drugid_tutorial_completed_lte_required",
            ),
        ]

    def clean(self):
        super().clean()
        allowed_groups = set(Group.values)
        if self.protocol_version >= 2:
            if len(self.group_order) != 3 or set(self.group_order) != allowed_groups:
                raise ValidationError(
                    {"group_order": "A protocol-v2 run needs each group exactly once."}
                )
        elif not self.group_order or not set(self.group_order).issubset(allowed_groups):
            raise ValidationError({"group_order": "The imported group order is invalid."})

        if self.current_group_position is not None and self.current_group_position > 2:
            raise ValidationError(
                {"current_group_position": "The group position must be between 0 and 2."}
            )

        required = self.tutorial_trials_required
        tutorial_order = self.tutorial_group_order or []
        if required == 0:
            if tutorial_order:
                raise ValidationError(
                    {"tutorial_group_order": "A grandfathered run cannot have a tutorial order."}
                )
        else:
            if not 5 <= required <= 10:
                raise ValidationError(
                    {"tutorial_trials_required": "Tutorial length must be between 5 and 10."}
                )
            if len(tutorial_order) != required:
                raise ValidationError(
                    {"tutorial_group_order": "The tutorial order must match its trial count."}
                )
            if (
                not set(tutorial_order).issubset(allowed_groups)
                or set(tutorial_order) != allowed_groups
            ):
                raise ValidationError(
                    {"tutorial_group_order": "The tutorial must contain all three groups."}
                )
            group_counts = [tutorial_order.count(group) for group in Group.values]
            if max(group_counts) - min(group_counts) > 1:
                raise ValidationError({"tutorial_group_order": "Tutorial groups must be balanced."})
            if any(left == right for left, right in zip(tutorial_order, tutorial_order[1:])):
                raise ValidationError(
                    {"tutorial_group_order": "Adjacent tutorial trials must use different groups."}
                )
        if self.tutorial_completed_trials > required:
            raise ValidationError(
                {"tutorial_completed_trials": "Tutorial progress exceeds its configured length."}
            )

    @property
    def total_trials(self) -> int:
        return self.trials_per_group * 3

    @property
    def current_group(self) -> int | None:
        if self.current_group_position is None:
            return None
        try:
            return int(self.group_order[self.current_group_position])
        except IndexError, TypeError, ValueError:
            return None

    @property
    def tutorial_complete(self) -> bool:
        return self.tutorial_completed_trials >= self.tutorial_trials_required

    def __str__(self) -> str:
        return f"Study run {self.pk}"


class GroupAttempt(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived legacy group"

    study_run = models.ForeignKey(
        StudyRun,
        on_delete=models.PROTECT,
        related_name="group_attempts",
    )
    position = models.PositiveSmallIntegerField()
    group = models.IntegerField(choices=Group.choices)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    completed_trials = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("study_run_id", "position")
        constraints = [
            models.UniqueConstraint(
                fields=("study_run", "position"),
                name="drugid_run_group_position_unique",
            ),
            models.UniqueConstraint(
                fields=("study_run", "group"),
                name="drugid_run_group_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=0, position__lte=2),
                name="drugid_group_position_range",
            ),
        ]

    def __str__(self) -> str:
        return f"Run {self.study_run_id}, group {self.group}"


class Drug(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Asset(models.Model):
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="assets")
    asset_url = models.CharField(max_length=200)
    group = models.IntegerField(choices=Group.choices)

    class Meta:
        ordering = ("group", "drug__name")
        constraints = [
            models.UniqueConstraint(
                fields=("drug", "group"),
                name="drugid_asset_drug_group_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.drug.name} ({self.get_group_display()})"


class Trial(models.Model):
    group_attempt = models.ForeignKey(
        GroupAttempt,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="trials",
    )
    group = models.IntegerField(choices=Group.choices)
    assets = models.ManyToManyField(Asset, related_name="trials")
    target = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="target_trials")
    time_limit_ms = models.PositiveIntegerField()
    trial_index = models.PositiveIntegerField(blank=True, null=True)
    asset_order = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("group_attempt_id", "trial_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("group_attempt", "trial_index"),
                condition=(
                    models.Q(group_attempt__isnull=False) & models.Q(trial_index__isnull=False)
                ),
                name="drugid_attempt_trial_index_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"Trial {self.pk}"


class TrialResult(models.Model):
    trial = models.OneToOneField(
        Trial,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="result",
    )
    # Raw legacy fields are intentionally retained for research provenance.
    time = models.CharField(max_length=20)
    selected = models.CharField(max_length=100, blank=True, null=True)
    correct = models.BooleanField()
    sequence_id = models.CharField(max_length=100)
    group_attempt = models.ForeignKey(
        GroupAttempt,
        on_delete=models.PROTECT,
        related_name="results",
    )
    group = models.IntegerField(choices=Group.choices)
    response_time_ms = models.PositiveIntegerField(blank=True, null=True)
    selected_asset = models.ForeignKey(
        Asset,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="selections",
    )
    timed_out = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("group_attempt_id", "id")

    def __str__(self) -> str:
        return f"Trial result {self.pk}"


class TutorialTrial(models.Model):
    """A practice trial, intentionally separate from measured study data."""

    study_run = models.ForeignKey(
        StudyRun,
        on_delete=models.PROTECT,
        related_name="tutorial_trials",
    )
    group = models.IntegerField(choices=Group.choices)
    assets = models.ManyToManyField(Asset, related_name="tutorial_trials")
    target = models.ForeignKey(
        Drug,
        on_delete=models.PROTECT,
        related_name="target_tutorial_trials",
    )
    time_limit_ms = models.PositiveIntegerField()
    sequence = models.PositiveSmallIntegerField()
    asset_order = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("study_run_id", "sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("study_run", "sequence"),
                name="drugid_run_tutorial_sequence_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"Tutorial trial {self.pk}"


class TutorialTrialResult(models.Model):
    trial = models.OneToOneField(
        TutorialTrial,
        on_delete=models.PROTECT,
        related_name="result",
    )
    selected_asset = models.ForeignKey(
        Asset,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="tutorial_selections",
    )
    response_time_ms = models.PositiveIntegerField()
    correct = models.BooleanField()
    timed_out = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("trial__study_run_id", "trial__sequence", "id")

    def __str__(self) -> str:
        return f"Tutorial trial result {self.pk}"


class MagicLink(models.Model):
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    email = models.EmailField(max_length=254)
    speciality = models.CharField(
        max_length=3,
        choices=Participant.SPECIALITY_CHOICES,
    )
    years_experience = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(80)],
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.PROTECT,
        related_name="magic_links",
    )
    study_run = models.ForeignKey(
        StudyRun,
        on_delete=models.PROTECT,
        related_name="magic_links",
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    delivery_failed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("email", "created_at"))]

    @property
    def is_usable(self) -> bool:
        return (
            self.used_at is None
            and self.delivery_failed_at is None
            and self.expires_at > timezone.now()
        )

    def __str__(self) -> str:
        return f"Magic link {self.pk}"
