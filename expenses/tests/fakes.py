"""A fake OpenAI client for the agent tests, so no test calls the real API."""
import json
from types import SimpleNamespace
from unittest import mock


def function_call(name, arguments, call_id="call_1"):
    """A function_call output item. Pass a str as arguments to send it unencoded (e.g. invalid JSON)."""
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, call_id=call_id)


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
