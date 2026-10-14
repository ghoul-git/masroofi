from django.db import models
from django.db.models.functions import Lower


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        constraints = [
            # unique=True alone allows both "Food" and "food".
            models.UniqueConstraint(Lower("name"), name="unique_category_name_ci"),
        ]

    def __str__(self):
        return self.name
