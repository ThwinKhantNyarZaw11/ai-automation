"""
Workflow step handlers. Each function handles one step of a workflow:
validates input, calls execution scripts, updates state, returns response messages.
"""
import re
import traceback
from execution.state_manager import (
    State, get_state, set_state, set_workflow, get_data, set_data, reset_session
)
from execution.file_handler import cleanup_session


WELCOME_MESSAGE = """Welcome! Please choose a workflow:
1. Source Finder & Script Generator
2. Video + Audio Combiner
3. Video Changer
4. Script Changer
5. Image + Audio Slideshow

Type the number or name of the workflow you want to use."""


WORKFLOW_INTROS = {
    "1": {"name": "Source Finder & Script Generator", "msg": "Please send a YouTube video link."},
    "2": {"name": "Video + Audio Combiner", "msg": "Please send:\n1. A video file\n2. An audio file"},
    "3": {"name": "Video Changer", "msg": "Please send a video file."},
    "4": {"name": "Script Changer", "msg": "Please send your script file."},
    "5": {"name": "Image + Audio Slideshow", "msg": "Please send:\n1. An audio file (mp3, wav, m4a, etc.)\n2. Multiple image files (jpg, png)\n\nI'll create a slideshow video with zoom-in/zoom-out animation between images, timed to match your audio length."},
}

