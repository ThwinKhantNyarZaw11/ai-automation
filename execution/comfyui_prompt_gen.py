"""
Generate ComfyUI-compatible image prompts from script scenes using Gemini.
Usage: python -m execution.comfyui_prompt_gen --scenes_json <path>
"""
import argparse
import json
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR

SYSTEM_PROMPT = """You are an expert at creating image generation prompts for ComfyUI.
Given a scene from a Burmese script, create a detailed image prompt in English.

Output ONLY valid JSON with this structure:
{
  "scene": <number>,
  "prompt": "<detailed positive prompt>",
  "negative_prompt": "<things to avoid>"
}

Guidelines for prompts:
- Be very detailed and descriptive
- Include style: cinematic lighting, ultra realistic, high quality
- Maintain character consistency across scenes
- Include relevant mood, setting, and action descriptions
"""


def generate_prompts(scenes: list[dict], output_dir: str = None) -> list[dict]:
    """Generate ComfyUI prompts for each scene."""
    output_dir = Path(output_dir) if output_dir else TMP_DIR / "comfyui_prompts"
    output_dir.mkdir(parents=True, exist_ok=True)

    prompts = []
    for scene in scenes:
        prompt_text = f"""Scene {scene['scene_number']}:
{scene['text']}

Create a ComfyUI image generation prompt for this scene. Output only JSON."""

        response = generate_text(prompt_text, system_prompt=SYSTEM_PROMPT)

        # Parse the JSON from the response
        try:
            # Try to extract JSON from response (handle markdown code blocks)
            json_str = response.strip()
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                json_str = json_str.strip()
            prompt_data = json.loads(json_str)
        except json.JSONDecodeError:
            prompt_data = {
                "scene": scene["scene_number"],
                "prompt": response.strip(),
                "negative_prompt": "blurry, low quality, distorted",
            }

        prompt_data["scene"] = scene["scene_number"]
        prompts.append(prompt_data)

        # Save individual prompt
        prompt_path = output_dir / f"scene_{scene['scene_number']:03d}.json"
        prompt_path.write_text(json.dumps(prompt_data, indent=2), encoding="utf-8")

    # Save all prompts
    all_path = output_dir / "all_prompts.json"
    all_path.write_text(json.dumps(prompts, indent=2), encoding="utf-8")

    return prompts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ComfyUI prompts from scenes")
    parser.add_argument("--scenes_json", required=True)
    parser.add_argument("--output_dir", default=str(TMP_DIR / "comfyui_prompts"))
    args = parser.parse_args()

    with open(args.scenes_json, "r", encoding="utf-8") as f:
        scenes = json.load(f)

    results = generate_prompts(scenes, args.output_dir)
    print(json.dumps(results, indent=2))
