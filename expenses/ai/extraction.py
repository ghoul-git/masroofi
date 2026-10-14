import json
import os

from django.conf import settings
from django.utils import timezone

from expenses.ai.client import get_client
from expenses.ai.prompts import load_prompt


def extract_fields(raw_text: str, categories: list[str]) -> tuple[dict, dict]:
    """Turn raw OCR text into structured receipt fields.

    Returns (fields, usage), where usage is {"input_tokens", "output_tokens"}.
    """
    response = get_client().chat.completions.create(
        model=os.environ["OPENAI_MODEL"],
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": load_prompt(
                "receipt_extraction",
                categories=", ".join(categories),
                today=timezone.localdate().isoformat(),
                payment_platforms=", ".join(settings.PAYMENT_PLATFORMS),
            )},
            {"role": "user", "content": raw_text},
        ],
    )
    # Chat Completions names them prompt/completion tokens; usage can be missing.
    response_usage = getattr(response, "usage", None)
    usage = {
        "input_tokens": getattr(response_usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(response_usage, "completion_tokens", 0) or 0,
    }
    return json.loads(response.choices[0].message.content), usage
