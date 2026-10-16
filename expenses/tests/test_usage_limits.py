import datetime
import io
import os
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from django.test import TestCase, override_settings

from expenses.models import AIUsage, ChatMessage, Receipt
from expenses.services import chat_service, receipt_service, usage_service
from expenses.services.exceptions import LimitReached
from expenses.tests.factories import make_category, make_user
from expenses.tests.fakes import (
    FakeOpenAI,
    MockedReceiptAI,
    function_call,
    patch_openai,
    process_next_receipt,
    text_response,
    tool_response,
)

UTC = datetime.timezone.utc


def add_usage(user, kind, count, at=None):
    """Create `count` AIUsage rows, optionally moved to time `at` (created_at is auto_now_add)."""
    rows = [AIUsage.objects.create(user=user, kind=kind) for _ in range(count)]
    if at is not None:
        AIUsage.objects.filter(pk__in=[r.pk for r in rows]).update(created_at=at)


def image():
    """A real 1x1 PNG: the upload API checks with Pillow that the file is an image."""
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buffer, format="PNG")
    return SimpleUploadedFile("receipt.png", buffer.getvalue(), content_type="image/png")


@override_settings(FREE_RECEIPTS_PER_MONTH=3, GLOBAL_DAILY_AI_CALLS=1000)
class ReceiptLimitTests(TestCase):
    def setUp(self):
        self.user = make_user()
        make_category("food")

    def test_allowed_below_the_limit_and_blocked_at_it(self):
        add_usage(self.user, AIUsage.Kind.RECEIPT, 2)
        receipt_service.queue_receipt(self.user, image())  # the 3rd of 3 is still allowed
        self.assertEqual(usage_service.receipt_usage(self.user)["label"], "3 of 3 receipts this month")

        with MockedReceiptAI() as ai, self.assertRaises(LimitReached) as ctx:
            receipt_service.queue_receipt(self.user, image())
        ai.assert_nothing_called(self)
        self.assertIn("all 3 free receipt scans", str(ctx.exception))
        self.assertEqual(Receipt.objects.count(), 1)  # the blocked image was not even saved
        self.assertEqual(AIUsage.objects.filter(user=self.user).count(), 3)

    def test_month_starts_at_midnight_amman_time(self):
        # Now: 14 October. 20:30 UTC on 30 September is 23:30 in Amman (still September);
        # 21:30 UTC is 00:30 on 1 October in Amman (counts for October).
        now = datetime.datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
        add_usage(self.user, AIUsage.Kind.RECEIPT, 5, at=datetime.datetime(2026, 9, 30, 20, 30, tzinfo=UTC))
        add_usage(self.user, AIUsage.Kind.RECEIPT, 2, at=datetime.datetime(2026, 9, 30, 21, 30, tzinfo=UTC))
        with mock.patch("django.utils.timezone.now", return_value=now):
            self.assertEqual(usage_service.receipt_usage(self.user)["used"], 2)
            usage_service.check_receipt_allowed(self.user)

    def test_chat_usage_does_not_count_towards_receipts(self):
        add_usage(self.user, AIUsage.Kind.CHAT, 10)
        usage_service.check_receipt_allowed(self.user)

    def test_api_returns_429_with_the_message_and_nothing_reaches_openai(self):
        add_usage(self.user, AIUsage.Kind.RECEIPT, 3)
        self.client.force_login(self.user)
        with MockedReceiptAI() as ai, mock.patch("expenses.ai.client.OpenAI") as openai_class:
            response = self.client.post("/api/receipts/", {"image": image()})
        self.assertEqual(response.status_code, 429)
        self.assertIn("all 3 free receipt scans for this month", response.json()["detail"])
        ai.assert_nothing_called(self)
        openai_class.assert_not_called()

    def test_upload_page_shows_usage_and_disables_the_form_at_the_limit(self):
        self.client.force_login(self.user)
        add_usage(self.user, AIUsage.Kind.RECEIPT, 2)
        html = self.client.get("/upload/").content.decode()
        self.assertIn("2 of 3 receipts this month", html)
        self.assertNotIn('id="upload-button" disabled', html)

        add_usage(self.user, AIUsage.Kind.RECEIPT, 1)
        html = self.client.get("/upload/").content.decode()
        self.assertIn("3 of 3 receipts this month", html)
        self.assertIn('id="upload-button" disabled', html)


