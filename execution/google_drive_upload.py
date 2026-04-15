"""
Upload a file to Google Drive.
Usage: python -m execution.google_drive_upload --file_path <path> [--folder_id <id>] [--mime_type <type>]
Returns the Drive file URL.
"""
import argparse
import mimetypes
import socket
import ssl
import time
from pathlib import Path
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from execution.google_drive_auth import get_drive_service
from execution.config import GDRIVE_OUTPUT_FOLDER_ID

# Make the default socket timeout more generous so the initial TCP/TLS
# handshake to Google has time to complete on flaky connections.
socket.setdefaulttimeout(120)

# Resumable upload chunk size (5 MB). Smaller chunks = finer-grained retries.
UPLOAD_CHUNK_SIZE = 5 * 1024 * 1024

# Network-level retry config
MAX_UPLOAD_RETRIES = 4
INITIAL_BACKOFF = 3  # seconds

# Exceptions we consider transient and worth retrying
_TRANSIENT_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    socket.timeout,
    socket.gaierror,
    ssl.SSLError,
    OSError,  # catches WinError 10060 etc.
)


def is_drive_available() -> bool:
    """Check if Google Drive credentials are configured."""
    from execution.google_drive_auth import CREDENTIALS_PATH, TOKEN_PATH
    return CREDENTIALS_PATH.exists() or TOKEN_PATH.exists()


def _is_transient_http_error(err: HttpError) -> bool:
    """HttpError 5xx and 429 are considered transient."""
    try:
        status = err.resp.status
    except Exception:
        return False
    return status in (408, 429, 500, 502, 503, 504)


def _chunked_resumable_upload(service, file_metadata, media):
    """
    Drive the resumable upload loop manually so we can retry each chunk on
    transient network errors (connection resets, timeouts, 5xx from Google).
    """
    request = service.files().create(
        body=file_metadata, media_body=media, fields="id, name, webViewLink"
    )
    response = None
    last_error = None

    while response is None:
        for attempt in range(MAX_UPLOAD_RETRIES):
            try:
                status, response = request.next_chunk()
                last_error = None
                break  # chunk OK, move on
            except _TRANSIENT_EXCEPTIONS as e:
                last_error = e
                wait = INITIAL_BACKOFF * (2 ** attempt)
                print(f"[Drive] Network error '{type(e).__name__}: {e}'. "
                      f"Retry {attempt+1}/{MAX_UPLOAD_RETRIES} in {wait}s...")
                time.sleep(wait)
            except HttpError as e:
                if _is_transient_http_error(e):
                    last_error = e
                    wait = INITIAL_BACKOFF * (2 ** attempt)
                    print(f"[Drive] Transient HTTP error {e.resp.status}. "
                          f"Retry {attempt+1}/{MAX_UPLOAD_RETRIES} in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        else:
            # Ran out of retries for this chunk
            raise last_error or RuntimeError("Upload failed after retries")

    return response


def upload_to_drive(file_path: str, folder_id: str = None, mime_type: str = None) -> dict:
    """
    Upload a file to Google Drive with retry on transient network errors.
    Returns dict with 'id', 'name', and 'url' of the uploaded file.
    If credentials are not configured, returns a placeholder result.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not is_drive_available():
        return {
            "id": "local",
            "name": file_path.name,
            "url": f"file:///{file_path}",
            "local_only": True,
        }

    folder_id = folder_id or GDRIVE_OUTPUT_FOLDER_ID
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

    file_metadata = {"name": file_path.name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    # Retry the whole upload (including service-build) on connect-level errors.
    last_error = None
    for attempt in range(MAX_UPLOAD_RETRIES):
        try:
            service = get_drive_service()
            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=True,
                chunksize=UPLOAD_CHUNK_SIZE,
            )
            file = _chunked_resumable_upload(service, file_metadata, media)
            return {
                "id": file["id"],
                "name": file["name"],
                "url": file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}/view"),
            }
        except _TRANSIENT_EXCEPTIONS as e:
            last_error = e
            wait = INITIAL_BACKOFF * (2 ** attempt)
            print(f"[Drive] Upload attempt {attempt+1}/{MAX_UPLOAD_RETRIES} "
                  f"failed: {type(e).__name__}: {e}. Retrying in {wait}s...")
            time.sleep(wait)
        except HttpError as e:
            if _is_transient_http_error(e):
                last_error = e
                wait = INITIAL_BACKOFF * (2 ** attempt)
                print(f"[Drive] Transient HTTP {e.resp.status} on attempt "
                      f"{attempt+1}/{MAX_UPLOAD_RETRIES}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise

    # All retries exhausted — surface a clear error but keep the local file.
    raise RuntimeError(
        f"Google Drive upload failed after {MAX_UPLOAD_RETRIES} attempts. "
        f"Last error: {type(last_error).__name__}: {last_error}. "
        f"The generated file is still available locally at: {file_path}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload file to Google Drive")
    parser.add_argument("--file_path", required=True)
    parser.add_argument("--folder_id", default=None)
    parser.add_argument("--mime_type", default=None)
    args = parser.parse_args()

    result = upload_to_drive(args.file_path, args.folder_id, args.mime_type)
    print(f"Uploaded: {result['name']}")
    print(f"URL: {result['url']}")
