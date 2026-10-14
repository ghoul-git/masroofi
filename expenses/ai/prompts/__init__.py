from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache
def _read(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def load_prompt(name: str, **values) -> str:
    """Read prompts/<name>.md and fill its {placeholders} with str.format.

    A literal brace in a prompt file must be written as {{ or }}.
    """
    return _read(name).format(**values)
