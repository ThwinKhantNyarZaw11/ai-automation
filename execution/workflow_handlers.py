"""
Workflow step handlers. Each function handles one step of a workflow:
validates input, calls execution scripts, updates state, returns response messages.
"""
import re
import traceback
from pathlib import Path
from execution.state_manager import (
    State, get_state, set_state, set_workflow, get_data, set_data, reset_session
)
from execution.file_handler import cleanup_session


# Characters not allowed in Windows/Unix filenames
_UNSAFE_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _safe_stem(name: str, fallback: str = "output") -> str:
    """
    Turn an original filename (or arbitrary label like a video title) into a
    filesystem-safe stem. Strips the extension (if any), removes unsafe
    characters, collapses whitespace, trims length. Returns `fallback` if
    nothing usable remains.
    """
    if not name:
        return fallback
    s = str(name)
    # Strip only the final extension if present (don't let Path split on '/')
    if "." in s:
        base, _, ext = s.rpartition(".")
        # Only treat as extension if it's short and alnum (not part of a title)
        if base and 0 < len(ext) <= 5 and ext.isalnum():
            s = base
    # Remove filesystem-unsafe characters
    s = _UNSAFE_FS_CHARS.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    # Limit to 80 chars so the full path stays well under OS limits
    s = s[:80].rstrip()
    return s or fallback


WELCOME_MESSAGE = """Welcome! Please choose a workflow:
1. Source Finder & Script Generator
2. Video + Audio Combiner
3. Video Changer
4. Script Changer
5. Image + Audio Slideshow
6. Script to Voice

Type the number or name of the workflow you want to use."""


WORKFLOW_INTROS = {
    "1": {"name": "Source Finder & Script Generator", "msg": "Please send a YouTube video link."},
    "2": {"name": "Video + Audio Combiner", "msg": "Please send:\n1. A video file\n2. An audio file"},
    "3": {"name": "Video Changer", "msg": "Please send a video file."},
    "4": {"name": "Script Changer", "msg": "Please send your script file."},
    "5": {"name": "Image + Audio Slideshow", "msg": "Please send:\n1. An audio file (mp3, wav, m4a, etc.)\n2. Multiple image files (jpg, png)\n\nI'll create a slideshow video with zoom-in/zoom-out animation between images, timed to match your audio length."},
    "6": {"name": "Script to Voice", "msg": "Please upload your script file (.docx or .txt).\n\nI'll read each page in parallel and combine them into one audio file."},
}

WORKFLOW_INIT = {
    "1": ("wf1", State.WF1_AWAITING_LINK),
    "2": ("wf2", State.WF2_AWAITING_FILES),
    "3": ("wf3", State.WF3_AWAITING_VIDEO),
    "4": ("wf4", State.WF4_AWAITING_SCRIPT),
    "5": ("wf5", State.WF5_AWAITING_FILES),
    "6": ("wf6", State.WF6_AWAITING_SCRIPT),
}


def get_workflow_welcome(session_id: str, workflow_num: str) -> list[dict]:
    """Initialize a session directly into a specific workflow and return welcome messages."""
    info = WORKFLOW_INTROS.get(workflow_num)
    init = WORKFLOW_INIT.get(workflow_num)
    if not info or not init:
        return [{"type": "message", "text": "Unknown workflow."}]

    wf_key, initial_state = init
    set_workflow(session_id, wf_key)
    set_state(session_id, initial_state)
    return [
        {"type": "workflow_started", "workflow": workflow_num, "name": info["name"]},
        {"type": "message", "text": info["msg"]},
    ]


def is_youtube_url(text: str) -> bool:
    return bool(re.search(r'(youtube\.com/watch|youtu\.be/)', text))


async def handle_message(session_id: str, text: str, files: list[dict] = None) -> list[dict]:
    """
    Main message router. Returns a list of response messages.
    Each message is a dict: {"type": "message"|"sources"|"images"|"prompt"|"status"|"file_ready", ...}
    """
    state = get_state(session_id)
    files = files or []

    try:
        # Global restart from any state
        if text.strip().lower() in ["restart", "reset", "start"]:
            cleanup_session(session_id)
            reset_session(session_id)
            return [{"type": "message", "text": WELCOME_MESSAGE}]

        # IDLE — route to workflow
        if state == State.IDLE:
            return _handle_idle(session_id, text)

        # Workflow 1
        if state.name.startswith("WF1"):
            return await _handle_wf1(session_id, state, text, files)

        # Workflow 2
        if state.name.startswith("WF2"):
            return await _handle_wf2(session_id, state, text, files)

        # Workflow 3
        if state.name.startswith("WF3"):
            return await _handle_wf3(session_id, state, text, files)

        # Workflow 4
        if state.name.startswith("WF4"):
            return await _handle_wf4(session_id, state, text, files)

        # Workflow 5
        if state.name.startswith("WF5"):
            return await _handle_wf5(session_id, state, text, files)

        # Workflow 6
        if state.name.startswith("WF6"):
            return await _handle_wf6(session_id, state, text, files)

    except Exception as e:
        traceback.print_exc()
        return [{"type": "message", "text": f"Error: {str(e)}\nPlease try again or type 'restart' to start over."}]

    return [{"type": "message", "text": WELCOME_MESSAGE}]


# Aliases that map user text → workflow number (in addition to "1".."6")
_IDLE_ALIASES = {
    "source finder": "1", "source": "1",
    "video audio": "2", "combiner": "2", "combine": "2",
    "video changer": "3", "video": "3",
    "script changer": "4", "script": "4",
    "image audio": "5", "slideshow": "5", "image + audio": "5",
    "script to voice": "6", "voice": "6", "tts": "6",
}


