"""
Generate video prompts from script scenes — single plain-text file.

Output structure:
  PART 1 — Character Design Sheets
    For each character: front view, side view, back view prompts
    (full body 9:16 + upper 3/4 body), all on white background.

  PART 2 — Scene Prompt Table
    For each scene: side-by-side Text-to-Image vs Image-to-Video prompts
    so the user can compare and paste into Grok / Runway / Kling etc.

Usage: python -m execution.video_prompt_gen --scenes_json <path> --style ...
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR


PROMPTS_PER_SCENE = 9


# ── System prompts ────────────────────────────────────────────────────────────

CHARACTER_SHEET_SYSTEM = """You are an expert character design prompt writer for AI image generation (Grok, Midjourney, DALL-E, Flux).

You will receive a script excerpt and a style preference. Your job:

1. Identify ALL named or distinct characters in the script.
2. For EACH character, write 6 image-generation prompts:
   a) FRONT VIEW — Full body, 9:16 portrait orientation
   b) SIDE VIEW  — Full body, 9:16 portrait orientation
   c) BACK VIEW  — Full body, 9:16 portrait orientation
   d) FRONT VIEW — Upper 3/4 body (head to mid-thigh)
   e) SIDE VIEW  — Upper 3/4 body (head to mid-thigh)
   f) BACK VIEW  — Upper 3/4 body (head to mid-thigh)

RULES:
- Every prompt MUST start with the character's NAME so the AI knows exactly who it is generating (e.g. "Prince Min Sit, front view, full body...")
- Every prompt MUST specify: white background, character design sheet style
- Every prompt MUST include the user's art style
- Describe the character in FULL DETAIL: age, gender, ethnicity, body type, height, hair color/style, eye color, clothing (top, bottom, shoes, accessories), facial features, distinctive traits
- Keep descriptions IDENTICAL across all 6 views of the same character (consistency of appearance, clothes, accessories)
- Each prompt should be self-contained and ready to paste into an AI image tool
- Keep each prompt under 150 words
- Do NOT add any extra commentary — just the prompts

OUTPUT FORMAT (plain text, exactly like this):

CHARACTER 1: [Full Name]

  Front View (Full Body):
  [Full Name], front view, full body, 9:16, [detailed prompt...], white background, character design sheet

  Side View (Full Body):
  [Full Name], side view, full body, 9:16, [detailed prompt...], white background, character design sheet

  Back View (Full Body):
  [Full Name], back view, full body, 9:16, [detailed prompt...], white background, character design sheet

  Front View (Upper 3/4):
  [Full Name], front view, upper 3/4 body, [detailed prompt...], white background, character design sheet

  Side View (Upper 3/4):
  [Full Name], side view, upper 3/4 body, [detailed prompt...], white background, character design sheet

  Back View (Upper 3/4):
  [Full Name], back view, upper 3/4 body, [detailed prompt...], white background, character design sheet

CHARACTER 2: [Full Name]
  ... (same format)
"""


SCENE_PROMPT_SYSTEM = """You are an expert at creating prompts for AI video generation tools.

You will receive a scene (paragraph) from a script plus the user's style/character/background preferences.

Your job: generate THREE things for this scene:

1. CHARACTERS IN THIS SCENE — List every character who appears or is mentioned in this scene by their full name.

2. TEXT-TO-IMAGE (T2I) PROMPT — A detailed prompt to generate a STATIC IMAGE of this scene.
   This will be used in Grok, Midjourney, DALL-E, or Flux.
   Include: scene composition, character poses, expressions, environment, lighting, camera angle, art style.
   IMPORTANT: Mention each character BY NAME in the prompt so the AI knows exactly who is in the scene.
   Keep under 200 words.

3. IMAGE-TO-VIDEO (I2V) PROMPT — A prompt to ANIMATE the image from above into a short video.
   This will be used in Runway Gen-3, Kling, Luma, or Pika.
   Include: what moves, camera motion (dolly, pan, zoom, orbit, etc.), character action, duration (3-5s).
   IMPORTANT: Mention each character BY NAME so the AI knows who is moving/acting.
   Keep under 150 words.

RULES:
- Include the user's style, character design, and background in both prompts
- If consistency = yes, use IDENTICAL character descriptions, clothes, and visual details across all scenes
- Refer to characters by their FULL NAMES in every prompt
- Make the T2I prompt describe the scene as a single still frame
- Make the I2V prompt describe how that frame comes alive with motion
- Output ONLY in the format below, no extra commentary

