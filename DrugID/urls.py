from django.contrib import admin
from django.urls import path, re_path

from DrugID_API import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path(
        "api/auth/magic-link/",
        views.MagicLinkRequestView.as_view(),
        name="magic-link-request",
    ),
    path(
        "api/auth/verify/",
        views.MagicLinkVerifyView.as_view(),
        name="magic-link-verify",
    ),
    path("api/auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("api/study/session/", views.StudySessionView.as_view(), name="study-session"),
    path(
        "api/study/tutorial/trials/next/",
        views.NextTutorialTrialView.as_view(),
        name="next-tutorial-trial",
    ),
    path(
        "api/study/tutorial/trials/<int:tutorial_trial_id>/result/",
        views.TutorialTrialResultView.as_view(),
        name="tutorial-trial-result",
    ),
    path("api/study/trials/next/", views.NextTrialView.as_view(), name="next-trial"),
    path(
        "api/study/assets/<int:asset_id>/image/",
        views.StudyAssetImageView.as_view(),
        name="study-asset-image",
    ),
    path(
        "api/study/trials/<int:trial_id>/result/",
        views.TrialResultView.as_view(),
        name="trial-result",
    ),
    path("admin/", admin.site.urls),
    re_path(
        r"^(?!api(?:/|$)|admin(?:/|$)|health(?:/|$)|static(?:/|$))(?P<path>.*)$",
        views.spa_index,
        name="spa-index",
    ),
]
