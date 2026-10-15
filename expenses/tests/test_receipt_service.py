import datetime
import tempfile
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from expenses.models import Expense, Item, Receipt
from expenses.services import receipt_service
from expenses.tests.factories import make_category, make_receipt, make_user
from expenses.tests.fakes import MockedReceiptAI, process_next_receipt


class ConfirmReceiptTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.category = make_category("food")
        self.receipt = make_receipt(self.user)

    def valid_data(self, **overrides):
        data = {
            "store_name": "Carrefour",
            "date": "2026-10-05",
            "total": "12.50",
            "currency": "jod",
            "category": self.category.pk,
            "items": [
                {"name": "Milk", "quantity": "2", "price": "1.25"},
                {"name": "Bread", "price": "0.50"},
            ],
        }
        data.update(overrides)
        return data

    def assert_rejected(self, data, field):
        with self.assertRaises(ValidationError) as ctx:
            receipt_service.confirm_receipt(self.user, self.receipt.pk, data)
        self.assertIn(field, ctx.exception.message_dict)
        self.assertFalse(Expense.objects.exists())
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.status, Receipt.Status.EXTRACTED)

    def test_valid_data_creates_expense_items_and_confirms_receipt(self):
        expense = receipt_service.confirm_receipt(self.user, self.receipt.pk, self.valid_data())

        self.assertEqual(expense.user, self.user)
        self.assertEqual(expense.receipt, self.receipt)
        self.assertEqual(expense.category, self.category)
        self.assertEqual(expense.store_name, "Carrefour")
        self.assertEqual(expense.date, datetime.date(2026, 10, 5))
        self.assertEqual(expense.total, Decimal("12.50"))
        self.assertEqual(expense.currency, "JOD")
        items = sorted(expense.items.all(), key=lambda i: i.name)
        self.assertEqual([(i.name, i.quantity, i.price) for i in items], [
            ("Bread", Decimal("1.00"), Decimal("0.50")),
            ("Milk", Decimal("2.00"), Decimal("1.25")),
        ])
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.status, Receipt.Status.CONFIRMED)

    def test_currency_defaults_to_jod(self):
        data = self.valid_data()
        del data["currency"]
        expense = receipt_service.confirm_receipt(self.user, self.receipt.pk, data)
        self.assertEqual(expense.currency, "JOD")

    def test_zero_total_is_allowed(self):
        expense = receipt_service.confirm_receipt(self.user, self.receipt.pk, self.valid_data(total="0"))
        self.assertEqual(expense.total, Decimal("0.00"))

    def test_negative_total_is_rejected(self):
        self.assert_rejected(self.valid_data(total="-0.01"), "total")

    def test_non_numeric_total_is_rejected(self):
        for total in ["abc", "", None, "NaN", "Infinity"]:
            with self.subTest(total=total):
                self.assert_rejected(self.valid_data(total=total), "total")

    def test_total_too_large_for_the_column_is_rejected(self):
        self.assert_rejected(self.valid_data(total="1000000000"), "total")

    def test_invalid_date_is_rejected(self):
        for date in ["2026-02-30", "05/10/2026", "not a date", "", None]:
            with self.subTest(date=date):
                self.assert_rejected(self.valid_data(date=date), "date")

    def test_missing_category_is_rejected(self):
        self.assert_rejected(self.valid_data(category=None), "category")

    def test_unknown_category_is_rejected(self):
        for category in [999999, "abc"]:
            with self.subTest(category=category):
                self.assert_rejected(self.valid_data(category=category), "category")

    def test_missing_store_name_is_rejected(self):
        self.assert_rejected(self.valid_data(store_name="   "), "store_name")

    def test_invalid_currency_is_rejected(self):
        self.assert_rejected(self.valid_data(currency="JD"), "currency")

    def test_invalid_item_is_rejected_and_nothing_is_saved(self):
        self.assert_rejected(self.valid_data(items=[{"name": "Milk", "price": "-1"}]), "items")
        self.assertFalse(Item.objects.exists())

    def test_all_errors_are_reported_together(self):
        data = self.valid_data(total="-5", date="2026-13-01", category=999999)
        with self.assertRaises(ValidationError) as ctx:
            receipt_service.confirm_receipt(self.user, self.receipt.pk, data)
        self.assertEqual(set(ctx.exception.message_dict), {"total", "date", "category"})

    def test_receipt_cannot_be_confirmed_twice(self):
        receipt_service.confirm_receipt(self.user, self.receipt.pk, self.valid_data())
        with self.assertRaises(ValidationError):
            receipt_service.confirm_receipt(self.user, self.receipt.pk, self.valid_data())
        self.assertEqual(Expense.objects.count(), 1)

    def test_failed_receipt_can_be_confirmed_with_manual_fields(self):
        receipt = make_receipt(self.user, status=Receipt.Status.FAILED)
        receipt_service.confirm_receipt(self.user, receipt.pk, self.valid_data())
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, Receipt.Status.CONFIRMED)

    def test_cannot_confirm_another_users_receipt(self):
        other = make_user("bob")
        with self.assertRaises(Receipt.DoesNotExist):
            receipt_service.confirm_receipt(other, self.receipt.pk, self.valid_data())
        self.assertFalse(Expense.objects.exists())
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.status, Receipt.Status.EXTRACTED)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProcessReceiptTests(TestCase):
    """What the worker stores for a receipt. The AI steps are mocked: these tests cover how
    their results are cleaned and saved."""

    def setUp(self):
        self.user = make_user()
        self.food = make_category("food")
        make_category("transport")
        self.image = SimpleUploadedFile("receipt.jpg", b"fake image bytes", content_type="image/jpeg")

    def run_with(self, **ai_options):
        receipt_service.queue_receipt(self.user, self.image)
        with MockedReceiptAI(**ai_options) as ai:
            receipt = process_next_receipt()
        return receipt, ai

    def test_extracted_fields_are_stored_and_receipt_is_marked_extracted(self):
        receipt, ai = self.run_with(extracted={
            "store_name": "Carrefour",
            "date": "2026-10-05",
            "total": 12.5,
            "currency": "jod",
            "category": "Food",
            "items": [{"name": "Milk", "quantity": 2, "price": 1.25}, {"name": "", "price": 1}],
        })

        ai.preprocess.assert_called_once_with(receipt.image.path)
        ai.extract.assert_called_once_with("RAW TEXT", ["Bills", "Entertainment", "Food", "Health", "Other", "Shopping", "Transport"])
        self.assertEqual(receipt.user, self.user)
        self.assertEqual(receipt.status, Receipt.Status.EXTRACTED)
        self.assertEqual(receipt.raw_text, "RAW TEXT")
        self.assertEqual(receipt.ocr_confidence, 0.9)
        self.assertIsNone(receipt.processing_started_at)
        self.assertEqual(receipt.extracted, {
            "store_name": "Carrefour",
            "date": "2026-10-05",
            "total": "12.500",
            "currency": "JOD",
            "category": self.food.pk,
            "items": [{"name": "Milk", "quantity": "2.000", "price": "1.250"}],
        })

    def test_invalid_model_output_is_dropped(self):
        receipt, _ = self.run_with(extracted={
            "store_name": "Shop",
            "date": "yesterday",
            "total": -3,
            "currency": "dollars",
            "category": "not a category",
            "items": "not a list",
        })
        self.assertEqual(receipt.status, Receipt.Status.EXTRACTED)
        self.assertEqual(receipt.extracted["date"], None)
        self.assertEqual(receipt.extracted["total"], None)
        self.assertEqual(receipt.extracted["currency"], "JOD")
        self.assertEqual(receipt.extracted["category"], None)
        self.assertEqual(receipt.extracted["items"], [])

    def test_empty_ocr_text_marks_receipt_failed(self):
        with self.assertLogs("expenses.services.receipt_service", "ERROR"):
            receipt, ai = self.run_with(text="")
        ai.extract.assert_not_called()
        self.assertEqual(receipt.status, Receipt.Status.FAILED)

    def test_extraction_error_marks_receipt_failed_but_keeps_ocr_text(self):
        with self.assertLogs("expenses.services.receipt_service", "ERROR"):
            receipt, _ = self.run_with(extract_error=RuntimeError("API down"))
        self.assertEqual(receipt.status, Receipt.Status.FAILED)
        self.assertEqual(receipt.raw_text, "RAW TEXT")
        self.assertEqual(receipt.extracted["store_name"], "")
