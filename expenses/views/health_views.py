from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from expenses.services import health_service


@never_cache
@require_GET
def healthz(request):
    """For the hosting platform's health check: 200 when the app and its database work, 503 if not.

    No login is needed, and nothing but the status is returned.
    """
    if health_service.database_ok():
        return JsonResponse({"status": "ok"})
    return JsonResponse({"status": "unavailable"}, status=503)
