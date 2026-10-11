import json
import os
from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from expenses.models import ChatMessage
from expenses.services import chat_service
from expenses.services.exceptions import ServiceUnavailable
from expenses.tests.factories import make_category, make_expense, make_user


def function_call(name, arguments, call_id="call_1"):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(arguments), call_id=call_id)


def text_response(text):
    return SimpleNamespace(output=[SimpleNamespace(type="message")], output_text=text)


def tool_response(*calls):
    return SimpleNamespace(output=list(calls), output_text="")


class FakeOpenAI:
    """Stands in for the OpenAI client: client.responses.create returns queued responses.

    Each request is recorded. The agent appends to its input list in place,
    so a copy of the input is kept per call.
    """

    def __init__(self, *queued, error=None):
        self.queued = list(queued)
        self.error = error
        self.requests = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append({**kwargs, "input": list(kwargs["input"])})
        if self.error:
            raise self.error
        return self.queued.pop(0)


def patch_openai(fake):
    return mock.patch("expenses.ai.agent.get_client", return_value=fake)


@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class AskTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        food = make_category("food")
        make_expense(self.alice, food, "Carrefour", "12.50", date="2026-10-02")
        make_expense(self.bob, food, "Bob Market", "500.00", date="2026-10-03")

    def test_saves_both_messages_and_returns_answer_tools_and_time(self):
        fake = FakeOpenAI(
            tool_response(function_call("get_spending_total", {
                "start_date": "2026-10-01", "end_date": "2026-10-31", "category": "food",
            })),
            text_response("You spent 12.50 JOD on food in October."),
        )
        with patch_openai(fake):
            result = chat_service.ask(self.alice, "  How much on food in October?  ")

        self.assertEqual(result["answer"], "You spent 12.50 JOD on food in October.")
        self.assertEqual(result["tools_used"], [{
            "name": "get_spending_total",
            "arguments": {"start_date": "2026-10-01", "end_date": "2026-10-31", "category": "food"},
        }])
        self.assertIsInstance(result["response_time"], float)
        self.assertGreaterEqual(result["response_time"], 0)

        messages = list(ChatMessage.objects.filter(user=self.alice).order_by("id").values_list("role", "content"))
        self.assertEqual(messages, [
            ("user", "How much on food in October?"),
            ("assistant", "You spent 12.50 JOD on food in October."),
        ])
        self.assertFalse(ChatMessage.objects.filter(user=self.bob).exists())

    def test_tools_run_for_the_asking_user_only(self):
        fake = FakeOpenAI(
            tool_response(function_call("get_spending_total", {
                "start_date": "2026-10-01", "end_date": "2026-10-31", "category": None,
            }, call_id="call_42")),
            text_response("12.50 JOD"),
        )
        with patch_openai(fake):
            chat_service.ask(self.alice, "Total in October?")

        tool_output = fake.requests[1]["input"][-1]
        self.assertEqual(tool_output["type"], "function_call_output")
        self.assertEqual(tool_output["call_id"], "call_42")
        output = json.loads(tool_output["output"])
        self.assertEqual(output["totals"], [{"currency": "JOD", "total": "12.50", "count": 1}])

    def test_sends_the_last_10_messages_as_history(self):
        for i in range(12):
            role = ChatMessage.Role.USER if i % 2 == 0 else ChatMessage.Role.ASSISTANT
            ChatMessage.objects.create(user=self.alice, role=role, content=f"message {i}")
        ChatMessage.objects.create(user=self.bob, role=ChatMessage.Role.USER, content="bob's secret question")

        fake = FakeOpenAI(text_response("Hello"))
        with patch_openai(fake):
            chat_service.ask(self.alice, "And now?")

        request = fake.requests[0]
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["input"], [
            *({"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"} for i in range(2, 12)),
            {"role": "user", "content": "And now?"},
        ])

    def test_answer_without_tools(self):
        fake = FakeOpenAI(text_response("I can only help with your expenses."))
        with patch_openai(fake):
            result = chat_service.ask(self.alice, "What's the weather?")
        self.assertEqual(result["tools_used"], [])
        self.assertEqual(ChatMessage.objects.filter(user=self.alice).count(), 2)

    def test_openai_failure_saves_nothing(self):
        fake = FakeOpenAI(error=RuntimeError("connection refused"))
        with patch_openai(fake), self.assertLogs("expenses.services.chat_service", "ERROR"):
            with self.assertRaises(ServiceUnavailable):
                chat_service.ask(self.alice, "Total in October?")
        self.assertFalse(ChatMessage.objects.exists())

    def test_empty_or_too_long_question_is_rejected_without_calling_openai(self):
        fake = FakeOpenAI()
        with patch_openai(fake):
            for question in ["", "   ", None, 42, "x" * 1001]:
                with self.subTest(question=str(question)[:10]):
                    with self.assertRaises(ValidationError):
                        chat_service.ask(self.alice, question)
        self.assertEqual(fake.requests, [])
        self.assertFalse(ChatMessage.objects.exists())

    def test_get_history_returns_own_messages_oldest_first(self):
        ChatMessage.objects.create(user=self.alice, role="user", content="first")
        ChatMessage.objects.create(user=self.bob, role="user", content="bob's")
        ChatMessage.objects.create(user=self.alice, role="assistant", content="second")
        self.assertEqual([m.content for m in chat_service.get_history(self.alice)], ["first", "second"])


@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class ChatApiTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.client.force_login(self.alice)

    def test_post_returns_answer(self):
        with patch_openai(FakeOpenAI(text_response("Hi"))):
            response = self.client.post("/api/chat/", {"question": "Hello"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "Hi")
        self.assertEqual(body["tools_used"], [])
        self.assertIsInstance(body["response_time"], float)

    def test_history_only_returns_own_messages(self):
        ChatMessage.objects.create(user=self.alice, role="user", content="mine")
        ChatMessage.objects.create(user=self.bob, role="user", content="bob's")
        response = self.client.get("/api/chat/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m["content"] for m in response.json()], ["mine"])

    def test_empty_question_returns_400(self):
        response = self.client.post("/api/chat/", {"question": " "}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("question", response.json())

    def test_openai_failure_returns_503(self):
        with patch_openai(FakeOpenAI(error=RuntimeError("down"))), self.assertLogs("expenses.services.chat_service", "ERROR"):
            response = self.client.post("/api/chat/", {"question": "Hello"}, content_type="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(ChatMessage.objects.exists())

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/chat/history/").status_code, 403)
        self.assertEqual(self.client.post("/api/chat/", {"question": "Hi"}, content_type="application/json").status_code, 403)
        self.assertEqual(self.client.get("/chat/").status_code, 302)
