import json
import os

from django.utils import timezone

from expenses.ai.client import get_client
from expenses.ai.prompts import load_prompt
from expenses.ai.tools import TOOL_SCHEMAS, run_tool

MAX_STEPS = 5


def _add_usage(total: dict, response) -> None:
    usage = getattr(response, "usage", None)  # can be missing
    total["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
    total["output_tokens"] += getattr(usage, "output_tokens", 0) or 0


def answer(user, question: str, history: list[dict]) -> dict:
    """Run the tool-calling loop and return the answer, the tools used, and the
    token usage summed over every model call in the loop."""
    input_items = [*history, {"role": "user", "content": question}]
    tools_used = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    for _ in range(MAX_STEPS):
        response = get_client().responses.create(
            model=os.environ["OPENAI_MODEL"],
            instructions=load_prompt("chat_agent", today=timezone.localdate().isoformat()),
            input=input_items,
            tools=TOOL_SCHEMAS,
        )
        _add_usage(usage, response)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return {"answer": response.output_text, "tools_used": tools_used, "usage": usage}

        input_items += response.output
        for call in calls:
            try:
                arguments = json.loads(call.arguments)
            except json.JSONDecodeError:
                # Send the error back as the tool result so the model can retry the call.
                result = {"error": "invalid JSON arguments"}
            else:
                result = run_tool(user, call.name, arguments)
                tools_used.append({"name": call.name, "arguments": arguments})
            input_items.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(result, default=str),
            })

    return {
        "answer": "Sorry, I could not work that out. Please rephrase the question.",
        "tools_used": tools_used,
        "usage": usage,
    }
