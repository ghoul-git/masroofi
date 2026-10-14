"""Checks that flag a field for the user to review. They warn; they never block saving.

- Dates in the future or more than MAX_DAYS_IN_PAST days ago are usually OCR or
  day/month mix-ups.
- On bill-payment platform receipts (settings.PAYMENT_PLATFORMS) the store is the
  biller (the company paid), not the platform.
"""
import datetime
import re

from django.conf import settings
from django.utils import timezone

MAX_DAYS_IN_PAST = 365
DATE_MESSAGE = "Please check this date"
STORE_MESSAGE = "Please check the store name: use the company you paid (the biller), not the payment platform."

# Labels that come before (or, in right-to-left OCR output, after) the biller's name.
# Longest first, so "Biller Name" wins over "Biller".
BILLER_LABELS = [
    "Service Provider",
    "Biller Name",
    "Biller",
    "الجهة المفوترة",
    "اسم المفوتر",
    "مزود الخدمة",
    "المفوتر",
]
_SEPARATORS = " \t:：-–—|"


def date_warning(date: datetime.date | None) -> str | None:
    if date is None:
        return None
    today = timezone.localdate()
    if date > today or date < today - datetime.timedelta(days=MAX_DAYS_IN_PAST):
        return DATE_MESSAGE
    return None


def _normalize(name: str) -> str:
    return re.sub(r"[\s\-_.·]", "", name).casefold()


def is_payment_platform(name: str) -> bool:
    """True if the name is a payment platform, e.g. "eFAWATEERcom", "e-Fawateercom" or "CliQ - Transfer".

    Matches the whole name (ignoring case, spaces and dashes) or the platform as a
    separate word, so "Clique Cafe" is not mistaken for CliQ.
    """
    if not name:
        return False
    normalized = _normalize(name)
    for platform in settings.PAYMENT_PLATFORMS:
        if normalized == _normalize(platform):
            return True
        if re.search(rf"(?<!\w){re.escape(platform)}(?!\w)", name, re.IGNORECASE):
            return True
    return False


def _clean(value: str) -> str:
    return value.strip(_SEPARATORS)[:200]


def _usable(value: str) -> bool:
    return bool(value) and not is_payment_platform(value) and value not in BILLER_LABELS


def find_biller(raw_text: str) -> str | None:
    """The biller's name from OCR text, from a line like "Biller: Orange Jordan" or
    "مزود الخدمة: شركة الكهرباء", or the line after a label on its own. None if not found."""
    lines = [line.strip() for line in (raw_text or "").splitlines()]
    for index, line in enumerate(lines):
        for label in BILLER_LABELS:
            escaped = re.escape(label)
            after = re.match(rf"^{escaped}(?!\w)(.*)$", line, re.IGNORECASE)   # "Biller: X"
            before = re.match(rf"^(.*?)(?<!\w){escaped}$", line, re.IGNORECASE)  # "X :مزود الخدمة" (RTL)
            match = after or before
            if not match:
                continue
            value = _clean(match.group(1))
            if not value:  # label on its own line: the name is on the next non-empty line
                value = next((_clean(nxt) for nxt in lines[index + 1:] if nxt), "")
            if _usable(value):
                return value
    return None


def expense_warnings(store_name: str, date: datetime.date | None) -> dict:
    """{field: message} for a saved or edited expense."""
    warnings = {}
    if date_warning(date):
        warnings["date"] = DATE_MESSAGE
    if is_payment_platform(store_name):
        warnings["store_name"] = STORE_MESSAGE
    return warnings