WORKFLOW_INIT = {
    "1": ("wf1", State.WF1_AWAITING_LINK),
    "2": ("wf2", State.WF2_AWAITING_FILES),
    "3": ("wf3", State.WF3_AWAITING_VIDEO),
    "4": ("wf4", State.WF4_AWAITING_SCRIPT),
    "5": ("wf5", State.WF5_AWAITING_FILES),
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

    except Exception as e:
        traceback.print_exc()
        return [{"type": "message", "text": f"Error: {str(e)}\nPlease try again or type 'restart' to start over."}]

    return [{"type": "message", "text": WELCOME_MESSAGE}]


def _handle_idle(session_id: str, text: str) -> list[dict]:
    text_lower = text.strip().lower()

    if text_lower in ["1", "source finder", "source"]:
        set_workflow(session_id, "wf1")
        set_state(session_id, State.WF1_AWAITING_LINK)
        return [{"type": "message", "text": "Please send a YouTube video link."}]

    elif text_lower in ["2", "video audio", "combiner", "combine"]:
        set_workflow(session_id, "wf2")
        set_state(session_id, State.WF2_AWAITING_FILES)
        return [{"type": "message", "text": "Please send:\n1. A video file\n2. An audio file"}]

    elif text_lower in ["3", "video changer", "video"]:
        set_workflow(session_id, "wf3")
        set_state(session_id, State.WF3_AWAITING_VIDEO)
        return [{"type": "message", "text": "Please send a video file."}]

    elif text_lower in ["4", "script changer", "script"]:
        set_workflow(session_id, "wf4")
        set_state(session_id, State.WF4_AWAITING_SCRIPT)
        return [{"type": "message", "text": "Please send your script file."}]

    elif text_lower in ["5", "image audio", "slideshow", "image + audio"]:
        set_workflow(session_id, "wf5")
        set_state(session_id, State.WF5_AWAITING_FILES)
        return [{"type": "message", "text": WORKFLOW_INTROS["5"]["msg"]}]

    elif text_lower in ["restart", "reset", "start"]:
        reset_session(session_id)
        return [{"type": "message", "text": WELCOME_MESSAGE}]

    else:
        return [{"type": "message", "text": WELCOME_MESSAGE}]


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
        import re as _re
        numbers = _re.findall(r'\d+', user_input)
        target_words = 3000  # default
        for n in numbers:
            n_int = int(n)
            if 1000 <= n_int <= 50000:
                target_words = n_int
                break

        # The rest is the prompt/style instruction
        user_prompt = _re.sub(r'\d{3,}', '', user_input).strip()
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

    system_prompt = f"""You are a professional scriptwriter. You write scripts in {language}.

USER'S STYLE INSTRUCTIONS: {user_prompt}

CRITICAL RULES:
- Write ENTIRELY in {language}
- Write EXACTLY {words_this_chunk} words
- Follow the user's style/prompt instructions precisely
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Do NOT repeat introductions or re-introduce the topic
- Just write continuous, seamless script text that flows naturally"""

    if not full_script:
        # First chunk — start the script
        prompt = f"""Write the beginning of a long script ({words_this_chunk} words) based on this video:

Title: {metadata.get('title', '')}
Description: {metadata.get('description', '')[:500]}
Channel: {metadata.get('channel', '')}
Tags: {', '.join(metadata.get('tags', [])[:10])}

Related Sources:
{source_texts}

Start the script directly. No title, no labels. Just begin naturally in {language}.
Write exactly {words_this_chunk} words."""
    else:
        # Continuation — pick up from where we left off
        last_part = full_script[-1500:]
        is_final = (words_remaining <= CHUNK_SIZE)

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

The script so far ends with:
\"\"\"
{last_part}
\"\"\"

Continue directly from where it left off. No labels, no headers, no re-introductions. Seamless continuation."""

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

    # Save full script
    output_path = str(get_session_dir(session_id) / "script.txt")
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
        {"type": "file_ready", "filename": "script.txt", "drive_url": drive_result["url"]},
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
            elif ext in ["mp3", "wav", "aac", "flac", "ogg", "m4a"] and "audio_path" not in data:
                set_data(session_id, "audio_path", f["path"])

        data = get_data(session_id)
        if "video_path" in data and "audio_path" in data:
            set_state(session_id, State.WF2_PROCESSING)

            from execution.ffmpeg_combine import combine_video_audio
            output_path = combine_video_audio(data["video_path"], data["audio_path"])
            set_data(session_id, "output_path", output_path)

            set_state(session_id, State.WF2_UPLOADING)
            from execution.google_drive_upload import upload_to_drive
            drive_result = upload_to_drive(output_path)

            set_state(session_id, State.WF2_COMPLETE)
            return [
                {"type": "status", "text": "We are combining your files, please wait a moment..."},
                {"type": "file_ready", "filename": "combined_video.mp4", "drive_url": drive_result["url"]},
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
        import re as _re
        numbers = _re.findall(r'\d+', text)
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

    system_prompt = f"""You are a professional scriptwriter. You write scripts in {language}.

USER'S STYLE INSTRUCTIONS: {user_prompt}

CRITICAL RULES:
- Write ENTIRELY in {language}
- Write EXACTLY {words_this_chunk} words
- Base the script ACCURATELY on the video content analysis provided
- Follow the user's style/prompt instructions precisely
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Do NOT repeat introductions or re-introduce the topic
- Just write continuous, seamless script text that flows naturally"""

    if not full_script:
        prompt = f"""Write the beginning of a long script ({words_this_chunk} words) based on this video:

Video Content Analysis:
{content_analysis}

Start the script directly. No title, no labels. Just begin naturally in {language}.
Write exactly {words_this_chunk} words."""
    else:
        last_part = full_script[-1500:]
        is_final = (words_remaining <= CHUNK_SIZE)

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

Video Content Analysis:
{content_analysis}

The script so far ends with:
\"\"\"
{last_part}
\"\"\"

Continue directly from where it left off. No labels, no headers, no re-introductions. Seamless continuation."""

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

    output_path = str(get_session_dir(session_id) / "video_script.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_script.strip())
    set_data(session_id, "script_path", output_path)

    set_state(session_id, State.WF3_UPLOADING)
    drive_result = upload_to_drive(output_path)
    set_data(session_id, "drive_url", drive_result["url"])

    set_state(session_id, State.WF3_COMPLETE)
    return [
        {"type": "message", "text": f"Script complete! Total words: {words_generated}"},
        {"type": "file_ready", "filename": "video_script.txt", "drive_url": drive_result["url"]},
        {"type": "prompt", "text": "Do you want to process another video?", "options": ["yes", "no"]},
    ]


# ─── Workflow 4: Script Changer + Image Generation ───

async def _handle_wf4(session_id: str, state: State, text: str, files: list) -> list[dict]:
    if state == State.WF4_AWAITING_SCRIPT:
        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in ["txt", "docx", "doc", "md"]:
                set_data(session_id, "script_path", f["path"])
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
        import re as _re
        numbers = _re.findall(r'\d+', text)
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
        set_state(session_id, State.WF4_ASK_CHARACTER)
        return [{"type": "message", "text": "Now describe your **character design**.\n\nInclude details like:\n- Age\n- Clothes\n- Facial features\n- Height / body type\n- Hair style & color\n- Any distinctive traits\n\n(e.g. \"A 25-year-old Burmese woman, wearing a traditional pink htamein and white blouse, long black hair, warm brown skin, gentle smile\")"}]

    elif state == State.WF4_ASK_CHARACTER:
        set_data(session_id, "img_character", text.strip())
        set_state(session_id, State.WF4_ASK_BACKGROUND)
        return [{"type": "message", "text": "Now describe your **background / setting**.\n\n(e.g. \"A traditional Burmese village with golden pagodas, teak houses, tropical palm trees, and a river in the distance\" or \"Inside a bustling zoo\", \"Modern city street\", etc.)"}]

    elif state == State.WF4_ASK_BACKGROUND:
        set_data(session_id, "img_background", text.strip())
        set_state(session_id, State.WF4_ASK_CONSISTENCY)
        return [{"type": "prompt", "text": "Do you want all images to have **consistent characters** across all scenes?\n\n- **yes** = same character looks identical in every scene\n- **no** = characters can vary per scene", "options": ["yes", "no"]}]

    elif state == State.WF4_ASK_CONSISTENCY:
        consistency = text.strip().lower() in ["yes", "y", "1", "true"]
        set_data(session_id, "img_consistency", consistency)
        set_state(session_id, State.WF4_GENERATING_PROMPTS)

        # Generate the two prompt files
        from execution.scene_splitter import split_into_scenes
        from execution.video_prompt_gen import generate_video_prompts
        from execution.file_handler import get_session_dir
        from execution.google_drive_upload import upload_to_drive

        data = get_data(session_id)
        session_dir = get_session_dir(session_id)

        # Split modified script into scenes
        scenes_path = str(session_dir / "scenes.json")
        scenes = split_into_scenes(data["modified_script_path"], output_path=scenes_path)
        set_data(session_id, "scenes", scenes)

        # Generate I2V and T2V prompts
        result = generate_video_prompts(
            scenes=scenes,
            style=data.get("img_style", ""),
            character=data.get("img_character", ""),
            background=data.get("img_background", ""),
            consistency=data.get("img_consistency", True),
            output_dir=str(session_dir / "video_prompts"),
        )

        # Upload both files to Drive
        i2v_drive = upload_to_drive(result["i2v_path"])
        t2v_drive = upload_to_drive(result["t2v_path"])

        set_state(session_id, State.WF4_COMPLETE)
        total_i2v = result.get("i2v_total_variations", result.get("i2v_scene_count", len(scenes)))
        total_t2v = result.get("t2v_total_variations", result.get("t2v_scene_count", len(scenes)))
        return [
            {"type": "message", "text": (
                f"Generated prompts for {len(scenes)} scenes "
                f"({total_i2v} I2V variations, {total_t2v} T2V variations)!\n\n"
                f"**Style:** {data.get('img_style', '')}\n"
                f"**Character:** {data.get('img_character', '')}\n"
                f"**Background:** {data.get('img_background', '')}\n"
                f"**Consistency:** {'Yes' if consistency else 'No'}"
            )},
            {"type": "file_ready", "filename": "image_to_video_prompts.txt", "drive_url": i2v_drive["url"]},
            {"type": "file_ready", "filename": "text_to_video_prompts.txt", "drive_url": t2v_drive["url"]},
            {"type": "message", "text": "Both prompt files are ready! Each paragraph has 9 prompt variations.\n- **image_to_video_prompts.txt** — use with Runway Gen-3, Kling, Luma, Pika\n- **text_to_video_prompts.txt** — use with Sora, Veo, Kling, Runway"},
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

    system_prompt = f"""You are an expert script editor. You write scripts in {language}.

MODIFICATION INSTRUCTIONS: {instructions}

CRITICAL RULES:
- Write ENTIRELY in {language}
- Write EXACTLY {words_this_chunk} words
- Apply the modification instructions to transform the original script
- Use natural, fluent {language} — not machine-translated text
- Do NOT include any labels like "Part 1" or "Section 1" or headers
- Do NOT repeat introductions or re-introduce the topic
- Just write continuous, seamless script text that flows naturally"""

    if not full_script:
        prompt = f"""Modify and rewrite the beginning of this script ({words_this_chunk} words) based on the instructions.

Original Script:
{original_text[:3000]}

Start the modified script directly. No title, no labels. Just begin naturally in {language}.
Write exactly {words_this_chunk} words."""
    else:
        last_part = full_script[-1500:]
        # Calculate how much of the original we've roughly covered
        orig_words = len(original_text.split())
        coverage_ratio = words_generated / target_words if target_words > 0 else 0
        orig_start = int(coverage_ratio * orig_words)
        orig_section = " ".join(original_text.split()[max(0, orig_start - 200):orig_start + 1500])
        is_final = (words_remaining <= CHUNK_SIZE)

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

Relevant section from original script:
{orig_section[:2000]}

The modified script so far ends with:
\"\"\"
{last_part}
\"\"\"

Continue directly from where it left off. No labels, no headers, no re-introductions. Seamless continuation."""

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

    output_path = str(get_session_dir(session_id) / "modified_script.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_script.strip())
    set_data(session_id, "modified_script_path", output_path)

    set_state(session_id, State.WF4_UPLOADING)
    drive_result = upload_to_drive(output_path)
    set_data(session_id, "drive_url", drive_result["url"])

    set_state(session_id, State.WF4_ASK_STYLE)
    return [
        {"type": "message", "text": f"Script modified! Total words: {words_generated}"},
        {"type": "file_ready", "filename": "modified_script.txt", "drive_url": drive_result["url"]},
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

        # Accept any newly uploaded files
        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in audio_exts and not audio_path:
                audio_path = f["path"]
            elif ext in image_exts:
                image_paths.append(f["path"])

        set_data(session_id, "audio_path", audio_path)
        set_data(session_id, "image_paths", image_paths)

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

        output_path = str(get_session_dir(session_id) / "slideshow.mp4")
        result = create_slideshow(audio_path, image_paths, output_path)

        set_state(session_id, State.WF5_UPLOADING)
        drive_result = upload_to_drive(output_path)

        set_state(session_id, State.WF5_COMPLETE)
        return [
            status_msg,
            {"type": "message", "text": f"Slideshow created! Duration: {result['duration']:.1f}s, {result['image_count']} images at {result['per_image_duration']:.1f}s each."},
            {"type": "file_ready", "filename": "slideshow.mp4", "drive_url": drive_result["url"]},
            {"type": "prompt", "text": "Do you want to create another slideshow?", "options": ["yes", "no"]},
        ]

    elif state == State.WF5_COMPLETE:
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
