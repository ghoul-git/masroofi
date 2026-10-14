from django.conf import settings
from django.db import models


class ConsentRecord(models.Model):
    """The user accepted these Terms and Privacy Policy versions (and confirmed being 18+) at this time.

    Rows are only added, never changed, so they form a history of what each user agreed to.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consent_records")
    terms_version = models.CharField(max_length=20)
    privacy_version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "terms_version", "privacy_version"], name="consent_user_versions"),
        ]
