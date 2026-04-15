"""
Modify an existing script based on user instructions using Gemini.
Usage: python -m execution.script_modifier --script_path <path> --instructions "..."
"""
import argparse
from pathlib import Path

from execution.gemini_generate import generate_text
from execution.config import TMP_DIR


def _read_script(script_path: str) -> str:
    """Read script text from .txt, .md, or .docx files."""
    p = Path(script_path)
    ext = p.suffix.lower()

    if ext == ".docx":
        from docx import Document
        doc = Document(str(p))
        return "\n".join(para.text for para in doc.paragraphs)
    else:
        # Try utf-8, fall back to other encodings
        for encoding in ["utf-8", "utf-16", "cp1252", "latin-1"]:
            try:
                return p.read_text(encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        # Last resort: read as binary and decode with replacement
        return p.read_bytes().decode("utf-8", errors="replace")


def modify_script(script_path: str, instructions: str, output_path: str = None,
                  language: str = "Burmese", target_words: int = 3000) -> str:
    """Modify an existing script based on user instructions."""
    script_text = _read_script(script_path)

    system_prompt = f"""You are an expert script editor. You write scripts in {language}.

Guidelines:
- Output entirely in {language}
- Follow the user's modification instructions precisely
- Preserve the overall structure unless told otherwise
- Maintain quality and coherence
- Write EXACTLY {target_words} words
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Just write continuous, seamless script text"""

    prompt = f"""Original Script:
{script_text}

Modification Instructions:
{instructions}

Rewrite the script with these changes applied. Write exactly {target_words} words in {language}."""

    result = generate_text(prompt, system_prompt=system_prompt)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Modify script")
    parser.add_argument("--script_path", required=True)
    parser.add_argument("--instructions", required=True)
    parser.add_argument("--output_path", default=str(TMP_DIR / "modified_script.txt"))
    parser.add_argument("--language", default="Burmese")
    parser.add_argument("--target_words", type=int, default=3000)
    args = parser.parse_args()

    result = modify_script(args.script_path, args.instructions, args.output_path,
                           args.language, args.target_words)
    print(result)
