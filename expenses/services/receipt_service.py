import logging
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from expenses.models import AIUsage, Expense, Receipt
from expenses.repositories import category_repository, expense_repository, receipt_repository
from expenses.services import usage_service
from expenses.services.expense_service import clean_expense_data
from expenses.services.validation import (
    DEFAULT_CURRENCY,
    MAX_AMOUNT,
    MAX_QUANTITY,
    parse_amount,
    parse_date_value,
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessedReceipt:
    receipt: Receipt
    fields: dict = field(default_factory=dict)
    confidence: float = 0.0
    usage: dict = field(default_factory=dict)  # usage_service.receipt_usage after this receipt


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


def process_receipt(user, image_file) -> ProcessedReceipt:
    """Save the image, read it with OCR and extract the receipt fields.

    Any failure in the AI steps marks the receipt as failed instead of raising,
    so the user can still fill in the fields by hand and confirm.

    Raises LimitReached, before the image is saved or anything is sent to
    OpenAI, when a usage limit has been reached. Every processed receipt,
    failed or not, is recorded as one AIUsage row.
    """
    usage_service.check_receipt_allowed(user)

    # Imported here because loading EasyOCR pulls in PyTorch, which would
    # otherwise slow down every Django start.
    from expenses.ai.extraction import extract_fields
    from expenses.ai.ocr import read_text
    from expenses.ai.preprocessing import preprocess

    receipt = receipt_repository.create(user, image_file)
    raw_text, confidence, fields, tokens = "", 0.0, _empty_fields(), None

    try:
        image = preprocess(receipt.image.path)
        raw_text, confidence = read_text(image)
        if not raw_text.strip():
            raise ValueError("OCR found no text in the image.")
        extracted, tokens = extract_fields(raw_text, category_repository.list_names())
        fields = _normalize_fields(extracted)
        status = Receipt.Status.EXTRACTED
    except Exception:
        logger.exception("Processing failed for receipt %s", receipt.pk)
        status = Receipt.Status.FAILED

    usage_service.record(user, AIUsage.Kind.RECEIPT, tokens)
    receipt_repository.update(user, receipt.pk, raw_text=raw_text, status=status)
    receipt = receipt_repository.get(user, receipt.pk)
    return ProcessedReceipt(receipt=receipt, fields=fields, confidence=confidence, usage=usage_service.receipt_usage(user))


def get_receipt(user, receipt_id) -> Receipt:
    receipt = receipt_repository.get(user, receipt_id)
    if receipt is None:
        raise Receipt.DoesNotExist("Receipt not found.")
    return receipt


def confirm_receipt(user, receipt_id, data) -> Expense:
    """Save the reviewed fields as an Expense with its Items and confirm the receipt."""
    with transaction.atomic():
        receipt = receipt_repository.get_for_update(user, receipt_id)
        if receipt is None:
            raise Receipt.DoesNotExist("Receipt not found.")
        if receipt.status == Receipt.Status.CONFIRMED:
            raise ValidationError("This receipt has already been confirmed.")

        fields, items = clean_expense_data(data)
        expense = expense_repository.create(user, receipt=receipt, items=items, **fields)
        receipt_repository.update(user, receipt.pk, status=Receipt.Status.CONFIRMED)
    return expense
