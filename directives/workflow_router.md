# Workflow Router

## Goal
Route incoming user messages to the correct workflow based on input type and user selection.

## Trigger
Every incoming message when session state is IDLE.

## Routing Logic

| User Input | Workflow |
|---|---|
| "1", "source finder", "source" | WF1: Source Finder + Script Generator |
| "2", "video audio", "combiner", "combine" | WF2: Video + Audio Combiner |
| "3", "video changer", "video" | WF3: Video Changer |
| "4", "script changer", "script" | WF4: Script Changer + Image Generation |
| "restart", "reset", "start" | Reset session to IDLE |

## State Machine
- All workflows start from IDLE
- Each workflow has its own state prefix (WF1_, WF2_, WF3_, WF4_)
- "restart" always returns to IDLE from any state
- Session cleanup happens on workflow completion

## Scripts Used
- `execution/state_manager.py` — state tracking
- `execution/workflow_handlers.py` — routing logic and step handlers

## Edge Cases
- Unknown input at IDLE → show welcome message with options
- Error in any workflow → show error + offer restart
- WebSocket disconnect → clean up session files
