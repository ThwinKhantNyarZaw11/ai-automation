"""
Generate image-to-video (I2V) and text-to-video (T2V) prompts from script scenes.
Takes user's style/character/background preferences and creates two JSON prompt files.
Usage: python -m execution.video_prompt_gen --scenes_json <path> --style ... --character ... --background ...
"""
import argparse
import json
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR


PROMPTS_PER_SCENE = 9


# ── I2V Prompt System Prompt ──
I2V_SYSTEM_PROMPT = f"""You are an expert at creating Image-to-Video (I2V) prompts for AI video generation tools like Runway Gen-3, Kling, Luma Dream Machine, and Pika.

You will receive:
1. User's STYLE preference
2. User's CHARACTER DESIGN preference
3. User's BACKGROUND preference
4. Whether characters should be CONSISTENT across scenes
5. A scene (paragraph) from a script

Your job: generate EXACTLY {PROMPTS_PER_SCENE} DIFFERENT I2V prompt variations for this single paragraph. Each variation should describe:
- The STATIC IMAGE that would be the starting frame
- The MOTION/CAMERA movement to animate from that frame
- Duration hints (usually 3-5 seconds)
- Camera terminology (dolly, pan, zoom, push in, orbit, etc.)

HOW TO CREATE {PROMPTS_PER_SCENE} DISTINCT VARIATIONS:
- Vary the CAMERA ANGLE (low-angle, high-angle, bird's-eye, Dutch tilt, eye-level, over-the-shoulder, etc.)
- Vary the SHOT TYPE (extreme close-up, close-up, medium, wide, extreme wide)
- Vary the CHARACTER PERSPECTIVE or POINT OF VIEW (the main character's POV, a bystander's POV, an antagonist's POV, a child's POV, an animal's POV, a drone/overhead POV, etc.)
- Vary the FOCAL SUBJECT (focus on face, hands, environment, reaction, foreground object, background detail)
- Vary the CAMERA MOTION (dolly in, pull back, orbit, crane up, handheld shake, locked tripod, whip pan)
- Vary the TIMING MOMENT within the paragraph (opening beat, middle action, final reaction)

If the paragraph is SHORT or has little obvious action, you MUST still produce {PROMPTS_PER_SCENE} variations by shifting POV / camera angle / focal subject as described above — do NOT invent new plot content, just show the same beat through different lenses.

CRITICAL RULES:
- Include the user's style, character design, and background EXACTLY in every variation
- If consistency = yes, use IDENTICAL character descriptions across all variations
- If consistency = no, allow character variation
- Each variation must be clearly DIFFERENT from the others
- Keep each prompt focused and under 150 words

Output ONLY valid JSON in this exact shape:
{{
  "scene": <number>,
  "variations": [
    {{
      "variation": 1,
      "pov": "<whose perspective / camera angle>",
      "shot_type": "<e.g. close-up, wide shot>",
      "starting_frame": "<detailed description of the initial image>",
      "motion": "<description of camera movement and subject animation>",
      "duration": "<e.g. 4 seconds>",
      "full_prompt": "<combined prompt ready to paste into I2V tools>"
    }},
    ... (exactly {PROMPTS_PER_SCENE} total variations)
  ]
}}"""


