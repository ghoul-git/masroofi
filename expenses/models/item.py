from django.core.validators import MinValueValidator
from django.db import models


class Item(models.Model):
    expense = models.ForeignKey("expenses.Expense", on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1, validators=[MinValueValidator(0)])
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
