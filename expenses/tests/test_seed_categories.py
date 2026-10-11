from importlib import import_module

from django.apps import apps
from django.test import TestCase

from expenses.models import Category

seed = import_module("expenses.migrations.0002_seed_categories")


class SeedCategoriesMigrationTests(TestCase):
    def test_migrate_creates_the_seven_categories(self):
        self.assertEqual(
            sorted(Category.objects.values_list("name", flat=True)),
            ["Bills", "Entertainment", "Food", "Health", "Other", "Shopping", "Transport"],
        )

    def test_running_again_does_not_duplicate_existing_categories_in_any_case(self):
        # A database created before this migration has lowercase names.
        Category.objects.all().delete()
        Category.objects.create(name="food")
        Category.objects.create(name="transport")

        seed.create_categories(apps, None)
        seed.create_categories(apps, None)

        names = sorted(Category.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Bills", "Entertainment", "Health", "Other", "Shopping", "food", "transport"])
