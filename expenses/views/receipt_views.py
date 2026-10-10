from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

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
