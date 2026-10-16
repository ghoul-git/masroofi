"""3-decimal amounts, date sanity checks and bill-payment platform receipts. OpenAI and OCR are mocked."""
import datetime
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from expenses.ai import extraction
from expenses.ai.tools import run_tool
from expenses.models import Expense, Item
from expenses.services import receipt_service, review_checks
from expenses.services.validation import MAX_AMOUNT, parse_amount
from expenses.tests.factories import make_category, make_expense, make_receipt, make_user
from expenses.tests.fakes import MockedReceiptAI, process_next_receipt

UTC = datetime.timezone.utc
# 09:00 UTC on 14 October 2026 is 12:00 the same day in Amman.
NOW = datetime.datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
TODAY = datetime.date(2026, 10, 14)


def at_now():
    return mock.patch("django.utils.timezone.now", return_value=NOW)


def days_ago(days):
    return (TODAY - datetime.timedelta(days=days)).isoformat()


def process(user, extracted, raw_text="RAW TEXT"):
    """Queue a receipt and run the worker on it, with OCR returning raw_text and the model
    returning `extracted`. Returns the stored receipt (.extracted and .warnings)."""
    image = SimpleUploadedFile("receipt.jpg", b"fake image bytes", content_type="image/jpeg")
    receipt_service.queue_receipt(user, image)
    with MockedReceiptAI(extracted=extracted, tokens=(10, 5), text=raw_text):
        return process_next_receipt()


class FakeChatCompletions:
    """Records the extraction request and answers with an empty JSON object."""

    def __init__(self):
        self.create = mock.Mock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))], usage=None,
        ))
        self.chat = SimpleNamespace(completions=self)

    def system_prompt(self):
        return self.create.call_args.kwargs["messages"][0]["content"]


# ---------------------------------------------------------------- 1. amounts


class ThreeDecimalAmountTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.food = make_category("food")

    def test_model_fields_have_3_decimals_and_12_digits(self):
        for model, name in [(Expense, "total"), (Item, "price"), (Item, "quantity")]:
            field = model._meta.get_field(name)
            self.assertEqual((field.max_digits, field.decimal_places), (12, 3), f"{model.__name__}.{name}")

    def test_parse_amount_keeps_fils_and_rounds_half_up_to_3_places(self):
        self.assertEqual(parse_amount("12.345", MAX_AMOUNT), Decimal("12.345"))
        self.assertEqual(parse_amount("1.2345", MAX_AMOUNT), Decimal("1.235"))
        self.assertEqual(parse_amount("0.750", MAX_AMOUNT), Decimal("0.750"))
        self.assertEqual(parse_amount("999999999.999", MAX_AMOUNT), Decimal("999999999.999"))
        with self.assertRaises(ValueError):
            parse_amount("1000000000", MAX_AMOUNT)

    def test_confirm_saves_and_returns_3_decimals(self):
        receipt = make_receipt(self.user)
        self.client.force_login(self.user)
        response = self.client.post(f"/api/receipts/{receipt.pk}/confirm/", {
            "store_name": "Cozmo", "date": days_ago(3), "total": "12.345", "category": self.food.pk,
            "items": [{"name": "Cheese", "quantity": "0.750", "price": "8.125"}],
        }, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["total"], "12.345")
        self.assertEqual(body["items"][0]["quantity"], "0.750")
        self.assertEqual(body["items"][0]["price"], "8.125")
        expense = Expense.objects.get(pk=body["id"])
        self.assertEqual(expense.total, Decimal("12.345"))

    def test_edit_keeps_3_decimals(self):
        expense = make_expense(self.user, self.food, total="5.000", date=days_ago(3))
        self.client.force_login(self.user)
        response = self.client.patch(f"/api/expenses/{expense.pk}/", {"total": "7.125"}, content_type="application/json")
        self.assertEqual(response.json()["total"], "7.125")

    def test_extracted_total_and_items_keep_3_decimals(self):
        result = process(self.user, {
            "store_name": "Cozmo", "date": days_ago(1), "total": 7.125,
            "items": [{"name": "Milk", "quantity": 0.5, "price": 1.375}],
        })
        self.assertEqual(result.extracted["total"], "7.125")
        self.assertEqual(result.extracted["items"], [{"name": "Milk", "quantity": "0.500", "price": "1.375"}])

    def test_chat_tools_report_fils(self):
        make_expense(self.user, self.food, total="12.345", date="2026-10-02")
        make_expense(self.user, self.food, total="0.005", date="2026-10-03")
        result = run_tool(self.user, "get_spending_total", {"start_date": "2026-10-01", "end_date": "2026-10-31"})
        self.assertEqual(result["totals"], [{"currency": "JOD", "total": "12.350", "count": 2}])

    def test_forms_accept_fils(self):
        self.client.force_login(self.user)
        html = self.client.get("/upload/").content.decode()
        self.assertIn('id="total" min="0" step="0.001"', html)
        self.assertNotIn('step="0.01"', html)


