import datetime
import logging
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from expenses.ai import redaction
from expenses.models import AIUsage, Expense, Receipt
from expenses.repositories import category_repository, expense_repository, receipt_repository
from expenses.services import review_checks, usage_service
from expenses.services.expense_service import clean_expense_data
from expenses.services.validation import (
    DEFAULT_CURRENCY,
    MAX_AMOUNT,
    MAX_QUANTITY,
    parse_amount,
    parse_date_value,
)

logger = logging.getLogger(__name__)

# A receipt still "processing" after this long belongs to a worker that stopped; it is queued again.
STUCK_AFTER = datetime.timedelta(minutes=10)


@dataclass
class QueuedReceipt:
    receipt: Receipt
    usage: dict  # usage_service.receipt_usage including this receipt


@dataclass
class RedactionPlan:
    """What redact_existing would change: {receipt id: redacted text}, and receipts whose image is deleted."""

    texts: dict = field(default_factory=dict)
    image_receipt_ids: list = field(default_factory=list)


def _empty_fields() -> dict:
    return {
        "store_name": "",
        "date": None,
        "total": None,
        "currency": DEFAULT_CURRENCY,
        "category": None,
        "items": [],
    }


def _optional_decimal(value, max_value):
    try:
        return str(parse_amount(value, max_value))
    except ValueError:
        return None


def _normalize_fields(extracted) -> dict:
    """Turn the model's JSON into form-ready values, dropping anything invalid."""
    fields = _empty_fields()
    if not isinstance(extracted, dict):
        return fields

    fields["store_name"] = str(extracted.get("store_name") or "").strip()[:200]

    date = parse_date_value(extracted.get("date"))
    fields["date"] = date.isoformat() if date else None

    fields["total"] = _optional_decimal(extracted.get("total"), MAX_AMOUNT)

    currency = str(extracted.get("currency") or "").strip().upper()
    if len(currency) == 3 and currency.isalpha():
        fields["currency"] = currency

    category_name = extracted.get("category")
    if isinstance(category_name, str) and category_name.strip():
        category = category_repository.get_by_name(category_name.strip())
        fields["category"] = category.pk if category else None

    raw_items = extracted.get("items")
    if isinstance(raw_items, list):
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()[:200]
            if not name:
                continue
            fields["items"].append({
                "name": name,
                "quantity": _optional_decimal(raw.get("quantity", 1), MAX_QUANTITY) or "1.00",
                "price": _optional_decimal(raw.get("price"), MAX_AMOUNT),
            })

    return fields


def _review(fields: dict, raw_text: str) -> dict:
    """Fix or flag fields that are often wrong. Changes fields in place and returns {field: message}."""
    warnings = {}
    if review_checks.is_payment_platform(fields["store_name"]):
        # The model returned the platform (e.g. eFAWATEERcom) instead of the company paid.
        biller = review_checks.find_biller(raw_text)
        if biller:
            fields["store_name"] = biller
        else:
            warnings["store_name"] = review_checks.STORE_MESSAGE
    if review_checks.date_warning(parse_date_value(fields["date"])):
        warnings["date"] = review_checks.DATE_MESSAGE
    return warnings


def queue_receipt(user, image_file) -> QueuedReceipt:
    """Save the image as a queued receipt for the process_receipts worker. No OCR or OpenAI call here.

    Raises LimitReached, before the image is saved, when a usage limit has been
    reached. The receipt counts towards the limits from now on (one AIUsage row,
    whose tokens the worker fills in), whether reading it succeeds or not.
    """
    usage_service.check_receipt_allowed(user)
    with transaction.atomic():
        receipt = receipt_repository.create(user, image_file)
        usage_service.record(user, AIUsage.Kind.RECEIPT, receipt=receipt)
    return QueuedReceipt(receipt=receipt, usage=usage_service.receipt_usage(user))


def claim_next_receipt() -> Receipt | None:
    """Take the oldest queued receipt and mark it processing, or return None if there is none.

    The row is locked with SKIP LOCKED, so several workers never take the same receipt.
    """
    with transaction.atomic():
        receipt = receipt_repository.next_queued_for_update()
        if receipt is None:
            return None
        receipt.status, receipt.processing_started_at = Receipt.Status.PROCESSING, timezone.now()
        receipt_repository.update_by_id(receipt.pk, status=receipt.status,
                                        processing_started_at=receipt.processing_started_at)
    return receipt


