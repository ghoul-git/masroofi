"""A fake OpenAI client for the agent tests, so no test calls the real API."""
import json
from types import SimpleNamespace
from unittest import mock


def function_call(name, arguments, call_id="call_1"):
    """A function_call output item. Pass a str as arguments to send it unencoded (e.g. invalid JSON)."""
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, call_id=call_id)


def _usage(tokens):
    """tokens is (input_tokens, output_tokens), or None for a response without usage."""
    if tokens is None:
        return None
    return SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1], total_tokens=sum(tokens))


def text_response(text, tokens=None):
    return SimpleNamespace(output=[SimpleNamespace(type="message")], output_text=text, usage=_usage(tokens))


def tool_response(*calls, tokens=None):
    return SimpleNamespace(output=list(calls), output_text="", usage=_usage(tokens))


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


class MockedReceiptAI:
    """Patches the three AI steps the receipt worker runs (preprocess, OCR, extraction),
    so no test loads EasyOCR or calls OpenAI, and records whether they were called."""

    def __init__(self, extracted=None, tokens=(120, 45), text="RAW TEXT", confidence=0.9, extract_error=None):
        if extracted is None:
            extracted = {"store_name": "Cozmo", "total": 5, "category": "Food", "items": []}
        self.patches = [
            mock.patch("expenses.ai.preprocessing.preprocess", return_value="image"),
            mock.patch("expenses.ai.ocr.read_text", return_value=(text, confidence)),
            mock.patch("expenses.ai.extraction.extract_fields", side_effect=extract_error,
                       return_value=(extracted, {"input_tokens": tokens[0], "output_tokens": tokens[1]})),
        ]

    def __enter__(self):
        self.preprocess, self.read_text, self.extract = [p.start() for p in self.patches]
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()

    def assert_nothing_called(self, test):
        test.assertFalse(self.preprocess.called or self.read_text.called or self.extract.called)


def process_next_receipt():
    """Do one step of the process_receipts worker: claim the oldest queued receipt and read it.

    Use inside MockedReceiptAI. Returns the receipt as stored afterwards.
    """
    from expenses.services import receipt_service

    receipt = receipt_service.claim_next_receipt()
    receipt_service.process_claimed_receipt(receipt)
    receipt.refresh_from_db()
    return receipt
