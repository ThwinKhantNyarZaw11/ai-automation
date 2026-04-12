"""
Analyze a video file: extract metadata and keyframes.
Usage: python -m execution.video_analyze --video_path <path>
"""
import argparse
import json
import subprocess
from pathlib import Path

from execution.config import TMP_DIR


def analyze_video(video_path: str, output_dir: str = None) -> dict:
    """
    Extract video metadata using FFprobe and capture keyframes.
    Returns analysis dict.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    output_dir = Path(output_dir) if output_dir else TMP_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get metadata with ffprobe
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(video_path),
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    if probe_result.returncode != 0:
        raise RuntimeError(f"FFprobe error: {probe_result.stderr}")

    probe_data = json.loads(probe_result.stdout)

    # Extract keyframes (1 per 10 seconds)
    duration = float(probe_data.get("format", {}).get("duration", 0))
    frames_dir = output_dir / "keyframes"
    frames_dir.mkdir(exist_ok=True)

    frame_cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", "fps=1/10",
        "-frame_pts", "1",
        str(frames_dir / "frame_%04d.jpg"),
    ]
    subprocess.run(frame_cmd, capture_output=True, text=True)

    keyframe_paths = sorted(str(p) for p in frames_dir.glob("*.jpg"))

    analysis = {
        "video_path": str(video_path),
        "duration": duration,
        "format": probe_data.get("format", {}).get("format_name", ""),
        "streams": len(probe_data.get("streams", [])),
        "keyframes": keyframe_paths,
        "metadata": probe_data.get("format", {}).get("tags", {}),
    }

    # Save analysis
    analysis_path = output_dir / "video_analysis.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

    return analysis


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze video file")
    parser.add_argument("--video_path", required=True)
    parser.add_argument("--output_dir", default=str(TMP_DIR))
    args = parser.parse_args()

    result = analyze_video(args.video_path, args.output_dir)
    print(json.dumps(result, indent=2))
