from rest_framework import serializers

from expenses.models import Category, Expense, Item


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
            "created_at",
        ]
        read_only_fields = fields