def _handle_idle(session_id: str, text: str) -> list[dict]:
    text_lower = text.strip().lower()

    if text_lower in ("restart", "reset", "start"):
        reset_session(session_id)
        return [{"type": "message", "text": WELCOME_MESSAGE}]

    wf_num = text_lower if text_lower in WORKFLOW_INIT else _IDLE_ALIASES.get(text_lower)
    if not wf_num:
        return [{"type": "message", "text": WELCOME_MESSAGE}]

    wf_key, initial_state = WORKFLOW_INIT[wf_num]
    set_workflow(session_id, wf_key)
    set_state(session_id, initial_state)
    return [{"type": "message", "text": WORKFLOW_INTROS[wf_num]["msg"]}]


# ─── Workflow 1: Source Finder + Script Generator ───

CHUNK_SIZE = 3000  # max words per generation/response


async def _handle_wf1(session_id: str, state: State, text: str, files: list) -> list[dict]:
    if state == State.WF1_AWAITING_LINK:
        if not is_youtube_url(text):
            return [{"type": "message", "text": "That doesn't look like a YouTube URL. Please send a valid YouTube link."}]

        set_state(session_id, State.WF1_EXTRACTING)
        set_data(session_id, "youtube_url", text.strip())

        # Extract metadata
        from execution.youtube_extract import extract_metadata
        from execution.file_handler import get_session_dir

        session_dir = str(get_session_dir(session_id))
        metadata = extract_metadata(text.strip(), session_dir)
        set_data(session_id, "metadata", metadata)
        # Use video title as the "original file name" source for outputs
        set_data(session_id, "source_name", metadata.get("title", "script"))

        # Search for sources
        set_state(session_id, State.WF1_SEARCHING_SOURCES)
        from execution.source_finder import search_sources

        search_query = f"{metadata['title']} {metadata.get('channel', '')}"
        sources = search_sources(search_query)
        set_data(session_id, "sources", sources)

        set_state(session_id, State.WF1_SHOWING_RESULTS)

        responses = [
            {"type": "message", "text": f"Video: {metadata['title']}\nChannel: {metadata.get('channel', 'N/A')}\nDuration: {metadata.get('duration', 0)}s"},
            {"type": "sources", "data": sources.get("sources", [])},
            {"type": "images", "urls": [img["image_url"] for img in sources.get("images", [])[:5]]},
            {"type": "prompt", "text": "Do you want me to generate a script based on this video?", "options": ["yes", "no"]},
        ]
        return responses

    elif state == State.WF1_SHOWING_RESULTS:
        if text.strip().lower() in ["yes", "y", "1"]:
            set_state(session_id, State.WF1_ASK_LANGUAGE)
            return [{"type": "message", "text": "Which language do you want the script in?\n\n(e.g. Burmese, English, Thai, Chinese, Japanese, Korean, Hindi, or any language you prefer)"}]
        else:
            set_state(session_id, State.WF1_COMPLETE)
            return [{"type": "prompt", "text": "Do you want to process another video?", "options": ["yes", "no"]}]

    elif state == State.WF1_ASK_LANGUAGE:
        language = text.strip()
        set_data(session_id, "language", language)
        set_state(session_id, State.WF1_ASK_PROMPT)
        return [{"type": "message", "text": f"Language set to: {language}\n\nNow please provide:\n1. Your prompt/instructions for this script (e.g. \"write as a news reporter\", \"storytelling style\", \"educational documentary\")\n2. How many words do you want? (e.g. 3000, 5000, 7000)"}]

    elif state == State.WF1_ASK_PROMPT:
        # Parse the user's message for word count and prompt
        user_input = text.strip()

        # Try to extract a number for word count
        numbers = re.findall(r'\d+', user_input)
        target_words = 3000  # default
        for n in numbers:
            n_int = int(n)
            if 1000 <= n_int <= 50000:
                target_words = n_int
                break

        # The rest is the prompt/style instruction
        user_prompt = re.sub(r'\d{3,}', '', user_input).strip()
        if not user_prompt:
            user_prompt = "Write a detailed, engaging script"

        set_data(session_id, "user_prompt", user_prompt)
        set_data(session_id, "target_words", target_words)
        set_data(session_id, "full_script", "")
        set_data(session_id, "words_generated", 0)

        # Generate first chunk
        return await _generate_wf1_chunk(session_id)

    elif state == State.WF1_CONTINUING:
        if text.strip().lower() in ["next", "continue", "more"]:
            return await _generate_wf1_chunk(session_id)
        elif text.strip().lower() in ["done", "stop", "finish", "end"]:
            return await _finish_wf1_script(session_id)
        else:
            return [{"type": "prompt", "text": "Send 'next' to continue generating, or 'done' to finish and save.", "options": ["next", "done"]}]

    elif state == State.WF1_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


