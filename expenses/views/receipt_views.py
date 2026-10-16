from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from expenses.models import Receipt
from expenses.serializers.expense_serializers import CategorySerializer, ExpenseSerializer
from expenses.serializers.receipt_serializers import (
    QueuedReceiptSerializer,
    ReceiptStatusSerializer,
    ReceiptUploadSerializer,
)
from expenses.services import category_service, receipt_service, usage_service
from expenses.views.api import ServiceAPIView


class ReceiptUploadView(ServiceAPIView):
    """Queue a receipt photo. The process_receipts worker reads it; poll ReceiptDetailView for the result."""

    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = ReceiptUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        result = receipt_service.queue_receipt(request.user, upload.validated_data["image"])
        return Response(QueuedReceiptSerializer(result).data, status=status.HTTP_202_ACCEPTED)


class ReceiptDetailView(ServiceAPIView):
    def get(self, request, receipt_id):
        receipt = receipt_service.get_receipt(request.user, receipt_id)
        return Response(ReceiptStatusSerializer(receipt).data)


class ReceiptConfirmView(ServiceAPIView):
    parser_classes = [JSONParser]

    def post(self, request, receipt_id):
        expense = receipt_service.confirm_receipt(request.user, receipt_id, request.data)
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)


@login_required
def upload_page(request):
    categories = CategorySerializer(category_service.list_categories(), many=True).data
    usage = usage_service.receipt_usage(request.user)
    return render(request, "expenses/upload.html", {"categories": categories, "usage": usage})


@login_required
def receipt_image(request, receipt_id):
    """Serve a receipt image to its owner only. Anyone else gets 404, as if it did not exist,
    and so does a receipt whose image has been removed (confirmed receipts)."""
    try:
        image = receipt_service.get_receipt_image(request.user, receipt_id)
    except Receipt.DoesNotExist:
        raise Http404("Receipt image not found.")
    response = HttpResponse(image.data, content_type=image.content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    return response
