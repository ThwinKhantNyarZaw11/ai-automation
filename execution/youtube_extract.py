"""
Extract metadata from a YouTube video URL using yt-dlp.
No video download — metadata only.
Usage: python -m execution.youtube_extract --url <youtube_url>
"""
import argparse
import json
from pathlib import Path
import yt_dlp

from execution.config import TMP_DIR


def extract_metadata(url: str, output_dir: str = None) -> dict:
    """
    Extract video metadata: title, description, channel, duration, tags, etc.
    Returns a dict with the metadata.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    metadata = {
        "url": url,
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "channel": info.get("channel", ""),
        "uploader": info.get("uploader", ""),
        "duration": info.get("duration", 0),
        "upload_date": info.get("upload_date", ""),
        "view_count": info.get("view_count", 0),
        "tags": info.get("tags", []),
        "categories": info.get("categories", []),
        "thumbnail": info.get("thumbnail", ""),
    }

    # Save to .tmp if output_dir provided
    if output_dir:
        out_path = Path(output_dir) / "youtube_metadata.json"
        out_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract YouTube video metadata")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output_dir", default=str(TMP_DIR))
    args = parser.parse_args()

    result = extract_metadata(args.url, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
