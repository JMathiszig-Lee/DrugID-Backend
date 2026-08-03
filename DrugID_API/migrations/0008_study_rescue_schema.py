import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("DrugID_API", "0007_auto_20201018_1354"),
    ]

    operations = [
        migrations.RenameModel(old_name="Result", new_name="TrialResult"),
        migrations.RenameModel(old_name="Set", new_name="Trial"),
        migrations.RenameModel(old_name="Session", new_name="GroupAttempt"),
        migrations.RenameModel(old_name="User", new_name="Participant"),
        migrations.RenameField(
            model_name="groupattempt", old_name="user_id", new_name="participant"
        ),
        migrations.RenameField(
            model_name="groupattempt", old_name="last_group", new_name="group"
        ),
        migrations.AlterField(
            model_name="groupattempt",
            name="participant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="DrugID_API.participant",
            ),
        ),
        migrations.RenameField(model_name="asset", old_name="drug_id", new_name="drug"),
        migrations.RenameField(model_name="trial", old_name="asset_id", new_name="assets"),
        migrations.RenameField(
            model_name="trial", old_name="time_limit", new_name="time_limit_ms"
        ),
        migrations.RenameField(
            model_name="trialresult", old_name="set_id", new_name="trial"
        ),
        migrations.RenameField(
            model_name="trialresult", old_name="session_id", new_name="group_attempt"
        ),
        migrations.AddField(
            model_name="participant",
            name="account",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="participant",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="participant",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="participant",
            name="email",
            field=models.EmailField(max_length=254),
        ),
        migrations.AlterField(
            model_name="participant",
            name="years_experience",
            field=models.PositiveSmallIntegerField(
                null=True,
                validators=[django.core.validators.MaxValueValidator(80)],
            ),
        ),
        migrations.CreateModel(
            name="ExperimentConfiguration",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "trials_per_group",
                    models.PositiveSmallIntegerField(
                        default=50,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "choices_per_trial",
                    models.PositiveSmallIntegerField(
                        default=8,
                        validators=[
                            django.core.validators.MinValueValidator(2),
                            django.core.validators.MaxValueValidator(20),
                        ],
                    ),
                ),
                (
                    "time_limit_ms",
                    models.PositiveIntegerField(
                        default=3000,
                        validators=[django.core.validators.MinValueValidator(100)],
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "experiment configuration"},
        ),
        migrations.CreateModel(
            name="StudyRun",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("protocol_version", models.PositiveSmallIntegerField(default=2)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ready", "Ready"),
                            ("in_progress", "In progress"),
                            ("between_groups", "Between groups"),
                            ("completed", "Completed"),
                            ("archived", "Archived legacy run"),
                        ],
                        default="ready",
                        max_length=20,
                    ),
                ),
                ("group_order", models.JSONField(default=list)),
                ("order_inferred", models.BooleanField(default=False)),
                (
                    "trials_per_group",
                    models.PositiveSmallIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)]
                    ),
                ),
                (
                    "choices_per_trial",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(2),
                            django.core.validators.MaxValueValidator(20),
                        ]
                    ),
                ),
                (
                    "time_limit_ms",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(100)]
                    ),
                ),
                (
                    "current_group_position",
                    models.PositiveSmallIntegerField(default=0, null=True),
                ),
                ("completed_trials", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "participant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="study_runs",
                        to="DrugID_API.participant",
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddField(
            model_name="groupattempt",
            name="study_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="group_attempts",
                to="DrugID_API.studyrun",
            ),
        ),
        migrations.AddField(
            model_name="groupattempt",
            name="position",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="groupattempt",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("active", "Active"),
                    ("completed", "Completed"),
                    ("archived", "Archived legacy group"),
                ],
                default="pending",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="groupattempt",
            name="completed_trials",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="groupattempt",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="trial",
            name="group_attempt",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trials",
                to="DrugID_API.groupattempt",
            ),
        ),
        migrations.AddField(
            model_name="trial",
            name="trial_index",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trial",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="trial",
            name="time_limit_ms",
            field=models.PositiveIntegerField(),
        ),
        migrations.AddField(
            model_name="trialresult",
            name="response_time_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trialresult",
            name="selected_asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="selections",
                to="DrugID_API.asset",
            ),
        ),
        migrations.AddField(
            model_name="trialresult",
            name="timed_out",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="trialresult",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="trialresult",
            name="trial",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="result_rows",
                to="DrugID_API.trial",
            ),
        ),
        migrations.AlterField(
            model_name="trialresult",
            name="group_attempt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="results",
                to="DrugID_API.groupattempt",
            ),
        ),
        migrations.CreateModel(
            name="MagicLink",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("token_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("email", models.EmailField(max_length=254)),
                (
                    "speciality",
                    models.CharField(
                        choices=[
                            ("GAS", "Anaesthetics"),
                            ("A+E", "Emergency Medicine"),
                            ("ICM", "Intensive Care"),
                            ("OTH", "Other"),
                        ],
                        max_length=3,
                    ),
                ),
                (
                    "years_experience",
                    models.PositiveSmallIntegerField(
                        validators=[django.core.validators.MaxValueValidator(80)]
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "participant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="magic_links",
                        to="DrugID_API.participant",
                    ),
                ),
                (
                    "study_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="magic_links",
                        to="DrugID_API.studyrun",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(
                        fields=["email", "created_at"],
                        name="DrugID_API__email_7ab76f_idx",
                    )
                ],
            },
        ),
    ]
