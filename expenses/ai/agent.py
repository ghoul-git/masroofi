import json
import os
from datetime import date

from expenses.ai.extraction import get_client
from expenses.ai.tools import TOOL_SCHEMAS, run_tool

MAX_STEPS = 5

SYSTEM_PROMPT = """You are Masroofi, an assistant that answers questions about the user's own expenses.
Today's date is {today}. The default currency is JOD.
Rules:
- Always call a tool to get numbers. Never guess and never answer from memory.
- If the tools return no data, say so plainly.
- Only answer questions about the user's expenses. Politely decline anything else.
- Reply in the language the user wrote in. Keep answers short and state the exact amounts."""


def answer(user, question: str, history: list[dict]) -> dict:
    """Run the tool-calling loop and return the answer plus the tools used."""
    input_items = [*history, {"role": "user", "content": question}]
    tools_used = []

    for _ in range(MAX_STEPS):
        response = get_client().responses.create(
            model=os.environ["OPENAI_MODEL"],
            instructions=SYSTEM_PROMPT.format(today=date.today().isoformat()),
            input=input_items,
            tools=TOOL_SCHEMAS,
        )
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return {"answer": response.output_text, "tools_used": tools_used}

        input_items += response.output
        for call in calls:
            arguments = json.loads(call.arguments)
            result = run_tool(user, call.name, arguments)
            tools_used.append({"name": call.name, "arguments": arguments})
            input_items.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(result, default=str),
            })

    return {"answer": "Sorry, I could not work that out. Please rephrase the question.", "tools_used": tools_used}