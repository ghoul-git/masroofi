from expenses.models import Receipt


def create(user, image) -> Receipt:
    return Receipt.objects.create(user=user, image=image)


def get(user, receipt_id) -> Receipt | None:
    return Receipt.objects.filter(user=user, pk=receipt_id).first()


def get_for_update(user, receipt_id) -> Receipt | None:
    """Lock the receipt row until the surrounding transaction ends."""
    return Receipt.objects.select_for_update().filter(user=user, pk=receipt_id).first()


def update(user, receipt_id, **fields) -> int:
    return Receipt.objects.filter(user=user, pk=receipt_id).update(**fields)


def list_for_user(user):
    return Receipt.objects.filter(user=user).order_by("uploaded_at", "id")
