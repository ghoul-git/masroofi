from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from expenses.serializers.expense_serializers import CategorySerializer, ExpenseSerializer
from expenses.services import category_service, expense_service
from expenses.views.api import ServiceAPIView


class ExpensePagination(PageNumberPagination):
    page_size = 20


class ExpenseListView(ServiceAPIView):
    """Returns {"count", "next", "previous", "results"}; ?page=N selects the page."""

    def get(self, request):
        paginator = ExpensePagination()
        page = paginator.paginate_queryset(expense_service.list_expenses(request.user), request, view=self)
        return paginator.get_paginated_response(ExpenseSerializer(page, many=True).data)


class ExpenseDetailView(ServiceAPIView):
    parser_classes = [JSONParser]

    def patch(self, request, expense_id):
        expense = expense_service.update_expense(request.user, expense_id, request.data)
        return Response(ExpenseSerializer(expense).data)

    def delete(self, request, expense_id):
        expense_service.delete_expense(request.user, expense_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@login_required
def expenses_page(request):
    categories = CategorySerializer(category_service.list_categories(), many=True).data
    return render(request, "expenses/expenses.html", {"categories": categories})
