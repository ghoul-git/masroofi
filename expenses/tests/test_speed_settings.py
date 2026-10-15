"""Reasoning effort on both OpenAI calls and downscaling before OCR. OpenAI is faked."""
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from expenses.ai import agent, extraction
from expenses.ai.client import reasoning_options
from expenses.ai.preprocessing import preprocess
from expenses.tests.factories import make_user
from expenses.tests.fakes import FakeOpenAI, patch_openai, text_response


def fake_chat_client():
    create = mock.Mock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))], usage=None,
    ))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class ReasoningEffortTests(TestCase):
    def test_defaults(self):
        self.assertEqual(settings.OPENAI_EXTRACTION_REASONING, "none")
        self.assertEqual(settings.OPENAI_AGENT_REASONING, "low")

    def test_parameter_names_match_the_installed_openai_sdk(self):
        import inspect

        from openai.resources.chat.completions import Completions
        from openai.resources.responses import Responses

        self.assertIn("reasoning_effort", inspect.signature(Completions.create).parameters)
        self.assertIn("reasoning", inspect.signature(Responses.create).parameters)
        self.assertEqual(reasoning_options("chat", "low"), {"reasoning_effort": "low"})
        self.assertEqual(reasoning_options("responses", "low"), {"reasoning": {"effort": "low"}})

    @override_settings(OPENAI_EXTRACTION_REASONING="minimal")
    def test_extraction_sends_its_reasoning_effort(self):
        client, create = fake_chat_client()
        with mock.patch("expenses.ai.extraction.get_client", return_value=client):
            extraction.extract_fields("RAW", ["Food"])
        self.assertEqual(create.call_args.kwargs["reasoning_effort"], "minimal")
        self.assertNotIn("reasoning", create.call_args.kwargs)

    @override_settings(OPENAI_AGENT_REASONING="medium")
    def test_agent_sends_its_reasoning_effort_on_every_call(self):
        fake = FakeOpenAI(text_response("Hi"))
        with patch_openai(fake):
            agent.answer(make_user(), "Hello", [])
        self.assertEqual(fake.requests[0]["reasoning"], {"effort": "medium"})
        self.assertNotIn("reasoning_effort", fake.requests[0])

    @override_settings(OPENAI_EXTRACTION_REASONING="off", OPENAI_AGENT_REASONING="off")
    def test_off_leaves_the_parameter_out(self):
        client, create = fake_chat_client()
        with mock.patch("expenses.ai.extraction.get_client", return_value=client):
            extraction.extract_fields("RAW", ["Food"])
        self.assertNotIn("reasoning_effort", create.call_args.kwargs)

        fake = FakeOpenAI(text_response("Hi"))
        with patch_openai(fake):
            agent.answer(make_user(), "Hello", [])
        self.assertNotIn("reasoning", fake.requests[0])


class DownscaleBeforeOcrTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)
        super().tearDownClass()

    def photo(self, width, height):
        path = os.path.join(self.folder, f"{width}x{height}.png")
        cv2.imwrite(path, np.full((height, width, 3), 255, dtype=np.uint8))
        return path

    def test_default_longest_side_is_1280(self):
        self.assertEqual(settings.OCR_MAX_SIDE, 1280)

    def test_large_photos_are_scaled_to_the_setting_keeping_the_shape(self):
        self.assertEqual(preprocess(self.photo(3000, 4000)).shape, (1280, 960))
        self.assertEqual(preprocess(self.photo(2560, 1000)).shape, (500, 1280))

    @override_settings(OCR_MAX_SIDE=800)
    def test_setting_controls_the_size(self):
        self.assertEqual(max(preprocess(self.photo(1600, 1200)).shape), 800)

    def test_small_photos_are_not_enlarged(self):
        self.assertEqual(preprocess(self.photo(600, 900)).shape, (900, 600))
