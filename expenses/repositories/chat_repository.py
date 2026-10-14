from expenses.models import ChatMessage


def create(user, role, content, tools_used=None) -> ChatMessage:
    return ChatMessage.objects.create(user=user, role=role, content=content, tools_used=tools_used or [])


def list_for_user(user):
    return ChatMessage.objects.filter(user=user).order_by("created_at", "id")


def recent(user, limit) -> list[ChatMessage]:
    """The last `limit` messages, oldest first."""
    latest = ChatMessage.objects.filter(user=user).order_by("-created_at", "-id")[:limit]
    return list(reversed(latest))
