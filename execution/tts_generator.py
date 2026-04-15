"""
Script-to-Voice using Gemini TTS API (gemini-2.5-pro-preview-tts).

Logic:
  - Read script file (DOCX or TXT), split into pages
  - Generate one WAV audio file per page in parallel (ThreadPoolExecutor)
  - Combine all page WAVs into one final MP3 via FFmpeg
  - Return path to the final combined MP3

Usage: python -m execution.tts_generator --script <path> --voice Kore --style "dramatic"
"""
import argparse
import base64
import io
import os
import re
import subprocess
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from execution.config import GEMINI_API_KEY, TMP_DIR


# ── Model & voice constants ──────────────────────────────────────────────────

TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Curated voice list with descriptions shown to the user
VOICE_LIST = [
    {"number": "1",  "name": "Kore",            "description": "Firm, authoritative"},
    {"number": "2",  "name": "Charon",          "description": "Informational, clear"},
    {"number": "3",  "name": "Aoede",           "description": "Breezy, natural"},
    {"number": "4",  "name": "Puck",            "description": "Upbeat, energetic"},
    {"number": "5",  "name": "Fenrir",          "description": "Excitable, dramatic"},
    {"number": "6",  "name": "Zephyr",          "description": "Bright, cheerful"},
    {"number": "7",  "name": "Leda",            "description": "Youthful, fresh"},
    {"number": "8",  "name": "Sulafat",         "description": "Warm, inviting"},
    {"number": "9",  "name": "Gacrux",          "description": "Mature, deep"},
    {"number": "10", "name": "Schedar",         "description": "Even, balanced"},
    {"number": "11", "name": "Achernar",        "description": "Soft, gentle"},
    {"number": "12", "name": "Orus",            "description": "Firm, strong"},
    {"number": "13", "name": "Enceladus",       "description": "Breathy, intimate"},
    {"number": "14", "name": "Iapetus",         "description": "Clear, precise"},
    {"number": "15", "name": "Sadaltager",      "description": "Knowledgeable, trustworthy"},
]

# Approx characters per script page (~55 lines × ~50 chars)
CHARS_PER_PAGE = 2750

# TTS retry config
MAX_RETRIES = 6             # more tolerance for paid-tier rate limiting
INITIAL_WAIT = 5            # seconds, used only when server gives no hint
RATE_LIMIT_BUFFER = 2       # extra seconds on top of the server's retryDelay