# ---------------------------------------------------------------- 2. dates


class DateWarningRuleTests(SimpleTestCase):
    def test_future_and_older_than_a_year_are_flagged(self):
        with at_now():
            for value, flagged in [
                (TODAY, False),
                (TODAY - datetime.timedelta(days=30), False),
                (TODAY - datetime.timedelta(days=365), False),  # boundary: exactly a year ago is fine
                (TODAY - datetime.timedelta(days=366), True),
                (TODAY + datetime.timedelta(days=1), True),
                (None, False),
            ]:
                with self.subTest(date=value):
                    self.assertEqual(review_checks.date_warning(value) is not None, flagged)

    def test_today_follows_amman_time(self):
        # 22:30 UTC on the 14th is already the 15th in Amman, so the 15th is not in the future.
        late = datetime.datetime(2026, 10, 14, 22, 30, tzinfo=UTC)
        with mock.patch("django.utils.timezone.now", return_value=late):
            self.assertIsNone(review_checks.date_warning(datetime.date(2026, 10, 15)))


class ExtractedDateTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_prompt_gets_todays_local_date_and_the_day_month_year_rule(self):
        fake = FakeChatCompletions()
        late = datetime.datetime(2026, 10, 14, 22, 30, tzinfo=UTC)  # the 15th in Amman
        with mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"}), \
                mock.patch("expenses.ai.extraction.get_client", return_value=fake), \
                mock.patch("django.utils.timezone.now", return_value=late):
            extraction.extract_fields("05/10/2026 Cozmo 7.125", ["Food"])
        prompt = fake.system_prompt()
        self.assertIn("Today's date is 2026-10-15.", prompt)
        self.assertIn("Jordanian receipts write dates as day/month/year", prompt)
        self.assertIn("05/10/2026 is 5 October 2026", prompt)

    def test_suspicious_dates_are_kept_but_flagged(self):
        for date in ["2026-12-01", days_ago(400)]:
            with self.subTest(date=date), at_now():
                result = process(self.user, {"store_name": "Cozmo", "date": date})
                self.assertEqual(result.extracted["date"], date)  # kept for the user to fix
                self.assertEqual(result.warnings, {"date": "Please check this date"})

    def test_normal_date_has_no_warning(self):
        with at_now():
            result = process(self.user, {"store_name": "Cozmo", "date": days_ago(2)})
        self.assertEqual(result.warnings, {})

    def test_upload_api_returns_the_warnings(self):
        self.client.force_login(self.user)
        from PIL import Image
        import io
        buffer = io.BytesIO()
        Image.new("RGB", (1, 1)).save(buffer, format="PNG")
        upload = SimpleUploadedFile("r.png", buffer.getvalue(), content_type="image/png")
        with at_now():
            receipt_id = self.client.post("/api/receipts/", {"image": upload}).json()["id"]
            with MockedReceiptAI(extracted={"store_name": "Cozmo", "date": "2027-01-01"}):
                process_next_receipt()
            body = self.client.get(f"/api/receipts/{receipt_id}/").json()
        self.assertEqual(body["warnings"], {"date": "Please check this date"})


class SavedDateWarningTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.food = make_category("food")
        self.client.force_login(self.user)

    def confirm(self, **fields):
        receipt = make_receipt(self.user)
        data = {"store_name": "Cozmo", "date": days_ago(2), "total": "5", "category": self.food.pk, **fields}
        return self.client.post(f"/api/receipts/{receipt.pk}/confirm/", data, content_type="application/json")

    def test_saving_a_future_date_warns_but_saves(self):
        with at_now():
            response = self.confirm(date="2027-03-01")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["warnings"], {"date": "Please check this date"})
        self.assertEqual(Expense.objects.get().date, datetime.date(2027, 3, 1))

    def test_saving_a_normal_date_has_no_warning(self):
        with at_now():
            self.assertEqual(self.confirm().json()["warnings"], {})

    def test_editing_to_an_old_date_warns_but_saves(self):
        expense = make_expense(self.user, self.food, date=days_ago(2))
        with at_now():
            response = self.client.patch(f"/api/expenses/{expense.pk}/", {"date": days_ago(500)},
                                         content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["warnings"], {"date": "Please check this date"})
        expense.refresh_from_db()
        self.assertEqual(expense.date.isoformat(), days_ago(500))

    def test_expense_list_includes_warnings(self):
        make_expense(self.user, self.food, "Old", date=days_ago(800))
        make_expense(self.user, self.food, "Recent", date=days_ago(1))
        with at_now():
            results = self.client.get("/api/expenses/").json()["results"]
        self.assertEqual({e["store_name"]: e["warnings"] for e in results},
                         {"Old": {"date": "Please check this date"}, "Recent": {}})


# ---------------------------------------------------------------- 3. payment platforms


