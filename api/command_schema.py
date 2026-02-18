# command_schema.py - Typed command envelopes for SpaceOS Ably communication
#
# Shared command types used between the web backend and SpaceOS firmware.
# The backend publishes these via Ably; the firmware validates and routes them.

from enum import Enum
from typing import Optional


class CommandType(str, Enum):
    """Command types sent over the Ably commands channel."""

    # Content sync commands
    MESSAGE_SYNC = "message_sync"  # New message -> /inbox
    ART_SYNC = "art_sync"          # New art -> /art

    # Board control commands
    SET_MODE = "set_mode"                # Change display mode (inbox/art)
    SET_AUTO_ROTATE = "set_auto_rotate"  # Toggle auto-rotate
    SET_BRIGHTNESS = "set_brightness"    # Set brightness level

    # Sync commands
    SYNC_REQUEST = "sync_request"        # Request board to re-sync from server


def build_message_sync(message_id: str, width: int, height: int, frames: int, fps: int) -> dict:
    """Build a message_sync command envelope for inbox delivery."""
    return {
        "type": CommandType.MESSAGE_SYNC.value,
        "messageId": message_id,
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
    }


def build_art_sync(message_id: str, width: int, height: int, frames: int, fps: int) -> dict:
    """Build an art_sync command envelope for art directory delivery."""
    return {
        "type": CommandType.ART_SYNC.value,
        "messageId": message_id,
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
    }


def build_set_mode(mode: str) -> dict:
    """Build a set_mode command envelope."""
    return {
        "type": CommandType.SET_MODE.value,
        "mode": mode,  # "inbox" or "art"
    }


def build_set_auto_rotate(enabled: bool) -> dict:
    """Build a set_auto_rotate command envelope."""
    return {
        "type": CommandType.SET_AUTO_ROTATE.value,
        "enabled": enabled,
    }


def build_set_brightness(brightness: float) -> dict:
    """Build a set_brightness command envelope."""
    return {
        "type": CommandType.SET_BRIGHTNESS.value,
        "brightness": max(0.0, min(1.0, brightness)),
    }


def build_sync_request() -> dict:
    """Build a sync_request command envelope."""
    return {
        "type": CommandType.SYNC_REQUEST.value,
    }


def validate_command_envelope(payload: dict) -> Optional[str]:
    """
    Validate a command envelope's type field.

    Returns the command type string if valid, None if invalid.
    """
    cmd_type = payload.get("type")
    if cmd_type is None:
        return None

    valid_types = {t.value for t in CommandType}
    if cmd_type not in valid_types:
        return None

    return cmd_type
