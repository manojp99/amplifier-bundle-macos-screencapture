"""Amplifier tool module for macOS screen capture.

Registers four tools:
  macos_screencapture_list_apps      — List visible running applications
  macos_screencapture_list_windows   — List windows (with CoreGraphics IDs) for an app
  macos_screencapture_capture_window — Screenshot a specific window by ID
  macos_screencapture_full_screen    — Screenshot the full display

Prerequisites:
  - macOS with Xcode CLT (uses Swift for CoreGraphics, osascript for app list)
  - Screen Recording permission granted to Terminal / the host process
    (System Settings > Privacy & Security > Screen Recording)
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from amplifier_core import ToolResult

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

# Swift script that lists windows via CoreGraphics.  Zero pip dependencies —
# Swift ships on every Mac with Xcode CLT.  We shell out to `swift -e` because
# the system Python on modern macOS no longer bundles PyObjC.
_SWIFT_WINDOW_LIST = r"""
import CoreGraphics
import Foundation

let options: CGWindowListOption = [.optionAll, .excludeDesktopElements]
guard let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
        as? [[String: Any]] else {
    print("[]")
    Foundation.exit(0)
}

var results: [[String: Any]] = []
for w in windowList {
    let owner  = w["kCGWindowOwnerName"] as? String ?? ""
    let name   = w["kCGWindowName"]      as? String ?? ""
    let wid    = w["kCGWindowNumber"]    as? Int    ?? 0
    let layer  = w["kCGWindowLayer"]     as? Int    ?? 0
    let onScr  = w["kCGWindowIsOnscreen"] as? Bool  ?? false
    let bounds = w["kCGWindowBounds"]    as? [String: Any] ?? [:]

    results.append([
        "window_id":    wid,
        "app_name":     owner,
        "window_title": name,
        "is_on_screen": onScr,
        "layer":        layer,
        "bounds": [
            "x":      bounds["X"]      as? Int ?? 0,
            "y":      bounds["Y"]      as? Int ?? 0,
            "width":  bounds["Width"]  as? Int ?? 0,
            "height": bounds["Height"] as? Int ?? 0,
        ],
    ])
}