OUTPUT FORMAT (plain text, exactly like this):

Characters: [Name1], [Name2], [Name3]

Text-to-Image:
[prompt]

Image-to-Video:
[prompt]
"""


# ── Core generation ───────────────────────────────────────────────────────────

def _build_user_context(style: str, character: str, background: str,
                        consistency: bool) -> str:
    """Format user preferences into a context block."""
    return "\n".join([
        f"STYLE: {style}",
        f"CHARACTER DESIGN: {character}",
        f"BACKGROUND: {background}",
        f"FULL CONSISTENCY: {'YES - Keep characters, clothes, background, art style, and all visual details IDENTICAL across every scene' if consistency else 'NO - Allow variation between scenes'}",
    ])


def _generate_character_sheets(script_text: str, style: str) -> str:
    """Generate character design sheet prompts from the full script."""
    # Use a generous excerpt so Gemini sees all characters
    excerpt = script_text[:5000]
    prompt = f"""Art style: {style}

Script:
\"\"\"
{excerpt}
\"\"\"

Identify all characters and generate the 6-view character design sheet prompts for each one."""

    return generate_text(prompt, system_prompt=CHARACTER_SHEET_SYSTEM)


def _generate_scene_prompt(scene_num: int, scene_text: str,
                           user_context: str, total_scenes: int) -> tuple[int, str]:
    """Generate T2I + I2V prompt pair for one scene. Returns (scene_num, text)."""
    prompt = f"""{user_context}

---

SCENE {scene_num}:
{scene_text}

---