async def _generate_wf1_chunk(session_id: str) -> list[dict]:
    """Generate the next chunk of the script (~3000 words)."""
    from execution.gemini_generate import generate_text

    data = get_data(session_id)
    metadata = data.get("metadata", {})
    sources = data.get("sources", {})
    language = data.get("language", "English")
    user_prompt = data.get("user_prompt", "")
    target_words = data.get("target_words", 3000)
    full_script = data.get("full_script", "")
    words_generated = data.get("words_generated", 0)

    # How many words left?
    words_remaining = target_words - words_generated
    words_this_chunk = min(CHUNK_SIZE, words_remaining)

    if words_this_chunk <= 0:
        return await _finish_wf1_script(session_id)

    # Build source context
    source_texts = ""
    for s in sources.get("sources", [])[:5]:
        source_texts += f"- {s.get('title', '')}: {s.get('snippet', '')}\n"

    is_final = not full_script and words_this_chunk >= target_words  # single-chunk script
    if full_script:
        is_final = (words_remaining <= CHUNK_SIZE)

    no_end_rule = "" if is_final else (
        f"\n- ABSOLUTELY DO NOT conclude, wrap up, or end the story in this chunk. "
        f"The full script must be {target_words} words total — you have only written "
        f"{words_generated} so far. This is a MIDDLE section. Leave the narrative open "
        f"and mid-flow so the next chunk can continue seamlessly."
        f"\n- Do NOT write any closing phrases, moral lessons, or 'the end' type sentences."
    )

    system_prompt = f"""You are a professional scriptwriter. You write scripts in {language}.

USER'S STYLE INSTRUCTIONS: {user_prompt}

OVERALL TARGET: {target_words} words total. Written so far: {words_generated}. This chunk: {words_this_chunk} words.

CRITICAL RULES:
- Write ENTIRELY in {language}
- Write EXACTLY {words_this_chunk} words
- Follow the user's style/prompt instructions precisely
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Do NOT repeat introductions or re-introduce the topic
- Just write continuous, seamless script text that flows naturally{no_end_rule}"""

    if not full_script:
        # First chunk — start the script
        prompt = f"""Write the beginning of a long script ({words_this_chunk} words) based on this video:
This is the START of a {target_words}-word script. Do NOT conclude or end the story — leave it mid-flow.

Title: {metadata.get('title', '')}
Description: {metadata.get('description', '')[:500]}
Channel: {metadata.get('channel', '')}
Tags: {', '.join(metadata.get('tags', [])[:10])}

Related Sources:
{source_texts}

Start the script directly. No title, no labels. Just begin naturally in {language}.
Write exactly {words_this_chunk} words. Do NOT end the story."""
    else:
        # Continuation — pick up from where we left off
        last_part = full_script[-1500:]

        if is_final:
            prompt = f"""Continue and CONCLUDE this script. Write exactly {words_this_chunk} words in {language}.

The script so far ends with:
\"\"\"
{last_part}
\"\"\"

Write the final {words_this_chunk} words. Bring the script to a satisfying conclusion.
Continue directly from where it left off. No labels, no headers."""
        else:
            prompt = f"""Continue this script. Write exactly {words_this_chunk} words in {language}.
You have written {words_generated}/{target_words} words. This is a MIDDLE chunk — do NOT end or conclude the story.

The script so far ends with:
\"\"\"
{last_part}
\"\"\"

Continue directly from where it left off. No labels, no headers, no re-introductions, no conclusions. Leave the narrative mid-flow."""

    set_state(session_id, State.WF1_GENERATING_SCRIPT)
    chunk_text = generate_text(prompt, system_prompt=system_prompt)

    # Update stored script
    full_script += chunk_text.strip() + "\n\n"
    chunk_words = len(chunk_text.split())
    words_generated += chunk_words

    set_data(session_id, "full_script", full_script)
    set_data(session_id, "words_generated", words_generated)

    responses = [
        {"type": "message", "text": chunk_text.strip()},
        {"type": "status", "text": f"Words so far: {words_generated} / {target_words}"},
    ]

    if words_generated >= target_words:
        # Target reached — finish automatically
        return responses + await _finish_wf1_script(session_id)
    else:
        # More to go — wait for "next"
        set_state(session_id, State.WF1_CONTINUING)
        responses.append({"type": "prompt", "text": f"{target_words - words_generated} words remaining. Send 'next' to continue or 'done' to finish early.", "options": ["next", "done"]})
        return responses


async def _finish_wf1_script(session_id: str) -> list[dict]:
    """Save the full script and upload to Drive."""
    from execution.file_handler import get_session_dir
    from execution.google_drive_upload import upload_to_drive

    data = get_data(session_id)
    full_script = data.get("full_script", "")
    words_generated = data.get("words_generated", 0)

    # Save full script using the source video's title as filename
    stem = _safe_stem(data.get("source_name"), fallback="script")
    filename = f"{stem}.txt"
    output_path = str(get_session_dir(session_id) / filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_script.strip())
    set_data(session_id, "script_path", output_path)

    # Upload to Drive
    set_state(session_id, State.WF1_UPLOADING)
    drive_result = upload_to_drive(output_path)
    set_data(session_id, "drive_url", drive_result["url"])

    set_state(session_id, State.WF1_COMPLETE)
    return [
        {"type": "message", "text": f"Script complete! Total words: {words_generated}"},
        {"type": "file_ready", "filename": filename, "drive_url": drive_result["url"]},
        {"type": "prompt", "text": "Do you want to process another video?", "options": ["yes", "no"]},
    ]


# ─── Workflow 2: Video + Audio Combiner ───

async def _handle_wf2(session_id: str, state: State, text: str, files: list) -> list[dict]:
    if state == State.WF2_AWAITING_FILES:
        data = get_data(session_id)

        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in ["mp4", "mov", "avi", "mkv", "webm"] and "video_path" not in data:
                set_data(session_id, "video_path", f["path"])
                set_data(session_id, "source_name", f["filename"])
            elif ext in ["mp3", "wav", "aac", "flac", "ogg", "m4a"] and "audio_path" not in data:
                set_data(session_id, "audio_path", f["path"])

        data = get_data(session_id)
        if "video_path" in data and "audio_path" in data:
            set_state(session_id, State.WF2_PROCESSING)

            from execution.ffmpeg_combine import combine_video_audio
            from execution.file_handler import get_session_dir

            stem = _safe_stem(data.get("source_name"), fallback="combined")
            filename = f"{stem}.mp4"
            output_path = str(get_session_dir(session_id) / filename)
            combine_video_audio(data["video_path"], data["audio_path"], output_path)
            set_data(session_id, "output_path", output_path)

            set_state(session_id, State.WF2_UPLOADING)
            from execution.google_drive_upload import upload_to_drive
            drive_result = upload_to_drive(output_path)

            set_state(session_id, State.WF2_COMPLETE)
            return [
                {"type": "status", "text": "We are combining your files, please wait a moment..."},
                {"type": "file_ready", "filename": filename, "drive_url": drive_result["url"]},
                {"type": "message", "text": "Your video and audio have been combined successfully!"},
                {"type": "prompt", "text": "Do you want to process another file?", "options": ["yes", "no"]},
            ]
        else:
            missing = []
            if "video_path" not in data:
                missing.append("video")
            if "audio_path" not in data:
                missing.append("audio")
            return [{"type": "message", "text": f"Still waiting for: {', '.join(missing)} file(s). Please upload them."}]

    elif state == State.WF2_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


