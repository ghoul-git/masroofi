import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model

from expenses.models import Category, Expense, Item, Receipt


def make_user(username="alice"):
    return get_user_model().objects.create_user(username=username, password="test-pass-123")


def make_category(name="food"):
    return Category.objects.get_or_create(name=name)[0]


def make_receipt(user, status=Receipt.Status.EXTRACTED):
    # The image path is never opened by these tests, so no real file is needed.
    return Receipt.objects.create(user=user, image="receipts/test.jpg", status=status)


def make_expense(user, category, store_name="Carrefour", total="10.00"):
    expense = Expense.objects.create(
        user=user,
        category=category,
        store_name=store_name,
        date=datetime.date(2026, 10, 1),
        total=Decimal(total),
    )
    Item.objects.create(expense=expense, name="Bread", quantity=1, price=Decimal("1.50"))
    return expense
