from django.db import migrations

CATEGORIES = ["Food", "Transport", "Bills", "Shopping", "Health", "Entertainment", "Other"]


def create_categories(apps, schema_editor):
    Category = apps.get_model("expenses", "Category")
    for name in CATEGORIES:
        # Matched case-insensitively so an existing "food" is reused instead of
        # adding a second "Food" (the unique constraint on name is case-sensitive).
        Category.objects.get_or_create(name__iexact=name, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0001_initial"),
    ]

    operations = [
        # Reversing does not delete the categories: expenses may already use them.
        migrations.RunPython(create_categories, migrations.RunPython.noop),
    ]
