import os
import uuid

from django.conf import settings
from django.db import models


def receipt_image_path(instance, filename):
    """receipts/<user_id>/<random hex><original extension>.

    The random name means file paths cannot be guessed, and the original
    filename (which may contain personal details) is not kept.
    """
    extension = os.path.splitext(filename)[1]
    return f"receipts/{instance.user_id}/{uuid.uuid4().hex}{extension}"


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
    # Emptied when the receipt is confirmed: the image file is deleted and only the expense is kept.
    image = models.ImageField(upload_to=receipt_image_path, blank=True)
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
