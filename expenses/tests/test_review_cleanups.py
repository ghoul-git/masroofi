"""Shared validation module, removed repository functions, CSS file, registration and category names."""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from expenses.models import Category
from expenses.repositories import receipt_repository
from expenses.services import expense_service, receipt_service, user_service, validation
from expenses.tests.factories import ALL_CONSENTS

User = get_user_model()


class ValidationModuleTests(SimpleTestCase):
    def test_both_services_use_the_shared_helpers(self):
        for name in ["parse_amount", "parse_date_value", "MAX_AMOUNT", "MAX_QUANTITY", "DEFAULT_CURRENCY"]:
            with self.subTest(name=name):
                self.assertIs(getattr(expense_service, name), getattr(validation, name))
                self.assertIs(getattr(receipt_service, name), getattr(validation, name))
        self.assertEqual(expense_service.parse_amount.__module__, "expenses.services.validation")

    def test_parse_amount(self):
        self.assertEqual(validation.parse_amount("12.3455", validation.MAX_AMOUNT), Decimal("12.346"))
        for bad in ["-1", "abc", "", None, True, "NaN", "1000000000"]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validation.parse_amount(bad, validation.MAX_AMOUNT)

    def test_parse_date_value(self):
        self.assertEqual(str(validation.parse_date_value("2026-10-14")), "2026-10-14")
        for bad in ["2026-02-30", "14/10/2026", None, 5]:
            with self.subTest(value=bad):
                self.assertIsNone(validation.parse_date_value(bad))


class ReceiptRepositoryTests(SimpleTestCase):
    def test_unused_delete_is_removed(self):
        # list_for_user was removed in the code review and brought back for the data export.
        self.assertFalse(hasattr(receipt_repository, "delete"))


class StylesheetTests(TestCase):
    def test_css_file_exists_and_base_links_it_instead_of_inline_styles(self):
        self.assertIsNotNone(finders.find("expenses/css/main.css"))
        html = self.client.get("/login/").content.decode()
        self.assertIn("expenses/css/main.css", html)
        self.assertNotIn("<style", html)


class RegisterUserTests(TestCase):
    def test_duplicate_username_is_rejected(self):
        user_service.register_user("alice", "", "a-strong-pass-123", ALL_CONSENTS)
        with self.assertRaises(ValidationError) as ctx:
            user_service.register_user("alice", "", "a-strong-pass-123", ALL_CONSENTS)
        self.assertEqual(ctx.exception.messages, ["Username is already taken."])

    def test_duplicate_caught_by_the_database_gives_the_same_error(self):
        # Simulate two sign-ups racing: the existence check passes, the insert hits the unique constraint.
        User.objects.create_user(username="alice", password="x")
        with mock.patch.object(User.objects, "filter") as filter_:
            filter_.return_value.exists.return_value = False
            with self.assertRaises(ValidationError) as ctx:
                user_service.register_user("alice", "", "a-strong-pass-123", ALL_CONSENTS)
        self.assertEqual(ctx.exception.messages, ["Username is already taken."])
        # The failed insert was rolled back to a savepoint, so the connection still works.
        self.assertEqual(User.objects.filter(username="alice").count(), 1)

    def test_invalid_email_is_rejected(self):
        for email in ["not-an-email", "a@", "@b.com", "a b@c.com"]:
            with self.subTest(email=email), self.assertRaises(ValidationError) as ctx:
                user_service.register_user("bob", email, "a-strong-pass-123", ALL_CONSENTS)
            self.assertEqual(ctx.exception.messages, ["Enter a valid email address."])
        self.assertFalse(User.objects.filter(username="bob").exists())

    def test_valid_or_empty_email_is_accepted(self):
        self.assertEqual(user_service.register_user("bob", "bob@example.com", "a-strong-pass-123", ALL_CONSENTS).email, "bob@example.com")
        self.assertEqual(user_service.register_user("carol", "", "a-strong-pass-123", ALL_CONSENTS).email, "")

    def test_register_page_shows_the_email_error(self):
        response = self.client.post("/register/", {
            "username": "dan", "email": "nope", "password": "a-strong-pass-123",
            "accept_terms": "on", "accept_privacy": "on", "confirm_age": "on",
        })
        self.assertContains(response, "Enter a valid email address.")


class CategoryNameConstraintTests(TestCase):
    def test_names_differing_only_in_case_are_rejected(self):
        self.assertTrue(Category.objects.filter(name="Food").exists())  # created by the 0002 migration
        for name in ["food", "FOOD", "fOoD"]:
            with self.subTest(name=name), self.assertRaises(IntegrityError), transaction.atomic():
                Category.objects.create(name=name)

    def test_new_names_are_still_allowed(self):
        Category.objects.create(name="Education")
        self.assertTrue(Category.objects.filter(name="Education").exists())
