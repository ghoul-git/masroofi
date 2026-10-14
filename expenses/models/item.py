from django.core.validators import MinValueValidator
from django.db import models


class Item(models.Model):
    expense = models.ForeignKey("expenses.Expense", on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    # 3 decimal places: JOD prices are in fils, and quantities can be weights such as 0.750 kg.
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1, validators=[MinValueValidator(0)])
    price = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
