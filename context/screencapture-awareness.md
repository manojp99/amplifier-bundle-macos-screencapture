# macOS Screen Capture Capability

This session has access to macOS screen capture tools via the `screen-observer` agent.

## What's Available

The `screen-observer` agent (`macos-screencapture:screen-observer`) can:
- List all visible running applications
- List windows with CoreGraphics IDs for any running app
- Capture a screenshot of a specific window by window ID
- Capture the full screen

## When to Delegate

Delegate to `macos-screencapture:screen-observer` when:
- The user wants to see or analyze the current screen state
- The user asks what apps or windows are open
- Visual verification of UI is needed
- A screenshot capture is requested

## Prerequisite

Screen Recording permission must be granted to the host process (Terminal or the
Amplifier app) in System Settings > Privacy & Security > Screen Recording.

## Direct Tool Use

The four tools are also available directly in the root session:

| Tool | Purpose |
|------|---------|
| `macos_screencapture_list_apps` | List visible running applications |
| `macos_screencapture_list_windows` | List windows with IDs for a given app |
| `macos_screencapture_capture_window` | Screenshot a window by its ID |
| `macos_screencapture_full_screen` | Screenshot the entire display |
