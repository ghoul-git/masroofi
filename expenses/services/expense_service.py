from django.core.exceptions import ValidationError
from django.db import transaction

from expenses.models import Expense
from expenses.repositories import category_repository, expense_repository
from expenses.services import review_checks
from expenses.services.validation import (
    DEFAULT_CURRENCY,
    MAX_AMOUNT,
    MAX_QUANTITY,
    parse_amount,
    parse_date_value,
)


def _clean_items(raw_items, errors):
    if not isinstance(raw_items, list):
        errors["items"] = ["Items must be a list."]
        return None

    items, item_errors = [], []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            item_errors.append(f"Item {index}: invalid item.")
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            item_errors.append(f"Item {index}: name is required.")
        elif len(name) > 200:
            item_errors.append(f"Item {index}: name is too long (max 200 characters).")
        try:
            quantity = parse_amount(raw.get("quantity", 1), MAX_QUANTITY)
        except ValueError as e:
            item_errors.append(f"Item {index}: quantity {e}." if str(e) else f"Item {index}: quantity must be a number.")
            quantity = None
        try:
            price = parse_amount(raw.get("price"), MAX_AMOUNT)
        except ValueError as e:
            item_errors.append(f"Item {index}: price {e}." if str(e) else f"Item {index}: price must be a number.")
            price = None
        items.append({"name": name, "quantity": quantity, "price": price})

    if item_errors:
        errors["items"] = item_errors
    return items


def clean_expense_data(data, *, partial=False):
    """Validate expense input.

    Returns (fields, items): fields holds the Expense column values that were
    given, and items is a list of item dicts, or None when items were not given.
    Raises ValidationError with a message per field.
    """
    if not isinstance(data, dict):
        raise ValidationError("Expected an object with the expense fields.")

    errors, fields, items = {}, {}, None

    def given(key):
        return key in data or not partial

    if given("store_name"):
        store_name = str(data.get("store_name") or "").strip()
        if not store_name:
            errors["store_name"] = ["Store name is required."]
        elif len(store_name) > 200:
            errors["store_name"] = ["Store name is too long (max 200 characters)."]
        else:
            fields["store_name"] = store_name

    if given("date"):
        date = parse_date_value(data.get("date"))
        if date is None:
            errors["date"] = ["Enter a valid date in YYYY-MM-DD format."]
        else:
            fields["date"] = date

    if given("total"):
        try:
            fields["total"] = parse_amount(data.get("total"), MAX_AMOUNT)
        except ValueError as e:
            errors["total"] = [f"Total {e}." if str(e) else "Total must be a number."]

    if "currency" in data or not partial:
        currency = str(data.get("currency") or DEFAULT_CURRENCY).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            errors["currency"] = ["Currency must be a 3-letter code, like JOD."]
        else:
            fields["currency"] = currency

    if given("category"):
        category_id = data.get("category")
        category = None
        if category_id in (None, ""):
            errors["category"] = ["Category is required."]
        else:
            try:
                category = category_repository.get(int(category_id))
            except (TypeError, ValueError):
                pass
            if category is None:
                errors["category"] = ["Category does not exist."]
            else:
                fields["category"] = category

    if "items" in data:
        items = _clean_items(data["items"], errors)
    elif not partial:
        items = []

    if errors:
        raise ValidationError(errors)
    return fields, items


def list_expenses(user):
    return expense_repository.list_for_user(user)


def get_expense(user, expense_id) -> Expense:
    expense = expense_repository.get(user, expense_id)
    if expense is None:
        raise Expense.DoesNotExist("Expense not found.")
    return expense


def update_expense(user, expense_id, data) -> Expense:
    get_expense(user, expense_id)
    fields, items = clean_expense_data(data, partial=True)
    with transaction.atomic():
        return expense_repository.update(user, expense_id, fields, items)


def delete_expense(user, expense_id) -> None:
    if not expense_repository.delete(user, expense_id):
        raise Expense.DoesNotExist("Expense not found.")


def expense_warnings(expense) -> dict:
    """{field: message} for fields to double-check on a saved expense. Never blocks saving."""
    return review_checks.expense_warnings(expense.store_name, expense.date)
