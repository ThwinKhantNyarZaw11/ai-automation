"""
Google Drive OAuth authentication.
Handles credentials.json -> token.json flow.
Exports get_drive_service() for use by other scripts.
"""
import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from execution.config import PROJECT_ROOT

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"


def get_drive_service():
    """Authenticate and return a Google Drive API service object."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


if __name__ == "__main__":
    service = get_drive_service()
    print("Google Drive authenticated successfully.")
    about = service.about().get(fields="user").execute()
    print(f"Logged in as: {about['user']['displayName']}")
