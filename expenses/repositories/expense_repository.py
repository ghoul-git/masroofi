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