let data = try JSONSerialization.data(
    withJSONObject: results, options: [.prettyPrinted, .sortedKeys]
)
print(String(data: data, encoding: .utf8) ?? "[]")
"""


def _get_window_list() -> list[dict[str, Any]]:
    """Return window info from CoreGraphics via inline Swift.

    Uses `swift -e` which is available on every Mac with Xcode CLT installed.
    Window titles require Screen Recording permission — without it, titles
    will be empty strings but window IDs and app names still work.
    """
    result = subprocess.run(
        ["swift", "-e", _SWIFT_WINDOW_LIST],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "xcrun" in stderr or "xcode-select" in stderr:
            raise RuntimeError(
                "Xcode Command Line Tools not installed. "
                "Install with: xcode-select --install"
            )
        raise RuntimeError(f"Swift window list failed: {stderr}")

    return json.loads(result.stdout.strip() or "[]")


# ─── Tool 1: List Running Applications ────────────────────────────────────────


class MacOSListAppsTool:
    """List visible (foreground) running macOS applications."""

    @property
    def name(self) -> str:
        return "macos_screencapture_list_apps"

    @property
    def description(self) -> str:
        return (
            "List all visible running macOS applications (foreground processes). "
            "Returns a JSON array of application names. "
            "Call this first to discover the app name you need for list_windows."
        )

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        script = (
            'tell application "System Events" '
            "to get name of every application process whose background only is false"
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return ToolResult(
                success=False, output=f"osascript error: {result.stderr.strip()}"
            )

        apps = [a.strip() for a in result.stdout.strip().split(",") if a.strip()]
        return ToolResult(success=True, output=json.dumps(apps, indent=2))


# ─── Tool 2: List Windows for an App ──────────────────────────────────────────


class MacOSListWindowsTool:
    """List windows with CoreGraphics IDs for a specific app (or all apps)."""

    @property
    def name(self) -> str:
        return "macos_screencapture_list_windows"

    @property
    def description(self) -> str:
        return (
            "List open windows with their CoreGraphics window IDs for a macOS application. "
            "Returns JSON array of {window_id, app_name, window_title, is_on_screen, bounds}. "
            "The window_id is required by macos_screencapture_capture_window. "
            "Pass app_name to filter (e.g. 'Safari'); omit to list all visible windows. "
            "NOTE: Window titles require Screen Recording permission — without it, "
            "titles will be empty but window IDs and app names still work."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": (
                        "Filter by application name (case-insensitive partial match). "
                        "E.g. 'Safari', 'Xcode', 'Terminal'. "
                        "Omit to return windows for ALL running apps."
                    ),
                },
                "on_screen_only": {
                    "type": "boolean",
                    "description": (
                        "If true, only return windows currently visible on screen. "
                        "Defaults to true."
                    ),
                },
            },
            "required": [],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            all_windows = _get_window_list()
        except RuntimeError as e:
            return ToolResult(success=False, output=str(e))

        app_filter = input_data.get("app_name", "").lower()
        on_screen_only = input_data.get("on_screen_only", True)

        windows = []
        has_any_titles = False

        for w in all_windows:
            if app_filter and app_filter not in w["app_name"].lower():
                continue
            if on_screen_only and not w["is_on_screen"]:
                continue
            # Skip Window Server entries (desktop chrome, not user windows)
            if w["app_name"] == "Window Server":
                continue
            # Skip zero-size windows (menu bar extras, status items)
            if w["bounds"]["width"] == 0 and w["bounds"]["height"] == 0:
                continue
            # Skip windows at non-standard layers (menus, overlays)
            if w.get("layer", 0) != 0:
                continue
            if w["window_title"]:
                has_any_titles = True
            windows.append(w)

        # Detect missing Screen Recording permission
        permission_note = ""
        if windows and not has_any_titles:
            permission_note = (
                "\n\nNOTE: All window titles are empty. This usually means Screen "
                "Recording permission has not been granted. Go to System Settings > "
                "Privacy & Security > Screen Recording and add Terminal (or the "
                "Amplifier host app). Window IDs are still valid for capture."
            )

        output = json.dumps(windows, indent=2) + permission_note
        return ToolResult(success=True, output=output)


# ─── Tool 3: Capture Specific Window ──────────────────────────────────────────


class MacOSCaptureWindowTool:
    """Screenshot a specific macOS window by its CoreGraphics window ID."""

    @property
    def name(self) -> str:
        return "macos_screencapture_capture_window"

    @property
    def description(self) -> str:
        return (
            "Capture a screenshot of a specific macOS window using its CoreGraphics window ID. "
            "Uses screencapture -l <window_id> — works even if the window is behind others. "
            "Get the window_id first from macos_screencapture_list_windows. "
            "Requires Screen Recording permission for the host process. "
            "Returns the saved file path and file size."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "integer",
                    "description": "CoreGraphics window ID from macos_screencapture_list_windows.",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Absolute path for the output file (.png or .jpg). "
                        "Omit to auto-generate a temp file path."
                    ),
                },
            },
            "required": ["window_id"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        window_id = input_data["window_id"]

        if output_path_str := input_data.get("output_path"):
            path = Path(output_path_str)
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, prefix="amplifier_screen_"
            )
            path = Path(tmp.name)
            tmp.close()

        # -l captures specific window, -x suppresses shutter sound
        result = subprocess.run(
            ["screencapture", "-l", str(window_id), "-x", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "could not create image" in stderr.lower():
                return ToolResult(
                    success=False,
                    output=(
                        f"Could not capture window {window_id}. This usually means "
                        "Screen Recording permission has not been granted. "
                        "Go to System Settings > Privacy & Security > Screen Recording "
                        "and add Terminal (or the Amplifier host app), then restart it."
                    ),
                )
            return ToolResult(
                success=False,
                output=f"screencapture error: {stderr}",
            )

        if not path.exists() or path.stat().st_size == 0:
            return ToolResult(
                success=False,
                output=f"No output produced at {path}. Is the window_id valid?",
            )

        return ToolResult(
            success=True,
            output=json.dumps(
                {
                    "screenshot_path": str(path),
                    "window_id": window_id,
                    "file_size_bytes": path.stat().st_size,
                },
                indent=2,
            ),
        )


# ─── Tool 4: Capture Full Screen ──────────────────────────────────────────────


class MacOSCaptureFullScreenTool:
    """Capture the full screen (all content on a given display)."""

    @property
    def name(self) -> str:
        return "macos_screencapture_full_screen"

    @property
    def description(self) -> str:
        return (
            "Capture a full-screen screenshot of a macOS display. "
            "Use when you need the complete screen state, not just a specific window. "
            "Returns the saved file path and file size."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "display": {
                    "type": "integer",
                    "description": (
                        "Display number to capture (1 = main display, 2 = secondary). "
                        "Defaults to main display."
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Absolute path for the output file (.png or .jpg). "
                        "Omit to auto-generate a temp file path."
                    ),
                },
            },
            "required": [],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        display = input_data.get("display")

        if output_path_str := input_data.get("output_path"):
            path = Path(output_path_str)
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, prefix="amplifier_screen_"
            )
            path = Path(tmp.name)
            tmp.close()

        cmd = ["screencapture", "-x"]
        if display is not None:
            cmd.append(f"-D{display}")
        cmd.append(str(path))

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return ToolResult(
                success=False,
                output=f"screencapture error: {result.stderr.strip()}",
            )

        if not path.exists() or path.stat().st_size == 0:
            return ToolResult(
                success=False, output=f"No output produced at {path}"
            )

        return ToolResult(
            success=True,
            output=json.dumps(
                {
                    "screenshot_path": str(path),
                    "display": display or "main",
                    "file_size_bytes": path.stat().st_size,
                },
                indent=2,
            ),
        )


# ─── mount() — The Iron Law ──────────────────────────────────────────────────


async def mount(
    coordinator: Any, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Mount all macOS screencapture tools.

    IRON LAW: mount() MUST call coordinator.mount() for every tool.
    """
    tools = [
        MacOSListAppsTool(),
        MacOSListWindowsTool(),
        MacOSCaptureWindowTool(),
        MacOSCaptureFullScreenTool(),
    ]
    for tool in tools:
        await coordinator.mount("tools", tool, name=tool.name)

    provided = [t.name for t in tools]
    logger.info("tool-macos-screencapture mounted: %s", ", ".join(provided))
    return {
        "name": "tool-macos-screencapture",
        "version": "0.1.0",
        "provides": provided,
    }
