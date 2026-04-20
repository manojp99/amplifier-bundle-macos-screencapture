"""Tests for tool-macos-screencapture mount and tool contracts."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from amplifier_module_tool_macos_screencapture import mount


@pytest.mark.asyncio
async def test_mount_registers_all_four_tools():
    """mount() must register all four tools via coordinator.mount()."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    result = await mount(coordinator)

    # Iron Law: coordinator.mount() must be called (once per tool = 4 times)
    assert coordinator.mount.call_count == 4

    # Every call must target "tools" as the first arg
    for call in coordinator.mount.call_args_list:
        assert call[0][0] == "tools"

    # Return value must be a metadata dict, not None
    assert result is not None
    assert result["name"] == "tool-macos-screencapture"
    assert len(result["provides"]) == 4


@pytest.mark.asyncio
async def test_all_tools_have_required_properties():
    """Every registered tool must have name, description, input_schema, execute."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    await mount(coordinator)

    for call in coordinator.mount.call_args_list:
        tool = call[0][1]
        assert isinstance(tool.name, str) and tool.name
        assert isinstance(tool.description, str) and len(tool.description) > 20
        assert isinstance(tool.input_schema, dict)
        assert callable(tool.execute)


@pytest.mark.asyncio
async def test_mount_returns_correct_tool_names():
    """mount() return value must list all four tool names."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    result = await mount(coordinator)

    expected_names = {
        "macos_screencapture_list_apps",
        "macos_screencapture_list_windows",
        "macos_screencapture_capture_window",
        "macos_screencapture_full_screen",
    }
    assert set(result["provides"]) == expected_names


@pytest.mark.asyncio
async def test_tool_names_match_registration():
    """Tool.name must match the name= kwarg passed to coordinator.mount()."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    await mount(coordinator)

    for call in coordinator.mount.call_args_list:
        tool = call[0][1]
        registered_name = call[1]["name"]
        assert tool.name == registered_name
