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
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        EXTRACTED = "extracted"
        CONFIRMED = "confirmed"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="receipts")
    image = models.ImageField(upload_to=receipt_image_path)
    raw_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    uploaded_at = models.DateTimeField(auto_now_add=True)
