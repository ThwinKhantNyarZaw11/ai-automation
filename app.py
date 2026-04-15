"""
FastAPI application entry point.
Serves the chat UI, handles WebSocket connections and file uploads.
"""
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from execution.config import APP_HOST, APP_PORT, STATIC_DIR
from execution.file_handler import save_upload
from execution.workflow_handlers import handle_message, get_workflow_welcome

app = FastAPI(title="AI Automation System")

# Mount static files
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Track uploaded files per session for WebSocket reference
_pending_files: dict[str, list[dict]] = {}


@app.get("/")
async def root():
    """Serve the chat interface."""
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/upload/{session_id}")
async def upload_file(session_id: str, file: UploadFile = File(...)):
    """Handle file upload. Save to .tmp and return file info."""
    file_bytes = await file.read()
    saved_path = await save_upload(session_id, file.filename, file_bytes)

    if session_id not in _pending_files:
        _pending_files[session_id] = []

    file_info = {"filename": file.filename, "path": saved_path}
    _pending_files[session_id].append(file_info)

    return JSONResponse({"status": "ok", "filename": file.filename, "path": saved_path})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, workflow: str = Query(default=None)):
    await ws.accept()
    session_id = str(uuid.uuid4())

    # Send session info
    await ws.send_json({"type": "session", "session_id": session_id})

    # Auto-start the workflow if specified
    if workflow and workflow in ["1", "2", "3", "4", "5", "6"]:
        welcome_msgs = get_workflow_welcome(session_id, workflow)
        for msg in welcome_msgs:
            await ws.send_json(msg)
    else:
        await ws.send_json({"type": "message", "text": "Send a message to get started."})

    try:
        while True:
            data = await ws.receive_json()

            if data.get("type") == "message":
                text = data.get("text", "")
                # Grab any pending uploaded files
                files = _pending_files.pop(session_id, [])
                responses = await handle_message(session_id, text, files)

                for resp in responses:
                    await ws.send_json(resp)

            elif data.get("type") == "upload_complete":
                await ws.send_json({"type": "status", "text": f"File received: {data.get('filename', '')}"})

    except WebSocketDisconnect:
        _pending_files.pop(session_id, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=int(APP_PORT))
