# Workflow 1: Source Finder + Script Generator

## Goal
Given a YouTube video link, find the original source of the content, related images, and optionally generate a Burmese-language script.

## States
1. `WF1_AWAITING_LINK` — waiting for YouTube URL
2. `WF1_EXTRACTING` — extracting video metadata via yt-dlp
3. `WF1_SEARCHING_SOURCES` — searching web for original sources
4. `WF1_SHOWING_RESULTS` — displaying sources and images, asking about script
5. `WF1_GENERATING_SCRIPT` — generating Burmese script via Gemini
6. `WF1_UPLOADING` — uploading script to Google Drive
7. `WF1_COMPLETE` — done, ask to process another

## Steps

### Step 1: Receive YouTube Link
- Validate URL contains `youtube.com/watch` or `youtu.be/`
- If invalid, ask again

### Step 2: Extract Metadata
- Script: `execution/youtube_extract.py`
- Input: YouTube URL
- Output: JSON with title, description, channel, duration, tags

### Step 3: Search Sources
- Script: `execution/source_finder.py`
- Input: video title + channel name as search query
- Output: web results (sources) + image results
- Requires: SERPER_API_KEY in .env

### Step 4: Show Results
- Display video info, sources, and images to user
- Ask: "Do you want to generate a Burmese script?"

### Step 5: Generate Script (if yes)
- Script: `execution/burmese_script_gen.py`
- Input: metadata + sources
- Output: Burmese script text file
- Requires: GEMINI_API_KEY in .env

### Step 6: Upload to Drive
- Script: `execution/google_drive_upload.py`
- Input: script file path
- Output: Google Drive URL

### Step 7: Notify + End
- Show Drive link to user
- Ask to process another or end

## Edge Cases
- yt-dlp fails → show error, ask for different link
- Serper API rate limit → retry once after 2s, then show error
- Gemini fails → show error, offer to retry
