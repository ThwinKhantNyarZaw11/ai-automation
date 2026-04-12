# Google Drive Upload (Shared)

## Goal
Upload deliverable files to a specific Google Drive folder.

## Prerequisites
- `credentials.json` in project root (from Google Cloud Console)
- `GDRIVE_OUTPUT_FOLDER_ID` set in `.env`
- First run will open browser for OAuth consent

## Scripts
- `execution/google_drive_auth.py` — handles OAuth flow
- `execution/google_drive_upload.py` — uploads files

## Setup Steps
1. Go to Google Cloud Console
2. Create a project or select existing
3. Enable Google Drive API
4. Create OAuth 2.0 credentials (Desktop App)
5. Download credentials.json to project root
6. Run `python -m execution.google_drive_auth` to authorize
7. Set GDRIVE_OUTPUT_FOLDER_ID in .env (the Drive folder for outputs)

## Usage
```python
from execution.google_drive_upload import upload_to_drive
result = upload_to_drive("path/to/file.txt")
# result = {"id": "...", "name": "...", "url": "..."}
```

## Edge Cases
- Token expired → auto-refresh via refresh_token
- credentials.json missing → raise clear error with setup instructions
- Upload fails → retry once, then report error
