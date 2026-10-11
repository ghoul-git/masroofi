from django.db.models import Count, Sum

from expenses.models import Expense, Item


def _for_user(user):
    return (
        Expense.objects.filter(user=user)
        .select_related("category")
        .prefetch_related("items")
    )


def create(user, *, receipt, category, store_name, date, total, currency, items) -> Expense:
    expense = Expense.objects.create(
        user=user,
        receipt=receipt,
        category=category,
        store_name=store_name,
        date=date,
        total=total,
        currency=currency,
    )
    Item.objects.bulk_create(Item(expense=expense, **item) for item in items)
    return get(user, expense.pk)


def get(user, expense_id) -> Expense | None:
    return _for_user(user).filter(pk=expense_id).first()


def list_for_user(user):
    return _for_user(user).order_by("-date", "-created_at")


def update(user, expense_id, fields: dict, items: list[dict] | None = None) -> Expense | None:
    """Update the given fields; when items is not None, replace all items."""
    if fields:
        Expense.objects.filter(user=user, pk=expense_id).update(**fields)
    if items is not None:
        Item.objects.filter(expense__user=user, expense_id=expense_id).delete()
        Item.objects.bulk_create(Item(expense_id=expense_id, **item) for item in items)
    return get(user, expense_id)


def delete(user, expense_id) -> int:
    deleted, _ = Expense.objects.filter(user=user, pk=expense_id).delete()
    return deleted


# Reporting queries for the chat tools. Totals are grouped by currency because
# amounts in different currencies cannot be added together.


def _in_period(user, start_date, end_date, category=None, store=None):
    expenses = Expense.objects.filter(user=user, date__range=(start_date, end_date))
    if category:
        expenses = expenses.filter(category__name__iexact=category)
    if store:
        expenses = expenses.filter(store_name__icontains=store)
    return expenses


def totals_by_currency(user, start_date, end_date, category=None) -> list[dict]:
    """[{"currency", "total", "count"}] for the period, largest total first."""
    return list(
        _in_period(user, start_date, end_date, category)
        .values("currency")
        .annotate(total=Sum("total"), count=Count("id"))
        .order_by("-total", "currency")
    )


def totals_by_category(user, start_date, end_date) -> list[dict]:
    """[{"category", "currency", "total", "count"}] for the period, largest total first."""
    return list(
        _in_period(user, start_date, end_date)
        .values("category__name", "currency")
        .annotate(total=Sum("total"), count=Count("id"))
        .order_by("-total", "category__name")
    )


def list_in_period(user, start_date, end_date, category=None, store=None, limit=20) -> list[Expense]:
    return list(
        _in_period(user, start_date, end_date, category, store)
        .select_related("category")
        .order_by("-date", "-created_at")[:limit]
    )


def count_in_period(user, start_date, end_date, category=None, store=None) -> int:
    return _in_period(user, start_date, end_date, category, store).count()


def top_in_period(user, start_date, end_date, limit=5) -> list[Expense]:
    return list(
        _in_period(user, start_date, end_date)
        .select_related("category")
        .order_by("-total", "-date")[:limit]
    )
