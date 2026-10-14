import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model

from expenses.models import Category, ConsentRecord, Expense, Item, Receipt
from expenses.services.consent_service import current_versions

PASSWORD = "test-pass-123"
ALL_CONSENTS = {"accept_terms": True, "accept_privacy": True, "confirm_age": True}


def make_user(username="alice", consent=True):
    """A user who has accepted the current Terms and Privacy versions, unless consent=False."""
    user = get_user_model().objects.create_user(username=username, password=PASSWORD)
    if consent:
        terms_version, privacy_version = current_versions()
        ConsentRecord.objects.create(user=user, terms_version=terms_version, privacy_version=privacy_version)
    return user


def make_category(name="food"):
    # The 0002 migration already creates "Food", "Transport", ... so match case-insensitively.
    return Category.objects.get_or_create(name__iexact=name, defaults={"name": name})[0]


def make_receipt(user, status=Receipt.Status.EXTRACTED):
    # The image path is never opened by these tests, so no real file is needed.
    return Receipt.objects.create(user=user, image="receipts/test.jpg", status=status)


def make_expense(user, category, store_name="Carrefour", total="10.00", date="2026-10-01", currency="JOD"):
    expense = Expense.objects.create(
        user=user,
        category=category,
        store_name=store_name,
        date=datetime.date.fromisoformat(date),
        total=Decimal(total),
        currency=currency,
    )
    Item.objects.create(expense=expense, name="Bread", quantity=1, price=Decimal("1.50"))
    return expense
