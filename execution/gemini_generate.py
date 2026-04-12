"""
Generic Gemini API text generation.
Usage: python -m execution.gemini_generate --prompt "..." [--system_prompt "..."] [--output_path out.txt]
"""
import argparse
import google.generativeai as genai

from execution.config import GEMINI_API_KEY, GEMINI_MODEL


def generate_text(prompt: str, system_prompt: str = None, model_name: str = None) -> str:
    """
    Call Gemini API and return the generated text.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=model_name or GEMINI_MODEL,
        system_instruction=system_prompt,
    )
    response = model.generate_content(prompt)
    return response.text


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
