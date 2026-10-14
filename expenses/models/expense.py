from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Expense(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="expenses")
    receipt = models.OneToOneField("expenses.Receipt", on_delete=models.SET_NULL, null=True, blank=True, related_name="expense")
    category = models.ForeignKey("expenses.Category", on_delete=models.PROTECT, related_name="expenses")
    store_name = models.CharField(max_length=200)
    date = models.DateField()
    # 3 decimal places: the Jordanian dinar has 1000 fils.
    total = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="JOD")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
