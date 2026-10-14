from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import render
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from expenses.models import Receipt
from expenses.serializers.expense_serializers import CategorySerializer, ExpenseSerializer
from expenses.serializers.receipt_serializers import ProcessedReceiptSerializer, ReceiptUploadSerializer
from expenses.services import category_service, receipt_service
from expenses.views.api import ServiceAPIView


class ReceiptUploadView(ServiceAPIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = ReceiptUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        result = receipt_service.process_receipt(request.user, upload.validated_data["image"])
        return Response(ProcessedReceiptSerializer(result).data, status=status.HTTP_201_CREATED)


class ReceiptConfirmView(ServiceAPIView):
    parser_classes = [JSONParser]

    def post(self, request, receipt_id):
        expense = receipt_service.confirm_receipt(request.user, receipt_id, request.data)
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)


@login_required
def upload_page(request):
    categories = CategorySerializer(category_service.list_categories(), many=True).data
    return render(request, "expenses/upload.html", {"categories": categories})


@login_required
def receipt_image(request, receipt_id):
    """Serve a receipt image to its owner only. Anyone else gets 404, as if it did not exist."""
    try:
        receipt = receipt_service.get_receipt(request.user, receipt_id)
        image = receipt.image.open("rb")
    except (Receipt.DoesNotExist, FileNotFoundError, ValueError):
        raise Http404("Receipt image not found.")
    response = FileResponse(image)
    response["Cache-Control"] = "private, no-store"
    return response
