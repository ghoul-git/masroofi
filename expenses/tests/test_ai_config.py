"""Prompts in files, the shared OpenAI client, the local timezone and bad tool-call JSON."""
import datetime
import json
import os
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from expenses.ai import agent, client, extraction
from expenses.ai.prompts import PROMPTS_DIR, load_prompt
from expenses.tests.factories import make_user
from expenses.tests.fakes import FakeOpenAI, function_call, patch_openai, text_response, tool_response


class LoadPromptTests(SimpleTestCase):
    def test_both_prompt_files_exist(self):
        for name in ["chat_agent", "receipt_extraction"]:
            self.assertTrue((PROMPTS_DIR / f"{name}.md").is_file(), name)

    def test_values_are_filled_in(self):
        self.assertIn("Today's date is 2026-10-14.", load_prompt("chat_agent", today="2026-10-14"))
        self.assertIn("exactly one of: Food, Bills", load_prompt("receipt_extraction", categories="Food, Bills"))

    def test_no_placeholder_is_left_unfilled(self):
        for text in [load_prompt("chat_agent", today="X"), load_prompt("receipt_extraction", categories="X")]:
            self.assertNotRegex(text, r"\{\w+\}")
            self.assertNotIn("CATEGORY_LIST", text)

    def test_missing_value_raises(self):
        with self.assertRaises(KeyError):
            load_prompt("chat_agent")


class SharedClientTests(SimpleTestCase):
    def setUp(self):
        client._client = None
        self.addCleanup(setattr, client, "_client", None)

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_client_is_created_once_with_timeout_and_retries(self):
        with mock.patch("expenses.ai.client.OpenAI") as openai_class:
            first, second = client.get_client(), client.get_client()
        openai_class.assert_called_once_with(api_key="test-key", timeout=30, max_retries=2)
        self.assertIs(first, second)

    def test_extraction_and_agent_use_the_shared_client(self):
        self.assertIs(extraction.get_client, client.get_client)
        self.assertIs(agent.get_client, client.get_client)
        self.assertFalse(hasattr(extraction, "_client"))

    @mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
    def test_extraction_sends_the_prompt_file_with_categories(self):
        create = mock.Mock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"store_name": "Cozmo"}'))],
            usage=SimpleNamespace(prompt_tokens=310, completion_tokens=42, total_tokens=352),
        ))
        fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with mock.patch("expenses.ai.extraction.get_client", return_value=fake):
            result, usage = extraction.extract_fields("RAW", ["Bills", "Food"])

        self.assertEqual(result, {"store_name": "Cozmo"})
        self.assertEqual(usage, {"input_tokens": 310, "output_tokens": 42})
        messages = create.call_args.kwargs["messages"]
        self.assertEqual(messages[0]["content"], load_prompt("receipt_extraction", categories="Bills, Food"))
        self.assertEqual(messages[1], {"role": "user", "content": "RAW"})


@mock.patch.dict(os.environ, {"OPENAI_MODEL": "test-model"})
class AgentTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_time_zone_is_amman(self):
        self.assertEqual(settings.TIME_ZONE, "Asia/Amman")

    def test_today_is_the_local_date_in_amman_not_utc(self):
        # 22:30 UTC on the 14th is already 01:30 on the 15th in Amman (UTC+3).
        utc_now = datetime.datetime(2026, 10, 14, 22, 30, tzinfo=datetime.timezone.utc)
        fake = FakeOpenAI(text_response("Hi"))
        with patch_openai(fake), mock.patch("django.utils.timezone.now", return_value=utc_now):
            agent.answer(self.user, "Hello", [])
        self.assertIn("Today's date is 2026-10-15.", fake.requests[0]["instructions"])

    def test_invalid_json_arguments_are_returned_as_an_error_so_the_model_can_retry(self):
        arguments = {"start_date": "2026-10-01", "end_date": "2026-10-31", "category": None}
        fake = FakeOpenAI(
            tool_response(function_call("get_spending_total", '{"start_date": "2026-10-01",', call_id="bad")),
            tool_response(function_call("get_spending_total", arguments, call_id="good")),
            text_response("You spent nothing."),
        )
        with patch_openai(fake):
            result = agent.answer(self.user, "Total in October?", [])

        error_output = fake.requests[1]["input"][-1]
        self.assertEqual(error_output["type"], "function_call_output")
        self.assertEqual(error_output["call_id"], "bad")
        self.assertEqual(json.loads(error_output["output"]), {"error": "invalid JSON arguments"})

        retry_output = fake.requests[2]["input"][-1]
        self.assertEqual(retry_output["call_id"], "good")
        self.assertEqual(json.loads(retry_output["output"])["totals"], [])

        self.assertEqual(result["answer"], "You spent nothing.")
        self.assertEqual(result["tools_used"], [{"name": "get_spending_total", "arguments": arguments}])