# ─── Workflow 3: Video Changer ───

async def _handle_wf3(session_id: str, state: State, text: str, files: list) -> list[dict]:
    if state == State.WF3_AWAITING_VIDEO:
        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in ["mp4", "mov", "avi", "mkv", "webm"]:
                set_data(session_id, "video_path", f["path"])
                set_data(session_id, "source_name", f["filename"])
                set_state(session_id, State.WF3_AWAITING_PROMPT)
                return [{"type": "message", "text": "Video received! Please describe what kind of script you want for this video.\n\n(e.g. \"write a documentary narration\", \"create a news report\", \"storytelling style\")"}]
        return [{"type": "message", "text": "Please send a video file."}]

    elif state == State.WF3_AWAITING_PROMPT:
        set_data(session_id, "user_prompt", text)
        set_state(session_id, State.WF3_ASK_LANGUAGE)
        return [{"type": "message", "text": "Which language do you want the script in?\n\n(e.g. Burmese, English, Thai, Chinese, Japanese, Korean, Hindi, or any language you prefer)"}]

    elif state == State.WF3_ASK_LANGUAGE:
        language = text.strip()
        set_data(session_id, "language", language)
        set_state(session_id, State.WF3_ASK_WORDCOUNT)
        return [{"type": "message", "text": f"Language set to: {language}\n\nHow many words do you want? (e.g. 3000, 5000, 7000)"}]

    elif state == State.WF3_ASK_WORDCOUNT:
        numbers = re.findall(r'\d+', text)
        target_words = 3000
        for n in numbers:
            n_int = int(n)
            if 500 <= n_int <= 50000:
                target_words = n_int
                break

        set_data(session_id, "target_words", target_words)
        set_data(session_id, "full_script", "")
        set_data(session_id, "words_generated", 0)

        # Analyze video with Gemini multimodal
        set_state(session_id, State.WF3_PROCESSING)
        from execution.video_analyze import analyze_video
        from execution.file_handler import get_session_dir

        session_dir = str(get_session_dir(session_id))
        analysis = analyze_video(get_data(session_id)["video_path"], session_dir)
        set_data(session_id, "video_analysis", analysis)

        # Generate first chunk
        return await _generate_wf3_chunk(session_id)

    elif state == State.WF3_CONTINUING:
        if text.strip().lower() in ["next", "continue", "more"]:
            return await _generate_wf3_chunk(session_id)
        elif text.strip().lower() in ["done", "stop", "finish", "end"]:
            return await _finish_wf3_script(session_id)
        else:
            return [{"type": "prompt", "text": "Send 'next' to continue generating, or 'done' to finish and save.", "options": ["next", "done"]}]

    elif state == State.WF3_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


async def _generate_wf3_chunk(session_id: str) -> list[dict]:
    """Generate the next chunk of the video script (~3000 words)."""
    from execution.gemini_generate import generate_text

    data = get_data(session_id)
    analysis = data.get("video_analysis", {})
    content_analysis = analysis.get("content_analysis", "")
    language = data.get("language", "English")
    user_prompt = data.get("user_prompt", "")
    target_words = data.get("target_words", 3000)
    full_script = data.get("full_script", "")
    words_generated = data.get("words_generated", 0)

    words_remaining = target_words - words_generated
    words_this_chunk = min(CHUNK_SIZE, words_remaining)

    if words_this_chunk <= 0:
        return await _finish_wf3_script(session_id)

    is_final = not full_script and words_this_chunk >= target_words
    if full_script:
        is_final = (words_remaining <= CHUNK_SIZE)

    no_end_rule = "" if is_final else (
        f"\n- ABSOLUTELY DO NOT conclude, wrap up, or end the story in this chunk. "
        f"The full script must be {target_words} words total — you have only written "
        f"{words_generated} so far. This is a MIDDLE section. Leave the narrative open "
        f"and mid-flow so the next chunk can continue seamlessly."
        f"\n- Do NOT write any closing phrases, moral lessons, or 'the end' type sentences."
    )

    system_prompt = f"""You are a professional scriptwriter. You write scripts in {language}.

USER'S STYLE INSTRUCTIONS: {user_prompt}

OVERALL TARGET: {target_words} words total. Written so far: {words_generated}. This chunk: {words_this_chunk} words.

CRITICAL RULES:
- Write ENTIRELY in {language}
- Write EXACTLY {words_this_chunk} words
- Base the script ACCURATELY on the video content analysis provided
- Follow the user's style/prompt instructions precisely
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Do NOT repeat introductions or re-introduce the topic
- Just write continuous, seamless script text that flows naturally{no_end_rule}"""

    if not full_script:
        prompt = f"""Write the beginning of a long script ({words_this_chunk} words) based on this video:
This is the START of a {target_words}-word script. Do NOT conclude or end the story — leave it mid-flow.

Video Content Analysis:
{content_analysis}

Start the script directly. No title, no labels. Just begin naturally in {language}.
Write exactly {words_this_chunk} words. Do NOT end the story."""
    else:
        last_part = full_script[-1500:]

        if is_final:
            prompt = f"""Continue and CONCLUDE this script. Write exactly {words_this_chunk} words in {language}.

Video Content Analysis:
{content_analysis}

The script so far ends with:
\"\"\"
{last_part}
\"\"\"

Write the final {words_this_chunk} words. Bring the script to a satisfying conclusion.
Continue directly from where it left off. No labels, no headers."""
        else:
            prompt = f"""Continue this script. Write exactly {words_this_chunk} words in {language}.
You have written {words_generated}/{target_words} words. This is a MIDDLE chunk — do NOT end or conclude the story.

Video Content Analysis:
{content_analysis}

The script so far ends with:
\"\"\"
{last_part}
\"\"\"

Continue directly from where it left off. No labels, no headers, no re-introductions, no conclusions. Leave the narrative mid-flow."""

    set_state(session_id, State.WF3_PROCESSING)
    chunk_text = generate_text(prompt, system_prompt=system_prompt)

    full_script += chunk_text.strip() + "\n\n"
    chunk_words = len(chunk_text.split())
    words_generated += chunk_words

    set_data(session_id, "full_script", full_script)
    set_data(session_id, "words_generated", words_generated)

    responses = [
        {"type": "message", "text": chunk_text.strip()},
        {"type": "status", "text": f"Words so far: {words_generated} / {target_words}"},
    ]

    if words_generated >= target_words:
        return responses + await _finish_wf3_script(session_id)
    else:
        set_state(session_id, State.WF3_CONTINUING)
        responses.append({"type": "prompt", "text": f"{target_words - words_generated} words remaining. Send 'next' to continue or 'done' to finish early.", "options": ["next", "done"]})
        return responses


