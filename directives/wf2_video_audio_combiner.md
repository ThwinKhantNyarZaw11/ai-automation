# Workflow 2: Video + Audio Combiner

## Goal
Combine a user-provided video file and audio file into a single synchronized video.

## States
1. `WF2_AWAITING_FILES` — waiting for video and audio files
2. `WF2_PROCESSING` — combining with FFmpeg
3. `WF2_UPLOADING` — uploading to Google Drive
4. `WF2_COMPLETE` — done

## Steps

### Step 1: Receive Files
- Accept video: mp4, mov, avi, mkv, webm
- Accept audio: mp3, wav, aac, flac, ogg, m4a
- Can be uploaded in any order
- Track which files are received, ask for missing ones

### Step 2: Combine
- Script: `execution/ffmpeg_combine.py`
- Flags: -c:v copy -c:a aac -shortest
- Output: combined MP4 in .tmp/

### Step 3: Upload
- Script: `execution/google_drive_upload.py`
- Upload combined video to Drive

### Step 4: Notify + End
- Show Drive link
- Ask to process another

## Edge Cases
- FFmpeg not installed → show install instructions
- Incompatible formats → try re-encoding both streams
- Large files → may take time, show progress status