Generate the Text-to-Image and Image-to-Video prompts for this scene."""

    response = generate_text(prompt, system_prompt=SCENE_PROMPT_SYSTEM)
    print(f"[VideoPromptGen] Scene {scene_num}/{total_scenes} done")
    return scene_num, response.strip()


def generate_video_prompts(
    scenes: list[dict],
    style: str,
    character: str,
    background: str,
    consistency: bool,
    output_dir: str = None,
    name_prefix: str = None,
    script_text: str = "",
) -> dict:
    """
    Generate a single prompt file containing:
      Part 1: Character design sheets (front/side/back views)
      Part 2: Scene-by-scene T2I vs I2V prompt table

    Returns dict with 'prompt_path', 'scene_count', 'character_section_length'.
    """
    output_dir = Path(output_dir) if output_dir else TMP_DIR / "video_prompts"
    output_dir.mkdir(parents=True, exist_ok=True)

    user_context = _build_user_context(style, character, background, consistency)
    total_scenes = len(scenes)

    # ── Fire character sheet + all scene prompts in parallel ──────────────
    scene_results = {}  # scene_num -> text

    with ThreadPoolExecutor(max_workers=min(total_scenes + 1, 8)) as executor:
        # Submit character sheet generation
        char_future = executor.submit(
            _generate_character_sheets, script_text, style
        )

        # Submit all scene prompts
        scene_futures = {
            executor.submit(
                _generate_scene_prompt,
                scene.get("scene_number", i + 1),
                scene.get("text", ""),
                user_context,
                total_scenes,
            ): scene.get("scene_number", i + 1)
            for i, scene in enumerate(scenes)
        }

        # Collect character sheet
        character_section = char_future.result()
        print(f"[VideoPromptGen] Character sheets done")

        # Collect scene results
        for future in as_completed(scene_futures):
            scene_num = scene_futures[future]
            scene_results[scene_num] = future.result()[1]

    # ── Assemble the final document ──────────────────────────────────────
    separator = "=" * 80
    thin_sep = "-" * 80

    lines = []
    lines.append(separator)
    lines.append("  VIDEO PROMPT FILE")
    lines.append(f"  Style: {style}")
    lines.append(f"  Scenes: {total_scenes}")
    lines.append(f"  Consistency: {'Yes' if consistency else 'No'}")
    lines.append(separator)
    lines.append("")

    # ── Part 1: Character Design Sheets ──
    lines.append(separator)
    lines.append("  PART 1: CHARACTER DESIGN SHEETS")
    lines.append("  (Use these prompts in Grok / Midjourney / DALL-E / Flux)")
    lines.append("  All characters on WHITE BACKGROUND for consistency")
    lines.append(separator)
    lines.append("")
    lines.append(character_section.strip())
    lines.append("")

    # ── Part 2: Scene Prompt Table ──
    lines.append(separator)
    lines.append("  PART 2: SCENE PROMPTS (Text-to-Image vs Image-to-Video)")
    lines.append("  Left: T2I prompt (for Grok/Midjourney)  |  Right: I2V prompt (for Runway/Kling)")
    lines.append(separator)
    lines.append("")

    # Assemble scenes in order
    scene_nums_sorted = sorted(scene_results.keys())
    for scene_num in scene_nums_sorted:
        scene_text_raw = ""
        for s in scenes:
            if s.get("scene_number", 0) == scene_num:
                scene_text_raw = s.get("text", "")[:200]
                break

        lines.append(thin_sep)
        lines.append(f"  SCENE {scene_num}")
        if scene_text_raw:
            lines.append(f"  Script: {scene_text_raw}...")
        lines.append(thin_sep)
        lines.append("")

        prompt_text = scene_results[scene_num]

        # Parse Characters, T2I, and I2V sections from the response
        characters_line = ""
        t2i_prompt = ""
        i2v_prompt = ""

        # Extract "Characters:" line if present
        remaining = prompt_text
        if "Characters:" in remaining:
            before_chars, after_chars = remaining.split("Characters:", 1)
            # Characters line ends at the next blank line or next section
            char_end = after_chars.find("\n\n")
            if char_end == -1:
                char_end = after_chars.find("Text-to-Image:")
            if char_end == -1:
                characters_line = after_chars.strip()
                remaining = ""
            else:
                characters_line = after_chars[:char_end].strip()
                remaining = after_chars[char_end:]

        if "Image-to-Video:" in remaining:
            parts = remaining.split("Image-to-Video:", 1)
            t2i_raw = parts[0]
            i2v_prompt = parts[1].strip()
            if "Text-to-Image:" in t2i_raw:
                t2i_prompt = t2i_raw.split("Text-to-Image:", 1)[1].strip()
            else:
                t2i_prompt = t2i_raw.strip()
        elif "Text-to-Image:" in remaining:
            t2i_prompt = remaining.split("Text-to-Image:", 1)[1].strip()
            i2v_prompt = "(generation failed - use T2I prompt as reference)"
        else:
            t2i_prompt = remaining.strip() or prompt_text.strip()
            i2v_prompt = "(generation failed - use T2I prompt as reference)"

        # Display characters in this scene
        if characters_line:
            lines.append(f"  Characters: {characters_line}")
            lines.append("")

        # Format as a clear side-by-side comparison
        lines.append("  +-- TEXT-TO-IMAGE (Grok / Midjourney / DALL-E) --+")
        lines.append("")
        for tl in t2i_prompt.splitlines():
            lines.append(f"  {tl}")
        lines.append("")
        lines.append("  +-- IMAGE-TO-VIDEO (Runway / Kling / Luma / Pika) --+")
        lines.append("")
        for il in i2v_prompt.splitlines():
            lines.append(f"  {il}")
        lines.append("")

    lines.append(separator)
    lines.append("  END OF PROMPT FILE")
    lines.append(separator)

    # ── Save ─────────────────────────────────────────────────────────────
    prefix = f"{name_prefix}_" if name_prefix else ""
    output_path = output_dir / f"{prefix}video_prompts.txt"
    output_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "prompt_path": str(output_path),
        "scene_count": total_scenes,
        "character_section_length": len(character_section),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate video prompts")
    parser.add_argument("--scenes_json", required=True)
    parser.add_argument("--style", required=True)
    parser.add_argument("--character", required=True)
    parser.add_argument("--background", required=True)
    parser.add_argument("--consistency", action="store_true")
    parser.add_argument("--script_text", default="")
    parser.add_argument("--output_dir", default=str(TMP_DIR / "video_prompts"))
    args = parser.parse_args()

    with open(args.scenes_json, "r", encoding="utf-8") as f:
        scenes = json.load(f)

    result = generate_video_prompts(
        scenes, args.style, args.character, args.background,
        args.consistency, args.output_dir, script_text=args.script_text,
    )
    print(f"Output: {result['prompt_path']}")
    print(f"Scenes: {result['scene_count']}")
