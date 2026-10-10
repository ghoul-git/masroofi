from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView


class ServiceAPIView(APIView):
    """Base for the JSON API: session login required, service errors become HTTP errors.

    Services raise Django's ValidationError and Model.DoesNotExist; this turns
    them into 400 and 404 responses so the views stay thin.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, ObjectDoesNotExist):
            exc = exceptions.NotFound(str(exc) or None)
        elif isinstance(exc, DjangoValidationError):
            detail = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
            exc = exceptions.ValidationError(detail)
        return super().handle_exception(exc)
