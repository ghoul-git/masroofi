import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from expenses.models import AIUsage, ChatMessage, ConsentRecord, Expense, Item, Receipt
from expenses.tests.factories import IMAGE_BYTES, PASSWORD, make_category, make_expense, make_receipt, make_user

User = get_user_model()


def make_receipt_with_image(user, raw_text="RAW"):
    receipt = make_receipt(user)
    Receipt.objects.filter(pk=receipt.pk).update(raw_text=raw_text)
    return receipt


def images_stored(user_id) -> int:
    return Receipt.objects.filter(user_id=user_id, image_data__isnull=False).count()


class UserDataMixin:
    """Alice and Bob each have a receipt (with its image), an expense with items, chat and usage rows."""

    def setUp(self):
        food = make_category("food")
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        for user, store in [(self.alice, "Alice Market"), (self.bob, "Bob Market")]:
            receipt = make_receipt_with_image(user, raw_text=f"{store} receipt text")
            expense = make_expense(user, food, store, total="12.50")
            Expense.objects.filter(pk=expense.pk).update(receipt=receipt)
            ChatMessage.objects.create(user=user, role="user", content=f"{store}: كم صرفت؟")
            ChatMessage.objects.create(user=user, role="assistant", content="12.50 JOD",
                                       tools_used=[{"name": "get_spending_total", "arguments": {}}])
            AIUsage.objects.create(user=user, kind="chat", input_tokens=300, output_tokens=20)


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

    def test_export_never_contains_the_image(self):
        response, data = self.export()
        [receipt] = data["receipts"]
        self.assertNotIn("image_data", receipt)
        self.assertEqual((receipt["image_name"], receipt["image_stored"]), ("0123abcd.jpg", True))
        self.assertNotIn(b"fake jpeg bytes", response.content)
        self.assertNotIn(IMAGE_BYTES.hex(), response.content.decode())

    def test_arabic_is_kept_readable(self):
        response, _ = self.export()
        self.assertIn("كم صرفت؟", response.content.decode("utf-8"))

    def test_export_requires_login(self):
        self.assertTrue(self.client.get("/account/export/")["Location"].startswith("/login/"))


class DeleteAccountTests(UserDataMixin, TestCase):
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

    def test_deleting_removes_every_row_and_image_and_logs_out(self):
        alice_id, bob_before = self.alice.pk, self.counts(self.bob.pk)
        self.assertEqual(images_stored(alice_id), 1)
        self.client.force_login(self.alice)

        response = self.client.post("/account/delete/", {"password": PASSWORD, "from": "account"})

        self.assertRedirects(response, "/account/deleted/")
        self.assertEqual(set(self.counts(alice_id).values()), {0})
        self.assertEqual(images_stored(alice_id), 0)
        # Bob is untouched.
        self.assertEqual(self.counts(self.bob.pk), bob_before)
        self.assertEqual(images_stored(self.bob.pk), 1)
        # Logged out, and the confirmation page is public.
        self.assertTrue(self.client.get("/account/")["Location"].startswith("/login/"))
        self.assertContains(self.client.get("/account/deleted/"), "Your account has been deleted")

    def test_wrong_password_blocks_deletion(self):
        before = self.counts(self.alice.pk)
        self.client.force_login(self.alice)
        response = self.client.post("/account/delete/", {"password": "wrong", "from": "account"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "The password is incorrect. Your account was not deleted.", status_code=400)
        self.assertEqual(self.counts(self.alice.pk), before)
        self.assertEqual(images_stored(self.alice.pk), 1)
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
