"""
Handle file uploads from the chat interface.
Saves files to .tmp/{session_id}/ and manages cleanup.
"""
import shutil
import uuid
from pathlib import Path
from execution.config import TMP_DIR


def get_session_dir(session_id: str) -> Path:
    """Get or create session-specific temp directory."""
    session_dir = TMP_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


async def save_upload(session_id: str, filename: str, file_bytes: bytes) -> str:
    """
    Save an uploaded file to the session's temp directory.
    Returns the full path to the saved file.
    """
    session_dir = get_session_dir(session_id)
    # Add unique prefix to avoid collisions
    safe_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    file_path = session_dir / safe_name
    file_path.write_bytes(file_bytes)
    return str(file_path)


def cleanup_session(session_id: str):
    """Remove all temp files for a session."""
    session_dir = TMP_DIR / session_id
    if session_dir.exists():
        try:
            shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            pass
