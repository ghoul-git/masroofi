"""Receipts are queued by the API and read by the process_receipts worker. OCR and OpenAI are mocked."""
import datetime
import io
import os
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from expenses.models import AIUsage, Receipt
from expenses.services import receipt_service
from expenses.tests.factories import make_category, make_receipt, make_user
from expenses.tests.fakes import MockedReceiptAI, process_next_receipt

MEDIA_ROOT = tempfile.mkdtemp()


def image():
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buffer, format="PNG")
    return SimpleUploadedFile("receipt.png", buffer.getvalue(), content_type="image/png")


def run_worker(**options):
    """Run process_receipts --once with the OCR model load mocked; returns its output."""
    out = io.StringIO()
    with mock.patch("expenses.ai.ocr.get_reader") as get_reader:
        call_command("process_receipts", once=True, stdout=out, **options)
    return out.getvalue(), get_reader


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class UploadApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        make_category("food")

    def test_upload_queues_the_receipt_and_returns_202_without_any_ai_call(self):
        with MockedReceiptAI() as ai, mock.patch("expenses.ai.client.OpenAI") as openai_class:
            response = self.client.post("/api/receipts/", {"image": image()})
        self.assertEqual(response.status_code, 202)
        body = response.json()
        receipt = Receipt.objects.get()
        self.assertEqual(body["id"], receipt.pk)
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["usage"]["used"], 1)
        self.assertEqual(receipt.status, Receipt.Status.QUEUED)
        self.assertTrue(receipt.image)
        ai.assert_nothing_called(self)
        openai_class.assert_not_called()

    def test_invalid_image_is_rejected_and_nothing_is_queued(self):
        bad = SimpleUploadedFile("receipt.png", b"not an image", content_type="image/png")
        response = self.client.post("/api/receipts/", {"image": bad})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Receipt.objects.exists())
        self.assertFalse(AIUsage.objects.exists())

    def test_status_while_waiting_has_no_result_yet(self):
        receipt_id = self.client.post("/api/receipts/", {"image": image()}).json()["id"]
        for status in (Receipt.Status.QUEUED, Receipt.Status.PROCESSING):
            with self.subTest(status=status):
                Receipt.objects.filter(pk=receipt_id).update(status=status)
                body = self.client.get(f"/api/receipts/{receipt_id}/").json()
                self.assertEqual(body["status"], status)
                self.assertIsNone(body["extracted"])
                self.assertIsNone(body["warnings"])
                self.assertIsNone(body["raw_text"])

    def test_status_after_the_worker_has_the_fields_and_warnings(self):
        receipt_id = self.client.post("/api/receipts/", {"image": image()}).json()["id"]
        with MockedReceiptAI(extracted={"store_name": "Cozmo", "date": "2001-01-01", "total": 5}):
            process_next_receipt()
        body = self.client.get(f"/api/receipts/{receipt_id}/").json()
        self.assertEqual(body["status"], "extracted")
        self.assertEqual(body["extracted"]["store_name"], "Cozmo")
        self.assertEqual(body["extracted"]["total"], "5.000")
        self.assertEqual(body["warnings"], {"date": "Please check this date"})
        self.assertEqual(body["raw_text"], "RAW TEXT")
        self.assertEqual(body["confidence"], 0.9)

    def test_failed_receipt_returns_empty_fields_for_the_manual_form(self):
        receipt_id = self.client.post("/api/receipts/", {"image": image()}).json()["id"]
        with MockedReceiptAI(text=""), self.assertLogs("expenses.services.receipt_service", "ERROR"):
            process_next_receipt()
        body = self.client.get(f"/api/receipts/{receipt_id}/").json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["extracted"]["store_name"], "")
        self.assertEqual(body["warnings"], {})

    def test_status_is_only_for_the_owner(self):
        receipt = make_receipt(make_user("bob"))
        self.assertEqual(self.client.get(f"/api/receipts/{receipt.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/receipts/999999/").status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(f"/api/receipts/{receipt.pk}/").status_code, 403)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class WorkerTests(TestCase):
    def setUp(self):
        self.user = make_user()
        make_category("food")

    def queue(self, count=1):
        return [receipt_service.queue_receipt(self.user, image()).receipt for _ in range(count)]

    def test_claims_the_oldest_queued_receipt_and_marks_it_processing(self):
        first, second = self.queue(2)
        Receipt.objects.filter(pk=second.pk).update(uploaded_at=first.uploaded_at - datetime.timedelta(minutes=1))
        claimed = receipt_service.claim_next_receipt()
        self.assertEqual(claimed.pk, second.pk)
        claimed.refresh_from_db()
        self.assertEqual(claimed.status, Receipt.Status.PROCESSING)
        self.assertIsNotNone(claimed.processing_started_at)
        self.assertEqual(receipt_service.claim_next_receipt().pk, first.pk)
        self.assertIsNone(receipt_service.claim_next_receipt())

    def test_only_queued_receipts_are_claimed(self):
        for status in (Receipt.Status.EXTRACTED, Receipt.Status.FAILED, Receipt.Status.CONFIRMED,
                       Receipt.Status.PROCESSING, Receipt.Status.UPLOADED):
            make_receipt(self.user, status=status)
        self.assertIsNone(receipt_service.claim_next_receipt())

    def test_claim_skips_rows_locked_by_another_worker(self):
        self.queue()
        with mock.patch("expenses.repositories.receipt_repository.Receipt.objects.select_for_update",
                        wraps=Receipt.objects.select_for_update) as select_for_update:
            receipt_service.claim_next_receipt()
        select_for_update.assert_called_once_with(skip_locked=True)

    def test_worker_once_processes_everything_queued_then_exits(self):
        self.queue(3)
        with MockedReceiptAI() as ai:
            output, get_reader = run_worker()
        get_reader.assert_called_once_with()  # the OCR model is loaded once, not per receipt
        self.assertEqual(ai.extract.call_count, 3)
        self.assertEqual(set(Receipt.objects.values_list("status", flat=True)), {"extracted"})
        self.assertIn("Done: 3 receipt(s) processed.", output)

    def test_worker_records_failures_and_carries_on(self):
        self.queue(2)
        with MockedReceiptAI(extract_error=RuntimeError("API down")), \
                self.assertLogs("expenses.services.receipt_service", "ERROR"):
            run_worker()
        self.assertEqual(set(Receipt.objects.values_list("status", flat=True)), {"failed"})

    def test_worker_sleeps_between_checks_when_idle(self):
        with mock.patch("expenses.management.commands.process_receipts.time.sleep",
                        side_effect=[None, KeyboardInterrupt]) as sleep, \
                mock.patch("expenses.ai.ocr.get_reader"):
            out = io.StringIO()
            call_command("process_receipts", sleep=0.5, stdout=out)
        self.assertEqual(sleep.call_args_list, [mock.call(0.5), mock.call(0.5)])
        self.assertIn("Stopped after 0 receipt(s).", out.getvalue())

    def test_ctrl_c_during_a_receipt_puts_it_back_in_the_queue(self):
        receipt, = self.queue()
        with mock.patch("expenses.ai.preprocessing.preprocess", side_effect=KeyboardInterrupt):
            output, _ = run_worker()
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, Receipt.Status.QUEUED)
        self.assertIsNone(receipt.processing_started_at)
        self.assertIn(f"Receipt {receipt.pk} was put back in the queue.", output)

    def test_receipts_stuck_in_processing_over_10_minutes_are_queued_again_on_start(self):
        stuck, recent = self.queue(2)
        now = timezone.now()
        Receipt.objects.filter(pk=stuck.pk).update(status="processing",
                                                   processing_started_at=now - datetime.timedelta(minutes=11))
        Receipt.objects.filter(pk=recent.pk).update(status="processing",
                                                    processing_started_at=now - datetime.timedelta(minutes=9))
        with MockedReceiptAI() as ai:
            output, _ = run_worker()
        self.assertIn("Queued 1 receipt(s) again", output)
        stuck.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual(stuck.status, Receipt.Status.EXTRACTED)
        self.assertEqual(recent.status, Receipt.Status.PROCESSING)  # possibly still being read by another worker
        self.assertEqual(ai.extract.call_count, 1)

    def test_receipt_confirmed_by_hand_while_processing_is_not_overwritten(self):
        receipt, = self.queue()
        claimed = receipt_service.claim_next_receipt()
        receipt_service.confirm_receipt(self.user, receipt.pk, {
            "store_name": "Typed by hand", "date": "2026-10-01", "total": "3", "category": make_category("food").pk,
        })
        with MockedReceiptAI():
            receipt_service.process_claimed_receipt(claimed)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, Receipt.Status.CONFIRMED)
        self.assertEqual(receipt.extracted, {})

    def test_ocr_text_is_redacted_before_openai_and_storage(self):
        self.queue()
        text = "Cozmo\nTel 0796268159\nCustomer Name: Abood Ahmad\nTotal 5.000"
        with MockedReceiptAI(text=text) as ai:
            receipt = process_next_receipt()
        sent = ai.extract.call_args.args[0]
        for stored in (sent, receipt.raw_text):
            self.assertNotIn("0796268159", stored)
            self.assertNotIn("Abood", stored)
            self.assertIn("[PHONE]", stored)
            self.assertIn("[NAME]", stored)
            self.assertIn("Total 5.000", stored)


class WebProcessImportTests(TestCase):
    def test_web_process_never_imports_easyocr_or_torch(self):
        """Load everything the web server loads (settings, URLs, every view, middleware) in a fresh
        Python process, then check that neither EasyOCR nor PyTorch was imported."""
        code = (
            "import sys, django; django.setup()\n"
            "from django.core.wsgi import get_wsgi_application\n"
            "from django.urls import get_resolver\n"
            "get_wsgi_application()\n"
            "get_resolver().url_patterns\n"
            "import expenses.views.receipt_views, expenses.views.chat_views, expenses.services.receipt_service\n"
            "print(sorted(m for m in ('easyocr', 'torch', 'cv2') if m in sys.modules))\n"
        )
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings")}
        result = subprocess.run([sys.executable, "-c", code], cwd=settings.BASE_DIR, env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "[]")
