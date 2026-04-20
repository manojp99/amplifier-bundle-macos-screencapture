# amplifier-bundle-macos-screencapture

An [Amplifier](https://github.com/microsoft/amplifier) bundle that gives AI agents the ability to list running applications, enumerate windows, and capture screenshots of specific app windows on macOS.

Inspired by John Maeda's [macOS Screen Capture Via CLI](https://maeda.pm/2024/11/16/macos-screen-capture-via-cli/) article.

## Prerequisites

- **macOS** (uses `screencapture` CLI and CoreGraphics APIs)
- **Xcode Command Line Tools** (`xcode-select --install`) — needed for inline Swift
- **Screen Recording permission** — grant to Terminal (or the Amplifier host app) in:
  **System Settings > Privacy & Security > Screen Recording**

Without Screen Recording permission:
- `list_apps` and `full_screen` still work
- `list_windows` returns window IDs and app names but **window titles will be empty**
- `capture_window` will fail with a clear error message

## Tools Provided

| Tool | Description |
|------|-------------|
| `macos_screencapture_list_apps` | List all visible running macOS applications |
| `macos_screencapture_list_windows` | List windows with CoreGraphics IDs for a given app |
| `macos_screencapture_capture_window` | Screenshot a specific window by its window ID |
| `macos_screencapture_full_screen` | Screenshot the full display |

## Agent

The bundle includes a `screen-observer` agent (`model_role: [vision, general]`) that can be delegated to for capture + visual analysis workflows:

```
delegate(agent="macos-screencapture:screen-observer",
         instruction="Screenshot the Safari window and describe what you see")
```

## Usage

### Add to an existing bundle

```yaml
includes:
  - bundle: git+https://github.com/manojp99/amplifier-bundle-macos-screencapture@main
```

### Compose as a behavior

```yaml
includes:
  - bundle: git+https://github.com/manojp99/amplifier-bundle-macos-screencapture@main
    behaviors:
      - macos-screencapture
```

### Typical agent workflow

1. **List apps** — discover what's running
2. **List windows** — find the window ID for a target app
3. **Capture** — screenshot that window by ID
4. **Analyze** — pass the screenshot to a vision-capable model

```
list_apps → ["Safari", "Xcode", "Terminal", ...]
list_windows(app_name="Safari") → [{window_id: 1234, ...}]
capture_window(window_id=1234) → {screenshot_path: "/tmp/amplifier_screen_xyz.png"}
```

## How It Works

- **App listing** uses `osascript` (AppleScript) to query System Events — works without Screen Recording permission.
- **Window listing** uses an inline Swift script calling `CGWindowListCopyWindowInfo` from CoreGraphics — zero pip dependencies. The system Python on modern macOS no longer bundles PyObjC, so Swift is the reliable zero-dependency path.
- **Window capture** uses the macOS `screencapture -l <windowID>` CLI — captures even if the window is behind other windows.
- **Full screen** uses `screencapture -x` — suppresses the shutter sound.

## Development

```bash
# Run tests (requires Amplifier's Python venv for amplifier_core)
cd modules/tool-macos-screencapture
uv pip install --python ~/.local/share/uv/tools/amplifier/bin/python -e .
~/.local/share/uv/tools/amplifier/bin/python -m pytest tests/ -v
```

## License

MIT
