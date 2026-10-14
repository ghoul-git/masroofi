"""Tools the chat agent can call to read the logged-in user's expenses.

The user is never a tool argument: run_tool receives it from the request, so the
model can only ever see the data of the person who is asking.
"""
import datetime
import inspect
from decimal import Decimal

from expenses.repositories import category_repository, expense_repository
from expenses.services.validation import AMOUNT_PLACES

MAX_LIMIT = 50


class ToolError(ValueError):
    """Bad tool arguments. run_tool turns it into {"error": message} for the model."""


# Argument parsing


def _date(value, name) -> datetime.date:
    if not isinstance(value, str):
        raise ToolError(f"{name} must be a date string in YYYY-MM-DD format.")
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        raise ToolError(f"{name} must be a valid date in YYYY-MM-DD format, got {value!r}.")


def _period(start_date, end_date, start_name="start_date", end_name="end_date"):
    start, end = _date(start_date, start_name), _date(end_date, end_name)
    if start > end:
        raise ToolError(f"{start_name} must be on or before {end_name}.")
    return start, end


def _category(value) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ToolError("category must be a string.")
    category = category_repository.get_by_name(value.strip())
    if category is None:
        names = ", ".join(category_repository.list_names())
        raise ToolError(f"Unknown category {value!r}. Valid categories: {names}.")
    return category.name


def _limit(value, default) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolError(f"limit must be a whole number between 1 and {MAX_LIMIT}.")
    return min(value, MAX_LIMIT)


# Output formatting


def _amount(value) -> str:
    return str((value or Decimal("0")).quantize(AMOUNT_PLACES))


def _totals(rows) -> list[dict]:
    return [{"currency": r["currency"], "total": _amount(r["total"]), "count": r["count"]} for r in rows]


def _expense(expense) -> dict:
    return {
        "id": expense.pk,
        "date": expense.date.isoformat(),
        "store_name": expense.store_name,
        "category": expense.category.name,
        "total": _amount(expense.total),
        "currency": expense.currency,
    }


# Tools


def get_spending_total(user, start_date, end_date, category=None):
    start, end = _period(start_date, end_date)
    category = _category(category)
    totals = _totals(expense_repository.totals_by_currency(user, start, end, category))
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "category": category,
        "totals": totals,
        "expense_count": sum(t["count"] for t in totals),
    }


def get_spending_by_category(user, start_date, end_date):
    start, end = _period(start_date, end_date)
    rows = expense_repository.totals_by_category(user, start, end)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "categories": [
            {"category": r["category__name"], "currency": r["currency"], "total": _amount(r["total"]), "count": r["count"]}
            for r in rows
        ],
    }


def list_expenses(user, start_date, end_date, category=None, store=None, limit=None):
    start, end = _period(start_date, end_date)
    category = _category(category)
    if store is not None and not isinstance(store, str):
        raise ToolError("store must be a string.")
    store = store.strip() if store else None
    limit = _limit(limit, default=20)
    expenses = expense_repository.list_in_period(user, start, end, category, store, limit)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "category": category,
        "store": store,
        "total_matching": expense_repository.count_in_period(user, start, end, category, store),
        "expenses": [_expense(e) for e in expenses],
    }


def get_top_expenses(user, start_date, end_date, limit=None):
    start, end = _period(start_date, end_date)
    limit = _limit(limit, default=5)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "expenses": [_expense(e) for e in expense_repository.top_in_period(user, start, end, limit)],
    }


def compare_periods(user, first_start, first_end, second_start, second_end, category=None):
    first = _period(first_start, first_end, "first_start", "first_end")
    second = _period(second_start, second_end, "second_start", "second_end")
    category = _category(category)

    first_totals = {r["currency"]: r["total"] for r in expense_repository.totals_by_currency(user, *first, category)}
    second_totals = {r["currency"]: r["total"] for r in expense_repository.totals_by_currency(user, *second, category)}

    comparison = []
    for currency in sorted(first_totals.keys() | second_totals.keys()):
        a = first_totals.get(currency) or Decimal("0")
        b = second_totals.get(currency) or Decimal("0")
        change = b - a
        percent = None if a == 0 else float(round(change / a * 100, 1))
        comparison.append({
            "currency": currency,
            "first_total": _amount(a),
            "second_total": _amount(b),
            "change": _amount(change),
            "change_percent": percent,
        })

    return {
        "first_period": {"start_date": first[0].isoformat(), "end_date": first[1].isoformat()},
        "second_period": {"start_date": second[0].isoformat(), "end_date": second[1].isoformat()},
        "category": category,
        "comparison": comparison,
    }


TOOLS = {
    "get_spending_total": get_spending_total,
    "get_spending_by_category": get_spending_by_category,
    "list_expenses": list_expenses,
    "get_top_expenses": get_top_expenses,
    "compare_periods": compare_periods,
}


def run_tool(user, name, arguments) -> dict:
    """Run a tool for the given user. Errors are returned as {"error": ...}, never raised."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool {name!r}. Available tools: {', '.join(TOOLS)}."}
    if not isinstance(arguments, dict):
        return {"error": "Tool arguments must be a JSON object."}
    if "user" in arguments:
        return {"error": "The user cannot be passed as an argument."}

    try:
        inspect.signature(tool).bind(user, **arguments)
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}."}

    try:
        return tool(user, **arguments)
    except ToolError as e:
        return {"error": str(e)}


# Schemas in the Responses API function tool format. strict mode makes the model
# always send every parameter, so optional ones are nullable and passed as null.

_DATE = {"type": "string", "description": "Date in YYYY-MM-DD format."}
_CATEGORY = {
    "type": ["string", "null"],
    "description": "Category name to filter by, such as food or transport. null for all categories.",
}


def _schema(name, description, properties):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOL_SCHEMAS = [
    _schema(
        "get_spending_total",
        "Total amount spent between two dates (inclusive), optionally for one category. "
        "Totals are grouped by currency.",
        {"start_date": _DATE, "end_date": _DATE, "category": _CATEGORY},
    ),
    _schema(
        "get_spending_by_category",
        "Amount spent per category between two dates (inclusive), largest first.",
        {"start_date": _DATE, "end_date": _DATE},
    ),
    _schema(
        "list_expenses",
        "List individual expenses between two dates (inclusive), newest first, "
        "optionally filtered by category and store name.",
        {
            "start_date": _DATE,
            "end_date": _DATE,
            "category": _CATEGORY,
            "store": {
                "type": ["string", "null"],
                "description": "Part of the store name to search for. null for all stores.",
            },
            "limit": {
                "type": ["integer", "null"],
                "description": f"Maximum number of expenses to return, 1 to {MAX_LIMIT}. null for 20.",
            },
        },
    ),
    _schema(
        "get_top_expenses",
        "The largest single expenses between two dates (inclusive).",
        {
            "start_date": _DATE,
            "end_date": _DATE,
            "limit": {
                "type": ["integer", "null"],
                "description": f"How many expenses to return, 1 to {MAX_LIMIT}. null for 5.",
            },
        },
    ),
    _schema(
        "compare_periods",
        "Compare total spending between two date ranges (each inclusive), optionally for one category. "
        "Returns both totals, the change, and the change in percent, per currency.",
        {
            "first_start": _DATE,
            "first_end": _DATE,
            "second_start": _DATE,
            "second_end": _DATE,
            "category": _CATEGORY,
        },
    ),
]
