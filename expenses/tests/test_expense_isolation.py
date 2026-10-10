from decimal import Decimal

from django.test import TestCase

from expenses.models import Expense, Item, Receipt
from expenses.services import expense_service
from expenses.tests.factories import make_category, make_expense, make_receipt, make_user


class ExpenseServiceIsolationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        category = make_category()
        self.alice_expense = make_expense(self.alice, category, store_name="Alice's shop", total="20.00")
        self.bob_expense = make_expense(self.bob, category, store_name="Bob's shop", total="30.00")

    def test_list_only_returns_own_expenses(self):
        self.assertEqual(list(expense_service.list_expenses(self.alice)), [self.alice_expense])
        self.assertEqual(list(expense_service.list_expenses(self.bob)), [self.bob_expense])

    def test_cannot_get_another_users_expense(self):
        with self.assertRaises(Expense.DoesNotExist):
            expense_service.get_expense(self.alice, self.bob_expense.pk)

    def test_cannot_update_another_users_expense(self):
        with self.assertRaises(Expense.DoesNotExist):
            expense_service.update_expense(self.alice, self.bob_expense.pk, {"total": "0", "items": []})
        self.bob_expense.refresh_from_db()
        self.assertEqual(self.bob_expense.total, Decimal("30.00"))
        self.assertEqual(self.bob_expense.items.count(), 1)

    def test_cannot_delete_another_users_expense(self):
        with self.assertRaises(Expense.DoesNotExist):
            expense_service.delete_expense(self.alice, self.bob_expense.pk)
        self.assertTrue(Expense.objects.filter(pk=self.bob_expense.pk).exists())

    def test_owner_can_update_and_delete(self):
        updated = expense_service.update_expense(self.alice, self.alice_expense.pk, {
            "total": "25",
            "items": [{"name": "Rice", "quantity": "1", "price": "25"}],
        })
        self.assertEqual(updated.total, Decimal("25.00"))
        self.assertEqual([i.name for i in updated.items.all()], ["Rice"])

        expense_service.delete_expense(self.alice, self.alice_expense.pk)
        self.assertFalse(Expense.objects.filter(pk=self.alice_expense.pk).exists())
        self.assertFalse(Item.objects.filter(expense_id=self.alice_expense.pk).exists())


class ExpenseApiIsolationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.category = make_category()
        self.alice_expense = make_expense(self.alice, self.category, store_name="Alice's shop")
        self.bob_expense = make_expense(self.bob, self.category, store_name="Bob's shop", total="30.00")
        self.client.force_login(self.alice)

    def test_list_only_returns_own_expenses(self):
        response = self.client.get("/api/expenses/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e["store_name"] for e in response.json()], ["Alice's shop"])

    def test_patch_another_users_expense_returns_404(self):
        response = self.client.patch(
            f"/api/expenses/{self.bob_expense.pk}/", {"total": "0"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)
        self.bob_expense.refresh_from_db()
        self.assertEqual(self.bob_expense.total, Decimal("30.00"))

    def test_delete_another_users_expense_returns_404(self):
        response = self.client.delete(f"/api/expenses/{self.bob_expense.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Expense.objects.filter(pk=self.bob_expense.pk).exists())

    def test_confirm_another_users_receipt_returns_404(self):
        receipt = make_receipt(self.bob)
        response = self.client.post(f"/api/receipts/{receipt.pk}/confirm/", {
            "store_name": "X", "date": "2026-10-05", "total": "1", "category": self.category.pk,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 404)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, Receipt.Status.EXTRACTED)

    def test_owner_can_patch_and_delete(self):
        response = self.client.patch(
            f"/api/expenses/{self.alice_expense.pk}/", {"total": "-1"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("total", response.json())

        response = self.client.patch(
            f"/api/expenses/{self.alice_expense.pk}/", {"store_name": "Renamed"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["store_name"], "Renamed")

        response = self.client.delete(f"/api/expenses/{self.alice_expense.pk}/")
        self.assertEqual(response.status_code, 204)

    def test_endpoints_require_login(self):
        self.client.logout()
        receipt = make_receipt(self.alice)
        for method, url in [
            ("get", "/api/expenses/"),
            ("patch", f"/api/expenses/{self.alice_expense.pk}/"),
            ("delete", f"/api/expenses/{self.alice_expense.pk}/"),
            ("post", "/api/receipts/"),
            ("post", f"/api/receipts/{receipt.pk}/confirm/"),
        ]:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)
