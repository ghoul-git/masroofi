import os

from openai import OpenAI

# Seconds to wait for one OpenAI request, and how many times to retry a failed one.
TIMEOUT = 30
MAX_RETRIES = 2

# Setting value that leaves the reasoning parameter out, for models without reasoning.
REASONING_OFF = "off"

_client = None


def get_client() -> OpenAI:
    """One shared OpenAI client for extraction and the chat agent."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=TIMEOUT, max_retries=MAX_RETRIES)
    return _client


def reasoning_options(api: str, effort: str) -> dict:
    """The reasoning-effort argument for one OpenAI call, or {} when effort is "off".

    Chat Completions takes reasoning_effort="low"; the Responses API takes
    reasoning={"effort": "low"} (both checked against the installed openai SDK).
    """
    if not effort or effort == REASONING_OFF:
        return {}
    if api == "chat":
        return {"reasoning_effort": effort}
    return {"reasoning": {"effort": effort}}
