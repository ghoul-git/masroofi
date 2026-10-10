import json
import os

from openai import OpenAI

_client = None

SYSTEM_PROMPT = """You extract structured data from receipt text produced by OCR.
The text may be noisy and may mix Arabic and English.
Return only a JSON object with these keys:
- store_name: string
- date: string in YYYY-MM-DD format, or null if not found
- total: number, the final amount paid, or null if not found
- currency: 3-letter code, use "JOD" if not stated
- category: exactly one of: CATEGORY_LIST
- items: list of objects with name (string), quantity (number), price (number)
Do not invent values. Use null when a field is not present in the text."""


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def extract_fields(raw_text: str, categories: list[str]) -> dict:
    """Turn raw OCR text into structured receipt fields."""
    response = get_client().chat.completions.create(
        model=os.environ["OPENAI_MODEL"],
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.replace("CATEGORY_LIST", ", ".join(categories))},
            {"role": "user", "content": raw_text},
        ],
    )
    return json.loads(response.choices[0].message.content)
