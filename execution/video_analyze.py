"""
Analyze a video file using Gemini multimodal API for accurate content understanding.
Compresses large videos with FFmpeg before uploading to stay within Gemini's 2GB limit.
Usage: python -m execution.video_analyze --video_path <path>
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

from execution.config import TMP_DIR

# Gemini File API limit is 2GB; we target well under that
MAX_UPLOAD_SIZE = 1_500_000_000  # 1.5 GB to be safe


def _compress_video(video_path: str, output_dir: str) -> str:
    """
    Compress a video with FFmpeg to fit within Gemini's upload limit.
    Uses lower resolution (720p) and moderate bitrate.
    Returns the path to the compressed file.
    """
    compressed_path = str(Path(output_dir) / "compressed_for_analysis.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", "scale=-2:720",       # scale to 720p height
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "28",                # moderate quality — good enough for analysis
        "-c:a", "aac",
        "-b:a", "64k",              # low audio bitrate
        "-movflags", "+faststart",
        compressed_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg compression failed: {result.stderr[-500:]}")

    return compressed_path


def _extract_keyframes_for_analysis(video_path: str, output_dir: str, interval: int = 5) -> list[str]:
    """
    Extract keyframes from video at given interval (seconds).
    Fallback when video is too large even after compression.
    """
    frames_dir = Path(output_dir) / "analysis_frames"
    frames_dir.mkdir(exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps=1/{interval}",
        "-q:v", "3",
        str(frames_dir / "frame_%04d.jpg"),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    return sorted(str(p) for p in frames_dir.glob("*.jpg"))


def analyze_video(video_path: str, output_dir: str = None) -> dict:
    """
    Analyze video content using Gemini's multimodal capability.
    - If video is under 1.5GB, uploads directly.
    - If over 1.5GB, compresses with FFmpeg first.
    - If compression still too large, falls back to keyframe analysis.
    Returns analysis dict with actual video content understanding.
    """
    from execution.gemini_generate import generate_with_video, generate_text

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    output_dir = Path(output_dir) if output_dir else TMP_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    file_size = os.path.getsize(video_path)
    upload_path = video_path

    # If file is too large, compress it
    if file_size > MAX_UPLOAD_SIZE:
        try:
            compressed = _compress_video(video_path, str(output_dir))
            compressed_size = os.path.getsize(compressed)
            if compressed_size <= MAX_UPLOAD_SIZE:
                upload_path = compressed
            else:
                # Still too large — fall back to keyframe analysis
                return _analyze_with_keyframes(video_path, str(output_dir))
        except Exception:
            # FFmpeg failed — fall back to keyframe analysis
            return _analyze_with_keyframes(video_path, str(output_dir))

    # Upload video to Gemini for multimodal analysis
    prompt = """Analyze this video in detail. Provide a comprehensive description including:

1. **Content Summary**: What is happening in the video? What is the main topic/subject?
2. **Scene-by-Scene Breakdown**: Describe each major scene or segment with timestamps if visible.
3. **Visual Elements**: What objects, people, locations, text overlays, graphics are shown?
4. **Audio/Narration**: If there is speech, narration, or important audio, describe what is said.
5. **Tone & Style**: What is the mood, style, and pacing of the video?
6. **Key Messages**: What are the main points or messages conveyed?

Be as detailed and specific as possible. This analysis will be used to write an accurate script."""

    system_prompt = "You are an expert video analyst. Provide detailed, accurate descriptions of video content. Be specific about what you see and hear."

    content_analysis = generate_with_video(upload_path, prompt, system_prompt=system_prompt)

    analysis = {
        "video_path": str(video_path),
        "content_analysis": content_analysis,
    }

    # Save analysis
    analysis_path = output_dir / "video_analysis.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

    # Clean up compressed file if we made one
    if upload_path != video_path:
        try:
            os.remove(upload_path)
        except Exception:
            pass

    return analysis


def _analyze_with_keyframes(video_path: str, output_dir: str) -> dict:
    """
    Fallback: extract keyframes and analyze them as images via Gemini.
    Used when video is too large for the File API even after compression.
    """
    import base64
    from execution.gemini_generate import generate_text

    frames = _extract_keyframes_for_analysis(video_path, output_dir, interval=10)

    if not frames:
        return {
            "video_path": video_path,
            "content_analysis": "Could not extract frames from video for analysis.",
        }

    # Build a text description prompt with frame info
    # Select up to 20 evenly spaced frames
    max_frames = 20
    if len(frames) > max_frames:
        step = len(frames) // max_frames
        selected = frames[::step][:max_frames]
    else:
        selected = frames

    # Read frames as base64 for Gemini multimodal
    from google import genai
    from execution.config import GEMINI_API_KEY, GEMINI_MODEL

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Build contents with images
    contents = []
    for i, frame_path in enumerate(selected):
        with open(frame_path, "rb") as f:
            img_data = f.read()
        contents.append(genai.types.Part.from_bytes(data=img_data, mime_type="image/jpeg"))
        contents.append(f"[Frame {i+1} of {len(selected)}, approximately {i * 10} seconds into the video]")

    contents.append("""Based on these keyframes extracted from a video, provide a detailed analysis:

1. **Content Summary**: What is happening in the video? What is the main topic?
2. **Scene-by-Scene Breakdown**: Describe what each frame/scene shows.
3. **Visual Elements**: What objects, people, locations, text, graphics are shown?
4. **Tone & Style**: What is the mood and style of the video?
5. **Key Messages**: What messages are being conveyed?

Be as detailed as possible. This analysis will be used to write an accurate script.""")

    config = {"system_instruction": "You are an expert video analyst. Analyze these keyframes extracted from a video and provide a comprehensive description of the video content."}

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=config,
    )

    analysis = {
        "video_path": video_path,
        "content_analysis": response.text,
        "method": "keyframe_analysis",
        "frames_analyzed": len(selected),
    }

    analysis_path = Path(output_dir) / "video_analysis.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

    return analysis


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze video file")
    parser.add_argument("--video_path", required=True)
    parser.add_argument("--output_dir", default=str(TMP_DIR))
    args = parser.parse_args()

    result = analyze_video(args.video_path, args.output_dir)
    print(json.dumps(result, indent=2))
