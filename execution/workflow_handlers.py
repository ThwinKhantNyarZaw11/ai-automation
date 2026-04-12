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

Type the number or name of the workflow you want to use."""


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

    elif text_lower in ["restart", "reset", "start"]:
        reset_session(session_id)
        return [{"type": "message", "text": WELCOME_MESSAGE}]

    else:
        return [{"type": "message", "text": WELCOME_MESSAGE}]


# ─── Workflow 1: Source Finder + Script Generator ───

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
            {"type": "message", "text": f"**Video:** {metadata['title']}\n**Channel:** {metadata.get('channel', 'N/A')}\n**Duration:** {metadata.get('duration', 0)}s"},
            {"type": "sources", "data": sources.get("sources", [])},
            {"type": "images", "urls": [img["image_url"] for img in sources.get("images", [])[:5]]},
            {"type": "prompt", "text": "Do you want me to generate a Burmese script based on this video?", "options": ["yes", "no"]},
        ]
        return responses

    elif state == State.WF1_SHOWING_RESULTS:
        if text.strip().lower() in ["yes", "y", "1"]:
            set_state(session_id, State.WF1_GENERATING_SCRIPT)

            from execution.burmese_script_gen import generate_burmese_script
            from execution.file_handler import get_session_dir

            metadata = get_data(session_id).get("metadata", {})
            sources = get_data(session_id).get("sources", {})

            source_data = {**metadata, "sources": sources.get("sources", [])}
            output_path = str(get_session_dir(session_id) / "burmese_script.txt")
            script = generate_burmese_script(source_data, output_path)
            set_data(session_id, "script_path", output_path)

            # Upload to Drive
            set_state(session_id, State.WF1_UPLOADING)
            from execution.google_drive_upload import upload_to_drive

            drive_result = upload_to_drive(output_path)
            set_data(session_id, "drive_url", drive_result["url"])

            set_state(session_id, State.WF1_COMPLETE)
            return [
                {"type": "message", "text": script[:500] + "..." if len(script) > 500 else script},
                {"type": "file_ready", "filename": "burmese_script.txt", "drive_url": drive_result["url"]},
                {"type": "prompt", "text": "Do you want to process another video?", "options": ["yes", "no"]},
            ]
        else:
            set_state(session_id, State.WF1_COMPLETE)
            return [{"type": "prompt", "text": "Do you want to process another video?", "options": ["yes", "no"]}]

    elif state == State.WF1_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


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
                {"type": "file_ready", "filename": "combined_video.mp4", "drive_url": drive_result["url"]},
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
                return [{"type": "message", "text": "Video received. What transformation do you want? Describe your desired changes."}]
        return [{"type": "message", "text": "Please send a video file."}]

    elif state == State.WF3_AWAITING_PROMPT:
        set_data(session_id, "user_prompt", text)
        set_state(session_id, State.WF3_PROCESSING)

        from execution.video_analyze import analyze_video
        from execution.video_script_gen import generate_video_script
        from execution.file_handler import get_session_dir

        session_dir = str(get_session_dir(session_id))
        analysis = analyze_video(get_data(session_id)["video_path"], session_dir)

        output_path = str(get_session_dir(session_id) / "video_script.txt")
        script = generate_video_script(analysis, text, output_path)
        set_data(session_id, "script_path", output_path)

        set_state(session_id, State.WF3_UPLOADING)
        from execution.google_drive_upload import upload_to_drive
        drive_result = upload_to_drive(output_path)

        set_state(session_id, State.WF3_COMPLETE)
        return [
            {"type": "message", "text": script[:500] + "..." if len(script) > 500 else script},
            {"type": "file_ready", "filename": "video_script.txt", "drive_url": drive_result["url"]},
            {"type": "prompt", "text": "Do you want to process another video?", "options": ["yes", "no"]},
        ]

    elif state == State.WF3_COMPLETE:
        return _handle_restart(session_id, text)

    return [{"type": "message", "text": "Something went wrong. Type 'restart' to start over."}]


# ─── Workflow 4: Script Changer + Image Generation ───

async def _handle_wf4(session_id: str, state: State, text: str, files: list) -> list[dict]:
    if state == State.WF4_AWAITING_SCRIPT:
        for f in files:
            ext = f["filename"].rsplit(".", 1)[-1].lower() if "." in f["filename"] else ""
            if ext in ["txt", "docx", "doc", "md"]:
                set_data(session_id, "script_path", f["path"])
                set_state(session_id, State.WF4_AWAITING_INSTRUCTIONS)
                return [{"type": "message", "text": "Script received. What changes do you want to make?"}]
        return [{"type": "message", "text": "Please send a script file (.txt, .docx, .md)."}]

    elif state == State.WF4_AWAITING_INSTRUCTIONS:
        set_data(session_id, "instructions", text)
        set_state(session_id, State.WF4_MODIFYING)

        from execution.script_modifier import modify_script
        from execution.file_handler import get_session_dir

        output_path = str(get_session_dir(session_id) / "modified_script.txt")
        modified = modify_script(get_data(session_id)["script_path"], text, output_path)
        set_data(session_id, "modified_script_path", output_path)

        # Save to drive
        from execution.google_drive_upload import upload_to_drive
        drive_result = upload_to_drive(output_path)

        set_state(session_id, State.WF4_ASK_IMAGES)
        return [
            {"type": "message", "text": modified[:500] + "..." if len(modified) > 500 else modified},
            {"type": "file_ready", "filename": "modified_script.txt", "drive_url": drive_result["url"]},
            {"type": "prompt", "text": "Do you want to generate images with consistency?", "options": ["yes", "no"]},
        ]

    elif state == State.WF4_ASK_IMAGES:
        if text.strip().lower() in ["yes", "y", "1"]:
            set_state(session_id, State.WF4_GENERATING_IMAGES)

            from execution.scene_splitter import split_into_scenes
            from execution.comfyui_prompt_gen import generate_prompts
            from execution.file_handler import get_session_dir

            session_dir = str(get_session_dir(session_id))
            scenes_path = str(get_session_dir(session_id) / "scenes.json")
            scenes = split_into_scenes(get_data(session_id)["modified_script_path"], output_path=scenes_path)
            set_data(session_id, "scenes", scenes)

            prompts = generate_prompts(scenes, str(get_session_dir(session_id) / "comfyui_prompts"))
            set_data(session_id, "prompts", prompts)

            set_state(session_id, State.WF4_ASK_OUTPUT_TYPE)
            return [
                {"type": "message", "text": f"Generated {len(prompts)} scene prompts for image generation."},
                {"type": "prompt", "text": "Choose an option:\n1. Save photos to Drive with animation prompts for Grok AI\n2. Make slide animation from generated images", "options": ["1", "2"]},
            ]
        else:
            set_state(session_id, State.WF4_COMPLETE)
            return [{"type": "prompt", "text": "Do you want to process another script?", "options": ["yes", "no"]}]

    elif state == State.WF4_ASK_OUTPUT_TYPE:
        set_state(session_id, State.WF4_SAVING)

        if text.strip() in ["1", "drive", "save"]:
            # Save prompts to Drive for user to use with Grok AI
            import json
            from execution.file_handler import get_session_dir
            from execution.google_drive_upload import upload_to_drive

            prompts = get_data(session_id).get("prompts", [])
            prompts_path = str(get_session_dir(session_id) / "animation_prompts.json")
            with open(prompts_path, "w", encoding="utf-8") as f:
                json.dump(prompts, f, indent=2, ensure_ascii=False)

            drive_result = upload_to_drive(prompts_path)

            set_state(session_id, State.WF4_COMPLETE)
            return [
                {"type": "file_ready", "filename": "animation_prompts.json", "drive_url": drive_result["url"]},
                {"type": "message", "text": "Photos and animation prompts saved to Google Drive."},
                {"type": "prompt", "text": "Do you want to process another script?", "options": ["yes", "no"]},
            ]
        else:
            # Generate images with ComfyUI and create slide animation
            set_state(session_id, State.WF4_COMPLETE)
            return [
                {"type": "message", "text": "Slide animation generation requires a running ComfyUI server. Prompts have been prepared — use them with your ComfyUI setup."},
                {"type": "prompt", "text": "Do you want to process another script?", "options": ["yes", "no"]},
            ]

    elif state == State.WF4_COMPLETE:
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
