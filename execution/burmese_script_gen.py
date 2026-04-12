"""
Generate a Burmese-language script from source material using Gemini.
Wraps gemini_generate.py with a Burmese scriptwriting system prompt.
Usage: python -m execution.burmese_script_gen --source_json <path> [--output_path <path>]
"""
import argparse
import json
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR

SYSTEM_PROMPT = """You are an expert Burmese-language scriptwriter.
Given source material about a topic, write a compelling, well-structured script in Burmese (Myanmar language).

Guidelines:
- Write entirely in Burmese script (Myanmar Unicode)
- Use a storytelling format suitable for video narration
- Include an engaging introduction, clear body sections, and a conclusion
- Keep the tone informative yet engaging
- Adapt the content faithfully from the source material
"""


def generate_burmese_script(source_data: dict, output_path: str = None) -> str:
    """
    Generate a Burmese script from source material.
    source_data should contain 'title', 'description', 'sources', etc.
    """
    prompt = f"""Based on the following source material, write a Burmese script:

Title: {source_data.get('title', '')}
Description: {source_data.get('description', '')}

Key Information:
{json.dumps(source_data.get('sources', []), indent=2, ensure_ascii=False)}

Write a complete Burmese script for this content."""

    result = generate_text(prompt, system_prompt=SYSTEM_PROMPT)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Burmese script")
    parser.add_argument("--source_json", required=True)
    parser.add_argument("--output_path", default=str(TMP_DIR / "burmese_script.txt"))
    args = parser.parse_args()

    with open(args.source_json, "r", encoding="utf-8") as f:
        source = json.load(f)

    script = generate_burmese_script(source, args.output_path)
    print(script)