# ── T2V Prompt System Prompt ──
T2V_SYSTEM_PROMPT = f"""You are an expert at creating Text-to-Video (T2V) prompts for AI video generation tools like Sora, Veo, Kling, and Runway.

You will receive:
1. User's STYLE preference
2. User's CHARACTER DESIGN preference
3. User's BACKGROUND preference
4. Whether characters should be CONSISTENT across scenes
5. A scene (paragraph) from a script

Your job: generate EXACTLY {PROMPTS_PER_SCENE} DIFFERENT T2V prompt variations for this single paragraph. Each variation describes the entire video clip from start to finish.

HOW TO CREATE {PROMPTS_PER_SCENE} DISTINCT VARIATIONS:
- Vary the CAMERA ANGLE (low-angle, high-angle, bird's-eye, Dutch tilt, eye-level, over-the-shoulder, etc.)
- Vary the SHOT TYPE (extreme close-up, close-up, medium, wide, extreme wide)
- Vary the CHARACTER PERSPECTIVE or POINT OF VIEW (main character's POV, bystander's POV, antagonist's POV, child's POV, animal's POV, overhead drone POV, etc.)
- Vary the FOCAL SUBJECT (face, hands, environment, reaction shot, foreground, background detail)
- Vary the CAMERA MOTION (dolly in, pull back, orbit, crane up, handheld, locked, whip pan)
- Vary the TIMING MOMENT within the paragraph (opening beat, middle, closing reaction)

If the paragraph is SHORT or has little obvious action, you MUST still produce {PROMPTS_PER_SCENE} variations by shifting POV / camera angle / focal subject — do NOT invent new plot content, just reframe the same beat.

CRITICAL RULES:
- Include the user's style, character design, and background EXACTLY in every variation
- If consistency = yes, use IDENTICAL character descriptions across all variations
- If consistency = no, allow character variation
- Each variation must be clearly DIFFERENT from the others
- Include cinematic terminology: shot type, lighting, mood, atmosphere
- Keep each prompt focused and under 200 words

Output ONLY valid JSON in this exact shape:
{{
  "scene": <number>,
  "variations": [
    {{
      "variation": 1,
      "pov": "<whose perspective / camera angle>",
      "shot_type": "<e.g. medium shot, wide shot, close-up>",
      "style": "<art style>",
      "action": "<what happens in the scene>",
      "camera": "<camera movement>",
      "lighting": "<lighting description>",
      "full_prompt": "<combined prompt ready to paste into T2V tools>"
    }},
    ... (exactly {PROMPTS_PER_SCENE} total variations)
  ]
}}"""


def _parse_json_response(response: str, fallback: dict) -> dict:
    """Parse JSON from Gemini response, handling markdown code blocks."""
    try:
        json_str = response.strip()
        if "```" in json_str:
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            json_str = json_str.strip()
        return json.loads(json_str)
    except json.JSONDecodeError:
        return fallback


def _build_user_context(style: str, character: str, background: str,
                        consistency: bool) -> str:
    """Format user preferences into a context block."""
    lines = [
        f"STYLE: {style}",
        f"CHARACTER DESIGN: {character}",
        f"BACKGROUND: {background}",
        f"CHARACTER CONSISTENCY: {'YES - Keep characters IDENTICAL across all scenes' if consistency else 'NO - Characters can vary per scene'}",
    ]
    return "\n".join(lines)


