import json
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings

from expenses.models import AIUsage, ChatMessage, ConsentRecord, Expense, Item, Receipt
from expenses.tests.factories import PASSWORD, make_category, make_expense, make_user

User = get_user_model()
MEDIA_ROOT = tempfile.mkdtemp()


def make_receipt_with_file(user, raw_text="RAW"):
    return Receipt.objects.create(
        user=user,
        image=SimpleUploadedFile("receipt.jpg", b"image bytes", content_type="image/jpeg"),
        raw_text=raw_text,
        status=Receipt.Status.CONFIRMED,
    )


class UserDataMixin:
    """Alice and Bob each have a receipt (with an image file), an expense with items, chat and usage rows."""

    def setUp(self):
        food = make_category("food")
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        for user, store in [(self.alice, "Alice Market"), (self.bob, "Bob Market")]:
            receipt = make_receipt_with_file(user, raw_text=f"{store} receipt text")
            expense = make_expense(user, food, store, total="12.50")
            Expense.objects.filter(pk=expense.pk).update(receipt=receipt)
            ChatMessage.objects.create(user=user, role="user", content=f"{store}: كم صرفت؟")
            ChatMessage.objects.create(user=user, role="assistant", content="12.50 JOD",
                                       tools_used=[{"name": "get_spending_total", "arguments": {}}])
            AIUsage.objects.create(user=user, kind="chat", input_tokens=300, output_tokens=20)
        self.alice_image = Receipt.objects.get(user=self.alice).image.name
        self.bob_image = Receipt.objects.get(user=self.bob).image.name


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ExportTests(UserDataMixin, TestCase):
    def export(self):
        self.client.force_login(self.alice)
        response = self.client.get("/account/export/")
        self.assertEqual(response.status_code, 200)
        return response, json.loads(response.content.decode("utf-8"))

    def test_download_is_a_json_attachment(self):
        response, _ = self.export()
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertRegex(response["Content-Disposition"], r'^attachment; filename="masroofi-data-alice-\d{4}-\d{2}-\d{2}\.json"$')
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_export_contains_all_of_the_users_data(self):
        _, data = self.export()
        self.assertEqual(data["profile"]["username"], "alice")
        self.assertEqual(set(data["profile"]), {"username", "email", "date_joined"})
        [expense] = data["expenses"]
        self.assertEqual((expense["store_name"], expense["total"], expense["category"]), ("Alice Market", "12.500", "Food"))
        self.assertEqual(expense["items"], [{"name": "Bread", "quantity": "1.000", "price": "1.500"}])
        self.assertEqual([r["raw_text"] for r in data["receipts"]], ["Alice Market receipt text"])
        self.assertEqual([m["content"] for m in data["chat_messages"]], ["Alice Market: كم صرفت؟", "12.50 JOD"])
        self.assertEqual(data["chat_messages"][1]["tools_used"], [{"name": "get_spending_total", "arguments": {}}])
        self.assertEqual(data["ai_usage"], [{"kind": "chat", "input_tokens": 300, "output_tokens": 20,
                                             "created_at": data["ai_usage"][0]["created_at"]}])
        self.assertEqual([(c["terms_version"], c["privacy_version"]) for c in data["consent_records"]], [("1.0", "1.0")])

    def test_export_contains_only_the_users_own_data(self):
        response, data = self.export()
        text = response.content.decode("utf-8")
        self.assertNotIn("Bob", text)
        self.assertNotIn("bob", text)
        self.assertEqual((len(data["expenses"]), len(data["receipts"]), len(data["chat_messages"]),
                          len(data["ai_usage"]), len(data["consent_records"])), (1, 1, 2, 1, 1))

    def test_arabic_is_kept_readable(self):
        response, _ = self.export()
        self.assertIn("كم صرفت؟", response.content.decode("utf-8"))

    def test_export_requires_login(self):
        self.assertTrue(self.client.get("/account/export/")["Location"].startswith("/login/"))


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DeleteAccountTests(UserDataMixin, TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def counts(self, user_id):
        return {
            "user": User.objects.filter(pk=user_id).count(),
            "receipts": Receipt.objects.filter(user_id=user_id).count(),
            "expenses": Expense.objects.filter(user_id=user_id).count(),
            "items": Item.objects.filter(expense__user_id=user_id).count(),
            "chat": ChatMessage.objects.filter(user_id=user_id).count(),
            "usage": AIUsage.objects.filter(user_id=user_id).count(),
            "consent": ConsentRecord.objects.filter(user_id=user_id).count(),
        }

    def test_deleting_removes_every_row_and_file_and_logs_out(self):
        alice_id, bob_before = self.alice.pk, self.counts(self.bob.pk)
        self.assertTrue(default_storage.exists(self.alice_image))
        self.client.force_login(self.alice)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/account/delete/", {"password": PASSWORD, "from": "account"})

        self.assertRedirects(response, "/account/deleted/")
        self.assertEqual(set(self.counts(alice_id).values()), {0})
        self.assertFalse(default_storage.exists(self.alice_image))
        # Bob is untouched.
        self.assertEqual(self.counts(self.bob.pk), bob_before)
        self.assertTrue(default_storage.exists(self.bob_image))
        # Logged out, and the confirmation page is public.
        self.assertTrue(self.client.get("/account/")["Location"].startswith("/login/"))
        self.assertContains(self.client.get("/account/deleted/"), "Your account has been deleted")

    def test_wrong_password_blocks_deletion(self):
        before = self.counts(self.alice.pk)
        self.client.force_login(self.alice)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/account/delete/", {"password": "wrong", "from": "account"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "The password is incorrect. Your account was not deleted.", status_code=400)
        self.assertEqual(self.counts(self.alice.pk), before)
        self.assertTrue(default_storage.exists(self.alice_image))
        self.assertEqual(self.client.get("/account/").status_code, 200)  # still logged in

    def test_empty_password_blocks_deletion(self):
        self.client.force_login(self.alice)
        response = self.client.post("/account/delete/", {"from": "account"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.alice.pk).exists())

    def test_withdraw_page_explains_and_leads_to_the_same_delete_flow(self):
        self.client.force_login(self.alice)
        html = self.client.get("/account/withdraw/").content.decode()
        self.assertIn("your data can no longer be processed", html)
        self.assertIn('action="/account/delete/"', html)
        self.assertIn('name="from" value="withdraw"', html)

        response = self.client.post("/account/delete/", {"password": "wrong", "from": "withdraw"})
        self.assertContains(response, "your data can no longer be processed", status_code=400)
        self.assertContains(response, "The password is incorrect.", status_code=400)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/account/delete/", {"password": PASSWORD, "from": "withdraw"})
        self.assertRedirects(response, "/account/deleted/")
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_delete_needs_post(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get("/account/delete/").status_code, 405)

    def test_account_page_has_the_three_sections(self):
        self.client.force_login(self.alice)
        html = self.client.get("/account/").content.decode()
        for text in ["Download my data", 'href="/account/export/"', "Withdraw consent", 'href="/account/withdraw/"',
                     "Delete my account", 'name="password"', "Terms of Service version 1.0"]:
            self.assertIn(text, html)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ReceiptFileDeletionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.receipt = make_receipt_with_file(self.user)
        self.name = self.receipt.image.name

    def test_deleting_a_receipt_deletes_its_file(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.receipt.delete()
        self.assertFalse(default_storage.exists(self.name))

    def test_queryset_delete_deletes_every_file(self):
        other = make_receipt_with_file(self.user).image.name
        with self.captureOnCommitCallbacks(execute=True):
            Receipt.objects.filter(user=self.user).delete()
        self.assertFalse(default_storage.exists(self.name))
        self.assertFalse(default_storage.exists(other))

    def test_deleting_the_user_cascades_to_the_file(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.user.delete()
        self.assertFalse(default_storage.exists(self.name))

    def test_rolled_back_delete_keeps_the_file(self):
        receipt_id = self.receipt.pk  # delete() sets the instance's pk to None
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            try:
                with transaction.atomic():
                    self.receipt.delete()
                    raise RuntimeError("roll back")
            except RuntimeError:
                pass
        self.assertEqual(callbacks, [])
        self.assertTrue(default_storage.exists(self.name))
        self.assertTrue(Receipt.objects.filter(pk=receipt_id).exists())

    def test_receipt_without_a_file_is_fine(self):
        receipt = Receipt.objects.create(user=self.user, image="")
        with self.captureOnCommitCallbacks(execute=True):
            receipt.delete()
