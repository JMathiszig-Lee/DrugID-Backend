from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, F, Q
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, Throttled, ValidationError

from DrugID_API.models import (
    Asset,
    ExperimentConfiguration,
    Group,
    GroupAttempt,
    MagicLink,
    Participant,
    StudyRun,
    Trial,
    TrialResult,
    TutorialTrial,
    TutorialTrialResult,
)


class StudyConflict(APIException):
    status_code = 409
    default_code = "study_conflict"
    default_detail = "The study is not in a state where that action can be performed."


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _tutorial_group_schedule(trial_count: int) -> list[int]:
    """Return a balanced mixed-style schedule with no adjacent repeats."""

    randomizer = secrets.SystemRandom()
    groups = list(Group.values)
    complete_cycles, remainder = divmod(trial_count, len(groups))
    schedule: list[int] = []

    for _ in range(complete_cycles):
        cycle = randomizer.sample(groups, k=len(groups))
        if schedule and cycle[0] == schedule[-1]:
            swap_index = next(
                index for index, group in enumerate(cycle[1:], start=1) if group != schedule[-1]
            )
            cycle[0], cycle[swap_index] = cycle[swap_index], cycle[0]
        schedule.extend(cycle)

    if remainder:
        tail = randomizer.sample(groups, k=remainder)
        if len(tail) == 1 and schedule and tail[0] == schedule[-1]:
            tail = [randomizer.choice([group for group in groups if group != schedule[-1]])]
        elif schedule and tail[0] == schedule[-1]:
            tail[0], tail[1] = tail[1], tail[0]
        schedule.extend(tail)

    return schedule


def _create_protocol_v2_run(participant: Participant) -> StudyRun:
    configuration, _ = ExperimentConfiguration.objects.select_for_update().get_or_create(pk=1)
    group_order = secrets.SystemRandom().sample(list(Group.values), k=3)
    tutorial_group_order = _tutorial_group_schedule(configuration.tutorial_trials)
    run = StudyRun.objects.create(
        participant=participant,
        protocol_version=2,
        status=StudyRun.Status.READY,
        group_order=group_order,
        order_inferred=False,
        trials_per_group=configuration.trials_per_group,
        choices_per_trial=configuration.choices_per_trial,
        time_limit_ms=configuration.time_limit_ms,
        tutorial_trials_required=configuration.tutorial_trials,
        tutorial_group_order=tutorial_group_order,
        current_group_position=0,
    )
    GroupAttempt.objects.bulk_create(
        [
            GroupAttempt(
                study_run=run,
                position=position,
                group=group,
                status=GroupAttempt.Status.PENDING,
            )
            for position, group in enumerate(group_order)
        ]
    )
    return run


