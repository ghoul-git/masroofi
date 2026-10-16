"""Data minimization: redacting OCR text, deleting images of confirmed receipts, redact_existing."""
import io
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from expenses.ai.redaction import NAME, PHONE, redact
from expenses.models import Expense, Receipt
from expenses.services import receipt_service
from expenses.tests.factories import IMAGE_BYTES, make_category, make_receipt, make_user


class PhoneRedactionTests(SimpleTestCase):
    def test_real_formats(self):
        self.assertEqual(redact("Tel: 0796268159"), f"Tel: {PHONE}")
        self.assertEqual(redact("Phone 0096265504142"), f"Phone {PHONE}")

    def test_mobiles(self):
        for text in ["0796268159", "0776268159", "0786268159", "079 626 8159", "079-626-8159",
                     "+962796268159", "+962 79 626 8159", "+962 (0)79 626 8159", "00962796268159",
                     "00962 79 626 8159"]:
            with self.subTest(text=text):
                self.assertEqual(redact(f"Call {text} today"), f"Call {PHONE} today")

    def test_landlines(self):
        for text in ["065504142", "06 5504142", "06-550-4142", "02 7201234", "03 2012345", "05 3501234",
                     "+96265504142", "+962 6 550 4142", "00962 6 5504142"]:
            with self.subTest(text=text):
                self.assertEqual(redact(f"Tel {text}"), f"Tel {PHONE}")

    def test_arabic_indic_digits(self):
        self.assertEqual(redact("هاتف: ٠٧٩٦٢٦٨١٥٩"), f"هاتف: {PHONE}")

    def test_several_numbers_on_one_receipt(self):
        text = "Mob 0796268159 / Tel 065504142\nTotal 12.500"
        self.assertEqual(redact(text), f"Mob {PHONE} / Tel {PHONE}\nTotal 12.500")

    def test_amounts_dates_and_other_numbers_are_kept(self):
        for text in ["Total 25.000 JOD", "Date 15/01/2019", "2026-10-05 14:32", "Amount 0.750",
                     "Bill no 123456789", "Invoice 07962681591234", "Ref 20796268159", "Qty 2 x 1.250",
                     "Card **** 1234", "VAT 16% 1.600"]:
            with self.subTest(text=text):
                self.assertEqual(redact(text), text)


class CustomerNameRedactionTests(SimpleTestCase):
    def test_english_label_with_the_value_on_the_same_line(self):
        self.assertEqual(redact("Customer Name: Abood Ahmad\nTotal 5.000"), f"Customer Name: {NAME}\nTotal 5.000")
        self.assertEqual(redact("CUSTOMER NAME - Abood"), f"CUSTOMER NAME: {NAME}")

    def test_arabic_customer_name_line(self):
        self.assertEqual(redact("اسم العميل: عبد الرحمن أحمد\nالمبلغ ٥٫٠٠٠"), f"اسم العميل: {NAME}\nالمبلغ ٥٫٠٠٠")

    def test_arabic_line_read_in_the_other_order(self):
        self.assertEqual(redact("عبد الرحمن أحمد :اسم العميل"), f"اسم العميل: {NAME}")

    def test_value_on_the_next_line(self):
        # EasyOCR returns the label and the value as separate lines.
        self.assertEqual(redact("Customer Name\nAbood Ahmad\nTotal 5.000"), f"Customer Name\n{NAME}\nTotal 5.000")
        self.assertEqual(redact("اسم العميل\n\nعبد الرحمن\nالمبلغ"), f"اسم العميل\n\n{NAME}\nالمبلغ")

    def test_text_without_a_customer_name_is_unchanged(self):
        text = "Carrefour\nCustomer service: 24/7\nTotal 5.000"
        self.assertEqual(redact(text), text)
        self.assertEqual(redact(""), "")


class ConfirmRemovesImageTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.receipt = make_receipt(self.user)
        Receipt.objects.filter(pk=self.receipt.pk).update(raw_text="Cozmo [PHONE]", extracted={"store_name": "Cozmo"})

    def confirm(self, **data):
        return self.client.post(f"/api/receipts/{self.receipt.pk}/confirm/", data or {
            "store_name": "Cozmo", "date": "2026-10-01", "total": "5", "category": make_category("food").pk,
        }, content_type="application/json")

    def test_confirming_clears_the_image_and_keeps_the_extracted_data(self):
        response = self.confirm()
        self.assertEqual(response.status_code, 201)
        self.receipt.refresh_from_db()
        self.assertIsNone(self.receipt.image_data)
        self.assertEqual((self.receipt.image_content_type, self.receipt.image_name), ("", ""))
        self.assertEqual(self.receipt.raw_text, "Cozmo [PHONE]")
        self.assertEqual(self.receipt.extracted, {"store_name": "Cozmo"})
        self.assertEqual(Expense.objects.get().receipt, self.receipt)
        self.assertEqual(self.client.get(f"/receipts/{self.receipt.pk}/image/").status_code, 404)

    def test_failed_confirmation_keeps_the_image(self):
        response = self.confirm(total="-1")
        self.assertEqual(response.status_code, 400)
        self.receipt.refresh_from_db()
        self.assertEqual(bytes(self.receipt.image_data), IMAGE_BYTES)
        self.assertEqual(self.receipt.image_content_type, "image/jpeg")


class RedactExistingCommandTests(TestCase):
    def setUp(self):
        user = make_user()
        self.with_phone = make_receipt(user)
        Receipt.objects.filter(pk=self.with_phone.pk).update(raw_text="Cozmo\nTel 0796268159\nTotal 5.000")
        self.clean = make_receipt(user)
        Receipt.objects.filter(pk=self.clean.pk).update(raw_text="Cozmo\nTotal 5.000")
        self.confirmed = make_receipt(user, status=Receipt.Status.CONFIRMED)  # saved before images were removed
        self.waiting = make_receipt(user, status=Receipt.Status.EXTRACTED)

    def run_command(self, *args, answer=None):
        out = io.StringIO()
        with mock.patch("builtins.input", return_value=answer) as prompt:
            call_command("redact_existing", *args, stdout=out)
        return out.getvalue(), prompt

    def test_shows_counts_and_changes_nothing_without_confirmation(self):
        output, prompt = self.run_command(answer="n")
        prompt.assert_called_once()
        self.assertIn("phone numbers or a customer name to redact: 1", output)
        self.assertIn("image will be deleted: 1", output)
        self.assertIn("Nothing was changed", output)
        self.with_phone.refresh_from_db()
        self.confirmed.refresh_from_db()
        self.assertIn("0796268159", self.with_phone.raw_text)
        self.assertIsNotNone(self.confirmed.image_data)

    def test_yes_redacts_text_and_removes_only_confirmed_receipts_images(self):
        output, prompt = self.run_command("--yes")
        prompt.assert_not_called()
        self.assertIn("Redacted the text of 1 receipt(s) and deleted 1 image(s).", output)
        for receipt in (self.with_phone, self.clean, self.confirmed, self.waiting):
            receipt.refresh_from_db()
        self.assertEqual(self.with_phone.raw_text, "Cozmo\nTel [PHONE]\nTotal 5.000")
        self.assertEqual(self.clean.raw_text, "Cozmo\nTotal 5.000")
        self.assertIsNone(self.confirmed.image_data)
        self.assertEqual((self.confirmed.image_content_type, self.confirmed.image_name), ("", ""))
        self.assertEqual(bytes(self.waiting.image_data), IMAGE_BYTES)  # not confirmed yet: still needed

    def test_answering_yes_applies_and_a_second_run_has_nothing_to_do(self):
        self.run_command(answer="y")
        output, _ = self.run_command()
        self.assertIn("Nothing to do.", output)

    def test_plan_matches_what_is_applied(self):
        plan = receipt_service.redaction_plan()
        self.assertEqual(list(plan.texts), [self.with_phone.pk])
        self.assertEqual(plan.image_receipt_ids, [self.confirmed.pk])