def _parse_retry_delay(error_str: str) -> Optional[float]:
    """
    Parse the 'retryDelay' or 'Please retry in Ns' hint out of a Gemini 429
    error. Returns seconds as a float, or None if no hint is present.
    """
    # Match '"retryDelay": "53s"' or similar
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)\s*s", error_str)
    if m:
        return float(m.group(1))
    # Match 'Please retry in 53.57144064s'
    m = re.search(r"retry in\s+(\d+(?:\.\d+)?)\s*s", error_str, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def format_voice_menu() -> str:
    """Return a formatted voice selection menu string."""
    lines = ["**Available Voice Models:**\n"]
    for v in VOICE_LIST:
        lines.append(f"  {v['number']:>2}. **{v['name']}** — {v['description']}")
    lines.append("\nType the number or name of the voice you want.")
    return "\n".join(lines)


def resolve_voice(choice: str) -> Optional[str]:
    """
    Resolve user input to a valid voice name.
    Accepts number (1-15) or voice name (case-insensitive).
    Returns None if not found.
    """
    choice = choice.strip()
    # By number
    for v in VOICE_LIST:
        if choice == v["number"]:
            return v["name"]
    # By name (case-insensitive)
    for v in VOICE_LIST:
        if choice.lower() == v["name"].lower():
            return v["name"]
    return None


# ── Text extraction & page splitting ────────────────────────────────────────

def extract_text_pages(file_path: str) -> list[str]:
    """
    Extract text from DOCX or TXT file and split into pages.

    For DOCX: detect explicit page breaks first. If none found, split by
              paragraph count (~30 paragraphs per page).
    For TXT:  split on form-feed characters (\f) first. If none, split by
              character count (~CHARS_PER_PAGE chars, breaking at newlines).
    Returns a list of page strings (at least 1 element).
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".docx":
        return _extract_docx_pages(file_path)
    else:
        # Treat everything else as plain text
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        return _split_text_pages(text)


def _extract_docx_pages(file_path: str) -> list[str]:
    """Extract pages from a DOCX file, respecting explicit page breaks."""
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(file_path)
    pages: list[str] = []
    current: list[str] = []

    def _flush():
        text = "\n".join(current).strip()
        if text:
            pages.append(text)
        current.clear()

    for para in doc.paragraphs:
        # Check for explicit page break before this paragraph
        if para._element.xml.find('w:pageBreakBefore') != -1:
            _flush()

        para_text = para.text.strip()

        # Check for page break inside runs
        has_page_break = False
        for run in para.runs:
            for br in run._element.findall(f'.//{qn("w:br")}'):
                if br.get(qn("w:type")) == "page":
                    has_page_break = True
                    break

        if has_page_break:
            if para_text:
                current.append(para_text)
            _flush()
        else:
            if para_text:
                current.append(para_text)

    _flush()

    # If no explicit breaks were found, fall back to char-count splitting
    if len(pages) == 1:
        full_text = pages[0]
        split = _split_text_pages(full_text)
        if len(split) > 1:
            return split

    return pages if pages else [""]


def _split_text_pages(text: str) -> list[str]:
    """
    Split plain text into pages.
    First tries form-feed (\f). Falls back to character-count chunks
    broken at the nearest newline.
    """
    # Try form-feed split
    if "\f" in text:
        pages = [p.strip() for p in text.split("\f") if p.strip()]
        if pages:
            return pages

    # Character-count split, break at newline boundaries
    lines = text.splitlines()
    pages: list[str] = []
    current_chars = 0
    current_lines: list[str] = []

    for line in lines:
        current_lines.append(line)
        current_chars += len(line) + 1  # +1 for newline
        if current_chars >= CHARS_PER_PAGE:
            pages.append("\n".join(current_lines).strip())
            current_lines = []
            current_chars = 0

    if current_lines:
        pages.append("\n".join(current_lines).strip())

    return [p for p in pages if p] or [text]


# ── TTS generation ───────────────────────────────────────────────────────────

def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000,
                channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM16 bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _generate_page_audio(
    page_text: str,
    voice_name: str,
    style_instruction: str,
    output_path: str,
    page_num: int,
) -> str:
    """
    Generate TTS audio for a single page with retry.
    Returns output_path on success.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env")

    # Prepend style instruction if provided
    prompt = page_text
    if style_instruction and style_instruction.strip():
        prompt = f"{style_instruction.strip()}\n\n{page_text}"

    client = genai.Client(api_key=GEMINI_API_KEY)
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=TTS_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name
                            )
                        )
                    ),
                ),
            )

            # Extract raw audio bytes from response
            audio_bytes = None
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    raw = part.inline_data.data
                    # SDK may return bytes or base64 string
                    if isinstance(raw, (bytes, bytearray)):
                        audio_bytes = bytes(raw)
                    else:
                        audio_bytes = base64.b64decode(raw)
                    break

            if not audio_bytes:
                raise RuntimeError(f"Page {page_num}: no audio data in response")

            # Wrap in WAV and save
            wav_bytes = _pcm_to_wav(audio_bytes)
            Path(output_path).write_bytes(wav_bytes)
            print(f"[TTS] Page {page_num} done -> {Path(output_path).name}")
            return output_path

        except Exception as e:
            error_str = str(e)
            is_429 = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
            is_503 = "503" in error_str or "UNAVAILABLE" in error_str

            if is_429 or is_503:
                # Prefer the server-supplied retryDelay when available (paid-tier
                # rate-limiter tells us exactly how long to wait).
                server_hint = _parse_retry_delay(error_str) if is_429 else None
                if server_hint is not None:
                    wait = server_hint + RATE_LIMIT_BUFFER
                    reason = f"rate limit, server hint {server_hint:.0f}s"
                else:
                    wait = INITIAL_WAIT * (2 ** attempt)
                    reason = "backoff"
                print(f"[TTS] Page {page_num} {('RATE-LIMITED' if is_429 else 'busy')} "
                      f"(attempt {attempt+1}/{MAX_RETRIES}, {reason}), "
                      f"retry in {wait:.0f}s...")
                time.sleep(wait)
                last_error = e
            else:
                raise

    raise last_error