class PaymentPlatformMatchingTests(SimpleTestCase):
    def test_default_setting_lists_the_platforms(self):
        from django.conf import settings
        for name in ["eFAWATEERcom", "Madfoatcom", "CliQ"]:
            self.assertIn(name, settings.PAYMENT_PLATFORMS)

    def test_platform_names_are_recognised(self):
        for name in ["eFAWATEERcom", "e-Fawateercom", "EFAWATEER COM", "eFAWATEERcom - Bill Payment",
                     "Madfoatcom", "madfoat.com", "CliQ", "CliQ Transfer", "مدفوعاتكم", "إي فواتيركم"]:
            with self.subTest(name=name):
                self.assertTrue(review_checks.is_payment_platform(name))

    def test_ordinary_stores_are_not(self):
        for name in ["Carrefour", "Clique Cafe", "Cliquot", "Orange Jordan", "", "شركة الكهرباء الأردنية"]:
            with self.subTest(name=name):
                self.assertFalse(review_checks.is_payment_platform(name))

    @override_settings(PAYMENT_PLATFORMS=["PayNow"])
    def test_setting_controls_the_list(self):
        self.assertTrue(review_checks.is_payment_platform("PayNow"))
        self.assertFalse(review_checks.is_payment_platform("eFAWATEERcom"))

    def test_find_biller_in_ocr_text(self):
        cases = [
            ("eFAWATEERcom\nBiller: Orange Jordan\nAmount: 25.000 JOD", "Orange Jordan"),
            ("Madfoatcom\nBiller Name : Jordan Electric Power Co.\n", "Jordan Electric Power Co."),
            ("إي فواتيركم\nمزود الخدمة: شركة الكهرباء الأردنية\nالمبلغ 18.250", "شركة الكهرباء الأردنية"),
            ("شركة مياه اليرموك :مزود الخدمة\nالمبلغ 9.500", "شركة مياه اليرموك"),  # right-to-left OCR order
            ("Receipt\nBiller\n\nZain Jordan\nAmount 10.000", "Zain Jordan"),  # label on its own line
            ("Service Provider - Umniah", "Umniah"),
        ]
        for text, biller in cases:
            with self.subTest(biller=biller):
                self.assertEqual(review_checks.find_biller(text), biller)

    def test_find_biller_returns_none_when_missing_or_only_the_platform(self):
        for text in ["eFAWATEERcom\nAmount 25.000", "Biller: eFAWATEERcom", "Billers list", "", None]:
            with self.subTest(text=text):
                self.assertIsNone(review_checks.find_biller(text))


class PaymentPlatformReceiptTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_prompt_has_the_biller_rule_and_the_platform_names(self):
        fake = FakeChatCompletions()
        with mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"}), \
                mock.patch("expenses.ai.extraction.get_client", return_value=fake):
            extraction.extract_fields("RAW", ["Bills"])
        prompt = fake.system_prompt()
        self.assertIn("eFAWATEERcom, Madfoatcom, CliQ", prompt)
        self.assertIn("store_name is the biller (Biller / مزود الخدمة)", prompt)

    def test_platform_store_falls_back_to_the_biller_in_the_ocr_text(self):
        with at_now():
            result = process(self.user, {"store_name": "eFAWATEERcom", "date": days_ago(1), "total": 25},
                             raw_text="eFAWATEERcom\nBiller: Orange Jordan\nAmount 25.000")
        self.assertEqual(result.extracted["store_name"], "Orange Jordan")
        self.assertEqual(result.warnings, {})

    def test_platform_store_without_a_biller_is_flagged(self):
        with at_now():
            result = process(self.user, {"store_name": "CliQ", "date": days_ago(1)}, raw_text="CliQ\nAmount 25.000")
        self.assertEqual(result.extracted["store_name"], "CliQ")
        self.assertEqual(result.warnings, {"store_name": review_checks.STORE_MESSAGE})

    def test_both_fields_can_be_flagged_together(self):
        with at_now():
            result = process(self.user, {"store_name": "Madfoatcom", "date": "2030-01-01"}, raw_text="Madfoatcom")
        self.assertEqual(set(result.warnings), {"store_name", "date"})

    def test_normal_store_is_left_alone(self):
        with at_now():
            result = process(self.user, {"store_name": "Carrefour", "date": days_ago(1)},
                             raw_text="Carrefour\nBiller: Someone Else")
        self.assertEqual(result.extracted["store_name"], "Carrefour")
        self.assertEqual(result.warnings, {})

    def test_saving_with_a_platform_store_warns_but_saves(self):
        self.client.force_login(self.user)
        receipt = make_receipt(self.user)
        with at_now():
            response = self.client.post(f"/api/receipts/{receipt.pk}/confirm/", {
                "store_name": "eFAWATEERcom", "date": days_ago(1), "total": "25", "category": make_category("bills").pk,
            }, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["warnings"], {"store_name": review_checks.STORE_MESSAGE})
