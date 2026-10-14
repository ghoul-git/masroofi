from rest_framework import serializers

from expenses.models import Category, Expense, Item
from expenses.services import expense_service


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ["id", "name", "quantity", "price"]


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    items = ItemSerializer(many=True, read_only=True)
    # {field: message} for values to double-check, e.g. {"date": "Please check this date"}.
    warnings = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id",
            "store_name",
            "date",
            "total",
            "currency",
            "category",
            "category_name",
            "receipt",
            "items",
            "warnings",
            "created_at",
        ]
        read_only_fields = fields

    def get_warnings(self, expense):
        return expense_service.expense_warnings(expense)
