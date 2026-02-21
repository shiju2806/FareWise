"""Prompt loader for reasoning guides."""

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    return (_PROMPT_DIR / name).read_text()
