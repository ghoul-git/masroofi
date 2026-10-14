import logging
import time

from django.core.exceptions import ValidationError
from django.db import transaction

from expenses.ai import agent
from expenses.models import ChatMessage
from expenses.repositories import chat_repository
from expenses.services.exceptions import ServiceUnavailable

logger = logging.getLogger(__name__)

HISTORY_SIZE = 10
MAX_QUESTION_LENGTH = 1000


def ask(user, question) -> dict:
    """Answer a question about the user's expenses and save both messages.

    Returns {"answer", "tools_used", "response_time"} with the time in seconds.
    Nothing is saved when the assistant fails.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValidationError({"question": ["Please type a question."]})
    question = question.strip()
    if len(question) > MAX_QUESTION_LENGTH:
        raise ValidationError({"question": [f"Questions can be at most {MAX_QUESTION_LENGTH} characters."]})

    history = [{"role": m.role, "content": m.content} for m in chat_repository.recent(user, HISTORY_SIZE)]

    started = time.perf_counter()
    try:
        result = agent.answer(user, question, history)
    except Exception as e:
        logger.exception("Chat agent failed for user %s", user.pk)
        raise ServiceUnavailable("The assistant is not available right now. Please try again.") from e
    response_time = round(time.perf_counter() - started, 2)

    with transaction.atomic():
        chat_repository.create(user, ChatMessage.Role.USER, question)
        chat_repository.create(user, ChatMessage.Role.ASSISTANT, result["answer"], tools_used=result["tools_used"])

    return {
        "answer": result["answer"],
        "tools_used": result["tools_used"],
        "response_time": response_time,
    }


def get_history(user):
    return chat_repository.list_for_user(user)