def _combine_wavs_to_mp3(wav_paths: list[str], output_path: str):
    """Concatenate multiple WAV files and encode as MP3 via FFmpeg."""
    work_dir = Path(output_path).parent
    concat_list = work_dir / "tts_concat.txt"

    with open(concat_list, "w", encoding="utf-8") as f:
        for wp in wav_paths:
            safe = wp.replace("\\", "/").replace("'", r"\'")
            f.write(f"file '{safe}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", "24000",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg combine failed: {result.stderr[-500:]}")

    # Clean up concat list
    try:
        concat_list.unlink()
    except Exception:
        pass


# ── Main entry point ─────────────────────────────────────────────────────────

def generate_speech(
    script_path: str,
    voice_name: str,
    style_instruction: str = "",
    output_path: str = None,
    max_workers: int = 8,
) -> dict:
    """
    Full pipeline: read script → split pages → parallel TTS → combine → MP3.

    Args:
        script_path:       Path to the script file (.docx or .txt).
        voice_name:        Gemini TTS voice name (e.g. "Kore").
        style_instruction: Speaking style hint sent before each page.
        output_path:       Where to save the final MP3. Auto-generated if None.
        max_workers:       Max parallel TTS requests.

    Returns dict with:
        audio_path:   final MP3 path
        page_count:   number of pages processed
        voice:        voice name used
    """
    script_path = str(script_path)
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")

    # Split into pages
    pages = extract_text_pages(script_path)
    page_count = len(pages)
    print(f"[TTS] {page_count} page(s) detected in script")

    # Prepare output paths
    output_path = output_path or str(TMP_DIR / "script_audio.mp3")
    work_dir = Path(output_path).parent / "tts_pages"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Generate page audio files in parallel
    page_wav_paths = [None] * page_count

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _generate_page_audio,
                pages[i],
                voice_name,
                style_instruction,
                str(work_dir / f"page_{i+1:04d}.wav"),
                i + 1,
            ): i
            for i in range(page_count)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            page_wav_paths[idx] = future.result()  # raises on error

    # Combine all page WAVs → final MP3 (in order)
    print(f"[TTS] Combining {page_count} page(s) into final MP3...")
    _combine_wavs_to_mp3(page_wav_paths, output_path)

    # Clean up individual page WAVs
    for wp in page_wav_paths:
        try:
            os.remove(wp)
        except Exception:
            pass
    try:
        work_dir.rmdir()
    except Exception:
        pass

    return {
        "audio_path": output_path,
        "page_count": page_count,
        "voice": voice_name,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script-to-Voice via Gemini TTS")
    parser.add_argument("--script",  required=True, help="Path to .docx or .txt script")
    parser.add_argument("--voice",   default="Kore", help="Voice name (e.g. Kore)")
    parser.add_argument("--style",   default="", help="Style instruction")
    parser.add_argument("--output",  default=str(TMP_DIR / "script_audio.mp3"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    result = generate_speech(
        args.script, args.voice, args.style, args.output, args.workers
    )
    print(f"Done! Audio: {result['audio_path']}, Pages: {result['page_count']}, Voice: {result['voice']}")
