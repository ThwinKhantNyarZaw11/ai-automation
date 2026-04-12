"""
Modify an existing script based on user instructions using Gemini.
Usage: python -m execution.script_modifier --script_path <path> --instructions "..."
"""
import argparse
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR

SYSTEM_PROMPT = """You are an expert Burmese-language script editor.
Given an existing script and modification instructions, rewrite the script accordingly.

Guidelines:
- Output entirely in Burmese script (Myanmar Unicode)
- Follow the user's modification instructions precisely
- Preserve the overall structure unless told otherwise
- Maintain quality and coherence
"""


def modify_script(script_path: str, instructions: str, output_path: str = None) -> str:
    """Modify an existing script based on user instructions."""
    script_text = Path(script_path).read_text(encoding="utf-8")

    prompt = f"""Original Script:
{script_text}

Modification Instructions:
{instructions}

Rewrite the script with these changes applied."""

    result = generate_text(prompt, system_prompt=SYSTEM_PROMPT)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Modify script in Burmese")
    parser.add_argument("--script_path", required=True)
    parser.add_argument("--instructions", required=True)
    parser.add_argument("--output_path", default=str(TMP_DIR / "modified_script.txt"))
    args = parser.parse_args()

    result = modify_script(args.script_path, args.instructions, args.output_path)
    print(result)
