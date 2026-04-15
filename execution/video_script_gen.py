"""
Generate a script based on video analysis + user prompt.
Uses Gemini with detailed video content analysis.
Usage: python -m execution.video_script_gen --analysis_json <path> --user_prompt "..."
"""
import argparse
import json
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR


def generate_video_script(analysis: dict, user_prompt: str, output_path: str = None,
                          language: str = "English", target_words: int = 3000) -> str:
    """Generate a script based on video analysis and user prompt."""
    content_analysis = analysis.get("content_analysis", "No analysis available")

    system_prompt = f"""You are a professional scriptwriter. You write scripts in {language}.

CRITICAL RULES:
- Write ENTIRELY in {language}
- Write EXACTLY {target_words} words
- Base the script ACCURATELY on the video content analysis provided
- Follow the user's style/prompt instructions precisely
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Just write continuous, seamless script text that flows naturally"""

    prompt = f"""Video Content Analysis:
{content_analysis}

User's Instructions: {user_prompt}

Based on the detailed video content analysis above and the user's instructions, write a complete script.
The script must accurately reflect what happens in the video.
Write exactly {target_words} words in {language}."""

    result = generate_text(prompt, system_prompt=system_prompt)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate video script")
    parser.add_argument("--analysis_json", required=True)
    parser.add_argument("--user_prompt", required=True)
    parser.add_argument("--output_path", default=str(TMP_DIR / "video_script.txt"))
    parser.add_argument("--language", default="English")
    parser.add_argument("--target_words", type=int, default=3000)
    args = parser.parse_args()

    with open(args.analysis_json, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    script = generate_video_script(analysis, args.user_prompt, args.output_path,
                                   args.language, args.target_words)
    print(script)
