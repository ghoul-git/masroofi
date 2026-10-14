import json
import os

from expenses.ai.client import get_client
from expenses.ai.prompts import load_prompt


def extract_fields(raw_text: str, categories: list[str]) -> dict:
    """Turn raw OCR text into structured receipt fields."""
    response = get_client().chat.completions.create(
        model=os.environ["OPENAI_MODEL"],
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": load_prompt("receipt_extraction", categories=", ".join(categories))},
            {"role": "user", "content": raw_text},
        ],
    )
    return json.loads(response.choices[0].message.content)
