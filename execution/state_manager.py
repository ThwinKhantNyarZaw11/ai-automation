"""
Session state management for the chat interface.
Tracks per-session workflow state using an in-memory dict.
"""
from enum import Enum
from typing import Any


class State(str, Enum):
    IDLE = "IDLE"
    # Workflow 1: Source Finder
    WF1_AWAITING_LINK = "WF1_AWAITING_LINK"
    WF1_EXTRACTING = "WF1_EXTRACTING"
    WF1_SEARCHING_SOURCES = "WF1_SEARCHING_SOURCES"
    WF1_SHOWING_RESULTS = "WF1_SHOWING_RESULTS"
    WF1_GENERATING_SCRIPT = "WF1_GENERATING_SCRIPT"
    WF1_UPLOADING = "WF1_UPLOADING"
    WF1_COMPLETE = "WF1_COMPLETE"
    # Workflow 2: Video + Audio Combiner
    WF2_AWAITING_FILES = "WF2_AWAITING_FILES"
    WF2_PROCESSING = "WF2_PROCESSING"
    WF2_UPLOADING = "WF2_UPLOADING"
    WF2_COMPLETE = "WF2_COMPLETE"
    # Workflow 3: Video Changer
    WF3_AWAITING_VIDEO = "WF3_AWAITING_VIDEO"
    WF3_AWAITING_PROMPT = "WF3_AWAITING_PROMPT"
    WF3_PROCESSING = "WF3_PROCESSING"
    WF3_UPLOADING = "WF3_UPLOADING"
    WF3_COMPLETE = "WF3_COMPLETE"
    # Workflow 4: Script Changer
    WF4_AWAITING_SCRIPT = "WF4_AWAITING_SCRIPT"
    WF4_AWAITING_INSTRUCTIONS = "WF4_AWAITING_INSTRUCTIONS"
    WF4_MODIFYING = "WF4_MODIFYING"
    WF4_ASK_IMAGES = "WF4_ASK_IMAGES"
    WF4_GENERATING_IMAGES = "WF4_GENERATING_IMAGES"
    WF4_ASK_OUTPUT_TYPE = "WF4_ASK_OUTPUT_TYPE"
    WF4_SAVING = "WF4_SAVING"
    WF4_COMPLETE = "WF4_COMPLETE"


# In-memory session store
_sessions: dict[str, dict] = {}


def get_session(session_id: str) -> dict:
    """Get or create a session."""
    if session_id not in _sessions:
        _sessions[session_id] = {
            "session_id": session_id,
            "current_workflow": None,
            "state": State.IDLE,
            "data": {},
        }
    return _sessions[session_id]


def get_state(session_id: str) -> State:
    return get_session(session_id)["state"]


def set_state(session_id: str, state: State):
    get_session(session_id)["state"] = state


def set_workflow(session_id: str, workflow: str):
    get_session(session_id)["current_workflow"] = workflow


def get_data(session_id: str) -> dict:
    return get_session(session_id)["data"]


def set_data(session_id: str, key: str, value: Any):
    get_session(session_id)["data"][key] = value


def reset_session(session_id: str):
    """Reset a session to IDLE."""
    _sessions[session_id] = {
        "session_id": session_id,
        "current_workflow": None,
        "state": State.IDLE,
        "data": {},
    }
