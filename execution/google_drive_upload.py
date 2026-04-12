"""
Upload a file to Google Drive.
Usage: python -m execution.google_drive_upload --file_path <path> [--folder_id <id>] [--mime_type <type>]
Returns the Drive file URL.
"""
import argparse
import mimetypes
from pathlib import Path
from googleapiclient.http import MediaFileUpload

from execution.google_drive_auth import get_drive_service
from execution.config import GDRIVE_OUTPUT_FOLDER_ID


def upload_to_drive(file_path: str, folder_id: str = None, mime_type: str = None) -> dict:
    """
    Upload a file to Google Drive.
    Returns dict with 'id', 'name', and 'url' of the uploaded file.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    folder_id = folder_id or GDRIVE_OUTPUT_FOLDER_ID
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

    service = get_drive_service()

    file_metadata = {"name": file_path.name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id, name, webViewLink"
    ).execute()

    return {
        "id": file["id"],
        "name": file["name"],
        "url": file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}/view"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload file to Google Drive")
    parser.add_argument("--file_path", required=True)
    parser.add_argument("--folder_id", default=None)
    parser.add_argument("--mime_type", default=None)
    args = parser.parse_args()

    result = upload_to_drive(args.file_path, args.folder_id, args.mime_type)
    print(f"Uploaded: {result['name']}")
    print(f"URL: {result['url']}")
