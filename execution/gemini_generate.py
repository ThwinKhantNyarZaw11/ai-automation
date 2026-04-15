"""
Generic Gemini API text generation using google.genai SDK.
Includes automatic retry with exponential backoff for 503/429 errors.
Usage: python -m execution.gemini_generate --prompt "..." [--system_prompt "..."] [--output_path out.txt]
"""
import argparse
import time
from google import genai

from execution.config import GEMINI_API_KEY, GEMINI_MODEL

# Retry config
MAX_RETRIES = 5
INITIAL_WAIT = 5  # seconds


def _retry_on_overload(func):
    """Decorator: retry API calls on 503/429 with exponential backoff."""
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e)
                # Retry on 503 (overloaded) or 429 (rate limit)
                if "503" in error_str or "429" in error_str or "UNAVAILABLE" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    wait_time = INITIAL_WAIT * (2 ** attempt)  # 5, 10, 20, 40, 80 seconds
                    print(f"[Gemini] Server busy (attempt {attempt + 1}/{MAX_RETRIES}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    last_error = e
                else:
                    raise  # Non-retryable error, raise immediately
        raise last_error  # All retries exhausted
    return wrapper


@_retry_on_overload
def generate_text(prompt: str, system_prompt: str = None, model_name: str = None) -> str:
    """
    Call Gemini API and return the generated text.
    Automatically retries on 503/429 errors with exponential backoff.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=GEMINI_API_KEY)

    config = {}
    if system_prompt:
        config["system_instruction"] = system_prompt

    response = client.models.generate_content(
        model=model_name or GEMINI_MODEL,
        contents=prompt,
        config=config if config else None,
    )
    return response.text


def generate_with_video(video_path: str, prompt: str, system_prompt: str = None, model_name: str = None) -> str:
    """
    Upload a video file to Gemini and generate text based on it.
    Uses the File API for videos. Retries on 503/429.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Upload the video file (with retry)
    video_file = _upload_with_retry(client, video_path)

    # Wait for file to be processed
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError(f"Video processing failed: {video_file.state}")

    # Generate content with retry
    config = {}
    if system_prompt:
        config["system_instruction"] = system_prompt

    response = _generate_content_with_retry(
        client, model_name, [video_file, prompt], config
    )

    # Clean up uploaded file
    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass

    return response.text


def _upload_with_retry(client, video_path: str, max_retries: int = 3):
    """Upload a file with retry on transient errors."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return client.files.upload(file=video_path)
        except Exception as e:
            error_str = str(e)
            if "503" in error_str or "429" in error_str or "UNAVAILABLE" in error_str:
                wait_time = INITIAL_WAIT * (2 ** attempt)
                print(f"[Gemini] Upload busy (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                last_error = e
            else:
                raise
    raise last_error


def _generate_content_with_retry(client, model_name, contents, config):
    """Generate content with retry on 503/429."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=model_name or GEMINI_MODEL,
                contents=contents,
                config=config if config else None,
            )
        except Exception as e:
            error_str = str(e)
            if "503" in error_str or "429" in error_str or "UNAVAILABLE" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = INITIAL_WAIT * (2 ** attempt)
                print(f"[Gemini] Server busy (attempt {attempt + 1}/{MAX_RETRIES}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                last_error = e
            else:
                raise
    raise last_error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate text with Gemini")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--system_prompt", default=None)
    parser.add_argument("--output_path", default=None)
    args = parser.parse_args()

    result = generate_text(args.prompt, args.system_prompt)

    if args.output_path:
        with open(args.output_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Output saved to {args.output_path}")
    else:
        print(result)
