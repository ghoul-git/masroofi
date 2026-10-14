from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from expenses.models import Receipt


@receiver(post_delete, sender=Receipt)
def delete_receipt_image(sender, instance, **kwargs):
    """Delete the image file whenever a Receipt row is deleted.

    This also runs for receipts deleted by a cascade (such as deleting the user)
    and by QuerySet.delete(). The file is removed only after the transaction
    commits, so a rolled-back delete never loses an image.
    """
    if not instance.image:
        return
    storage, name = instance.image.storage, instance.image.name
    transaction.on_commit(lambda: storage.delete(name))