async def _finish_wf3_script(session_id: str) -> list[dict]:
    """Save the full video script and upload to Drive."""
    from execution.file_handler import get_session_dir
    from execution.google_drive_upload import upload_to_drive

    data = get_data(session_id)
    full_script = data.get("full_script", "")
    words_generated = data.get("words_generated", 0)

    stem = _safe_stem(data.get("source_name"), fallback="video_script")
    filename = f"{stem}.txt"
    output_path = str(get_session_dir(session_id) / filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_script.strip())
    set_data(session_id, "script_path", output_path)

    set_state(session_id, State.WF3_UPLOADING)
    drive_result = upload_to_drive(output_path)
    set_data(session_id, "drive_url", drive_result["url"])

    set_state(session_id, State.WF3_COMPLETE)
    return [
        {"type": "message", "text": f"Script complete! Total words: {words_generated}"},
        {"type": "file_ready", "filename": filename, "drive_url": drive_result["url"]},
        {"type": "prompt", "text": "Do you want to process another video?", "options": ["yes", "no"]},
    ]


# ─── Workflow 4: Script Changer + Image Generation ───

async def _handle_wf4(session_id: str, state: State, text: str, files: list) -> list[dict]:
    if state == State.WF4_AWAITING_SCRIPT:
        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in ["txt", "docx", "doc", "md"]:
                set_data(session_id, "script_path", f["path"])
                set_data(session_id, "source_name", f["filename"])
                set_state(session_id, State.WF4_AWAITING_INSTRUCTIONS)
                return [{"type": "message", "text": "Script received! What changes do you want to make?"}]
        return [{"type": "message", "text": "Please send a script file (.txt, .docx, .md)."}]

    elif state == State.WF4_AWAITING_INSTRUCTIONS:
        set_data(session_id, "instructions", text)
        set_state(session_id, State.WF4_ASK_LANGUAGE)
        return [{"type": "message", "text": "Which language do you want the modified script in?\n\n(e.g. Burmese, English, Thai, Chinese, Japanese, Korean, Hindi, or any language you prefer)"}]

    elif state == State.WF4_ASK_LANGUAGE:
        language = text.strip()
        set_data(session_id, "language", language)
        set_state(session_id, State.WF4_ASK_WORDCOUNT)
        return [{"type": "message", "text": f"Language set to: {language}\n\nHow many words do you want? (e.g. 3000, 5000, 7000)"}]

    elif state == State.WF4_ASK_WORDCOUNT:
        numbers = re.findall(r'\d+', text)
        target_words = 3000
        for n in numbers:
            n_int = int(n)
            if 500 <= n_int <= 50000:
                target_words = n_int
                break

        set_data(session_id, "target_words", target_words)
        set_data(session_id, "full_script", "")
        set_data(session_id, "words_generated", 0)

        # Read the original script
        from execution.script_modifier import _read_script
        original_text = _read_script(get_data(session_id)["script_path"])
        set_data(session_id, "original_script_text", original_text)

        # Generate first chunk
        return await _generate_wf4_chunk(session_id)

    elif state == State.WF4_CONTINUING:
        if text.strip().lower() in ["next", "continue", "more"]:
            return await _generate_wf4_chunk(session_id)
        elif text.strip().lower() in ["done", "stop", "finish", "end"]:
            return await _finish_wf4_script(session_id)
        else:
            return [{"type": "prompt", "text": "Send 'next' to continue generating, or 'done' to finish and save.", "options": ["next", "done"]}]

    elif state == State.WF4_ASK_STYLE:
        set_data(session_id, "img_style", text.strip())
        set_state(session_id, State.WF4_ASK_CONSISTENCY)
        return [{"type": "prompt", "text": "Do you want **full consistency** across all scenes?\n\n- **yes** = characters, clothes, background, art style, and visual details stay identical across every scene\n- **no** = allow variation between scenes", "options": ["yes", "no"]}]

    elif state == State.WF4_ASK_CONSISTENCY:
        consistency = text.strip().lower() in ["yes", "y", "1", "true"]
        set_data(session_id, "img_consistency", consistency)
        set_state(session_id, State.WF4_GENERATING_PROMPTS)

        from execution.scene_splitter import split_into_scenes
        from execution.video_prompt_gen import generate_video_prompts
        from execution.gemini_generate import generate_text
        from execution.file_handler import get_session_dir
        from execution.google_drive_upload import upload_to_drive

        data = get_data(session_id)
        session_dir = get_session_dir(session_id)
        script_text = data.get("full_script", "") or data.get("original_script_text", "")

        # Auto-extract character + background from script
        excerpt = script_text[:3000]
        extract_response = generate_text(
            f"""Read the following script excerpt and extract:
1. CHARACTER DESIGN - visual details of main character(s): age, gender, ethnicity, clothing, hair, body type, facial features, distinctive traits. Infer from context if not explicit.
2. BACKGROUND / SETTING - visual details: location, architecture, landscape, lighting, weather, time of day, colors, atmosphere.

Script excerpt:
\"\"\"{excerpt}\"\"\"

Respond in EXACTLY this format:
CHARACTER: <description>
BACKGROUND: <description>"""
        )
        img_character = ""
        img_background = ""
        for line in extract_response.strip().splitlines():
            if line.upper().startswith("CHARACTER:"):
                img_character = line.split(":", 1)[1].strip()
            elif line.upper().startswith("BACKGROUND:"):
                img_background = line.split(":", 1)[1].strip()
        if not img_character:
            img_character = "A character appropriate to the script's setting and tone"
        if not img_background:
            img_background = "A setting appropriate to the script's context"
        set_data(session_id, "img_character", img_character)
        set_data(session_id, "img_background", img_background)
        print(f"[WF4] Auto-extracted character: {img_character[:100]}...")
        print(f"[WF4] Auto-extracted background: {img_background[:100]}...")

        # Split modified script into scenes
        scenes_path = str(session_dir / "scenes.json")
        scenes = split_into_scenes(data["modified_script_path"], output_path=scenes_path)
        set_data(session_id, "scenes", scenes)

        # Generate single prompt file (character sheets + scene T2I/I2V table)
        stem = _safe_stem(data.get("source_name"), fallback="script")
        result = generate_video_prompts(
            scenes=scenes,
            style=data.get("img_style", ""),
            character=img_character,
            background=img_background,
            consistency=consistency,
            output_dir=str(session_dir / "video_prompts"),
            name_prefix=stem,
            script_text=script_text,
        )

        # Upload prompt file to Drive
        prompt_drive = upload_to_drive(result["prompt_path"])
        prompt_name = Path(result["prompt_path"]).name

        set_state(session_id, State.WF4_COMPLETE)
        return [
            {"type": "message", "text": (
                f"Generated prompts for {len(scenes)} scenes!\n\n"
                f"**Style:** {data.get('img_style', '')}\n"
                f"**Consistency:** {'Yes' if consistency else 'No'}\n\n"
                f"The file contains:\n"
                f"- **Part 1:** Character design sheets (front/side/back views for each character)\n"
                f"- **Part 2:** Scene-by-scene Text-to-Image vs Image-to-Video prompts side by side"
            )},
            {"type": "file_ready", "filename": prompt_name, "drive_url": prompt_drive["url"]},
            {"type": "message", "text": (
                "**How to use:**\n"
                "1. Use the character sheet prompts in Grok/Midjourney to generate consistent character reference images\n"
                "2. Use T2I prompts to generate scene images in Grok/Midjourney\n"
                "3. Use I2V prompts in Runway/Kling/Luma to animate each scene image into video"
            )},
            {"type": "prompt", "text": "Do you want to process another script?", "options": ["yes", "no"]},
        ]

    elif state == State.WF4_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


