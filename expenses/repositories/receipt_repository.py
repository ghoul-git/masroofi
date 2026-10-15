from expenses.models import Receipt


def create(user, image) -> Receipt:
    return Receipt.objects.create(user=user, image=image, status=Receipt.Status.QUEUED)


def get(user, receipt_id) -> Receipt | None:
    return Receipt.objects.filter(user=user, pk=receipt_id).first()


def get_for_update(user, receipt_id) -> Receipt | None:
    """Lock the receipt row until the surrounding transaction ends."""
    return Receipt.objects.select_for_update().filter(user=user, pk=receipt_id).first()


def update(user, receipt_id, **fields) -> int:
    return Receipt.objects.filter(user=user, pk=receipt_id).update(**fields)


def list_for_user(user):
    return Receipt.objects.filter(user=user).order_by("uploaded_at", "id")


# For the process_receipts worker and the redact_existing command, which work across users.


def next_queued_for_update() -> Receipt | None:
    """Lock the oldest queued receipt, skipping rows another worker has already locked."""
    return (Receipt.objects.select_for_update(skip_locked=True)
            .filter(status=Receipt.Status.QUEUED).order_by("uploaded_at", "id").first())


def update_by_id(receipt_id, **fields) -> int:
    return Receipt.objects.filter(pk=receipt_id).update(**fields)


def update_if_processing(receipt_id, **fields) -> int:
    """Update only while the receipt is still processing, so a receipt the user has
    confirmed in the meantime is never overwritten by the worker."""
    return Receipt.objects.filter(pk=receipt_id, status=Receipt.Status.PROCESSING).update(**fields)


def requeue_processing_started_before(cutoff) -> int:
    return Receipt.objects.filter(
        status=Receipt.Status.PROCESSING, processing_started_at__lt=cutoff,
    ).update(status=Receipt.Status.QUEUED, processing_started_at=None)


def with_raw_text():
    return Receipt.objects.exclude(raw_text="").only("id", "raw_text").order_by("id")


def confirmed_with_image():
    return Receipt.objects.filter(status=Receipt.Status.CONFIRMED).exclude(image="").only("id", "image").order_by("id")
