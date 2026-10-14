"""Parsing helpers shared by the expense and receipt services."""
import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.utils.dateparse import parse_date

# Amounts are stored with 3 decimal places (DecimalField max_digits=12, decimal_places=3),
# because the Jordanian dinar has 1000 fils. These are the largest values that fit.
AMOUNT_PLACES = Decimal("0.001")
MAX_AMOUNT = Decimal("999999999.999")
MAX_QUANTITY = Decimal("999999999.999")
DEFAULT_CURRENCY = "JOD"


def parse_amount(value, max_value):
    """Parse a non-negative amount, rounded to 3 decimal places, or raise ValueError."""
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError
    if not number.is_finite():
        raise ValueError
    number = number.quantize(AMOUNT_PLACES, rounding=ROUND_HALF_UP)
    if number < 0:
        raise ValueError("must not be negative")
    if number > max_value:
        raise ValueError(f"must not be more than {max_value}")
    return number


def parse_date_value(value):
    """Return a date from a date, datetime or YYYY-MM-DD string, or None if it is not valid."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return parse_date(value.strip())
    except ValueError:  # well formatted but impossible, like 2024-02-30
        return None
