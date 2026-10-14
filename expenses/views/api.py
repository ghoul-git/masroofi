from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from expenses.services.exceptions import LimitReached, ServiceUnavailable


class ServiceUnavailableError(exceptions.APIException):
    status_code = 503
    default_detail = "The service is not available right now. Please try again."
    default_code = "service_unavailable"


class LimitReachedError(exceptions.APIException):
    status_code = 429
    default_detail = "You have reached a usage limit. Please try again later."
    default_code = "limit_reached"


class ServiceAPIView(APIView):
    """Base for the JSON API: session login required, service errors become HTTP errors.

    Services raise Django's ValidationError, Model.DoesNotExist, LimitReached and
    ServiceUnavailable; this turns them into 400, 404, 429 and 503 responses so
    the views stay thin.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, ObjectDoesNotExist):
            exc = exceptions.NotFound(str(exc) or None)
        elif isinstance(exc, DjangoValidationError):
            detail = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
            exc = exceptions.ValidationError(detail)
        elif isinstance(exc, LimitReached):
            exc = LimitReachedError(str(exc) or None)
        elif isinstance(exc, ServiceUnavailable):
            exc = ServiceUnavailableError(str(exc) or None)
        return super().handle_exception(exc)