@override_settings(FREE_CHAT_PER_DAY=2, GLOBAL_DAILY_AI_CALLS=1000)
@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class ChatLimitTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_allowed_below_the_limit_and_blocked_at_it(self):
        fake = FakeOpenAI(text_response("one"), text_response("two"), text_response("three"))
        with patch_openai(fake):
            chat_service.ask(self.user, "first?")
            result = chat_service.ask(self.user, "second?")  # the 2nd of 2 is still allowed
            self.assertEqual(result["usage"]["label"], "2 of 2 questions today")
            self.assertTrue(result["usage"]["limit_reached"])
            with self.assertRaises(LimitReached) as ctx:
                chat_service.ask(self.user, "third?")
        self.assertEqual(len(fake.requests), 2)  # the third question never reached OpenAI
        self.assertIn("asked 2 questions today", str(ctx.exception))
        self.assertEqual(ChatMessage.objects.filter(user=self.user).count(), 4)

    def test_day_starts_at_midnight_amman_time(self):
        # 21:30 UTC on the 13th is 00:30 on the 14th in Amman; 20:30 UTC is still the 13th there.
        now = datetime.datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
        add_usage(self.user, AIUsage.Kind.CHAT, 5, at=datetime.datetime(2026, 10, 13, 20, 30, tzinfo=UTC))
        add_usage(self.user, AIUsage.Kind.CHAT, 1, at=datetime.datetime(2026, 10, 13, 21, 30, tzinfo=UTC))
        with mock.patch("django.utils.timezone.now", return_value=now):
            self.assertEqual(usage_service.chat_usage(self.user)["label"], "1 of 2 questions today")

    def test_api_returns_429_and_nothing_reaches_openai(self):
        add_usage(self.user, AIUsage.Kind.CHAT, 2)
        self.client.force_login(self.user)
        fake = FakeOpenAI(text_response("never"))
        with patch_openai(fake):
            response = self.client.post("/api/chat/", {"question": "Hi"}, content_type="application/json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"],
                         "You have asked 2 questions today, which is the daily limit. You can ask more tomorrow.")
        self.assertEqual(fake.requests, [])
        self.assertFalse(ChatMessage.objects.exists())

    def test_invalid_question_is_rejected_before_the_limit_check(self):
        add_usage(self.user, AIUsage.Kind.CHAT, 2)
        self.client.force_login(self.user)
        response = self.client.post("/api/chat/", {"question": "  "}, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_chat_page_shows_usage_and_the_limit_notice(self):
        self.client.force_login(self.user)
        add_usage(self.user, AIUsage.Kind.CHAT, 1)
        html = self.client.get("/chat/").content.decode()
        self.assertIn("1 of 2 questions today", html)
        self.assertIn('data-limit-reached="false"', html)

        add_usage(self.user, AIUsage.Kind.CHAT, 1)
        html = self.client.get("/chat/").content.decode()
        self.assertIn('data-limit-reached="true"', html)
        self.assertNotIn('id="limit-notice" hidden', html)


@override_settings(GLOBAL_DAILY_AI_CALLS=3, FREE_RECEIPTS_PER_MONTH=30, FREE_CHAT_PER_DAY=20)
@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class GlobalCapTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.staff = make_user("admin")
        self.staff.is_staff = True
        self.staff.save()
        # Other users have used up today's global budget between them.
        add_usage(make_user("bob"), AIUsage.Kind.RECEIPT, 2)
        add_usage(make_user("carol"), AIUsage.Kind.CHAT, 1)

    def test_global_cap_blocks_everyone_including_staff(self):
        for user in [self.alice, self.staff]:
            with self.subTest(user=user.username):
                fake = FakeOpenAI(text_response("never"))
                with patch_openai(fake), self.assertRaises(LimitReached) as ctx:
                    chat_service.ask(user, "Hi")
                self.assertEqual(fake.requests, [])
                self.assertIn("reached its AI usage limit for today", str(ctx.exception))

                with self.assertRaises(LimitReached):
                    receipt_service.queue_receipt(user, image())
                self.assertFalse(Receipt.objects.exists())

    def test_yesterdays_usage_does_not_count(self):
        AIUsage.objects.update(created_at=datetime.datetime(2026, 1, 1, tzinfo=UTC))
        usage_service.check_chat_allowed(self.alice)

    def test_global_cap_returns_429_from_the_api(self):
        self.client.force_login(self.alice)
        response = self.client.post("/api/chat/", {"question": "Hi"}, content_type="application/json")
        self.assertEqual(response.status_code, 429)
        self.assertIn("try again tomorrow", response.json()["detail"])


@override_settings(FREE_RECEIPTS_PER_MONTH=1, FREE_CHAT_PER_DAY=1, GLOBAL_DAILY_AI_CALLS=1000)
@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class StaffExemptionTests(TestCase):
    def setUp(self):
        self.staff = make_user("admin")
        self.staff.is_staff = True
        self.staff.save()
        make_category("food")
        add_usage(self.staff, AIUsage.Kind.RECEIPT, 5)
        add_usage(self.staff, AIUsage.Kind.CHAT, 5)

    def test_staff_can_go_past_the_per_user_limits(self):
        receipt_service.queue_receipt(self.staff, image())
        with patch_openai(FakeOpenAI(text_response("ok"))):
            result = chat_service.ask(self.staff, "Hi")
        self.assertEqual(result["usage"], {
            "used": 6, "limit": None, "limit_reached": False, "label": "6 questions today (no limit for staff)",
        })
        self.assertEqual(usage_service.receipt_usage(self.staff)["label"], "6 receipts this month (no limit for staff)")

    def test_regular_user_at_the_same_usage_is_blocked(self):
        user = make_user("alice")
        add_usage(user, AIUsage.Kind.CHAT, 1)
        with self.assertRaises(LimitReached):
            usage_service.check_chat_allowed(user)


@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class UsageRecordingTests(TestCase):
    def setUp(self):
        self.user = make_user()
        make_category("food")

    def test_chat_records_one_row_with_tokens_summed_over_every_model_call(self):
        arguments = {"start_date": "2026-10-01", "end_date": "2026-10-31", "category": None}
        fake = FakeOpenAI(
            tool_response(function_call("get_spending_total", arguments), tokens=(400, 25)),
            text_response("You spent nothing.", tokens=(520, 60)),
        )
        with patch_openai(fake):
            chat_service.ask(self.user, "Total in October?")

        row = AIUsage.objects.get(user=self.user)
        self.assertEqual((row.kind, row.input_tokens, row.output_tokens), ("chat", 920, 85))

    def test_chat_response_without_usage_records_zero_tokens(self):
        with patch_openai(FakeOpenAI(text_response("Hi"))):
            chat_service.ask(self.user, "Hello")
        row = AIUsage.objects.get(user=self.user)
        self.assertEqual((row.input_tokens, row.output_tokens), (0, 0))

    def test_failed_chat_records_nothing(self):
        with patch_openai(FakeOpenAI(error=RuntimeError("down"))), \
                self.assertLogs("expenses.services.chat_service", "ERROR"), self.assertRaises(Exception):
            chat_service.ask(self.user, "Hello")
        self.assertFalse(AIUsage.objects.exists())

    def test_receipt_counts_when_queued_and_the_worker_adds_the_extraction_tokens(self):
        result = receipt_service.queue_receipt(self.user, image())
        self.assertEqual(result.usage["used"], 1)
        row = AIUsage.objects.get(user=self.user)
        self.assertEqual((row.kind, row.receipt, row.input_tokens, row.output_tokens),
                         ("receipt", result.receipt, 0, 0))

        with MockedReceiptAI(tokens=(1200, 150)):
            process_next_receipt()
        row.refresh_from_db()
        self.assertEqual((row.input_tokens, row.output_tokens), (1200, 150))
        self.assertEqual(AIUsage.objects.count(), 1)

    def test_receipt_that_fails_before_openai_still_counts_with_zero_tokens(self):
        receipt_service.queue_receipt(self.user, image())
        with MockedReceiptAI(text="") as ai, self.assertLogs("expenses.services.receipt_service", "ERROR"):
            receipt = process_next_receipt()
        ai.extract.assert_not_called()
        self.assertEqual(receipt.status, Receipt.Status.FAILED)
        row = AIUsage.objects.get(user=self.user)
        self.assertEqual((row.kind, row.input_tokens, row.output_tokens), ("receipt", 0, 0))

    def test_api_responses_include_the_new_usage(self):
        self.client.force_login(self.user)
        body = self.client.post("/api/receipts/", {"image": image()}).json()
        self.assertEqual(body["usage"]["label"], "1 of 30 receipts this month")

        with patch_openai(FakeOpenAI(text_response("Hi"))):
            body = self.client.post("/api/chat/", {"question": "Hello"}, content_type="application/json").json()
        self.assertEqual(body["usage"]["label"], "1 of 20 questions today")
