from rest_framework.authentication import SessionAuthentication


class ParticipantSessionAuthentication(SessionAuthentication):
    """Make a missing session distinguishable from an authenticated CSRF failure."""

    def authenticate_header(self, request):
        return "Session"