async def _generate_wf4_chunk(session_id: str) -> list[dict]:
    """Generate the next chunk of the modified script (~3000 words)."""
    from execution.gemini_generate import generate_text

    data = get_data(session_id)
    original_text = data.get("original_script_text", "")
    instructions = data.get("instructions", "")
    language = data.get("language", "English")
    target_words = data.get("target_words", 3000)
    full_script = data.get("full_script", "")
    words_generated = data.get("words_generated", 0)

    words_remaining = target_words - words_generated
    words_this_chunk = min(CHUNK_SIZE, words_remaining)

    if words_this_chunk <= 0:
        return await _finish_wf4_script(session_id)

    is_final = (words_remaining <= CHUNK_SIZE)

    no_end_rule = "" if is_final else (
        f"\n- ABSOLUTELY DO NOT conclude, wrap up, or end the story in this chunk. "
        f"The full script must be {target_words} words total — you have only written "
        f"{words_generated} so far. This is a MIDDLE section. Leave the narrative open "
        f"and mid-flow so the next chunk can continue seamlessly."
        f"\n- Do NOT write any closing phrases, moral lessons, or 'the end' type sentences."
    )

    system_prompt = f"""You are an expert script editor. You write scripts in {language}.

MODIFICATION INSTRUCTIONS: {instructions}

OVERALL TARGET: {target_words} words total. Written so far: {words_generated}. This chunk: {words_this_chunk} words.

CRITICAL RULES:
- Write ENTIRELY in {language}
- Write EXACTLY {words_this_chunk} words
- Apply the modification instructions to transform the original script
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Do NOT repeat introductions or re-introduce the topic
- Just write continuous, seamless script text that flows naturally{no_end_rule}"""

    if not full_script:
        prompt = f"""Modify and rewrite the beginning of this script ({words_this_chunk} words) based on the instructions.
This is the START of a {target_words}-word script. Do NOT conclude or end the story — leave it mid-flow.

Original Script:
{original_text[:3000]}

Start the modified script directly. No title, no labels. Just begin naturally in {language}.
Write exactly {words_this_chunk} words. Do NOT end the story."""
    else:
        last_part = full_script[-1500:]
        # Calculate how much of the original we've roughly covered
        orig_words = len(original_text.split())
        coverage_ratio = words_generated / target_words if target_words > 0 else 0
        orig_start = int(coverage_ratio * orig_words)
        orig_section = " ".join(original_text.split()[max(0, orig_start - 200):orig_start + 1500])

        if is_final:
            prompt = f"""Continue and CONCLUDE this modified script. Write exactly {words_this_chunk} words in {language}.

Relevant section from original script:
{orig_section[:2000]}

The modified script so far ends with:
\"\"\"
{last_part}
\"\"\"

Write the final {words_this_chunk} words. Bring the script to a satisfying conclusion.
Continue directly from where it left off. No labels, no headers."""
        else:
            prompt = f"""Continue this modified script. Write exactly {words_this_chunk} words in {language}.
You have written {words_generated}/{target_words} words. This is a MIDDLE chunk — do NOT end or conclude the story.

Relevant section from original script:
{orig_section[:2000]}

The modified script so far ends with:
\"\"\"
{last_part}
\"\"\"

Continue directly from where it left off. No labels, no headers, no re-introductions, no conclusions. Leave the narrative mid-flow."""

    set_state(session_id, State.WF4_MODIFYING)
    chunk_text = generate_text(prompt, system_prompt=system_prompt)

    full_script += chunk_text.strip() + "\n\n"
    chunk_words = len(chunk_text.split())
    words_generated += chunk_words

    set_data(session_id, "full_script", full_script)
    set_data(session_id, "words_generated", words_generated)

    responses = [
        {"type": "message", "text": chunk_text.strip()},
        {"type": "status", "text": f"Words so far: {words_generated} / {target_words}"},
    ]

    if words_generated >= target_words:
        return responses + await _finish_wf4_script(session_id)
    else:
        set_state(session_id, State.WF4_CONTINUING)
        responses.append({"type": "prompt", "text": f"{target_words - words_generated} words remaining. Send 'next' to continue or 'done' to finish early.", "options": ["next", "done"]})
        return responses


