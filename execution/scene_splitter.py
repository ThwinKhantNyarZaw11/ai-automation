"""
Split a script into scenes (3 sentences per scene).
Pure Python text processing — no API calls.
Usage: python -m execution.scene_splitter --script_path <path>
"""
import argparse
import json
import re
from pathlib import Path

from execution.config import TMP_DIR


def split_into_scenes(script_path: str, sentences_per_scene: int = 3, output_path: str = None) -> list[dict]:
    """
    Split a script into scenes, each containing a fixed number of sentences.
    Returns a list of scene dicts with 'scene_number' and 'text'.
    """
    text = Path(script_path).read_text(encoding="utf-8")

    # Split on Burmese sentence endings (။) and common punctuation
    sentences = re.split(r'(?<=[။.!?\n])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    scenes = []
    for i in range(0, len(sentences), sentences_per_scene):
        chunk = sentences[i:i + sentences_per_scene]
        scenes.append({
            "scene_number": len(scenes) + 1,
            "text": " ".join(chunk),
        })

    if output_path:
        Path(output_path).write_text(
            json.dumps(scenes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return scenes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split script into scenes")
    parser.add_argument("--script_path", required=True)
    parser.add_argument("--sentences_per_scene", type=int, default=3)
    parser.add_argument("--output_path", default=str(TMP_DIR / "scenes.json"))
    args = parser.parse_args()

    scenes = split_into_scenes(args.script_path, args.sentences_per_scene, args.output_path)
    print(json.dumps(scenes, indent=2, ensure_ascii=False))