def generate_video_prompts(
    scenes: list[dict],
    style: str,
    character: str,
    background: str,
    consistency: bool,
    output_dir: str = None,
    name_prefix: str = None,
) -> dict:
    """
    Generate I2V and T2V prompts for all scenes.
    Returns dict with paths to the two output files.

    If `name_prefix` is provided, outputs are named
    `{prefix}_image_to_video_prompts.txt` and `{prefix}_text_to_video_prompts.txt`.
    """
    output_dir = Path(output_dir) if output_dir else TMP_DIR / "video_prompts"
    output_dir.mkdir(parents=True, exist_ok=True)

    user_context = _build_user_context(style, character, background, consistency)

    i2v_prompts = []
    t2v_prompts = []

    for scene in scenes:
        scene_num = scene.get("scene_number", 0)
        scene_text = scene.get("text", "")

        # ── Generate I2V prompts (9 variations) ──
        i2v_input = f"""{user_context}

---

SCENE {scene_num}:
{scene_text}

---

Generate exactly {PROMPTS_PER_SCENE} I2V prompt variations for this paragraph. Output only JSON."""

        i2v_response = generate_text(i2v_input, system_prompt=I2V_SYSTEM_PROMPT)
        i2v_data = _parse_json_response(i2v_response, {
            "scene": scene_num,
            "variations": [
                {
                    "variation": 1,
                    "pov": "main character eye-level",
                    "shot_type": "medium shot",
                    "starting_frame": scene_text[:200],
                    "motion": "slow camera push in",
                    "duration": "4 seconds",
                    "full_prompt": i2v_response.strip(),
                }
            ],
        })
        i2v_data["scene"] = scene_num
        # Ensure variations list exists and is numbered correctly
        if "variations" not in i2v_data or not isinstance(i2v_data["variations"], list):
            i2v_data["variations"] = []
        for idx, v in enumerate(i2v_data["variations"], start=1):
            v["variation"] = idx
        i2v_prompts.append(i2v_data)
        print(f"[VideoPromptGen] I2V scene {scene_num}/{len(scenes)} done "
              f"({len(i2v_data['variations'])} variations)")

        # ── Generate T2V prompts (9 variations) ──
        t2v_input = f"""{user_context}

---

SCENE {scene_num}:
{scene_text}

---

Generate exactly {PROMPTS_PER_SCENE} T2V prompt variations for this paragraph. Output only JSON."""

        t2v_response = generate_text(t2v_input, system_prompt=T2V_SYSTEM_PROMPT)
        t2v_data = _parse_json_response(t2v_response, {
            "scene": scene_num,
            "variations": [
                {
                    "variation": 1,
                    "pov": "main character eye-level",
                    "shot_type": "medium shot",
                    "style": style,
                    "action": scene_text[:200],
                    "camera": "static",
                    "lighting": "natural",
                    "full_prompt": t2v_response.strip(),
                }
            ],
        })
        t2v_data["scene"] = scene_num
        if "variations" not in t2v_data or not isinstance(t2v_data["variations"], list):
            t2v_data["variations"] = []
        for idx, v in enumerate(t2v_data["variations"], start=1):
            v["variation"] = idx
        t2v_prompts.append(t2v_data)
        print(f"[VideoPromptGen] T2V scene {scene_num}/{len(scenes)} done "
              f"({len(t2v_data['variations'])} variations)")

    # Save as .txt files containing JSON
    prefix = f"{name_prefix}_" if name_prefix else ""
    i2v_path = output_dir / f"{prefix}image_to_video_prompts.txt"
    t2v_path = output_dir / f"{prefix}text_to_video_prompts.txt"

    i2v_output = {
        "type": "image_to_video",
        "user_preferences": {
            "style": style,
            "character": character,
            "background": background,
            "consistency": consistency,
        },
        "scenes": i2v_prompts,
    }
    t2v_output = {
        "type": "text_to_video",
        "user_preferences": {
            "style": style,
            "character": character,
            "background": background,
            "consistency": consistency,
        },
        "scenes": t2v_prompts,
    }

    i2v_path.write_text(
        json.dumps(i2v_output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    t2v_path.write_text(
        json.dumps(t2v_output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    total_i2v = sum(len(s.get("variations", [])) for s in i2v_prompts)
    total_t2v = sum(len(s.get("variations", [])) for s in t2v_prompts)

    return {
        "i2v_path": str(i2v_path),
        "t2v_path": str(t2v_path),
        "i2v_scene_count": len(i2v_prompts),
        "t2v_scene_count": len(t2v_prompts),
        "i2v_total_variations": total_i2v,
        "t2v_total_variations": total_t2v,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate I2V and T2V prompts")
    parser.add_argument("--scenes_json", required=True)
    parser.add_argument("--style", required=True)
    parser.add_argument("--character", required=True)
    parser.add_argument("--background", required=True)
    parser.add_argument("--consistency", action="store_true")
    parser.add_argument("--output_dir", default=str(TMP_DIR / "video_prompts"))
    args = parser.parse_args()

    with open(args.scenes_json, "r", encoding="utf-8") as f:
        scenes = json.load(f)

    result = generate_video_prompts(
        scenes, args.style, args.character, args.background,
        args.consistency, args.output_dir
    )
    print(json.dumps(result, indent=2))
