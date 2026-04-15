# Workflow 3: Video Changer

## Goal
Analyze a video and generate a Burmese script based on the user's transformation prompt.

## States
1. `WF3_AWAITING_VIDEO` — waiting for video file
2. `WF3_AWAITING_PROMPT` — waiting for transformation instructions
3. `WF3_PROCESSING` — analyzing video + generating script
4. `WF3_UPLOADING` — uploading to Drive
5. `WF3_COMPLETE` — done

## Steps

### Step 1: Receive Video
- Accept: mp4, mov, avi, mkv, webm

### Step 2: Get Prompt
- Ask user what transformation/script they want
- Free-form text input

### Step 3: Analyze + Generate
- Script: `execution/video_analyze.py` — extract metadata + keyframes
- Script: `execution/video_script_gen.py` — generate Burmese script via Gemini
- Uses Gemini for Burmese language output

### Step 4: Upload
- Script: `execution/google_drive_upload.py`

### Step 5: Notify + End

## Edge Cases
- Video too large for analysis → extract fewer keyframes
- Gemini context limit → summarize video analysis first
