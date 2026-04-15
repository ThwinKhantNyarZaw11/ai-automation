# Gemini Text Generation (Shared)

## Goal
Generate text using Gemini API, primarily for Burmese-language content.

## Prerequisites
- `GEMINI_API_KEY` set in `.env`
- Model: gemini-2.0-flash (configurable via GEMINI_MODEL in .env)

## Script
- `execution/gemini_generate.py` — generic Gemini caller

## Usage
```python
from execution.gemini_generate import generate_text
result = generate_text("Your prompt", system_prompt="Optional system prompt")
```

## Burmese Language Guidelines
- Always include system prompt specifying Myanmar Unicode output
- Gemini handles Burmese well with explicit instruction
- Use storytelling format for video scripts
- Maintain consistent tone across scenes

## Wrapper Scripts
- `execution/burmese_script_gen.py` — WF1: script from source material
- `execution/video_script_gen.py` — WF3: script from video analysis
- `execution/script_modifier.py` — WF4: modify existing scripts
- `execution/comfyui_prompt_gen.py` — WF4: Burmese to English image prompts

## Edge Cases
- API key invalid → clear error message
- Rate limit → wait and retry (Gemini free tier: 15 RPM)
- Response empty → retry with rephrased prompt
- Content blocked → adjust prompt, remove sensitive terms
