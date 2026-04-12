"""
Generate a Burmese script based on video analysis + user prompt.
Uses Gemini with video-specific context.
Usage: python -m execution.video_script_gen --analysis_json <path> --user_prompt "..."
"""
import argparse
import json
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR

SYSTEM_PROMPT = """You are an expert Burmese-language scriptwriter who creates scripts based on video content.
Given a video analysis and a user's desired transformation, write a new script in Burmese.

Guidelines:
- Write entirely in Burmese script (Myanmar Unicode)
- Follow the user's transformation instructions precisely
- Maintain the video's structure and key moments
- Create engaging narration suitable for the video
"""


def generate_video_script(analysis: dict, user_prompt: str, output_path: str = None) -> str:
    """Generate a Burmese script based on video analysis and user prompt."""
    prompt = f"""Video Analysis:
- Duration: {analysis.get('duration', 0)} seconds
- Format: {analysis.get('format', 'unknown')}
- Keyframes captured: {len(analysis.get('keyframes', []))}
- Metadata: {json.dumps(analysis.get('metadata', {}), ensure_ascii=False)}

User's Request: {user_prompt}

Based on this video analysis and the user's request, write a complete Burmese script."""

    result = generate_text(prompt, system_prompt=SYSTEM_PROMPT)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate video script in Burmese")
    parser.add_argument("--analysis_json", required=True)
    parser.add_argument("--user_prompt", required=True)
    parser.add_argument("--output_path", default=str(TMP_DIR / "video_script.txt"))
    args = parser.parse_args()

    with open(args.analysis_json, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    script = generate_video_script(analysis, args.user_prompt, args.output_path)
    print(script)