async def _finish_wf4_script(session_id: str) -> list[dict]:
    """Save the full modified script and upload to Drive."""
    from execution.file_handler import get_session_dir
    from execution.google_drive_upload import upload_to_drive

    data = get_data(session_id)
    full_script = data.get("full_script", "")
    words_generated = data.get("words_generated", 0)

    stem = _safe_stem(data.get("source_name"), fallback="modified_script")
    filename = f"{stem}.txt"
    output_path = str(get_session_dir(session_id) / filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_script.strip())
    set_data(session_id, "modified_script_path", output_path)

    set_state(session_id, State.WF4_UPLOADING)
    drive_result = upload_to_drive(output_path)
    set_data(session_id, "drive_url", drive_result["url"])

    set_state(session_id, State.WF4_ASK_STYLE)
    return [
        {"type": "message", "text": f"Script modified! Total words: {words_generated}"},
        {"type": "file_ready", "filename": filename, "drive_url": drive_result["url"]},
        {"type": "message", "text": "Now let's create video prompts for your script.\n\nFirst, describe your **image generation style**.\n\n(e.g. \"3D Pixar style\", \"Disney animation\", \"photorealistic cinematic\", \"anime\", \"watercolor illustration\", \"cyberpunk\")"},
    ]


# ─── Workflow 5: Image + Audio Slideshow ───

async def _handle_wf5(session_id: str, state: State, text: str, files: list) -> list[dict]:
    if state == State.WF5_AWAITING_FILES:
        data = get_data(session_id)

        audio_exts = {"mp3", "wav", "aac", "flac", "ogg", "m4a"}
        image_exts = {"jpg", "jpeg", "png", "webp", "bmp"}

        audio_path = data.get("audio_path")
        image_paths = list(data.get("image_paths", []))
        audio_name = data.get("source_name")

        # Accept any newly uploaded files
        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in audio_exts and not audio_path:
                audio_path = f["path"]
                audio_name = f["filename"]
            elif ext in image_exts:
                image_paths.append(f["path"])

        set_data(session_id, "audio_path", audio_path)
        set_data(session_id, "image_paths", image_paths)
        if audio_name:
            set_data(session_id, "source_name", audio_name)

        # If we don't yet have both, tell the user what's missing
        if not audio_path or len(image_paths) < 1:
            missing = []
            if not audio_path:
                missing.append("audio file")
            if len(image_paths) < 1:
                missing.append("at least 1 image")
            have = []
            if audio_path:
                have.append("1 audio")
            if image_paths:
                have.append(f"{len(image_paths)} image(s)")
            have_str = ", ".join(have) if have else "nothing yet"
            return [{
                "type": "message",
                "text": f"Received: {have_str}.\nStill waiting for: {', '.join(missing)}.\n\nYou can upload multiple images at once. When done, send any message (e.g. 'go') to start processing."
            }]

        # Also allow the user to explicitly trigger with a message after all files uploaded
        # If they just uploaded files this turn, proceed automatically.
        set_state(session_id, State.WF5_PROCESSING)

        # Run the slideshow generation
        from execution.image_audio_slideshow import create_slideshow, get_audio_duration
        from execution.file_handler import get_session_dir
        from execution.google_drive_upload import upload_to_drive

        try:
            audio_duration = get_audio_duration(audio_path)
        except Exception as e:
            return [{"type": "message", "text": f"Could not read audio duration: {e}"}]

        num_images = len(image_paths)
        per_image = audio_duration / num_images

        status_msg = {
            "type": "status",
            "text": (
                f"Creating slideshow...\n"
                f"- Audio duration: {audio_duration:.1f}s\n"
                f"- Images: {num_images}\n"
                f"- Per image: {per_image:.1f}s\n"
                f"- Effect: alternating zoom in / zoom out"
            ),
        }

        stem = _safe_stem(get_data(session_id).get("source_name"), fallback="slideshow")
        filename = f"{stem}.mp4"
        output_path = str(get_session_dir(session_id) / filename)
        result = create_slideshow(audio_path, image_paths, output_path)

        set_state(session_id, State.WF5_UPLOADING)
        drive_result = upload_to_drive(output_path)

        set_state(session_id, State.WF5_COMPLETE)
        return [
            status_msg,
            {"type": "message", "text": f"Slideshow created! Duration: {result['duration']:.1f}s, {result['image_count']} images at {result['per_image_duration']:.1f}s each."},
            {"type": "file_ready", "filename": filename, "drive_url": drive_result["url"]},
            {"type": "prompt", "text": "Do you want to create another slideshow?", "options": ["yes", "no"]},
        ]

    elif state == State.WF5_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


