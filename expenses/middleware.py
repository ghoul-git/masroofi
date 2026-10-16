from urllib.parse import urlencode

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from expenses.services import consent_service

SESSION_KEY = "consent_versions"


def remember_consent(request):
    """Mark the session as having consent to the current versions, so the database is not asked again."""
    request.session[SESSION_KEY] = list(consent_service.current_versions())


class ConsentRequiredMiddleware:
    """Sends logged-in users without consent to the current Terms/Privacy versions to /consent/.

    Exempt: admin, static files, the consent page itself, logging out, the Terms and
    Privacy pages (so they can be read first), /account/ (so a user who does not
    accept can still download or delete their data), the web app manifest,
    service worker and offline page (which have no user data and must never be
    swapped for the consent page), and the /healthz health check. API requests get a JSON 403 instead of a redirect.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_consent(request):
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {"detail": "Please accept the current Terms of Service and Privacy Policy first."},
                    status=403,
                )
            return redirect(f"{reverse('consent')}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)

    def _exempt_prefixes(self):
        return (
            reverse("admin:index"),
            settings.STATIC_URL if settings.STATIC_URL.startswith("/") else f"/{settings.STATIC_URL}",
            reverse("consent"),
            reverse("logout"),
            reverse("terms"),
            reverse("privacy"),
            reverse("account"),
            reverse("manifest"),
            reverse("service-worker"),
            reverse("offline"),
            reverse("healthz"),
        )

    def _needs_consent(self, request) -> bool:
        if not request.user.is_authenticated:
            return False
        if request.path.startswith(self._exempt_prefixes()):
            return False
        if request.session.get(SESSION_KEY) == list(consent_service.current_versions()):
            return False
        if consent_service.has_current_consent(request.user):
            remember_consent(request)
            return False
        return True
