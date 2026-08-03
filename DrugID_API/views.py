from django.conf import settings
from django.contrib.auth import logout
from django.db import connection
from django.http import FileResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from DrugID_API.authentication import ParticipantSessionAuthentication
from DrugID_API.serializers import (
    MagicLinkRequestSerializer,
    MagicLinkVerifySerializer,
    TrialResultInputSerializer,
)
from DrugID_API.services import (
    next_trial_for_user,
    next_tutorial_trial_for_user,
    outstanding_asset_for_user,
    request_magic_link,
    resolve_study_asset_path,
    study_run_for_user,
    study_status,
    submit_trial_result,
    submit_tutorial_trial_result,
    trial_payload,
    tutorial_trial_payload,
    verify_magic_link,
)


class MagicLinkRequestView(APIView):
    authentication_classes = []
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "magic_link"

    def post(self, request):
        serializer = MagicLinkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        debug_link = request_magic_link(**serializer.validated_data)
        payload = {"detail": "If the address is valid, a sign-in link has been sent."}
        if settings.DEBUG and settings.SHOW_DEBUG_MAGIC_LINK:
            payload["debug_magic_link"] = debug_link
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class MagicLinkVerifyView(APIView):
    authentication_classes = []
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = MagicLinkVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = verify_magic_link(request, serializer.validated_data["token"])
        get_token(request)
        return Response(
            {
                "detail": "Signed in.",
                "session": study_status(run),
            }
        )


class LogoutView(APIView):
    authentication_classes = (ParticipantSessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        logout(request)
        return Response({"detail": "Signed out."})


class StudySessionView(APIView):
    authentication_classes = (ParticipantSessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        run = study_run_for_user(request.user)
        return Response(study_status(run))


class NextTrialView(APIView):
    authentication_classes = (ParticipantSessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        run, trial = next_trial_for_user(request.user)
        return Response(
            {
                "status": study_status(run),
                "trial": trial_payload(trial) if trial is not None else None,
            }
        )


class NextTutorialTrialView(APIView):
    authentication_classes = (ParticipantSessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        run, trial = next_tutorial_trial_for_user(request.user)
        return Response(
            {
                "status": study_status(run),
                "trial": tutorial_trial_payload(trial) if trial is not None else None,
            }
        )


class StudyAssetImageView(APIView):
    authentication_classes = (ParticipantSessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, asset_id):
        asset = outstanding_asset_for_user(request.user, asset_id)
        asset_path = resolve_study_asset_path(asset)
        content_type = {
            ".jpeg": "image/jpeg",
            ".jpg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(asset_path.suffix.lower())
        if content_type is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(
            asset_path.open("rb"),
            content_type=content_type,
        )
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, no-store"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        return response


class TrialResultView(APIView):
    authentication_classes = (ParticipantSessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, trial_id):
        serializer = TrialResultInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _, run = submit_trial_result(
            user=request.user,
            trial_id=trial_id,
            **serializer.validated_data,
        )
        return Response({"status": study_status(run)})


class TutorialTrialResultView(APIView):
    authentication_classes = (ParticipantSessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, tutorial_trial_id):
        serializer = TrialResultInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result, run = submit_tutorial_trial_result(
            user=request.user,
            tutorial_trial_id=tutorial_trial_id,
            **serializer.validated_data,
        )
        return Response(
            {
                "status": study_status(run),
                "feedback": {
                    "correct": result.correct,
                    "timed_out": result.timed_out,
                    "sequence": result.trial.sequence,
                    "total_trials": run.tutorial_trials_required,
                },
            }
        )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return Response({"status": "unhealthy"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})


def spa_index(request, path=""):
    return render(request, "index.html")
