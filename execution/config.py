"""
Shared configuration for all execution scripts.
Loads .env and defines paths, API keys, and constants.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
EXECUTION_DIR = PROJECT_ROOT / "execution"
DIRECTIVES_DIR = PROJECT_ROOT / "directives"
STATIC_DIR = PROJECT_ROOT / "static"

# Ensure .tmp exists
TMP_DIR.mkdir(exist_ok=True)

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

# Google Drive
GDRIVE_OUTPUT_FOLDER_ID = os.getenv("GDRIVE_OUTPUT_FOLDER_ID", "")

# ComfyUI
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")

# App
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Gemini model
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
