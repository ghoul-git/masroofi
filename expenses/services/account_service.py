"""Data subject rights: a copy of all of a user's data, and deleting the account."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from expenses.repositories import (
    ai_usage_repository,
    chat_repository,
    consent_repository,
    expense_repository,
    receipt_repository,
    user_repository,
)

WRONG_PASSWORD = "The password is incorrect. Your account was not deleted."


def _iso(value):
    return value.isoformat() if value else None


def export_user_data(user) -> dict:
    """Everything stored about the user, as JSON-ready data. Amounts are strings to keep exact decimals."""
    return {
        "exported_at": _iso(timezone.now()),
        "profile": {
            "username": user.username,
            "email": user.email,
            "date_joined": _iso(user.date_joined),
        },
        "expenses": [
            {
                "id": e.pk,
                "store_name": e.store_name,
                "date": _iso(e.date),
                "total": str(e.total),
                "currency": e.currency,
                "category": e.category.name,
                "receipt_id": e.receipt_id,
                "created_at": _iso(e.created_at),
                "items": [
                    {"name": i.name, "quantity": str(i.quantity), "price": str(i.price)}
                    for i in e.items.all()
                ],
            }
            for e in expense_repository.list_for_user(user)
        ],
        "receipts": [
            {
                "id": r.pk,
                "status": r.status,
                "uploaded_at": _iso(r.uploaded_at),
                "raw_text": r.raw_text,
                "extracted": r.extracted,
                # Never the image bytes, only whether the image is still stored.
                "image_name": r.image_name,
                "image_stored": r.image_name != "",
            }
            for r in receipt_repository.list_for_user(user)
        ],
        "chat_messages": [
            {
                "role": m.role,
                "content": m.content,
                "tools_used": m.tools_used,
                "created_at": _iso(m.created_at),
            }
            for m in chat_repository.list_for_user(user)
        ],
        "ai_usage": [
            {
                "kind": u.kind,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "created_at": _iso(u.created_at),
            }
            for u in ai_usage_repository.list_for_user(user)
        ],
        "consent_records": [
            {
                "terms_version": c.terms_version,
                "privacy_version": c.privacy_version,
                "accepted_at": _iso(c.accepted_at),
            }
            for c in consent_repository.list_for_user(user)
        ],
    }


def delete_account(user, password) -> None:
    """Delete the user and all their data, including the receipt images.

    The current password is required, so someone using an unlocked, logged-in
    browser cannot delete the account.
    """
    if not isinstance(password, str) or not user.check_password(password):
        raise ValidationError(WRONG_PASSWORD)
    with transaction.atomic():
        user_repository.delete(user)
