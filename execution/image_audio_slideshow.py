"""
Create a slideshow video from images + audio with Ken Burns zoom effect.

Logic:
  - Get audio duration via ffprobe
  - Divide duration evenly across all images (time per image = duration / num_images)
  - For each image: create a clip with alternating zoom-in / zoom-out animation
  - Concat all clips
  - Mux with audio track

Usage: python -m execution.image_audio_slideshow --audio <path> --images <path1> <path2> ...
"""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from execution.config import TMP_DIR


# Output video settings
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
FPS = 30


def get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def _build_zoompan_filter(duration: float, zoom_in: bool) -> str:
    """
    Build a zoompan filter string for a Ken Burns effect.

    Args:
        duration: how long the clip lasts (seconds)
        zoom_in: True = zoom in (1.0 → 1.6), False = zoom out (1.6 → 1.0)

    zoompan's `d` is number of frames to zoom over. We hold the zoom for the
    whole clip duration. `s` is the output size per frame.
    """
    total_frames = int(duration * FPS)
    zoom_max = 1.8
    # Increment per frame so we reach zoom_max at the last frame.
    # Larger range over same duration = faster-feeling motion.
    zoom_step = (zoom_max - 1.0) / max(total_frames, 1)

    if zoom_in:
        # z starts at 1.0 and grows
        z_expr = f"'min(zoom+{zoom_step:.6f},{zoom_max})'"
    else:
        # z starts at zoom_max and shrinks; use 'if' to init
        z_expr = f"'if(eq(on,0),{zoom_max},max(zoom-{zoom_step:.6f},1.0))'"

    # Keep the focal point centered
    x_expr = "'iw/2-(iw/zoom/2)'"
    y_expr = "'ih/2-(ih/zoom/2)'"

    # Scale input up first so zoompan has pixels to work with (avoids pixelation)
    scale = f"scale={OUTPUT_WIDTH*4}:{OUTPUT_HEIGHT*4}:force_original_aspect_ratio=increase,crop={OUTPUT_WIDTH*4}:{OUTPUT_HEIGHT*4}"
    zoompan = f"zoompan=z={z_expr}:x={x_expr}:y={y_expr}:d={total_frames}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:fps={FPS}"

    return f"{scale},{zoompan}"


def _make_clip(image_path: str, duration: float, zoom_in: bool, output_path: str):
    """Create a single zoom clip from one image."""
    vf = _build_zoompan_filter(duration, zoom_in)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg clip creation failed: {result.stderr[-500:]}")


def create_slideshow(audio_path: str, image_paths: list[str],
                     output_path: str = None) -> dict:
    """
    Create a slideshow video with Ken Burns zoom + audio.

    Returns dict with:
        video_path: final MP4 path
        duration: total duration in seconds
        per_image_duration: seconds per image
        image_count: number of images
    """
    if not image_paths:
        raise ValueError("At least one image is required")

    audio_path = str(audio_path)
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    for img in image_paths:
        if not os.path.exists(img):
            raise FileNotFoundError(f"Image not found: {img}")

    # Duration math
    audio_duration = get_audio_duration(audio_path)
    num_images = len(image_paths)
    per_image = audio_duration / num_images

    print(f"[Slideshow] Audio: {audio_duration:.2f}s, Images: {num_images}, "
          f"Per image: {per_image:.2f}s")

    output_path = output_path or str(TMP_DIR / "slideshow.mp4")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Working directory for per-image clips
    work_dir = Path(output_path).parent / "slideshow_clips"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Build one clip per image with alternating zoom direction
    clip_paths = []
    for i, img in enumerate(image_paths):
        clip_path = str(work_dir / f"clip_{i:04d}.mp4")
        zoom_in = (i % 2 == 0)  # even = zoom in, odd = zoom out
        print(f"[Slideshow] Creating clip {i+1}/{num_images} "
              f"({'zoom in' if zoom_in else 'zoom out'})")
        _make_clip(img, per_image, zoom_in, clip_path)
        clip_paths.append(clip_path)

    # Concat all clips (silent video first)
    concat_list = work_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for cp in clip_paths:
            # ffmpeg concat demuxer requires forward slashes / escaping
            safe_path = cp.replace("\\", "/").replace("'", r"\'")
            f.write(f"file '{safe_path}'\n")

    silent_video = str(work_dir / "silent.mp4")
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        silent_video,
    ]
    result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-500:]}")

    # Mux with audio (use shortest so trailing video is trimmed if any drift)
    mux_cmd = [
        "ffmpeg", "-y",
        "-i", silent_video,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mux failed: {result.stderr[-500:]}")

    # Clean up intermediate clips
    try:
        for cp in clip_paths:
            os.remove(cp)
        os.remove(silent_video)
        os.remove(concat_list)
    except Exception:
        pass

    return {
        "video_path": output_path,
        "duration": audio_duration,
        "per_image_duration": per_image,
        "image_count": num_images,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create slideshow video from images + audio")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--output", default=str(TMP_DIR / "slideshow.mp4"))
    args = parser.parse_args()

    result = create_slideshow(args.audio, args.images, args.output)
    print(json.dumps(result, indent=2))
