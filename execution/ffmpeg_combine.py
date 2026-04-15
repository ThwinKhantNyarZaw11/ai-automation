"""
Combine a video file and audio file using FFmpeg.
Usage: python -m execution.ffmpeg_combine --video_path <path> --audio_path <path> [--output_path <path>]
"""
import argparse
import subprocess
from pathlib import Path

from execution.config import TMP_DIR


def combine_video_audio(video_path: str, audio_path: str, output_path: str = None) -> str:
    """
    Combine video and audio files using FFmpeg.
    Returns the path to the output file.
    """
    video_path = Path(video_path)
    audio_path = Path(audio_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if not output_path:
        output_path = str(TMP_DIR / f"combined_{video_path.stem}.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr}")

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine video and audio")
    parser.add_argument("--video_path", required=True)
    parser.add_argument("--audio_path", required=True)
    parser.add_argument("--output_path", default=None)
    args = parser.parse_args()

    out = combine_video_audio(args.video_path, args.audio_path, args.output_path)
    print(f"Output saved to: {out}")
