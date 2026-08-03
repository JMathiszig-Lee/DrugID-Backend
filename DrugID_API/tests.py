from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.contrib import admin
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from DrugID_API.actions import export_trial_results_csv
from DrugID_API.models import (
    Asset,
    Drug,
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
from DrugID_API.services import request_magic_link, request_returning_magic_link


@override_settings(
    DEBUG=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_URL="http://testserver",
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    MAGIC_LINK_TTL_SECONDS=900,
    SHOW_DEBUG_MAGIC_LINK=True,
)
class StudyApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        configuration = ExperimentConfiguration.load()
        configuration.trials_per_group = 1
        configuration.choices_per_trial = 2
        configuration.time_limit_ms = 1000
        configuration.tutorial_trials = 6
        configuration.save()
        self._create_assets()

    def _create_assets(self, count=4):
        drugs = [Drug.objects.create(name=f"drug-{index}") for index in range(count)]
        for group in Group.values:
            for drug in drugs:
                Asset.objects.create(
                    drug=drug,
                    group=group,
                    asset_url=f"group-{group}/{drug.name}.png",
                )

    def register(self, client, *, email="participant@example.test", **overrides):
        payload = {
            "email": email,
            "speciality": "GAS",
            "years_experience": 7,
        }
        payload.update(overrides)
        response = client.post(reverse("magic-link-request"), payload, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        link = response.data["debug_magic_link"]
        parsed = urlsplit(link)
        self.assertEqual(parsed.query, "")
        token = parse_qs(parsed.fragment)["token"][0]
        return token, Participant.objects.get(email=email)

    def request_returning_link(self, client, *, email="participant@example.test"):
        response = client.post(
            reverse("returning-magic-link-request"),
            {"email": email},
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        link = response.data.get("debug_magic_link")
        if link is None:
            return response, None
        parsed = urlsplit(link)
        self.assertEqual(parsed.query, "")
        return response, parse_qs(parsed.fragment)["token"][0]

    def verify(self, client, token, *, complete_tutorial=True):
        response = client.post(reverse("magic-link-verify"), {"token": token}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("sessionid", client.cookies)
        self.assertIn("csrftoken", client.cookies)
        if complete_tutorial:
            run = StudyRun.objects.get(pk=response.data["session"]["id"])
            run.tutorial_completed_trials = run.tutorial_trials_required
            run.tutorial_completed_at = timezone.now()
            run.save(update_fields=("tutorial_completed_trials", "tutorial_completed_at"))
            response.data["session"] = client.get(reverse("study-session")).data
        return response, client.cookies["csrftoken"].value

    def next_trial(self, client, csrf):
        return client.post(reverse("next-trial"), HTTP_X_CSRFTOKEN=csrf)

    def next_tutorial_trial(self, client, csrf):
        return client.post(reverse("next-tutorial-trial"), HTTP_X_CSRFTOKEN=csrf)

    def submit(self, client, csrf, trial_id, selected_asset_id, response_time_ms=250):
        return client.post(
            reverse("trial-result", kwargs={"trial_id": trial_id}),
            {
                "selected_asset_id": selected_asset_id,
                "response_time_ms": response_time_ms,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

    def submit_tutorial(
        self,
        client,
        csrf,
        tutorial_trial_id,
        selected_asset_id,
        response_time_ms=250,
    ):
        return client.post(
            reverse(
                "tutorial-trial-result",
                kwargs={"tutorial_trial_id": tutorial_trial_id},
            ),
            {
                "selected_asset_id": selected_asset_id,
                "response_time_ms": response_time_ms,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )


class MagicLinkTests(StudyApiTestCase):
    @override_settings(SHOW_DEBUG_MAGIC_LINK=False)
    def test_debug_link_requires_explicit_opt_in(self):
        client = APIClient()
        response = client.post(
            reverse("magic-link-request"),
            {
                "email": "no-debug-link@example.test",
                "speciality": "GAS",
                "years_experience": 4,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("debug_magic_link", response.data)

        returning = client.post(
            reverse("returning-magic-link-request"),
            {"email": "no-debug-link@example.test"},
            format="json",
        )
        self.assertEqual(returning.status_code, 202)
        self.assertNotIn("debug_magic_link", returning.data)

    def test_returning_debug_link_is_only_exposed_for_a_known_email(self):
        client = APIClient()
        _, participant = self.register(client, email="known-debug@example.test")

        known, known_token = self.request_returning_link(client, email=participant.email)
        unknown, unknown_token = self.request_returning_link(
            client,
            email="unknown-debug@example.test",
        )

        self.assertIn("debug_magic_link", known.data)
        self.assertIsNotNone(known_token)
        self.assertNotIn("debug_magic_link", unknown.data)
        self.assertIsNone(unknown_token)

    def test_registration_fixes_full_order_and_snapshots_configuration(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client)
        run = StudyRun.objects.get(participant=participant, protocol_version=2)

        self.assertCountEqual(run.group_order, Group.values)
        self.assertEqual(len(run.group_order), 3)
        self.assertEqual(run.status, StudyRun.Status.READY)
        self.assertEqual(run.trials_per_group, 1)
        self.assertEqual(run.choices_per_trial, 2)
        self.assertEqual(run.time_limit_ms, 1000)
        self.assertEqual(run.tutorial_trials_required, 6)
        self.assertEqual(len(run.tutorial_group_order), 6)
        self.assertEqual(
            {group: run.tutorial_group_order.count(group) for group in Group.values},
            {group: 2 for group in Group.values},
        )
        self.assertFalse(
            any(
                left == right
                for left, right in zip(
                    run.tutorial_group_order,
                    run.tutorial_group_order[1:],
                )
            )
        )
        self.assertEqual(list(run.group_attempts.values_list("group", flat=True)), run.group_order)

        magic_link = MagicLink.objects.get(participant=participant)
        self.assertNotEqual(magic_link.token_hash, token)
        self.assertEqual(len(magic_link.token_hash), 64)
        self.assertEqual(magic_link.study_run, run)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("#token=", mail.outbox[0].body)

    def test_registration_balances_every_supported_tutorial_length(self):
        expected_sorted_counts = {
            5: [1, 2, 2],
            6: [2, 2, 2],
            7: [2, 2, 3],
            8: [2, 3, 3],
            9: [3, 3, 3],
            10: [3, 3, 4],
        }

        for tutorial_trials, expected_counts in expected_sorted_counts.items():
            with self.subTest(tutorial_trials=tutorial_trials):
                configuration = ExperimentConfiguration.load()
                configuration.tutorial_trials = tutorial_trials
                configuration.save()
                cache.clear()

                _, participant = self.register(
                    APIClient(),
                    email=f"tutorial-{tutorial_trials}@example.test",
                )
                run = participant.study_runs.get(protocol_version=2)
                counts = sorted(run.tutorial_group_order.count(group) for group in Group.values)

                self.assertEqual(run.tutorial_trials_required, tutorial_trials)
                self.assertEqual(len(run.tutorial_group_order), tutorial_trials)
                self.assertEqual(set(run.tutorial_group_order), set(Group.values))
                self.assertEqual(counts, expected_counts)
                self.assertFalse(
                    any(
                        left == right
                        for left, right in zip(
                            run.tutorial_group_order,
                            run.tutorial_group_order[1:],
                        )
                    )
                )

    def test_registration_rejects_a_case_insensitive_duplicate_with_email_error(self):
        client = APIClient(enforce_csrf_checks=True)
        _, participant = self.register(client)
        run = participant.study_runs.get(protocol_version=2)

        response = client.post(
            reverse("magic-link-request"),
            {
                "email": " Participant@Example.TEST ",
                "speciality": "ICM",
                "years_experience": 30,
            },
            format="json",
        )

        participant.refresh_from_db()
        run.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            str(response.data["email"]),
            "This email is already registered. Request a returning-participant link instead.",
        )
        self.assertEqual(Participant.objects.count(), 1)
        self.assertEqual(StudyRun.objects.filter(participant=participant).count(), 1)
        self.assertEqual(participant.speciality, "GAS")
        self.assertEqual(participant.years_experience, 7)
        self.assertEqual(MagicLink.objects.filter(participant=participant).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_returning_request_reuses_completed_run_order_and_demographics(self):
        client = APIClient(enforce_csrf_checks=True)
        _, participant = self.register(client)
        run = participant.study_runs.get(protocol_version=2)
        original_order = list(run.group_order)
        original_tutorial_order = list(run.tutorial_group_order)

        run.status = StudyRun.Status.COMPLETED
        run.current_group_position = None
        run.completed_trials = run.total_trials
        run.completed_at = timezone.now()
        run.save(
            update_fields=(
                "status",
                "current_group_position",
                "completed_trials",
                "completed_at",
            )
        )
        configuration = ExperimentConfiguration.load()
        configuration.trials_per_group = 9
        configuration.tutorial_trials = 10
        configuration.save()

        response, token = self.request_returning_link(client, email="PARTICIPANT@example.test")

        participant.refresh_from_db()
        run.refresh_from_db()
        self.assertIsNotNone(token)
        self.assertEqual(
            response.data["detail"],
            ("If this address is registered, a returning-participant link has been sent."),
        )
        self.assertEqual(StudyRun.objects.filter(participant=participant).count(), 1)
        self.assertEqual(run.status, StudyRun.Status.COMPLETED)
        self.assertEqual(run.group_order, original_order)
        self.assertEqual(run.tutorial_group_order, original_tutorial_order)
        self.assertEqual(run.tutorial_trials_required, 6)
        self.assertEqual(run.trials_per_group, 1)
        self.assertEqual(participant.speciality, "GAS")
        self.assertEqual(participant.years_experience, 7)
        returning_link = MagicLink.objects.filter(participant=participant).latest("created_at")
        self.assertEqual(returning_link.study_run, run)
        self.assertEqual(returning_link.speciality, "GAS")
        self.assertEqual(returning_link.years_experience, 7)

        verified, _ = self.verify(APIClient(enforce_csrf_checks=True), token)
        self.assertEqual(verified.data["session"]["id"], run.pk)
        self.assertEqual(verified.data["session"]["phase"], "completed")

    @override_settings(SHOW_DEBUG_MAGIC_LINK=False)
    def test_returning_request_is_generic_and_unknown_email_creates_nothing(self):
        client = APIClient(enforce_csrf_checks=True)
        with self.settings(SHOW_DEBUG_MAGIC_LINK=True):
            _, participant = self.register(client, email="privacy@example.test")
        expected = {
            "detail": "If this address is registered, a returning-participant link has been sent."
        }

        existing = client.post(
            reverse("returning-magic-link-request"),
            {"email": "PRIVACY@example.test"},
            format="json",
        )
        missing = client.post(
            reverse("returning-magic-link-request"),
            {"email": "absent@example.test"},
            format="json",
        )

        self.assertEqual(existing.status_code, 202)
        self.assertEqual(missing.status_code, 202)
        self.assertEqual(existing.data, expected)
        self.assertEqual(missing.data, expected)
        self.assertEqual(Participant.objects.count(), 1)
        self.assertFalse(Participant.objects.filter(email="absent@example.test").exists())
        self.assertEqual(StudyRun.objects.count(), 1)
        self.assertEqual(MagicLink.objects.filter(participant=participant).count(), 2)
        self.assertEqual(len(mail.outbox), 2)

    def test_registration_and_returning_links_are_independently_usable(self):
        first_client = APIClient(enforce_csrf_checks=True)
        first_token, participant = self.register(first_client)
        _, returning_token = self.request_returning_link(first_client, email=participant.email)
        self.assertIsNotNone(returning_token)

        first_response, _ = self.verify(first_client, first_token)
        second_client = APIClient(enforce_csrf_checks=True)
        second_response, _ = self.verify(second_client, returning_token)

        self.assertEqual(
            first_response.data["session"]["id"], second_response.data["session"]["id"]
        )
        self.assertEqual(
            MagicLink.objects.filter(participant=participant, used_at__isnull=False).count(), 2
        )

    def test_returning_request_respects_database_email_issuance_limit(self):
        client = APIClient(enforce_csrf_checks=True)
        _, participant = self.register(client)
        self.request_returning_link(client, email=participant.email)
        self.request_returning_link(client, email=participant.email)

        limited = client.post(
            reverse("returning-magic-link-request"),
            {"email": participant.email},
            format="json",
        )
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(MagicLink.objects.filter(participant=participant).count(), 3)

    def test_delivery_failure_does_not_consume_email_quota(self):
        details = {
            "email": "delivery-failure@example.test",
            "speciality": "GAS",
            "years_experience": 5,
        }
        with mock.patch("DrugID_API.services.send_mail", side_effect=RuntimeError("smtp")):
            with self.assertRaises(RuntimeError):
                request_magic_link(**details)

        failed_link = MagicLink.objects.get(email=details["email"])
        self.assertIsNotNone(failed_link.delivery_failed_at)
        with mock.patch("DrugID_API.services.send_mail", return_value=1):
            recovery_link = request_returning_magic_link(email=details["email"].upper())
        self.assertIsNotNone(recovery_link)
        self.assertEqual(Participant.objects.filter(email=details["email"]).count(), 1)
        self.assertEqual(StudyRun.objects.count(), 1)
        self.assertEqual(
            MagicLink.objects.filter(
                email=details["email"], delivery_failed_at__isnull=True
            ).count(),
            1,
        )

    def test_verify_creates_unusable_auth_account_and_replay_fails(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client)
        response, _ = self.verify(client, token)

        participant.refresh_from_db()
        self.assertIsNotNone(participant.account_id)
        self.assertFalse(participant.account.has_usable_password())
        self.assertEqual(response.data["session"]["phase"], "ready")

        replay_client = APIClient(enforce_csrf_checks=True)
        replay = replay_client.post(reverse("magic-link-verify"), {"token": token}, format="json")
        self.assertEqual(replay.status_code, 400)

    def test_expired_link_is_rejected_without_creating_account(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client)
        MagicLink.objects.filter(participant=participant).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = client.post(reverse("magic-link-verify"), {"token": token}, format="json")
        self.assertEqual(response.status_code, 400)
        participant.refresh_from_db()
        self.assertIsNone(participant.account_id)

    def test_bootstrap_endpoints_ignore_existing_session_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client)
        self.verify(client, token)

        self.assertEqual(client.post(reverse("logout")).status_code, 403)

        registration = client.post(
            reverse("magic-link-request"),
            {
                "email": "new-bootstrap@example.test",
                "speciality": "ICM",
                "years_experience": 2,
            },
            format="json",
        )
        returning = client.post(
            reverse("returning-magic-link-request"),
            {"email": participant.email},
            format="json",
        )

        self.assertEqual(registration.status_code, 202)
        self.assertEqual(returning.status_code, 202)


class AuthenticationAndIsolationTests(StudyApiTestCase):
    def test_study_requires_login_and_csrf_for_mutation(self):
        client = APIClient(enforce_csrf_checks=True)
        missing_session = client.get(reverse("study-session"))
        self.assertEqual(missing_session.status_code, 401)
        self.assertEqual(missing_session["WWW-Authenticate"], "Session")
        token, _ = self.register(client)
        _, csrf = self.verify(client, token)

        self.assertEqual(client.get(reverse("study-session")).status_code, 200)
        self.assertEqual(client.post(reverse("next-trial")).status_code, 403)
        self.assertEqual(self.next_trial(client, csrf).status_code, 200)

    def test_participant_cannot_submit_another_participants_trial(self):
        first = APIClient(enforce_csrf_checks=True)
        token, _ = self.register(first, email="first@example.test")
        _, first_csrf = self.verify(first, token)
        trial_id = self.next_trial(first, first_csrf).data["trial"]["id"]

        second = APIClient(enforce_csrf_checks=True)
        token, _ = self.register(second, email="second@example.test")
        _, second_csrf = self.verify(second, token)
        response = self.submit(second, second_csrf, trial_id, None)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(TrialResult.objects.filter(trial_id=trial_id).exists())

    def test_private_asset_is_only_available_for_the_current_outstanding_trial(self):
        client = APIClient(enforce_csrf_checks=True)
        token, _ = self.register(client, email="image-owner@example.test")
        _, csrf = self.verify(client, token)
        trial_data = self.next_trial(client, csrf).data["trial"]
        trial = Trial.objects.get(pk=trial_data["id"])
        asset = trial.assets.select_related("drug").get(pk=trial_data["ampoules"][0]["id"])
        image_url = reverse("study-asset-image", kwargs={"asset_id": asset.pk})

        with TemporaryDirectory() as temporary_directory:
            asset_root = Path(temporary_directory) / "private-assets"
            image_path = asset_root / asset.asset_url
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"private-study-image")

            with self.settings(STUDY_ASSET_ROOT=asset_root):
                anonymous = APIClient().get(image_url)
                self.assertEqual(anonymous.status_code, 401)

                other_client = APIClient(enforce_csrf_checks=True)
                other_token, _ = self.register(other_client, email="other-image-user@example.test")
                self.verify(other_client, other_token)
                self.assertEqual(other_client.get(image_url).status_code, 404)

                response = client.get(image_url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"private-study-image")
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertEqual(response["Content-Disposition"], "inline")
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
                self.assertNotIn(asset.drug.name, image_url)
                self.assertNotIn(asset.drug.name, response["Content-Disposition"])

                unoffered = (
                    Asset.objects.filter(group=trial.group)
                    .exclude(pk__in=trial.assets.values("pk"))
                    .first()
                )
                self.assertEqual(
                    client.get(
                        reverse("study-asset-image", kwargs={"asset_id": unoffered.pk})
                    ).status_code,
                    404,
                )

                submitted = self.submit(client, csrf, trial.pk, asset.pk)
                self.assertEqual(submitted.status_code, 200)
                self.assertEqual(client.get(image_url).status_code, 404)

        self.assertEqual(client.get("/static/industry/adrenaline.png").status_code, 404)

    def test_private_asset_path_cannot_escape_its_root(self):
        client = APIClient(enforce_csrf_checks=True)
        token, _ = self.register(client, email="path-check@example.test")
        _, csrf = self.verify(client, token)
        trial_data = self.next_trial(client, csrf).data["trial"]
        asset = Asset.objects.get(pk=trial_data["ampoules"][0]["id"])

        with TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            asset_root = temporary_root / "private-assets"
            asset_root.mkdir()
            (temporary_root / "outside.png").write_bytes(b"must-not-be-served")
            asset.asset_url = "../outside.png"
            asset.save(update_fields=("asset_url",))

            with self.settings(STUDY_ASSET_ROOT=asset_root):
                response = client.get(reverse("study-asset-image", kwargs={"asset_id": asset.pk}))
            self.assertEqual(response.status_code, 404)

    def test_old_crud_api_is_gone_and_unknown_api_is_not_spa(self):
        client = APIClient()
        self.assertEqual(client.get("/api/users/").status_code, 404)
        self.assertEqual(client.get("/api/results/").status_code, 404)
        self.assertEqual(client.get("/api/not-a-route/").status_code, 404)
        spa_response = client.get("/participant/start")
        self.assertEqual(spa_response.status_code, 200)
        self.assertIn("text/html", spa_response["Content-Type"])


class TutorialFlowTests(StudyApiTestCase):
    def test_tutorial_is_mandatory_idempotent_and_separate_from_measured_trials(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client, email="tutorial-flow@example.test")
        verified, csrf = self.verify(client, token, complete_tutorial=False)
        run = participant.study_runs.get(protocol_version=2)

        self.assertEqual(verified.data["session"]["phase"], "tutorial")
        self.assertEqual(
            verified.data["session"]["tutorial"],
            {
                "required": 6,
                "complete": False,
                "completed_trials": 0,
                "total_trials": 6,
                "has_active_trial": False,
            },
        )
        self.assertEqual(client.post(reverse("next-tutorial-trial")).status_code, 403)

        blocked = self.next_trial(client, csrf)
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("Complete the tutorial", blocked.data["detail"])
        self.assertFalse(Trial.objects.exists())

        first = self.next_tutorial_trial(client, csrf)
        retry = self.next_tutorial_trial(client, csrf)
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(retry.data["trial"], first.data["trial"])
        self.assertEqual(first.data["trial"]["trial_type"], "tutorial")
        self.assertEqual(
            first.data["trial"]["storage_key"], f"tutorial:{first.data['trial']['id']}"
        )
        self.assertEqual(first.data["trial"]["sequence"], 1)
        self.assertEqual(first.data["trial"]["sequence_total"], 6)
        self.assertIsNone(first.data["trial"]["group_index"])

        first_trial = TutorialTrial.objects.get(pk=first.data["trial"]["id"])
        self.assertEqual(first_trial.group, run.tutorial_group_order[0])
        self.assertEqual(first.data["trial"]["style_name"], first_trial.get_group_display())
        self.assertEqual(
            [ampoule["id"] for ampoule in first.data["trial"]["ampoules"]],
            first_trial.asset_order,
        )
        correct_asset = first_trial.assets.get(drug=first_trial.target)
        first_result = self.submit_tutorial(client, csrf, first_trial.pk, correct_asset.pk)
        self.assertEqual(first_result.status_code, 200, first_result.data)
        self.assertEqual(
            first_result.data["feedback"],
            {"correct": True, "timed_out": False, "sequence": 1, "total_trials": 6},
        )

        duplicate = self.submit_tutorial(
            client,
            csrf,
            first_trial.pk,
            None,
            response_time_ms=first_trial.time_limit_ms,
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.data)
        self.assertEqual(duplicate.data["feedback"], first_result.data["feedback"])
        run.refresh_from_db()
        self.assertEqual(run.tutorial_completed_trials, 1)
        self.assertEqual(TutorialTrialResult.objects.filter(trial=first_trial).count(), 1)

        for sequence in range(2, run.tutorial_trials_required + 1):
            response = self.next_tutorial_trial(client, csrf)
            self.assertEqual(response.status_code, 200, response.data)
            trial_data = response.data["trial"]
            self.assertEqual(trial_data["sequence"], sequence)
            trial = TutorialTrial.objects.get(pk=trial_data["id"])
            self.assertEqual(trial.group, run.tutorial_group_order[sequence - 1])

            if sequence == 2:
                selected = trial.assets.exclude(drug=trial.target).first()
                response_time_ms = 300
                expected_feedback = {"correct": False, "timed_out": False}
            elif sequence == 3:
                selected = trial.assets.get(drug=trial.target)
                response_time_ms = trial.time_limit_ms
                expected_feedback = {"correct": False, "timed_out": True}
            elif sequence == 4:
                selected = None
                response_time_ms = 0
                expected_feedback = {"correct": False, "timed_out": True}
            else:
                selected = trial.assets.get(drug=trial.target)
                response_time_ms = 250
                expected_feedback = {"correct": True, "timed_out": False}

            submitted = self.submit_tutorial(
                client,
                csrf,
                trial.pk,
                selected.pk if selected is not None else None,
                response_time_ms=response_time_ms,
            )
            self.assertEqual(submitted.status_code, 200, submitted.data)
            self.assertEqual(
                {
                    "correct": submitted.data["feedback"]["correct"],
                    "timed_out": submitted.data["feedback"]["timed_out"],
                },
                expected_feedback,
            )
            self.assertEqual(submitted.data["feedback"]["sequence"], sequence)

        run.refresh_from_db()
        self.assertTrue(run.tutorial_complete)
        self.assertIsNotNone(run.tutorial_completed_at)
        self.assertEqual(run.status, StudyRun.Status.READY)
        self.assertEqual(run.completed_trials, 0)
        self.assertEqual(TutorialTrial.objects.filter(study_run=run).count(), 6)
        self.assertEqual(TutorialTrialResult.objects.filter(trial__study_run=run).count(), 6)
        self.assertFalse(Trial.objects.exists())
        self.assertFalse(TrialResult.objects.exists())
        self.assertFalse(run.group_attempts.exclude(status=GroupAttempt.Status.PENDING).exists())

        tutorial_finished = self.next_tutorial_trial(client, csrf)
        self.assertIsNone(tutorial_finished.data["trial"])
        self.assertEqual(tutorial_finished.data["status"]["phase"], "ready")

        measured = self.next_trial(client, csrf)
        self.assertEqual(measured.status_code, 200, measured.data)
        self.assertEqual(measured.data["trial"]["trial_type"], "study")
        self.assertEqual(Trial.objects.count(), 1)
        self.assertEqual(TrialResult.objects.count(), 0)

    def test_unoffered_or_another_participants_tutorial_asset_cannot_be_submitted(self):
        owner = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(owner, email="tutorial-owner@example.test")
        _, owner_csrf = self.verify(owner, token, complete_tutorial=False)
        trial_data = self.next_tutorial_trial(owner, owner_csrf).data["trial"]
        trial = TutorialTrial.objects.get(pk=trial_data["id"])
        offered = {ampoule["id"] for ampoule in trial_data["ampoules"]}
        unoffered = Asset.objects.filter(group=trial.group).exclude(pk__in=offered).first()

        rejected = self.submit_tutorial(owner, owner_csrf, trial.pk, unoffered.pk)
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(TutorialTrialResult.objects.filter(trial=trial).exists())
        participant.study_runs.get(protocol_version=2).refresh_from_db()
        self.assertEqual(
            participant.study_runs.get(protocol_version=2).tutorial_completed_trials,
            0,
        )
        self.assertEqual(self.next_tutorial_trial(owner, owner_csrf).data["trial"], trial_data)

        other = APIClient(enforce_csrf_checks=True)
        other_token, _ = self.register(other, email="other-tutorial-user@example.test")
        _, other_csrf = self.verify(other, other_token, complete_tutorial=False)
        cross_participant = self.submit_tutorial(other, other_csrf, trial.pk, None)
        self.assertEqual(cross_participant.status_code, 404)
        self.assertFalse(TutorialTrialResult.objects.filter(trial=trial).exists())

    def test_tutorial_assets_are_private_and_revoked_after_result(self):
        client = APIClient(enforce_csrf_checks=True)
        token, _ = self.register(client, email="tutorial-image-owner@example.test")
        _, csrf = self.verify(client, token, complete_tutorial=False)
        trial_data = self.next_tutorial_trial(client, csrf).data["trial"]
        trial = TutorialTrial.objects.get(pk=trial_data["id"])
        asset = trial.assets.get(pk=trial_data["ampoules"][0]["id"])
        image_url = reverse("study-asset-image", kwargs={"asset_id": asset.pk})

        with TemporaryDirectory() as temporary_directory:
            asset_root = Path(temporary_directory) / "private-assets"
            image_path = asset_root / asset.asset_url
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"private-tutorial-image")

            with self.settings(STUDY_ASSET_ROOT=asset_root):
                self.assertEqual(APIClient().get(image_url).status_code, 401)
                other = APIClient(enforce_csrf_checks=True)
                other_token, _ = self.register(
                    other,
                    email="other-tutorial-image-user@example.test",
                )
                self.verify(other, other_token, complete_tutorial=False)
                self.assertEqual(other.get(image_url).status_code, 404)
                response = client.get(image_url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"private-tutorial-image")
                submitted = self.submit_tutorial(client, csrf, trial.pk, asset.pk)
                self.assertEqual(submitted.status_code, 200)
                self.assertEqual(client.get(image_url).status_code, 404)

    def test_crafted_measured_trial_result_is_rejected_until_tutorial_completion(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client, email="tutorial-gate@example.test")
        _, csrf = self.verify(client, token, complete_tutorial=False)
        run = participant.study_runs.get(protocol_version=2)
        attempt = run.group_attempts.get(position=0)
        attempt.status = GroupAttempt.Status.ACTIVE
        attempt.save(update_fields=("status",))
        run.status = StudyRun.Status.IN_PROGRESS
        run.save(update_fields=("status",))
        offered = list(Asset.objects.filter(group=attempt.group)[:2])
        trial = Trial.objects.create(
            group_attempt=attempt,
            group=attempt.group,
            target=offered[0].drug,
            time_limit_ms=run.time_limit_ms,
            trial_index=1,
            asset_order=[asset.pk for asset in offered],
        )
        trial.assets.set(offered)

        response = self.submit(client, csrf, trial.pk, offered[0].pk)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Complete the tutorial", response.data["detail"])
        self.assertFalse(TrialResult.objects.filter(trial=trial).exists())
        run.refresh_from_db()
        self.assertEqual(run.completed_trials, 0)


class StudyFlowTests(StudyApiTestCase):
    def test_trials_only_use_drugs_available_in_all_three_groups(self):
        configuration = ExperimentConfiguration.load()
        configuration.choices_per_trial = 4
        configuration.save()
        for group in Group.values:
            drug = Drug.objects.create(name=f"single-group-{group}")
            Asset.objects.create(
                drug=drug,
                group=group,
                asset_url=f"group-{group}/{drug.name}.png",
            )

        client = APIClient(enforce_csrf_checks=True)
        token, _ = self.register(client)
        _, csrf = self.verify(client, token)
        trial_data = self.next_trial(client, csrf).data["trial"]

        self.assertEqual(len(trial_data["ampoules"]), 4)
        offered_assets = Asset.objects.filter(
            pk__in=[ampoule["id"] for ampoule in trial_data["ampoules"]]
        ).select_related("drug")
        self.assertFalse(
            any(asset.drug.name.startswith("single-group-") for asset in offered_assets)
        )

    def test_all_groups_progress_authoritatively_and_requests_are_idempotent(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client)
        _, csrf = self.verify(client, token)
        run = participant.study_runs.get(protocol_version=2)

        initial = client.get(reverse("study-session"))
        self.assertEqual(initial.data["phase"], "ready")
        self.assertEqual(initial.data["group_index"], 1)
        self.assertEqual(initial.data["total_trials"], 3)

        observed_groups = []
        for position in range(3):
            first = self.next_trial(client, csrf)
            self.assertEqual(first.status_code, 200, first.data)
            retry = self.next_trial(client, csrf)
            self.assertEqual(retry.data["trial"], first.data["trial"])

            trial_data = first.data["trial"]
            trial = Trial.objects.get(pk=trial_data["id"])
            observed_groups.append(trial.group)
            self.assertEqual(trial_data["group_index"], position + 1)
            self.assertEqual(
                [ampoule["id"] for ampoule in trial_data["ampoules"]],
                trial.asset_order,
            )
            for ampoule in trial_data["ampoules"]:
                self.assertEqual(
                    ampoule["image_url"],
                    reverse("study-asset-image", kwargs={"asset_id": ampoule["id"]}),
                )

            selected_asset = trial.assets.get(drug=trial.target)
            submitted = self.submit(client, csrf, trial.pk, selected_asset.pk)
            self.assertEqual(submitted.status_code, 200, submitted.data)
            self.assertNotIn("correct", submitted.data)
            self.assertTrue(TrialResult.objects.get(trial=trial).correct)

            duplicate = self.submit(client, csrf, trial.pk, None, response_time_ms=999)
            self.assertEqual(duplicate.status_code, 200)
            self.assertNotIn("correct", duplicate.data)
            self.assertEqual(TrialResult.objects.filter(trial=trial).count(), 1)

            expected_phase = "completed" if position == 2 else "between_groups"
            self.assertEqual(submitted.data["status"]["phase"], expected_phase)
            self.assertEqual(submitted.data["status"]["completed_trials"], position + 1)

        run.refresh_from_db()
        self.assertEqual(observed_groups, run.group_order)
        self.assertEqual(run.status, StudyRun.Status.COMPLETED)
        self.assertIsNone(run.current_group_position)
        self.assertEqual(run.completed_trials, 3)
        self.assertEqual(TrialResult.objects.filter(group_attempt__study_run=run).count(), 3)
        self.assertFalse(run.group_attempts.exclude(status=GroupAttempt.Status.COMPLETED).exists())

        finished = self.next_trial(client, csrf)
        self.assertIsNone(finished.data["trial"])
        self.assertEqual(finished.data["status"]["phase"], "completed")

    def test_late_selection_and_null_selection_are_server_bounded_timeouts(self):
        client = APIClient(enforce_csrf_checks=True)
        token, _ = self.register(client)
        _, csrf = self.verify(client, token)
        trial_data = self.next_trial(client, csrf).data["trial"]
        selected_id = trial_data["ampoules"][0]["id"]

        response = self.submit(
            client,
            csrf,
            trial_data["id"],
            selected_id,
            response_time_ms=trial_data["time_limit_ms"],
        )
        self.assertEqual(response.status_code, 200)
        result = TrialResult.objects.get(trial_id=trial_data["id"])
        self.assertTrue(result.timed_out)
        self.assertFalse(result.correct)
        self.assertIsNone(result.selected_asset_id)
        self.assertEqual(result.response_time_ms, trial_data["time_limit_ms"])

    def test_asset_not_offered_is_rejected_without_advancing(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client)
        _, csrf = self.verify(client, token)
        trial_data = self.next_trial(client, csrf).data["trial"]
        offered = {ampoule["id"] for ampoule in trial_data["ampoules"]}
        other = (
            Asset.objects.filter(group=Trial.objects.get(pk=trial_data["id"]).group)
            .exclude(pk__in=offered)
            .first()
        )

        response = self.submit(client, csrf, trial_data["id"], other.pk)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TrialResult.objects.filter(trial_id=trial_data["id"]).exists())
        run = participant.study_runs.get(protocol_version=2)
        self.assertEqual(run.completed_trials, 0)


class ConfigurationAndUtilityTests(StudyApiTestCase):
    def test_configuration_rejects_client_incompatible_time_limit(self):
        configuration = ExperimentConfiguration.load()
        configuration.time_limit_ms = 600_001
        with self.assertRaises(ValidationError):
            configuration.save()

    def test_configuration_defaults_to_six_tutorial_trials_and_enforces_five_to_ten(self):
        field = ExperimentConfiguration._meta.get_field("tutorial_trials")
        self.assertEqual(field.get_default(), 6)

        configuration = ExperimentConfiguration.load()
        for invalid_count in (4, 11):
            with self.subTest(tutorial_trials=invalid_count):
                configuration.tutorial_trials = invalid_count
                with self.assertRaises(ValidationError):
                    configuration.save()

        for valid_count in range(5, 11):
            with self.subTest(tutorial_trials=valid_count):
                configuration.tutorial_trials = valid_count
                configuration.save()
                configuration.refresh_from_db()
                self.assertEqual(configuration.tutorial_trials, valid_count)

    def test_configuration_changes_only_affect_new_registrations(self):
        first_client = APIClient()
        _, first_participant = self.register(first_client, email="snapshot-one@example.test")
        first_run = first_participant.study_runs.get(protocol_version=2)

        configuration = ExperimentConfiguration.load()
        configuration.trials_per_group = 4
        configuration.choices_per_trial = 3
        configuration.time_limit_ms = 2500
        configuration.tutorial_trials = 10
        configuration.save()

        second_client = APIClient()
        _, second_participant = self.register(second_client, email="snapshot-two@example.test")
        second_run = second_participant.study_runs.get(protocol_version=2)
        first_run.refresh_from_db()

        self.assertEqual(
            (
                first_run.trials_per_group,
                first_run.choices_per_trial,
                first_run.time_limit_ms,
                first_run.tutorial_trials_required,
            ),
            (1, 2, 1000, 6),
        )
        self.assertEqual(
            (
                second_run.trials_per_group,
                second_run.choices_per_trial,
                second_run.time_limit_ms,
                second_run.tutorial_trials_required,
            ),
            (4, 3, 2500, 10),
        )
        self.assertEqual(len(first_run.tutorial_group_order), 6)
        self.assertEqual(len(second_run.tutorial_group_order), 10)

    def test_health_and_asset_loader(self):
        self.assertEqual(APIClient().get(reverse("health")).status_code, 200)

        Asset.objects.all().delete()
        Drug.objects.all().delete()
        call_command("insert_assets", verbosity=0)
        first_counts = (Drug.objects.count(), Asset.objects.count())
        call_command("insert_assets", verbosity=0)

        self.assertEqual((Drug.objects.count(), Asset.objects.count()), first_counts)
        self.assertEqual(first_counts, (21, 61))
        self.assertFalse(Asset.objects.filter(asset_url__startswith="static/").exists())

    def test_admin_export_is_analysis_ready(self):
        client = APIClient(enforce_csrf_checks=True)
        token, participant = self.register(client, email="export@example.test")
        _, csrf = self.verify(client, token)
        trial_data = self.next_trial(client, csrf).data["trial"]
        selected = trial_data["ampoules"][0]
        self.submit(client, csrf, trial_data["id"], selected["id"])

        participant.refresh_from_db()
        participant.account.is_staff = True
        participant.account.save(update_fields=("is_staff",))
        request = RequestFactory().post("/admin/export")
        request.user = participant.account
        response = export_trial_results_csv(
            None,
            request,
            TrialResult.objects.filter(trial_id=trial_data["id"]),
        )
        csv_text = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("participant_email", csv_text)
        self.assertIn("group_order", csv_text)
        self.assertIn("offered_drugs", csv_text)
        self.assertIn("raw_sequence", csv_text)
        self.assertNotIn(participant.email, csv_text)

        for model in (
            Participant,
            StudyRun,
            GroupAttempt,
            Trial,
            TrialResult,
            TutorialTrial,
            TutorialTrialResult,
        ):
            model_admin = admin.site._registry[model]
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            self.assertFalse(model_admin.has_delete_permission(request))


class LegacyCompatibilityTests(TestCase):
    def test_archived_partial_runs_duplicate_sequences_and_orphan_trials_remain_valid(self):
        participant = Participant.objects.create(
            email="legacy@example.test",
            speciality="GAS",
            years_experience=6,
        )
        run = StudyRun.objects.create(
            participant=participant,
            protocol_version=1,
            status=StudyRun.Status.ARCHIVED,
            group_order=[3],
            order_inferred=True,
            trials_per_group=50,
            choices_per_trial=8,
            time_limit_ms=3000,
            current_group_position=None,
        )
        attempt = GroupAttempt.objects.create(
            study_run=run,
            position=0,
            group=3,
            status=GroupAttempt.Status.ARCHIVED,
            completed_trials=2,
        )
        drug = Drug.objects.create(name="legacy-drug")
        asset = Asset.objects.create(
            drug=drug,
            asset_url="blackwhite/legacy-drug.png",
            group=3,
        )
        first_trial = Trial.objects.create(
            group_attempt=attempt,
            group=3,
            target=drug,
            time_limit_ms=3000,
        )
        first_trial.assets.add(asset)
        second_trial = Trial.objects.create(
            group_attempt=attempt,
            group=3,
            target=drug,
            time_limit_ms=3000,
        )
        second_trial.assets.add(asset)
        orphan_trial = Trial.objects.create(
            group_attempt=None,
            group=3,
            target=drug,
            time_limit_ms=3000,
        )
        orphan_trial.assets.add(asset)

        first = TrialResult.objects.create(
            trial=first_trial,
            time="479.0",
            selected="legacy-drug",
            correct=True,
            sequence_id="0",
            group_attempt=attempt,
            group=3,
            response_time_ms=479,
            selected_asset=asset,
        )
        timeout = TrialResult.objects.create(
            trial=second_trial,
            time="3026.0",
            selected=None,
            correct=False,
            sequence_id="0",
            group_attempt=attempt,
            group=3,
            response_time_ms=3026,
            timed_out=True,
        )

        self.assertEqual(run.group_order, [3])
        self.assertTrue(run.order_inferred)
        self.assertEqual(first.time, "479.0")
        self.assertEqual(first.response_time_ms, 479)
        self.assertEqual(first.selected, "legacy-drug")
        self.assertIsNotNone(first.selected_asset_id)
        self.assertEqual(timeout.response_time_ms, 3026)
        self.assertTrue(timeout.timed_out)
        self.assertEqual(timeout.sequence_id, "0")
        self.assertEqual(
            TrialResult.objects.filter(group_attempt=attempt, sequence_id="0").count(), 2
        )
        self.assertIsNone(orphan_trial.group_attempt_id)
