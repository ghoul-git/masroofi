import os
import uuid

from django.conf import settings
from django.db import models


def random_image_name(filename) -> str:
    """<random hex><original extension>: the original filename may contain personal details."""
    return f"{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"[:100]


def receipt_image_path(instance, filename):
    """No longer used: images were files on disk until migration 0012. Kept because the
    migrations that created that field (0003, 0009) refer to it by name."""
    return f"receipts/{instance.user_id}/{random_image_name(filename)}"


class Receipt(models.Model):
    """An uploaded receipt photo. The process_receipts worker reads it in the background:

    queued -> processing -> extracted or failed -> confirmed (when the user saves the expense).
    """

    class Status(models.TextChoices):
        UPLOADED = "uploaded"  # receipts from before background processing
        QUEUED = "queued"
        PROCESSING = "processing"
        EXTRACTED = "extracted"
        CONFIRMED = "confirmed"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="receipts")
    # The photo itself, stored in the database so the web server and the worker need no shared disk.
    # Cleared when the receipt is confirmed. Never part of an API response, the data export or the admin.
    image_data = models.BinaryField(null=True)
    image_content_type = models.CharField(max_length=50, blank=True)  # e.g. image/jpeg, from Pillow
    image_name = models.CharField(max_length=100, blank=True)  # random name + extension, not the uploaded filename
    raw_text = models.TextField(blank=True)  # OCR text with phone numbers and the customer name redacted
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    # The worker's result for the review form: the extracted fields and {field: message} warnings.
    extracted = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=dict, blank=True)
    ocr_confidence = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            # The worker takes the oldest queued receipt.
            models.Index(fields=["status", "uploaded_at"], name="receipt_status_uploaded"),
        ]