# ─── Workflow 6: Script to Voice ────────────────────────────────────────────

async def _handle_wf6(session_id: str, state: State, text: str, files: list) -> list[dict]:
    from execution.tts_generator import (
        generate_speech, format_voice_menu, resolve_voice, extract_text_pages
    )
    from execution.config import TMP_DIR

    script_exts = {"docx", "txt", "doc"}

    # ── Step 1: Await script file upload ────────────────────────────────────
    if state == State.WF6_AWAITING_SCRIPT:
        script_path = None
        script_filename = None
        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in script_exts:
                script_path = f["path"]
                script_filename = f["filename"]
                break

        if not script_path:
            return [{"type": "message", "text": "Please upload a script file (.docx or .txt) to get started."}]

        set_data(session_id, "script_path", script_path)
        set_data(session_id, "script_filename", script_filename)

        # Count pages for info
        try:
            pages = extract_text_pages(script_path)
            page_count = len(pages)
        except Exception:
            page_count = "?"

        set_state(session_id, State.WF6_ASK_VOICE)
        return [
            {"type": "message", "text": f"Script received! Detected **{page_count}** page(s).\n\n{format_voice_menu()}"},
        ]

    # ── Step 2: Choose voice ─────────────────────────────────────────────────
    elif state == State.WF6_ASK_VOICE:
        voice_name = resolve_voice(text.strip())
        if not voice_name:
            return [{"type": "message", "text": f"Voice not recognised. Please enter a number (1-15) or a voice name.\n\n{format_voice_menu()}"}]

        set_data(session_id, "voice_name", voice_name)
        set_state(session_id, State.WF6_ASK_STYLE)
        return [{"type": "message", "text": (
            f"Voice set to **{voice_name}**.\n\n"
            "Now describe the **speaking style** for this script.\n\n"
            "Examples:\n"
            "- *Read this as a dramatic movie trailer narrator*\n"
            "- *Calm and professional news anchor tone*\n"
            "- *Warm storytelling voice for children*\n"
            "- *Energetic and motivational*\n\n"
            "Or type **skip** to use the default voice style."
        )}]

    # ── Step 3: Style instruction → process ─────────────────────────────────
    elif state == State.WF6_ASK_STYLE:
        style = "" if text.strip().lower() in ["skip", "none", "-"] else text.strip()
        set_data(session_id, "style_instruction", style)

        data = get_data(session_id)
        script_path = data.get("script_path")
        voice_name  = data.get("voice_name")

        try:
            pages = extract_text_pages(script_path)
            page_count = len(pages)
        except Exception:
            page_count = "?"

        set_state(session_id, State.WF6_PROCESSING)

        style_display = f'"{style}"' if style else "default"
        yield_status = {
            "type": "status",
            "text": (
                f"Generating audio…\n"
                f"- Voice: {voice_name}\n"
                f"- Style: {style_display}\n"
                f"- Pages: {page_count}\n"
                f"- Running {page_count} parallel TTS jobs then combining into one MP3"
            ),
        }

        # Save directly to .tmp with the original script's base filename
        # (e.g. "my_script.docx" -> ".tmp/my_script.mp3")
        original_filename = data.get("script_filename") or "script.mp3"
        base_stem = Path(original_filename).stem or "script"
        output_path = str(TMP_DIR / f"{base_stem}.mp3")

        result = generate_speech(
            script_path=script_path,
            voice_name=voice_name,
            style_instruction=style,
            output_path=output_path,
        )

        set_state(session_id, State.WF6_COMPLETE)
        saved_filename = Path(result["audio_path"]).name
        return [
            yield_status,
            {"type": "message", "text": (
                f"Audio generated successfully!\n\n"
                f"- **Voice:** {result['voice']}\n"
                f"- **Pages processed:** {result['page_count']}\n"
                f"- **Style:** {style_display}\n"
                f"- **Saved as:** `{saved_filename}`\n"
                f"- **Location:** `{result['audio_path']}`"
            )},
            {"type": "file_ready", "filename": saved_filename, "local_path": result["audio_path"]},
            {"type": "prompt", "text": "Do you want to convert another script?", "options": ["yes", "no"]},
        ]

    elif state == State.WF6_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


def _handle_restart(session_id: str, text: str) -> list[dict]:
    if text.strip().lower() in ["yes", "y", "1"]:
        cleanup_session(session_id)
        reset_session(session_id)
        return [{"type": "message", "text": WELCOME_MESSAGE}]
    else:
        cleanup_session(session_id)
        reset_session(session_id)
        return [{"type": "message", "text": "Session ended. Type anything to start again."}]