def request_magic_link(*, email: str, speciality: str, years_experience: int) -> str:
    """Register a participant/run and send a one-use authentication link.

    A repeated request reuses the participant's original protocol-v2 run,
    including a completed run, so its assigned ordering never changes.
    """

    raw_token = secrets.token_urlsafe(32)
    now = timezone.now()

    with transaction.atomic():
        participant = Participant.objects.filter(email__iexact=email).first()
        if participant is None:
            participant, _ = Participant.objects.get_or_create(
                email=email,
                defaults={
                    "speciality": speciality,
                    "years_experience": years_experience,
                },
            )
        participant = Participant.objects.select_for_update().get(pk=participant.pk)

        run = (
            StudyRun.objects.select_for_update()
            .filter(participant=participant, protocol_version=2)
            .order_by("created_at", "id")
            .first()
        )
        if run is None:
            run = _create_protocol_v2_run(participant)

        issuance_window_start = now - timedelta(seconds=settings.MAGIC_LINK_EMAIL_WINDOW_SECONDS)
        recent_links = MagicLink.objects.filter(
            email=participant.email,
            created_at__gte=issuance_window_start,
            delivery_failed_at__isnull=True,
        ).order_by("created_at")
        if recent_links.count() >= settings.MAGIC_LINK_EMAIL_LIMIT:
            oldest = recent_links.first()
            retry_at = oldest.created_at + timedelta(
                seconds=settings.MAGIC_LINK_EMAIL_WINDOW_SECONDS
            )
            wait_seconds = max(1, int((retry_at - now).total_seconds()))
            raise Throttled(
                wait=wait_seconds,
                detail="Too many sign-in links have been requested. Please try again later.",
            )
        magic_link = MagicLink.objects.create(
            token_hash=token_digest(raw_token),
            email=participant.email,
            speciality=participant.speciality,
            years_experience=participant.years_experience,
            participant=participant,
            study_run=run,
            expires_at=now + timedelta(seconds=settings.MAGIC_LINK_TTL_SECONDS),
        )

    magic_link_url = f"{settings.PUBLIC_APP_URL}/verify#token={quote(raw_token, safe='')}"
    try:
        send_mail(
            subject="Your Ampoule Study sign-in link",
            message=(
                "Open this one-use link to continue the Ampoule Study. "
                f"It expires in {settings.MAGIC_LINK_TTL_SECONDS // 60} minutes.\n\n"
                f"{magic_link_url}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[participant.email],
            fail_silently=False,
        )
    except Exception:
        MagicLink.objects.filter(pk=magic_link.pk, used_at__isnull=True).update(
            delivery_failed_at=timezone.now()
        )
        raise
    return magic_link_url


def verify_magic_link(request, raw_token: str) -> StudyRun:
    digest = token_digest(raw_token)
    now = timezone.now()

    with transaction.atomic():
        link = (
            MagicLink.objects.select_for_update()
            .select_related("participant__account", "study_run")
            .filter(token_hash=digest)
            .first()
        )
        if (
            link is None
            or link.used_at is not None
            or link.delivery_failed_at is not None
            or link.expires_at <= now
        ):
            raise ValidationError({"token": "This magic link is invalid or expired."})
        if link.study_run.participant_id != link.participant_id:
            raise ValidationError({"token": "This magic link is invalid or expired."})

        participant = link.participant
        account = participant.account
        if account is None:
            UserModel = get_user_model()
            account = UserModel.objects.create_user(
                username=f"participant-{uuid.uuid4().hex}",
                email=participant.email,
                password=None,
            )
            participant.account = account
            participant.save(update_fields=("account",))

        link.used_at = now
        link.save(update_fields=("used_at",))
        login(request, account, backend="django.contrib.auth.backends.ModelBackend")

    return link.study_run


def study_run_for_user(user, *, lock: bool = False) -> StudyRun:
    queryset = StudyRun.objects.select_related("participant")
    if lock:
        queryset = queryset.select_for_update()
    run = (
        queryset.filter(participant__account=user, protocol_version=2)
        .order_by("created_at", "id")
        .first()
    )
    if run is None:
        raise NotFound("No study session is registered for this account.")
    return run


def current_attempt(run: StudyRun, *, lock: bool = False) -> GroupAttempt | None:
    if run.current_group_position is None:
        return None
    queryset = run.group_attempts
    if lock:
        queryset = queryset.select_for_update()
    return queryset.filter(position=run.current_group_position).first()


def _available_assets(group: int) -> list[Asset]:
    eligible_drug_ids = (
        Asset.objects.values("drug_id")
        .annotate(group_count=Count("group", distinct=True))
        .filter(group_count=len(Group.values))
        .values("drug_id")
    )
    return list(
        Asset.objects.filter(group=group, drug_id__in=eligible_drug_ids)
        .select_related("drug")
        .order_by("id")
    )


def study_status(run: StudyRun) -> dict:
    attempt = current_attempt(run)
    tutorial_active = run.tutorial_trials.filter(result__isnull=True).exists()
    in_tutorial = not run.tutorial_complete
    group_value = None if in_tutorial else run.current_group
    active_trial = False
    completed_in_group = 0
    if attempt is not None and not in_tutorial:
        completed_in_group = attempt.completed_trials
        active_trial = attempt.trials.filter(result__isnull=True).exists()

    return {
        "id": run.pk,
        "phase": "tutorial" if in_tutorial else run.status,
        "group_index": (
            run.current_group_position + 1
            if not in_tutorial and run.current_group_position is not None
            else None
        ),
        "groups_total": 3,
        "current_group_name": Group(group_value).label if group_value is not None else None,
        "completed_trials": run.completed_trials,
        "total_trials": run.total_trials,
        "completed_in_group": completed_in_group,
        "trials_per_group": run.trials_per_group,
        "choices_per_trial": run.choices_per_trial,
        "time_limit_ms": run.time_limit_ms,
        "has_active_trial": active_trial,
        "tutorial": {
            "required": run.tutorial_trials_required,
            "complete": run.tutorial_complete,
            "completed_trials": run.tutorial_completed_trials,
            "total_trials": run.tutorial_trials_required,
            "has_active_trial": tutorial_active,
        },
    }


def next_tutorial_trial_for_user(user) -> tuple[StudyRun, TutorialTrial | None]:
    with transaction.atomic():
        run = study_run_for_user(user, lock=True)
        if run.tutorial_complete:
            return run, None
        if run.status != StudyRun.Status.READY:
            raise StudyConflict("The tutorial is not available for this study session.")

        outstanding = (
            run.tutorial_trials.filter(result__isnull=True)
            .select_related("target")
            .prefetch_related("assets__drug")
            .order_by("sequence", "id")
            .first()
        )
        if outstanding is not None:
            return run, outstanding

        sequence = run.tutorial_completed_trials + 1
        try:
            group = int(run.tutorial_group_order[sequence - 1])
        except IndexError, TypeError, ValueError:
            raise StudyConflict("The tutorial schedule could not be resolved.") from None

        available_assets = _available_assets(group)
        if len(available_assets) < run.choices_per_trial:
            raise StudyConflict("There are not enough configured ampoule images for this group.")

        randomizer = secrets.SystemRandom()
        choices = randomizer.sample(available_assets, k=run.choices_per_trial)
        target_asset = randomizer.choice(choices)
        trial = TutorialTrial.objects.create(
            study_run=run,
            group=group,
            target=target_asset.drug,
            time_limit_ms=run.time_limit_ms,
            sequence=sequence,
            asset_order=[asset.pk for asset in choices],
        )
        trial.assets.set(choices)
        return run, trial


def next_trial_for_user(user) -> tuple[StudyRun, Trial | None]:
    with transaction.atomic():
        run = study_run_for_user(user, lock=True)
        if not run.tutorial_complete:
            raise StudyConflict("Complete the tutorial before starting the experiment.")
        if run.status == StudyRun.Status.COMPLETED:
            return run, None

        attempt = current_attempt(run, lock=True)
        if attempt is None:
            raise StudyConflict("The current group could not be resolved.")

        outstanding = (
            attempt.trials.filter(result__isnull=True)
            .select_related("target")
            .prefetch_related("assets__drug")
            .order_by("trial_index", "id")
            .first()
        )
        if outstanding is not None:
            return run, outstanding

        if attempt.completed_trials >= run.trials_per_group:
            raise StudyConflict("This group is already complete.")

        available_assets = _available_assets(attempt.group)
        if len(available_assets) < run.choices_per_trial:
            raise StudyConflict("There are not enough configured ampoule images for this group.")

        randomizer = secrets.SystemRandom()
        choices = randomizer.sample(available_assets, k=run.choices_per_trial)
        target_asset = randomizer.choice(choices)
        trial = Trial.objects.create(
            group_attempt=attempt,
            group=attempt.group,
            target=target_asset.drug,
            time_limit_ms=run.time_limit_ms,
            trial_index=attempt.completed_trials + 1,
            asset_order=[asset.pk for asset in choices],
        )
        trial.assets.set(choices)

        if attempt.status != GroupAttempt.Status.ACTIVE:
            attempt.status = GroupAttempt.Status.ACTIVE
            attempt.save(update_fields=("status",))
        if run.status != StudyRun.Status.IN_PROGRESS:
            run.status = StudyRun.Status.IN_PROGRESS
            run.save(update_fields=("status",))
        return run, trial


def submit_tutorial_trial_result(
    *, user, tutorial_trial_id: int, selected_asset_id: int | None, response_time_ms: int
) -> tuple[TutorialTrialResult, StudyRun]:
    with transaction.atomic():
        trial = (
            TutorialTrial.objects.select_for_update()
            .select_related("study_run__participant", "target")
            .filter(
                pk=tutorial_trial_id,
                study_run__participant__account=user,
                study_run__protocol_version=2,
            )
            .first()
        )
        if trial is None:
            raise NotFound("Tutorial trial not found.")

        existing = TutorialTrialResult.objects.filter(trial=trial).first()
        if existing is not None:
            return existing, trial.study_run

        run = StudyRun.objects.select_for_update().get(pk=trial.study_run_id)
        if (
            run.status != StudyRun.Status.READY
            or run.tutorial_complete
            or trial.sequence != run.tutorial_completed_trials + 1
        ):
            raise StudyConflict("This is not the active tutorial trial.")

        selected_asset = None
        if selected_asset_id is not None:
            selected_asset = (
                trial.assets.select_related("drug").filter(pk=selected_asset_id).first()
            )
            if selected_asset is None:
                raise ValidationError(
                    {"selected_asset_id": "The selected ampoule was not offered."}
                )
            if response_time_ms >= trial.time_limit_ms:
                selected_asset = None

        recorded_response_time = (
            response_time_ms if selected_asset is not None else trial.time_limit_ms
        )
        result = TutorialTrialResult.objects.create(
            trial=trial,
            selected_asset=selected_asset,
            response_time_ms=recorded_response_time,
            correct=bool(selected_asset and selected_asset.drug_id == trial.target_id),
            timed_out=selected_asset is None,
        )

        run.tutorial_completed_trials += 1
        update_fields = ["tutorial_completed_trials"]
        if run.tutorial_complete:
            run.tutorial_completed_at = timezone.now()
            update_fields.append("tutorial_completed_at")
        run.save(update_fields=update_fields)
        return result, run


def submit_trial_result(
    *, user, trial_id: int, selected_asset_id: int | None, response_time_ms: int
) -> tuple[TrialResult, StudyRun]:
    with transaction.atomic():
        trial = (
            Trial.objects.select_for_update()
            .select_related("group_attempt__study_run__participant", "target")
            .filter(
                pk=trial_id,
                group_attempt__study_run__participant__account=user,
                group_attempt__study_run__protocol_version=2,
            )
            .first()
        )
        if trial is None or trial.group_attempt_id is None:
            raise NotFound("Trial not found.")

        run = StudyRun.objects.select_for_update().get(pk=trial.group_attempt.study_run_id)
        if not run.tutorial_complete:
            raise StudyConflict("Complete the tutorial before submitting experiment results.")

        existing = TrialResult.objects.filter(trial=trial).first()
        if existing is not None:
            return existing, run

        attempt = GroupAttempt.objects.select_for_update().get(pk=trial.group_attempt_id)
        if (
            run.status != StudyRun.Status.IN_PROGRESS
            or run.current_group_position != attempt.position
            or attempt.status != GroupAttempt.Status.ACTIVE
        ):
            raise StudyConflict("This is not the active trial for the study session.")

        selected_asset = None
        if selected_asset_id is not None:
            selected_asset = (
                trial.assets.select_related("drug").filter(pk=selected_asset_id).first()
            )
            if selected_asset is None:
                raise ValidationError(
                    {"selected_asset_id": "The selected ampoule was not offered."}
                )
            if response_time_ms >= trial.time_limit_ms:
                # A click racing the client timer is still authoritatively a timeout.
                selected_asset = None

        recorded_response_time = (
            response_time_ms if selected_asset is not None else trial.time_limit_ms
        )

        correct = bool(selected_asset is not None and selected_asset.drug_id == trial.target_id)
        result = TrialResult.objects.create(
            trial=trial,
            time=str(recorded_response_time),
            selected=selected_asset.drug.name if selected_asset else None,
            correct=correct,
            sequence_id=str(trial.trial_index),
            group_attempt=attempt,
            group=trial.group,
            response_time_ms=recorded_response_time,
            selected_asset=selected_asset,
            timed_out=selected_asset is None,
        )

        attempt.completed_trials += 1
        run.completed_trials += 1
        run_fields = ["completed_trials", "status", "current_group_position"]

        if attempt.completed_trials >= run.trials_per_group:
            attempt.status = GroupAttempt.Status.COMPLETED
            if attempt.position == 2:
                run.status = StudyRun.Status.COMPLETED
                run.current_group_position = None
                run.completed_at = timezone.now()
                run_fields.append("completed_at")
            else:
                run.status = StudyRun.Status.BETWEEN_GROUPS
                run.current_group_position = attempt.position + 1

        attempt.save(update_fields=("completed_trials", "status"))
        run.save(update_fields=tuple(run_fields))
        return result, run


def outstanding_asset_for_user(user, asset_id: int) -> Asset:
    """Return an asset only while it belongs to this user's current trial."""

    main_trial = Q(
        trials__group_attempt__study_run__participant__account=user,
        trials__group_attempt__study_run__protocol_version=2,
        trials__group_attempt__study_run__status=StudyRun.Status.IN_PROGRESS,
        trials__group_attempt__study_run__current_group_position=F(
            "trials__group_attempt__position"
        ),
        trials__group_attempt__status=GroupAttempt.Status.ACTIVE,
        trials__result__isnull=True,
    )
    tutorial_trial = Q(
        tutorial_trials__study_run__participant__account=user,
        tutorial_trials__study_run__protocol_version=2,
        tutorial_trials__study_run__status=StudyRun.Status.READY,
        tutorial_trials__study_run__tutorial_completed_trials__lt=F(
            "tutorial_trials__study_run__tutorial_trials_required"
        ),
        tutorial_trials__sequence=F("tutorial_trials__study_run__tutorial_completed_trials") + 1,
        tutorial_trials__result__isnull=True,
    )
    asset = Asset.objects.filter(Q(pk=asset_id) & (main_trial | tutorial_trial)).distinct().first()
    if asset is None:
        raise NotFound("Study asset not found.")
    return asset


def resolve_study_asset_path(asset: Asset) -> Path:
    """Resolve an asset below the private root without permitting path traversal."""

    try:
        root = Path(settings.STUDY_ASSET_ROOT).resolve()
        relative_path = Path(asset.asset_url)
        if relative_path.is_absolute():
            raise NotFound("Study asset not found.")
        asset_path = (root / relative_path).resolve(strict=True)
    except OSError, RuntimeError, ValueError:
        raise NotFound("Study asset not found.") from None

    if not asset_path.is_relative_to(root) or not asset_path.is_file():
        raise NotFound("Study asset not found.")
    return asset_path


def trial_payload(trial: Trial) -> dict:
    assets_by_id = {asset.pk: asset for asset in trial.assets.select_related("drug").order_by("id")}
    assets = [assets_by_id[asset_id] for asset_id in trial.asset_order if asset_id in assets_by_id]
    if len(assets) != len(assets_by_id):
        assets = list(assets_by_id.values())
    return {
        "id": trial.pk,
        "trial_type": "study",
        "storage_key": f"study:{trial.pk}",
        "sequence": trial.trial_index,
        "sequence_total": trial.group_attempt.study_run.trials_per_group,
        "group_index": trial.group_attempt.position + 1,
        "style_name": trial.get_group_display(),
        "target_drug": trial.target.name,
        "time_limit_ms": trial.time_limit_ms,
        "ampoules": [
            {
                "id": asset.pk,
                "image_url": reverse("study-asset-image", kwargs={"asset_id": asset.pk}),
            }
            for asset in assets
        ],
    }


def tutorial_trial_payload(trial: TutorialTrial) -> dict:
    assets_by_id = {asset.pk: asset for asset in trial.assets.select_related("drug").order_by("id")}
    assets = [assets_by_id[asset_id] for asset_id in trial.asset_order if asset_id in assets_by_id]
    if len(assets) != len(assets_by_id):
        assets = list(assets_by_id.values())
    return {
        "id": trial.pk,
        "trial_type": "tutorial",
        "storage_key": f"tutorial:{trial.pk}",
        "sequence": trial.sequence,
        "sequence_total": trial.study_run.tutorial_trials_required,
        "group_index": None,
        "style_name": trial.get_group_display(),
        "target_drug": trial.target.name,
        "time_limit_ms": trial.time_limit_ms,
        "ampoules": [
            {
                "id": asset.pk,
                "image_url": reverse("study-asset-image", kwargs={"asset_id": asset.pk}),
            }
            for asset in assets
        ],
    }
