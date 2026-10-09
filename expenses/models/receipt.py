from django.conf import settings
from django.db import models


class Receipt(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        EXTRACTED = "extracted"
        CONFIRMED = "confirmed"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="receipts")
    image = models.ImageField(upload_to="receipts/")
    raw_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    uploaded_at = models.DateTimeField(auto_now_add=True)
