"""Apply the data-minimization rules to receipts saved before they existed.

    python manage.py redact_existing          # shows the counts and asks first
    python manage.py redact_existing --yes    # no question

Redacts phone numbers and customer names in the stored OCR text (the same rules
as for new receipts, expenses.ai.redaction) and deletes the images of receipts
that have already been confirmed. Expenses and their items are not changed.
"""
from django.core.management.base import BaseCommand

from expenses.services import receipt_service


class Command(BaseCommand):
    help = "Redact phone numbers and customer names in stored receipt text and delete confirmed receipts' images."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")

    def handle(self, *args, yes, **options):
        plan = receipt_service.redaction_plan()
        texts, images = len(plan.texts), len(plan.image_receipt_ids)
        self.stdout.write(f"Receipts whose text has phone numbers or a customer name to redact: {texts}")
        self.stdout.write(f"Confirmed receipts whose image will be deleted: {images}")
        if not texts and not images:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        if not yes:
            answer = input("This cannot be undone. Continue? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                self.stdout.write("Cancelled. Nothing was changed.")
                return

        receipt_service.apply_redaction_plan(plan)
        self.stdout.write(self.style.SUCCESS(f"Redacted the text of {texts} receipt(s) and deleted {images} image(s)."))
