"""AI usage limits and tracking.

Every receipt processed and every chat question answered is one AIUsage row.
The limits count those rows, in the local timezone (settings.TIME_ZONE):

- FREE_RECEIPTS_PER_MONTH per user, per calendar month
- FREE_CHAT_PER_DAY per user, per day
- GLOBAL_DAILY_AI_CALLS for all users together, per day

Staff users are exempt from the per-user limits but not from the global one.
The check_* functions must be called before any OpenAI request.
"""
import datetime

from django.conf import settings
from django.utils import timezone

from expenses.models import AIUsage
from expenses.repositories import ai_usage_repository
from expenses.services.exceptions import LimitReached

GLOBAL_LIMIT_MESSAGE = (
    "Masroofi has reached its AI usage limit for today. Please try again tomorrow. "
    "You can still view and edit your saved expenses."
)


def _start_of_today():
    return timezone.make_aware(datetime.datetime.combine(timezone.localdate(), datetime.time.min))


def _start_of_month():
    return timezone.make_aware(datetime.datetime.combine(timezone.localdate().replace(day=1), datetime.time.min))


def _next_month_label():
    today = timezone.localdate()
    first_of_next = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return f"{first_of_next.day} {first_of_next:%B}"


def _check_global():
    if ai_usage_repository.count_all_since(_start_of_today()) >= settings.GLOBAL_DAILY_AI_CALLS:
        raise LimitReached(GLOBAL_LIMIT_MESSAGE)


def receipt_usage(user) -> dict:
    """{"used", "limit", "limit_reached", "label"}; limit is None for staff."""
    used = ai_usage_repository.count_for_user(user, AIUsage.Kind.RECEIPT, _start_of_month())
    if user.is_staff:
        return {"used": used, "limit": None, "limit_reached": False,
                "label": f"{used} receipts this month (no limit for staff)"}
    limit = settings.FREE_RECEIPTS_PER_MONTH
    return {"used": used, "limit": limit, "limit_reached": used >= limit,
            "label": f"{used} of {limit} receipts this month"}


def chat_usage(user) -> dict:
    """{"used", "limit", "limit_reached", "label"}; limit is None for staff."""
    used = ai_usage_repository.count_for_user(user, AIUsage.Kind.CHAT, _start_of_today())
    if user.is_staff:
        return {"used": used, "limit": None, "limit_reached": False,
                "label": f"{used} questions today (no limit for staff)"}
    limit = settings.FREE_CHAT_PER_DAY
    return {"used": used, "limit": limit, "limit_reached": used >= limit,
            "label": f"{used} of {limit} questions today"}


def check_receipt_allowed(user) -> None:
    _check_global()
    usage = receipt_usage(user)
    if usage["limit_reached"]:
        raise LimitReached(
            f"You have used all {usage['limit']} free receipt scans for this month. "
            f"You can scan more from {_next_month_label()}."
        )


def check_chat_allowed(user) -> None:
    _check_global()
    usage = chat_usage(user)
    if usage["limit_reached"]:
        raise LimitReached(
            f"You have asked {usage['limit']} questions today, which is the daily limit. "
            "You can ask more tomorrow."
        )


def record(user, kind, tokens: dict | None = None) -> AIUsage:
    tokens = tokens or {}
    return ai_usage_repository.create(
        user,
        kind,
        input_tokens=tokens.get("input_tokens", 0),
        output_tokens=tokens.get("output_tokens", 0),
    )