def process_claimed_receipt(receipt) -> str:
    """Read a claimed receipt with OCR, extract its fields and store the result. Returns the new status.

    Any failure in the AI steps marks the receipt as failed instead of raising, so
    the user can still fill in the fields by hand. Phone numbers and the customer's
    name are redacted from the OCR text before it is sent to OpenAI or stored.
    """
    # Imported here so only the worker loads EasyOCR and PyTorch; the web process never does.
    from expenses.ai.extraction import extract_fields
    from expenses.ai.ocr import read_text
    from expenses.ai.preprocessing import preprocess

    raw_text, confidence, fields, tokens, warnings = "", 0.0, _empty_fields(), None, {}
    try:
        image = preprocess(receipt.image.path)
        raw_text, confidence = read_text(image)
        raw_text = redaction.redact(raw_text)
        if not raw_text.strip():
            raise ValueError("OCR found no text in the image.")
        extracted, tokens = extract_fields(raw_text, category_repository.list_names())
        fields = _normalize_fields(extracted)
        warnings = _review(fields, raw_text)
        status = Receipt.Status.EXTRACTED
    except Exception:
        logger.exception("Processing failed for receipt %s", receipt.pk)
        status = Receipt.Status.FAILED

    usage_service.record_receipt_tokens(receipt.pk, tokens)
    receipt_repository.update_if_processing(
        receipt.pk, status=status, raw_text=raw_text, extracted=fields, warnings=warnings,
        ocr_confidence=confidence, processing_started_at=None,
    )
    return status


def requeue_receipt(receipt_id) -> None:
    """Put a receipt the worker was stopped in the middle of back in the queue."""
    receipt_repository.update_if_processing(receipt_id, status=Receipt.Status.QUEUED, processing_started_at=None)


def requeue_stuck_receipts() -> int:
    """Queue again receipts left processing for more than STUCK_AFTER by a worker that stopped."""
    return receipt_repository.requeue_processing_started_before(timezone.now() - STUCK_AFTER)


def get_receipt(user, receipt_id) -> Receipt:
    receipt = receipt_repository.get(user, receipt_id)
    if receipt is None:
        raise Receipt.DoesNotExist("Receipt not found.")
    return receipt


def confirm_receipt(user, receipt_id, data) -> Expense:
    """Save the reviewed fields as an Expense with its Items and confirm the receipt.

    The image is no longer needed once the expense is saved, so its file is deleted
    and the field cleared (data minimization); the extracted data stays.
    """
    with transaction.atomic():
        receipt = receipt_repository.get_for_update(user, receipt_id)
        if receipt is None:
            raise Receipt.DoesNotExist("Receipt not found.")
        if receipt.status == Receipt.Status.CONFIRMED:
            raise ValidationError("This receipt has already been confirmed.")

        fields, items = clean_expense_data(data)
        expense = expense_repository.create(user, receipt=receipt, items=items, **fields)
        receipt_repository.update(user, receipt.pk, status=Receipt.Status.CONFIRMED, image="")
        _delete_image_after_commit(receipt.image)
    return expense


def _delete_image_after_commit(image) -> None:
    """Delete the file only once the transaction commits, so a rollback never loses an image."""
    if image:
        storage, name = image.storage, image.name
        transaction.on_commit(lambda: storage.delete(name))


def redaction_plan() -> RedactionPlan:
    """Receipts whose stored text still has phone numbers or a customer name, and confirmed
    receipts that still have an image. Nothing is changed."""
    plan = RedactionPlan()
    for receipt in receipt_repository.with_raw_text().iterator():
        redacted = redaction.redact(receipt.raw_text)
        if redacted != receipt.raw_text:
            plan.texts[receipt.pk] = redacted
    plan.image_receipt_ids = [r.pk for r in receipt_repository.confirmed_with_image()]
    return plan


def apply_redaction_plan(plan: RedactionPlan) -> None:
    for receipt_id, text in plan.texts.items():
        receipt_repository.update_by_id(receipt_id, raw_text=text)
    for receipt in receipt_repository.confirmed_with_image().filter(pk__in=plan.image_receipt_ids):
        with transaction.atomic():
            receipt_repository.update_by_id(receipt.pk, image="")
            _delete_image_after_commit(receipt.image)
