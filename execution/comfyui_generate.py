"""
Send prompts to a running ComfyUI server and retrieve generated images.
Requires ComfyUI running locally.
Usage: python -m execution.comfyui_generate --prompt_json <path> [--output_path <path>]
"""
import argparse
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

from execution.config import COMFYUI_URL, TMP_DIR


def queue_prompt(prompt: dict, server_url: str = None) -> str:
    """Queue a prompt on ComfyUI and return the prompt_id."""
    server_url = server_url or COMFYUI_URL
    data = json.dumps({"prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        f"{server_url}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    response = urllib.request.urlopen(req)
    result = json.loads(response.read())
    return result["prompt_id"]


def wait_for_result(prompt_id: str, server_url: str = None, timeout: int = 300) -> dict:
    """Poll ComfyUI until the prompt is complete."""
    server_url = server_url or COMFYUI_URL
    start = time.time()

    while time.time() - start < timeout:
        response = urllib.request.urlopen(f"{server_url}/history/{prompt_id}")
        history = json.loads(response.read())

        if prompt_id in history:
            return history[prompt_id]

        time.sleep(2)

    raise TimeoutError(f"ComfyUI did not complete within {timeout}s")


def download_image(filename: str, subfolder: str, folder_type: str, server_url: str = None, output_path: str = None) -> str:
    """Download a generated image from ComfyUI."""
    server_url = server_url or COMFYUI_URL
    params = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
    url = f"{server_url}/view?{params}"

    output_path = output_path or str(TMP_DIR / filename)
    urllib.request.urlretrieve(url, output_path)
    return output_path


def generate_image(prompt_data: dict, output_path: str = None, server_url: str = None) -> str:
    """
    Full pipeline: queue prompt, wait, download result.
    prompt_data should be a ComfyUI workflow dict.
    Returns path to the generated image.
    """
    server_url = server_url or COMFYUI_URL

    prompt_id = queue_prompt(prompt_data, server_url)
    history = wait_for_result(prompt_id, server_url)

    # Find output images
    outputs = history.get("outputs", {})
    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for img in node_output["images"]:
                return download_image(
                    img["filename"],
                    img.get("subfolder", ""),
                    img.get("type", "output"),
                    server_url,
                    output_path,
                )

    raise RuntimeError("No images found in ComfyUI output")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate image with ComfyUI")
    parser.add_argument("--prompt_json", required=True)
    parser.add_argument("--output_path", default=None)
    parser.add_argument("--comfyui_url", default=COMFYUI_URL)
    args = parser.parse_args()

    with open(args.prompt_json, "r") as f:
        prompt = json.load(f)

    result = generate_image(prompt, args.output_path, args.comfyui_url)
    print(f"Image saved to: {result}")
