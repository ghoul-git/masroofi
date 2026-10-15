from django.conf import settings
from django.db import models


class AIUsage(models.Model):
    """One row per receipt processed and per chat question answered, with the OpenAI tokens used."""

    class Kind(models.TextChoices):
        RECEIPT = "receipt"
        CHAT = "chat"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_usage")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # The receipt this row counts. The row is created when the receipt is queued and the
    # worker fills in the tokens; it stays (for the limits) if the receipt is deleted.
    receipt = models.ForeignKey("Receipt", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # Per-user limits count by user, kind and period; the global cap counts by period.
            models.Index(fields=["user", "kind", "created_at"], name="aiusage_user_kind_created"),
            models.Index(fields=["created_at"], name="aiusage_created"),
        ]
