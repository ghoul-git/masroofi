import os

from openai import OpenAI

# Seconds to wait for one OpenAI request, and how many times to retry a failed one.
TIMEOUT = 30
MAX_RETRIES = 2

_client = None


def get_client() -> OpenAI:
    """One shared OpenAI client for extraction and the chat agent."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=TIMEOUT, max_retries=MAX_RETRIES)
    return _client
