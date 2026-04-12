# Workflow 4: Script Changer + Image Generation

## Goal
Modify an existing script in Burmese, optionally generate consistent images for each scene using ComfyUI.

## States
1. `WF4_AWAITING_SCRIPT` — waiting for script file
2. `WF4_AWAITING_INSTRUCTIONS` — waiting for modification instructions
3. `WF4_MODIFYING` — modifying script via Gemini
4. `WF4_ASK_IMAGES` — asking if user wants image generation
5. `WF4_GENERATING_IMAGES` — splitting scenes + generating ComfyUI prompts
6. `WF4_ASK_OUTPUT_TYPE` — asking output preference
7. `WF4_SAVING` — saving results
8. `WF4_COMPLETE` — done

## Steps

### Step 1: Receive Script
- Accept: txt, docx, md files

### Step 2: Get Instructions
- Free-form text describing desired changes

### Step 3: Modify Script
- Script: `execution/script_modifier.py`
- Uses Gemini with Burmese-specific system prompt
- Save modified script to Drive immediately

### Step 4: Ask About Images
- "Do you want to generate images with consistency?"

### Step 5: Scene Breakdown (if yes)
- Script: `execution/scene_splitter.py`
- Split into scenes (3 sentences per scene)

### Step 6: Generate Prompts
- Script: `execution/comfyui_prompt_gen.py`
- Create ComfyUI-compatible JSON prompts per scene
- Uses Gemini to convert Burmese text to English image descriptions

### Step 7: Output Choice
- Option 1: Save photos + Grok AI animation prompts to Drive
- Option 2: Generate slide animation (requires running ComfyUI)

### Step 8: Save + Notify

## Edge Cases
- ComfyUI not running → save prompts only, user can generate later
- Script too long → split into batches for Gemini
- Image generation fails → save successful images, report failures
