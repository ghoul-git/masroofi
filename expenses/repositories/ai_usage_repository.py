from expenses.models import AIUsage


def create(user, kind, input_tokens=0, output_tokens=0, receipt=None) -> AIUsage:
    return AIUsage.objects.create(user=user, kind=kind, input_tokens=input_tokens, output_tokens=output_tokens,
                                  receipt=receipt)


def set_tokens_for_receipt(receipt_id, input_tokens, output_tokens) -> int:
    return AIUsage.objects.filter(receipt_id=receipt_id).update(input_tokens=input_tokens, output_tokens=output_tokens)


def count_for_user(user, kind, since) -> int:
    return AIUsage.objects.filter(user=user, kind=kind, created_at__gte=since).count()


def count_all_since(since) -> int:
    """Every user's AI requests since the given time, for the global daily cap."""
    return AIUsage.objects.filter(created_at__gte=since).count()


def list_for_user(user):
    return AIUsage.objects.filter(user=user).order_by("created_at", "id")
